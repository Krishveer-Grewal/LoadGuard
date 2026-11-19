from __future__ import annotations

import asyncio
import time
from datetime import timedelta, timezone
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from ..db import Analysis, Handler, SessionLocal, Trailer, iso, utcnow
from ..services.monitor import monitor
from ..vision.overlay import ALL_LAYERS, encode_jpeg, render_overlay
from ..vision.sources import PushSource

router = APIRouter(prefix="/api", tags=["trailers"])


class TrailerIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    door: int = 0
    source_type: str = Field("simulator", pattern="^(simulator|rtsp|webcam|video|push)$")
    source_uri: Optional[str] = None
    sim_skill: float = Field(0.6, ge=0, le=1)
    handler_id: Optional[int] = None
    calibration: Optional[dict] = None


class TrailerPatch(BaseModel):
    door: Optional[int] = None
    source_type: Optional[str] = Field(None, pattern="^(simulator|rtsp|webcam|video|push)$")
    source_uri: Optional[str] = None
    sim_skill: Optional[float] = Field(None, ge=0, le=1)
    handler_id: Optional[int] = None
    calibration: Optional[dict] = None
    active: Optional[bool] = None


def _worker(tid: str):
    w = monitor.get(tid)
    if not w:
        raise HTTPException(404, f"Trailer {tid} is not being monitored")
    return w


def _trailer_dict(t: Trailer, handlers: dict) -> dict:
    w = monitor.get(t.id)
    live = w.summary() if w else {"status": "Offline", "online": False, "wallScore": None}
    h = handlers.get(t.handler_id)
    return {
        **live,
        "trailerId": t.id,
        "door": t.door,
        "sourceType": t.source_type,
        "sourceUri": t.source_uri,
        "simSkill": t.sim_skill,
        "active": t.active,
        "calibration": t.calibration,
        "handler": {"id": h.id, "name": h.name, "badge": h.badge} if h else None,
    }


@router.get("/handlers")
def list_handlers():
    with SessionLocal() as db:
        return [{"id": h.id, "name": h.name, "badge": h.badge} for h in db.query(Handler).order_by(Handler.id)]


@router.get("/trailers")
def list_trailers():
    with SessionLocal() as db:
        handlers = {h.id: h for h in db.query(Handler).all()}
        return [_trailer_dict(t, handlers) for t in db.query(Trailer).order_by(Trailer.door, Trailer.id).all()]


@router.post("/trailers", status_code=201)
def create_trailer(body: TrailerIn):
    with SessionLocal() as db:
        if db.get(Trailer, body.id):
            raise HTTPException(409, "Trailer already exists")
        if body.source_type in ("rtsp", "video") and not body.source_uri:
            raise HTTPException(422, "source_uri is required for rtsp/video sources")
        t = Trailer(**body.model_dump())
        if body.source_type == "simulator" and not body.calibration:
            from ..vision.simulator import sim_calibration
            t.calibration = sim_calibration().to_dict()
        db.add(t)
        db.commit()
        monitor.start(t)
        handlers = {h.id: h for h in db.query(Handler).all()}
        return _trailer_dict(t, handlers)


@router.patch("/trailers/{tid}")
def update_trailer(tid: str, body: TrailerPatch):
    with SessionLocal() as db:
        t = db.get(Trailer, tid)
        if not t:
            raise HTTPException(404, "Trailer not found")
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(t, k, v)
        db.commit()
        if t.active:
            monitor.start(t)
        else:
            monitor.stop(t.id)
        handlers = {h.id: h for h in db.query(Handler).all()}
        return _trailer_dict(t, handlers)


@router.delete("/trailers/{tid}", status_code=204)
def delete_trailer(tid: str):
    with SessionLocal() as db:
        t = db.get(Trailer, tid)
        if not t:
            raise HTTPException(404, "Trailer not found")
        monitor.stop(tid)
        db.query(Analysis).filter(Analysis.trailer_id == tid).delete()
        from ..db import Alert
        db.query(Alert).filter(Alert.trailer_id == tid).delete()
        db.delete(t)
        db.commit()
    return Response(status_code=204)


@router.get("/trailers/{tid}")
def get_trailer(tid: str):
    with SessionLocal() as db:
        t = db.get(Trailer, tid)
        if not t:
            raise HTTPException(404, "Trailer not found")
        handlers = {h.id: h for h in db.query(Handler).all()}
        d = _trailer_dict(t, handlers)
    w = monitor.get(tid)
    d["latest"] = w.latest if w else None
    return d


