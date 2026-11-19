"""Ad-hoc analysis of uploaded images and recorded videos (FR-1 single image / recorded video)."""
from __future__ import annotations

import base64
import json
import tempfile
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..analysis.pipeline import analyze_frame
from ..vision.detector import get_detector
from ..vision.overlay import encode_jpeg, render_overlay
from ..vision.simulator import render_complete_wall, sim_calibration
from ..vision.types import Calibration, Frame

router = APIRouter(prefix="/api", tags=["analyze"])
MAX_UPLOAD = 200 * 1024 * 1024


def _calib(raw: Optional[str], img: np.ndarray) -> Calibration:
    if raw:
        try:
            return Calibration.from_dict(json.loads(raw))
        except (ValueError, TypeError):
            raise HTTPException(422, "calibration must be JSON: {roi:[x0,y0,x1,y1], floor_y, px_per_inch}")
    return Calibration()


def _b64(img: np.ndarray) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(encode_jpeg(img, 82)).decode()


def _analyze_image(img: np.ndarray, calib: Calibration, depth=None) -> dict:
    h, w = img.shape[:2]
    if w > 1600:
        scale = 1600 / w
        img = cv2.resize(img, (1600, int(h * scale)))
        if calib.roi:
            calib.roi = tuple(int(v * scale) for v in calib.roi)  # type: ignore[assignment]
        if calib.floor_y:
            calib.floor_y *= scale
        if calib.px_per_inch:
            calib.px_per_inch *= scale
    result = analyze_frame(Frame(img, time.time(), depth), calib)
    result["image"] = _b64(img)
    result["annotatedImage"] = _b64(render_overlay(img, result))
    return result


@router.post("/analyze")
async def analyze_image(file: UploadFile, calibration: Optional[str] = Form(None)):
    """Analyze a single uploaded wall photo. Returns detections, wall model, rules, WQI, risk,
    explanations and an annotated image."""
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File too large")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "Could not decode image (use JPEG or PNG)")
    calib = _calib(calibration, img)
    return await run_in_threadpool(_analyze_image, img, calib)


@router.post("/analyze/sample")
async def analyze_sample(skill: float = Form(0.3), seed: Optional[int] = Form(None)):
    """Analyze a freshly simulated wall (handy for demos without a camera)."""
    seed = seed if seed is not None else int(time.time()) % 100000
    frame = render_complete_wall(max(0.0, min(1.0, skill)), seed)

    def run():
        r = analyze_frame(frame, sim_calibration())
        r["image"] = _b64(frame.image)
        r["annotatedImage"] = _b64(render_overlay(frame.image, r))
        r["sample"] = {"skill": skill, "seed": seed}
        return r

    return await run_in_threadpool(run)


@router.post("/analyze/video")
async def analyze_video(file: UploadFile, every_s: float = Form(1.0), calibration: Optional[str] = Form(None)):
    """Analyze a recorded video by sampling frames. Returns a per-sample score timeline and the
    full analysis of the worst frame."""
    suffix = Path(file.filename or "v.mp4").suffix or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        size = 0
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD:
                raise HTTPException(413, "File too large")
            tmp.write(chunk)
        tmp.flush()

        def run():
            cap = cv2.VideoCapture(tmp.name)
            if not cap.isOpened():
                raise HTTPException(400, "Could not open video")
            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            step = max(1, int(fps * max(every_s, 0.2)))
            timeline, worst, worst_img, idx = [], None, None, 0
            calib = None
            while len(timeline) < 600:
                ok = cap.grab()
                if not ok:
                    break
                if idx % step == 0:
                    ok, img = cap.retrieve()
                    if not ok:
                        break
                    h, w = img.shape[:2]
                    if w > 1280:
                        img = cv2.resize(img, (1280, int(h * 1280 / w)))
                    calib = calib or _calib(calibration, img)
                    r = analyze_frame(Frame(img, idx / fps), calib)
                    timeline.append({"t": round(idx / fps, 2), "score": r["wallScore"], "risk": r["collapseRisk"],
                                     "issues": len(r["issues"]), "packages": len(r["detections"])})
                    if worst is None or r["wallScore"] < worst["wallScore"]:
                        worst, worst_img = r, img
                idx += 1
            cap.release()
            if worst is None:
                raise HTTPException(400, "No frames decoded")
            worst["image"] = _b64(worst_img)
            worst["annotatedImage"] = _b64(render_overlay(worst_img, worst))
            return {"frames": len(timeline), "timeline": timeline, "worst": worst,
                    "avgScore": round(float(np.mean([p["score"] for p in timeline])), 1)}

        return await run_in_threadpool(run)


@router.get("/system")
def system_info():
    from ..config import settings
    det = get_detector()
    return {
        "detector": det.name,
        "detectorSetting": settings.detector,
        "captureFps": settings.capture_fps,
        "analysisFps": settings.analysis_fps,
        "alertDebounce": settings.alert_debounce,
        "database": "postgresql" if settings.database_url.startswith("postgres") else "sqlite",
    }
