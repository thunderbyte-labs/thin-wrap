#!/bin/sh
# Universal installer for thin-wrap (Linux & macOS)
# XDG mode only (modern default)
# POSIX-compliant, no bash required
# Usage:
#   curl -fsSL .../install.sh | sh
#   curl -fsSL .../install.sh | sh -s -- --force
#   THIN_WRAP_VERSION=v0.1.6 curl -fsSL .../install.sh | sh
#
# On macOS, Homebrew is the recommended install path:
#   brew install thunderbyte-labs/tap/thin-wrap
#   brew upgrade thin-wrap
#
# This script tracks the latest *stable* GitHub release (pre-releases are
# ignored). Pin a tag with THIN_WRAP_VERSION or --tag=vX.Y.Z.

set -e

REPO="thunderbyte-labs/thin-wrap"
API_BASE="https://api.github.com/repos/${REPO}"

FORCE=0
PINNED_TAG="${THIN_WRAP_VERSION:-}"

for arg in "$@"; do
    case "$arg" in
        --force|-f) FORCE=1 ;;
        --tag=*) PINNED_TAG="${arg#--tag=}" ;;
        --help|-h)
            echo "Usage: install.sh [--force] [--tag=vX.Y.Z]"
            echo "  --force          Reinstall even if this version is already present"
            echo "  --tag=vX.Y.Z     Install a specific release instead of latest stable"
            echo "Env: FORCE=1, THIN_WRAP_VERSION=vX.Y.Z"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $arg"
            echo "Usage: install.sh [--force] [--tag=vX.Y.Z]"
            exit 1
            ;;
    esac
done

if [ "${FORCE}" = "1" ] || [ "${FORCE}" = "true" ]; then
    FORCE=1
fi

# Block root execution
if [ "$(id -u)" -eq 0 ]; then
    echo "ERROR: thin-wrap refuses to install as root."
    echo "Run without sudo to install to ~/.local/"
    exit 1
fi

# Platform detection
OS="$(uname -s)"
case "$OS" in
    Linux*)  PLATFORM="Linux" ;;
    Darwin*) PLATFORM="Darwin" ;;
    *) echo "ERROR: Unsupported OS: $OS"; exit 1 ;;
esac

# Architecture detection
ARCH_RAW="$(uname -m)"
case "$ARCH_RAW" in
    x86_64|amd64) ARCH="x86_64" ;;
    aarch64)      ARCH="aarch64" ;;
    arm64)        ARCH="arm64" ;;
    *)
        echo "ERROR: Unsupported architecture: $ARCH_RAW"
        echo "Supported: x86_64, aarch64, arm64"
        echo "Please download manually from: https://github.com/${REPO}/releases"
        exit 1
        ;;
esac

# glibc compatibility check on Linux
if [ "$PLATFORM" = "Linux" ]; then
    if command -v ldd >/dev/null 2>&1; then
        GLIBC_VERSION=$(ldd --version 2>/dev/null | head -n 1 | grep -oE '[0-9]+\.[0-9]+' | head -n 1)
        if [ -n "$GLIBC_VERSION" ]; then
            MAJOR=$(echo "$GLIBC_VERSION" | cut -d. -f1)
            MINOR=$(echo "$GLIBC_VERSION" | cut -d. -f2)
            if [ "$MAJOR" -lt 2 ] || { [ "$MAJOR" -eq 2 ] && [ "$MINOR" -lt 35 ]; }; then
                echo "WARNING: Your system's glibc version is $GLIBC_VERSION."
                echo "The pre-built binary requires glibc 2.35+."
                echo "It may fail with a library version error (GLIBC_2.xx not found)."
                echo "Recommended actions:"
                echo "  - Upgrade your distribution (Ubuntu 22.04+ or equivalent), or"
                echo "  - Build from source on your system (see README)."
                echo ""
            fi
        fi
    fi
fi

