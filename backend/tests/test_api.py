import time

import cv2
from fastapi.testclient import TestClient

from app.main import app
from app.vision.simulator import render_complete_wall


def _wait_for_analysis(client, tid, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/api/trailers/{tid}/latest")
        if r.status_code == 200:
            return r.json()
        time.sleep(0.3)
    raise AssertionError("no analysis produced")


def test_end_to_end_api():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["ok"]
        trailers = client.get("/api/trailers").json()
        assert len(trailers) == 6
        tid = trailers[0]["trailerId"]

        latest = _wait_for_analysis(client, tid)
        assert {"detections", "wall", "rules", "issues", "wallScore", "collapseRisk"} <= set(latest)
        assert {"rows", "columns", "packages"} <= set(latest["wall"])
        assert {r["rule"] for r in latest["rules"]} == {
            "T_STACK", "FLUSH_FACE", "LEVEL_SHELF", "VOIDS", "BOTTOM_HEAVY", "UNSUPPORTED"}

        d = client.get(f"/api/trailers/{tid}/detections").json()["detections"]
        assert d and set(d[0]["bbox"]) == {"x", "y", "width", "height"}

        jpg = client.get(f"/api/trailers/{tid}/frame.jpg")
        assert jpg.status_code == 200 and jpg.headers["content-type"] == "image/jpeg"

        # single-image upload
        ok, buf = cv2.imencode(".jpg", render_complete_wall(0.2, 11).image)
        r = client.post("/api/analyze", files={"file": ("wall.jpg", buf.tobytes(), "image/jpeg")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["detections"] and body["annotatedImage"].startswith("data:image/jpeg")
        # uncalibrated upload: flush face needs depth and is reported N/A, not guessed
        assert next(x for x in body["rules"] if x["rule"] == "FLUSH_FACE")["status"] == "N/A"

        bad = client.post("/api/analyze", files={"file": ("x.jpg", b"not an image", "image/jpeg")})
        assert bad.status_code == 400

        # trailer CRUD + push source
        r = client.post("/api/trailers", json={"id": "T900", "door": 9, "source_type": "push"})
        assert r.status_code == 201
        r = client.post("/api/trailers/T900/frames", files={"file": ("f.jpg", buf.tobytes(), "image/jpeg")})
        assert r.status_code == 202
        _wait_for_analysis(client, "T900")
        assert client.delete("/api/trailers/T900").status_code == 204

        assert "rows" in client.get("/api/analytics/shifts").json()
        assert "highlights" in client.get("/api/reports/weekly").json()
        assert client.get("/api/reports/weekly?format=csv").text.startswith("LoadGuard weekly report")

        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "hello"
