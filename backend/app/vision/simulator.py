"""Trailer loading simulator.

Generates a camera view of a package wall *as it is being built*, with defects injected
according to a handler skill profile. Used to demo the platform without a physical camera,
to seed historical data, and to measure detector precision against ground truth.

Geometry is planned in inches on a 2-D wall face (x across the trailer, y up from the floor)
using a skyline packer that mimics how handlers actually build walls: fill the lowest shelf
first, left to right. Skill controls whether seams are offset (T-stacking), gaps are filled,
shelves are kept level, heavy freight goes low, and packages are placed square and flush.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from .types import Calibration, Detection, Frame

IMG_W, IMG_H = 960, 720
WALL_W_IN, WALL_H_IN = 96, 104
SCALE = 6.2  # px per inch
FLOOR_Y = 690
WALL_X0 = int((IMG_W - WALL_W_IN * SCALE) / 2)
WALL_TOP_Y = int(FLOOR_Y - WALL_H_IN * SCALE)

BG_DEEP = (52, 44, 38)  # BGR: shadowed trailer interior behind the wall
SEAM = (16, 16, 18)

DENSITY = {"box": 1.0, "tire": 3.2, "cylinder": 1.6, "irregular": 1.2, "bag": 0.35, "envelope": 0.1}


def sim_calibration() -> Calibration:
    return Calibration(
        roi=(WALL_X0 - 6, WALL_TOP_Y, int(WALL_X0 + WALL_W_IN * SCALE + 6), FLOOR_Y),
        floor_y=float(FLOOR_Y),
        px_per_inch=SCALE,
        trailer_height_in=108.0,
    )


@dataclass
class Profile:
    skill: float  # 0 = untrained, 1 = expert

    @property
    def tstack(self): return 0.2 + 0.75 * self.skill
    @property
    def column(self): return 0.7 * (1 - self.skill)
    @property
    def fill_gaps(self): return 0.3 + 0.68 * self.skill
    @property
    def bridge(self): return 0.25 * (1 - self.skill)
    @property
    def level(self): return 0.25 + 0.7 * self.skill
    @property
    def lean(self): return 0.12 * (1 - self.skill)
    @property
    def protrude(self): return 0.22 * (1 - self.skill)
    @property
    def heavy_top(self): return 0.45 * (1 - self.skill)


@dataclass
class SimPackage:
    cls: str
    x: float  # inches from left wall
    y: float  # inches from floor (bottom)
    w: float
    h: float
    weight: float
    angle: float = 0.0
    protrusion: float = 0.0
    color: tuple = (90, 140, 185)
    label: bool = False
    seed: int = 0


@dataclass
class WallPlan:
    packages: list[SimPackage] = field(default_factory=list)


def plan_wall(rng: np.random.Generator, profile: Profile) -> WallPlan:
    W = WALL_W_IN
    target_h = int(rng.integers(84, 101))
    sky = np.zeros(W, dtype=float)
    edges_at: dict[int, set[int]] = {}
    tier_h: dict[int, float] = {}  # skilled handlers build full-width tiers of matched height
    plan = WallPlan()
    guard = 0

    def heavy_choice(h_base: float) -> Optional[str]:
        low = h_base < 30
        if low and rng.random() < 0.18 + 0.2 * profile.skill:
            return "tire" if rng.random() < 0.5 else "bigbox"
        if not low and h_base > target_h * 0.45 and rng.random() < profile.heavy_top * 0.35:
            return "tire" if rng.random() < 0.6 else "bigbox"
        return None

    while guard < 400:
        guard += 1
        hmin = float(sky.min())
        if hmin >= target_h - 6:
            break
        x0 = int(np.argmin(sky))
        x1 = x0
        while x1 < W and sky[x1] == hmin:
            x1 += 1
        seg_len = x1 - x0
        left_h = sky[x0 - 1] if x0 > 0 else None
        right_h = sky[x1] if x1 < W else None
        neighbors = [h for h in (left_h, right_h) if h is not None]

        if seg_len < 8:
            if rng.random() < profile.fill_gaps and seg_len >= 4:
                h = (min(neighbors) - hmin) if neighbors else 10
                h = float(np.clip(h, 6, 16))
                plan.packages.append(_mk(rng, "box", x0, hmin, seg_len, h, profile))
                sky[x0:x1] = hmin + h
                edges_at.setdefault(int(hmin + h), set()).update({x0, x1})
            else:
                # Gap left open: it becomes a chimney/cavity once something is stacked over it.
                sky[x0:x1] = min(neighbors) if neighbors else hmin + 8
            continue

        if seg_len < 20 and neighbors and min(neighbors) > hmin and rng.random() < profile.level:
            # Skilled: close a narrow dip with one package cut to the neighbours' height.
            h = float(np.clip(min(neighbors) - hmin, 4, 26))
            plan.packages.append(_mk(rng, "box", x0, hmin, seg_len, h, profile))
            sky[x0:x1] = hmin + h
            edges_at.setdefault(int(hmin + h), set()).update({x0, x1})
            continue

        heavy = heavy_choice(hmin)
        top_layer = hmin > target_h - 26
        if heavy == "tire":
            cls, w, h = "tire", 28.0, 9.0
        elif heavy == "bigbox":
            cls, w, h = "box", float(rng.integers(24, 31)), float(rng.integers(18, 25))
        elif top_layer and rng.random() < 0.15:
            cls, w, h = "bag", float(rng.integers(14, 22)), float(rng.integers(8, 13))
        elif top_layer and rng.random() < 0.06:
            cls, w, h = "envelope", float(rng.integers(13, 17)), 3.0
        else:
            cls, w, h = "box", float(rng.integers(10, 27)), float(rng.integers(8, 21))

        w = min(w, seg_len)
        leftover = seg_len - w
        if 0 < leftover < 8 and rng.random() < profile.fill_gaps:
            w = float(seg_len) if seg_len <= 32 else w - (8 - leftover)

        below = edges_at.get(int(hmin), set()) | {x0, x1}
        below.discard(0)
        below.discard(W)
        xr = x0 + w
        if xr < W - 2 and below:
            nearest = min(below, key=lambda e: abs(e - xr))
            if abs(nearest - xr) < 4 and rng.random() < profile.tstack:
                w2 = w + 6 if x0 + w + 6 <= x1 else w - 6
                if w2 >= 8:
                    w = w2
            elif abs(nearest - xr) < 12 and nearest > x0 + 6 and rng.random() < profile.column:
                w = float(nearest - x0)

        if rng.random() < profile.bridge and x0 + seg_len + 6 < W:
            w = min(float(W - x0), seg_len + float(rng.integers(4, 13)))

        w = max(4.0, min(w, W - x0))
        if cls == "box" and heavy is None and rng.random() < profile.level:
            h = tier_h.setdefault(int(hmin), float(rng.integers(10, 19)))
        elif neighbors and rng.random() < profile.level:
            for nh in neighbors:
                if 4 <= nh - hmin <= 24 and abs((nh - hmin) - h) <= 6:
                    h = nh - hmin
                    break

        xi0, xi1 = int(x0), int(x0 + w)
        base = float(sky[xi0:xi1].max())
        if base + h > target_h + 6:
            h = target_h + 6 - base
            if h < 6:
                sky[xi0:xi1] = base + 6
                continue

        pkg = _mk(rng, cls, x0, base, w, h, profile)
        plan.packages.append(pkg)
        sky[xi0:xi1] = base + h
        edges_at.setdefault(int(base + h), set()).update({xi0, xi1})

    return plan


def _mk(rng, cls, x, y, w, h, profile: Profile) -> SimPackage:
    angle = 0.0
    if cls not in ("tire",) and y > 10 and rng.random() < profile.lean:
        angle = float(rng.choice([-1, 1]) * rng.uniform(5, 11))
    protr = float(rng.uniform(0, 0.8))
    if rng.random() < profile.protrude:
        protr = float(rng.uniform(4, 10))
    if cls == "box":
        base = np.array([84, 136, 180]) + rng.integers(-30, 25) + rng.integers(-8, 8, 3)
        color = tuple(int(c) for c in np.clip(base, 40, 235))
    elif cls == "tire":
        color = (82, 82, 86)
    elif cls == "bag":
        color = tuple(int(c) for c in rng.choice([[226, 226, 222], [210, 214, 216], [228, 210, 186]]))
    else:
        color = (240, 240, 238)
    weight = DENSITY.get(cls, 1.0) * w * h * min(w, h) / 1000
    return SimPackage(cls, float(x), float(y), float(w), float(h), weight, angle, protr, color,
                      bool(rng.random() < 0.55), int(rng.integers(0, 1 << 30)))


# --------------------------------------------------------------------------- rendering

def _to_px(p: SimPackage) -> tuple[float, float, float, float]:
    x1 = WALL_X0 + p.x * SCALE
    x2 = WALL_X0 + (p.x + p.w) * SCALE
    y2 = FLOOR_Y - p.y * SCALE
    y1 = FLOOR_Y - (p.y + p.h) * SCALE
    return x1, y1, x2, y2


def _background() -> np.ndarray:
    img = np.zeros((IMG_H, IMG_W, 3), np.uint8)
    # deep interior gradient
    for yy in range(IMG_H):
        t = yy / IMG_H
        img[yy, :] = (int(BG_DEEP[0] - 8 * t), int(BG_DEEP[1] - 6 * t), int(BG_DEEP[2] - 4 * t))
    wx1 = int(WALL_X0 + WALL_W_IN * SCALE)
    alu, rib = (112, 110, 106), (140, 138, 134)
    # side walls (perspective trapezoids)
    left = np.array([[0, 0], [WALL_X0 - 8, WALL_TOP_Y - 10], [WALL_X0 - 8, FLOOR_Y], [0, IMG_H]], np.int32)
    right = np.array([[IMG_W, 0], [wx1 + 8, WALL_TOP_Y - 10], [wx1 + 8, FLOOR_Y], [IMG_W, IMG_H]], np.int32)
    cv2.fillPoly(img, [left], alu)
    cv2.fillPoly(img, [right], alu)
    for i in range(1, 7):
        t = i / 7
        xl = int((WALL_X0 - 8) * t)
        cv2.line(img, (xl, int((WALL_TOP_Y - 10) * t)), (xl, int(IMG_H - (IMG_H - FLOOR_Y) * t)), rib, 2)
        xr = int(IMG_W - (IMG_W - wx1 - 8) * t)
        cv2.line(img, (xr, int((WALL_TOP_Y - 10) * t)), (xr, int(IMG_H - (IMG_H - FLOOR_Y) * t)), rib, 2)
    floor = np.array([[0, IMG_H], [WALL_X0 - 8, FLOOR_Y], [wx1 + 8, FLOOR_Y], [IMG_W, IMG_H]], np.int32)
    cv2.fillPoly(img, [floor], (66, 70, 74))
    for i in range(1, 9):
        fx = WALL_X0 - 8 + (wx1 + 16 - WALL_X0) * i / 9
        bx = IMG_W * i / 9
        cv2.line(img, (int(fx), FLOOR_Y), (int(bx), IMG_H), (84, 88, 92), 1)
    ceil = np.array([[0, 0], [WALL_X0 - 8, WALL_TOP_Y - 10], [wx1 + 8, WALL_TOP_Y - 10], [IMG_W, 0]], np.int32)
    cv2.fillPoly(img, [ceil], (92, 90, 88))
    return img


_BG = None


def _draw_package(img: np.ndarray, depth: np.ndarray, p: SimPackage) -> np.ndarray:
    rng = np.random.default_rng(p.seed)
    x1, y1, x2, y2 = _to_px(p)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    s = 1 + p.protrusion * 0.006
    hw, hh = (x2 - x1) / 2 * s, (y2 - y1) / 2 * s
    corners = np.array([[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]])
    a = math.radians(p.angle)
    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    pts = (corners @ rot.T) + [cx, cy]
    if p.angle:
        # pivot on the lower corner so the leaning box still touches its support
        low = pts[:, 1].max()
        pts[:, 1] += (y2 - low)
    poly = pts.astype(np.int32)

    if p.protrusion > 2:
        d = int(p.protrusion * 1.2)
        cv2.fillPoly(img, [poly + [d, d]], (28, 26, 24))

    if p.cls == "bag":
        n = 18
        ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
        r = 1 + rng.uniform(-0.08, 0.05, n)
        bpts = np.stack([cx + hw * 0.98 * r * np.cos(ang), cy + hh * 0.98 * r * np.sin(ang)], 1)
        bpts[:, 1] = np.minimum(bpts[:, 1], y2 - 1)
        poly = bpts.astype(np.int32)
        cv2.fillPoly(img, [poly], p.color)
        for _ in range(4):
            px0 = int(cx + rng.uniform(-hw, hw) * 0.5)
            cv2.line(img, (px0, int(cy - hh * 0.4)), (px0 + int(rng.uniform(-8, 8)), int(cy + hh * 0.4)),
                     tuple(int(c * 0.86) for c in p.color), 1)
    elif p.cls == "tire":
        cv2.fillPoly(img, [poly], p.color)
        for k in range(int(x1) + 6, int(x2) - 4, 9):
            cv2.line(img, (k, int(y1) + 4), (k - 4, int(y2) - 4), (60, 60, 64), 2)
    else:
        cv2.fillPoly(img, [poly], p.color)
        if p.cls == "box":
            tape = tuple(int(min(255, c * 1.12)) for c in p.color)
            t1 = (corners[[0, 1]] * [1, 0.08]) @ rot.T + [cx, cy]
            t2 = (corners[[1, 0]] * [1, -0.08]) @ rot.T + [cx, cy]
            tp = np.vstack([t1, t2]).astype(np.int32)
            if p.angle:
                tp[:, 1] += int(y2 - (corners @ rot.T + [cx, cy])[:, 1].max())
            cv2.fillPoly(img, [tp], tape)
            if p.label and (x2 - x1) > 50 and (y2 - y1) > 40 and not p.angle:
                lx, ly = int(x1 + (x2 - x1) * 0.12), int(y1 + (y2 - y1) * 0.55)
                lw, lh = int((x2 - x1) * 0.35), int((y2 - y1) * 0.3)
                cv2.rectangle(img, (lx, ly), (lx + lw, ly + lh), (236, 236, 236), -1)
                for k in range(lx + 4, lx + lw - 3, 3):
                    if rng.random() < 0.6:
                        cv2.line(img, (k, ly + lh // 2), (k, ly + lh - 4), (70, 70, 70), 1)
    cv2.polylines(img, [poly], True, SEAM, 2, cv2.LINE_AA)

    mask = np.zeros(depth.shape, np.uint8)
    cv2.fillPoly(mask, [poly], 1)
    depth[mask.astype(bool)] = p.protrusion
    return poly


def render(packages: list[SimPackage]) -> tuple[np.ndarray, np.ndarray, list[Detection]]:
    global _BG
    if _BG is None:
        _BG = _background()
    img = _BG.copy()
    depth = np.full((IMG_H, IMG_W), np.nan, np.float32)
    polys = [_draw_package(img, depth, p) for p in packages]
    gt: list[Detection] = []
    for i, (p, poly) in enumerate(zip(packages, polys)):
        x, y, w, h = cv2.boundingRect(poly)
        gt.append(Detection(i + 1, p.cls, 1.0, x, y, w, h, p.angle, p.protrusion, "groundtruth"))
    return img, depth, gt


class SimulatorSource:
    """A live 'camera' that shows a wall being built, then starts the next wall."""

    kind = "simulator"

    def __init__(self, skill: float = 0.6, seed: Optional[int] = None,
                 place_interval_s: float = 1.6, hold_s: float = 10.0, label: str = "CAM"):
        self.rng = np.random.default_rng(seed)
        self.skill = skill
        self.place_interval_s = place_interval_s
        self.hold_s = hold_s
        self.label = label
        self.wall_seq = 0
        self._new_wall()
        self._noise = [self.rng.normal(0, 3, (IMG_H, IMG_W, 1)).astype(np.int16) for _ in range(4)]
        self._tick = 0

    def _new_wall(self):
        self.wall_seq += 1
        jitter = float(self.rng.normal(0, 0.08))
        self.plan = plan_wall(self.rng, Profile(float(np.clip(self.skill + jitter, 0, 1))))
        self.k = int(self.rng.integers(2, 6))
        self.last_place = time.time()
        self.complete_at: Optional[float] = None
        self._cache_k = -1

    def calibration(self) -> Calibration:
        return sim_calibration()

    def read(self) -> Optional[Frame]:
        now = time.time()
        if self.complete_at is not None:
            if now - self.complete_at > self.hold_s:
                self._new_wall()
        elif now - self.last_place >= self.place_interval_s:
            self.k += 1
            self.last_place = now
            if self.k >= len(self.plan.packages):
                self.k = len(self.plan.packages)
                self.complete_at = now
        if self._cache_k != self.k:
            self._cache = render(self.plan.packages[: self.k])
            self._cache_k = self.k
        img, depth, gt = self._cache
        self._tick += 1
        frame = np.clip(img.astype(np.int16) + self._noise[self._tick % 4], 0, 255).astype(np.uint8)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"{self.label}  {stamp}", (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (235, 235, 235), 1, cv2.LINE_AA)
        return Frame(frame, now, depth, gt, {
            "wall_seq": self.wall_seq,
            "placed": self.k,
            "total": len(self.plan.packages),
            "complete": self.complete_at is not None,
        })

    def release(self):
        pass


def render_complete_wall(skill: float, seed: int) -> Frame:
    """One finished wall (used for history seeding and tests)."""
    rng = np.random.default_rng(seed)
    plan = plan_wall(rng, Profile(skill))
    img, depth, gt = render(plan.packages)
    return Frame(img, time.time(), depth, gt, {"complete": True, "total": len(plan.packages)})
