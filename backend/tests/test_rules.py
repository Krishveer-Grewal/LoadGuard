"""Structural engine tests on hand-built walls (pixel coordinates, floor at y=600)."""
import numpy as np

from app.analysis.pipeline import analyze_frame
from app.analysis.rules import bottom_heavy, level_shelf, t_stack, unsupported, voids
from app.analysis.wall import reconstruct
from app.vision.detector import ClassicalDetector, detect, precision_recall
from app.vision.simulator import render_complete_wall, sim_calibration
from app.vision.types import Calibration, Detection

FLOOR = 600
CAL = Calibration(roi=(0, 0, 800, FLOOR), floor_y=FLOOR, px_per_inch=6.0)


def box(i, x, layer, w=100, h=80, cls="box", **kw):
    """Package `i` at x, sitting in row `layer` of uniform 80px rows (2px seams)."""
    y2 = FLOOR - layer * h
    return Detection(i, cls, 0.95, x + 1, y2 - h + 1, w - 2, h - 2, **kw)


def stacked_columns(rows=4):
    """Classic bad wall: identical columns, every seam continuous to the top."""
    d, i = [], 1
    for r in range(rows):
        for c in range(4):
            d.append(box(i, 100 + c * 100, r))
            i += 1
    return d


def brick_wall(rows=4):
    """Good wall: alternate rows offset by half a box (T-stacking)."""
    d, i = [], 1
    for r in range(rows):
        if r % 2 == 0:
            xs = [(100, 100), (200, 100), (300, 100), (400, 100)]
        else:
            xs = [(100, 50), (150, 100), (250, 100), (350, 100), (450, 50)]
        for x, w in xs:
            d.append(box(i, x, r, w=w))
            i += 1
    return d


def test_column_stacking_fails_tstack_and_reports_seams():
    wall = reconstruct(stacked_columns(), CAL)
    r = t_stack(wall)
    assert r.status == "FAIL"
    assert r.metrics["longestSeamLayers"] == 4
    assert any(i.code == "VERTICAL_SEAM" and i.severity == "HIGH" for i in r.issues)


def test_brick_pattern_passes_tstack():
    wall = reconstruct(brick_wall(), CAL)
    r = t_stack(wall)
    assert r.status == "PASS", r.metrics
    assert r.metrics["interlockRatio"] > 0.9
    assert not r.issues


def test_layers_and_support_graph():
    wall = reconstruct(brick_wall(), CAL)
    layers = wall.layers()
    assert sorted(layers) == [0, 1, 2, 3]
    top = [p for p in wall.packages.values() if p.layer == 1 and p.det.w > 90][0]
    assert len(top.supporters) == 2  # a bridging box rests on two below


def test_cavity_detected_under_bridging_package():
    d = [box(1, 100, 0), box(2, 300, 0),        # gap of 100px between them at floor level
         box(3, 150, 1, w=250)]                 # bridges over the gap
    wall = reconstruct(d, CAL)
    r = voids(wall)
    assert wall.voids and wall.voids[0].kind == "cavity"
    assert r.issues and r.issues[0].code == "VOID_CAVITY"


def test_open_area_on_unfinished_layer_is_not_a_void():
    d = [box(1, 100, 0), box(2, 200, 0), box(3, 100, 1)]  # partially built: right side simply not built yet
    wall = reconstruct(d, CAL)
    assert not wall.voids


def test_floating_and_leaning_packages():
    d = [box(1, 100, 0), box(2, 200, 0),
         Detection(3, "box", 0.9, 400, FLOOR - 260, 90, 70),       # floating high with nothing below
         box(4, 120, 1, angle=9.0)]                                # leaning on top of #1
    r = unsupported(reconstruct(d, CAL))
    codes = {i.code for i in r.issues}
    assert "FLOATING" in codes and "LEANING" in codes
    assert r.status != "PASS"


def test_uneven_shelf_detected():
    d = [box(1, 100, 0, h=80), Detection(2, "box", 0.9, 201, FLOOR - 50 + 1, 98, 48),  # shorter neighbour
         Detection(3, "box", 0.9, 150, FLOOR - 80 - 70 + 1, 120, 68)]                    # spans both
    r = level_shelf(reconstruct(d, CAL))
    assert r.issues and r.issues[0].code == "SHELF_SLOPE"


def test_tire_high_in_wall_warns():
    d = brick_wall(3)
    d.append(Detection(99, "tire", 0.9, 160, FLOOR - 3 * 80 - 56, 170, 56))
    r = bottom_heavy(reconstruct(d, CAL))
    assert r.status in ("WARNING", "FAIL")
    assert any(i.code == "HEAVY_HIGH" for i in r.issues)


def test_every_issue_is_explained():
    frame = render_complete_wall(0.1, 3)
    res = analyze_frame(frame, sim_calibration(), ClassicalDetector())
    assert res["issues"]
    for i in res["issues"]:
        for k in ("issue", "reason", "risk", "recommendation"):
            assert i[k], (i["code"], k)
    assert 0 <= res["wallScore"] <= 100 and 0 <= res["collapseRisk"] <= 1
    assert res["timing"]["totalMs"] < 2000


def test_score_separates_skill_levels():
    det, cal = ClassicalDetector(), sim_calibration()
    good = np.mean([analyze_frame(render_complete_wall(0.95, s), cal, det)["wallScore"] for s in range(8)])
    bad = np.mean([analyze_frame(render_complete_wall(0.05, s), cal, det)["wallScore"] for s in range(8)])
    assert good >= 70 and bad < 50 and good - bad > 30


def test_detector_precision_on_simulated_walls():
    det, cal = ClassicalDetector(), sim_calibration()
    ps = []
    for s in range(10):
        f = render_complete_wall(float(np.random.default_rng(s).uniform()), 500 + s)
        ps.append(precision_recall(detect(f, cal, det), f.ground_truth)[0])
    assert np.mean(ps) > 0.9
