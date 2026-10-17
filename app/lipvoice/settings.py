"""設定ファイル（config.json）。制限値はハードコードせず、ここに置く（既定は緩い）。"""
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

# 設定ごとの許容範囲（画面のスライダーにも使う）
LIMITS: dict[str, tuple[float, float]] = {
    "threshold": (0.002, 0.05),     # 口の開きの変動幅（目尻間の距離を 1 とした値）
    "still_sec": (0.5, 3.0),        # 止まってから録画を終えるまで
    "max_sec": (3.0, 30.0),         # 最大の録画時間
    "session_minutes": (1.0, 60.0),
    "min_detected_ratio": (0.0, 1.0),
}

DEFAULT_NEGATIVE_KINDS = ["あくび", "咳", "口を湿らせる", "飲み込み", "自由な口パク", "その他"]


@dataclass
class Settings:
    # 録画の終了条件（収集 7.1 と認識 7.2 で共通）
    threshold: float = 0.01
    still_sec: float = 1.0
    max_sec: float = 10.0
    # 収集セッション
    session_minutes: float = 5.0
    min_detected_ratio: float = 0.7      # 検出できたフレームの割合がこれ未満なら保存させない
    negative_kinds: list[str] = field(default_factory=lambda: list(DEFAULT_NEGATIVE_KINDS))
    # カメラ
    camera_source: str = "0"             # カメラ番号、または動画ファイルのパス（試験用）
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30
    timezone: str = "Asia/Tokyo"         # 撮影日（学習/評価を分ける単位）の基準
    # 制限（0 は無制限）。既定は緩く、必要になったら絞る
    max_phrases: int = 1000
    max_phrase_chars: int = 200
    max_clips_per_day: int = 0


def sanitize(raw: dict) -> Settings:
    base = Settings()
    out = asdict(base)
    for f in fields(Settings):
        if f.name not in raw:
            continue
        v, default = raw[f.name], getattr(base, f.name)
        if isinstance(default, bool):
            continue
        if isinstance(default, (int, float)) and isinstance(v, (int, float)) and not isinstance(v, bool):
            if f.name in LIMITS:
                lo, hi = LIMITS[f.name]
                v = min(hi, max(lo, float(v)))
            out[f.name] = type(default)(v) if f.name not in LIMITS else float(v)
        elif isinstance(default, str) and isinstance(v, str) and v.strip():
            out[f.name] = v.strip()
        elif isinstance(default, list) and isinstance(v, list):
            items = [str(x).strip() for x in v if str(x).strip()]
            out[f.name] = items[:200] or default
    for k in ("max_phrases", "max_phrase_chars", "max_clips_per_day", "camera_width", "camera_height", "camera_fps"):
        out[k] = max(0, int(out[k]))
    for k in ("camera_width", "camera_height", "camera_fps"):
        out[k] = out[k] or getattr(base, k)
    return Settings(**out)


def load(path: Path) -> Settings:
    try:
        return sanitize(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return Settings()


def save(path: Path, s: Settings) -> None:
    """途中で電源が落ちても壊れないよう、一時ファイルに書いてから置き換える。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(s), f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class SettingsHolder:
    """最新の設定を保持し、変更をファイルに書く（画面・エンジン・保存処理が同じものを見る）。"""

    def __init__(self, path: Path):
        self.path = path
        self._s = load(path)

    def get(self) -> Settings:
        return self._s

    def update(self, changes: dict) -> Settings:
        merged = {**asdict(self._s), **{k: v for k, v in changes.items() if k in asdict(self._s)}}
        self._s = sanitize(merged)
        save(self.path, self._s)
        return self._s
