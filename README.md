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

## セットアップ（概要）
1. GCP プロジェクトを専用に作り、Firebase を有効化
2. `.env.dev.example` をコピーして `.env.dev` を作り、値を埋める
3. `scripts/deploy.sh dev`

秘密の値は `.env.*` にのみ置く。リポジトリには入れない。

## 安全上の前提
- 緊急の呼び出しはこの仕組みに頼らない
- 既存の意思伝達装置は置き換えず併用する
- 自動再生は取り違えが少ないと確認できるまで OFF

## ライセンス
MIT
