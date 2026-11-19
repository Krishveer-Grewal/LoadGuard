"""Historical analytics & reporting (Stage 6). Aggregation is done in Python over completed-wall
records so the same code runs on PostgreSQL and SQLite."""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Optional

from sqlalchemy import select

from ..analysis.explain import RULE_NAMES
from ..db import Alert, Analysis, Handler, SessionLocal, Trailer, iso, utcnow

ISSUE_NAMES = {
    "VERTICAL_SEAM": "Vertical seams", "PROTRUSION": "Protruding packages", "SHELF_SLOPE": "Uneven shelves",
    "VOID_CAVITY": "Voids", "VOID_GAP": "Chimney gaps", "HEAVY_HIGH": "Heavy freight high",
    "FLOATING": "Unsupported packages", "OVERHANG": "Overhangs", "LEANING": "Leaning packages",
}


def _local_date(dt: datetime) -> str:
    return dt.replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d")


def _walls(db, since: datetime, trailer_id: Optional[str] = None, until: Optional[datetime] = None):
    q = select(Analysis.id, Analysis.trailer_id, Analysis.handler_id, Analysis.ts, Analysis.shift,
               Analysis.wall_score, Analysis.collapse_risk, Analysis.grade, Analysis.rule_scores,
               Analysis.issue_counts, Analysis.high_count, Analysis.latency_ms).where(
        Analysis.wall_complete.is_(True), Analysis.ts >= since)
    if until is not None:
        q = q.where(Analysis.ts < until)
    if trailer_id:
        q = q.where(Analysis.trailer_id == trailer_id)
    return db.execute(q.order_by(Analysis.ts)).all()


def _alerts(db, since: datetime, until: Optional[datetime] = None):
    q = select(Alert).where(Alert.ts >= since)
    if until is not None:
        q = q.where(Alert.ts < until)
    return db.execute(q).scalars().all()


def _avg(xs) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return round(mean(xs), 1) if xs else None


def overview(live: list[dict]) -> dict:
    now = utcnow()
    with SessionLocal() as db:
        w7 = _walls(db, now - timedelta(days=7))
        w14 = _walls(db, now - timedelta(days=14), until=now - timedelta(days=7))
        today = _local_date(now)
        walls_today = [w for w in w7 if _local_date(w.ts) == today]
        active_alerts = db.query(Alert).filter(Alert.status == "active").count()
    scores = [t["wallScore"] for t in live if t["wallScore"] is not None]
    return {
        "activeTrailers": sum(1 for t in live if t["online"]),
        "totalTrailers": len(live),
        "fleetScore": _avg(scores),
        "hazardTrailers": sum(1 for t in live if t["status"] == "Hazard"),
        "warningTrailers": sum(1 for t in live if t["status"] == "Warning"),
        "activeAlerts": active_alerts,
        "wallsToday": len(walls_today),
        "avgScore7d": _avg(w.wall_score for w in w7),
        "avgScorePrev7d": _avg(w.wall_score for w in w14),
        "hazardousWalls7d": sum(1 for w in w7 if w.wall_score < 50),
    }


def trends(days: int = 21, trailer_id: Optional[str] = None) -> dict:
    now = utcnow()
    since = now - timedelta(days=days)
    with SessionLocal() as db:
        walls = _walls(db, since, trailer_id)
        alerts = _alerts(db, since)
    by_day: dict[str, list] = defaultdict(list)
    for w in walls:
        by_day[_local_date(w.ts)].append(w)
    alerts_by_day = Counter(_local_date(a.ts) for a in alerts if not trailer_id or a.trailer_id == trailer_id)
    daily = []
    for day in sorted(by_day):
        ws = by_day[day]
        rules = defaultdict(list)
        issues: Counter = Counter()
        for w in ws:
            for k, v in (w.rule_scores or {}).items():
                if v is not None:
                    rules[k].append(v)
            issues.update(w.issue_counts or {})
        daily.append({
            "date": day,
            "walls": len(ws),
            "avgScore": _avg(w.wall_score for w in ws),
            "avgRisk": round(mean(w.collapse_risk for w in ws), 3),
            "hazardousWalls": sum(1 for w in ws if w.wall_score < 50),
            "excellentWalls": sum(1 for w in ws if w.wall_score >= 90),
            "alerts": alerts_by_day.get(day, 0),
            "ruleScores": {k: round(mean(v), 3) for k, v in rules.items()},
            "issues": dict(issues),
        })
    return {"days": days, "trailerId": trailer_id, "daily": daily}


