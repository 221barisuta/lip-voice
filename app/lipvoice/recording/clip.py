"""1 回の録画（可変長）。特徴点は正規化前の生の座標で保存し、正規化は学習・認識の側で行う。"""
import io
from dataclasses import dataclass, field

import numpy as np

from ..vision.indices import SAVED_INDICES
from ..vision.stillness import StopReason


@dataclass
class RecordedClip:
    t_ms: np.ndarray            # (N,) 録画開始からのミリ秒
    points: np.ndarray          # (N, K, 3) float32。K = len(SAVED_INDICES)。検出できなかったフレームは 0
    valid: np.ndarray           # (N,) bool 顔を検出できたフレーム
    blend: np.ndarray           # (N, 52) float32
    opening: np.ndarray         # (N,) 口の開き（検出できなかったフレームは NaN）
    crops: list[np.ndarray] = field(default_factory=list)   # 96×96 グレースケール（口元動画の元）
    blend_names: list[str] = field(default_factory=list)
    width: int = 0
    height: int = 0
    stop_reason: StopReason = "still"

    @property
    def frame_count(self) -> int:
        return len(self.t_ms)

    @property
    def duration_ms(self) -> int:
        return int(self.t_ms[-1]) if self.frame_count else 0

    @property
    def fps_measured(self) -> float:
        d = self.duration_ms / 1000
        return round(self.frame_count / d, 1) if d > 0 else 0.0

    @property
    def detected_ratio(self) -> float:
        return float(self.valid.mean()) if self.frame_count else 0.0

    def to_npz(self) -> bytes:
        buf = io.BytesIO()
        np.savez_compressed(
            buf, version=np.int32(1), t_ms=self.t_ms.astype(np.int32), points=self.points.astype(np.float32),
            indices=np.array(SAVED_INDICES, dtype=np.int16), valid=self.valid, blend=self.blend.astype(np.float32),
            opening=self.opening.astype(np.float32), blend_names=np.array(self.blend_names, dtype="U40"),
            image_size=np.array([self.width, self.height], dtype=np.int32))
        return buf.getvalue()


def load_npz(data: bytes | str) -> dict[str, np.ndarray]:
    """保存した特徴点を読む。pickle は使わない（allow_pickle=False）。"""
    with np.load(io.BytesIO(data) if isinstance(data, bytes) else data, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}
