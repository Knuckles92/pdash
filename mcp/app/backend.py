"""Thin async HTTP wrapper around the FastAPI backend's ``/api/v1/internal/*``
surface.

Responsibilities:

- Attach the service-secret Bearer + ``X-Agent-Id`` headers on each call.
- Pass through the caller-supplied (or MCP-server-generated)
  ``Idempotency-Key`` header on POSTs.
- Convert non-2xx ``application/problem+json`` responses into a typed
  :class:`BackendError`.

Translation between BackendError and MCP error / payload-level statuses
lives in ``tools.py`` — this module deliberately stays dumb.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    agent_id: str
    display_name: str
    status: str
    permissions: dict[str, Any]


class BackendError(Exception):
    """A backend call returned a non-2xx response.

    ``code`` mirrors the RFC 7807 ``code`` field (e.g. ``module.not_found``,
    ``rate_limit.exceeded``, ``agent.disabled``). Use it to map to the right
    MCP error type or payload-level outcome.
    """

    def __init__(
        self,
        *,
        status: int,
        code: str,
        detail: str | None = None,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(f"{status} {code}: {detail or ''}".strip())
        self.status = status
        self.code = code
        self.detail = detail
        self.extra = extra or {}
        self.headers = headers or {}

    @property
    def retry_after_ms(self) -> int | None:
        """Convenience: pull the retry hint either from extras or the header."""
        if "retry_after_ms" in self.extra:
            try:
                return int(self.extra["retry_after_ms"])
            except (TypeError, ValueError):
                pass
        ra = self.headers.get("retry-after") or self.headers.get("Retry-After")
        if ra is not None:
            try:
                return int(float(ra) * 1000)
            except ValueError:
                return None
        return None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class BackendClient:
    """Async client. Construct one per process; reused across requests."""

    def __init__(self, *, base_url: str | None = None, service_secret: str | None = None) -> None:
        settings = get_settings()
        self._base = (base_url or settings.backend_url).rstrip("/")
        self._secret = service_secret if service_secret is not None else settings.service_secret
        self._client = httpx.AsyncClient(
            base_url=self._base,
            timeout=settings.backend_timeout_s,
            headers={"User-Agent": "pdash-mcp/0.1"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---- low-level ---------------------------------------------------------

    def _headers(
        self,
        *,
        agent_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, str]:
        h: dict[str, str] = {"Authorization": f"Bearer {self._secret}"}
        if agent_id is not None:
            h["X-Agent-Id"] = agent_id
        if idempotency_key is not None:
            h["Idempotency-Key"] = idempotency_key
        return h

    def sse_stream_request(self) -> tuple[str, dict[str, str]]:
        """Return ``(url, headers)`` for streaming the internal events feed.

        Lets the decision-cache SSE consumer reuse this client's configured
        base URL + auth without reaching into private attributes.
        """
        url = self._base.rstrip("/") + "/api/v1/internal/events"
        headers = self._headers()
        headers["Accept"] = "text/event-stream"
        return url, headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        agent_id: str | None = None,
        idempotency_key: str | None = None,
        json: Any = None,
        params: dict[str, Any] | None = None,
        accept_statuses: tuple[int, ...] = (200, 201, 202, 204),
    ) -> tuple[int, dict[str, Any], dict[str, str]]:
        """Returns ``(status_code, body, response_headers)``.

        ``accept_statuses`` controls which response codes are treated as
        success; the rest become :class:`BackendError`. The internal triad
        endpoints use 200 (applied), 202 (pending), 403 (denied_by_rule), and
        500 (application_failed), all of which carry useful payload — so the
        caller passes them all in.
        """
        try:
            resp = await self._client.request(
                method,
                path,
                headers=self._headers(agent_id=agent_id, idempotency_key=idempotency_key),
                json=json,
                params=params,
            )
        except httpx.HTTPError as exc:
            # Network-level failure: surface as 503-equivalent.
            raise BackendError(
                status=503,
                code="backend.unreachable",
                detail=f"backend transport error: {exc!s}",
            ) from exc

        body: dict[str, Any]
        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = {"_raw": resp.text}
        headers = dict(resp.headers)

        if resp.status_code in accept_statuses:
            return resp.status_code, body, headers
        # Error path: turn problem+json into BackendError.
        code = body.get("code") or f"http.{resp.status_code}"
        detail = body.get("detail") or body.get("title") or resp.text
        # Strip _internal keys; pass through known extras (rule_id, retry_after_ms…)
        extra = {k: v for k, v in body.items() if not k.startswith("_") and k not in {
            "type", "title", "status", "code", "detail", "instance"
        }}
        raise BackendError(
            status=resp.status_code,
            code=code,
            detail=detail,
            extra=extra,
            headers=headers,
        )

    async def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        agent_id: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[bytes, str]:
        """Like :meth:`_request` but returns raw ``(content, content_type)``.

        Used for binary endpoints (e.g. screenshots) that don't return JSON. A
        non-2xx response is parsed as problem+json into a :class:`BackendError`.
        """
        try:
            resp = await self._client.request(
                method, path, headers=self._headers(agent_id=agent_id), params=params
            )
        except httpx.HTTPError as exc:
            raise BackendError(
                status=503,
                code="backend.unreachable",
                detail=f"backend transport error: {exc!s}",
            ) from exc
        if resp.status_code == 200:
            return resp.content, resp.headers.get("content-type", "application/octet-stream")
        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = {}
        code = body.get("code") or f"http.{resp.status_code}"
        detail = body.get("detail") or body.get("title") or resp.text
        raise BackendError(
            status=resp.status_code,
            code=code,
            detail=detail,
            headers=dict(resp.headers),
        )

    # ---- auth --------------------------------------------------------------

    async def resolve_key(self, api_key: str) -> AgentInfo | None:
        """Resolve a raw agent API key to an agent. Returns ``None`` on 401."""
        try:
            _, body, _ = await self._request(
                "POST",
                "/api/v1/internal/auth/resolve-key",
                json={"api_key": api_key},
            )
        except BackendError as exc:
            if exc.status == 401:
                return None
            raise
        return AgentInfo(
            agent_id=body["agent_id"],
            display_name=body["display_name"],
            status=body["status"],
            permissions=body.get("permissions") or {},
        )

    async def whoami(self, agent_id: str) -> dict[str, Any]:
        _, body, _ = await self._request("GET", "/api/v1/internal/whoami", agent_id=agent_id)
        return body

    # ---- agent self-registration (ungated bootstrap) ----------------------
    # No agent_id is sent — these are callable on behalf of a keyless client,
    # authenticated by the shared service secret alone (like resolve_key).

    async def register_agent(self, *, body: dict[str, Any]) -> dict[str, Any]:
        """Create a pending agent-registration request. Returns a claim token."""
        _, out, _ = await self._request(
            "POST",
            "/api/v1/internal/bootstrap/register",
            json=body,
            accept_statuses=(200, 201),
        )
        return out

    async def claim_registration(self, *, body: dict[str, Any]) -> dict[str, Any]:
        """Poll a registration; the minted key is returned once on approval."""
        _, out, _ = await self._request(
            "POST",
            "/api/v1/internal/bootstrap/claim",
            json=body,
            accept_statuses=(200,),
        )
        return out

    # ---- module schema -----------------------------------------------------

    async def module_schema(self, agent_id: str, module_type: str) -> dict[str, Any]:
        _, body, _ = await self._request(
            "GET",
            f"/api/v1/internal/module-schema/{module_type}",
            agent_id=agent_id,
        )
        return body

    async def list_module_schemas(self, agent_id: str) -> dict[str, Any]:
        _, body, _ = await self._request(
            "GET", "/api/v1/internal/module-schemas", agent_id=agent_id
        )
        return body

    async def validate_module(self, agent_id: str, *, body: dict[str, Any]) -> dict[str, Any]:
        _, out, _ = await self._request(
            "POST", "/api/v1/internal/validate-module", agent_id=agent_id, json=body
        )
        return out

    # ---- visibility tools --------------------------------------------------

    async def module_health(
        self,
        agent_id: str,
        *,
        page_id: str | None = None,
        only_broken: bool = False,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "only_broken": str(only_broken).lower()}
        if page_id is not None:
            params["page_id"] = page_id
        if cursor is not None:
            params["cursor"] = cursor
        _, body, _ = await self._request(
            "GET", "/api/v1/internal/module-health", agent_id=agent_id, params=params
        )
        return body

    async def render_page(self, agent_id: str, page_id: str) -> dict[str, Any]:
        _, body, _ = await self._request(
            "GET", f"/api/v1/internal/pages/{page_id}/render", agent_id=agent_id
        )
        return body

    async def page_screenshot(
        self,
        agent_id: str,
        page_id: str,
        *,
        viewport_width: int | None = None,
        full_page: bool = True,
    ) -> tuple[bytes, str]:
        params: dict[str, Any] = {"full_page": str(full_page).lower()}
        if viewport_width is not None:
            params["viewport_width"] = viewport_width
        return await self._request_bytes(
            "GET",
            f"/api/v1/internal/pages/{page_id}/screenshot",
            agent_id=agent_id,
            params=params,
        )

    # ---- read tools --------------------------------------------------------

    async def list_my_modules(
        self,
        agent_id: str,
        *,
        page_id: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if page_id is not None:
            params["page_id"] = page_id
        if cursor is not None:
            params["cursor"] = cursor
        _, body, _ = await self._request(
            "GET", "/api/v1/internal/my-modules", agent_id=agent_id, params=params
        )
        return body

    async def get_module(self, agent_id: str, module_id: str) -> dict[str, Any]:
        _, body, _ = await self._request(
            "GET", f"/api/v1/internal/modules/{module_id}", agent_id=agent_id
        )
        return body

    async def list_pages(
        self, agent_id: str, *, cursor: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        _, body, _ = await self._request(
            "GET", "/api/v1/internal/pages", agent_id=agent_id, params=params
        )
        return body

    async def list_my_pending_requests(
        self,
        agent_id: str,
        *,
        status_filter: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if status_filter is not None:
            params["status_filter"] = status_filter
        if cursor is not None:
            params["cursor"] = cursor
        _, body, _ = await self._request(
            "GET",
            "/api/v1/internal/my-pending-requests",
            agent_id=agent_id,
            params=params,
        )
        return body

    # ---- files -------------------------------------------------------------

    async def file_dropbox(
        self, agent_id: str, *, page_id: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if page_id is not None:
            params["page_id"] = page_id
        _, body, _ = await self._request(
            "GET", "/api/v1/internal/file-dropbox", agent_id=agent_id, params=params
        )
        return body

    async def my_files(
        self, agent_id: str, *, cursor: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        _, body, _ = await self._request(
            "GET", "/api/v1/internal/my-files", agent_id=agent_id, params=params
        )
        return body

    # ---- write tools (the internal triad endpoints) ------------------------

    async def propose_module(
        self,
        agent_id: str,
        *,
        idempotency_key: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        status, body_out, _ = await self._request(
            "POST",
            "/api/v1/internal/propose-module",
            agent_id=agent_id,
            idempotency_key=idempotency_key,
            json=body,
            accept_statuses=(200, 202, 403, 500),
        )
        return status, body_out

    async def update_module(
        self,
        agent_id: str,
        *,
        idempotency_key: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        status, body_out, _ = await self._request(
            "POST",
            "/api/v1/internal/update-module",
            agent_id=agent_id,
            idempotency_key=idempotency_key,
            json=body,
            accept_statuses=(200, 202, 403, 500),
        )
        return status, body_out

    async def delete_module(
        self,
        agent_id: str,
        *,
        idempotency_key: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        status, body_out, _ = await self._request(
            "POST",
            "/api/v1/internal/delete-module",
            agent_id=agent_id,
            idempotency_key=idempotency_key,
            json=body,
            accept_statuses=(200, 202, 403, 500),
        )
        return status, body_out

    async def propose_page(
        self,
        agent_id: str,
        *,
        idempotency_key: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        status, body_out, _ = await self._request(
            "POST",
            "/api/v1/internal/propose-page",
            agent_id=agent_id,
            idempotency_key=idempotency_key,
            json=body,
            accept_statuses=(200, 202, 403, 500),
        )
        return status, body_out

    async def fire_action(
        self,
        agent_id: str,
        *,
        idempotency_key: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        status, body_out, _ = await self._request(
            "POST",
            "/api/v1/internal/fire-action",
            agent_id=agent_id,
            idempotency_key=idempotency_key,
            json=body,
            accept_statuses=(200, 202, 403, 500),
        )
        return status, body_out

    async def append_log(
        self,
        agent_id: str,
        *,
        idempotency_key: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        status, body_out, _ = await self._request(
            "POST",
            "/api/v1/internal/append-log",
            agent_id=agent_id,
            idempotency_key=idempotency_key,
            json=body,
            accept_statuses=(200, 202, 403, 500),
        )
        return status, body_out

    async def register_file(
        self,
        agent_id: str,
        *,
        idempotency_key: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        status, body_out, _ = await self._request(
            "POST",
            "/api/v1/internal/register-file",
            agent_id=agent_id,
            idempotency_key=idempotency_key,
            json=body,
            accept_statuses=(200, 202, 403, 500),
        )
        return status, body_out


# ---------------------------------------------------------------------------
# Process-singleton accessor (lazy)
# ---------------------------------------------------------------------------


_client: BackendClient | None = None


def get_client() -> BackendClient:
    global _client
    if _client is None:
        _client = BackendClient()
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def set_client_for_tests(client: BackendClient | None) -> None:
    """Test hook."""
    global _client
    _client = client
