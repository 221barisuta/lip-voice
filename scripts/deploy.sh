#!/usr/bin/env bash
# 使い方: scripts/deploy.sh dev|prod
# 環境ごとの差分は .env.<env> だけ。プロジェクトID・バケット名などはここに書かない。
# DRY_RUN=1 を付けると、実行せずにコマンドだけ表示する。
set -euo pipefail

ENV_NAME="${1:-}"
case "$ENV_NAME" in dev|prod) ;; *) echo "使い方: $0 dev|prod" >&2; exit 2;; esac

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env.$ENV_NAME"
[ -f "$ENV_FILE" ] || { echo "$ENV_FILE がありません（.env.$ENV_NAME.example を参照）" >&2; exit 1; }

set -a; . "$ENV_FILE"; set +a

for v in GCP_PROJECT_ID GCP_REGION GCS_BUCKET VITE_FIREBASE_API_KEY VITE_FIREBASE_AUTH_DOMAIN \
         VITE_FIREBASE_PROJECT_ID VITE_FIREBASE_STORAGE_BUCKET VITE_FIREBASE_APP_ID \
         CLOUD_RUN_SERVICE ALLOWED_EMAILS; do
  [ -n "${!v:-}" ] || { echo "$ENV_FILE の $v が空です" >&2; exit 1; }
done

# 取り違え防止: Firebase 側と GCP 側のプロジェクトが一致していること
[ "$VITE_FIREBASE_PROJECT_ID" = "$GCP_PROJECT_ID" ] \
  || { echo "VITE_FIREBASE_PROJECT_ID と GCP_PROJECT_ID が一致しません" >&2; exit 1; }

# ローカル検証用のエミュレータ設定が配置物に混ざらないようにする
[ -z "${VITE_AUTH_EMULATOR_URL:-}" ] || { echo "VITE_AUTH_EMULATOR_URL は配置時には空にしてください" >&2; exit 1; }

P="$GCP_PROJECT_ID"
SA_NAME="lip-voice-api"
SA="$SA_NAME@$P.iam.gserviceaccount.com"
# サーバーの CORS 許可は Hosting の URL を自動で加える（ALLOWED_ORIGINS は追加分があれば）
ORIGINS="https://$P.web.app,https://$P.firebaseapp.com${ALLOWED_ORIGINS:+,$ALLOWED_ORIGINS}"

run() { if [ -n "${DRY_RUN:-}" ]; then echo "+ $*"; else "$@"; fi; }
FIREBASE=(npx --yes firebase-tools)

echo "== 環境: $ENV_NAME / プロジェクト: $P / リージョン: $GCP_REGION =="
if [ "$ENV_NAME" = prod ] && [ -z "${DRY_RUN:-}" ]; then
  read -r -p "prod に配置します。プロジェクトID ($P) を入力してください: " ans
  [ "$ans" = "$P" ] || { echo "中止しました" >&2; exit 1; }
fi

echo "== 1/6 API の有効化 =="
run gcloud services enable --project "$P" run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com firestore.googleapis.com storage.googleapis.com \
  firebase.googleapis.com identitytoolkit.googleapis.com

echo "== 2/6 Firestore・バケット・サービスアカウント =="
if [ -n "${DRY_RUN:-}" ] || ! gcloud firestore databases describe --project "$P" >/dev/null 2>&1; then
  run gcloud firestore databases create --project "$P" --location "$GCP_REGION"
fi
if [ -n "${DRY_RUN:-}" ] || ! gcloud storage buckets describe "gs://$GCS_BUCKET" --project "$P" >/dev/null 2>&1; then
  run gcloud storage buckets create "gs://$GCS_BUCKET" --project "$P" --location "$GCP_REGION" \
    --uniform-bucket-level-access --public-access-prevention
fi
if [ -n "${DRY_RUN:-}" ] || ! gcloud iam service-accounts describe "$SA" --project "$P" >/dev/null 2>&1; then
  run gcloud iam service-accounts create "$SA_NAME" --project "$P" --display-name "lip-voice API"
fi
# 最小権限: Firestore の読み書きと、このバケットのオブジェクト操作だけ
run gcloud projects add-iam-policy-binding "$P" --member "serviceAccount:$SA" \
  --role roles/datastore.user --condition=None >/dev/null
run gcloud storage buckets add-iam-policy-binding "gs://$GCS_BUCKET" --project "$P" \
  --member "serviceAccount:$SA" --role roles/storage.objectAdmin >/dev/null

echo "== 3/6 API（Cloud Run）の配置 =="
ENV_YAML="$(mktemp)"; trap 'rm -f "$ENV_YAML"' EXIT
cat > "$ENV_YAML" <<YAML
GCP_PROJECT_ID: "$P"
GCS_BUCKET: "$GCS_BUCKET"
ALLOWED_ORIGINS: "$ORIGINS"
ALLOWED_EMAILS: "$ALLOWED_EMAILS"
YAML
run gcloud run deploy "$CLOUD_RUN_SERVICE" --project "$P" --region "$GCP_REGION" \
  --source "$ROOT/server" --service-account "$SA" --allow-unauthenticated \
  --max-instances 2 --concurrency 10 --memory 512Mi --timeout 60 \
  --env-vars-file "$ENV_YAML"
if [ -n "${DRY_RUN:-}" ]; then
  API_URL="https://<cloud-run-url>"
else
  API_URL="$(gcloud run services describe "$CLOUD_RUN_SERVICE" --project "$P" --region "$GCP_REGION" --format 'value(status.url)')"
fi

echo "== 4/6 セキュリティルールの配置 =="
(cd "$ROOT/infra" && run "${FIREBASE[@]}" deploy --project "$P" --only firestore:rules,storage)

echo "== 5/6 画面のビルド =="
(cd "$ROOT/web" && npm ci && VITE_API_BASE_URL="${VITE_API_BASE_URL:-$API_URL}" APP_ENV="$ENV_NAME" npm run build)

echo "== 6/6 画面（Hosting）の配置 =="
(cd "$ROOT/infra" && run "${FIREBASE[@]}" deploy --project "$P" --only hosting)

echo
echo "公開URL:   https://$P.web.app"
echo "API の URL: $API_URL"
echo "手動設定が必要な項目は README の「初回セットアップ」を参照"
