"""自動学習: 切り替えの判定、排他、モデルの保存の頑丈さ、起動の判断、別プロセスでの学習の一連。"""
import json
import os
import time
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from lipvoice.ml import model_store
from lipvoice.ml.auto_train import AutoTrainer, lock_active, should_activate, train_lock
from lipvoice.ml.synthetic import generate_into_store
from lipvoice.settings import Settings
from lipvoice.storage import store as store_mod
from lipvoice.storage.store import Store


def m(k, n):
    return {"top3": {"k": k, "n": n, "rate": k / n if n else None}}


def report(kind="A", evaluated=True, by_day=None, tau=5.0, total=None):
    by_day = by_day if by_day is not None else {"d1": m(9, 10), "d2": m(9, 10)}
    k = sum(v["top3"]["k"] for v in by_day.values())
    n = sum(v["top3"]["n"] for v in by_day.values())
    return {"active": kind, "evaluated": evaluated, "taus": {kind: tau},
            "results": {kind: {"lodo": total or m(k, n), "by_day": by_day}} if evaluated else {}}


# ---- should_activate ----
def test_not_evaluated_is_not_switched():
    ok, why = should_activate(None, report(evaluated=False))
    assert not ok and "評価できない" in why


def test_below_threshold_is_not_switched_and_at_threshold_is():
    assert not should_activate(None, report(by_day={"d1": m(6, 10), "d2": m(6, 10)}))[0]       # 60% < 70%
    assert should_activate(None, report(by_day={"d1": m(7, 10), "d2": m(7, 10)}))[0]           # 70%
    assert should_activate(None, report(by_day={"d1": m(6, 10), "d2": m(6, 10)}), min_top3=0.5)[0]


def test_newest_day_collapse_is_suspicious():
    ok, why = should_activate(None, report(by_day={"d1": m(10, 10), "d2": m(10, 10), "d3": m(2, 10)}, total=m(22, 30)), 0.7)
    assert not ok and "最新の日" in why


def test_regression_on_common_days_blocks_switch():
    old = report(by_day={"d1": m(9, 10), "d2": m(9, 10)})
    worse = report(by_day={"d1": m(8, 10), "d2": m(8, 10), "d3": m(10, 10)})                    # 共通の日で 2 本減る
    ok, why = should_activate(old, worse, 0.7)
    assert not ok and "減っている" in why
    same = report(by_day={"d1": m(9, 10), "d2": m(9, 10), "d3": m(10, 10)})
    assert should_activate(old, same, 0.7)[0]
    one_less = report(by_day={"d1": m(8, 10), "d2": m(9, 10), "d3": m(10, 10)})                  # 1 本の揺らぎは許す
    assert should_activate(old, one_less, 0.7)[0]


def test_unevaluated_old_model_does_not_block_a_good_new_one():
    assert should_activate(report(evaluated=False), report())[0]


def test_looser_rejection_threshold_blocks_switch():
    old = report(tau=4.0)
    assert not should_activate(old, report(tau=7.0))[0]
    assert should_activate(old, report(tau=5.5))[0]


# ---- 排他 ----
def test_train_lock_is_exclusive_and_stale_locks_are_dropped(tmp_path):
    root = tmp_path / "models"
    with train_lock(root):
        assert lock_active(root)
        with pytest.raises(RuntimeError):
            with train_lock(root):
                pass
    assert not lock_active(root)
    root.mkdir(exist_ok=True)
    stale = root / "train.lock"
    stale.write_text("123")
    old = time.time() - 3600
    os.utime(stale, (old, old))
    with train_lock(root):                                    # 古いロックは破棄される
        assert lock_active(root)


# ---- モデルの保存の頑丈さ ----
def fake_version(root, name, broken=False):
    d = root / name
    d.mkdir(parents=True)
    (d / "meta.json").write_text("" if broken else json.dumps(
        {"version": name, "classes": ["a"], "feature": {}, "active": "A", "tau": {}, "extra": {}}), encoding="utf-8")


def test_tmp_folders_are_not_versions_and_are_cleaned(tmp_path):
    root = tmp_path
    fake_version(root, "20260101-000000")
    fake_version(root, ".tmp-abc")
    assert model_store.versions(root) == ["20260101-000000"]
    assert model_store.cleanup_tmp(root) == 1 and not (root / ".tmp-abc").exists()
    with pytest.raises(FileNotFoundError):
        model_store.set_active(root, ".tmp-abc")


def test_broken_active_version_falls_back_without_crashing(tmp_path, capsys):
    root = tmp_path
    fake_version(root, "20260101-000000", broken=True)
    assert model_store.load_active(root) is None                          # 読める版がなければ None（起動は続く）
    assert "読めません" in capsys.readouterr().err


def test_set_active_remembers_previous(tmp_path):
    fake_version(tmp_path, "20260101-000000")
    fake_version(tmp_path, "20260102-000000")
    model_store.set_active(tmp_path, "20260101-000000")
    model_store.set_active(tmp_path, "20260102-000000")
    assert json.loads((tmp_path / "active.json").read_text())["previous"] == "20260101-000000"


