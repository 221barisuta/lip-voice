"""自動学習（DTW のみ。別プロセス・低い優先度）。仕様 8.5。

- 新しいデータがあるときだけ、決まった時機（毎晩 / セッション終了後 / 起動時）に、`lipvoice train --no-cnn --no-activate` を別プロセスで走らせる
  （学習が録画・視線入力ソフトの邪魔をしない。クラッシュやメモリがアプリに及ばない）
- できた新しい版は、評価が基準を満たす時だけ自動で使い始める（should_activate）。満たさない時は、版を保存して、画面で案内する
- 評価できない（別の日のデータがない）新しい版は、自動では切り替えない（棄却の基準が暫定で、誤った発話が増えるため）。使うモデルが 1 つもない時だけ例外
"""
import json
import math
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..paths import Paths
from ..settings import TRAIN_SOURCES
from .data import select_rows
from .model_store import _atomic_json, active_version, set_active, versions

LOCK_STALE_SEC = 30 * 60
MIN_NEWEST_DAY_TOP3 = 0.5          # 新しい日を評価に回した時の成績がこれ未満なら、ラベル・撮影条件の疑い
MIN_RUN_INTERVAL_SEC = 10 * 60
STARTUP_DELAY_SEC = 5 * 60         # 起動直後（カメラの初期化・視線入力ソフトの起動）は避ける
RUN_TIMEOUT_SEC = 30 * 60


# ---- 排他（手動の train.cmd と自動学習が、同時に走らない）----
def _lock_path(models: Path) -> Path:
    return models / "train.lock"


def lock_active(models: Path) -> bool:
    try:
        return time.time() - _lock_path(models).stat().st_mtime < LOCK_STALE_SEC
    except OSError:
        return False


