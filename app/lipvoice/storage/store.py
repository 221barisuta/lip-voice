"""クリップ・フレーズの保存。ファイルと SQLite を、壊れにくい順序で書く。

書き込み順: 一時ファイルに書く → fsync → 名前変更（置き換え）→ SQLite に 1 トランザクションで記録。
途中で電源が落ちても、孤児ファイルが残るだけで DB は壊れない（起動時の検査で orphans/ へ移す）。
"""
import os
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ..initial_phrases import INITIAL_PHRASES
from ..paths import Paths
from ..settings import Settings
from .db import connect

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class LimitExceeded(Exception):
    pass


@dataclass
class ClipRecord:
    kind: str                       # phrase | negative
    session_id: str
    phrase_id: str | None = None
    negative_label: str | None = None
    source: str = "collect"
    duration_ms: int = 0
    frame_count: int = 0
    fps_measured: float = 0.0
    detected_ratio: float = 0.0
    stop_reason: str = ""
    width: int = 0
    height: int = 0


def _fsync_write(path: Path, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


class Store:
    def __init__(self, paths: Paths, settings_fn):
        self.paths = paths.ensure()
        self._settings = settings_fn          # 呼ぶたびに最新の Settings を返す
        self.db = connect(paths.db)
        self._lock = threading.RLock()
        if not self.db.execute("SELECT 1 FROM phrases LIMIT 1").fetchone():
            self.replace_phrases(INITIAL_PHRASES, _initial=True)

    # ---- 日付 ----
    def today(self) -> str:
        return datetime.now(ZoneInfo(self._settings().timezone)).strftime("%Y-%m-%d")

    # ---- フレーズ ----
    def phrases(self) -> list[dict]:
        rows = self.db.execute("SELECT id, text FROM phrases ORDER BY position").fetchall()
        return [{"id": r["id"], "text": r["text"]} for r in rows]

    def replace_phrases(self, phrases: list[dict], _initial: bool = False) -> list[dict]:
        s: Settings = self._settings()
        ids = [p.get("id", "") for p in phrases]
        if not phrases:
            raise ValueError("フレーズが空です")
        if s.max_phrases and len(phrases) > s.max_phrases:
            raise ValueError(f"フレーズは {s.max_phrases} 件までです")
        if len(set(ids)) != len(ids):
            raise ValueError("id が重複しています")
        for p in phrases:
            text = str(p.get("text", "")).strip()
            if not ID_RE.match(str(p.get("id", ""))) or not text:
                raise ValueError("id またはテキストが不正です")
            if s.max_phrase_chars and len(text) > s.max_phrase_chars:
                raise ValueError(f"フレーズは {s.max_phrase_chars} 文字までです")
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("DELETE FROM phrases")
                self.db.executemany("INSERT INTO phrases(id, text, position) VALUES (?,?,?)",
                                    [(p["id"], str(p["text"]).strip(), i) for i, p in enumerate(phrases)])
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        return self.phrases()

    def phrase_exists(self, phrase_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM phrases WHERE id=?", (phrase_id,)).fetchone() is not None

    # ---- クリップ ----
    def save_clip(self, rec: ClipRecord, npz: bytes, webm: bytes) -> str:
        s = self._settings()
        if rec.kind == "phrase" and not (rec.phrase_id and self.phrase_exists(rec.phrase_id)):
            raise ValueError("phrase_id が存在しません")
        if rec.kind == "negative" and not rec.negative_label:
            raise ValueError("負例の種類がありません")
        day = self.today()
        with self._lock:
            if s.max_clips_per_day and self.count_on(day) >= s.max_clips_per_day:
                raise LimitExceeded("本日の保存上限に達しました")
            clip_id = uuid.uuid4().hex       # 保存先は常にこの ID から決める（外部の値は使わない）
            rel_dir = Path(day)
            dest = self.paths.clips / rel_dir
            dest.mkdir(parents=True, exist_ok=True)
            tmp_n, tmp_v = self.paths.tmp / f"{clip_id}.npz.part", self.paths.tmp / f"{clip_id}.webm.part"
            f_n, f_v = dest / f"{clip_id}.npz", dest / f"{clip_id}.webm"
            try:
                _fsync_write(tmp_n, npz)
                _fsync_write(tmp_v, webm)
                os.replace(tmp_n, f_n)
                os.replace(tmp_v, f_v)
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    self.db.execute(
                        "INSERT INTO clips(id,kind,phrase_id,negative_label,source,session_id,date,created_at,"
                        "duration_ms,frame_count,fps_measured,detected_ratio,stop_reason,width,height,landmarks_path,video_path)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (clip_id, rec.kind, rec.phrase_id, rec.negative_label, rec.source, rec.session_id, day,
                         datetime.now(timezone.utc).isoformat(timespec="seconds"), rec.duration_ms, rec.frame_count,
                         rec.fps_measured, rec.detected_ratio, rec.stop_reason, rec.width, rec.height,
                         (rel_dir / f_n.name).as_posix(), (rel_dir / f_v.name).as_posix()))
                    self.db.execute("COMMIT")
                except BaseException:
                    self.db.execute("ROLLBACK")
                    raise
            except BaseException:
                for p in (tmp_n, tmp_v, f_n, f_v):
                    p.unlink(missing_ok=True)
                raise
        return clip_id

    def count_on(self, day: str) -> int:
        return self.db.execute("SELECT COUNT(*) FROM clips WHERE date=?", (day,)).fetchone()[0]

    def stats(self) -> dict:
        today = self.today()
        per = {r["phrase_id"]: r["n"] for r in self.db.execute(
            "SELECT phrase_id, COUNT(*) n FROM clips WHERE kind='phrase' GROUP BY phrase_id")}
        neg = {r["negative_label"]: r["n"] for r in self.db.execute(
            "SELECT negative_label, COUNT(*) n FROM clips WHERE kind='negative' GROUP BY negative_label")}
        total = self.db.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        return {"today": self.count_on(today), "total": total, "per_phrase": per, "negatives": neg}

    def clip_rows(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM clips ORDER BY created_at").fetchall()

    def clip_path(self, rel: str) -> Path:
        p = (self.paths.clips / rel).resolve()
        if not p.is_relative_to(self.paths.clips.resolve()):
            raise ValueError("不正なパスです")
        return p

    def close(self) -> None:
        self.db.close()
