"""export / import / import-models。往復で一致すること、壊れた・不正な入力を取り込まないこと。"""
import json
import shutil
from dataclasses import replace

import pytest

from lipvoice import transfer
from lipvoice.ml.features import FeatureConfig
from lipvoice.ml.model_store import active_version, load_active
from lipvoice.ml.synthetic import generate_into_store
from lipvoice.ml.train import run_training
from lipvoice.paths import Paths
from lipvoice.recording.clip import load_npz
from lipvoice.storage import integrity
from lipvoice.storage.store import Store
from lipvoice.settings import Settings

PHRASES = ["p01", "p02", "p03"]


@pytest.fixture
def src(tmp_path):
    home = tmp_path / "src"
    p = Paths(home, "patient").ensure()
    st = Store(p, lambda: Settings())
    generate_into_store(st, [3, 3], PHRASES, {"あくび": 3}, seed=2)
    run_training(st, p, FeatureConfig(), use_cnn=False, log=lambda *_: None)
    yield p, st
    st.close()


def do_export(p, tmp_path, **kw):
    out = tmp_path / "usb"
    out.mkdir(exist_ok=True)
    return transfer.export(p, Settings(), out, **kw)


def test_roundtrip_preserves_clips_and_predictions(src, tmp_path):
    p, st = src
    exp = do_export(p, tmp_path)                                  # 元のプロフィールを開いたまま（WAL）でも書き出せる
    assert not list(exp.parent.glob("*.part"))
    home = tmp_path / "dst"
    t = transfer.import_profile(exp, home, "imported")
    st2 = Store(t, lambda: Settings())
    try:
        assert [r["id"] for r in st2.clip_rows()] == [r["id"] for r in st.clip_rows()]
        assert integrity.check(st2).ok
        row = next(r for r in st.clip_rows() if r["kind"] == "phrase")
        z = load_npz(str(st.clip_path(row["landmarks_path"])))
        a = load_active(p.models).predict(z)["candidates"]
        b = load_active(t.models).predict(z)["candidates"]
        assert [c["phrase_id"] for c in a] == [c["phrase_id"] for c in b]
        assert st2.phrases() == st.phrases()
    finally:
        st2.close()


def test_video_excluded_by_default_and_included_on_request(src, tmp_path):
    p, st = src
    plain = do_export(p, tmp_path)
    assert not list(plain.rglob("*.webm"))
    with_v = do_export(p, tmp_path, with_video=True)
    assert len(list(with_v.rglob("*.webm"))) == len(st.clip_rows())
    t = transfer.import_profile(plain, tmp_path / "d1", "p1")
    st2 = Store(t, lambda: Settings())
    try:
        assert all(r["video_path"] == "" for r in st2.clip_rows()) and integrity.check(st2).ok
        with pytest.raises(ValueError):
            st2.clip_video_path(st2.clip_rows()[0]["id"])
        st2.delete_clip(st2.clip_rows()[0]["id"])                 # 動画がなくても削除できる
    finally:
        st2.close()
    t2 = transfer.import_profile(with_v, tmp_path / "d2", "p2")
    st3 = Store(t2, lambda: Settings())
    try:
        assert all(r["video_path"] for r in st3.clip_rows()) and integrity.check(st3).ok
    finally:
        st3.close()


def test_export_refuses_test_date_override(src, tmp_path):
    p, _ = src
    out = tmp_path / "usb"; out.mkdir()
    with pytest.raises(transfer.TransferError):
        transfer.export(p, replace(Settings(), date_override="day1"), out)
    assert not list(out.iterdir())
    transfer.export(p, replace(Settings(), date_override="day1"), out, force=True)


def test_exported_config_drops_test_and_machine_settings(src, tmp_path):
    p, _ = src
    exp = do_export(p, tmp_path)
    cfg = json.loads((exp / "config.json").read_text(encoding="utf-8"))
    assert "date_override" not in cfg and "camera_source" not in cfg and "auto_save" not in cfg and "threshold" in cfg


