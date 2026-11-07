"""FastAPI backend and production frontend server.

Local development: uvicorn app:app --reload
All journal and chart processing is local; no outbound HTTP client is used.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from analyser import (
    BASE_DIR,
    continuous_learning,
    journal_fingerprint,
    read_learned_system,
    read_trades_select_only,
)


LOGGER = logging.getLogger("continuous_learning")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"


def _learning_status() -> dict[str, Any]:
    learned = read_learned_system()
    return {
        "last_learned_from_journal": learned["last_learned_from_journal"],
        "system": f"System: {learned['system_status']}",
        "system_status": learned["system_status"],
        "trade_count": learned["journal_trade_count"],
        "journal_sha256": learned["journal_sha256"],
        "setup_learning": learned["setup_learning"],
        "execution_learning": learned["execution_learning"],
        "journal_mode": "READ_ONLY_LOCAL_MOCK",
        "chart_data_mode": "SIMULATED_LOCAL_OHLC",
    }


async def _watch_local_journal() -> None:
    """Detect local CSV additions and automatically rerun continuous learning."""
    while True:
        await asyncio.sleep(2)
        try:
            current_fingerprint = journal_fingerprint()
            learned_fingerprint = read_learned_system()["journal_sha256"]
            if current_fingerprint != learned_fingerprint:
                LOGGER.info("Local journal change detected; re-learning patterns.")
                await asyncio.to_thread(continuous_learning)
                LOGGER.info("Continuous learning update completed.")
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Journal watcher iteration failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    LOGGER.info("Starting local-only learning system; remote journal writes are not implemented.")
    report = await asyncio.to_thread(continuous_learning)
    LOGGER.info("Learned from %d local journal rows.", report["overall"]["trades"])
    watcher = asyncio.create_task(_watch_local_journal())
    try:
        yield
    finally:
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Trade Journal Continuous Learning System",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def local_data_policy_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Data-Policy"] = "LOCAL-ONLY; JOURNAL-READ-ONLY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "LOCAL_ONLY", "journal": "READ_ONLY"}


@app.get("/api/journal/read-only")
def journal_read_only() -> dict[str, Any]:
    """Return journal rows using only a local SQLite SELECT query."""
    try:
        trades = read_trades_select_only()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "source": "template.csv (local Vercel mock) -> local SQLite mirror",
        "access": "SELECT_ONLY",
        "remote_requests": 0,
        "remote_writes": 0,
        "count": len(trades),
        "trades": trades,
    }


@app.get("/api/patterns/analyze")
def analyze_patterns() -> dict[str, Any]:
    """Synchronously learn from the latest CSV and return the plaintext report."""
    try:
        report = continuous_learning()
        status = _learning_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    LOGGER.info("Analysis refreshed: %d trades, %.2f%% win rate.", report["overall"]["trades"], report["overall"]["win_rate"])
    return {"status": "ok", "report": report, "learning": status}


@app.get("/api/system/status")
def system_status() -> dict[str, Any]:
    try:
        return _learning_status()
    except FileNotFoundError:
        continuous_learning()
        return _learning_status()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def generate_ohlc(symbol: str, timeframe: str, count: int = 180) -> list[dict[str, Any]]:
    """Generate deterministic simulated OHLCV; never represents live market data."""
    seed = int(hashlib.sha256(f"{symbol}:{timeframe}".encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    base_prices = {"XAUUSD": 2650.0, "EURUSD": 1.0920, "GBPUSD": 1.2680}
    decimals = 2 if symbol == "XAUUSD" else 5
    base = base_prices[symbol]
    scale = base * (0.00045 if timeframe == "M5" else 0.00020)
    minutes = 5 if timeframe == "M5" else 1
    start = datetime(2025, 1, 6, 7, 0, tzinfo=timezone.utc)
    candles = []
    previous_close = base

    for index in range(count):
        cycle = 1 if (index // 35) % 2 == 0 else -1
        drift = cycle * scale * 0.20
        open_price = previous_close
        close_price = open_price + drift + rng.gauss(0, scale)
        spread = abs(rng.gauss(scale * 0.8, scale * 0.35)) + scale * 0.15
        high = max(open_price, close_price) + spread
        low = max(0.00001, min(open_price, close_price) - spread * rng.uniform(0.7, 1.2))
        volume = int(rng.uniform(300, 1100) * (2.0 if index % 29 == 0 else 1.0))
        timestamp = int((start + timedelta(minutes=index * minutes)).timestamp())
        candles.append(
            {
                "time": timestamp,
                "open": round(open_price, decimals),
                "high": round(high, decimals),
                "low": round(low, decimals),
                "close": round(close_price, decimals),
                "volume": volume,
            }
        )
        previous_close = close_price
    return candles


def calculate_heikin_ashi(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Calculate HA candles, including HA high/low and first-candle seeding."""
    ha_candles = []
    previous_ha_open = None
    previous_ha_close = None

    for index, candle in enumerate(candles):
        ha_close = (candle["open"] + candle["high"] + candle["low"] + candle["close"]) / 4
        if index == 0:
            ha_open = (candle["open"] + candle["close"]) / 2
        else:
            ha_open = (previous_ha_open + previous_ha_close) / 2
        ha_high = max(candle["high"], ha_open, ha_close)
        ha_low = min(candle["low"], ha_open, ha_close)
        ha_candles.append(
            {
                "time": candle["time"],
                "open": ha_open,
                "high": ha_high,
                "low": ha_low,
                "close": ha_close,
                "volume": candle["volume"],
            }
        )
        previous_ha_open = ha_open
        previous_ha_close = ha_close
    return ha_candles


@app.get("/api/charts/data")
def chart_data(
    symbol: str = Query(default="XAUUSD", pattern="^(XAUUSD|EURUSD|GBPUSD)$"),
    timeframe: str = Query(default="M5", pattern="^(M1|M5)$"),
) -> dict[str, Any]:
    candles = generate_ohlc(symbol, timeframe)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "data_mode": "SIMULATED_LOCAL_OHLC",
        "candles": candles,
        "ha_candles": calculate_heikin_ashi(candles),
        "price_format": {
            "precision": 2 if symbol == "XAUUSD" else 5,
            "min_move": 0.01 if symbol == "XAUUSD" else 0.00001,
        },
    }


# API routes are registered before this mount. The built Vite app is therefore
# available at localhost:8000 without a second process.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:
    @app.get("/", include_in_schema=False)
    def frontend_not_built():
        return JSONResponse(
            {
                "message": "Frontend is not built. Run: cd frontend && npm install && npm run build",
                "api_docs": "/docs",
            }
        )
