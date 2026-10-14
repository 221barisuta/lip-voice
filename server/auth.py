"""Firebase ID トークンを検証し、uid を取り出す。uid は必ずここから取る。"""
import re

import firebase_admin
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as fb_auth

import config

_bearer = HTTPBearer(auto_error=False)
_UID_RE = re.compile(r"^[A-Za-z0-9]{1,128}$")


def _ensure_app() -> None:
    if not firebase_admin._apps:
        # 別プロジェクト（dev/prod）で発行されたトークンを通さないよう、プロジェクトIDを明示する
        firebase_admin.initialize_app(options={"projectId": config.project_id()})


def authorize(decoded: dict) -> str:
    """検証済みトークンの中身から uid を返す。許可されないアカウントは 403。"""
    uid = decoded.get("uid")
    if not isinstance(uid, str) or not _UID_RE.match(uid):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "認証に失敗しました")
    if (decoded.get("firebase") or {}).get("sign_in_provider") != "google.com":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "認証に失敗しました")
    email = str(decoded.get("email", "")).lower()
    if not decoded.get("email_verified") or email not in config.allowed_emails():
        # Firebase はサインアップを開けると誰でもアカウントを作れるため、サーバー側でも許可リストで絞る
        raise HTTPException(status.HTTP_403_FORBIDDEN, "このアカウントは許可されていません")
    return uid


def current_uid(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if cred is None or cred.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "認証が必要です")
    _ensure_app()
    try:
        decoded = fb_auth.verify_id_token(cred.credentials, check_revoked=True)
    except Exception:
        # 失効・期限切れ・改ざんを区別せず 401（詳細は返さない）
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "認証に失敗しました")
    return authorize(decoded)
