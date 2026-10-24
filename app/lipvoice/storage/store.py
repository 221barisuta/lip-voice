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
from datetime import datetime, timedelta, timezone
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
        """撮影日。試験用に date_override が設定されていれば、それを使う（実際の収集では空）。"""
        s = self._settings()
        if s.date_override:
            return s.date_override
        now = datetime.now(ZoneInfo(s.timezone))
        return (now - timedelta(hours=s.day_start_hour)).strftime("%Y-%m-%d")     # 夜更かしの収集は、前日にまとめる

    # ---- フレーズ ----
    def phrases(self) -> list[dict]:
        with self._lock:
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
        if not _initial:
            # 録画のあるフレーズは消せない（clips.phrase_id に外部キーがなく、黙って孤児になるため）。この関数を通るすべての経路で守る
            in_use = {r[0] for r in self.db.execute("SELECT DISTINCT phrase_id FROM clips WHERE phrase_id IS NOT NULL")}
            lost = in_use - set(ids)
            if lost:
                names = [r["text"] for r in self.db.execute(
                    f"SELECT text FROM phrases WHERE id IN ({','.join('?' * len(lost))})", list(lost))]
                raise ValueError(f"録画のあるフレーズは削除できません: {'、'.join(names) or ', '.join(sorted(lost))}")
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

    def add_phrase(self, text: str) -> dict:
        """フレーズを 1 件、末尾に追加する。id は p + 連番で自動採番し、削除しても番号を戻さない（古いモデル・評価と食い違わないように）。"""
        s: Settings = self._settings()
        text = (text or "").strip()
        if not text:
            raise ValueError("フレーズが空です")
        if s.max_phrase_chars and len(text) > s.max_phrase_chars:
            raise ValueError(f"フレーズは {s.max_phrase_chars} 文字までです")
        with self._lock:
            cur = self.phrases()
            if s.max_phrases and len(cur) >= s.max_phrases:
                raise ValueError(f"フレーズは {s.max_phrases} 件までです")
            if any(p["text"] == text for p in cur):
                raise ValueError("同じフレーズがすでにあります")
            self.db.execute("BEGIN IMMEDIATE")
            try:
                used = [int(m.group(1)) for (v,) in self.db.execute(
                    "SELECT id FROM phrases UNION SELECT phrase_id FROM clips WHERE phrase_id IS NOT NULL "
                    "UNION SELECT chosen FROM predictions WHERE chosen IS NOT NULL") if v and (m := re.fullmatch(r"p(\d+)", v))]
                row = self.db.execute("SELECT value FROM meta WHERE key='next_phrase_seq'").fetchone()
                n = max(int(row[0]) if row else 0, max(used, default=0) + 1)
                pid = f"p{n:02d}"
                self.db.execute("INSERT INTO phrases(id, text, position) VALUES (?,?,?)", (pid, text, len(cur)))
                self.db.execute("INSERT INTO meta(key, value) VALUES ('next_phrase_seq', ?) "
                                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(n + 1),))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        return {"id": pid, "text": text}

    def phrase_stats(self) -> dict[str, dict]:
        """フレーズごとの録画の本数と、撮影日の数（評価には別の日が 2 日以上要る）。"""
        return {r["phrase_id"]: {"clips": r["n"], "days": r["d"]} for r in self.db.execute(
            "SELECT phrase_id, COUNT(*) n, COUNT(DISTINCT date) d FROM clips WHERE kind='phrase' GROUP BY phrase_id")}

    def phrase_exists(self, phrase_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM phrases WHERE id=?", (phrase_id,)).fetchone() is not None

    # ---- クリップ ----
    def save_clip(self, rec: ClipRecord, npz: bytes, webm: bytes, day: str | None = None) -> str:
        s = self._settings()
        if rec.kind == "phrase" and not (rec.phrase_id and self.phrase_exists(rec.phrase_id)):
            raise ValueError("phrase_id が存在しません")
        if rec.kind == "negative" and not rec.negative_label:
            raise ValueError("負例の種類がありません")
        day = day or self.today()
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

    def delete_clip(self, clip_id: str) -> None:
        """クリップを消す（ファイルと記録）。ID は 32 桁の 16 進数だけを受け付ける。"""
        if not re.fullmatch(r"[0-9a-f]{32}", clip_id):
            raise ValueError("クリップ ID が正しくありません")
        with self._lock:
            row = self.db.execute("SELECT landmarks_path, video_path FROM clips WHERE id=?", (clip_id,)).fetchone()
            if row is None:
                raise ValueError("クリップが見つかりません")
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute("DELETE FROM clips WHERE id=?", (clip_id,))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            for rel in (row["landmarks_path"], row["video_path"]):
                if rel:
                    self.clip_path(rel).unlink(missing_ok=True)

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

    def add_prediction(self, **v) -> str:
        pid = uuid.uuid4().hex
        with self._lock:
            self.db.execute(
                "INSERT INTO predictions(id,created_at,date,clip_id,model_version,model_kind,top3_json,distance,rejected,agree,"
                "chosen,outcome,correct_top1,correct_top3,latency_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid, datetime.now(timezone.utc).isoformat(timespec="seconds"), self.today(), v.get("clip_id"),
                 v.get("model_version"), v.get("model_kind"), v.get("top3_json"), v.get("distance"), v.get("rejected"),
                 v.get("agree"), v.get("chosen"), v["outcome"], v.get("correct_top1"), v.get("correct_top3"), v.get("latency_ms")))
        return pid

    def real_use_by_day(self) -> list[dict]:
        """実使用（認識画面で選ばれた結果）の、日ごとの正解率。"""
        rows = self.db.execute(
            "SELECT date, COUNT(*) n, SUM(correct_top1) top1, SUM(correct_top3) top3, SUM(rejected) rejected "
            "FROM predictions WHERE outcome='phrase' GROUP BY date ORDER BY date").fetchall()
        return [{"date": r["date"], "n": r["n"], "top1": r["top1"] or 0, "top3": r["top3"] or 0, "rejected": r["rejected"] or 0}
                for r in rows]

    def list_clips(self, *, date: str | None = None, kind: str | None = None, limit: int = 100, offset: int = 0) -> dict:
        """クリップの一覧（新しい順）。ファイルの場所は返さない。"""
        where, args = [], []
        if date:
            where.append("c.date=?"); args.append(date)
        if kind in ("phrase", "negative"):
            where.append("c.kind=?"); args.append(kind)
        cond = (" WHERE " + " AND ".join(where)) if where else ""
        total = self.db.execute(f"SELECT COUNT(*) FROM clips c{cond}", args).fetchone()[0]
        rows = self.db.execute(
            "SELECT c.id, c.kind, c.source, c.date, c.created_at, c.duration_ms, c.detected_ratio, c.stop_reason, "
            "COALESCE(p.text, c.negative_label, '') AS label FROM clips c LEFT JOIN phrases p ON p.id=c.phrase_id"
            f"{cond} ORDER BY c.created_at DESC LIMIT ? OFFSET ?", [*args, max(1, min(limit, 500)), max(0, offset)]).fetchall()
        dates = [r[0] for r in self.db.execute("SELECT DISTINCT date FROM clips ORDER BY date DESC")]
        return {"clips": [dict(r) for r in rows], "total": total, "dates": dates}

    def clip_video_path(self, clip_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", clip_id):
            raise ValueError("クリップ ID が正しくありません")
        row = self.db.execute("SELECT video_path FROM clips WHERE id=?", (clip_id,)).fetchone()
        if row is None:
            raise ValueError("クリップが見つかりません")
        if not row["video_path"]:
            raise ValueError("動画は含まれていません")
        return self.clip_path(row["video_path"])

    def clip_rows(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM clips ORDER BY created_at").fetchall()

    def clip_path(self, rel: str) -> Path:
        p = (self.paths.clips / rel).resolve()
        if not p.is_relative_to(self.paths.clips.resolve()):
            raise ValueError("不正なパスです")
        return p

    def close(self) -> None:
        self.db.close()
