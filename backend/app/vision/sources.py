"""Video ingestion (FR-1): RTSP streams, local webcams, recorded video files, pushed frames
(e.g. a handheld's camera), and the built-in simulator."""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np

from .simulator import SimulatorSource
from .types import Calibration, Frame

log = logging.getLogger("loadguard.sources")


class OpenCVSource:
    """RTSP / HTTP stream, webcam index, or video file. Video files loop; streams reconnect."""

    def __init__(self, uri: str, kind: str, calibration: Optional[Calibration] = None):
        self.uri = uri
        self.kind = kind
        self._calib = calibration or Calibration()
        self.cap: Optional[cv2.VideoCapture] = None
        self._next_retry = 0.0
        self.error: Optional[str] = None

    def _open(self):
        target = int(self.uri) if self.kind == "webcam" and str(self.uri).isdigit() else self.uri
        self.cap = cv2.VideoCapture(target)
        if not self.cap.isOpened():
            self.error = f"Cannot open {self.kind} source"
            self.cap = None
            self._next_retry = time.time() + 5
        else:
            self.error = None

    def calibration(self) -> Calibration:
        return self._calib

    def read(self) -> Optional[Frame]:
        if self.cap is None:
            if time.time() < self._next_retry:
                return None
            self._open()
            if self.cap is None:
                return None
        ok, img = self.cap.read()
        if not ok:
            if self.kind == "video":
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, img = self.cap.read()
            if not ok:
                log.warning("Source %s dropped; reconnecting", self.uri)
                self.release()
                self._next_retry = time.time() + 3
                return None
        h, w = img.shape[:2]
        if w > 1280:
            img = cv2.resize(img, (1280, int(h * 1280 / w)))
        return Frame(img, time.time(), meta={})

    def release(self):
        if self.cap is not None:
            self.cap.release()
        self.cap = None


class PushSource:
    """Frames uploaded over HTTP (handheld camera / edge device)."""

    kind = "push"

    def __init__(self, calibration: Optional[Calibration] = None):
        self._calib = calibration or Calibration()
        self._frame: Optional[Frame] = None
        self._lock = threading.Lock()
        self.error = None

    def push(self, img: np.ndarray):
        with self._lock:
            self._frame = Frame(img, time.time(), meta={})

    def calibration(self) -> Calibration:
        return self._calib

    def read(self) -> Optional[Frame]:
        with self._lock:
            return self._frame

    def release(self):
        pass


def create_source(trailer) -> object:
    calib = Calibration.from_dict(trailer.calibration) if trailer.calibration else None
    st = trailer.source_type
    if st == "simulator":
        src = SimulatorSource(skill=trailer.sim_skill, seed=None, label=f"TRL {trailer.id} DOOR {trailer.door}")
        from ..config import settings
        src.place_interval_s = settings.sim_place_interval_s
        src.error = None
        return src
    if st in ("rtsp", "webcam", "video"):
        return OpenCVSource(trailer.source_uri or "0", st, calib)
    if st == "push":
        return PushSource(calib)
    raise ValueError(f"Unknown source type {st}")
