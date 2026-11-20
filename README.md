# LoadGuard — Real-Time Trailer Load Quality Monitoring

LoadGuard watches package walls being built inside trailers. It works out each wall's structure from camera frames, checks it against loading best practices, scores it, explains every problem in plain language, and pushes corrective guidance to handlers and managers in real time.

It uses only **pre-trained** detection (no custom training). Most of the system's value is in the parts after detection: wall reconstruction, a rule-based structural engine, scoring, explainability, and the operational workflow around them.

```
Camera / RTSP / video / handheld ─▶ Video service ─▶ Detection engine ─▶ Wall modeling
                                                     (YOLO11 + OpenCV)    (layers, seams,
                                                                            support graph, voids)
                                                                                 │
                                       ┌─────────────────────────────────────────┤
                                       ▼                                         ▼
                                  Rule engine (6 rules)                  Risk model (logistic)
                                       └──────────────┬──────────────────────────┘
                                                      ▼
                                   Explanation layer (what / why / risk / fix)
                                                      ▼
                         REST API + WebSocket ─▶ Manager dashboard · Handler app (Zebra)
                                                      ▼
                                            PostgreSQL (history, alerts)
```

## Quick start

### Docker (PostgreSQL, backend, frontend)

```bash
cp .env.example .env        # optional
docker compose up --build
```

- Dashboard: http://localhost:8080
- Handler app (open on the handheld): http://localhost:8080/handler
- API docs (OpenAPI): http://localhost:8000/docs

On first boot the system creates 6 simulated trailers (doors 101–106) and 8 fictional handlers. It then backfills 21 days of history by running the real pipeline over simulated walls, so the analytics pages have data straight away. Set `INSTALL_YOLO=false` for a slim image that uses the classical detector only.

### Local development (SQLite, no Docker)

```bash
# backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-yolo.txt   # yolo file optional
.venv/bin/uvicorn app.main:app --reload --port 8000

# frontend (in another terminal)
cd frontend
npm install
npm run dev        # http://localhost:5173 — proxies /api and /ws to :8000

# tests
cd backend && .venv/bin/pytest -q
```

## Connecting real cameras

Go to **Trailers & cameras → Add trailer** and pick a source:

| Source | `source_uri` | Notes |
|---|---|---|
| `rtsp` | `rtsp://user:pass@10.0.0.20:554/stream1` | Also accepts HTTP/MJPEG URLs. Reconnects automatically. |
| `webcam` | `0` | Device index on the server. |
| `video` | `/data/videos/load.mp4` | Recorded file on the server; loops. |
| `push` | – | Frames arrive at `POST /api/trailers/{id}/frames`. In the Handler app, tap **Use this device's camera** to stream from a Zebra handheld or phone. |
| `simulator` | – | Synthetic wall built live; the handler skill slider controls defect rates. |

**Calibration** (optional, JSON per trailer): `{"roi":[x0,y0,x1,y1], "floor_y":690, "px_per_inch":6.2, "trailer_height_in":108}`. Without it, the floor is taken from the lowest packages and scale is estimated from typical package size.

**Flush-face** needs depth (an RGB-D camera). Without depth it reports `N/A` rather than guessing, and it is left out of the score. The simulator emulates a depth sensor.

## How the analysis works

