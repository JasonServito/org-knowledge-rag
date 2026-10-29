"""The JSON log formatter and the request-ID context variable (S14-T2), and `make serve`'s log
config. Expected lines are typed by hand from docs/interfaces.md ("Logs")."""

import json
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from orgknow.logs import JsonFormatter, request_id

ROOT = Path(__file__).parents[2]
# The docs' example time, 2026-10-13 22:05:11.250 UTC, as the Unix time a log record holds.
CREATED = datetime(2026, 10, 13, 22, 5, 11, 250000, tzinfo=UTC).timestamp()
DOCS_ID = "0b9f6c2e8d0a4f6b9c1d2e3f4a5b6c7d"


def _record(level: int, message: str, **extra: object) -> logging.LogRecord:
    """A record of `orgknow.api.middleware` at the docs' example time; `extra` as `extra=` adds."""
    return logging.makeLogRecord(
        {
            "name": "orgknow.api.middleware",
            "levelno": level,
            "levelname": logging.getLevelName(level),
            "msg": message,
            "created": CREATED,
            **extra,
        }
    )


def test_a_request_line_is_the_docs_example() -> None:
    record = _record(
        logging.INFO,
        "GET /health 200",
        method="GET",
        path="/health",
        status=200,
        duration_ms=1.4,
    )
    token = request_id.set(DOCS_ID)
    try:
        line = JsonFormatter().format(record)
    finally:
        request_id.reset(token)

    # docs/interfaces.md's example line, copied character for character.
    assert line == (
        '{"ts": "2026-10-13T22:05:11.250+00:00", "level": "INFO", '
        '"logger": "orgknow.api.middleware", "message": "GET /health 200", '
        '"request_id": "0b9f6c2e8d0a4f6b9c1d2e3f4a5b6c7d", "method": "GET", "path": "/health", '
        '"status": 200, "duration_ms": 1.4}'
    )


def test_outside_a_request_a_line_has_no_request_id() -> None:
    line = JsonFormatter().format(_record(logging.WARNING, "a warning outside any request"))

    assert json.loads(line) == {
        "ts": "2026-10-13T22:05:11.250+00:00",
        "level": "WARNING",
        "logger": "orgknow.api.middleware",
        "message": "a warning outside any request",
    }


def test_an_error_line_carries_its_traceback_as_text_on_one_line() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        exc_info = sys.exc_info()
    record = _record(logging.ERROR, "unexpected error", exc_info=exc_info)

    line = JsonFormatter().format(record)

    assert "\n" not in line  # one line: the traceback's newlines are escaped
    fields = json.loads(line)
    assert fields["exc_info"].startswith("Traceback (most recent call last):\n")
    assert fields["exc_info"].endswith("RuntimeError: boom")


def test_non_ascii_is_written_as_is_and_uvicorns_color_copy_is_left_out() -> None:
    record = _record(logging.INFO, "café ✓", color_message="\x1b[32mcafé ✓\x1b[0m")

    line = JsonFormatter().format(record)

    assert '"message": "café ✓"' in line
    assert "color_message" not in line


def test_serve_log_config_writes_json_lines_for_the_app_uvicorn_and_library_warnings() -> None:
    # A fresh interpreter, so configuring logging can't touch this test process. It loads
    # config/logging.json the way uvicorn's --log-config does (`dictConfig` of the JSON).
    script = "\n".join(
        [
            "import json, logging, logging.config",
            "from orgknow.logs import request_id",
            "with open('config/logging.json') as file:",
            "    logging.config.dictConfig(json.load(file))",
            "logging.getLogger('uvicorn.error').info('Application startup complete.')",
            "request_id.set('req-1')",
            "logging.getLogger('orgknow.api.middleware').info('GET /health 200')",
            "logging.getLogger('httpx').info('a library info line')",
            "logging.getLogger('langfuse').warning('a library warning')",
        ]
    )

    result = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, check=True
    )

    lines = [json.loads(line) for line in result.stderr.splitlines()]
    # The library's INFO line is left out: only the app and uvicorn log at INFO.
    assert [
        (line["logger"], line["level"], line["message"], line.get("request_id")) for line in lines
    ] == [
        ("uvicorn.error", "INFO", "Application startup complete.", None),
        ("orgknow.api.middleware", "INFO", "GET /health 200", "req-1"),
        ("langfuse", "WARNING", "a library warning", "req-1"),
    ]
    assert result.stdout == ""
