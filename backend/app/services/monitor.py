"""Real-time trailer monitoring: one worker thread per trailer.

capture -> analyze (at analysis_fps) -> overlay -> alert engine -> WebSocket push -> persist.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime
from typing import Optional

from ..analysis.pipeline import analyze_frame
from ..config import settings
from ..db import Alert, Analysis, SessionLocal, Trailer, iso, shift_for, utcnow
from ..vision.overlay import encode_jpeg, render_overlay
from ..vision.sources import create_source
from .hub import hub

log = logging.getLogger("loadguard.monitor")
SEV_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def alert_to_dict(a: Alert) -> dict:
    return {
        "id": a.id,
        "trailerId": a.trailer_id,
        "handlerId": a.handler_id,
        "timestamp": iso(a.ts),
        "severity": a.severity,
        "rule": a.rule,
        "code": a.code,
        "message": a.message,
        "detail": a.detail,
        "status": a.status,
        "wallScore": a.wall_score,
        "acknowledgedAt": iso(a.acknowledged_at),
        "acknowledgedBy": a.acknowledged_by,
        "resolvedAt": iso(a.resolved_at),
        "hasSnapshot": bool(a.snapshot),
    }


class AlertEngine:
    """Debounces issues so transient detections during normal loading don't page anyone.

    An issue must appear in `alert_debounce` consecutive analyses before an alert fires, and an
    alert auto-resolves after the issue is absent for `alert_resolve_after` analyses.
    """

    def __init__(self, trailer_id: str):
        self.trailer_id = trailer_id
        self.streak: dict[str, int] = {}
        self.missing: dict[str, int] = {}
        self.active: dict[str, int] = {}  # issue key -> alert id

    def process(self, result: dict, handler_id: Optional[int], snapshot_jpeg: bytes) -> list[dict]:
        events = []
        present = {i["key"]: i for i in result["issues"] if i["severity"] == "HIGH"}
        for k in list(self.streak):
            if k not in present:
                self.streak.pop(k)
        for k, issue in present.items():
            self.streak[k] = self.streak.get(k, 0) + 1
            self.missing.pop(k, None)
            if k not in self.active and self.streak[k] >= settings.alert_debounce:
                events.append(self._create(issue, result, handler_id, snapshot_jpeg))
        for k in list(self.active):
            if k not in present:
                self.missing[k] = self.missing.get(k, 0) + 1
                if self.missing[k] >= settings.alert_resolve_after:
                    ev = self._resolve(self.active.pop(k))
                    self.missing.pop(k, None)
                    if ev:
                        events.append(ev)
        return events

    def _create(self, issue: dict, result: dict, handler_id, jpeg: bytes) -> dict:
        with SessionLocal() as db:
            a = Alert(trailer_id=self.trailer_id, handler_id=handler_id, severity=issue["severity"],
                      rule=issue["rule"], code=issue["code"], issue_key=issue["key"],
                      message=issue.get("shortMessage") or issue.get("title", issue["code"]),
                      detail=issue, wall_score=result["wallScore"])
            db.add(a)
            db.commit()
            path = settings.data_dir / "snapshots" / f"alert_{a.id}.jpg"
            path.write_bytes(jpeg)
            a.snapshot = str(path)
            db.commit()
            self.active[issue["key"]] = a.id
            return {"type": "alert", "alert": alert_to_dict(a)}

    def _resolve(self, alert_id: int) -> Optional[dict]:
        with SessionLocal() as db:
            a = db.get(Alert, alert_id)
            if not a or a.status == "resolved":
                return None
            a.status = "resolved"
            a.resolved_at = utcnow()
            db.commit()
            return {"type": "alert_update", "alert": alert_to_dict(a)}

    def resolve_all(self):
        for aid in list(self.active.values()):
            ev = self._resolve(aid)
            if ev:
                hub.publish(ev)
        self.active.clear()
        self.streak.clear()


class TrailerWorker(threading.Thread):
    def __init__(self, trailer: Trailer):
        super().__init__(daemon=True, name=f"trailer-{trailer.id}")
        self.trailer_id = trailer.id
        self.door = trailer.door
        self.handler_id = trailer.handler_id
        self.source_type = trailer.source_type
        self.source = create_source(trailer)
        self.calib = self.source.calibration()
        self.alerts = AlertEngine(trailer.id)
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.raw_jpeg: bytes = b""
        self.annotated_jpeg: bytes = b""
        self.latest_image = None
        self.analyzed_image = None  # exact frame the latest analysis refers to
        self.latest: Optional[dict] = None
        self.timeline: deque = deque(maxlen=600)
        self.last_persist = 0.0
        self.last_wall_seq: Optional[int] = None
        self.persisted_complete: set[int] = set()
        self.last_sim_wall_recorded = 0.0
        self.frame_counter = 0
        self.updated_at: Optional[float] = None

    # -- public -------------------------------------------------------------------
    def summary(self) -> dict:
        r = self.latest
        return {
            "trailerId": self.trailer_id,
            "door": self.door,
            "handlerId": self.handler_id,
            "sourceType": self.source_type,
            "online": self.updated_at is not None and time.time() - self.updated_at < 10,
            "sourceError": getattr(self.source, "error", None),
            "wallScore": r["wallScore"] if r else None,
            "grade": r["grade"] if r else None,
            "status": r["status"] if r else "Offline",
            "collapseRisk": r["collapseRisk"] if r else None,
            "issueCount": len(r["issues"]) if r else 0,
            "highCount": sum(1 for i in r["issues"] if i["severity"] == "HIGH") if r else 0,
            "topIssue": r["issues"][0]["title"] if r and r["issues"] else None,
            "activeAlerts": len(self.alerts.active),
            "packages": len(r["detections"]) if r else 0,
            "wallSeq": (r or {}).get("meta", {}).get("wall_seq"),
            "progress": self._progress(r),
            "latencyMs": r["timing"]["totalMs"] if r else None,
            "updatedAt": self.updated_at,
        }

    def _progress(self, r):
        if not r:
            return None
        m = r.get("meta") or {}
        if m.get("total"):
            return round(min(1.0, m["placed"] / m["total"]), 2)
        return round(r["wall"]["metrics"]["wallHeightPct"] / 100, 2)

    def stop(self):
        self.stop_event.set()

    # -- loop ---------------------------------------------------------------------
    def run(self):
        cap_dt = 1 / max(settings.capture_fps, 0.5)
        ana_dt = 1 / max(settings.analysis_fps, 0.1)
        last_analysis = 0.0
        last_frame_ts = None
        while not self.stop_event.is_set():
            t0 = time.time()
            try:
                frame = self.source.read()
                if frame is not None:
                    self.latest_image = frame.image
                    raw = encode_jpeg(frame.image, 75)
                    with self.lock:
                        self.raw_jpeg = raw
                    is_new = frame.timestamp != last_frame_ts
                    if is_new and t0 - last_analysis >= ana_dt:
                        last_analysis = t0
                        last_frame_ts = frame.timestamp
                        self._analyze(frame)
            except Exception:
                log.exception("worker %s error", self.trailer_id)
                time.sleep(1)
            self.stop_event.wait(max(0.0, cap_dt - (time.time() - t0)))
        self.source.release()
        self.alerts.resolve_all()

    def _analyze(self, frame):
        result = analyze_frame(frame, self.calib)
        result["trailerId"] = self.trailer_id
        result["handlerId"] = self.handler_id
        self.frame_counter += 1
        result["frameId"] = self.frame_counter
        annotated = encode_jpeg(render_overlay(frame.image, result), 78)
        with self.lock:
            self.analyzed_image = frame.image
            self.latest = result
            self.annotated_jpeg = annotated
            self.updated_at = time.time()
        self.timeline.append({
            "t": frame.timestamp, "score": result["wallScore"], "risk": result["collapseRisk"],
            "issues": len(result["issues"]), "packages": len(result["detections"]),
        })

        seq = (result.get("meta") or {}).get("wall_seq")
        if self.last_wall_seq is not None and seq is not None and seq != self.last_wall_seq:
            self.alerts.resolve_all()  # new wall started
        self.last_wall_seq = seq

        for ev in self.alerts.process(result, self.handler_id, annotated):
            hub.publish(ev)

        complete = bool((result.get("meta") or {}).get("complete"))
        now = time.time()
        if complete and self.source_type == "simulator" and seq not in self.persisted_complete:
            if now - self.last_sim_wall_recorded < settings.sim_history_min_interval_s:
                self.persisted_complete.add(seq)  # skip recording this simulated wall
            else:
                self.last_sim_wall_recorded = now
        if (complete and seq not in self.persisted_complete) or now - self.last_persist >= settings.persist_interval_s:
            self.last_persist = now
            if complete:
                self.persisted_complete.add(seq)
            persist_analysis(result, self.trailer_id, self.handler_id, complete, seq or 0)

        hub.publish({"type": "trailer_update", "trailer": self.summary()})


def persist_analysis(result: dict, trailer_id: str, handler_id, complete: bool, wall_seq: int,
                     ts: Optional[datetime] = None, db=None) -> None:
    counts: dict[str, int] = {}
    for i in result["issues"]:
        counts[i["code"]] = counts.get(i["code"], 0) + 1
    ts = ts or utcnow()
    row = Analysis(
        trailer_id=trailer_id, handler_id=handler_id, ts=ts, shift=shift_for(ts),
        wall_seq=wall_seq, wall_complete=complete, wall_score=result["wallScore"],
        collapse_risk=result["collapseRisk"], grade=result["grade"], status=result["status"],
        rule_scores={r["rule"]: r["score"] for r in result["rules"]}, issue_counts=counts,
        high_count=sum(1 for i in result["issues"] if i["severity"] == "HIGH"),
        issue_total=len(result["issues"]), package_count=len(result["detections"]),
        latency_ms=result["timing"]["totalMs"], summary=result["summary"],
        result=result if complete else None,
    )
    if db is not None:
        db.add(row)
        return
    with SessionLocal() as s:
        s.add(row)
        s.commit()


class Monitor:
    def __init__(self):
        self.workers: dict[str, TrailerWorker] = {}
        self.lock = threading.Lock()

    def start_all(self):
        with SessionLocal() as db:
            for t in db.query(Trailer).filter(Trailer.active.is_(True)).all():
                self.start(t)

    def start(self, trailer: Trailer):
        with self.lock:
            old = self.workers.pop(trailer.id, None)
            if old:
                old.stop()
            w = TrailerWorker(trailer)
            self.workers[trailer.id] = w
            w.start()
            log.info("Started worker for trailer %s (%s)", trailer.id, trailer.source_type)

    def stop(self, trailer_id: str):
        with self.lock:
            w = self.workers.pop(trailer_id, None)
        if w:
            w.stop()

    def stop_all(self):
        for tid in list(self.workers):
            self.stop(tid)

    def get(self, trailer_id: str) -> Optional[TrailerWorker]:
        return self.workers.get(trailer_id)


monitor = Monitor()
