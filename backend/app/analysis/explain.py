"""Explainability engine (FR-12).

Every issue gets: what is wrong (issue), why the system thinks so (reason, with the measured
evidence), why it matters (risk) and a short, feasible corrective action (recommendation).
Recommendations are phrased for a handler mid-load: one action, plain words.
"""
from __future__ import annotations

from .rules import Issue, RuleResult

RULE_NAMES = {
    "T_STACK": "T-Stacking / Interlock",
    "FLUSH_FACE": "Flush Wall Face",
    "LEVEL_SHELF": "Level Shelves",
    "VOIDS": "Voids & Gaps",
    "BOTTOM_HEAVY": "Heavy on Bottom",
    "UNSUPPORTED": "Package Support",
}


def _explain(i: Issue) -> dict:
    d = i.data
    c = i.code
    if c == "VERTICAL_SEAM":
        return {
            "title": "Vertical seam detected",
            "issue": "Vertical seam detected",
            "reason": f"{d['packages']} packages share the same seam line about {d['xIn']:.0f}\" from the left wall, "
                      f"running through {d['layers']} consecutive layers ({d['heightIn']:.0f}\" tall).",
            "risk": "Columns on either side of a continuous seam are not tied together and can separate or "
                    "topple independently when the trailer brakes or turns.",
            "recommendation": "Offset the next package so it straddles this seam (brick / T-stack pattern) — "
                              "about half a box width to the side shown by the arrow.",
            "shortMessage": f"Vertical seam through {d['layers']} layers — offset next box.",
        }
    if c == "PROTRUSION":
        return {
            "title": "Package sticking out of wall face",
            "issue": "Package not flush with wall face",
            "reason": f"Package sits about {d['protrusionIn']:.1f}\" proud of the wall face (depth sensor).",
            "risk": "Protruding packages take the impact of the next wall, get crushed, and leave a gap "
                    "behind them that lets the wall shift.",
            "recommendation": "Push the package back until its face is flush with its neighbours.",
            "shortMessage": f"Package {d['protrusionIn']:.0f}\" out of face — push flush.",
        }
    if c == "SHELF_SLOPE":
        return {
            "title": "Shelf is not level",
            "issue": "Uneven shelf",
            "reason": f"Package sits on supports that differ by {d['stepIn']:.1f}\" in height, tilting it "
                      f"about {d['angle']:.0f}° (layer {d['layer'] + 1}).",
            "risk": "A package on an uneven shelf bears on one corner and slides toward the low side, "
                    "loading the wall unevenly and leaving a void beneath.",
            "recommendation": "Build up the low side with a thinner package so the shelf is level before stacking on it.",
            "shortMessage": f"Uneven shelf ({d['stepIn']:.0f}\" step) — level it first.",
        }
    if c == "SHELF_STEP":
        return {
            "title": "Step in shelf height",
            "issue": "Uneven shelf height",
            "reason": f"Neighbouring packages differ in height by {d['stepIn']:.1f}\" while carrying load above.",
            "risk": "Packages bridging a step rest on one corner, concentrating weight and creating a void.",
            "recommendation": "Match package heights within a layer, or fill the low side before bridging it.",
            "shortMessage": f"{d['stepIn']:.0f}\" step in shelf — match heights.",
        }
    if c == "VOID_CAVITY":
        sev_word = "Large" if i.severity == "HIGH" else "Medium"
        return {
            "title": f"{sev_word} unsupported void",
            "issue": f"{sev_word} void detected inside the wall",
            "reason": f"An enclosed empty space of about {d['areaIn2']:.0f} sq in "
                      f"({d['widthIn']:.0f}\" × {d['heightIn']:.0f}\") sits under packages above it.",
            "risk": "Packages above the cavity have nothing beneath them; vibration can collapse them into "
                    "the void and the wall loses its shape.",
            "recommendation": "Fill the void with a package or a soft bag that fits snugly before stacking higher.",
            "shortMessage": f"{sev_word} unsupported void detected.",
        }
    if c == "VOID_GAP":
        return {
            "title": "Chimney gap between stacks",
            "issue": "Narrow vertical gap",
            "reason": f"A {d['widthIn']:.0f}\"-wide gap runs {d['heightIn']:.0f}\" down between two stacks — "
                      "too narrow for a regular package.",
            "risk": "The stacks on either side can lean into the gap; it is also a crush point for small items.",
            "recommendation": "Fill the gap with a narrow box or bag, or re-space the stacks to close it.",
            "shortMessage": "Chimney gap between stacks — fill it.",
        }
    if c == "HEAVY_HIGH":
        kind = "tire" if d["class"] == "tire" else "heavy package"
        return {
            "title": "Heavy package placed high",
            "issue": f"{kind.capitalize()} high in the wall",
            "reason": f"A {kind} (~{d['weightRatio']:.1f}× typical weight, estimated from type and size) sits "
                      f"{d['heightIn']:.0f}\" above the floor on lighter freight.",
            "risk": "Heavy freight up high crushes packages below and raises the wall's centre of gravity, "
                    "making it more likely to topple.",
            "recommendation": "Move it down to the floor layer of the next wall; keep heavy items low.",
            "shortMessage": f"{kind.capitalize()} up high — move it to the floor.",
        }
    if c == "FLOATING":
        return {
            "title": "Unsupported package",
            "issue": "Package with no support beneath it",
            "reason": f"Only {d['supportPct']}% of the package's base rests on anything; "
                      f"there is about a {d['gapIn']:.0f}\" drop below it.",
            "risk": "An unsupported package will drop when the trailer moves, damaging itself and freight below.",
            "recommendation": "Fill the space beneath it, or move it onto a full-width base.",
            "shortMessage": "Package floating with no support.",
        }
    if c == "OVERHANG":
        return {
            "title": "Package overhang",
            "issue": "Package overhangs its support",
            "reason": f"Only {d['supportPct']}% of its base is resting on packages below.",
            "risk": "Overhanging packages tip toward the unsupported side and can pull the layer with them.",
            "recommendation": "Slide the package over so at least half of it rests on the packages below.",
            "shortMessage": f"Overhang: only {d['supportPct']}% supported.",
        }
    if c == "LEANING":
        return {
            "title": "Leaning package",
            "issue": "Package is leaning",
            "reason": f"Package is tilted {d['angle']:.1f}° from square.",
            "risk": "Leaning packages push sideways on neighbours and start a domino failure.",
            "recommendation": "Square it up so it sits flat; wedge with a filler if the space is too wide.",
            "shortMessage": f"Package leaning {d['angle']:.0f}° — square it up.",
        }
    return {"title": c, "issue": c, "reason": "", "risk": "", "recommendation": "", "shortMessage": c}


