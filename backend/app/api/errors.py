"""RFC 9457 problem details for the API.

Every client-facing failure answers with this shape (docs/api.md):

    { "status": 404, "title": "Not Found", "detail": "..." }

`detail` is user-facing: no stack traces, no secrets, no internal identifiers.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class HTTPProblem(HTTPException):
    """An error rendered as an RFC 9457 problem document."""

    def __init__(self, status_code: int, detail: str, title: str | None = None) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.title = title or _DEFAULT_TITLES.get(status_code, "Error")


_DEFAULT_TITLES = {
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Content",
    429: "Too Many Requests",
    500: "Internal Server Error",
}


async def http_problem_handler(_request: Request, exc: HTTPProblem) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": exc.status_code,
            "title": exc.title,
            "detail": exc.detail,
        },
    )
