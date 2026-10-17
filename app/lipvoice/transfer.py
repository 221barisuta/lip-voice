"""データの持ち出し・取り込み（患者さんの PC → Mac、学習済みモデルの Mac → 患者さんの PC）。

export: 1 つのフォルダにまとめる。DB は SQLite の backup() で整合したスナップショットを取り（起動中でもよい）、
        その記録にあるクリップのファイルだけをコピーする。manifest.json（各ファイルの SHA-256）は最後に書き、
        一時フォルダ（.part）から名前変更で完成させる。既定は特徴点（npz）だけ。--with-video で口元動画も含める。
import: manifest を検証してから、空のプロフィールにだけ取り込む（一時フォルダ → 名前変更）。
import-models: モデルの版だけを、いまのプロフィールに追加する（既存の版は上書きしない）。
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from . import __version__
from .ml.model_store import set_active
from .paths import Paths
from .settings import SettingsHolder, save, sanitize
from .storage.db import SCHEMA_VERSION

FORMAT = 1
VERSION_RE = re.compile(r"^\d{8}-\d{6}x*$")
# 許可するファイルの形（manifest の中のパスは、ここに合うものだけを受け付ける）
PATH_RES = [re.compile(p) for p in (
    r"^lipvoice\.db$", r"^config\.json$",
    r"^clips/[0-9A-Za-z_-]{1,20}/[0-9a-f]{32}\.(npz|webm)$",
    r"^models/active\.json$", r"^models/\d{8}-\d{6}x*/(meta\.json|stats\.npz|dtw\.npz|cnn\.npz)$",
    r"^models/reports/[0-9A-Za-z_.-]{1,60}\.json$",
)]
# 取り込まない設定（試験用・この PC 固有の値）
DROP_SETTINGS = ("date_override", "auto_save", "camera_source", "camera_width", "camera_height", "camera_fps",
                 "camera_backend", "camera_rotate")


class TransferError(Exception):
    pass


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _allowed(rel: str) -> bool:
    return ".." not in rel.split("/") and any(r.match(rel) for r in PATH_RES)


def _copy(src: Path, root: Path, rel: str, files: dict) -> None:
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    files[rel] = {"sha256": _sha(dest), "size": dest.stat().st_size}


def export(p: Paths, settings, out_dir: Path, *, with_video: bool = False, models: bool = True, db: bool = True,
           force: bool = False) -> Path:
    if db and settings.date_override and not force:
        raise TransferError(f"試験用の撮影日の上書き（{settings.date_override}）が設定されています。"
                            "実際のデータなら設定を空にしてください（試験データなら --force）")
    name = f"lipvoice-export-{p.profile}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    n = 1
    while (out_dir / name).exists() or (out_dir / f"{name}.part").exists():     # 同じ秒に 2 回書き出しても上書きしない
        n += 1
        name = f"lipvoice-export-{p.profile}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{n}"
    final, part = out_dir / name, out_dir / f"{name}.part"
    part.mkdir(parents=True)
    files: dict = {}
    counts = {"clips": 0, "phrases": 0, "models": 0}
    try:
        if db:
            snap = part / "lipvoice.db"
            src = sqlite3.connect(p.db)
            dst = sqlite3.connect(snap)
            with dst:
                src.backup(dst)                       # WAL の状態に関係なく、整合したスナップショット
            dst.execute("PRAGMA journal_mode=DELETE")
            rows = dst.execute("SELECT id, landmarks_path, video_path FROM clips").fetchall()
            counts["phrases"] = dst.execute("SELECT COUNT(*) FROM phrases").fetchone()[0]
            dst.close(); src.close()
            for cid, lm, vd in rows:
                if not (p.clips / lm).exists():
                    raise TransferError(f"クリップのファイルが欠けています（{cid}）。lipvoice check を実行してください")
                _copy(p.clips / lm, part, f"clips/{lm}", files)
                if with_video and vd and (p.clips / vd).exists():
                    _copy(p.clips / vd, part, f"clips/{vd}", files)
            counts["clips"] = len(rows)
            files["lipvoice.db"] = {"sha256": _sha(snap), "size": snap.stat().st_size}
        if models and p.models.exists():
            for f in sorted(p.models.rglob("*")):
                rel = f.relative_to(p.models).as_posix()
                if f.is_file() and _allowed(f"models/{rel}"):
                    _copy(f, part, f"models/{rel}", files)
            counts["models"] = len({k.split("/")[1] for k in files if re.match(r"models/\d{8}", k)})
        cfg = {k: v for k, v in asdict(settings).items() if k not in DROP_SETTINGS}
        (part / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        files["config.json"] = {"sha256": _sha(part / "config.json"), "size": (part / "config.json").stat().st_size}
        manifest = {"format": FORMAT, "schema_version": SCHEMA_VERSION, "app_version": __version__, "profile": p.profile,
                    "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"), "with_video": with_video,
                    "has_db": db, "counts": counts, "files": files}
        (part / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.rename(part, final)
    except BaseException:
        shutil.rmtree(part, ignore_errors=True)
        raise
    return final


def verify(src: Path) -> dict:
    """manifest を読み、すべてのファイルの存在・ハッシュ・パスの形を検証する。余分なファイルがあっても拒否する。"""
    try:
        m = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise TransferError("manifest.json が読めません（書き出しが完了していないか、別のフォルダです）")
    if m.get("format") != FORMAT:
        raise TransferError(f"manifest の形式が違います（{m.get('format')}）")
    if m.get("schema_version", 0) > SCHEMA_VERSION:
        raise TransferError("新しい版のデータです。アプリを更新してください")
    files = m.get("files") or {}
    for rel, info in files.items():
        if not isinstance(rel, str) or not _allowed(rel):
            raise TransferError(f"想定外のパスです: {rel!r}")
        f = src / rel
        if not f.is_file():
            raise TransferError(f"ファイルがありません: {rel}")
        if f.stat().st_size != info.get("size") or _sha(f) != info.get("sha256"):
            raise TransferError(f"ファイルが壊れています: {rel}")
    on_disk = {q.relative_to(src).as_posix() for q in src.rglob("*") if q.is_file()} - {"manifest.json"}
    extra = on_disk - set(files)
    if extra:
        raise TransferError(f"manifest にないファイルがあります: {sorted(extra)[:3]}")
    return m


def _is_empty_profile(p: Paths) -> bool:
    if not p.root.exists():
        return True
    if any(p.clips.rglob("*.npz")) if p.clips.exists() else False:
        return False
    if p.models.exists() and any((v / "meta.json").exists() for v in p.models.iterdir() if v.is_dir()):
        return False
    if p.db.exists():
        con = sqlite3.connect(p.db)
        try:
            return all(con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0 for t in ("clips", "predictions"))
        except sqlite3.Error:
            return False
        finally:
            con.close()
    return True


def import_profile(src: Path, home: Path, profile: str | None = None) -> Paths:
    m = verify(src)
    if not m.get("has_db"):
        raise TransferError("データベースを含まない書き出しです（モデルだけの場合は import-models を使います）")
    target = Paths(home, profile or m["profile"])
    if target.profile in ("default", "test") and profile is None:
        raise TransferError("取り込み先の名前を --as-profile で指定してください（default / test は使えません）")
    if not _is_empty_profile(target):
        raise TransferError(f"取り込み先のプロフィール「{target.profile}」にはすでにデータがあります。--as-profile で別の名前にしてください")
    stage = home / f"{target.profile}.importing"
    shutil.rmtree(stage, ignore_errors=True)
    try:
        shutil.copytree(src, stage, ignore=shutil.ignore_patterns("manifest.json", "config.json"))
        for sub in ("tmp", "orphans", "logs", "models", "clips"):
            (stage / sub).mkdir(exist_ok=True)
        cfg = json.loads((src / "config.json").read_text(encoding="utf-8"))
        save(stage / "config.json", sanitize({k: v for k, v in cfg.items() if k not in DROP_SETTINGS}))
        con = sqlite3.connect(stage / "lipvoice.db")
        n = con.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
        for cid, vd in con.execute("SELECT id, video_path FROM clips").fetchall():
            if vd and not (stage / "clips" / vd).exists():           # 動画を含めなかった書き出し
                con.execute("UPDATE clips SET video_path='' WHERE id=?", (cid,))
        con.commit()
        con.close()
        if n != m["counts"]["clips"]:
            raise TransferError(f"クリップの件数が合いません（記録 {n} 件、manifest {m['counts']['clips']} 件）")
        if target.root.exists():
            os.rename(target.root, home / f"{target.profile}.before-import-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        os.rename(stage, target.root)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return target.ensure()


def import_models(src: Path, p: Paths, activate: bool = False) -> list[str]:
    """モデルの版を追加する。同じ名前の版が別の内容なら拒否。有効にするのは --activate の時だけ。"""
    verify(src)
    root = src / "models"
    found = sorted(d.name for d in root.iterdir() if d.is_dir() and VERSION_RE.match(d.name)) if root.exists() else []
    if not found:
        raise TransferError("モデルが含まれていません")
    p.models.mkdir(parents=True, exist_ok=True)
    added: list[str] = []
    for v in found:
        dest = p.models / v
        if dest.exists():
            same = all((dest / f.name).exists() and _sha(dest / f.name) == _sha(f) for f in (root / v).iterdir())
            if not same:
                raise TransferError(f"同じ名前の版「{v}」が、別の内容ですでにあります。取り込みを中止しました")
            continue
        tmp = p.models / f".tmp-import-{v}"
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(root / v, tmp)
        os.replace(tmp, dest)
        rep = root / "reports" / f"{v}.json"
        if rep.exists():
            (p.models / "reports").mkdir(exist_ok=True)
            shutil.copyfile(rep, p.models / "reports" / f"{v}.json")
        added.append(v)
    if activate:
        set_active(p.models, found[-1])
    return added
