#!/usr/bin/env bash
# ローカルで API を起動する。dev の実プロジェクトに gcloud のアプリケーションデフォルト認証（ADC）で接続する。
# 事前に一度だけ:  gcloud auth application-default login
# 使い方:           scripts/dev-server.sh   （別ターミナルで web/ で npm run dev）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/.env.dev" ] || { echo "$ROOT/.env.dev がありません" >&2; exit 1; }

# エミュレータ向けの変数が残っていると実プロジェクトに繋がらないため消す
unset FIRESTORE_EMULATOR_HOST STORAGE_EMULATOR_HOST FIREBASE_AUTH_EMULATOR_HOST
set -a; . "$ROOT/.env.dev"; set +a

for v in GCP_PROJECT_ID GCS_BUCKET ALLOWED_ORIGINS ALLOWED_EMAILS; do
  [ -n "${!v:-}" ] || { echo ".env.dev の $v が空です" >&2; exit 1; }
done
gcloud auth application-default print-access-token >/dev/null 2>&1 \
  || { echo "ADC がありません。先に: gcloud auth application-default login" >&2; exit 1; }

cd "$ROOT/server"
if [ ! -x .venv/bin/uvicorn ]; then
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/uvicorn main:app --port 8000
