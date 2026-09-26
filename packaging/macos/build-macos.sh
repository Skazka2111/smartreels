#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"
ARCH="$(uname -m)"
case "$ARCH" in arm64) LABEL="ARM64" ;; x86_64) LABEL="Intel" ;; *) exit 1 ;; esac
VENV="$ROOT/.macos-build-venv-$ARCH"
[[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install ".[build]"
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  command -v brew >/dev/null || { echo "Install Homebrew and FFmpeg"; exit 1; }
  brew install ffmpeg
fi
export SMART_REELS_FFMPEG="$(command -v ffmpeg)"
export SMART_REELS_FFPROBE="$(command -v ffprobe)"
BUILD="$ROOT/build/macos/$ARCH"
DIST="$ROOT/artifacts/macos/dist-$ARCH"
PACKAGE="$ROOT/artifacts/macos/Smart Reels Studio macOS $LABEL"
ZIP="$ROOT/artifacts/macos/Smart_Reels_Studio_macOS_${LABEL}_v010.zip"
rm -rf "$BUILD" "$DIST" "$PACKAGE" "$ZIP"
mkdir -p "$BUILD" "$DIST" "$PACKAGE"
"$VENV/bin/python" -m PyInstaller --noconfirm --clean \
  --workpath "$BUILD" --distpath "$DIST" \
  "$ROOT/packaging/macos/SmartReelsStudio.spec"
APP="$DIST/Smart Reels Studio.app"
[[ -d "$APP" ]] || { echo "Application bundle was not created"; exit 1; }
codesign --force --deep --sign - "$APP"
cp -R "$APP" "$PACKAGE/"
cp -R "$ROOT/portable_template/." "$PACKAGE/"
mkdir -p "$PACKAGE/Smart_Reels_Project/results"
ditto -c -k --sequesterRsrc --keepParent "$PACKAGE" "$ZIP"
echo "Build completed: $ZIP"

