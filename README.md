# lip-voice

口パク（声を出さない口の動き）をカメラで読み取り、登録した定型フレーズを判定して音声で再生するウェブアプリ。
声を失ったが口は動かせる人（気管切開後の ALS 患者など）が、自分のフレーズを自分専用のモデルで認識させることを目指す。

## 特徴
- ブラウザだけで動く。インストール不要
- Google ログイン。データ・モデル・フレーズは利用者ごとに完全分離
- 顔全体の映像はブラウザの外に出さない（口元の切り出しと特徴点のみ送信）
- 利用者自身のデータで学習し、口の動きの変化に合わせて再学習できる

## 状態
フェーズ1（検証版）の仕様策定が完了。実装はこれから。
詳細は [docs/spec.md](docs/spec.md)。

## 構成
```
web/      フロント（React + Vite + TypeScript、MediaPipe Face Landmarker）
server/   API（Python + FastAPI on Cloud Run）と学習コード（PyTorch）
infra/    Firebase / Cloud Run 設定、Firestore / Storage セキュリティルール
scripts/  配置スクリプト（dev / prod 切り替え）
docs/     仕様書
```

## 初回セットアップ（dev）
前提: Node 22.12 以上、Python 3.12 以上、`gcloud` と `firebase-tools`（`npx` で可）。

1. 専用の GCP プロジェクトを作り、課金を有効にし、予算アラートを月1,000円で設定する
2. [Firebase コンソール](https://console.firebase.google.com/)でそのプロジェクトに Firebase を追加し、Web アプリを登録して設定値を控える
3. Authentication → Sign-in method で **Google を有効化**（サポートメールを設定）。OAuth 同意画面は Firebase が作る。外部公開の「テスト」状態なら、自分のアカウントをテストユーザーに追加する
4. Authentication → Settings → 承認済みドメインに `<project>.web.app` と `<project>.firebaseapp.com` があることを確認（通常は自動）
5. `.env.dev.example` をコピーして `.env.dev` を作り、値を埋める（`ALLOWED_EMAILS` に自分のメールを入れる）
6. `gcloud auth login` と `firebase login` を済ませ、`scripts/deploy.sh dev` を実行
7. 自分で一度ログインしてアカウントができたら、Authentication → Settings → ユーザーの操作 →
   **「作成（登録）を有効にする」をオフ**にする（第三者のアカウント作成を防ぐ。サーバー側も `ALLOWED_EMAILS` で絞っている）

Firestore とバケットのリージョンは作成後に変更できない（既定は `asia-northeast1`）。

## ローカル開発
```
# 1. エミュレータ（Auth / Firestore / Storage）
cd infra && npx firebase-tools emulators:start --only auth,firestore,storage --project demo-lipvoice

# 2. API
cd server && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8081 STORAGE_EMULATOR_HOST=http://127.0.0.1:9199 \
       FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099 GCP_PROJECT_ID=demo-lipvoice \
       GCS_BUCKET=demo-lipvoice.appspot.com ALLOWED_ORIGINS=http://localhost:5173 ALLOWED_EMAILS=you@example.com
.venv/bin/uvicorn main:app --port 8000

# 3. 画面（.env.emulator に VITE_* を書く。git 管理外）
cd web && npm ci && npm run dev:emulator
```
テスト: `server/` で `pytest`、`web/` で `npm test`、`infra/rules-test/` で `npm test`（エミュレータ起動中）。

## 安全上の前提
- 緊急の呼び出しはこの仕組みに頼らない
- 既存の意思伝達装置は置き換えず併用する
- 自動再生は取り違えが少ないと確認できるまで OFF

## ライセンス
MIT
