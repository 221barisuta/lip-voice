"""学習と評価（日ごとの leave-one-day-out 交差検証）。仕様 8章。

 1. 日ごとに、その日を評価に回し、残りの日で A・B を学習して、評価日を予想する（日付で分ける。ランダムに分けない）
 2. 全予想をまとめて、正解率・取り違え表・棄却の閾値を決める
 3. 最終モデルは全日で学習し直す（閾値は 2 で決めた値）
標準化の値や距離のお手本は、学習側の日だけから作る（評価日が混ざると過大評価になる）。
"""
import time
from dataclasses import asdict
from datetime import datetime

import numpy as np

from ..paths import Paths
from .data import ClipItem, load_items, stack
from .dtw_baseline import DTWModel
from .evaluate import CRITERIA, Pred, choose_tau, judge, metrics, rejection_table
from .features import FeatureConfig, Standardizer
from .infer import CNNModel, Predictor
from .model_store import _atomic_json, save_version
from .split import dates_of, leave_one_day_out


def _fit(pos: list[ClipItem], classes: list[str], use_cnn: bool, epochs: int, seed: int, log):
    std = Standardizer.fit(stack(pos))
    xs = std(stack(pos))
    labels = [it.label for it in pos]
    dtw = DTWModel.fit(xs, labels)
    cnn = None
    if use_cnn:
        from .model import train_cnn
        cnn = train_cnn(xs, np.array([classes.index(l) for l in labels]), classes, epochs=epochs, seed=seed, log=log)
    return std, dtw, cnn


def _predict(items: list[ClipItem], std: Standardizer, dtw: DTWModel, cnn: dict | None) -> dict[str, list[Pred]]:
    out: dict[str, list[Pred]] = {"A": [], "B": []}
    cnn_m = CNNModel(cnn) if cnn else None
    for it in items:
        x = std(it.x)
        true = it.label if it.kind == "phrase" else None
        neg = it.label if it.kind == "negative" else None
        for key, model in (("A", dtw), ("B", cnn_m)):
            if model is None:
                continue
            r = model.predict(x)
            out[key].append(Pred(it.id, it.date, true, neg, r["ranked"], r["confidence"], r["distance"]))
    return out


def run_training(store, paths: Paths, cfg: FeatureConfig, *, epochs: int = 60, seed: int = 0, use_cnn: bool = True,
                 sources: tuple[str, ...] = ("collect",), activate: bool = True, force_active: str | None = None,
                 log=print) -> dict:
    t_start = time.time()
    items = load_items(store, cfg, sources)
    pos = [it for it in items if it.kind == "phrase"]
    neg = [it for it in items if it.kind == "negative"]
    if len(pos) < 4:
        raise ValueError("学習できるクリップが足りません（フレーズのクリップが 4 本未満）")
    classes = sorted({it.label for it in pos})
    dates = dates_of(pos)
    log(f"データ: フレーズ {len(pos)} 本 / 負例 {len(neg)} 本 / 撮影日 {dates} / フレーズ {len(classes)} 種")

    lodo: dict[str, list[Pred]] = {"A": [], "B": []}
    per_day: dict[str, dict] = {}
    folds = leave_one_day_out(pos)
    for train_days, held in folds:
        log(f"交差検証: 評価日 {held}（学習日 {train_days}）")
        tr = [it for it in pos if it.date in train_days]
        ev = [it for it in pos + neg if it.date == held]
        std, dtw, cnn = _fit(tr, classes, use_cnn, epochs, seed, log)
        res = _predict(ev, std, dtw, cnn)
        for k in res:
            lodo[k].extend(res[k])
        per_day[held] = {k: metrics([p for p in v if p.true is not None]) for k, v in res.items() if v}

    report: dict = {"created_at": datetime.now().isoformat(timespec="seconds"), "dates": dates, "classes": classes,
                    "feature": asdict(cfg), "n_pos": len(pos), "n_neg": len(neg), "criteria": CRITERIA,
                    "counts_by_day": {d: sum(it.date == d for it in pos) for d in dates},
                    "negatives_by_label": {l: sum(it.label == l for it in neg) for l in sorted({it.label for it in neg})},
                    "evaluated": bool(folds)}
    taus: dict[str, float] = {}
    tau_note: dict[str, str] = {}
    results: dict[str, dict] = {}
    if folds:
        for k in ("A", "B"):
            if not lodo[k]:
                continue
            m = metrics(lodo[k])
            pos_d = [p.distance for p in lodo[k] if p.true is not None]
            neg_d = [p.distance for p in lodo[k] if p.true is None]
            taus[k], tau_note[k] = choose_tau(pos_d, neg_d)
            last = per_day[dates[-1]].get(k) if dates[-1] in per_day else None     # 仕様 8.4 の既定の分け方（最新日を評価）
            results[k] = {"lodo": m, "last_day": last, "tau": taus[k], "tau_note": tau_note[k],
                          "rejection": rejection_table(lodo[k], taus[k]), "by_day": {d: v.get(k) for d, v in per_day.items()}}
    else:
        report["note"] = "別の日のデータがないため、評価していません（撮影日が 2 日以上になると評価できます）"

    log("最終モデルを全日のデータで学習します")
    std, dtw, cnn = _fit(pos, classes, use_cnn, epochs, seed, log)
    if not folds:                                                  # 評価できない時の暫定の閾値（学習データ自身の距離から）
        for k, model in (("A", dtw), ("B", CNNModel(cnn) if cnn else None)):
            if model is not None:
                d = [model.predict(std(it.x))["distance"] for it in pos[:100]]
                taus[k] = float(np.percentile(d, 99) * 2.0 + 1e-6)
                tau_note[k] = "評価できないため暫定の値（正例の距離から。別の日のデータで校正してください）"
    active = force_active or ("B" if ("B" in results and "A" in results and
                                      (results["B"]["lodo"]["top3"]["rate"] or 0) > (results["A"]["lodo"]["top3"]["rate"] or 0))
                              else ("B" if cnn and not folds else "A"))
    version = save_version(paths.models, classes=classes, feature=asdict(cfg), std=std, active=active, tau=taus,
                           dtw=dtw.to_npz(), cnn=cnn, activate=activate,
                           extra={"n_train": len(pos), "dates": dates, "seed": seed, "epochs": epochs,
                                  "clip_ids": [it.id for it in pos], "created_at": report["created_at"]})
    pred = Predictor(paths.models / version)
    lat = []
    for it in pos[:30]:
        t0 = time.perf_counter()
        pred.predict_features(std(it.x))
        lat.append((time.perf_counter() - t0) * 1000)
    report.update({"version": version, "active": active, "taus": taus, "tau_note": tau_note, "results": results,
                   "latency_ms": {"mean": round(float(np.mean(lat)), 1), "p95": round(float(np.percentile(lat, 95)), 1)}})
    if results.get(active):
        report["judgement"] = {"lodo": judge(results[active]["lodo"], report["latency_ms"]["p95"]),
                               "last_day": judge(results[active]["last_day"], report["latency_ms"]["p95"]) if results[active]["last_day"] else None}
    report["seconds"] = round(time.time() - t_start, 1)
    rdir = paths.models / "reports"
    rdir.mkdir(parents=True, exist_ok=True)
    _atomic_json(rdir / f"{version}.json", report)
    if activate:                                       # 使わなかった版の成績を、「最新」として出さない
        _atomic_json(rdir / "latest.json", report)
    return report