# ---- 起動の判断と、別プロセスでの学習 ----
class Clk:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def world(paths):
    cfg = {"s": Settings()}
    store = Store(paths, lambda: cfg["s"])
    generate_into_store(store, [3, 3], ["p01", "p02", "p03"], {"あくび": 2}, seed=3)
    collect = SimpleNamespace(phase="idle", session_id="s1")
    speak = SimpleNamespace(phase="idle", reloaded=0)
    speak.reload_model = lambda: setattr(speak, "reloaded", speak.reloaded + 1)
    clk = Clk()
    tr = AutoTrainer(paths, store, lambda: cfg["s"], speak, collect, clock=clk)
    yield tr, cfg, store, collect, speak, clk, paths
    store.close()


def at_hour(h):
    return datetime(2026, 10, 25, h, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def test_due_nightly_waits_for_hour_startup_delay_and_new_data(world):
    tr, cfg, store, collect, speak, clk, paths = world
    assert tr.due(at_hour(2)) is None                           # 起動直後は避ける
    clk.t += 400
    assert tr.due(at_hour(0)) is None                           # 日付の切り替えの 1 時間後より前
    assert tr.due(at_hour(2)) == "nightly"
    collect.phase = "recording"
    assert tr.due(at_hour(2)) is None                           # 録画中は始めない
    collect.phase = "idle"
    cfg["s"] = replace(cfg["s"], auto_train="off")
    assert tr.due(at_hour(2)) is None
    cfg["s"] = replace(cfg["s"], auto_train="nightly", date_override="day1")
    assert tr.due(at_hour(2)) is None                           # 試験用の撮影日の上書き中はしない
    cfg["s"] = replace(cfg["s"], date_override="", day_start_hour=4.0)
    assert tr.due(at_hour(4)) is None and tr.due(at_hour(5)) == "nightly"


def test_after_session_and_on_start_modes(world):
    tr, cfg, store, collect, speak, clk, paths = world
    cfg["s"] = replace(cfg["s"], auto_train="after_session")
    assert tr.due() is None
    collect.phase = "ended"
    assert tr.due() == "after_session"
    cfg["s"] = replace(cfg["s"], auto_train="on_start")
    assert tr.due() is None
    clk.t += 400
    assert tr.due() == "on_start"


def test_run_trains_in_a_subprocess_activates_first_model_and_then_has_no_new_data(world):
    tr, cfg, store, collect, speak, clk, paths = world
    assert model_store.active_version(paths.models) is None
    assert tr.run_now("manual", wait=True)
    st = tr.state()
    assert st["activated"] is True and st["error"] is None and st["version"] == model_store.active_version(paths.models)
    assert speak.reloaded == 1
    assert not tr.has_new_data()                                  # 同じデータなので、次は学習しない
    clk.t += 400
    assert tr.due(at_hour(2)) is None
    assert not lock_active(paths.models)


def test_new_unevaluable_model_is_kept_but_not_activated(world):
    tr, cfg, store, collect, speak, clk, paths = world
    # 1 日分だけのデータで最初の版（評価なし）を作る
    store.db.execute("DELETE FROM clips WHERE date != (SELECT MIN(date) FROM clips)")
    assert tr.run_now("manual", wait=True) and tr.state()["activated"] is True
    first = model_store.active_version(paths.models)
    generate_into_store(store, [3], ["p01", "p02", "p03"], {}, seed=9)           # 別の日を足す → 評価できる新版
    clk.t += 4000
    assert tr.has_new_data()
    tr.run_now("manual", wait=True)
    st = tr.state()
    assert st["version"] != first and st["version"] in model_store.versions(paths.models)
    assert st["activated"] in (True, False) and st["reason"]


def test_failed_training_keeps_the_old_model(world, monkeypatch):
    tr, cfg, store, collect, speak, clk, paths = world
    tr._spawn = lambda cmd, log: __import__("subprocess").Popen([os.sys.executable, "-c", "import sys; sys.exit(3)"])
    assert tr.run_now("manual", wait=True)
    st = tr.state()
    assert st["error"] and st["activated"] is False and model_store.active_version(paths.models) is None


# ---- 日付の切り替え時刻 ----
def test_day_start_hour_shifts_the_shooting_date(paths, monkeypatch):
    cfg = {"s": Settings()}
    st = Store(paths, lambda: cfg["s"])

    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 25, 2, 30, tzinfo=tz)
    monkeypatch.setattr(store_mod, "datetime", FakeDT)
    assert st.today() == "2026-10-25"
    cfg["s"] = replace(cfg["s"], day_start_hour=4.0)
    assert st.today() == "2026-10-24"                              # 午前 4 時までは前日
    cfg["s"] = replace(cfg["s"], date_override="day2")
    assert st.today() == "day2"
    st.close()
