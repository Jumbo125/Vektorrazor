#!/usr/bin/env bash
set -euo pipefail

# Vektorrazor Release-Pack-Script
# Erstellt Release-Archive fuer Windows AMD64, Linux AMD64 und macOS.
#
# Erwartete Dateien/Ordner:
#   dist/Vektorrazor.exe                         -> Windows AMD64 Build
#   dist/Vektorrazor                             -> Linux AMD64 Build
#   dist/*mac*.zip / dist/*macos*.zip            -> macOS Build-ZIP aus GitHub Actions
#
#   vektorrazor_config/lang/                     -> Sprachdateien
#   vektorrazor_config/real_esrgan/models/       -> Real-ESRGAN Models, fuer alle Releases
#   vektorrazor_config/real_esrgan/windows/      -> Real-ESRGAN Windows Vulkan Binary
#   vektorrazor_config/real_esrgan/linux/        -> Real-ESRGAN Linux Vulkan Binary
#   vektorrazor_config/real_esrgan/mac/          -> Real-ESRGAN macOS Vulkan Binary
#
# Ausgabe:
#   release/Vektorrazor-Windows-amd64-YYYY-MM-DD.zip
#   release/Vektorrazor-Linux-amd64-YYYY-MM-DD.tar.gz
#   release/Vektorrazor-macOS-amd64-YYYY-MM-DD.zip
#   release/SHA256SUMS-YYYY-MM-DD.txt
#
# Datum ist automatisch das heutige Datum.
# Fuer ein fixes Datum:
#   RELEASE_DATE=2026-05-26 ./pack_release.sh
#
# Falls mehrere macOS-ZIPs in dist/ liegen:
#   MAC_ZIP="dist/DEIN-MAC-BUILD.zip" ./pack_release.sh
#
# Falls macOS ARM64 gebaut wurde:
#   MAC_ARCH=arm64 ./pack_release.sh

APP_NAME="Vektorrazor"
RELEASE_DATE="${RELEASE_DATE:-$(date +%F)}"

WIN_ARCH="${WIN_ARCH:-amd64}"
LINUX_ARCH="${LINUX_ARCH:-amd64}"
MAC_ARCH="${MAC_ARCH:-amd64}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$ROOT_DIR/dist"
RELEASE_DIR="$ROOT_DIR/release"

CONFIG_DIR="$ROOT_DIR/vektorrazor_config"
LANG_DIR="$CONFIG_DIR/lang"

REAL_ESRGAN_DIR="$CONFIG_DIR/real_esrgan"
REAL_ESRGAN_MODELS_DIR="$REAL_ESRGAN_DIR/models"
REAL_ESRGAN_WIN_DIR="$REAL_ESRGAN_DIR/windows"
REAL_ESRGAN_LINUX_DIR="$REAL_ESRGAN_DIR/linux"
REAL_ESRGAN_MAC_DIR="$REAL_ESRGAN_DIR/mac"

WIN_EXE="$DIST_DIR/${APP_NAME}.exe"
LINUX_BIN="$DIST_DIR/${APP_NAME}"

WIN_PACKAGE="${APP_NAME}-Windows-${WIN_ARCH}-${RELEASE_DATE}"
LINUX_PACKAGE="${APP_NAME}-Linux-${LINUX_ARCH}-${RELEASE_DATE}"
MAC_PACKAGE="${APP_NAME}-macOS-${MAC_ARCH}-${RELEASE_DATE}"

mkdir -p "$RELEASE_DIR"

echo "== Vektorrazor Release packen =="
echo "Datum:      $RELEASE_DATE"
echo "Windows:    $WIN_ARCH"
echo "Linux:      $LINUX_ARCH"
echo "macOS:      $MAC_ARCH"
echo

require_file() {
    local file="$1"
    local message="$2"

    if [[ ! -f "$file" ]]; then
        echo "FEHLER: Datei nicht gefunden:"
        echo "  $file"
        echo
        echo "$message"
        exit 1
    fi
}

require_dir() {
    local dir="$1"
    local message="$2"

    if [[ ! -d "$dir" ]]; then
        echo "FEHLER: Ordner nicht gefunden:"
        echo "  $dir"
        echo
        echo "$message"
        exit 1
    fi
}

