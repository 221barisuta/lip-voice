#!/usr/bin/env bash
# Windows 用の導入パッケージ（zip）を Mac / Linux で作る。患者さんの PC には、この zip を USB で持っていく。
# 使い方: scripts/make-release.sh [出力先フォルダ]   （既定: release/）
#   PYTHON_VERSION=3.13.16 で Windows に入れる Python を変えられる（3.12 以上。依存の wheel は cp313 用）。
#   インターネットから取る物（Python のインストーラ、VC++ ランタイム、顔検出モデル、Windows 用の wheel）は release-cache/ に溜める。
#   取得できない時は、同じ名前のファイルを release-cache/ に手で置けばよい。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/release}"
CACHE="$ROOT/release-cache"
PYTHON_VERSION="${PYTHON_VERSION:-3.13.16}"
PY_TAG="cp$(echo "$PYTHON_VERSION" | awk -F. '{print $1$2}')"
PY_EXE="python-${PYTHON_VERSION}-amd64.exe"
VERSION="$(grep -m1 '^version' "$ROOT/app/pyproject.toml" | sed 's/.*"\(.*\)".*/\1/')"
PKG="lipvoice-win-${VERSION}"
STAGE="$OUT/$PKG"
PIP="$ROOT/app/.venv/bin/pip"
[ -x "$PIP" ] || { echo "先に scripts/setup-dev.sh を実行してください（app/.venv が必要）"; exit 1; }

mkdir -p "$CACHE" "$OUT"
rm -rf "$STAGE"
mkdir -p "$STAGE/vendor" "$STAGE/wheels" "$STAGE/profiles" "$STAGE/docs"

fetch() {  # fetch <url> <ファイル名>
  [ -s "$CACHE/$2" ] || curl -fL --retry 3 -o "$CACHE/$2" "$1" || { rm -f "$CACHE/$2"; echo "取得できません: $1 （$CACHE/$2 に手で置いてください）"; exit 1; }
  cp "$CACHE/$2" "$STAGE/vendor/$2"
}

echo "== 画面をビルド"
"$ROOT/scripts/build-ui.sh"

echo "== lipvoice の wheel（純 Python）"
"$PIP" wheel -q --no-deps -w "$STAGE/wheels" "$ROOT/app"

echo "== Windows 用の依存の wheel（${PY_TAG}, win_amd64）"
# colorama は click の Windows 専用の依存（この Mac では自動で選ばれないので明示する）
"$PIP" download -q --only-binary=:all: --platform win_amd64 --python-version "${PYTHON_VERSION%.*}" --implementation cp \
  --abi "$PY_TAG" --abi abi3 --abi none -c "$ROOT/app/constraints.txt" -d "$STAGE/wheels" \
  numpy mediapipe av fastapi uvicorn python-multipart tzdata colorama

echo "== インストーラとモデル"
fetch "https://www.python.org/ftp/python/${PYTHON_VERSION}/${PY_EXE}" "$PY_EXE"
fetch "https://aka.ms/vs/17/release/vc_redist.x64.exe" "vc_redist.x64.exe"
fetch "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" "face_landmarker.task"

echo "== スクリプト・設定・手順書"
cp "$ROOT"/scripts/windows/install-windows.ps1 "$STAGE/"
for f in "$ROOT"/scripts/windows/*.cmd; do sed 's/\r$//; s/$/\r/' "$f" > "$STAGE/$(basename "$f")"; done   # .cmd は CRLF にする
cp "$ROOT/app/profiles/patient.config.json" "$STAGE/profiles/"
cp "$ROOT/docs/day0-checklist.md" "$STAGE/docs/"

echo "== ハッシュ（導入時に USB のコピー誤りを検出する）"
( cd "$STAGE" && find . -type f ! -name MANIFEST.sha256 | sed 's|^\./||' | sort | while read -r f; do
    if command -v sha256sum >/dev/null; then h=$(sha256sum "$f" | cut -d' ' -f1); else h=$(shasum -a 256 "$f" | cut -d' ' -f1); fi
    echo "$h  $f"
  done > MANIFEST.sha256 )

( cd "$OUT" && rm -f "$PKG.zip" && zip -qr "$PKG.zip" "$PKG" )
echo "完成: $OUT/$PKG.zip（$(du -h "$OUT/$PKG.zip" | cut -f1)）"
