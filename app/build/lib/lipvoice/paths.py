"""データの置き場所。利用者ごと（プロフィールごと）にフォルダを分ける。

~/LipVoice/                     LIPVOICE_HOME で変更できる
  assets/face_landmarker.task   MediaPipe のモデル（初回だけ取得。以後はオフラインで動く）
  <profile>/                    既定は default。開発者のテストデータと本人のデータを混ぜない
    config.json  lipvoice.db  clips/  tmp/  orphans/  models/  logs/
"""
import os
from dataclasses import dataclass
from pathlib import Path


def home_dir() -> Path:
    return Path(os.environ.get("LIPVOICE_HOME", "~/LipVoice")).expanduser()


@dataclass(frozen=True)
class Paths:
    home: Path
    profile: str = "default"

    @property
    def root(self) -> Path:
        return self.home / self.profile

    @property
    def assets(self) -> Path:
        return self.home / "assets"

    @property
    def model_file(self) -> Path:
        return self.assets / "face_landmarker.task"

    @property
    def config(self) -> Path:
        return self.root / "config.json"

    @property
    def db(self) -> Path:
        return self.root / "lipvoice.db"

    @property
    def clips(self) -> Path:
        return self.root / "clips"

    @property
    def tmp(self) -> Path:
        return self.root / "tmp"

    @property
    def orphans(self) -> Path:
        return self.root / "orphans"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def ensure(self) -> "Paths":
        for p in (self.assets, self.root, self.clips, self.tmp, self.orphans, self.models, self.logs):
            p.mkdir(parents=True, exist_ok=True)
        return self
