#!/bin/sh
# Universal installer for thin-wrap (Linux & macOS)
# POSIX-compliant, no bash required
# Usage: curl -fsSL .../install.sh | sh

set -e

REPO="thunderbyte-labs/thin-wrap"
API_URL="https://api.github.com/repos/${REPO}/releases/latest"

# Helper: Fetch latest version and download URL
fetch_latest_info() {
    # Try curl first, fallback to wget
    if command -v curl >/dev/null 2>&1; then
        JSON=$(curl -fsSL "$API_URL" 2>/dev/null) || true
    elif command -v wget >/dev/null 2>&1; then
        JSON=$(wget -qO- "$API_URL" 2>/dev/null) || true
    fi
    
    if [ -z "$JSON" ]; then
        echo "ERROR: Failed to fetch release info from GitHub API."
        echo "This may be due to API rate limits (60 requests/hour per IP)."
        echo "Please try again later or download manually from:"
        echo "  https://github.com/${REPO}/releases"
        exit 1
    fi
    
    # Extract tag_name (e.g., "v1.2.3")
    VERSION=$(echo "$JSON" | grep '"tag_name":' | sed -E 's/.*"tag_name": "([^"]+)".*/\1/')
    
    # Extract direct download URL for our archive
    # Looks for: https://github.com/.../releases/download/vX.Y.Z/thin-wrap-PLATFORM-ARCH.zip
    DOWNLOAD_URL=$(echo "$JSON" | grep -o "https://[^\"]*${ARCHIVE}" | head -n 1)
    
    if [ -z "$VERSION" ]; then
        echo "ERROR: Could not parse latest version from GitHub API."
        echo "Response was: $JSON"
        exit 1
    fi
    
    # Fallback to constructed URL if direct extraction fails
    if [ -z "$DOWNLOAD_URL" ]; then
        DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${VERSION}/${ARCHIVE}"
    fi
}

# Dilemma F: Block root
if [ "$(id -u)" -eq 0 ]; then
    echo "ERROR: thin-wrap refuses to install as root."
    echo "Run without sudo to install to ~/.local/"
    exit 1
fi

# Platform detection (Dilemma 2: Option A - same XDG paths for both)
OS="$(uname -s)"
case "$OS" in
    Linux*)  PLATFORM="Linux" ; PROFILE_FILE="${HOME}/.profile" ;;
    Darwin*) PLATFORM="Darwin" ; PROFILE_FILE="${HOME}/.bash_profile" ;; # Login shell on macOS
    *) echo "ERROR: Unsupported OS: $OS"; exit 1 ;;
esac

# Architecture detection (Dilemma 5)
ARCH_RAW="$(uname -m)"
case "$ARCH_RAW" in
    x86_64|amd64) ARCH="x86_64" ;;
    aarch64)      ARCH="aarch64" ;;
    arm64)        ARCH="arm64" ;; # macOS Apple Silicon
    *)
        echo "ERROR: Unsupported architecture: $ARCH_RAW"
        echo "Supported: x86_64, aarch64, arm64"
        echo "Please download manually from: https://github.com/${REPO}/releases"
        exit 1
        ;;
esac

ARCHIVE="thin-wrap-${PLATFORM}-${ARCH}.zip"
TMPDIR="${TMPDIR:-/tmp}/thin-wrap-install-$$"
PREFIX="${HOME}/.local"
LIBDIR="${PREFIX}/lib/thin-wrap"
BINDIR="${PREFIX}/bin"
CONFIG_DIR_XDG="${XDG_CONFIG_HOME:-${HOME}/.config}/thin-wrap"

# Fetch latest version info before proceeding
fetch_latest_info

mkdir -p "$TMPDIR"
cd "$TMPDIR"

# Determine if interactive (Dilemma 3: SSH non-interactive handling)
if [ -t 0 ]; then
    INTERACTIVE=1
else
    INTERACTIVE=0
    echo "Non-interactive mode detected (SSH/CI). Using defaults."
fi

echo "=== thin-wrap ${VERSION} Installer (${PLATFORM}/${ARCH}) ==="
echo ""

# Check existing installation (Dilemma 10: manual updates, detect existing)
if [ -d "$LIBDIR" ] && [ -f "${LIBDIR}/thin-wrap" ]; then
    UPDATE_MODE=1
    echo "Existing installation detected. Updating to ${VERSION}..."
    if [ -f "${LIBDIR}/.config_location" ]; then
        CONFIG_MODE=$(cat "${LIBDIR}/.config_location")
    else
        CONFIG_MODE="portable"
    fi
else
    UPDATE_MODE=0
    CONFIG_MODE=""
fi