def shifts(days: int = 7) -> dict:
    now = utcnow()
    with SessionLocal() as db:
        walls = _walls(db, now - timedelta(days=days))
        alerts = _alerts(db, now - timedelta(days=days))
        handlers = {h.id: h.name for h in db.query(Handler).all()}
    groups: dict[tuple, list] = defaultdict(list)
    for w in walls:
        groups[(_local_date(w.ts), w.shift)].append(w)
    agroups = Counter((_local_date(a.ts), _shift_of(a.ts)) for a in alerts)
    rows = []
    for (day, sh), ws in sorted(groups.items(), reverse=True):
        issues: Counter = Counter()
        for w in ws:
            issues.update(w.issue_counts or {})
        top = issues.most_common(1)
        rows.append({
            "date": day, "shift": sh, "walls": len(ws),
            "avgScore": _avg(w.wall_score for w in ws),
            "minScore": min(w.wall_score for w in ws),
            "avgRisk": round(mean(w.collapse_risk for w in ws), 3),
            "hazardousWalls": sum(1 for w in ws if w.wall_score < 50),
            "alerts": agroups.get((day, sh), 0),
            "handlers": sorted({handlers.get(w.handler_id, "?") for w in ws}),
            "topIssue": ISSUE_NAMES.get(top[0][0], top[0][0]) if top else None,
        })
    return {"days": days, "rows": rows}


def _shift_of(dt: datetime) -> str:
    from ..db import shift_for
    return shift_for(dt)


def trailer_metrics(days: int = 14) -> dict:
    now = utcnow()
    with SessionLocal() as db:
        walls = _walls(db, now - timedelta(days=days))
        alerts = _alerts(db, now - timedelta(days=days))
        trailers = db.query(Trailer).all()
    out = []
    for t in trailers:
        ws = [w for w in walls if w.trailer_id == t.id]
        al = [a for a in alerts if a.trailer_id == t.id]
        issues: Counter = Counter()
        for w in ws:
            issues.update(w.issue_counts or {})
        out.append({
            "trailerId": t.id, "door": t.door, "walls": len(ws),
            "avgScore": _avg(w.wall_score for w in ws),
            "bestScore": max((w.wall_score for w in ws), default=None),
            "worstScore": min((w.wall_score for w in ws), default=None),
            "avgRisk": round(mean(w.collapse_risk for w in ws), 3) if ws else None,
            "hazardRate": round(sum(1 for w in ws if w.wall_score < 50) / len(ws), 3) if ws else None,
            "alerts": len(al),
            "avgLatencyMs": _avg(w.latency_ms for w in ws),
            "topIssues": [{"code": c, "name": ISSUE_NAMES.get(c, c), "count": n} for c, n in issues.most_common(3)],
        })
    out.sort(key=lambda r: r["avgScore"] or 0)
    return {"days": days, "trailers": out}


def handler_metrics() -> dict:
    now = utcnow()
    with SessionLocal() as db:
        walls = _walls(db, now - timedelta(days=28))
        alerts = _alerts(db, now - timedelta(days=28))
        handlers = db.query(Handler).order_by(Handler.id).all()
    out = []
    for h in handlers:
        ws = [w for w in walls if w.handler_id == h.id]
        cur = [w.wall_score for w in ws if w.ts >= now - timedelta(days=7)]
        prev = [w.wall_score for w in ws if now - timedelta(days=14) <= w.ts < now - timedelta(days=7)]
        weekly = []
        for k in range(3, -1, -1):
            lo, hi = now - timedelta(days=7 * (k + 1)), now - timedelta(days=7 * k)
            s = [w.wall_score for w in ws if lo <= w.ts < hi]
            weekly.append({"week": f"W-{k}" if k else "This week", "avgScore": _avg(s), "walls": len(s)})
        issues: Counter = Counter()
        for w in ws:
            if w.ts >= now - timedelta(days=7):
                issues.update(w.issue_counts or {})
        al = [a for a in alerts if a.handler_id == h.id and a.acknowledged_at]
        ack = [(a.acknowledged_at - a.ts).total_seconds() for a in al]
        a_cur, a_prev = _avg(cur), _avg(prev)
        out.append({
            "handlerId": h.id, "name": h.name, "badge": h.badge,
            "walls7d": len(cur), "avgScore7d": a_cur, "avgScorePrev7d": a_prev,
            "improvement": round(a_cur - a_prev, 1) if a_cur is not None and a_prev is not None else None,
            "weekly": weekly,
            "focusArea": ISSUE_NAMES.get(issues.most_common(1)[0][0]) if issues else None,
            "avgAckSeconds": round(mean(ack)) if ack else None,
        })
    out.sort(key=lambda r: -(r["improvement"] or -999))
    return {"handlers": out}


