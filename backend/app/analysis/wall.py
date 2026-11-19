"""Wall reconstruction: turn flat 2-D detections into a structural model of the wall.

Produces layers (rows), stacked columns, joints (where two neighbouring packages meet),
seams (joints that line up vertically across layers), a support graph, and voids.
All geometry is in image pixels; `ppi` (pixels per inch) converts to physical units.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from ..vision.types import Calibration, Detection

DENSITY = {"box": 1.0, "tire": 3.2, "cylinder": 1.6, "irregular": 1.2, "bag": 0.35, "envelope": 0.1}
ASSUMED_PKG_HEIGHT_IN = 13.0  # used to estimate scale when the camera is uncalibrated


@dataclass
class Pkg:
    det: Detection
    on_floor: bool = False
    supporters: list[int] = field(default_factory=list)
    supporting: list[int] = field(default_factory=list)
    support_ratio: float = 1.0
    gap_below: float = 0.0
    layer: int = 0
    weight: float = 0.0
    column: Optional[int] = None

    @property
    def id(self) -> int:
        return self.det.id

    def to_dict(self, ppi: float) -> dict:
        d = self.det.to_dict()
        d.update({
            "layer": self.layer,
            "onFloor": self.on_floor,
            "supportedBy": self.supporters,
            "supportRatio": round(self.support_ratio, 2),
            "weightEstimate": round(self.weight, 1),
            "column": self.column,
            "heightFromFloorIn": None,
        })
        return d


@dataclass
class Joint:
    x: float
    y_top: float
    y_bot: float
    left: int
    right: int
    state: str = "open"  # open (nothing above) | bridged | aligned


@dataclass
class Seam:
    x: float
    y_top: float
    y_bot: float
    layers: int
    package_ids: list[int]


@dataclass
class Void:
    id: int
    x: float
    y: float
    w: float
    h: float
    area_px: float
    area_in2: float
    kind: str  # cavity (covered) | gap (open chimney)
    severity: str
    relative_size: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "area": round(self.area_in2, 0),
            "areaPx": int(self.area_px),
            "kind": self.kind,
            "severity": self.severity,
            "relativeSize": round(self.relative_size, 2),
            "bbox": {"x": round(self.x), "y": round(self.y), "width": round(self.w), "height": round(self.h)},
        }


@dataclass
class WallModel:
    packages: dict[int, Pkg]
    floor_y: float
    x0: float
    x1: float
    ppi: float
    ppi_estimated: bool
    med_w: float
    med_h: float
    tol_x: float
    tol_y: float
    joints: list[Joint]
    seams: list[Seam]
    voids: list[Void]
    pending_fill_px: float
    top_y: float
    skyline: list[float]
    trailer_height_in: float

    @property
    def height_px(self) -> float:
        return max(0.0, self.floor_y - self.top_y)

    @property
    def height_in(self) -> float:
        return self.height_px / self.ppi

    def layers(self) -> dict[int, list[Pkg]]:
        out: dict[int, list[Pkg]] = {}
        for p in self.packages.values():
            out.setdefault(p.layer, []).append(p)
        for v in out.values():
            v.sort(key=lambda p: p.det.x)
        return dict(sorted(out.items()))

    def to_dict(self) -> dict:
        rows = []
        for li, ps in self.layers().items():
            rows.append({
                "index": li,
                "packageIds": [p.id for p in ps],
                "topY": round(float(np.mean([p.det.y for p in ps])), 1),
                "bottomY": round(float(np.mean([p.det.y2 for p in ps])), 1),
            })
        cols: dict[int, list[int]] = {}
        for p in self.packages.values():
            if p.column is not None:
                cols.setdefault(p.column, []).append(p.id)
        columns = [
            {"index": i, "packageIds": ids,
             "x": round(float(np.mean([self.packages[k].det.cx for k in ids])), 1)}
            for i, ids in enumerate(v for v in cols.values() if len(v) >= 3)
        ]
        pk = []
        for p in self.packages.values():
            d = p.to_dict(self.ppi)
            d["heightFromFloorIn"] = round((self.floor_y - p.det.y2) / self.ppi, 1)
            pk.append(d)
        area_px = sum(v.area_px for v in self.voids)
        built = max(1.0, (self.x1 - self.x0) * self.height_px)
        return {
            "rows": rows,
            "columns": columns,
            "packages": pk,
            "seams": [
                {"x": round(s.x, 1), "yTop": round(s.y_top, 1), "yBottom": round(s.y_bot, 1),
                 "layers": s.layers, "packageIds": s.package_ids}
                for s in self.seams
            ],
            "voids": [v.to_dict() for v in self.voids],
            "skyline": [round(v, 1) for v in self.skyline],
            "metrics": {
                "packageCount": len(self.packages),
                "layerCount": len(self.layers()),
                "wallHeightIn": round(self.height_in, 1),
                "wallHeightPct": round(100 * self.height_in / self.trailer_height_in, 1),
                "voidAreaIn2": round(area_px / self.ppi ** 2, 0),
                "voidPct": round(100 * area_px / built, 1),
                "jointCount": len(self.joints),
                "pixelsPerInch": round(self.ppi, 2),
                "scaleEstimated": self.ppi_estimated,
                "floorY": round(self.floor_y, 1),
                "wallX": [round(self.x0, 1), round(self.x1, 1)],
            },
        }


def _overlap(a0, a1, b0, b1) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _union_len(intervals: list[tuple[float, float]]) -> float:
    total, cur0, cur1 = 0.0, None, None
    for s, e in sorted(intervals):
        if cur1 is None or s > cur1:
            if cur1 is not None:
                total += cur1 - cur0
            cur0, cur1 = s, e
        else:
            cur1 = max(cur1, e)
    if cur1 is not None:
        total += cur1 - cur0
    return total


def reconstruct(dets: list[Detection], calib: Calibration) -> WallModel:
    pkgs = {d.id: Pkg(d) for d in dets}
    if dets:
        med_w = float(np.median([d.w for d in dets]))
        med_h = float(np.median([d.h for d in dets]))
    else:
        med_w = med_h = 60.0
    tol_x = max(7.0, 0.14 * med_w)
    tol_y = max(6.0, 0.12 * med_h)

    floor_y = calib.floor_y if calib.floor_y else (max(d.y2 for d in dets) if dets else 0.0)
    if calib.roi:
        x0, x1 = float(calib.roi[0]), float(calib.roi[2])
    elif dets:
        x0, x1 = min(d.x for d in dets), max(d.x2 for d in dets)
    else:
        x0, x1 = 0.0, 1.0
    ppi_est = calib.px_per_inch is None
    ppi = calib.px_per_inch or max(1.0, med_h / ASSUMED_PKG_HEIGHT_IN)

    # ---- support graph -------------------------------------------------------------
    for a in pkgs.values():
        da = a.det
        a.on_floor = da.y2 >= floor_y - 1.6 * tol_y
        a.weight = DENSITY.get(da.cls, 1.0) * (da.w / ppi) * (da.h / ppi) * min(da.w, da.h) / ppi / 1000
        if a.on_floor:
            a.support_ratio = 1.0
            continue
        spans = []
        best_gap = floor_y - da.y2
        for b in pkgs.values():
            if b is a:
                continue
            db = b.det
            ov = _overlap(da.x, da.x2, db.x, db.x2)
            if ov < 3:
                continue
            dy = db.y - da.y2  # >0: b's top is below a's bottom
            if -1.6 * tol_y <= dy <= 1.6 * tol_y and db.cy > da.cy:
                a.supporters.append(b.id)
                spans.append((max(da.x, db.x), min(da.x2, db.x2)))
            elif dy > 0:
                best_gap = min(best_gap, dy)
        a.support_ratio = _union_len(spans) / max(da.w, 1) if spans else 0.0
        a.gap_below = 0.0 if spans else float(best_gap)
    for a in pkgs.values():
        for s in a.supporters:
            pkgs[s].supporting.append(a.id)

    # ---- layers (longest support path from the floor) ------------------------------
    for a in sorted(pkgs.values(), key=lambda p: -p.det.y2):
        if a.on_floor:
            a.layer = 0
        elif a.supporters:
            a.layer = 1 + max(pkgs[s].layer for s in a.supporters)
        else:
            below = [p for p in pkgs.values() if p.det.cy > a.det.cy
                     and _overlap(a.det.x, a.det.x2, p.det.x, p.det.x2) > 0]
            a.layer = 1 + max((p.layer for p in below), default=0)

    # ---- columns (packages stacked squarely on top of one another) -----------------
    parent = {i: i for i in pkgs}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a in pkgs.values():
        for s in a.supporters:
            b = pkgs[s].det
            if abs(a.det.x - b.x) < tol_x and abs(a.det.x2 - b.x2) < tol_x:
                parent[find(a.id)] = find(s)
    groups: dict[int, list[int]] = {}
    for i in pkgs:
        groups.setdefault(find(i), []).append(i)
    for ci, (_, members) in enumerate(sorted(groups.items())):
        if len(members) >= 2:
            for m in members:
                pkgs[m].column = ci

    # ---- joints & seams --------------------------------------------------------------
    gap_tol = max(10.0, 0.18 * med_w)
    joints: list[Joint] = []
    plist = list(pkgs.values())
    for a in plist:
        for b in plist:
            if a is b:
                continue
            da, db = a.det, b.det
            g = db.x - da.x2
            if -tol_x <= g <= gap_tol:
                vov = _overlap(da.y, da.y2, db.y, db.y2)
                if vov > 0.5 * min(da.h, db.h):
                    jx = (da.x2 + db.x) / 2
                    if jx - x0 < tol_x or x1 - jx < tol_x:
                        continue
                    joints.append(Joint(jx, max(da.y, db.y), min(da.y2, db.y2), a.id, b.id))

    for j in joints:
        for c in plist:
            dc = c.det
            if c.id in (j.left, j.right):
                continue
            if abs(dc.y2 - j.y_top) <= 1.8 * tol_y and dc.x < j.x + tol_x and dc.x2 > j.x - tol_x:
                if dc.x < j.x - tol_x and dc.x2 > j.x + tol_x:
                    j.state = "bridged"
                    break
                j.state = "aligned"

    # chain vertically aligned joints into seams
    order = sorted(range(len(joints)), key=lambda i: -joints[i].y_bot)
    chain = {i: 1 for i in order}
    prev: dict[int, Optional[int]] = {i: None for i in order}
    for idx in order:
        j = joints[idx]
        for k in order:
            if k == idx:
                continue
            jb = joints[k]  # candidate below
            if jb.y_bot <= j.y_bot:
                continue
            if abs(jb.x - j.x) <= tol_x and abs(j.y_bot - jb.y_top) <= 2.0 * tol_y:
                if chain[k] + 1 > chain[idx]:
                    chain[idx] = chain[k] + 1
                    prev[idx] = k
    used: set[int] = set()
    seams: list[Seam] = []
    for idx in sorted(order, key=lambda i: -chain[i]):
        if chain[idx] < 2 or idx in used:
            continue
        path = []
        cur: Optional[int] = idx
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        if any(p in used for p in path):
            continue
        used.update(path)
        js = [joints[p] for p in path]
        ids = sorted({i for jj in js for i in (jj.left, jj.right)})
        seams.append(Seam(float(np.mean([jj.x for jj in js])), min(jj.y_top for jj in js),
                          max(jj.y_bot for jj in js), len(js), ids))
    seams.sort(key=lambda s: -s.layers)

    # ---- voids -----------------------------------------------------------------------
    voids, pending, top_y, skyline = _find_voids(pkgs, floor_y, x0, x1, med_w, med_h, ppi)

    return WallModel(pkgs, floor_y, x0, x1, ppi, ppi_est, med_w, med_h, tol_x, tol_y,
                     joints, seams, voids, pending, top_y, skyline, calib.trailer_height_in)


def _find_voids(pkgs, floor_y, x0, x1, med_w, med_h, ppi):
    g = 4  # grid cell size in px
    if not pkgs:
        return [], 0.0, floor_y, []
    top = min(p.det.y for p in pkgs.values())
    gx0, gy0 = int(x0), int(top)
    W = max(1, int((x1 - x0) / g) + 1)
    H = max(1, int((floor_y - top) / g) + 1)
    occ = np.zeros((H, W), np.uint8)
    for p in pkgs.values():
        d = p.det
        c0, c1 = int((d.x - gx0) / g), int(np.ceil((d.x2 - gx0) / g))
        r0, r1 = int((d.y - gy0) / g), int(np.ceil((d.y2 - gy0) / g))
        occ[max(0, r0):max(0, r1), max(0, c0):max(0, c1)] = 1
    occ = cv2.dilate(occ, np.ones((3, 3), np.uint8))  # close detector seams between boxes

    rows_idx = np.arange(H)[:, None]
    any_occ = occ.any(axis=0)
    first = np.where(any_occ, occ.argmax(axis=0), H)  # skyline row per column
    height = H - first
    lmax = np.maximum.accumulate(height)
    rmax = np.maximum.accumulate(height[::-1])[::-1]
    level = np.maximum(height, np.minimum(lmax, rmax))
    cand = (occ == 0) & (rows_idx >= (H - level)[None, :])

    n, labels, stats, _ = cv2.connectedComponentsWithStats(cand.astype(np.uint8), 4)
    med_area = med_w * med_h
    voids: list[Void] = []
    pending = 0.0
    for i in range(1, n):
        cx, cy, cw, ch, area = stats[i]
        area_px = float(area * g * g)
        comp_cols = np.where((labels == i).any(axis=0))[0]
        comp_top = cy
        covered_frac = float(np.mean(first[comp_cols] < comp_top)) if len(comp_cols) else 0.0
        covered = covered_frac > 0.3
        w_px, h_px = cw * g, ch * g
        rel = area_px / max(med_area, 1)
        if covered:
            if rel < 0.1 or min(w_px, h_px) < 0.16 * med_h:
                continue
            kind = "cavity"
            sev = "HIGH" if rel >= 0.8 else "MEDIUM" if rel >= 0.3 else "LOW"
        else:
            if w_px < 0.6 * med_w and h_px > 0.6 * med_h:
                kind = "gap"
                sev = "HIGH" if h_px > 2.2 * med_h else "MEDIUM"
            else:
                pending += area_px  # open area the next package will fill; not a defect yet
                continue
        voids.append(Void(len(voids) + 1, gx0 + cx * g, gy0 + cy * g, w_px, h_px, area_px,
                          area_px / ppi ** 2, kind, sev, rel))
    voids.sort(key=lambda v: -v.area_px)
    for k, v in enumerate(voids, 1):
        v.id = k
    skyline = [float(gy0 + r * g) for r in first[:: max(1, W // 48)]]
    return voids, pending, float(top), skyline