| Stage | Module | What it does |
|---|---|---|
| FR-2 Detection | `app/vision/detector.py` | `auto` = **hybrid**: pre-trained YOLO11 (COCO, class-mapped) fused with OpenCV contour segmentation for cardboard. Also `yolo`, `yoloworld` (open-vocabulary prompts such as "cardboard box" and "tire"), `classical`, and `groundtruth`. Rotated-rect fitting gives package tilt. |
| FR-3 Wall reconstruction | `app/analysis/wall.py` | Support graph (who rests on whom, support ratio), layers (longest support path from the floor), stacked columns, joints between neighbours, **seams** (joints chained vertically), and **voids** (occupancy grid + skyline "water-trapping": covered cavities and unfillable chimney gaps; open areas the next package will fill are *not* flagged). |
| FR-4 Flush face | `rules.flush_face` | Max protrusion, surface variance, face consistency (needs depth). |
| FR-5 T-stack | `rules.t_stack` | Interlock ratio (joints bridged by the package above) and seam continuity (seams through 3 or more layers). |
| FR-6 Level shelf | `rules.level_shelf` | Packages resting on supports of different heights; reports tilt angle and step. |
| FR-7 Voids | `rules.voids` | Area (sq in), kind and severity per void. |
| FR-8 Heavy on bottom | `rules.bottom_heavy` | Weight estimated from package type and size; heavy items high in the wall; centre of mass. |
| FR-9 Unsupported | `rules.unsupported` | Floating packages, overhangs (<50% supported), leaning packages. |
| FR-10 WQI | `analysis/scoring.py` | Weighted rule scores (rules with no data are re-weighted out) minus a capped penalty for HIGH findings. Every lost point is attributed to a rule. |
| FR-11 Risk | `analysis/scoring.py` | Transparent logistic model over structural deficits and wall height. Each factor's contribution is returned. |
| FR-12 Explainability | `analysis/explain.py` | Each issue gets: issue, reason (with measured evidence), risk, recommendation, and a short message. |
| FR-13 Alerts | `services/monitor.py` | A HIGH issue must persist for 3 consecutive analyses before it alerts (fewer false positives), then auto-resolves once fixed. Alerts are pushed over WebSocket with a snapshot image. |
| FR-14 Overlays | `vision/overlay.py`, `WallViewer.tsx` | Boxes, heatmap, dashed seam lines, hatched voids, corrective arrows, numbered markers. Rendered server-side (JPEG/MJPEG) and as an interactive SVG overlay in the UI. |

Measured on simulated walls (`tests/test_rules.py`): detector precision is about 100% and recall 99.9% against ground truth. Full analysis takes about 18 ms per frame with the classical detector and 70–120 ms with hybrid YOLO on a laptop CPU (target: under 2 s). Novice walls average WQI ≈25 (Hazardous) and expert walls ≈79 (Good).

## API (selected)

```
GET  /api/trailers                       live status of all trailers
GET  /api/trailers/{id}/latest           full analysis (detections, wall, rules, issues, WQI, risk)
GET  /api/trailers/{id}/detections       FR-2 detection list
GET  /api/trailers/{id}/frame.jpg        annotated still (?layers=boxes,seams,voids,heatmap,arrows,markers)
GET  /api/trailers/{id}/stream.mjpg      live MJPEG (?annotated=1)
POST /api/trailers/{id}/frames           push a frame (push sources)
POST /api/analyze                        analyze an uploaded image
POST /api/analyze/video                  analyze a recorded video (sampled)
GET  /api/alerts   POST /api/alerts/{id}/ack
GET  /api/analytics/{overview|trends|shifts|trailers|handlers}
GET  /api/reports/weekly[?format=csv]
WS   /ws                                 trailer_update, alert, alert_update events
```

## Configuration (env, prefix `LG_`)

`DATABASE_URL`, `DETECTOR`, `YOLO_MODEL`, `YOLOWORLD_MODEL`, `YOLO_CONF`, `CAPTURE_FPS` (6), `ANALYSIS_FPS` (2), `ALERT_DEBOUNCE` (3), `ALERT_RESOLVE_AFTER` (4), `SEED_DEMO`, `SEED_HISTORY_DAYS` (21), `SIM_PLACE_INTERVAL_S`, `SIM_HISTORY_MIN_INTERVAL_S`.

## Known limitations / next steps

- COCO has no "cardboard box" class, so box geometry comes from OpenCV segmentation. This is tuned for walls viewed face-on against a darker trailer interior and will be less reliable on cluttered real photos. Use `LG_DETECTOR=yoloworld`, or drop a box-trained YOLO model into `LG_YOLO_MODEL`; the rest of the pipeline is detector-agnostic.
- Weight is estimated from package type and size only (no scale data or deformation cues yet). Placement-sequence tracking (Phase 2) would strengthen FR-8.
- Push-style alerts reach the open Handler app (WebSocket with vibration, sound, and a full-screen takeover; system notifications only while the app is backgrounded). True background Web Push would need a service worker and VAPID keys.
- No authentication yet. Put it behind the site SSO or a reverse proxy before exposing it.
