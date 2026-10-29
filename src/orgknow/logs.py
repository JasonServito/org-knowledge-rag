"""JSON log lines and the current request's ID (S14-T2; docs/interfaces.md, "Logs").

`JsonFormatter` writes each log record as one JSON object on one line. Only `make serve` uses it,
through uvicorn's log config (config/logging.json): library code never configures logging, so the
CLI's stderr lines stay plain text. `request_id` holds the ID of the request being served; the
API's middleware sets it, and every line written meanwhile carries it, from any thread the
request runs in. S14-R2's worker reuses both.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

# The ID of the request being served, or None outside a request. A context variable, not a
# global: concurrent requests each see their own, and a worker thread gets a copy of it.
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

# The attributes every log record has, and the 2 a formatter may add (`message`, `asctime`); any
# other attribute came from `extra=`. Also left out: `color_message`, uvicorn's copy of some of
# its messages with terminal color codes.
_NOT_EXTRA = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "color_message"}


class JsonFormatter(logging.Formatter):
    """A record as one line of JSON: `ts` (UTC, milliseconds), `level`, `logger`, `message`, then
    `request_id` inside a request, the fields passed with `extra=`, and `exc_info` (the traceback
    as text) when the record has one."""

    def format(self, record: logging.LogRecord) -> str:
        fields: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        current = request_id.get()
        if current is not None:
            fields["request_id"] = current
        fields |= {key: value for key, value in vars(record).items() if key not in _NOT_EXTRA}
        if record.exc_info:
            fields["exc_info"] = self.formatException(record.exc_info)
        # `default=str`: an extra field JSON can't encode is written as its text, not an error.
        return json.dumps(fields, ensure_ascii=False, default=str)
