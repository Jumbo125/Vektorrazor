#!/usr/bin/env bash
# Build and prepare a GitHub Release asset for Linux AMD64.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

APP_NAME="Vektorrazor"
PLATFORM="Linux-amd64"
VERSION="$(tr -d '\r\n' < VERSION)"

if [[ ! "$VERSION" =~ ^[0-9]+(\.[0-9]+){1,3}([-+][0-9A-Za-z.-]+)?$ ]]; then
    echo "FEHLER: VERSION enthaelt keine gueltige Versionsnummer: '$VERSION'" >&2
    exit 1
fi

ASSET_BASENAME="${APP_NAME}-${VERSION}-${PLATFORM}"
STAGE_DIR="build/release/${ASSET_BASENAME}"
RELEASE_DIR="release"
ARCHIVE="${RELEASE_DIR}/${ASSET_BASENAME}.tar.gz"
CHECKSUM="${RELEASE_DIR}/${ASSET_BASENAME}.tar.gz.sha256"

rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR" "$RELEASE_DIR"

python -m PyInstaller \
    --onefile \
    --windowed \
    --clean \
    --name "$APP_NAME" \
    --hidden-import=PIL._tkinter_finder \
    --hidden-import=PIL.ImageTk \
    --collect-submodules=PIL \
    --add-data "assets/vektorrazor_icon.png:assets" \
    --add-data "assets/vektorrazor.ico:assets" \
    main.py

install -m 755 "dist/${APP_NAME}" "$STAGE_DIR/${APP_NAME}"
for file in README.md README.de.md README.en.md LICENSE NOTICE.md AUTHORS.md; do
    [[ -f "$file" ]] && install -m 644 "$file" "$STAGE_DIR/"
done

rm -f "$ARCHIVE" "$CHECKSUM"
tar -C "$(dirname "$STAGE_DIR")" -czf "$ARCHIVE" "$ASSET_BASENAME"
(
    cd "$RELEASE_DIR"
    sha256sum "${ASSET_BASENAME}.tar.gz" > "${ASSET_BASENAME}.tar.gz.sha256"
)

echo "GitHub-Release-Artefakte erstellt:"
echo "  $ARCHIVE"
echo "  $CHECKSUM"
