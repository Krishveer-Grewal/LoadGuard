from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from ..db import Alert, SessionLocal, utcnow
from ..services import analytics
from ..services.hub import hub
from ..services.monitor import alert_to_dict, monitor
from ..services.seed import seed_status

router = APIRouter(prefix="/api", tags=["alerts", "analytics"])


class AckIn(BaseModel):
    by: str = "manager"


@router.get("/alerts")
def list_alerts(status: Optional[str] = None, trailer_id: Optional[str] = None,
                severity: Optional[str] = None, limit: int = Query(100, le=1000), offset: int = 0):
    with SessionLocal() as db:
        q = db.query(Alert)
        if status:
            q = q.filter(Alert.status.in_(status.split(",")))
        if trailer_id:
            q = q.filter(Alert.trailer_id == trailer_id)
        if severity:
            q = q.filter(Alert.severity == severity)
        total = q.count()
        rows = q.order_by(Alert.ts.desc()).offset(offset).limit(limit).all()
        return {"total": total, "alerts": [alert_to_dict(a) for a in rows]}


@router.post("/alerts/{aid}/ack")
def ack_alert(aid: int, body: AckIn):
    with SessionLocal() as db:
        a = db.get(Alert, aid)
        if not a:
            raise HTTPException(404, "Alert not found")
        if a.status == "active":
            a.status = "acknowledged"
        if not a.acknowledged_at:
            a.acknowledged_at = utcnow()
            a.acknowledged_by = body.by[:80]
        db.commit()
        d = alert_to_dict(a)
    hub.publish({"type": "alert_update", "alert": d})
    return d


@router.get("/alerts/{aid}/snapshot.jpg")
def alert_snapshot(aid: int):
    with SessionLocal() as db:
        a = db.get(Alert, aid)
        if not a or not a.snapshot or not Path(a.snapshot).exists():
            raise HTTPException(404, "No snapshot")
        return FileResponse(a.snapshot, media_type="image/jpeg")


@router.get("/analytics/overview")
def overview():
    live = [w.summary() for w in monitor.workers.values()]
    return {**analytics.overview(live), "seeding": seed_status}


@router.get("/analytics/trends")
def trends(days: int = Query(21, ge=1, le=120), trailer_id: Optional[str] = None):
    return analytics.trends(days, trailer_id)


@router.get("/analytics/shifts")
def shifts(days: int = Query(7, ge=1, le=60)):
    return analytics.shifts(days)


@router.get("/analytics/trailers")
def trailers(days: int = Query(14, ge=1, le=120)):
    return analytics.trailer_metrics(days)


@router.get("/analytics/handlers")
def handlers():
    return analytics.handler_metrics()


@router.get("/reports/weekly")
def weekly(week_offset: int = Query(0, ge=0, le=52), format: str = "json"):
    if format == "csv":
        return PlainTextResponse(analytics.weekly_report_csv(week_offset), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=loadguard-weekly.csv"})
    return analytics.weekly_report(week_offset)
