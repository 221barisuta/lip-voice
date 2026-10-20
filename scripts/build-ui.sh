#!/usr/bin/env bash
# 画面（React）をビルドして app/lipvoice/static に出力する。Node 22 以上が必要。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/web"
# 旧版（ブラウザ内で顔検出していた時代）の名残。残っていると、画面と一緒に配られる（約 44MB）
rm -rf public/mediapipe
npm ci
npm run build
