"""Database models (PostgreSQL in Docker, SQLite fallback for local dev)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings

is_sqlite = settings.database_url.startswith("sqlite")
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False, "timeout": 30} if is_sqlite else {},
)
if is_sqlite:
    @event.listens_for(engine, "connect")
    def _wal(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA synchronous=NORMAL")

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Handler(Base):
    __tablename__ = "handlers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    badge: Mapped[str] = mapped_column(String(20))
    skill: Mapped[float] = mapped_column(Float, default=0.6)  # simulator only
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Trailer(Base):
    __tablename__ = "trailers"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    door: Mapped[int] = mapped_column(Integer, default=0)
    source_type: Mapped[str] = mapped_column(String(20), default="simulator")  # simulator|rtsp|webcam|video|push
    source_uri: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sim_skill: Mapped[float] = mapped_column(Float, default=0.6)
    handler_id: Mapped[Optional[int]] = mapped_column(ForeignKey("handlers.id"), nullable=True)
    calibration: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trailer_id: Mapped[str] = mapped_column(ForeignKey("trailers.id", ondelete="CASCADE"), index=True)
    handler_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    shift: Mapped[str] = mapped_column(String(2))
    wall_seq: Mapped[int] = mapped_column(Integer, default=0)
    wall_complete: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    wall_score: Mapped[int] = mapped_column(Integer)
    collapse_risk: Mapped[float] = mapped_column(Float)
    grade: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    rule_scores: Mapped[dict] = mapped_column(JSON)
    issue_counts: Mapped[dict] = mapped_column(JSON)
    high_count: Mapped[int] = mapped_column(Integer, default=0)
    issue_total: Mapped[int] = mapped_column(Integer, default=0)
    package_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # full payload for completed walls


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trailer_id: Mapped[str] = mapped_column(ForeignKey("trailers.id", ondelete="CASCADE"), index=True)
    handler_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    severity: Mapped[str] = mapped_column(String(10))
    rule: Mapped[str] = mapped_column(String(30))
    code: Mapped[str] = mapped_column(String(30))
    issue_key: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(String(300))
    detail: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(15), default="active", index=True)  # active|acknowledged|resolved
    wall_score: Mapped[int] = mapped_column(Integer, default=0)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    snapshot: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)


def init_db() -> None:
    Base.metadata.create_all(engine)


def shift_for(dt: datetime) -> str:
    """Shift letter in the site's local time. Naive datetimes are treated as UTC."""
    local = (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt).astimezone()
    h = local.hour
    return "A" if 6 <= h < 14 else "B" if 14 <= h < 22 else "C"


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None
