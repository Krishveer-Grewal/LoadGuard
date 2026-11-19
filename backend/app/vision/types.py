"""Core data types shared by the detection and analysis layers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

PACKAGE_CLASSES = ("box", "irregular", "bag", "envelope", "tire", "cylinder")


@dataclass
class Detection:
    id: int
    cls: str
    confidence: float
    x: float
    y: float
    w: float
    h: float
    angle: float = 0.0  # tilt in degrees (from rotated-rect fit); used for lean detection
    protrusion: Optional[float] = None  # inches proud of the wall face (requires depth)
    source: str = "classical"

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def area(self) -> float:
        return self.w * self.h

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "class": self.cls,
            "confidence": round(float(self.confidence), 3),
            "bbox": {
                "x": round(float(self.x), 1),
                "y": round(float(self.y), 1),
                "width": round(float(self.w), 1),
                "height": round(float(self.h), 1),
            },
            "angle": round(float(self.angle), 1),
            "source": self.source,
        }
        if self.protrusion is not None:
            d["protrusion"] = round(float(self.protrusion), 2)
        return d


@dataclass
class Calibration:
    """Per-camera calibration. ROI = wall face region in pixels; floor_y = trailer floor line."""

    roi: Optional[tuple[int, int, int, int]] = None  # x0, y0, x1, y1
    floor_y: Optional[float] = None
    px_per_inch: Optional[float] = None
    trailer_height_in: float = 108.0

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Calibration":
        if not d:
            return cls()
        roi = d.get("roi")
        return cls(
            roi=tuple(roi) if roi else None,  # type: ignore[arg-type]
            floor_y=d.get("floor_y"),
            px_per_inch=d.get("px_per_inch"),
            trailer_height_in=d.get("trailer_height_in", 108.0),
        )

    def to_dict(self) -> dict:
        return {
            "roi": list(self.roi) if self.roi else None,
            "floor_y": self.floor_y,
            "px_per_inch": self.px_per_inch,
            "trailer_height_in": self.trailer_height_in,
        }


@dataclass
class Frame:
    image: np.ndarray  # BGR
    timestamp: float
    depth: Optional[np.ndarray] = None  # per-pixel protrusion (inches) from an RGB-D sensor
    ground_truth: Optional[list[Detection]] = None
    meta: dict = field(default_factory=dict)