ARCHIVE="thin-wrap-${PLATFORM}-${ARCH}.zip"
TMPDIR="${TMPDIR:-/tmp}/thin-wrap-install-$$"
PREFIX="${HOME}/.local"
LIBDIR="${PREFIX}/lib"
BINDIR="${PREFIX}/bin"
CONFIG_DIR_XDG="${XDG_CONFIG_HOME:-${HOME}/.config}/thin-wrap"
APP_DIR="${LIBDIR}/thin-wrap"
BACKUP_DIR="${APP_DIR}.bak"
CONFIG_MODE="xdg"
CONFIG_TARGET="$CONFIG_DIR_XDG"

http_get() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$1"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- "$1"
    else
        echo "ERROR: Neither curl nor wget found. Please install one of them." >&2
        return 1
    fi
}

http_download() {
    DEST="$1"
    URL="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsL -o "$DEST" "$URL"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$DEST" "$URL"
    else
        echo "ERROR: Neither curl nor wget found. Please install one of them."
        return 1
    fi
}

parse_release_json() {
    ARCHIVE_NAME="$1"
    if command -v python3 >/dev/null 2>&1; then
        printf '%s' "$JSON" | ARCHIVE_NAME="$ARCHIVE_NAME" python3 -c '
import json, os, sys
r = json.load(sys.stdin)
tag = r.get("tag_name") or ""
want = os.environ["ARCHIVE_NAME"]
digest = ""
url = ""
for asset in r.get("assets") or []:
    if asset.get("name") == want:
        raw = asset.get("digest") or ""
        if raw.startswith("sha256:"):
            digest = raw.split(":", 1)[1]
        url = asset.get("browser_download_url") or ""
        break
sys.stdout.write(tag + "\n" + digest + "\n" + url + "\n")
'
        return
    fi
    echo "$JSON" | grep '"tag_name":' | sed -E 's/.*"tag_name": "([^"]+)".*/\1/' | head -n 1
    echo "$JSON" | grep -F "\"name\": \"${ARCHIVE_NAME}\"" >/dev/null 2>&1 || true
    echo "$JSON" | grep '"digest":' | head -n 1 | sed -E 's/.*sha256:([0-9a-f]+).*/\1/'
    echo "https://github.com/${REPO}/releases/download/PLACEHOLDER/${ARCHIVE_NAME}"
}

file_sha256() {
    FILE="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$FILE" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$FILE" | awk '{print $1}'
    else
        echo ""
    fi
}

restore_backup() {
    echo "Update failed, restoring the previous installation..."
    if [ -d "$BACKUP_DIR" ]; then
        rm -rf "$APP_DIR"
        mv "$BACKUP_DIR" "$APP_DIR"
        echo "Restored ${APP_DIR} from ${BACKUP_DIR}"
    else
        echo "ERROR: No backup found at ${BACKUP_DIR}"
    fi
}

# Fetch release metadata (latest stable, or a pinned tag)
if [ -n "$PINNED_TAG" ]; then
    case "$PINNED_TAG" in
        v*) TAG_PATH="$PINNED_TAG" ;;
        *)  TAG_PATH="v${PINNED_TAG}" ;;
    esac
    API_URL="${API_BASE}/releases/tags/${TAG_PATH}"
else
    API_URL="${API_BASE}/releases/latest"
fi

JSON=$(http_get "$API_URL" 2>/dev/null) || JSON=""
if [ -z "$JSON" ]; then
    echo "ERROR: Failed to fetch release info from GitHub API."
    echo "This may be due to API rate limits (60 requests/hour per IP)."
    echo "Please try again later or download manually from:"
    echo "  https://github.com/${REPO}/releases"
    exit 1
fi

PARSE_OUT=$(parse_release_json "$ARCHIVE") || true
VERSION=$(printf '%s\n' "$PARSE_OUT" | sed -n '1p')
EXPECTED_SHA=$(printf '%s\n' "$PARSE_OUT" | sed -n '2p')
DOWNLOAD_URL=$(printf '%s\n' "$PARSE_OUT" | sed -n '3p')

if [ -z "$VERSION" ]; then
    echo "ERROR: Could not parse release tag from GitHub API."
    exit 1
fi

if [ -z "$DOWNLOAD_URL" ] || echo "$DOWNLOAD_URL" | grep -q PLACEHOLDER; then
    DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${VERSION}/${ARCHIVE}"
fi

CURRENT_VERSION="unknown"
if [ -f "${APP_DIR}/.version" ]; then
    CURRENT_VERSION=$(cat "${APP_DIR}/.version" 2>/dev/null || echo "unknown")
