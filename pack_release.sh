#!/usr/bin/env bash
set -euo pipefail

# Vektorrazor Release-Pack-Script
# Erstellt Release-Archive fuer Windows AMD64 und Linux AMD64.
#
# Erwartete Dateien:
#   dist/Vektorrazor.exe   -> Windows AMD64 Build
#   dist/Vektorrazor       -> Linux AMD64 Build
#
# Ausgabe:
#   release/Vektorrazor-Windows-amd64-YYYY-MM-DD.zip
#   release/Vektorrazor-Linux-amd64-YYYY-MM-DD.tar.gz
#   release/SHA256SUMS-YYYY-MM-DD.txt
#
# Datum ist automatisch das heutige Datum.
# Fuer ein fixes Datum:
#   RELEASE_DATE=2026-05-26 ./pack_release.sh

APP_NAME="Vektorrazor"
RELEASE_DATE="${RELEASE_DATE:-$(date +%F)}"
ARCH="amd64"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$ROOT_DIR/dist"
RELEASE_DIR="$ROOT_DIR/release"

WIN_EXE="$DIST_DIR/${APP_NAME}.exe"
LINUX_BIN="$DIST_DIR/${APP_NAME}"

WIN_PACKAGE="${APP_NAME}-Windows-${ARCH}-${RELEASE_DATE}"
LINUX_PACKAGE="${APP_NAME}-Linux-${ARCH}-${RELEASE_DATE}"

mkdir -p "$RELEASE_DIR"

echo "== Vektorrazor Release packen =="
echo "Datum: $RELEASE_DATE"
echo "Architektur: $ARCH"
echo

if [[ ! -f "$WIN_EXE" ]]; then
    echo "FEHLER: Windows-Datei nicht gefunden:"
    echo "  $WIN_EXE"
    echo
    echo "Erwartet wird vorheriger Windows-Build, z. B.:"
    echo '  pyinstaller --onefile --windowed --clean --name Vektorrazor --icon assets\vektorrazor.ico --version-file version_info.txt --add-data "assets\vektorrazor.ico;assets" --add-data "assets\vektorrazor_icon.png;assets" main.py'
    exit 1
fi

if [[ ! -f "$LINUX_BIN" ]]; then
    echo "FEHLER: Linux-Datei nicht gefunden:"
    echo "  $LINUX_BIN"
    echo
    echo "Erwartet wird vorheriger Linux-Build, z. B. unter WSL/Ubuntu:"
    echo '  pyinstaller --onefile --windowed --clean --name Vektorrazor --add-data "assets/vektorrazor.ico:assets" --add-data "assets/vektorrazor_icon.png:assets" main.py'
    exit 1
fi

chmod +x "$LINUX_BIN"

rm -f "$RELEASE_DIR/${WIN_PACKAGE}.zip"
rm -f "$RELEASE_DIR/${LINUX_PACKAGE}.tar.gz"
rm -f "$RELEASE_DIR/SHA256SUMS-${RELEASE_DATE}.txt"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir -p "$TMP_DIR/$WIN_PACKAGE"
cp "$WIN_EXE" "$TMP_DIR/$WIN_PACKAGE/"
[[ -f "$ROOT_DIR/README.md" ]] && cp "$ROOT_DIR/README.md" "$TMP_DIR/$WIN_PACKAGE/"
[[ -f "$ROOT_DIR/README.de.md" ]] && cp "$ROOT_DIR/README.de.md" "$TMP_DIR/$WIN_PACKAGE/"
[[ -f "$ROOT_DIR/README.en.md" ]] && cp "$ROOT_DIR/README.en.md" "$TMP_DIR/$WIN_PACKAGE/"
[[ -f "$ROOT_DIR/LICENSE" ]] && cp "$ROOT_DIR/LICENSE" "$TMP_DIR/$WIN_PACKAGE/"
[[ -f "$ROOT_DIR/NOTICE.md" ]] && cp "$ROOT_DIR/NOTICE.md" "$TMP_DIR/$WIN_PACKAGE/"

(
    cd "$TMP_DIR"
    zip -qr "$RELEASE_DIR/${WIN_PACKAGE}.zip" "$WIN_PACKAGE"
)

mkdir -p "$TMP_DIR/$LINUX_PACKAGE"
cp "$LINUX_BIN" "$TMP_DIR/$LINUX_PACKAGE/"
[[ -f "$ROOT_DIR/README.md" ]] && cp "$ROOT_DIR/README.md" "$TMP_DIR/$LINUX_PACKAGE/"
[[ -f "$ROOT_DIR/README.de.md" ]] && cp "$ROOT_DIR/README.de.md" "$TMP_DIR/$LINUX_PACKAGE/"
[[ -f "$ROOT_DIR/README.en.md" ]] && cp "$ROOT_DIR/README.en.md" "$TMP_DIR/$LINUX_PACKAGE/"
[[ -f "$ROOT_DIR/LICENSE" ]] && cp "$ROOT_DIR/LICENSE" "$TMP_DIR/$LINUX_PACKAGE/"
[[ -f "$ROOT_DIR/NOTICE.md" ]] && cp "$ROOT_DIR/NOTICE.md" "$TMP_DIR/$LINUX_PACKAGE/"

(
    cd "$TMP_DIR"
    tar -czf "$RELEASE_DIR/${LINUX_PACKAGE}.tar.gz" "$LINUX_PACKAGE"
)

(
    cd "$RELEASE_DIR"
    sha256sum "${WIN_PACKAGE}.zip" "${LINUX_PACKAGE}.tar.gz" > "SHA256SUMS-${RELEASE_DATE}.txt"
)

echo
echo "Fertig:"
echo "  $RELEASE_DIR/${WIN_PACKAGE}.zip"
echo "  $RELEASE_DIR/${LINUX_PACKAGE}.tar.gz"
echo "  $RELEASE_DIR/SHA256SUMS-${RELEASE_DATE}.txt"
echo
echo "GitHub Release-Dateinamen:"
echo "  ${WIN_PACKAGE}.zip"
echo "  ${LINUX_PACKAGE}.tar.gz"
