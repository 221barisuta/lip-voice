"""環境変数から設定を読む。値の既定は置かない（未設定なら起動時に落とす）。"""
import os
from functools import lru_cache


class MissingConfig(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise MissingConfig(f"環境変数 {name} が未設定です")
    return value


@lru_cache
def project_id() -> str:
    return _required("GCP_PROJECT_ID")


@lru_cache
def bucket_name() -> str:
    return _required("GCS_BUCKET")


@lru_cache
def allowed_origins() -> list[str]:
    raw = _required("ALLOWED_ORIGINS")
    return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def allowed_emails() -> set[str]:
    """ログインを許可する Google アカウント（メール）。未設定なら誰も通さない。"""
    raw = _required("ALLOWED_EMAILS")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}
