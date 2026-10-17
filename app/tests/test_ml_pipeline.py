import json

import numpy as np
import pytest

from lipvoice.ml.features import FeatureConfig
from lipvoice.ml.infer import CNNModel, Predictor
from lipvoice.ml.model_store import active_version, load_active, set_active, versions
from lipvoice.ml.synthetic import generate_into_store
from lipvoice.ml.train import run_training
from lipvoice.recording.clip import load_npz

PHRASES = ["p01", "p02", "p03", "p04"]


@pytest.fixture
def synth_store(store):
    generate_into_store(store, [4, 4, 3], PHRASES, {"あくび": 5, "咳": 5}, seed=1)
    return store


def test_numpy_inference_matches_torch():
    torch = pytest.importorskip("torch")
    from lipvoice.ml.model import build, export_net
    torch.manual_seed(0)
    net = build(20, 5)
    for m in net.modules():                                    # BN の統計をわざと非自明にする
        if isinstance(m, torch.nn.BatchNorm1d):
            m.running_mean.normal_(0, 0.5); m.running_var.uniform_(0.5, 2.0); m.weight.data.uniform_(0.5, 1.5); m.bias.data.normal_(0, 0.3)
    net.eval()
    x = np.random.default_rng(0).normal(size=(64, 20)).astype(np.float32)
    with torch.no_grad():
        t_logits = net(torch.tensor(x).T[None]).numpy()[0]
        t_emb = net.embed(torch.tensor(x).T[None]).numpy()[0]
    cnn = CNNModel(export_net(net, np.zeros((5, 64), np.float32), list("abcde")))
    logits, emb = cnn.forward(x)
    assert np.allclose(logits, t_logits, atol=1e-4) and np.allclose(emb, t_emb, atol=1e-4)


def test_train_saves_versioned_model_and_predicts(synth_store, paths):
    pytest.importorskip("torch")
    rep = run_training(synth_store, paths, FeatureConfig(), epochs=8, log=lambda *_: None)
    assert rep["evaluated"] and set(rep["results"]) == {"A", "B"} and rep["active"] in ("A", "B")
    assert rep["results"]["A"]["lodo"]["top3"]["n"] == 4 * 11            # 4 フレーズ × (4+4+3) 本
    assert (paths.models / "active.json").exists() and (paths.models / "reports" / "latest.json").exists()
    pred = load_active(paths.models)
    row = next(r for r in synth_store.clip_rows() if r["kind"] == "phrase")
    out = pred.predict(load_npz(str(synth_store.clip_path(row["landmarks_path"]))))
    assert len(out["candidates"]) == 3 and out["candidates"][0]["phrase_id"] in PHRASES
    assert out["version"] == rep["version"] and isinstance(out["rejected"], bool) and out["latency_ms"] < 2000
    # フレーズに似ていない動き（負例）は、正例より距離が大きい
    d_pos, d_neg = [], []
    for r in synth_store.clip_rows():
        raw = load_npz(str(synth_store.clip_path(r["landmarks_path"])))
        (d_pos if r["kind"] == "phrase" else d_neg).append(pred.predict(raw)["distance"])
    assert np.mean(d_neg) > np.mean(d_pos)


def test_model_versions_and_rollback(synth_store, paths):
    run_training(synth_store, paths, FeatureConfig(), use_cnn=False, log=lambda *_: None)
    v1 = active_version(paths.models)
    run_training(synth_store, paths, FeatureConfig(), use_cnn=False, log=lambda *_: None)
    v2 = active_version(paths.models)
    assert v1 != v2 and versions(paths.models) == sorted([v1, v2])
    set_active(paths.models, v1)                                          # ロールバック
    assert active_version(paths.models) == v1 and Predictor(paths.models / v1).version == v1
    assert json.loads((paths.models / "active.json").read_text())["version"] == v1
    with pytest.raises(FileNotFoundError):
        set_active(paths.models, "nope")


def test_single_day_is_not_evaluated(store, paths):
    generate_into_store(store, [4], PHRASES, None, seed=2)
    rep = run_training(store, paths, FeatureConfig(), use_cnn=False, log=lambda *_: None)
    assert rep["evaluated"] is False and "別の日" in rep["note"] and rep["taus"]["A"] > 0


def test_models_are_pickle_free(synth_store, paths):
    run_training(synth_store, paths, FeatureConfig(), use_cnn=False, log=lambda *_: None)
    for f in (paths.models / active_version(paths.models)).glob("*.npz"):
        with np.load(f, allow_pickle=False) as z:                          # allow_pickle=False で読めること
            assert z.files
