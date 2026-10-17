"""起動時の整合性検査。DB とファイルの食い違いを見つけ、孤児ファイルを orphans/ へ退避する。"""
import shutil
from dataclasses import dataclass, field

from .store import Store


@dataclass
class Report:
    missing_files: list[str] = field(default_factory=list)     # DB にあるがファイルがない（クリップ ID）
    orphan_files: list[str] = field(default_factory=list)      # ファイルはあるが DB にない
    stale_tmp: list[str] = field(default_factory=list)         # 書き込み途中で残った一時ファイル
    moved: int = 0

    @property
    def ok(self) -> bool:
        return not (self.missing_files or self.orphan_files or self.stale_tmp)


def check(store: Store, repair: bool = False) -> Report:
    rep = Report()
    root = store.paths.clips
    known: set[str] = set()
    for r in store.clip_rows():
        for rel in (r["landmarks_path"], r["video_path"]):
            if not rel:                                        # 動画なしで取り込んだクリップ
                continue
            known.add(rel)
            if not (root / rel).exists():
                rep.missing_files.append(r["id"])
                break
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            if rel not in known:
                rep.orphan_files.append(rel)
                if repair:
                    dest = store.paths.orphans / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(p), dest)
                    rep.moved += 1
    for p in store.paths.tmp.glob("*.part"):
        rep.stale_tmp.append(p.name)
        if repair:
            p.unlink(missing_ok=True)
    return rep
