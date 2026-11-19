"""End-to-end analysis of one frame: detect -> reconstruct -> rules -> score -> explain."""
from __future__ import annotations

import time
from typing import Any

from ..vision.detector import detect
from ..vision.types import Calibration, Frame
from .explain import RULE_NAMES, explain_issues, explain_rule, summarize
from .rules import SEV_RANK, run_rules
from .scoring import STATUS_FOR_GRADE, collapse_risk, grade_for, wall_quality_index
from .wall import reconstruct


def analyze_frame(frame: Frame, calib: Calibration, detector=None) -> dict[str, Any]:
    t0 = time.perf_counter()
    dets = detect(frame, calib, detector)
    t_det = time.perf_counter()

    wall = reconstruct(dets, calib)
    rules = run_rules(wall)
    issues = [i for r in rules for i in r.issues]
    issues.sort(key=lambda i: (-SEV_RANK[i.severity], i.rule))
    for k, i in enumerate(issues, 1):
        i.id = k
    explain_issues(issues)

    score, breakdown = wall_quality_index(rules, issues)
    risk, factors = collapse_risk(rules, wall)
    grade = grade_for(score)
    if not dets:
        score, grade, risk = 100, "Excellent", 0.0

    rule_dicts = []
    for r in rules:
        d = r.to_dict()
        d["name"] = RULE_NAMES[r.rule]
        d["explanation"] = explain_rule(r)
        rule_dicts.append(d)

    t1 = time.perf_counter()
    return {
        "timestamp": frame.timestamp,
        "imageSize": {"width": int(frame.image.shape[1]), "height": int(frame.image.shape[0])},
        "detections": [d.to_dict() for d in dets],
        "wall": wall.to_dict(),
        "rules": rule_dicts,
        "issues": [i.to_dict() for i in issues],
        "wallScore": score,
        "grade": grade,
        "status": STATUS_FOR_GRADE[grade],
        "collapseRisk": risk,
        "scoreBreakdown": breakdown,
        "riskFactors": factors,
        "summary": summarize(score, grade, risk, issues) if dets else "No packages detected yet.",
        "meta": frame.meta,
        "timing": {
            "detectMs": round(1000 * (t_det - t0), 1),
            "analyzeMs": round(1000 * (t1 - t_det), 1),
            "totalMs": round(1000 * (t1 - t0), 1),
        },
    }