@router.get("/trailers/{tid}/latest")
def latest_result(tid: str):
    """Full structural analysis for the most recent frame (FR-2 .. FR-12 payloads)."""
    w = _worker(tid)
    if not w.latest:
        raise HTTPException(503, "No analysis yet")
    return w.latest


@router.get("/trailers/{tid}/detections")
def latest_detections(tid: str):
    w = _worker(tid)
    if not w.latest:
        raise HTTPException(503, "No analysis yet")
    return {"trailerId": tid, "timestamp": w.latest["timestamp"], "detections": w.latest["detections"]}


@router.get("/trailers/{tid}/frame.jpg")
def frame_jpg(tid: str, annotated: bool = True, layers: Optional[str] = None):
    w = _worker(tid)
    if layers is not None and w.latest is not None and w.analyzed_image is not None:
        # `layers=` (empty) returns the exact analyzed frame, for client-side SVG overlays
        sel = tuple(x for x in layers.split(",") if x in ALL_LAYERS)
        with w.lock:
            img, res = w.analyzed_image, w.latest
        data = encode_jpeg(render_overlay(img, res, sel), 80)
    else:
        with w.lock:
            data = w.annotated_jpeg if annotated else w.raw_jpeg
    if not data:
        raise HTTPException(503, "No frame yet")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/trailers/{tid}/stream.mjpg")
async def stream(tid: str, request: Request, annotated: bool = False, fps: float = Query(5, gt=0, le=15)):
    """Live MJPEG feed for <img> tags. Raw frames by default; annotated=1 for overlays."""
    w = _worker(tid)
    boundary = "frame"

    async def gen():
        last = None
        while not await request.is_disconnected():
            with w.lock:
                data = w.annotated_jpeg if annotated else w.raw_jpeg
            if data and data is not last:
                last = data
                yield (b"--" + boundary.encode() + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                       + str(len(data)).encode() + b"\r\n\r\n" + data + b"\r\n")
            await asyncio.sleep(1 / fps)

    return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={boundary}")


@router.post("/trailers/{tid}/frames", status_code=202)
async def push_frame(tid: str, file: UploadFile):
    """Push a camera frame (JPEG/PNG) for trailers with source_type=push (e.g. a handheld)."""
    w = _worker(tid)
    if not isinstance(w.source, PushSource):
        raise HTTPException(409, "Trailer is not configured for pushed frames")
    data = await file.read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Could not decode image")
    h, wd = img.shape[:2]
    if wd > 1280:
        img = cv2.resize(img, (1280, int(h * 1280 / wd)))
    w.source.push(img)
    return {"accepted": True}


@router.get("/trailers/{tid}/timeline")
def timeline(tid: str, minutes: int = Query(60, ge=1, le=24 * 60)):
    w = monitor.get(tid)
    live = list(w.timeline) if w else []
    since = utcnow() - timedelta(minutes=minutes)
    with SessionLocal() as db:
        rows = db.query(Analysis.ts, Analysis.wall_score, Analysis.collapse_risk, Analysis.issue_total,
                        Analysis.package_count).filter(Analysis.trailer_id == tid, Analysis.ts >= since) \
            .order_by(Analysis.ts).all()
    cutoff = live[0]["t"] if live else time.time()
    pts = [{"t": r.ts.replace(tzinfo=timezone.utc).timestamp(), "score": r.wall_score,
            "risk": r.collapse_risk, "issues": r.issue_total, "packages": r.package_count}
           for r in rows]
    pts = [p for p in pts if p["t"] < cutoff] + live
    return {"trailerId": tid, "points": pts[-800:]}


@router.get("/trailers/{tid}/walls")
def completed_walls(tid: str, limit: int = Query(20, le=200)):
    with SessionLocal() as db:
        rows = db.query(Analysis).filter(Analysis.trailer_id == tid, Analysis.wall_complete.is_(True)) \
            .order_by(Analysis.ts.desc()).limit(limit).all()
        handlers = {h.id: h.name for h in db.query(Handler).all()}
        return [{
            "id": r.id, "timestamp": iso(r.ts), "shift": r.shift, "wallSeq": r.wall_seq,
            "wallScore": r.wall_score, "collapseRisk": r.collapse_risk, "grade": r.grade,
            "issueCounts": r.issue_counts, "ruleScores": r.rule_scores, "summary": r.summary,
            "handler": handlers.get(r.handler_id), "hasDetail": r.result is not None,
        } for r in rows]


@router.get("/analyses/{aid}")
def analysis_detail(aid: int):
    with SessionLocal() as db:
        r = db.get(Analysis, aid)
        if not r or r.result is None:
            raise HTTPException(404, "Analysis detail not stored")
        return r.result
