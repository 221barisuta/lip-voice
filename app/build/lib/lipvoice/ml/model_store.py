"""学習済みモデルの保存と版管理。models/<版>/ に保存し、models/active.json が現在の版を指す。
ロールバックは active.json を書き換えるだけ。書き込みは一時フォルダ → 名前変更で、途中で壊れない。"""
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

from .features import Standardizer
from .infer import Predictor


def _atomic_json(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def save_version(root: Path, *, classes: list[str], feature: dict, std: Standardizer, active: str, tau: dict,
                 dtw: dict | None, cnn: dict | None, extra: dict, activate: bool = True) -> str:
    root.mkdir(parents=True, exist_ok=True)
    version = datetime.now().strftime("%Y%m%d-%H%M%S")
    while (root / version).exists():
        version += "x"
    tmp = Path(tempfile.mkdtemp(dir=root, prefix=".tmp-"))
    try:
        np.savez_compressed(tmp / "stats.npz", mean=std.mean, std=std.std)
        if dtw is not None:
            np.savez_compressed(tmp / "dtw.npz", **dtw)
        if cnn is not None:
            np.savez_compressed(tmp / "cnn.npz", **cnn)
        (tmp / "meta.json").write_text(json.dumps(
            {"version": version, "classes": classes, "feature": feature, "active": active, "tau": tau, "extra": extra},
            ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, root / version)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    if activate:
        set_active(root, version)
    return version


def set_active(root: Path, version: str) -> None:
    if not (root / version / "meta.json").exists():
        raise FileNotFoundError(f"モデルの版がありません: {version}")
    _atomic_json(root / "active.json", {"version": version})


def versions(root: Path) -> list[str]:
    return sorted(p.name for p in root.glob("*") if (p / "meta.json").exists()) if root.exists() else []


def active_version(root: Path) -> str | None:
    try:
        v = json.loads((root / "active.json").read_text(encoding="utf-8"))["version"]
        return v if (root / v / "meta.json").exists() else None
    except (OSError, ValueError, KeyError):
        return None


def load_active(root: Path) -> Predictor | None:
    v = active_version(root)
    return Predictor(root / v) if v else None
