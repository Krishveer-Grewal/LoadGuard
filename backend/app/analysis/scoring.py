"""Wall Quality Index (FR-10) and collapse-risk model (FR-11).

WQI: weighted average of rule scores (rules without data are excluded and weights
renormalised), minus a capped penalty for HIGH-severity findings. Every point lost is
attributed back to a rule so the score is never a black box.

Risk: a transparent logistic model over structural deficits. Coefficients are hand-set from
loading best practice (support and interlock matter most), not learned; each factor's
contribution to the log-odds is returned for explainability.
"""
from __future__ import annotations

import math

from .rules import Issue, RuleResult
from .wall import WallModel

GRADES = [(90, "Excellent"), (75, "Good"), (50, "Needs Attention"), (0, "Hazardous")]
STATUS_FOR_GRADE = {"Excellent": "Good", "Good": "Good", "Needs Attention": "Warning", "Hazardous": "Hazard"}

RISK_COEF = {
    "UNSUPPORTED": 2.4,
    "T_STACK": 2.0,
    "VOIDS": 1.8,
    "LEVEL_SHELF": 1.0,
    "BOTTOM_HEAVY": 1.2,
    "FLUSH_FACE": 0.7,
}
RISK_BIAS = -3.4


def grade_for(score: float) -> str:
    for lo, g in GRADES:
        if score >= lo:
            return g
    return "Hazardous"


def wall_quality_index(rules: list[RuleResult], issues: list[Issue]) -> tuple[int, list[dict]]:
    active = [r for r in rules if r.score is not None]
    total_w = sum(r.weight for r in active) or 1.0
    breakdown = []
    for r in active:
        w = r.weight / total_w
        breakdown.append({
            "rule": r.rule,
            "weight": round(w, 3),
            "score": round(r.score, 2),
            "pointsLost": round(100 * w * (1 - r.score), 1),
        })
    base = sum(100 * (r.weight / total_w) * r.score for r in active)
    n_high = sum(1 for i in issues if i.severity == "HIGH")
    penalty = min(15.0, 3.0 * n_high)
    if penalty:
        breakdown.append({"rule": "HIGH_SEVERITY_PENALTY", "weight": 0, "score": None, "pointsLost": round(penalty, 1)})
    return int(round(max(0.0, min(100.0, base - penalty)))), breakdown


def collapse_risk(rules: list[RuleResult], wall: WallModel) -> tuple[float, list[dict]]:
    z = RISK_BIAS
    factors = []
    for r in rules:
        if r.score is None:
            continue
        c = RISK_COEF.get(r.rule, 0.5) * (1 - r.score)
        z += c
        factors.append({"factor": r.rule, "contribution": round(c, 2)})
    height_frac = min(1.0, wall.height_in / max(wall.trailer_height_in, 1))
    hc = 0.9 * height_frac
    z += hc
    factors.append({"factor": "WALL_HEIGHT", "contribution": round(hc, 2)})
    risk = 1 / (1 + math.exp(-z))
    factors.sort(key=lambda f: -f["contribution"])
    return round(risk, 2), factors