def weekly_report(week_offset: int = 0) -> dict:
    now = utcnow()
    end = now - timedelta(days=7 * week_offset)
    start = end - timedelta(days=7)
    prev_start = start - timedelta(days=7)
    with SessionLocal() as db:
        ws = _walls(db, start, until=end)
        prev = _walls(db, prev_start, until=start)
        al = _alerts(db, start, until=end)
    issues: Counter = Counter()
    rules = defaultdict(list)
    for w in ws:
        issues.update(w.issue_counts or {})
        for k, v in (w.rule_scores or {}).items():
            if v is not None:
                rules[k].append(v)
    avg, pavg = _avg(w.wall_score for w in ws), _avg(w.wall_score for w in prev)
    weakest = sorted(((k, mean(v)) for k, v in rules.items()), key=lambda kv: kv[1])
    tm = trailer_metrics(7)["trailers"]
    hm = handler_metrics()["handlers"]
    highlights = []
    if avg is not None and pavg is not None:
        highlights.append(f"Average wall score {avg} ({'+' if avg >= pavg else ''}{round(avg - pavg, 1)} vs prior week).")
    if weakest:
        highlights.append(f"Weakest practice: {RULE_NAMES.get(weakest[0][0], weakest[0][0])} "
                          f"(avg rule score {weakest[0][1]:.2f}).")
    if issues:
        c, n = issues.most_common(1)[0]
        highlights.append(f"Most frequent defect: {ISSUE_NAMES.get(c, c)} ({n} occurrences).")
    improvers = [h for h in hm if (h["improvement"] or 0) > 3]
    if improvers:
        highlights.append("Most improved: " + ", ".join(f"{h['name']} (+{h['improvement']})" for h in improvers[:3]) + ".")
    coach = [h for h in hm if h["avgScore7d"] is not None and h["avgScore7d"] < 50]
    if coach:
        highlights.append("Coaching recommended: " + ", ".join(
            f"{h['name']} — focus on {h['focusArea'] or 'fundamentals'}" for h in coach) + ".")
    acked = [a for a in al if a.acknowledged_at]
    return {
        "weekStart": iso(start), "weekEnd": iso(end),
        "walls": len(ws), "avgScore": avg, "avgScorePrevWeek": pavg,
        "hazardousWalls": sum(1 for w in ws if w.wall_score < 50),
        "excellentWalls": sum(1 for w in ws if w.wall_score >= 90),
        "alerts": len(al),
        "alertAckRate": round(len(acked) / len(al), 3) if al else None,
        "avgAckSeconds": round(mean((a.acknowledged_at - a.ts).total_seconds() for a in acked)) if acked else None,
        "ruleAverages": {k: round(mean(v), 3) for k, v in rules.items()},
        "topIssues": [{"code": c, "name": ISSUE_NAMES.get(c, c), "count": n} for c, n in issues.most_common(6)],
        "trailers": tm,
        "handlers": hm,
        "highlights": highlights,
    }


def weekly_report_csv(week_offset: int = 0) -> str:
    r = weekly_report(week_offset)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["LoadGuard AI weekly report", r["weekStart"], r["weekEnd"]])
    w.writerow([])
    w.writerow(["Walls", "Avg score", "Prev week", "Hazardous", "Excellent", "Alerts", "Ack rate"])
    w.writerow([r["walls"], r["avgScore"], r["avgScorePrevWeek"], r["hazardousWalls"], r["excellentWalls"],
                r["alerts"], r["alertAckRate"]])
    w.writerow([])
    w.writerow(["Trailer", "Door", "Walls", "Avg score", "Worst", "Hazard rate", "Alerts"])
    for t in r["trailers"]:
        w.writerow([t["trailerId"], t["door"], t["walls"], t["avgScore"], t["worstScore"], t["hazardRate"], t["alerts"]])
    w.writerow([])
    w.writerow(["Handler", "Badge", "Walls 7d", "Avg 7d", "Prev 7d", "Change", "Focus area"])
    for h in r["handlers"]:
        w.writerow([h["name"], h["badge"], h["walls7d"], h["avgScore7d"], h["avgScorePrev7d"], h["improvement"],
                    h["focusArea"]])
    w.writerow([])
    w.writerow(["Highlights"])
    for hl in r["highlights"]:
        w.writerow([hl])
    return buf.getvalue()
