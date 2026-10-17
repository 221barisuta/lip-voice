from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class Frame:
    image: np.ndarray   # BGR
    t: float            # 単調増加の秒（time.monotonic）


class FrameSource(Protocol):
    description: str

    def read(self) -> Frame | None: ...
    def close(self) -> None: ...
