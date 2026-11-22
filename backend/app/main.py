"""VoiceGuard AI - FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload --port 8000
Swagger UI: http://127.0.0.1:8000/api/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    routes_analytics,
    routes_audio,
    routes_auth,
    routes_forensics,
    routes_history,
    routes_reports,
    routes_stream,
    routes_system,
)
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.services.storage_service import ensure_storage_dirs, purge_temporary_files

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("voiceguard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_storage_dirs()
    removed = purge_temporary_files()
    if removed:
        logger.info("Removed %d stale temporary upload(s)", removed)
    mode = "offline (cache only)" if settings.model_offline else "online"
    logger.info(
        "%s %s starting | env=%s | model=%s (%s)",
        settings.app_name,
        settings.app_version,
        settings.environment,
        settings.model_id,
        mode,
    )
    yield
    logger.info("%s shutting down", settings.app_name)


DESCRIPTION = """
**VoiceGuard AI** analyses a WAV or MP3 recording and estimates whether the speech is
likely genuine human speech or potentially synthetic (voice-cloned / TTS) speech.

* The verdict comes from a real pretrained wav2vec 2.0 spoof-detection model running on CPU.
* If the model cannot be loaded, the analysis is recorded as **unavailable** - the API never
  invents a prediction.
* Every result is probabilistic. It is an indicator, not proof of who is speaking.

Authentication: `POST /api/auth/login`, then click **Authorize** and paste the returned token.
"""


app = FastAPI(
    title="VoiceGuard AI API",
    version=settings.app_version,
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    contact={"name": "VoiceGuard AI", "url": "https://github.com/"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    # The microphone is only used by the same origin (the recorder pages).
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), geolocation=(), microphone=(self)"
    )
    if request.url.path.startswith(settings.api_prefix):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


register_exception_handlers(app)

app.include_router(routes_auth.router)
app.include_router(routes_audio.router)
app.include_router(routes_forensics.router)
app.include_router(routes_history.router)
app.include_router(routes_reports.router)
app.include_router(routes_stream.router)
app.include_router(routes_analytics.router)
app.include_router(routes_system.router)


@app.get("/", include_in_schema=False)
def root() -> JSONResponse:
    return JSONResponse(
        {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/api/docs",
            "health": "/api/health",
        }
    )