fi

EXISTING=0
if [ -d "$APP_DIR" ] && [ -f "${APP_DIR}/thin-wrap" ]; then
    EXISTING=1
fi

echo "=== thin-wrap ${VERSION} Installer (${PLATFORM}/${ARCH}) ==="

if [ "$EXISTING" -eq 1 ] && [ "$CURRENT_VERSION" = "$VERSION" ] && [ "$FORCE" -eq 0 ]; then
    echo "thin-wrap ${VERSION} is already installed and up to date."
    echo "Re-run with --force (or FORCE=1) to reinstall."
    exit 0
fi

if [ "$EXISTING" -eq 1 ]; then
    echo "Updating: ${CURRENT_VERSION} -> ${VERSION}"
else
    echo "Installing ${VERSION}"
fi

if command -v pgrep >/dev/null 2>&1; then
    if pgrep -f "${APP_DIR}/thin-wrap" >/dev/null 2>&1; then
        echo "WARNING: thin-wrap appears to be running."
        echo "Quit it before continuing if the file replacement fails."
    fi
fi

mkdir -p "$LIBDIR" "$BINDIR" "$TMPDIR"
cd "$TMPDIR"

# Download (current install is still intact)
if ! http_download "${ARCHIVE}" "${DOWNLOAD_URL}"; then
    echo "ERROR: Download failed"
    echo "URL: ${DOWNLOAD_URL}"
    rm -rf "$TMPDIR"
    exit 1
fi

ARCHIVE_SIZE=$(wc -c < "${ARCHIVE}" | tr -d ' ')
if [ "${ARCHIVE_SIZE:-0}" -lt 1048576 ]; then
    echo "ERROR: Downloaded archive is too small (${ARCHIVE_SIZE} bytes)."
    rm -rf "$TMPDIR"
    exit 1
fi