@contextmanager
def train_lock(models: Path):
    """学習中のロック。古い（30 分以上）ロックは、落ちた学習の残りとみなして破棄する。ロック中なら RuntimeError。"""
    models.mkdir(parents=True, exist_ok=True)
    path = _lock_path(models)
    if path.exists() and not lock_active(models):
        path.unlink(missing_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError("別の学習が実行中です。終わってからやり直してください")
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


# ---- 切り替えの判定（純粋な関数）----
def _top3(m: dict | None) -> tuple[int, int, float]:
    t = (m or {}).get("top3") or {}
    return int(t.get("k") or 0), int(t.get("n") or 0), float(t.get("rate") or 0.0)


def should_activate(old: dict | None, new: dict, min_top3: float = 0.7) -> tuple[bool, str]:
    kind = new.get("active")
    res = (new.get("results") or {}).get(kind)
    if not new.get("evaluated") or not res:
        return False, "別の日のデータがなく、新しいモデルを評価できないため、自動では切り替えていません"
    rate = _top3(res["lodo"])[2]
    if rate < min_top3:
        return False, f"新しいモデルの上位3の正解率が {rate:.0%} で、基準（{min_top3:.0%}）に届かないため、切り替えていません"
    by_day = res.get("by_day") or {}
    newest = sorted(by_day)[-1] if by_day else None
    if newest and by_day[newest]:
        k, n, r = _top3(by_day[newest])
        if n >= 3 and r < MIN_NEWEST_DAY_TOP3:
            return False, f"最新の日（{newest}）の成績が極端に低い（{r:.0%}）ため、切り替えていません。ラベルや撮影条件を確認してください"
    old_res = (old or {}).get("results", {}).get((old or {}).get("active")) if (old or {}).get("evaluated") else None
    if old_res:
        old_days = old_res.get("by_day") or {}
        common = [d for d in by_day if by_day[d] and old_days.get(d)]       # 同じ評価の日だけを比べる
        if common:
            k_new = sum(_top3(by_day[d])[0] for d in common)
            k_old = sum(_top3(old_days[d])[0] for d in common)
            n = sum(_top3(by_day[d])[1] for d in common)
            if k_old - k_new >= max(2, math.ceil(0.05 * n)):
                return False, f"以前のモデルより、共通の日の正解が {k_old - k_new} 本減っているため、切り替えていません"
        tn, to = (new.get("taus") or {}).get(kind), (old.get("taus") or {}).get(old.get("active"))
        if tn and to and tn > to * 1.5:
            return False, "棄却の基準が以前より大きく緩くなったため、切り替えていません"
    return True, f"新しいモデルの評価（上位3 {rate:.0%}）が基準を満たしたため、自動で切り替えました"


# ---- 実行 ----
def _read_report(models: Path, version: str | None) -> dict | None:
    if not version:
        return None
    try:
        return json.loads((models / "reports" / f"{version}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _spawn(cmd: list[str], log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "ab")
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": log}
    if sys.platform == "win32":
        kw["creationflags"] = 0x00004000 | 0x08000000          # BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW
    proc = subprocess.Popen(cmd, **kw)                          # preexec_fn は、スレッドのあるプロセスで固まることがあるので使わない
    if sys.platform != "win32":
        try:
            os.setpriority(os.PRIO_PROCESS, proc.pid, 10)
        except OSError:
            pass
    return proc


class AutoTrainer:
    def __init__(self, paths: Paths, store, settings_fn, speak, collect, spawn=_spawn, clock=time.time):
        self._p, self._store, self._settings, self._speak, self._collect = paths, store, settings_fn, speak, collect
        self._spawn, self._clock = spawn, clock
        self._started_at = clock()
        self._lock = threading.Lock()
        self._running = False
        self._ran_on_start = False
        self._ended_seen: str | None = None
        self._last_run = 0.0
        self._stop = threading.Event()

    # ---- 状態 ----
    @property
    def state_path(self) -> Path:
        return self._p.models / "auto_train.json"

    def state(self) -> dict:
        try:
            st = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            st = {}
        st["running"] = self._running or lock_active(self._p.models)
        return st

    def _save_state(self, **kw) -> None:
        st = self.state()
        st.pop("running", None)
        st.update(kw)
        self._p.models.mkdir(parents=True, exist_ok=True)
        _atomic_json(self.state_path, st)

    # ---- 判断 ----
    def has_new_data(self) -> bool:
        s = self._settings()
        rows = [r for r in select_rows(self._store, TRAIN_SOURCES[s.train_sources]) if r["kind"] == "phrase"]
        if len(rows) < 4:
            return False
        v = active_version(self._p.models)
        if v is None:
            return True
        try:
            used = set(json.loads((self._p.models / v / "meta.json").read_text(encoding="utf-8"))["extra"]["clip_ids"])
        except (OSError, ValueError, KeyError):
            return True
        return {r["id"] for r in rows} != used

    def due(self, now: datetime | None = None) -> str | None:
        """いま学習を始めるべきなら、その理由。認識・録画中は待つ（入れ替え自体はいつでもよい）。"""
        s = self._settings()
        if s.auto_train == "off" or s.date_override or self._running or lock_active(self._p.models):
            return None
        if self._collect.phase in ("recording", "review") or self._speak.phase == "recording":
            return None
        t = self._clock()
        if t - self._last_run < MIN_RUN_INTERVAL_SEC:
            return None
        reason = None
        if s.auto_train == "on_start":
            if not self._ran_on_start and t - self._started_at >= STARTUP_DELAY_SEC:
                reason = "on_start"
        elif s.auto_train == "after_session":
            if self._collect.phase == "ended" and self._ended_seen != self._collect.session_id:
                reason = "after_session"
        elif s.auto_train == "nightly":
            now = now or datetime.now(ZoneInfo(s.timezone))
            if (t - self._started_at >= STARTUP_DELAY_SEC and now.hour >= int(s.day_start_hour) + 1
                    and self.state().get("last_attempt_day") != self._store.today()):
                reason = "nightly"
        return reason if reason and self.has_new_data() else None

    # ---- 実行 ----
    def run_now(self, reason: str = "manual", wait: bool = False) -> bool:
        with self._lock:
            if self._running or lock_active(self._p.models):
                return False
            self._running = True
        self._last_run = self._clock()
        if reason == "on_start":
            self._ran_on_start = True
        if reason == "after_session":
            self._ended_seen = self._collect.session_id
        t = threading.Thread(target=self._run, args=(reason,), name="auto-train", daemon=True)
        t.start()
        if wait:
            t.join()
        return True

    def _run(self, reason: str) -> None:
        s = self._settings()
        before = set(versions(self._p.models))
        old_v = active_version(self._p.models)
        started = datetime.now().astimezone().isoformat(timespec="seconds")
        self._save_state(last_attempt_day=self._store.today(), last_run_at=started, last_reason=reason, error=None)
        cmd = [sys.executable, "-m", "lipvoice", "--home", str(self._p.home), "--profile", self._p.profile,
               "train", "--no-cnn", "--no-activate", "--sources", ",".join(TRAIN_SOURCES[s.train_sources])]
        try:
            proc = self._spawn(cmd, self._p.logs / "auto-train.log")
            try:
                rc = proc.wait(timeout=RUN_TIMEOUT_SEC)
            except subprocess.TimeoutExpired:
                proc.kill()
                rc = -9
            new = sorted(set(versions(self._p.models)) - before)
            if rc != 0 or not new:
                self._save_state(error="学習に失敗しました（前のモデルのまま使います）。logs/auto-train.log を確認してください",
                                 version=None, activated=False, reason=None)
                return
            version = new[-1]
            report = _read_report(self._p.models, version) or {}
            if old_v is None:
                ok, why = True, "使うモデルがなかったので、新しいモデルを使い始めました"
            else:
                ok, why = should_activate(_read_report(self._p.models, old_v), report, s.auto_activate_min_top3)
            if ok:
                set_active(self._p.models, version)
                _atomic_json(self._p.models / "reports" / "latest.json", report)
                self._speak.reload_model()                    # 入れ替えは、認識中でも安全（認識側が、使うモデルを取り出して推論する）
            self._save_state(version=version, activated=ok, reason=why, error=None, finished_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        except Exception as e:
            self._save_state(error=f"自動学習でエラー: {type(e).__name__}", activated=False)
        finally:
            self._running = False

    # ---- 定期チェック ----
    def start(self) -> None:
        threading.Thread(target=self._loop, name="auto-train-scheduler", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(30):
            try:
                reason = self.due()
                if reason:
                    self.run_now(reason)
            except Exception:
                pass                                             # 自動学習の不具合でアプリを止めない
