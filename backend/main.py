"""Production-Ready FastAPI Entrypoint for Bharat Trader AI (Render / Docker / Cloud Run)."""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

IST = ZoneInfo("Asia/Kolkata")

try:
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from backend.api.routes import build_root_health_payload, build_router
    from backend.database.db import init_db
    from backend.database.stock_master_db import sync_stock_master

    _DEFAULT_ORIGINS = [
        "https://rahul882213.github.io",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
    ]

    def _get_allowed_origins() -> list[str]:
        raw = (os.getenv("ALLOWED_ORIGINS") or "").strip()
        if not raw:
            return _DEFAULT_ORIGINS
        parsed = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
        return parsed or _DEFAULT_ORIGINS

    # Sliding-window per-IP rate limiter
    _RATE_LOCK = threading.Lock()
    _RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
    _HEAVY_PREFIXES = ("/api/workflow/run", "/api/scanner/market-wide", "/api/backtest", "/api/ai/research")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        init_db()
        try:
            sync_stock_master(force=False)
        except Exception:
            pass
        yield

    app = FastAPI(
        title="Bharat Trader AI API",
        description="Production FastAPI backend for NSE/BSE Indian Stock Market Intelligence, Screener.in Integration, Backtesting, and Risk Management.",
        version="2.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_get_allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    @app.middleware("http")
    async def rate_limit_and_security_headers(request: Request, call_next):
        path = request.url.path
        if request.method != "OPTIONS" and path not in {"/health", "/api/health", "/"}:
            limit_per_min = int(os.getenv("RATE_LIMIT_PER_MIN", "120"))
            if any(path.startswith(p) for p in _HEAVY_PREFIXES):
                limit_per_min = min(limit_per_min, int(os.getenv("HEAVY_RATE_LIMIT_PER_MIN", "30")))

            client_ip = (
                (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
                or (request.client.host if request.client else "unknown")
            )
            bucket_key = f"{client_ip}:{'heavy' if any(path.startswith(p) for p in _HEAVY_PREFIXES) else 'std'}"
            now = time.monotonic()
            cutoff = now - 60.0

            with _RATE_LOCK:
                dq = _RATE_BUCKETS[bucket_key]
                while dq and dq[0] < cutoff:
                    dq.popleft()
                if len(dq) >= limit_per_min:
                    retry_after = max(1, int(60 - (now - dq[0])))
                    return JSONResponse(
                        status_code=429,
                        content={"error": "Rate limit exceeded. Please retry shortly.", "retry_after_sec": retry_after},
                        headers={"Retry-After": str(retry_after)},
                    )
                dq.append(now)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @app.get("/")
    def root():
        return {
            "service": "Bharat Trader AI API",
            "version": "2.0.0",
            "health": "/health",
            "docs": "/docs",
            "time_ist": datetime.now(tz=IST).isoformat(),
        }

    @app.get("/health")
    def root_health():
        return build_root_health_payload()

    router = build_router()
    if router is not None:
        app.include_router(router)
except ImportError:
    app = None  # FastAPI optional when running pure-stdlib Python CLI/tests
