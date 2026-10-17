#!/usr/bin/env bash
# 開発用のセットアップ（Mac / Linux）。Python の仮想環境を作り、依存を入れ、画面をビルドし、顔検出のモデルを取得する。
# 使い方: scripts/setup-dev.sh [--train]   （--train は学習用の torch も入れる）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/app"
python3 -m venv .venv
.venv/bin/pip install -q -U pip
EXTRAS="dev"; [ "${1:-}" = "--train" ] && EXTRAS="dev,train"
.venv/bin/pip install -q -e ".[${EXTRAS}]"
"$ROOT/scripts/build-ui.sh"
.venv/bin/lipvoice fetch-models
echo "完了。起動: app/.venv/bin/lipvoice run --open"