def test_corrupted_file_is_rejected(src, tmp_path):
    p, _ = src
    exp = do_export(p, tmp_path)
    f = next(exp.rglob("*.npz"))
    f.write_bytes(f.read_bytes()[:-5] + b"xxxxx")
    with pytest.raises(transfer.TransferError, match="壊れて"):
        transfer.import_profile(exp, tmp_path / "d", "x")
    assert not (tmp_path / "d" / "x").exists() and not (tmp_path / "d" / "x.importing").exists()


def test_missing_and_extra_files_are_rejected(src, tmp_path):
    p, _ = src
    exp = do_export(p, tmp_path)
    (exp / "stray.txt").write_text("x")
    with pytest.raises(transfer.TransferError, match="manifest にない"):
        transfer.verify(exp)
    (exp / "stray.txt").unlink()
    next(exp.rglob("*.npz")).unlink()
    with pytest.raises(transfer.TransferError, match="ありません"):
        transfer.verify(exp)


def test_path_traversal_in_manifest_is_rejected(src, tmp_path):
    p, _ = src
    exp = do_export(p, tmp_path)
    m = json.loads((exp / "manifest.json").read_text(encoding="utf-8"))
    m["files"]["clips/../../evil.npz"] = {"sha256": "0" * 64, "size": 1}
    (exp / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(transfer.TransferError, match="想定外"):
        transfer.verify(exp)


def test_unfinished_export_without_manifest_is_rejected(tmp_path):
    (tmp_path / "x").mkdir()
    with pytest.raises(transfer.TransferError):
        transfer.verify(tmp_path / "x")


def test_import_refuses_non_empty_profile_and_reserved_names(src, tmp_path):
    p, _ = src
    exp = do_export(p, tmp_path)
    home = tmp_path / "dst"
    transfer.import_profile(exp, home, "once")
    with pytest.raises(transfer.TransferError, match="すでにデータ"):
        transfer.import_profile(exp, home, "once")
    m = json.loads((exp / "manifest.json").read_text(encoding="utf-8"))
    assert m["profile"] == "patient"
    transfer.import_profile(exp, home)                              # 元と同じ名前（patient）で取り込める
    exp2 = do_export(Paths(tmp_path / "src", "patient"), tmp_path)
    shutil.rmtree(home / "patient")
    bad = json.loads((exp2 / "manifest.json").read_text(encoding="utf-8"))
    bad["profile"] = "default"
    (exp2 / "manifest.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(transfer.TransferError, match="--as-profile"):
        transfer.import_profile(exp2, home)


def test_empty_existing_profile_is_set_aside_not_deleted(src, tmp_path):
    p, _ = src
    exp = do_export(p, tmp_path)
    home = tmp_path / "dst"
    Store(Paths(home, "pt").ensure(), lambda: Settings()).close()   # 空のプロフィール（初期フレーズだけ）
    transfer.import_profile(exp, home, "pt")
    assert list(home.glob("pt.before-import-*"))


def test_import_models_adds_without_overwriting(src, tmp_path):
    p, _ = src
    exp = do_export(p, tmp_path, models=True, db=False)            # モデルだけ
    assert not (exp / "lipvoice.db").exists()
    with pytest.raises(transfer.TransferError, match="import-models"):
        transfer.import_profile(exp, tmp_path / "h", "m")
    dst = Paths(tmp_path / "other", "patient").ensure()
    added = transfer.import_models(exp, dst)
    assert added and active_version(dst.models) is None            # 取り込んだだけでは、使うモデルは変わらない
    assert transfer.import_models(exp, dst) == []                  # 同じ内容は何もしない
    transfer.import_models(exp, dst, activate=True)
    assert active_version(dst.models) == added[-1] or active_version(dst.models) is not None
    (dst.models / added[0] / "meta.json").write_text("{}", encoding="utf-8")
    with pytest.raises(transfer.TransferError, match="別の内容"):
        transfer.import_models(exp, dst)


def test_export_with_missing_clip_file_is_refused_and_cleaned(src, tmp_path):
    p, st = src
    next(p.clips.rglob("*.npz")).unlink()
    out = tmp_path / "usb"; out.mkdir()
    with pytest.raises(transfer.TransferError, match="欠けて"):
        transfer.export(p, Settings(), out)
    assert not list(out.iterdir())
