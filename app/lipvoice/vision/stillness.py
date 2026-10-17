"""口の開きの時系列から「話し終えたか」を判定する（収集 7.1 と認識 7.2 で共通）。

 - 直近 still_sec 秒間の開きの変動幅（最大 − 最小）が threshold 以下なら静止とみなす
 - 一度動き出すまでは判定しない（録画開始直後の静止で終わらないように）
 - 時刻（秒）で数えるので、フレームレートが変わっても同じ基準で動く
"""
from dataclasses import dataclass
from typing import Literal

StopReason = Literal["still", "max", "no_motion"]


@dataclass
class StillnessConfig:
    threshold: float   # 口の開き（目尻間の距離を 1 とした値）の変動幅
    still_sec: float   # 止まった状態がこの秒数続いたら終える
    max_sec: float     # 止まらなくてもこの秒数で終える


class StillnessDetector:
    def __init__(self, cfg: StillnessConfig):
        self.cfg = cfg
        self._samples: list[tuple[float, float]] = []
        self._moved = False

    @property
    def has_moved(self) -> bool:
        return self._moved

    @property
    def range(self) -> float:
        """直近 still_sec 秒間の開きの変動幅（画面表示・調整用）。"""
        if len(self._samples) < 2:
            return 0.0
        vs = [v for _, v in self._samples]
        return max(vs) - min(vs)

    def push(self, t: float, v: float | None) -> StopReason | None:
        """t: 録画開始からの秒。v: 口の開き（顔を見失ったら None）。終了すべきなら理由を返す。"""
        if v is not None:
            self._samples.append((t, v))
            # 窓（直近 still_sec 秒）の手前の 1 点は残す。窓の端まで観測できたかを知るため
            cutoff = t - self.cfg.still_sec
            while len(self._samples) > 1 and self._samples[1][0] <= cutoff:
                self._samples.pop(0)
            if self.range > self.cfg.threshold:
                self._moved = True
        if t >= self.cfg.max_sec:
            return "max" if self._moved else "no_motion"
        covered = bool(self._samples) and self._samples[0][0] <= t - self.cfg.still_sec
        if self._moved and covered and self.range <= self.cfg.threshold:
            return "still"
        return None
