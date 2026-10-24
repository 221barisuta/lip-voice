"""学習済みモデルの保存と版管理。models/<版>/ に保存し、models/active.json が現在の版を指す。
ロールバックは active.json を書き換えるだけ。書き込みは一時フォルダ → 名前変更で、途中で壊れない。"""
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

from .features import Standardizer
from .infer import Predictor


VERSION_RE = re.compile(r"^\d{8}-\d{6}x*$")     # 版のフォルダ名。学習途中の .tmp-* などは、版として扱わない


def _fsync_file(path: Path) -> None:
    """停電で、空や途中のファイルが「完成した版」に残らないよう、書いたファイルを確実にディスクへ書き出す。"""
    with open(path, "rb+") as f:
        f.flush()
        os.fsync(f.fileno())


def cleanup_tmp(root: Path) -> int:
    """学習の途中で止まった一時フォルダを消す（起動時）。"""
    n = 0
    for p in root.glob(".tmp-*") if root.exists() else []:
        shutil.rmtree(p, ignore_errors=True)
        n += 1
    return n


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
        for f in tmp.iterdir():
            _fsync_file(f)
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
    prev = active_version(root)
    _atomic_json(root / "active.json", {"version": version, "previous": prev if prev != version else _previous(root)})


def _previous(root: Path) -> str | None:
    try:
        return json.loads((root / "active.json").read_text(encoding="utf-8")).get("previous")
    except (OSError, ValueError):
        return None


def versions(root: Path) -> list[str]:
    return sorted(p.name for p in root.glob("*") if VERSION_RE.match(p.name) and (p / "meta.json").exists()) if root.exists() else []


def active_version(root: Path) -> str | None:
    try:
        v = json.loads((root / "active.json").read_text(encoding="utf-8"))["version"]
        return v if VERSION_RE.match(v) and (root / v / "meta.json").exists() else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def load_active(root: Path) -> Predictor | None:
    """使うモデルを読む。壊れていたら（停電などで）、前に使っていた版、なければ新しい順に、読める版を使う。アプリが起動できなくならないように。"""
    first = active_version(root)
    candidates = ([first] if first else []) + ([_previous(root)] if _previous(root) else []) + list(reversed(versions(root)))
    seen = set()
    for v in candidates:
        if not v or v in seen or not (root / v).is_dir():
            continue
        seen.add(v)
        try:
            return Predictor(root / v)
        except Exception as e:                              # meta.json が壊れている、ファイルが欠けている、など
            print(f"モデルの版 {v} を読めません（{type(e).__name__}）。別の版を試します", file=sys.stderr)
    return None