if [ -n "$EXPECTED_SHA" ]; then
    ACTUAL_SHA=$(file_sha256 "${ARCHIVE}")
    if [ -z "$ACTUAL_SHA" ]; then
        echo "WARNING: No sha256 tool found; skipping checksum verification."
    elif [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
        echo "ERROR: Checksum mismatch for ${ARCHIVE}"
        echo "  expected: ${EXPECTED_SHA}"
        echo "  actual:   ${ACTUAL_SHA}"
        rm -rf "$TMPDIR"
        exit 1
    fi
else
    echo "WARNING: GitHub release did not publish a digest for ${ARCHIVE}; skipping checksum."
fi

if ! command -v unzip >/dev/null 2>&1; then
    echo "ERROR: unzip command not found. Please install unzip."
    rm -rf "$TMPDIR"
    exit 1
fi

EXTRACT_DIR="${TMPDIR}/extract"
mkdir -p "$EXTRACT_DIR"
if ! unzip -qq -o "${ARCHIVE}" -d "$EXTRACT_DIR"; then
    echo "ERROR: Extraction failed; existing installation was not changed."
    rm -rf "$TMPDIR"
    exit 1
fi

NEW_DIR=""
if [ -d "${EXTRACT_DIR}/thin-wrap" ] && [ -f "${EXTRACT_DIR}/thin-wrap/thin-wrap" ]; then
    NEW_DIR="${EXTRACT_DIR}/thin-wrap"
elif [ -f "${EXTRACT_DIR}/thin-wrap" ]; then
    NEW_DIR="${EXTRACT_DIR}"
else
    echo "ERROR: Cannot find thin-wrap binary after extraction."
    echo "Existing installation was not changed."
    rm -rf "$TMPDIR"
    exit 1
fi

chmod +x "${NEW_DIR}/thin-wrap"
if [ ! -x "${NEW_DIR}/thin-wrap" ]; then
    echo "ERROR: Extracted binary is not executable."
    rm -rf "$TMPDIR"
    exit 1
fi

# Swap: move current aside, then move the new tree into place.
# Not POSIX-atomic across filesystems, but $APP_DIR is never left empty
# by an rm -rf that happens before the new tree is ready.
if [ "$EXISTING" -eq 1 ]; then
    rm -rf "$BACKUP_DIR"
    if ! mv "$APP_DIR" "$BACKUP_DIR"; then
        echo "ERROR: Could not move the current install aside."
        rm -rf "$TMPDIR"
        exit 1
    fi
    if ! mv "$NEW_DIR" "$APP_DIR"; then
        echo "ERROR: Could not move the new version into place."
        restore_backup
        rm -rf "$TMPDIR"
        exit 1
    fi
else
    if ! mv "$NEW_DIR" "$APP_DIR"; then
        echo "ERROR: Could not install thin-wrap to ${APP_DIR}"
        rm -rf "$TMPDIR"
        exit 1
    fi
fi

chmod +x "${APP_DIR}/thin-wrap"
if [ ! -x "${APP_DIR}/thin-wrap" ]; then
    echo "ERROR: Installed binary is not executable."
    if [ "$EXISTING" -eq 1 ]; then
        restore_backup
    fi
    rm -rf "$TMPDIR"
    exit 1
fi

printf '%s\n' "$VERSION" > "${APP_DIR}/.version"
echo "$CONFIG_MODE" > "${APP_DIR}/.config_location"

cat > "${BINDIR}/thin-wrap" << EOF
#!/bin/sh
# thin-wrap wrapper – provides environment variables for consistent path reporting
export THIN_WRAP_APP_DIR="${APP_DIR}"
export THIN_WRAP_CONFIG_DIR="${CONFIG_TARGET}"
exec "${APP_DIR}/thin-wrap" "\$@"
EOF
chmod +x "${BINDIR}/thin-wrap"

# Never overwrite an existing user config
if [ ! -f "${CONFIG_TARGET}/config.json" ]; then
    mkdir -p "${CONFIG_TARGET}"
    if [ -f "${APP_DIR}/config.json" ]; then
        cp "${APP_DIR}/config.json" "${CONFIG_TARGET}/config.json"
    fi
fi

if [ "$PLATFORM" = "Darwin" ]; then
    if command -v xattr >/dev/null 2>&1; then
        xattr -cr "$APP_DIR" 2>/dev/null || true
        xattr -cr "${BINDIR}/thin-wrap" 2>/dev/null || true
    fi
fi

# Success: drop the single previous backup
rm -rf "$BACKUP_DIR"
cd - >/dev/null 2>&1 || true
rm -rf "$TMPDIR"

add_path_to_file() {
    FILE="$1"
    PATH_LINE="export PATH=\"${BINDIR}:\$PATH\""
    if grep -qsF "$PATH_LINE" "$FILE" 2>/dev/null; then
        return 0
    fi
    echo "" >> "$FILE"
    echo "# thin-wrap install - added by installer" >> "$FILE"
    echo "$PATH_LINE" >> "$FILE"
    echo "Added PATH to $FILE"
}

if [ "$PLATFORM" = "Linux" ]; then
    add_path_to_file "${HOME}/.bashrc"
    add_path_to_file "${HOME}/.profile"
elif [ "$PLATFORM" = "Darwin" ]; then
    add_path_to_file "${HOME}/.zprofile"
    add_path_to_file "${HOME}/.zshrc"
    add_path_to_file "${HOME}/.bash_profile"
    if basename "$SHELL" 2>/dev/null | grep -q bash; then
        add_path_to_file "${HOME}/.bashrc"
    fi
fi

if [ "$EXISTING" -eq 1 ]; then
    echo "Update complete: ${CURRENT_VERSION} -> ${VERSION}"
else
    echo "Installation complete: ${VERSION}"
fi

echo "Run: thin-wrap --help"
echo ""
echo "NOTE: To use thin-wrap in this terminal, run:"
if [ "$PLATFORM" = "Linux" ]; then
    echo "  source ~/.bashrc"
elif [ "$PLATFORM" = "Darwin" ]; then
    SHELL_NAME=$(basename "${SHELL:-/bin/zsh}")
    case "$SHELL_NAME" in
        zsh) echo "  source ~/.zshrc" ;;
        bash) echo "  source ~/.bash_profile" ;;
        *) echo "  export PATH=\"${BINDIR}:\$PATH\"" ;;
    esac
fi
echo "Or open a new terminal window."
