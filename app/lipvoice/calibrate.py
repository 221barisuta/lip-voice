"""閾値のキャリブレーション（実機 Day 0 と収集画面で共通）。

口を閉じて静止した間の口の動き（ノイズ）と、口パクした間の口の動きを測り、録画の終了条件の閾値の候補を出す。
口の動き = 直近 still_sec 秒間の口の開き・口の幅の変動幅（stillness.py）。測る時の窓は、設定の still_sec と同じにする。
"""
import statistics
import threading
from dataclasses import dataclass, field

from .settings import LIMITS

SKIP_SEC = 1.0              # 測り始めの落ち着くまでの間は除く
MIN_SAMPLES = 20            # これ未満だと測定が短すぎる
SNR_OK, SNR_WARN = 3.0, 2.0
NOISE_FACTOR = 1.5          # 閾値の候補 = 静止ノイズ（95%）の 1.5 倍
SPEECH_QUANTILE = 0.75      # 発話中は間もあるので、中央値ではなく 75% を発話時の動きとする


def percentile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(len(s) * q))]


def suggest(still: list[float], speech: list[float] | None, still_sec: float) -> dict:
    """still: 静止中の口の動きの列。speech: 口パク中の列（なくてもよい）。"""
    out: dict = {"still_sec": still_sec, "n_still": len(still), "n_speech": len(speech or []), "warnings": []}
    warn = out["warnings"]
    if len(still) < MIN_SAMPLES:
        warn.append("静止の測定が短すぎます（顔が検出できていないか、時間が短い）。もう一度測ってください")
        out["grade"] = "ng"
        return out
    noise = percentile(still, 0.95)
    lo, hi = LIMITS["threshold"]
    threshold = min(hi, max(lo, noise * NOISE_FACTOR))
    out.update({"noise_p95": round(noise, 4), "threshold": round(threshold, 4), "grade": "partial"})
    noisy = "静止していても口の動きが大きく出ています。カメラを近づける・明るくする・位置を変えると改善することがあります"
    if speech is None:
        if threshold >= 0.02:
            warn.append(noisy)
        return out
    if len(speech) < MIN_SAMPLES:
        warn.append("口パクの測定が短すぎます。もう一度測ってください")
        out["grade"] = "ng"
        return out
    level = percentile(speech, SPEECH_QUANTILE)
    snr = level / noise if noise > 0 else 99.0
    out.update({"speech_level": round(level, 4), "snr": round(min(snr, 99.0), 2)})
    if snr >= SNR_OK:
        out["grade"] = "ok"
    elif snr >= SNR_WARN:
        out["grade"] = "conditional"
        warn.append("動きとノイズの差が小さめです。明るさやカメラの位置を調整して測り直すと安定します")
    else:
        out["grade"] = "ng"
        warn.append("動きとノイズの差が小さすぎます（SNR 2 未満）。口を大きめに動かして測り直すか、カメラ位置・明るさを見直してください")
    if out["grade"] != "ok" and threshold >= 0.02 and noisy not in warn:       # 動きが十分大きければ（合格）、ノイズの大きさは問題にしない
        warn.append(noisy)
    return out


@dataclass
class Sampler:
    """エンジンのスレッドが、測定中の口の動きを集める。"""
    phase: str                          # still | speech
    seconds: float
    t0: float | None = None
    samples: list[float] = field(default_factory=list)
    frames: int = 0
    faces: int = 0

    def add(self, t: float, value: float | None) -> bool:
        """1 フレーム分を入れる。測定が終わったら True。"""
        if self.t0 is None:
            self.t0 = t
        self.frames += 1
        if value is not None:
            self.faces += 1
            if t - self.t0 >= SKIP_SEC:
                self.samples.append(value)
        return t - self.t0 >= self.seconds

    def remaining(self, t: float) -> float:
        return max(0.0, self.seconds - (t - (self.t0 if self.t0 is not None else t)))


class Calibration:
    """収集画面からの校正の状態（静止 → 口パク → 候補）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.sampler: Sampler | None = None
        self.still: list[float] | None = None
        self.speech: list[float] | None = None
        self.still_sec = 1.0
        self.face_ratio: float | None = None
        self._last_t: float | None = None

    def start(self, phase: str, seconds: float, still_sec: float) -> None:
        if phase not in ("still", "speech"):
            raise ValueError("phase は still か speech")
        with self._lock:
            if phase == "still":
                self.still = self.speech = None
            self.sampler = Sampler(phase, seconds)
            self.still_sec = still_sec

    def feed(self, t: float, value: float | None) -> None:
        with self._lock:
            sm = self.sampler
            self._last_t = t
            if sm is None:
                return
            if sm.add(t, value):
                if sm.phase == "still":
                    self.still = sm.samples
                    self.face_ratio = sm.faces / max(sm.frames, 1)
                else:
                    self.speech = sm.samples
                self.sampler = None

    def snapshot(self) -> dict:
        with self._lock:
            sm = self.sampler
            out = {"running": sm is not None, "phase": sm.phase if sm else None,
                   "remaining_sec": round(sm.remaining(self._last_t if self._last_t is not None else 0.0), 1) if sm and sm.t0 is not None else (sm.seconds if sm else None),
                   "face_ratio": self.face_ratio}
            if self.still is not None:
                out["result"] = suggest(self.still, self.speech, self.still_sec)
            return out

    def result(self) -> dict | None:
        with self._lock:
            return suggest(self.still, self.speech, self.still_sec) if self.still is not None else None
