"""Runtime configuration (environment variables, `.env` supported)."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LG_", extra="ignore")

    # Postgres in Docker (postgresql+psycopg://...). Falls back to a local SQLite file for dev.
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'loadguard.db'}"
    data_dir: Path = BASE_DIR / "data"

    # Detection backend: auto | classical | yolo | yoloworld | hybrid | groundtruth
    #   auto       -> hybrid if ultralytics is installed, otherwise classical
    #   classical  -> OpenCV contour segmentation (no downloads, works offline)
    #   yolo       -> pre-trained YOLO11 (COCO) with class mapping
    #   yoloworld  -> pre-trained open-vocabulary YOLO-World ("cardboard box", "tire", ...)
    #   hybrid     -> YOLO for non-box classes fused with classical box segmentation
    #   groundtruth-> simulator ground truth (isolates the structural engine from detector noise)
    detector: str = "auto"
    yolo_model: str = "yolo11n.pt"
    yoloworld_model: str = "yolov8s-worldv2.pt"
    yolo_conf: float = 0.25

    # Worker loop rates
    capture_fps: float = 6.0
    analysis_fps: float = 2.0
    persist_interval_s: float = 5.0

    # Alerting: an issue must persist this many consecutive analyses before alerting
    alert_debounce: int = 3
    alert_resolve_after: int = 4

    # Demo seeding
    seed_demo: bool = True
    seed_history_days: int = 21
    sim_place_interval_s: float = 2.2
    # A simulated wall completes every ~90 s (vs ~20+ min for a real one). Record at most one
    # simulated live wall per trailer per interval so live demos don't swamp historical analytics.
    sim_history_min_interval_s: float = 1200

    cors_origins: str = "*"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.data_dir / "snapshots").mkdir(parents=True, exist_ok=True)
(settings.data_dir / "uploads").mkdir(parents=True, exist_ok=True)
