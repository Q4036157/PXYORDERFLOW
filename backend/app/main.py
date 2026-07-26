"""FastAPI entry point for the standalone order-flow application."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import settings
from .runtime import runtime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("of.api")

# Production builds may serve frontend/dist from this process.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_STATIC_DIR = Path(
    __import__("os").getenv("OF_STATIC_DIR", str(_PROJECT_ROOT / "frontend" / "dist"))
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "OF API starting host=%s port=%s md=%s trade=%s",
        settings.bind_host,
        settings.http_port,
        settings.md_mode,
        settings.trade_mode,
    )
    await runtime.start()
    try:
        yield
    finally:
        await runtime.stop()
        logger.info("OF API stopped")


app = FastAPI(title="PXYORDERFLOW", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlaceBody(BaseModel):
    accountId: str
    side: str = Field(pattern="^(buy|sell)$")
    price: float
    qty: float
    postOnly: bool = False


class CancelBody(BaseModel):
    accountId: str
    orderId: str
    symbol: str = ""


class CancelAllBody(BaseModel):
    accountId: str
    symbol: str | None = None
    confirmed: bool = False


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "pxy-orderflow",
        "mdMode": settings.md_mode,
        "tradeMode": settings.trade_mode,
        "tradingEnabled": settings.trading_enabled,
        "cancelEnabled": True,
        "tradeStatus": "public mock execution adapter",
    }


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    return runtime.state_snapshot()


@app.get("/api/chart")
async def get_chart(limit: int = Query(default=120, ge=1, le=120)) -> dict[str, Any]:
    return runtime.flow.chart_snapshot(limit)


@app.get("/api/accounts")
async def list_accounts() -> dict[str, Any]:
    rows = await runtime.trade.list_accounts()
    return {"accounts": [a.to_dict() for a in rows]}


@app.get("/api/orders/open")
async def open_orders(accountId: str, symbol: str | None = None) -> dict[str, Any]:
    rows = await runtime.list_open_orders(accountId, symbol)
    return {"orders": rows}


@app.get("/api/portfolio")
async def portfolio(accountId: str, symbol: str | None = None) -> dict[str, Any]:  # noqa: ARG001
    # The public adapter is intentionally in-memory and does not simulate fills.
    return {"positions": [], "fills": []}


@app.post("/api/orders/place")
async def place_order(body: PlaceBody) -> dict[str, Any]:
    try:
        return await runtime.place_from_ladder(
            account_id=body.accountId,
            side=body.side,
            price=body.price,
            qty=body.qty,
            post_only=body.postOnly,
        )
    except (PermissionError, ValueError) as exc:
        return {"success": False, "message": str(exc)}


@app.post("/api/orders/cancel")
async def cancel_order(body: CancelBody) -> dict[str, Any]:
    return await runtime.cancel(body.accountId, body.orderId, body.symbol)


@app.post("/api/orders/cancel-all")
async def cancel_all(body: CancelAllBody) -> dict[str, Any]:
    try:
        return await runtime.cancel_all(body.accountId, body.confirmed, body.symbol)
    except PermissionError as exc:
        return {"success": False, "message": str(exc)}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    q = runtime.subscribe()
    try:
        await ws.send_json({"type": "hello", "data": runtime.state_snapshot()})
        while True:
            msg = await q.get()
            await ws.send_json(msg)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws error: %s", exc)
    finally:
        runtime.unsubscribe(q)


# Serve the icon explicitly so the SPA fallback can never return HTML for it.
@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    icon = _STATIC_DIR / "favicon.svg"
    if icon.is_file():
        return FileResponse(
            icon,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


# 静态前端（生产）：/assets + SPA fallback；API/WS 路由优先注册，不冲突
if _STATIC_DIR.exists():
    assets = _STATIC_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):  # noqa: ARG001
        index = _STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(
                index,
                headers={"Cache-Control": "no-store, must-revalidate"},
            )
        return {"ok": False, "message": "frontend dist missing"}


def main() -> None:
    import uvicorn

    # 硬约束：默认只绑 127.0.0.1
    uvicorn.run(
        "app.main:app",
        host=settings.bind_host,
        port=settings.http_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
