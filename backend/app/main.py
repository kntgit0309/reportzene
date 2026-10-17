"""ReportZenE API: /api/v1 routes, /mcp for AI agents, SPA from web/dist."""
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app import mcp_server, models  # noqa: F401  (register tables)
from app.config import settings
from app.core import errors
from app.core.errors import AppError
from app.core.security import hash_password
from app.db import Base, SessionLocal, engine
from app.db_migrate import add_missing_columns
from app.models import User
from app.routers import auth, plan, report, sheets, tokens, users
from app.routers import settings as settings_router
from app.services.naming import clean_code

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("rzn")
ROUTERS = (auth, tokens, users, report, plan, sheets, settings_router)


def bootstrap_admin() -> None:
    """Create the first admin from BOOTSTRAP_* env when there are no users yet."""
    if not (settings.bootstrap_email and settings.bootstrap_password):
        return
    with SessionLocal() as db:
        if db.scalar(select(func.count(User.id))):
            return
        db.add(User(email=settings.bootstrap_email.lower(), name=settings.bootstrap_name, code=clean_code(settings.bootstrap_code, 16),
                    role="admin", password_hash=hash_password(settings.bootstrap_password)))
        db.commit()
        log.info("Created bootstrap admin %s", settings.bootstrap_email)


class McpSlash:
    """MCP clients often save the URL without the trailing slash; serve /mcp exactly like /mcp/ (no redirect, POST-safe)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/mcp":
            scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        await self.app(scope, receive, send)


def create_app(init_db: bool = True) -> FastAPI:
    if init_db:
        Base.metadata.create_all(engine)
        add_missing_columns(engine)
        bootstrap_admin()

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with mcp_server.mcp.session_manager.run():
            yield

    app = FastAPI(title="ReportZenE", version="0.1.0", lifespan=lifespan)
    errors.install(app)
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
                       allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["x-request-id"] = request.state.request_id
        return response

    for module in ROUTERS:
        app.include_router(module.router, prefix="/api/v1")
    app.include_router(auth.callback_router)

    @app.get("/api/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    app.mount("/mcp", mcp_server.http_app())  # AI agents (personal token auth inside each tool)
    app.add_middleware(McpSlash)
    _mount_spa(app)
    return app


NO_CACHE = {"Cache-Control": "no-cache"}  # index.html must always be fresh: it names the hashed asset files of this deploy


def _mount_spa(app: FastAPI) -> None:
    dist = settings.web_dist
    if not (dist / "index.html").exists():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(("api/", "mcp")):
            raise AppError(404, "NOT_FOUND", f"No API route /{path}")
        target = (dist / path).resolve()
        if path and target.is_file() and dist.resolve() in target.parents and target.name != "index.html":
            return FileResponse(target)
        return FileResponse(dist / "index.html", headers=NO_CACHE)


app = create_app()
