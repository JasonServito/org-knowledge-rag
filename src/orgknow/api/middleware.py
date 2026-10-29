"""The request-ID middleware (S14-T2; docs/interfaces.md, "Request IDs" and "Logs").

For each HTTP request it picks the request's ID, sets it for the request's log lines, adds it to
the response as `X-Request-ID`, and writes the request's one log line after the response. It also
turns an unexpected exception into the `internal` 500 envelope: Starlette's own 500 is sent by a
layer outside every middleware, so it would have no `X-Request-ID` (an S14-R1 probe).

A pure ASGI middleware (a class called with scope, receive, send), not Starlette's
`BaseHTTPMiddleware`, which runs the app in another task.
"""

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from orgknow.api.errors import error_response
from orgknow.logs import request_id

log = logging.getLogger(__name__)

# A caller's ID is kept only if the whole value is 1 to 64 of these characters, so it can't
# inject a line break or other text into a log line. `fullmatch`: `$` would allow a final "\n".
_VALID_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def choose_request_id(given: str | None) -> str:
    """The caller's `X-Request-ID` when valid, else a new random ID of 32 lowercase hex
    characters."""
    if given is not None and _VALID_ID.fullmatch(given):
        return given
    return uuid.uuid4().hex


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # the lifespan's startup and shutdown messages
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        method, path = scope["method"], scope["path"]  # the path has no query string
        # ASGI servers send header names in lowercase, and names and values as bytes.
        given = dict(scope["headers"]).get(b"x-request-id")
        current = choose_request_id(None if given is None else given.decode("latin-1"))
        token = request_id.set(current)
        status: int | None = None  # set when the response starts

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                id_header = (b"x-request-id", current.encode())
                message["headers"] = [*message.get("headers", []), id_header]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            if status is not None:  # the response has started: too late to send another
                raise
            log.exception("unexpected error")  # the traceback goes to the log, never the body
            await error_response("internal", "internal error")(scope, receive, send_with_id)
        finally:
            if status is not None:  # a response was sent
                fields: dict[str, object] = {
                    "method": method,
                    "path": path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                }
                # POST /query's Langfuse trace ID, when tracing is on (api/app.py stores it in
                # the request's state, which lives in the scope).
                trace_id = scope.get("state", {}).get("trace_id")
                if trace_id is not None:
                    fields["trace_id"] = trace_id
                log.info("%s %s %d", method, path, status, extra=fields)
            request_id.reset(token)
