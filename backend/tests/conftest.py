import os
import sys
import tempfile
from pathlib import Path

# Isolated DB + no history seeding + fast offline detector for tests. Must run before app import.
_tmp = tempfile.mkdtemp(prefix="loadguard-test-")
os.environ.setdefault("LG_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ.setdefault("LG_DATA_DIR", _tmp)
os.environ.setdefault("LG_SEED_HISTORY_DAYS", "0")
os.environ.setdefault("LG_DETECTOR", "classical")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
