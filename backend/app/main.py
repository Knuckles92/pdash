"""FastAPI app entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse

from .api import (
    about as about_api,
)
from .api import (
    action_targets,
    iframe_allowlist,
    module_schemas,
)
from .api import (
    activity_log as activity_log_api,
)
from .api import (
    agent_registrations as agent_registrations_api,
)
from .api import (
    agents as agents_api,
)
from .api import (
    approval_requests as approval_requests_api,
)
from .api import (
    approval_rules as approval_rules_api,
)
from .api import (
    auth as auth_api,
)
from .api import (
    events as events_api,
)
from .api import (
    files as files_api,
)
from .api import (
    internal as internal_api,
)
from .api import (
    internal_auth as internal_auth_api,
)
from .api import (
    internal_bootstrap as internal_bootstrap_api,
)
from .api import (
    mcp_status as mcp_status_api,
)
from .api import (
    modules as modules_api,
)
from .api import (
    page_agent_access as page_agent_access_api,
)
from .api import (
    pages as pages_api,
)
from .auth.deps import CurrentUser, require_session
from .config import get_settings
from .errors import ProblemDetail
from .logging_config import configure_logging
from .version import app_version

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    # Ensure the agent file-drop inbox + managed store dirs exist (native dev
    # runs without the Docker entrypoint, which also creates them).
    settings = get_settings()
    for path in (settings.resolved_files_inbox_path(), settings.resolved_files_store_path()):
        path.mkdir(parents=True, exist_ok=True)
    logger.info("pdash backend starting")
    yield
    logger.info("pdash backend shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    openapi_url = "/api/v1/openapi.json"
    app = FastAPI(
        title="pdash",
        version=app_version(),
        docs_url=None,
        redoc_url=None,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # ----- Exception handlers -------------------------------------------------
    @app.exception_handler(ProblemDetail)
    async def _problem_handler(request: Request, exc: ProblemDetail) -> JSONResponse:
        return exc.to_response(request)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # noqa: ARG001
        logger.exception("Unhandled error")
        problem = ProblemDetail(
            status=500,
            code="internal.error",
            title="Internal Server Error",
            detail="An unexpected error occurred.",
        )
        return problem.to_response(request)

    # ----- Health -------------------------------------------------------------
    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> dict:
        # Phase 1: no DB ping required (per spec). Just respond.
        return {"status": "ready"}

    # ----- Docs (session-gated) ----------------------------------------------
    if settings.docs_enabled:

        @app.get("/api/v1/docs", include_in_schema=False)
        async def docs(_: Annotated[CurrentUser, Depends(require_session)]):
            return get_swagger_ui_html(
                openapi_url=openapi_url,
                title="pdash · API docs",
            )

    # ----- Routers -----------------------------------------------------------
    app.include_router(about_api.router)
    app.include_router(auth_api.router)
    app.include_router(module_schemas.router)
    app.include_router(modules_api.router)
    app.include_router(pages_api.router)
    app.include_router(page_agent_access_api.router)
    app.include_router(agents_api.router)
    app.include_router(agent_registrations_api.router)
    app.include_router(mcp_status_api.router)
    app.include_router(iframe_allowlist.router)
    app.include_router(action_targets.router)
    app.include_router(files_api.router)
    # Phase 3 routers
    app.include_router(approval_requests_api.router)
    app.include_router(approval_rules_api.router)
    app.include_router(activity_log_api.router)
    app.include_router(internal_api.router)
    app.include_router(internal_auth_api.router)
    app.include_router(internal_bootstrap_api.router)
    # Phase 5: SSE
    app.include_router(events_api.router)

    return app


app = create_app()