def explain_issues(issues: list[Issue]) -> None:
    for i in issues:
        i.explanation = _explain(i)


def explain_rule(r: RuleResult) -> str:
    m = r.metrics
    if r.status == "N/A":
        return m.get("reason", "Not applicable.")
    if r.rule == "T_STACK":
        return (f"{m['bridgedJoints']} of {m['bridgedJoints'] + m['alignedJoints']} covered joints are bridged by the "
                f"package above (interlock {m['interlockRatio']:.0%}); longest seam spans {m['longestSeamLayers']} layers.")
    if r.rule == "FLUSH_FACE":
        return (f"Max protrusion {m['maxProtrusionIn']}\"; {m['faceConsistency']:.0%} of packages within 2\" of the "
                f"wall face (variance {m['surfaceVarianceIn']}\").")
    if r.rule == "LEVEL_SHELF":
        return (f"{m['tiltedPackages']} package(s) rest on an uneven shelf; worst tilt {m['angle']}°.")
    if r.rule == "VOIDS":
        return (f"{m['voidCount']} void(s) totalling {m['voidAreaIn2']} sq in "
                f"({m['voidFraction']:.1%} of the built wall face).")
    if r.rule == "BOTTOM_HEAVY":
        com = m.get("centerOfMassRatio")
        if com is None:
            return "Too few packages to judge weight distribution yet."
        return f"Estimated centre of mass at {com:.0%} of wall height; {m['heavyHighCount']} heavy item(s) placed high."
    if r.rule == "UNSUPPORTED":
        return (f"{m['floating']} floating, {m['overhangs']} overhanging and {m['leaning']} leaning package(s) "
                f"among {m['checked']} above the floor.")
    return ""


def summarize(score: int, grade: str, risk: float, issues: list[Issue]) -> str:
    if not issues:
        return f"Wall scores {score}/100 ({grade}). No structural issues detected — keep building this way."
    counts: dict[str, int] = {}
    for i in issues:
        t = i.explanation.get("title", i.code)
        counts[t] = counts.get(t, 0) + 1
    top = ", ".join(f"{n}× {t.lower()}" for t, n in sorted(counts.items(), key=lambda kv: -kv[1])[:3])
    first = issues[0].explanation.get("recommendation", "")
    return (f"Wall scores {score}/100 ({grade}) with {risk:.0%} estimated collapse risk. "
            f"Main concerns: {top}. Fix first: {first}")
