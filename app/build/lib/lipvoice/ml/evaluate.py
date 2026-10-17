"""評価（仕様 7.3・8.4）。上位1・上位3の正解率（件数 n/N つき）、フレーズ別、取り違え表、棄却の評価。"""
from dataclasses import dataclass, field

import numpy as np

CRITERIA = {"top3": 0.90, "top1": 0.70, "latency_ms": 2000}     # 仕様 2章の合格基準


@dataclass
class Pred:
    clip_id: str
    date: str
    true: str | None                 # 正解のフレーズ。負例は None
    neg_label: str | None
    ranked: list[str]
    conf: list[float]
    distance: float                  # 棄却に使う距離
    extra: dict = field(default_factory=dict)


def _rate(k: int, n: int) -> dict:
    return {"k": int(k), "n": int(n), "rate": (k / n) if n else None}


def metrics(preds: list[Pred]) -> dict:
    pos = [p for p in preds if p.true is not None]
    top1 = sum(p.ranked[0] == p.true for p in pos)
    top3 = sum(p.true in p.ranked[:3] for p in pos)
    per: dict[str, dict] = {}
    conf: dict[str, dict[str, int]] = {}
    for p in pos:
        d = per.setdefault(p.true, {"n": 0, "top1": 0, "top3": 0})
        d["n"] += 1
        d["top1"] += p.ranked[0] == p.true
        d["top3"] += p.true in p.ranked[:3]
        conf.setdefault(p.true, {}).setdefault(p.ranked[0], 0)
        conf[p.true][p.ranked[0]] += 1
    mistakes = [{"clip_id": p.clip_id, "date": p.date, "true": p.true, "top3": p.ranked[:3]} for p in pos
                if p.ranked[0] != p.true][:100]
    return {"top1": _rate(top1, len(pos)), "top3": _rate(top3, len(pos)),
            "per_phrase": {k: {**v, "top1_rate": v["top1"] / v["n"], "top3_rate": v["top3"] / v["n"]} for k, v in per.items()},
            "confusion": conf, "mistakes": mistakes}


def choose_tau(pos_dist: list[float], neg_dist: list[float], target_far: float = 0.05) -> tuple[float, str]:
    """棄却の閾値。負例の誤受理率が目標以下になる最大の値。負例がなければ、正例の距離の 95 パーセンタイルの 1.2 倍。"""
    pos = np.array(pos_dist) if len(pos_dist) else np.array([1.0])
    if len(neg_dist) >= 5:
        neg = np.sort(np.array(neg_dist))
        k = int(np.floor(target_far * len(neg)))          # 受理してよい負例の数
        tau = float(neg[k]) * 0.999 if k < len(neg) else float(neg[-1])
        return min(tau, float(pos.max()) * 1.5), "負例の誤受理率が目標以下になる値"
    return float(np.percentile(pos, 95) * 1.2), "負例がないため、正例の距離から決めた値（負例を録ると校正できます）"


def rejection_table(preds: list[Pred], tau: float, conf_thresholds=(0.5, 0.7, 0.8, 0.9, 0.95, 0.99)) -> list[dict]:
    """確信度の閾値ごとに、自動で発話する割合と、その中の誤発話率（正例の取り違え + 負例の誤受理）。"""
    pos = [p for p in preds if p.true is not None]
    neg = [p for p in preds if p.true is None]
    rows = []
    for c in conf_thresholds:
        acc_pos = [p for p in pos if p.distance <= tau and p.conf[0] >= c]
        acc_neg = [p for p in neg if p.distance <= tau and p.conf[0] >= c]
        wrong = sum(p.ranked[0] != p.true for p in acc_pos) + len(acc_neg)
        spoken = len(acc_pos) + len(acc_neg)
        rows.append({"conf": c, "auto_rate": _rate(len(acc_pos), len(pos)),
                     "wrong_rate": _rate(wrong, spoken), "neg_accept": _rate(len(acc_neg), len(neg))})
    return rows


def judge(m: dict, latency_ms: float | None) -> dict:
    t1, t3 = m["top1"]["rate"], m["top3"]["rate"]
    return {"top3": {"value": t3, "need": CRITERIA["top3"], "ok": t3 is not None and t3 >= CRITERIA["top3"]},
            "top1": {"value": t1, "need": CRITERIA["top1"], "ok": t1 is not None and t1 >= CRITERIA["top1"]},
            "latency_ms": {"value": latency_ms, "need": CRITERIA["latency_ms"],
                           "ok": latency_ms is not None and latency_ms <= CRITERIA["latency_ms"]}}
