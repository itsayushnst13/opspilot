"""OpsPilot API entrypoint."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text

from .api import audit, auth, documents, knowledge, metrics, quality, rfq
from .core.config import get_settings
from .core.db import SessionLocal
from .core.logging import log, setup_logging
from .models import Product
from .services.bootstrap import bootstrap

logger = logging.getLogger("opspilot.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    s = get_settings()
    if s.env == "prod" and s.jwt_secret == "dev-only-secret-change-me":
        raise RuntimeError("JWT_SECRET must be set in production")
    bootstrap()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="OpsPilot API", version="1.0.0", lifespan=lifespan,
                  description="AI-assisted chemical operations prototype (synthetic data). "
                              "Independent prototype - not affiliated with any company.")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
                       allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        rid = uuid.uuid4().hex[:8]
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled error", extra={"ctx": {"request_id": rid, "path": request.url.path}})
            return JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
        ms = (time.perf_counter() - t0) * 1000
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api") and request.url.path != "/api/health":
            log(logger, "request", request_id=rid, method=request.method, path=request.url.path,
                status=response.status_code, ms=round(ms, 1))
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        errs = [{"loc": [str(x) for x in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"detail": "Invalid request", "errors": errs}, status_code=422)

    for r in (auth.router, rfq.router, quality.router, documents.router, knowledge.router, audit.router, metrics.router):
        app.include_router(r)

    @app.get("/api/health", tags=["system"])
    def health():
        with SessionLocal() as db:
            db.execute(text("select 1"))
            products = db.scalar(select(func.count()).select_from(Product))
        return {"status": "ok", "mode": s.effective_mode, "products": products, "version": app.version}

    if s.static_dir and Path(s.static_dir).is_dir():
        root = Path(s.static_dir).resolve()
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Not found")
            f = (root / path).resolve()
            if path and root in f.parents and f.is_file():
                return FileResponse(f)
            return FileResponse(root / "index.html")

    return app


app = create_app()
