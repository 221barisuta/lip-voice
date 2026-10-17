import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS phrases(
  id TEXT PRIMARY KEY, text TEXT NOT NULL, position INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS clips(
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('phrase','negative')),
  phrase_id TEXT,
  negative_label TEXT,
  source TEXT NOT NULL DEFAULT 'collect',
  session_id TEXT NOT NULL,
  date TEXT NOT NULL,
  created_at TEXT NOT NULL,
  duration_ms INTEGER, frame_count INTEGER, fps_measured REAL, detected_ratio REAL,
  stop_reason TEXT, width INTEGER, height INTEGER,
  landmarks_path TEXT NOT NULL, video_path TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_clips_date ON clips(date);
CREATE INDEX IF NOT EXISTS idx_clips_phrase ON clips(phrase_id);
CREATE TABLE IF NOT EXISTS predictions(
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, date TEXT NOT NULL, clip_id TEXT,
  model_version TEXT, model_kind TEXT, top3_json TEXT, distance REAL, rejected INTEGER, agree INTEGER,
  chosen TEXT, outcome TEXT NOT NULL,   -- outcome: phrase（選ばれた）| negative（フレーズではない動き）| skipped
  correct_top1 INTEGER, correct_top3 INTEGER, latency_ms REAL);
CREATE INDEX IF NOT EXISTS idx_pred_date ON predictions(date);
"""


def connect(path: Path) -> sqlite3.Connection:
    """WAL モード。電源断でもコミット済みの内容は失われない（synchronous=FULL）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False, isolation_level=None)   # 明示的に BEGIN する
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(_SCHEMA)
    ver = con.execute("PRAGMA user_version").fetchone()[0]
    if ver > SCHEMA_VERSION:
        raise RuntimeError(f"データベースが新しい版です（{ver}）。アプリを更新してください")
    con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    return con
