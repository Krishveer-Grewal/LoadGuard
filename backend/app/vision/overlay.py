"""Visual overlay generation (FR-14): boxes, heatmap, seams, voids, arrows, markers."""
from __future__ import annotations

import cv2
import numpy as np

SEV_COLOR = {"HIGH": (60, 60, 235), "MEDIUM": (40, 170, 250), "LOW": (200, 200, 90)}
OK_COLOR = (120, 200, 90)
ALL_LAYERS = ("boxes", "heatmap", "seams", "voids", "arrows", "markers", "hud")


def _dashed_line(img, p1, p2, color, thickness=2, dash=10):
    p1, p2 = np.array(p1, float), np.array(p2, float)
    length = np.linalg.norm(p2 - p1)
    if length < 1:
        return
    d = (p2 - p1) / length
    for s in np.arange(0, length, dash * 2):
        a = p1 + d * s
        b = p1 + d * min(s + dash, length)
        cv2.line(img, tuple(a.astype(int)), tuple(b.astype(int)), color, thickness, cv2.LINE_AA)


def render_overlay(image: np.ndarray, result: dict, layers=ALL_LAYERS) -> np.ndarray:
    out = image.copy()
    H, W = out.shape[:2]
    issues = result.get("issues", [])
    pkg_sev: dict[int, str] = {}
    rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    for i in issues:
        for pid in i["packageIds"]:
            if rank[i["severity"]] > rank.get(pkg_sev.get(pid, ""), 0):
                pkg_sev[pid] = i["severity"]

    if "heatmap" in layers and issues:
        heat = np.zeros((H, W), np.float32)
        for i in issues:
            r = i["region"]
            w = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}[i["severity"]]
            x0, y0 = max(0, r["x"]), max(0, r["y"])
            x1, y1 = min(W, r["x"] + r["width"]), min(H, r["y"] + r["height"])
            heat[y0:y1, x0:x1] += w
        heat = cv2.GaussianBlur(heat, (0, 0), 25)
        if heat.max() > 0:
            norm = np.clip(heat / max(heat.max(), 1.0), 0, 1)
            cmap = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_JET)
            alpha = (norm * 0.45)[..., None]
            out = (out * (1 - alpha) + cmap * alpha).astype(np.uint8)

    if "voids" in layers:
        for v in result.get("wall", {}).get("voids", []):
            b = v["bbox"]
            col = SEV_COLOR.get(v["severity"], (200, 200, 90))
            x0, y0, x1, y1 = b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"]
            sub = out[y0:y1, x0:x1]
            if sub.size:
                tint = np.full_like(sub, col)
                out[y0:y1, x0:x1] = cv2.addWeighted(sub, 0.55, tint, 0.45, 0)
                for k in range(-b["height"], b["width"], 10):
                    cv2.line(out, (x0 + k, y1), (x0 + k + b["height"], y0), col, 1, cv2.LINE_AA)
                cv2.rectangle(out, (x0, y0), (x1, y1), col, 2)

    if "boxes" in layers:
        for d in result.get("detections", []):
            b = d["bbox"]
            col = SEV_COLOR.get(pkg_sev.get(d["id"], ""), OK_COLOR)
            th = 3 if d["id"] in pkg_sev else 1
            cv2.rectangle(out, (int(b["x"]), int(b["y"])), (int(b["x"] + b["width"]), int(b["y"] + b["height"])),
                          col, th, cv2.LINE_AA)

    if "seams" in layers:
        for s in result.get("wall", {}).get("seams", []):
            if s["layers"] >= 3:
                col = SEV_COLOR["HIGH" if s["layers"] >= 4 else "MEDIUM"]
                _dashed_line(out, (s["x"], s["yTop"]), (s["x"], s["yBottom"]), col, 4, 12)

    if "arrows" in layers:
        for i in issues:
            a = i.get("arrow")
            if a:
                cv2.arrowedLine(out, (a["x1"], a["y1"]), (a["x2"], a["y2"]), (255, 255, 255), 6, cv2.LINE_AA,
                                tipLength=0.3)
                cv2.arrowedLine(out, (a["x1"], a["y1"]), (a["x2"], a["y2"]), SEV_COLOR[i["severity"]], 3,
                                cv2.LINE_AA, tipLength=0.3)

    if "markers" in layers:
        for i in issues:
            m = i["marker"]
            col = SEV_COLOR[i["severity"]]
            cv2.circle(out, (m["x"], m["y"]), 13, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(out, (m["x"], m["y"]), 13, col, 3, cv2.LINE_AA)
            txt = str(i["id"])
            (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.putText(out, txt, (m["x"] - tw // 2, m["y"] + th // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (30, 30, 30), 2, cv2.LINE_AA)

    if "hud" in layers and "wallScore" in result:
        score = result["wallScore"]
        col = (90, 190, 80) if score >= 75 else (40, 170, 250) if score >= 50 else (60, 60, 235)
        cv2.rectangle(out, (W - 250, 8), (W - 8, 64), (25, 25, 25), -1)
        cv2.rectangle(out, (W - 250, 8), (W - 8, 64), col, 2)
        cv2.putText(out, f"WQI {score}", (W - 238, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.95, col, 2, cv2.LINE_AA)
        cv2.putText(out, f"risk {result['collapseRisk']:.0%}", (W - 110, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (230, 230, 230), 1, cv2.LINE_AA)
    return out


def encode_jpeg(img: np.ndarray, quality: int = 80) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""
