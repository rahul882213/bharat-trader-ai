"""Standalone FastAPI Application Entrypoint (uvicorn backend.main:app --reload)."""
from __future__ import annotations

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from backend.api.routes import build_router

    app = FastAPI(title="Bharat Trader AI API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    router = build_router()
    if router is not None:
        app.include_router(router)
except ImportError:
    app = None  # FastAPI optional; CLI & Express bridge work with Python stdlib
