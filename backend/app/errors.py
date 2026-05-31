"""RFC 7807 problem+json error helpers."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ProblemDetail(Exception):
    """An error that should serialize as RFC 7807 application/problem+json."""

    def __init__(
        self,
        *,
        status: int,
        code: str,
        title: str,
        detail: str | None = None,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.extra = extra or {}
        self.headers = headers or {}
        super().__init__(f"{code}: {detail or title}")

    def to_response(self, request: Request | None = None) -> JSONResponse:
        body: dict[str, Any] = {
            "type": f"about:blank#{self.code}",
            "title": self.title,
            "status": self.status,
            "code": self.code,
        }
        if self.detail:
            body["detail"] = self.detail
        if request is not None:
            body["instance"] = str(request.url)
        body.update(self.extra)
        return JSONResponse(
            status_code=self.status,
            content=body,
            headers=self.headers,
            media_type="application/problem+json",
        )


# Commonly used factories
def not_found(code: str, what: str) -> ProblemDetail:
    return ProblemDetail(status=404, code=code, title="Not Found", detail=f"{what} not found")


def bad_request(code: str, detail: str) -> ProblemDetail:
    return ProblemDetail(status=400, code=code, title="Bad Request", detail=detail)


def conflict(code: str, detail: str) -> ProblemDetail:
    return ProblemDetail(status=409, code=code, title="Conflict", detail=detail)


def unauthorized(code: str = "auth.required", detail: str = "Authentication required") -> ProblemDetail:
    return ProblemDetail(status=401, code=code, title="Unauthorized", detail=detail)


def forbidden(code: str = "auth.forbidden", detail: str = "Forbidden") -> ProblemDetail:
    return ProblemDetail(status=403, code=code, title="Forbidden", detail=detail)


def precondition_failed(code: str = "etag.mismatch", detail: str = "ETag mismatch") -> ProblemDetail:
    return ProblemDetail(status=412, code=code, title="Precondition Failed", detail=detail)
