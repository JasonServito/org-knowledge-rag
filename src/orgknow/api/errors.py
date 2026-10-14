"""The API's one error shape (S14-R1 decision 1; docs/interfaces.md, "Errors"): the codes and the
status of each, the envelope, the exception the routes raise, and the handlers that turn errors
into envelopes. An unexpected exception becomes the `internal` 500 in the middleware instead
(api/middleware.py), the only place that can still add the request ID to it."""

from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.requests import Request

from orgknow.logs import request_id

ERROR_CODES: dict[str, int] = {
    "invalid_request": 422,
    "not_found": 404,
    "upstream_failed": 502,
    "database_unavailable": 503,
    "internal": 500,
}


class ErrorDetail(BaseModel):
    code: str  # one of ERROR_CODES: a client switches on it, never on the message
    message: str  # one line; never a traceback, a secret, a database URL or the caller's input
    request_id: str  # the response's X-Request-ID header


class ErrorEnvelope(BaseModel):
    """Every error response's body: `{"error": {"code", "message", "request_id"}}`."""

    error: ErrorDetail


class ApiError(Exception):
    """An expected failure a route reports: its code, the code's status, and a message that is
    safe to show (docs/interfaces.md, "Message rules")."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status = ERROR_CODES[code]
        self.message = message


def error_response(code: str, message: str) -> JSONResponse:
    """The envelope of `code` at its status, with the current request's ID (the middleware sets
    it for every request)."""
    detail = ErrorDetail(code=code, message=message, request_id=request_id.get() or "")
    return JSONResponse(ErrorEnvelope(error=detail).model_dump(), status_code=ERROR_CODES[code])


async def api_error(_: Request, error: ApiError) -> Response:
    return error_response(error.code, error.message)


async def invalid_request(_: Request, error: RequestValidationError) -> Response:
    """A 422 `invalid_request` naming where the first validation error is and what is wrong, e.g.
    `body.question: Field required`. Never the value sent (the error's `input`)."""
    first = error.errors()[0]
    where = ".".join(str(part) for part in first["loc"])
    return error_response("invalid_request", f"{where}: {first['msg']}")


async def http_error(request: Request, error: HTTPException) -> Response:
    """Starlette's own HTTP errors. A 404 (no route for the path) is `not_found`; any other (a 405:
    the wrong method) keeps FastAPI's default body, `{"detail": ...}`."""
    if error.status_code == 404:
        return error_response("not_found", "Not Found")
    return await http_exception_handler(request, error)
