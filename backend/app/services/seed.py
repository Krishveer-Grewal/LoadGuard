"""Demo data: handlers, simulated trailers, and weeks of history produced by running the real
pipeline over simulated walls (so analytics reflect the actual engine, not random numbers)."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

import numpy as np

from ..analysis.pipeline import analyze_frame
from ..config import settings
from ..db import Alert, Analysis, Handler, SessionLocal, Trailer
from ..vision.detector import ClassicalDetector
from ..vision.simulator import render_complete_wall, sim_calibration
from .monitor import persist_analysis

log = logging.getLogger("loadguard.seed")

# Fictional handlers: (name, badge, skill at start of history, skill now)
HANDLERS = [
    ("M. Okafor", "H-1042", 0.86, 0.95),
    ("D. Reyes", "H-1107", 0.40, 0.68),
    ("S. Patel", "H-1121", 0.58, 0.60),
    ("J. Kowalski", "H-1188", 0.15, 0.52),
    ("A. Nguyen", "H-1203", 0.72, 0.84),
    ("T. Brooks", "H-1219", 0.42, 0.30),
    ("L. Moreau", "H-1230", 0.90, 0.93),
    ("R. Haddad", "H-1254", 0.10, 0.38),
]
# trailer id, dock door, current handler index
TRAILERS = [("14531", 101, 0), ("19284", 102, 1), ("22371", 103, 7), ("30417", 104, 4),
            ("41126", 105, 5), ("52808", 106, 6)]

seed_status = {"state": "idle", "progress": 0.0}


def seed_base() -> bool:
    """Create handlers + trailers if the DB is empty. Returns True if seeded."""
    with SessionLocal() as db:
        if db.query(Trailer).count() > 0:
            return False
        hs = []
        for name, badge, s0, s1 in HANDLERS:
            h = Handler(name=name, badge=badge, skill=s1)
            db.add(h)
            hs.append(h)
        db.flush()
        for tid, door, hi in TRAILERS:
            db.add(Trailer(id=tid, door=door, source_type="simulator", sim_skill=HANDLERS[hi][3],
                           handler_id=hs[hi].id, calibration=sim_calibration().to_dict()))
        db.commit()
        return True


def _local_to_utc_naive(dt_local: datetime) -> datetime:
    return dt_local.astimezone(timezone.utc).replace(tzinfo=None)


def seed_history(days: int) -> None:
    seed_status["state"] = "running"
    det = ClassicalDetector()
    cal = sim_calibration()
    rng = np.random.default_rng(7)
    with SessionLocal() as db:
        handlers = db.query(Handler).order_by(Handler.id).all()
        trailers = db.query(Trailer).order_by(Trailer.id).all()
    now_local = datetime.now().astimezone()
    start = (now_local - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    total = days * 2 * len(trailers)
    done = 0
    seed_n = 10_000
    for d in range(days):
        day = start + timedelta(days=d)
        progress = d / max(days - 1, 1)
        with SessionLocal() as db:
            for si, (shift, h0) in enumerate((("A", 6), ("B", 14))):
                for ti, t in enumerate(trailers):
                    done += 1
                    hidx = (ti + d + si * 3) % len(handlers)
                    name, badge, s0, s1 = HANDLERS[hidx]
                    skill = float(np.clip(s0 + (s1 - s0) * progress + rng.normal(0, 0.05), 0, 1))
                    for k in range(3):
                        ts_local = day.replace(hour=h0) + timedelta(minutes=40 + 150 * k + int(rng.integers(0, 60)))
                        if ts_local > now_local - timedelta(minutes=30):
                            continue
                        seed_n += 1
                        frame = render_complete_wall(skill, seed_n)
                        r = analyze_frame(frame, cal, det)
                        ts = _local_to_utc_naive(ts_local)
                        persist_analysis(r, t.id, handlers[hidx].id, True, k + 1, ts=ts, db=db)
                        for issue in [i for i in r["issues"] if i["severity"] == "HIGH"][:2]:
                            ats = ts - timedelta(minutes=int(rng.integers(3, 25)))
                            acked = rng.random() < 0.8
                            ack_delay = timedelta(seconds=int(rng.integers(20, 420)))
                            db.add(Alert(
                                trailer_id=t.id, handler_id=handlers[hidx].id, ts=ats,
                                severity=issue["severity"], rule=issue["rule"], code=issue["code"],
                                issue_key=issue["key"], message=issue.get("shortMessage", issue["code"]),
                                detail=issue, status="resolved", wall_score=r["wallScore"],
                                acknowledged_at=ats + ack_delay if acked else None,
                                acknowledged_by=name if acked else None,
                                resolved_at=ats + ack_delay + timedelta(seconds=int(rng.integers(30, 300))),
                            ))
                    seed_status["progress"] = round(done / total, 2)
            db.commit()
    seed_status["state"] = "done"
    seed_status["progress"] = 1.0
    log.info("Seeded %d days of history", days)


def seed_all_async(on_base_ready) -> None:
    created = seed_base()
    on_base_ready()
    if not (created and settings.seed_demo and settings.seed_history_days > 0):
        seed_status["state"] = "done"
        return
    with SessionLocal() as db:
        if db.query(Analysis).count() > 0:
            seed_status["state"] = "done"
            return
    threading.Thread(target=seed_history, args=(settings.seed_history_days,), daemon=True,
                     name="seed-history").start()