# Config location choice (Dilemma A: Option 3 - user chooses, default portable)
if [ -z "$CONFIG_MODE" ]; then
    if [ $INTERACTIVE -eq 1 ]; then
        echo "Choose configuration storage location:"
        echo "  [1] Portable (next to app, in ~/.local/lib/thin-wrap/) - DEFAULT"
        echo "  [2] XDG Standard (~/.config/thin-wrap/)"
        printf "Select [1/2]: "
        read -r choice
        case "$choice" in
            2) CONFIG_MODE="xdg" ;;
            *) CONFIG_MODE="portable" ;;
        esac
    else
        CONFIG_MODE="portable" # Default for non-interactive
        echo "Defaulting to portable mode."
    fi
fi

# Set config target path
if [ "$CONFIG_MODE" = "xdg" ]; then
    CONFIG_TARGET="$CONFIG_DIR_XDG"
else
    CONFIG_TARGET="$LIBDIR"
fi

echo "Installing to: $LIBDIR"
echo "Config location: $CONFIG_TARGET"
echo "Downloading ${ARCHIVE}..."
echo "URL: ${DOWNLOAD_URL}"

# Download
if command -v curl >/dev/null 2>&1; then
    curl -fsL -o "${ARCHIVE}" "${DOWNLOAD_URL}" || {
        echo "ERROR: Download failed (curl exited $?)"
        echo "URL: ${DOWNLOAD_URL}"
        exit 1
    }
elif command -v wget >/dev/null 2>&1; then
    wget -q -O "${ARCHIVE}" "${DOWNLOAD_URL}" || {
        echo "ERROR: Download failed (wget exited $?)"
        echo "URL: ${DOWNLOAD_URL}"
        exit 1
    }
else
    echo "ERROR: Neither curl nor wget found. Please install one of them."
    exit 1
fi

# Extract
unzip -o "${ARCHIVE}"
rm -f "${ARCHIVE}"

# Create directories
mkdir -p "$LIBDIR" "$BINDIR"

# Move binary (atomic)
chmod +x thin-wrap
mv thin-wrap "${LIBDIR}/thin-wrap"

# Store config mode for future updates
echo "$CONFIG_MODE" > "${LIBDIR}/.config_location"

# Dilemma D: Create wrapper script with hardcoded paths (Option A)
# This avoids PyInstaller symlink bug and survives SSH sessions
cat > "${BINDIR}/thin-wrap" << EOF
#!/bin/sh
# thin-wrap wrapper - hardcoded paths for SSH/compatibility
export THIN_WRAP_APP_DIR="${LIBDIR}"
export THIN_WRAP_CONFIG_DIR="${CONFIG_TARGET}"
exec "${LIBDIR}/thin-wrap" "\$@"
EOF
chmod +x "${BINDIR}/thin-wrap"

# Copy default config if missing and exists in bundle
if [ ! -f "${CONFIG_TARGET}/config.json" ]; then
    mkdir -p "${CONFIG_TARGET}"
    if [ -f "${LIBDIR}/config.json" ]; then
        cp "${LIBDIR}/config.json" "${CONFIG_TARGET}/config.json"
        echo "Created default config at: ${CONFIG_TARGET}/config.json"
    fi
fi

# Cleanup
cd - >/dev/null 2>&1 || true
rm -rf "$TMPDIR"

# Dilemma C: PATH handling (Login shell only)
if echo ":${PATH}:" | grep -q ":${BINDIR}:"; then
    echo "PATH already configured."
else
    if [ $INTERACTIVE -eq 1 ]; then
        echo ""
        echo "WARNING: ${BINDIR} is not in your PATH."
        printf "Add to ${PROFILE_FILE}? [y/N]: "
        read -r add_path
        if [ "$add_path" = "y" ] || [ "$add_path" = "Y" ]; then
            echo "export PATH=\"${BINDIR}:\$PATH\"" >> "$PROFILE_FILE"
            echo "Added to ${PROFILE_FILE}"
            echo "Run: source ${PROFILE_FILE}"
        else
            echo "Add manually: export PATH=\"${BINDIR}:\$PATH\""
        fi
    else
        echo ""
        echo "WARNING: Add to your PATH:"
        echo "  export PATH=\"${BINDIR}:\$PATH\""
        echo "Add to ${PROFILE_FILE} for persistence."
    fi
fi

# macOS Gatekeeper warning (Dilemma 6)
if [ "$PLATFORM" = "Darwin" ]; then
    echo ""
    echo "macOS Security Notice:"
    echo "If you see 'cannot be verified' warnings, run:"
    echo "  xattr -d com.apple.quarantine ${LIBDIR}/thin-wrap"
    echo "Or install via Homebrew (recommended) when available:"
    echo "  brew install thunderbyte-labs/tap/thin-wrap"
fi

echo ""
if [ $UPDATE_MODE -eq 1 ]; then
    echo "Update complete! (v${VERSION})"
else
    echo "Installation complete!"
fi
echo "Run: thin-wrap --help"