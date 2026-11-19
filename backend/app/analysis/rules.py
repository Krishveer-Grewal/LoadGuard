"""Structural rule engine (FR-4 .. FR-9).

Each rule returns a 0..1 score, a PASS / WARNING / FAIL / N/A status, the raw metrics it used,
and localized issues. Issues carry machine-readable `data`; the explanation layer turns
them into natural language.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .wall import WallModel

SEV_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


@dataclass
class Issue:
    rule: str
    code: str
    severity: str
    bbox: tuple[float, float, float, float]  # x, y, w, h
    package_ids: list[int] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    arrow: Optional[tuple[float, float, float, float]] = None  # x1,y1 -> x2,y2 corrective motion
    id: int = 0
    explanation: dict = field(default_factory=dict)

    @property
    def marker(self) -> tuple[float, float]:
        x, y, w, h = self.bbox
        return x + w / 2, y + h / 2

    @property
    def key(self) -> str:
        """Stable identity across frames for alert de-duplication (coarse location bucket)."""
        mx, my = self.marker
        return f"{self.code}:{int(mx // 60)}:{int(my // 60)}"

    def to_dict(self) -> dict:
        x, y, w, h = self.bbox
        d = {
            "id": self.id,
            "rule": self.rule,
            "code": self.code,
            "severity": self.severity,
            "key": self.key,
            "region": {"x": round(x), "y": round(y), "width": round(w), "height": round(h)},
            "marker": {"x": round(self.marker[0]), "y": round(self.marker[1])},
            "packageIds": self.package_ids,
            "data": self.data,
        }
        if self.arrow:
            d["arrow"] = {"x1": round(self.arrow[0]), "y1": round(self.arrow[1]),
                          "x2": round(self.arrow[2]), "y2": round(self.arrow[3])}
        d.update(self.explanation)
        return d


@dataclass
class RuleResult:
    rule: str
    score: Optional[float]
    status: str
    metrics: dict
    issues: list[Issue]
    weight: float

    def __post_init__(self):
        # A rule never reports PASS while it has a HIGH-severity finding.
        if self.status == "PASS" and any(i.severity == "HIGH" for i in self.issues):
            self.status = "WARNING"

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "score": None if self.score is None else round(self.score, 2),
            "status": self.status,
            "metrics": self.metrics,
            "issueCount": len(self.issues),
            "weight": self.weight,
        }


def status_for(score: Optional[float]) -> str:
    if score is None:
        return "N/A"
    return "PASS" if score >= 0.75 else "WARNING" if score >= 0.5 else "FAIL"


def _bbox_of(wall: WallModel, ids: list[int], pad: float = 4) -> tuple[float, float, float, float]:
    ds = [wall.packages[i].det for i in ids]
    x0 = min(d.x for d in ds) - pad
    y0 = min(d.y for d in ds) - pad
    x1 = max(d.x2 for d in ds) + pad
    y1 = max(d.y2 for d in ds) + pad
    return x0, y0, x1 - x0, y1 - y0


# --------------------------------------------------------------------------- FR-4

def flush_face(wall: WallModel) -> RuleResult:
    vals = [(p.id, p.det.protrusion) for p in wall.packages.values() if p.det.protrusion is not None]
    if not vals:
        return RuleResult("FLUSH_FACE", None, "N/A",
                          {"reason": "Depth data unavailable for this camera; flush-face needs an RGB-D sensor."},
                          [], 0.10)
    prot = np.array([v for _, v in vals])
    maxp = float(prot.max())
    variance = float(prot.std())
    consistency = float(np.mean(prot <= 2.0))
    score = float(np.clip(0.6 * consistency + 0.4 * (1 - min(1.0, maxp / 12)), 0, 1))
    issues = []
    for pid, v in vals:
        if v > 3.0:
            d = wall.packages[pid].det
            sev = "HIGH" if v > 6.5 else "MEDIUM"
            issues.append(Issue("FLUSH_FACE", "PROTRUSION", sev, (d.x, d.y, d.w, d.h), [pid],
                                {"protrusionIn": round(v, 1)}))
    return RuleResult("FLUSH_FACE", score, status_for(score), {
        "maxProtrusionIn": round(maxp, 1),
        "surfaceVarianceIn": round(variance, 2),
        "faceConsistency": round(consistency, 2),
    }, issues, 0.10)


# --------------------------------------------------------------------------- FR-5

def t_stack(wall: WallModel) -> RuleResult:
    joints = wall.joints
    bridged = sum(1 for j in joints if j.state == "bridged")
    aligned = sum(1 for j in joints if j.state == "aligned")
    covered = bridged + aligned
    interlock = bridged / covered if covered else 1.0
    excess = sum(max(0, s.layers - 2) for s in wall.seams)
    seam_pen = min(1.0, excess / 5)
    longest = max((s.layers for s in wall.seams), default=1 if joints else 0)
    score = float(np.clip(0.55 * interlock + 0.45 * (1 - seam_pen), 0, 1)) if joints else 1.0
    issues = []
    for s in wall.seams:
        if s.layers < 3:
            continue
        sev = "HIGH" if s.layers >= 4 else "MEDIUM"
        shift = wall.med_w * 0.5
        dir_ = 1 if s.x < (wall.x0 + wall.x1) / 2 else -1
        issues.append(Issue("T_STACK", "VERTICAL_SEAM", sev,
                            (s.x - wall.tol_x * 1.5, s.y_top, wall.tol_x * 3, s.y_bot - s.y_top),
                            s.package_ids,
                            {"layers": s.layers, "packages": len(s.package_ids),
                             "xIn": round((s.x - wall.x0) / wall.ppi, 0),
                             "heightIn": round((s.y_bot - s.y_top) / wall.ppi, 0)},
                            arrow=(s.x, s.y_top - 6, s.x + dir_ * shift, s.y_top - 6)))
    return RuleResult("T_STACK", score, status_for(score), {
        "joints": len(joints),
        "bridgedJoints": bridged,
        "alignedJoints": aligned,
        "interlockRatio": round(interlock, 2),
        "longestSeamLayers": longest,
        "seamsOver3Layers": sum(1 for s in wall.seams if s.layers >= 3),
        "seamAlignmentTolPx": round(wall.tol_x, 1),
    }, issues, 0.25)


# --------------------------------------------------------------------------- FR-6

def level_shelf(wall: WallModel) -> RuleResult:
    """A shelf is the surface the next layer sits on. It is 'not level' when a package rests on
    supports of different heights: it tilts toward the low side and bears on a corner."""
    issues = []
    worst_angle = 0.0
    tilted = 0
    for p in wall.packages.values():
        if p.on_floor:
            continue
        d = p.det
        below = [b.det for b in wall.packages.values()
                 if b is not p and b.det.cy > d.cy and b.det.y >= d.y2 - 1.6 * wall.tol_y]
        tops = []
        for sx in np.linspace(d.x + 0.08 * d.w, d.x2 - 0.08 * d.w, 9):
            under = [db.y for db in below if db.x <= sx <= db.x2]
            if under and min(under) <= d.y2 + 0.9 * wall.med_h:
                tops.append(min(under))  # surface directly beneath this point
        if len(tops) < 3:
            continue
        step = max(tops) - min(tops)
        if step <= 1.6 * wall.tol_y:
            continue
        angle = math.degrees(math.atan(step / max(d.w, 1)))
        worst_angle = max(worst_angle, angle)
        if angle >= 5.0:
            tilted += 1
            sev = "HIGH" if angle >= 12 else "MEDIUM"
            issues.append(Issue("LEVEL_SHELF", "SHELF_SLOPE", sev, (d.x, d.y, d.w, d.y2 + step - d.y), [p.id],
                                {"angle": round(angle, 1), "stepIn": round(step / wall.ppi, 1),
                                 "layer": p.layer}))
    per_layer = []
    for li, ps in wall.layers().items():
        if len(ps) >= 2:
            ys = [q.det.y for q in ps]
            per_layer.append({"layer": li, "elevationRangeIn": round((max(ys) - min(ys)) / wall.ppi, 1)})
    pen = sum(0.2 if i.severity == "HIGH" else 0.1 for i in issues)
    score = float(np.clip(1 - pen - 0.25 * min(1.0, worst_angle / 30), 0, 1))
    return RuleResult("LEVEL_SHELF", score, status_for(score), {
        "angle": round(worst_angle, 1),
        "tiltedPackages": tilted,
        "layers": per_layer,
    }, issues, 0.15)


def _overlap(a0, a1, b0, b1) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


# --------------------------------------------------------------------------- FR-7

def voids(wall: WallModel) -> RuleResult:
    built = max(1.0, (wall.x1 - wall.x0) * wall.height_px)
    area = sum(v.area_px for v in wall.voids if v.severity != "LOW")
    frac = area / built
    n_high = sum(1 for v in wall.voids if v.severity == "HIGH")
    score = float(np.clip(1 - min(1.0, frac * 6) - 0.08 * n_high, 0, 1))
    issues = []
    for v in wall.voids:
        if v.severity == "LOW":
            continue
        issues.append(Issue("VOIDS", "VOID_CAVITY" if v.kind == "cavity" else "VOID_GAP", v.severity,
                            (v.x, v.y, v.w, v.h), [],
                            {"voidId": v.id, "areaIn2": round(v.area_in2), "kind": v.kind,
                             "widthIn": round(v.w / wall.ppi, 0), "heightIn": round(v.h / wall.ppi, 0)}))
    return RuleResult("VOIDS", score, status_for(score), {
        "voidCount": len(wall.voids),
        "voidAreaIn2": round(sum(v.area_in2 for v in wall.voids)),
        "voidFraction": round(frac, 3),
        "pendingFillIn2": round(wall.pending_fill_px / wall.ppi ** 2),
    }, issues, 0.20)


# --------------------------------------------------------------------------- FR-8

def bottom_heavy(wall: WallModel) -> RuleResult:
    ps = list(wall.packages.values())
    if len(ps) < 4 or wall.height_px <= 0:
        return RuleResult("BOTTOM_HEAVY", 1.0, "PASS", {"centerOfMassRatio": None}, [], 0.10)
    weights = np.array([p.weight for p in ps])
    med = float(np.median(weights))
    heights = np.array([(wall.floor_y - p.det.cy) for p in ps])
    com = float((weights * heights).sum() / max(weights.sum(), 1e-6) / wall.height_px)
    issues = []
    for p in ps:
        hb = (wall.floor_y - p.det.y2) / wall.height_px
        if p.on_floor or hb < 0.4:
            continue
        sup_w = [wall.packages[s].weight for s in p.supporters]
        heavy = p.weight >= 3.5 * med and hb >= 0.5 and (not sup_w or p.weight > 2.0 * float(np.mean(sup_w)))
        if heavy or p.det.cls == "tire":
            d = p.det
            sev = "HIGH" if p.det.cls == "tire" or p.weight > 6 * med else "MEDIUM"
            issues.append(Issue("BOTTOM_HEAVY", "HEAVY_HIGH", sev, (d.x, d.y, d.w, d.h), [p.id],
                                {"class": d.cls, "weightRatio": round(p.weight / max(med, 1e-6), 1),
                                 "heightIn": round((wall.floor_y - d.y2) / wall.ppi)},
                                arrow=(d.cx, d.y2, d.cx, min(wall.floor_y - 6, d.y2 + 90))))
    score = 1 - 0.18 * len(issues) - max(0.0, com - 0.5) * 1.5
    score = float(np.clip(score, 0, 1))
    status = status_for(score)
    if status == "FAIL" and score > 0.3:
        status = "WARNING"
    return RuleResult("BOTTOM_HEAVY", score, status, {
        "centerOfMassRatio": round(com, 2),
        "heavyHighCount": len(issues),
        "indicators": ["package dimensions", "package type"],
    }, issues, 0.10)


# --------------------------------------------------------------------------- FR-9

def unsupported(wall: WallModel) -> RuleResult:
    issues = []
    non_floor = [p for p in wall.packages.values() if not p.on_floor]
    for p in non_floor:
        d = p.det
        if not p.supporters or p.support_ratio < 0.15:
            issues.append(Issue("UNSUPPORTED", "FLOATING", "HIGH", (d.x, d.y, d.w, d.h), [p.id],
                                {"supportPct": round(100 * p.support_ratio),
                                 "gapIn": round(p.gap_below / wall.ppi, 1)},
                                arrow=(d.cx, d.y2, d.cx, d.y2 + max(20, p.gap_below))))
        elif p.support_ratio < 0.5:
            sev = "HIGH" if p.support_ratio < 0.3 else "MEDIUM"
            issues.append(Issue("UNSUPPORTED", "OVERHANG", sev, (d.x, d.y, d.w, d.h), [p.id],
                                {"supportPct": round(100 * p.support_ratio)}))
        if abs(d.angle) > 4.0:
            sev = "HIGH" if abs(d.angle) > 8 else "MEDIUM"
            issues.append(Issue("UNSUPPORTED", "LEANING", sev, (d.x, d.y, d.w, d.h), [p.id],
                                {"angle": round(abs(d.angle), 1)}))
    pen = sum(0.22 if i.severity == "HIGH" else 0.1 for i in issues)
    score = float(np.clip(1 - pen, 0, 1))
    return RuleResult("UNSUPPORTED", score, status_for(score), {
        "checked": len(non_floor),
        "floating": sum(1 for i in issues if i.code == "FLOATING"),
        "overhangs": sum(1 for i in issues if i.code == "OVERHANG"),
        "leaning": sum(1 for i in issues if i.code == "LEANING"),
        "meanSupportRatio": round(float(np.mean([p.support_ratio for p in non_floor])), 2) if non_floor else 1.0,
    }, issues, 0.20)


ALL_RULES = (t_stack, flush_face, level_shelf, voids, bottom_heavy, unsupported)


def run_rules(wall: WallModel) -> list[RuleResult]:
    return [r(wall) for r in ALL_RULES]
