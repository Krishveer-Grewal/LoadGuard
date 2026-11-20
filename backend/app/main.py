"""LoadGuard — FastAPI application."""
from __future__ import annotations

import asyncio
import logging
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .api import alerts, analyze, trailers
from .config import settings
from .db import init_db
from .services.hub import hub
from .services.monitor import monitor
from .services.seed import seed_all_async
from .vision.detector import get_detector

warnings.filterwarnings("ignore", category=FutureWarning)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _resolve_stale_alerts() -> None:
    """Alerts left open by a previous process have no worker tracking them; resolve them.
    Fresh workers re-raise anything that is still wrong after the debounce window."""
    from .db import Alert, SessionLocal, utcnow

    with SessionLocal() as db:
        db.query(Alert).filter(Alert.status.in_(["active", "acknowledged"])).update(
            {"status": "resolved", "resolved_at": utcnow()}, synchronize_session=False)
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.bind(asyncio.get_running_loop())
    init_db()
    _resolve_stale_alerts()
    await asyncio.to_thread(get_detector)  # warm the model before workers start
    seed_all_async(on_base_ready=monitor.start_all)
    yield
    monitor.stop_all()


app = FastAPI(title="LoadGuard", version="1.0.0",
              description="Real-time trailer load quality monitoring", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"],
                   allow_headers=["*"])
app.include_router(trailers.router)
app.include_router(analyze.router)
app.include_router(alerts.router)


@app.get("/api/health")
def health():
    return {"ok": True, "trailers": len(monitor.workers)}


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await hub.connect(websocket)
    try:
        await websocket.send_json({"type": "hello", "trailers": [w.summary() for w in monitor.workers.values()]})
        while True:
            await websocket.receive_text()  # keepalive pings from client
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(websocket)


# Serve the built frontend when present (single-container deployments).
STATIC = Path(__file__).resolve().parent.parent / "static"
if STATIC.exists():
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = STATIC / path
        if path and f.is_file() and STATIC in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(STATIC / "index.html")
