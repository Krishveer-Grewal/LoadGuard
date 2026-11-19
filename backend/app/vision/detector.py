"""Package detection engine.

Pre-trained models only (no custom training). Backends:

* classical  - OpenCV colour/contour segmentation of the wall face. Zero downloads, fast, and
               well suited to cardboard against a trailer interior. Gives rotated-rect tilt.
* yolo       - pre-trained YOLO11 (COCO). COCO has no "cardboard box" class, so classes are
               mapped (suitcase->box, handbag/backpack->bag, ...). Good for bags/irregulars.
* yoloworld  - pre-trained open-vocabulary YOLO-World prompted with package vocabulary.
* hybrid     - YOLO detections for non-box freight fused with classical box segmentation.
* groundtruth- simulator ground truth (to evaluate the structural engine in isolation).
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import cv2
import numpy as np

from ..config import settings
from .types import Calibration, Detection, Frame

log = logging.getLogger("loadguard.detector")

COCO_MAP = {
    "suitcase": "box",
    "backpack": "bag",
    "handbag": "bag",
    "sports ball": "cylinder",
    "bottle": "cylinder",
    "vase": "irregular",
    "teddy bear": "irregular",
    "book": "envelope",
}
WORLD_PROMPTS = {
    "cardboard box": "box",
    "package": "box",
    "plastic bag": "bag",
    "polybag": "bag",
    "envelope": "envelope",
    "tire": "tire",
    "barrel": "cylinder",
    "tube": "cylinder",
}


def _iou(a: Detection, b: Detection) -> float:
    ix = max(0.0, min(a.x2, b.x2) - max(a.x, b.x))
    iy = max(0.0, min(a.y2, b.y2) - max(a.y, b.y))
    inter = ix * iy
    return inter / (a.area + b.area - inter + 1e-6)


class ClassicalDetector:
    name = "classical"

    def detect(self, image: np.ndarray, calib: Calibration) -> list[Detection]:
        H, W = image.shape[:2]
        x0, y0, x1, y1 = calib.roi or (0, 0, W, H)
        roi = image[y0:y1, x0:x1]
        lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB).astype(np.float32)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        v, s = hsv[..., 2], hsv[..., 1]

        # Background = the shadowed cavity behind/above the wall: dark, low-saturation.
        cand = (v > 30) & (v < 75) & (s < 90)
        bg = np.median(lab[cand], axis=0) if cand.sum() > 500 else lab.reshape(-1, 3).mean(0)
        dist = np.linalg.norm(lab - bg, axis=2)
        fg = ((dist > 20) & (v > 36)).astype(np.uint8)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

        n, labels, stats, _ = cv2.connectedComponentsWithStats(fg, 8)
        min_area = max(600, 0.0012 * roi.shape[0] * roi.shape[1])
        dets: list[Detection] = []
        for i in range(1, n):
            bx, by, bw, bh, area = stats[i]
            if area < min_area or bw < 12 or bh < 10:
                continue
            comp = (labels[by:by + bh, bx:bx + bw] == i).astype(np.uint8)
            cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cnts:
                continue
            c = max(cnts, key=cv2.contourArea)
            (_, _), (rw, rh), ra = cv2.minAreaRect(c)
            rect_area = max(rw * rh, 1)
            rectangularity = float(area / rect_area)
            hull_area = max(cv2.contourArea(cv2.convexHull(c)), 1)
            solidity = float(area / hull_area)
            # tilt relative to the nearest axis
            tilt = ra % 90
            tilt = tilt - 90 if tilt > 45 else tilt
            mask = labels[by:by + bh, bx:bx + bw] == i
            mh = float(hsv[by:by + bh, bx:bx + bw][..., 0][mask].mean())
            ms = float(s[by:by + bh, bx:bx + bw][mask].mean())
            mv = float(v[by:by + bh, bx:bx + bw][mask].mean())
            cls = self._classify(mh, ms, mv, bw, bh, rectangularity)
            conf = float(np.clip(0.55 + 0.4 * min(rectangularity, solidity), 0, 0.99))
            dets.append(Detection(0, cls, conf, float(bx + x0), float(by + y0), float(bw), float(bh),
                                  float(tilt) if abs(tilt) > 2.5 and rectangularity > 0.85 and cls == "box" else 0.0,
                                  None, "classical"))
        return dets

    @staticmethod
    def _classify(h, s, v, w, h_px, rect) -> str:
        if s < 40 and v < 120:
            return "tire"
        if s < 60 and v > 165:
            if w / max(h_px, 1) > 3.5 and h_px < 30:
                return "envelope"
            return "bag" if rect < 0.9 else "box"
        if rect < 0.8:
            return "irregular"
        return "box"


class YoloDetector:
    def __init__(self, world: bool = False):
        from ultralytics import YOLO  # optional dependency

        self.world = world
        self.name = "yoloworld" if world else "yolo"
        weights = settings.yoloworld_model if world else settings.yolo_model
        self.model = YOLO(weights)
        if world:
            self.model.set_classes(list(WORLD_PROMPTS))
            self.map = {i: WORLD_PROMPTS[k] for i, k in enumerate(WORLD_PROMPTS)}
        else:
            names = self.model.names
            self.map = {i: COCO_MAP[n] for i, n in names.items() if n in COCO_MAP}
        self._lock = threading.Lock()

    def detect(self, image: np.ndarray, calib: Calibration) -> list[Detection]:
        import supervision as sv

        with self._lock:
            res = self.model.predict(image, conf=settings.yolo_conf, verbose=False)[0]
        sdet = sv.Detections.from_ultralytics(res).with_nms(threshold=0.5)
        out: list[Detection] = []
        roi = calib.roi
        for (x1, y1, x2, y2), conf, cid in zip(sdet.xyxy, sdet.confidence, sdet.class_id):
            cls = self.map.get(int(cid))
            if cls is None:
                continue
            if roi and not (roi[0] <= (x1 + x2) / 2 <= roi[2] and roi[1] <= (y1 + y2) / 2 <= roi[3]):
                continue
            out.append(Detection(0, cls, float(conf), float(x1), float(y1), float(x2 - x1), float(y2 - y1),
                                 0.0, None, self.name))
        return out


class HybridDetector:
    name = "hybrid"

    def __init__(self, yolo: YoloDetector):
        self.yolo = yolo
        self.classical = ClassicalDetector()

    def detect(self, image: np.ndarray, calib: Calibration) -> list[Detection]:
        base = self.classical.detect(image, calib)
        extra = self.yolo.detect(image, calib)
        for e in extra:
            match = max(base, key=lambda b: _iou(b, e), default=None)
            if match is not None and _iou(match, e) > 0.5:
                # YOLO is more reliable at semantic class; geometry stays from segmentation.
                if e.cls != "box" and e.confidence > 0.5:
                    match.cls = e.cls
                match.confidence = max(match.confidence, e.confidence)
                match.source = "hybrid"
            elif e.cls != "box":
                base.append(e)
        return base


class GroundTruthDetector:
    name = "groundtruth"

    def __init__(self, fallback):
        self.fallback = fallback

    def detect_frame(self, frame: Frame, calib: Calibration) -> list[Detection]:
        if frame.ground_truth is not None:
            return [Detection(**{**d.__dict__}) for d in frame.ground_truth]
        return self.fallback.detect(frame.image, calib)


_detector = None
_lock = threading.Lock()


def get_detector():
    global _detector
    with _lock:
        if _detector is not None:
            return _detector
        choice = settings.detector.lower()
        if choice in ("auto", "yolo", "yoloworld", "hybrid"):
            try:
                if choice == "yoloworld":
                    _detector = YoloDetector(world=True)
                elif choice == "yolo":
                    _detector = YoloDetector()
                else:
                    _detector = HybridDetector(YoloDetector())
            except Exception as exc:  # ultralytics missing or weights unavailable offline
                log.warning("YOLO unavailable (%s); falling back to classical detector", exc)
                _detector = ClassicalDetector()
        elif choice == "groundtruth":
            _detector = GroundTruthDetector(ClassicalDetector())
        else:
            _detector = ClassicalDetector()
        log.info("Detector backend: %s", _detector.name)
        return _detector


def detect(frame: Frame, calib: Calibration, detector=None) -> list[Detection]:
    det = detector or get_detector()
    if isinstance(det, GroundTruthDetector):
        dets = det.detect_frame(frame, calib)
    else:
        dets = det.detect(frame.image, calib)
    dets.sort(key=lambda d: (round(d.y2 / 20), d.x))
    for i, d in enumerate(dets, 1):
        d.id = i
        if frame.depth is not None:
            patch = frame.depth[int(d.y):int(d.y2), int(d.x):int(d.x2)]
            vals = patch[np.isfinite(patch)]
            d.protrusion = float(np.median(vals)) if vals.size else 0.0
    return dets


def precision_recall(dets: list[Detection], gt: list[Detection], thr: float = 0.5) -> tuple[float, float]:
    matched_gt: set[int] = set()
    tp = 0
    for d in dets:
        best, bi = 0.0, -1
        for j, g in enumerate(gt):
            if j in matched_gt:
                continue
            v = _iou(d, g)
            if v > best:
                best, bi = v, j
        if best >= thr:
            tp += 1
            matched_gt.add(bi)
    p = tp / len(dets) if dets else 1.0
    r = tp / len(gt) if gt else 1.0
    return p, r