find_mac_zip() {
    if [[ -n "${MAC_ZIP:-}" ]]; then
        local mac_zip_path="$MAC_ZIP"

        if [[ "$mac_zip_path" != /* ]]; then
            mac_zip_path="$ROOT_DIR/$mac_zip_path"
        fi

        require_file "$mac_zip_path" "MAC_ZIP zeigt auf keine gueltige ZIP-Datei."
        echo "$mac_zip_path"
        return
    fi

    mapfile -t candidates < <(
        find "$DIST_DIR" -maxdepth 1 -type f \
            \( -iname "*mac*.zip" -o -iname "*macos*.zip" -o -iname "*darwin*.zip" \) \
            | sort
    )

    if [[ "${#candidates[@]}" -eq 0 ]]; then
        echo "FEHLER: Keine macOS-ZIP in dist/ gefunden." >&2
        echo >&2
        echo "Lege den macOS-Build aus GitHub Actions z. B. hier ab:" >&2
        echo "  dist/Vektorrazor-macOS-${MAC_ARCH}.zip" >&2
        echo >&2
        echo "Oder gib die Datei explizit an:" >&2
        echo '  MAC_ZIP="dist/DEIN-MAC-BUILD.zip" ./pack_release.sh' >&2
        exit 1
    fi

    if [[ "${#candidates[@]}" -gt 1 ]]; then
        echo "FEHLER: Mehrere moegliche macOS-ZIPs in dist/ gefunden:" >&2
        printf '  %s\n' "${candidates[@]}" >&2
        echo >&2
        echo "Bitte eindeutig angeben, z. B.:" >&2
        echo '  MAC_ZIP="dist/DEIN-MAC-BUILD.zip" ./pack_release.sh' >&2
        exit 1
    fi

    echo "${candidates[0]}"
}

copy_common_files() {
    local target_dir="$1"

    [[ -f "$ROOT_DIR/README.md" ]] && cp "$ROOT_DIR/README.md" "$target_dir/"
    [[ -f "$ROOT_DIR/README.de.md" ]] && cp "$ROOT_DIR/README.de.md" "$target_dir/"
    [[ -f "$ROOT_DIR/README.en.md" ]] && cp "$ROOT_DIR/README.en.md" "$target_dir/"
    [[ -f "$ROOT_DIR/LICENSE" ]] && cp "$ROOT_DIR/LICENSE" "$target_dir/"
    [[ -f "$ROOT_DIR/NOTICE.md" ]] && cp "$ROOT_DIR/NOTICE.md" "$target_dir/"
    [[ -f "$ROOT_DIR/AUTHORS.md" ]] && cp "$ROOT_DIR/AUTHORS.md" "$target_dir/"

    if [[ -d "$LANG_DIR" ]]; then
        mkdir -p "$target_dir/vektorrazor_config"
        cp -a "$LANG_DIR" "$target_dir/vektorrazor_config/"
    fi
}

copy_real_esrgan_files() {
    local target_dir="$1"
    local platform="$2"

    require_dir "$REAL_ESRGAN_MODELS_DIR" "Die Models muessen fuer alle Releases vorhanden sein."

    mkdir -p "$target_dir/vektorrazor_config/real_esrgan"

    echo "  + Real-ESRGAN models"
    cp -a "$REAL_ESRGAN_MODELS_DIR" "$target_dir/vektorrazor_config/real_esrgan/"

    case "$platform" in
        windows)
            require_dir "$REAL_ESRGAN_WIN_DIR" "Windows Real-ESRGAN Ordner fehlt."
            echo "  + Real-ESRGAN windows"
            cp -a "$REAL_ESRGAN_WIN_DIR" "$target_dir/vektorrazor_config/real_esrgan/windows"
            ;;

        linux)
            require_dir "$REAL_ESRGAN_LINUX_DIR" "Linux Real-ESRGAN Ordner fehlt."
            echo "  + Real-ESRGAN linux"
            cp -a "$REAL_ESRGAN_LINUX_DIR" "$target_dir/vektorrazor_config/real_esrgan/linux"

            if [[ -f "$target_dir/vektorrazor_config/real_esrgan/linux/realesrgan-ncnn-vulkan" ]]; then
                chmod +x "$target_dir/vektorrazor_config/real_esrgan/linux/realesrgan-ncnn-vulkan"
            fi
            ;;

        mac)
            require_dir "$REAL_ESRGAN_MAC_DIR" "macOS Real-ESRGAN Ordner fehlt."
            echo "  + Real-ESRGAN mac"
            cp -a "$REAL_ESRGAN_MAC_DIR" "$target_dir/vektorrazor_config/real_esrgan/mac"

            if [[ -f "$target_dir/vektorrazor_config/real_esrgan/mac/realesrgan-ncnn-vulkan" ]]; then
                chmod +x "$target_dir/vektorrazor_config/real_esrgan/mac/realesrgan-ncnn-vulkan"
            fi
            ;;

        *)
            echo "FEHLER: Unbekannte Plattform fuer Real-ESRGAN: $platform"
            exit 1
            ;;
    esac

    # Drittanbieter-Lizenzen/Notices mitnehmen, falls vorhanden.
    # Wichtig fuer Real-ESRGAN / ncnn-vulkan / Models.
    find "$REAL_ESRGAN_DIR" -maxdepth 1 -type f \
        \( -iname "LICENSE*" -o -iname "NOTICE*" -o -iname "THIRD_PARTY*" -o -iname "README*" \) \
        -exec cp {} "$target_dir/vektorrazor_config/real_esrgan/" \;
}

require_file "$WIN_EXE" "Erwartet wird vorheriger Windows-Build, z. B. mit PyInstaller."
require_file "$LINUX_BIN" "Erwartet wird vorheriger Linux-Build, z. B. unter WSL/Ubuntu."
require_dir "$REAL_ESRGAN_MODELS_DIR" "Fehlt: vektorrazor_config/real_esrgan/models"
require_dir "$REAL_ESRGAN_WIN_DIR" "Fehlt: vektorrazor_config/real_esrgan/windows"
require_dir "$REAL_ESRGAN_LINUX_DIR" "Fehlt: vektorrazor_config/real_esrgan/linux"
require_dir "$REAL_ESRGAN_MAC_DIR" "Fehlt: vektorrazor_config/real_esrgan/mac"

MAC_SOURCE_ZIP="$(find_mac_zip)"

chmod +x "$LINUX_BIN"

rm -f "$RELEASE_DIR/${WIN_PACKAGE}.zip"
rm -f "$RELEASE_DIR/${LINUX_PACKAGE}.tar.gz"
rm -f "$RELEASE_DIR/${MAC_PACKAGE}.zip"
rm -f "$RELEASE_DIR/SHA256SUMS-${RELEASE_DATE}.txt"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Windows Release packen..."
mkdir -p "$TMP_DIR/$WIN_PACKAGE"
cp "$WIN_EXE" "$TMP_DIR/$WIN_PACKAGE/"
copy_common_files "$TMP_DIR/$WIN_PACKAGE"
copy_real_esrgan_files "$TMP_DIR/$WIN_PACKAGE" "windows"

(
    cd "$TMP_DIR"
    zip -qr "$RELEASE_DIR/${WIN_PACKAGE}.zip" "$WIN_PACKAGE"
)

echo
echo "Linux Release packen..."
mkdir -p "$TMP_DIR/$LINUX_PACKAGE"
cp "$LINUX_BIN" "$TMP_DIR/$LINUX_PACKAGE/"
chmod +x "$TMP_DIR/$LINUX_PACKAGE/$APP_NAME"
copy_common_files "$TMP_DIR/$LINUX_PACKAGE"
copy_real_esrgan_files "$TMP_DIR/$LINUX_PACKAGE" "linux"

(
    cd "$TMP_DIR"
    tar -czf "$RELEASE_DIR/${LINUX_PACKAGE}.tar.gz" "$LINUX_PACKAGE"
)

echo
echo "macOS Release packen..."
echo "  Quelle: $MAC_SOURCE_ZIP"

MAC_UNPACK_DIR="$TMP_DIR/mac_unpacked"
mkdir -p "$MAC_UNPACK_DIR"
unzip -q "$MAC_SOURCE_ZIP" -d "$MAC_UNPACK_DIR"

mkdir -p "$TMP_DIR/$MAC_PACKAGE"

# macOS-ZIP normalisieren:
# - Wenn ZIP einen Root-Ordner enthaelt, wird dessen Inhalt uebernommen.
# - Wenn ZIP direkt Vektorrazor.app enthaelt, bleibt die .app erhalten.
shopt -s dotglob nullglob
mac_entries=("$MAC_UNPACK_DIR"/*)

if [[ "${#mac_entries[@]}" -eq 1 && -d "${mac_entries[0]}" && "$(basename "${mac_entries[0]}")" != *.app ]]; then
    cp -a "${mac_entries[0]}"/. "$TMP_DIR/$MAC_PACKAGE/"
else
    cp -a "$MAC_UNPACK_DIR"/. "$TMP_DIR/$MAC_PACKAGE/"
fi

shopt -u dotglob nullglob

copy_common_files "$TMP_DIR/$MAC_PACKAGE"
copy_real_esrgan_files "$TMP_DIR/$MAC_PACKAGE" "mac"

# Falls eine .app enthalten ist, MacOS-Binaries vorsichtshalber ausfuehrbar machen.
find "$TMP_DIR/$MAC_PACKAGE" -path "*/Contents/MacOS/*" -type f -exec chmod +x {} \; 2>/dev/null || true

(
    cd "$TMP_DIR"
    zip -qr "$RELEASE_DIR/${MAC_PACKAGE}.zip" "$MAC_PACKAGE"
)

echo
echo "SHA256SUMS erzeugen..."

(
    cd "$RELEASE_DIR"
    sha256sum \
        "${WIN_PACKAGE}.zip" \
        "${LINUX_PACKAGE}.tar.gz" \
        "${MAC_PACKAGE}.zip" \
        > "SHA256SUMS-${RELEASE_DATE}.txt"
)

echo
echo "Fertig:"
echo "  $RELEASE_DIR/${WIN_PACKAGE}.zip"
echo "  $RELEASE_DIR/${LINUX_PACKAGE}.tar.gz"
echo "  $RELEASE_DIR/${MAC_PACKAGE}.zip"
echo "  $RELEASE_DIR/SHA256SUMS-${RELEASE_DATE}.txt"

echo
echo "GitHub Release-Dateinamen:"
echo "  ${WIN_PACKAGE}.zip"
echo "  ${LINUX_PACKAGE}.tar.gz"
echo "  ${MAC_PACKAGE}.zip"
echo "  SHA256SUMS-${RELEASE_DATE}.txt"