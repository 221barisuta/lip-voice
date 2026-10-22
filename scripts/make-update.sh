#!/usr/bin/env bash
# コードだけの更新パッケージ（1MB 未満）を作る。患者さんの PC に導入済みの LipVoice に、lipvoice の wheel だけを入れ替える。
# 使い方: scripts/make-update.sh [出力先フォルダ]   （既定: release/）。依存の wheel やインストーラは含まない。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/release}"
VERSION="$(grep -m1 '^version' "$ROOT/app/pyproject.toml" | sed 's/.*"\(.*\)".*/\1/')"
PKG="lipvoice-update-${VERSION}"
STAGE="$OUT/$PKG"
PIP="$ROOT/app/.venv/bin/pip"
[ -x "$PIP" ] || { echo "先に scripts/setup-dev.sh を実行してください"; exit 1; }
rm -rf "$STAGE"; mkdir -p "$STAGE"
"$ROOT/scripts/build-ui.sh"
rm -rf "$ROOT/app/build" "$ROOT"/app/*.egg-info
"$PIP" wheel -q --no-deps -w "$STAGE" "$ROOT/app"
KB=$(du -k "$STAGE"/lipvoice-*.whl | cut -f1)
[ "$KB" -lt 3072 ] || { echo "wheel が大きすぎます（${KB}KB）"; exit 1; }
for f in "$ROOT"/scripts/windows/*.cmd; do
  [ "$(basename "$f")" = install.cmd ] || sed 's/\r$//; s/$/\r/' "$f" > "$STAGE/$(basename "$f")"    # .cmd は CRLF（install.cmd は含めない）
done
( cd "$OUT" && rm -f "$PKG.zip" && zip -qr "$PKG.zip" "$PKG" )
echo "完成: $OUT/$PKG.zip（$(du -h "$OUT/$PKG.zip" | cut -f1)）"
