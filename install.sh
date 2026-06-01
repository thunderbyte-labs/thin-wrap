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
    
    # Construct download URL
    DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${VERSION}/${ARCHIVE}"
    
    if [ -z "$VERSION" ]; then
        echo "ERROR: Could not parse latest version from GitHub API."
        exit 1
    fi
}

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
            # Pre-built Linux binaries now target glibc >= 2.35 (built on ubuntu-22.04)
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

# Create necessary directories early
mkdir -p "$LIBDIR"
mkdir -p "$BINDIR"

# Fetch latest version info
fetch_latest_info

mkdir -p "$TMPDIR"
cd "$TMPDIR"

# Determine if running interactively
if [ -t 0 ]; then
    INTERACTIVE=1
else
    INTERACTIVE=0
fi

echo "=== thin-wrap ${VERSION} Installer (${PLATFORM}/${ARCH}) ==="

# Check for existing installation (update mode)
if [ -d "$APP_DIR" ] && [ -f "${APP_DIR}/thin-wrap" ]; then
    UPDATE_MODE=1
    if [ -f "${APP_DIR}/.config_location" ]; then
        CONFIG_MODE=$(cat "${APP_DIR}/.config_location")
    else
        CONFIG_MODE="portable"
    fi
else
    UPDATE_MODE=0
    CONFIG_MODE=""
fi

# Config location selection
if [ -z "$CONFIG_MODE" ]; then
    if [ $INTERACTIVE -eq 1 ]; then
        printf "Select config location [1=portable (default), 2=XDG]: "
        read -r choice
        case "$choice" in
            2) CONFIG_MODE="xdg" ;;
            *) CONFIG_MODE="portable" ;;
        esac
    else
        CONFIG_MODE="portable"
    fi
fi

# Set config target
if [ "$CONFIG_MODE" = "xdg" ]; then
    CONFIG_TARGET="$CONFIG_DIR_XDG"
else
    CONFIG_TARGET="$APP_DIR"
fi

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

# Extract quietly
if command -v unzip >/dev/null 2>&1; then
    unzip -qq -o "${ARCHIVE}"
else
    echo "ERROR: unzip command not found. Please install unzip."
    exit 1
fi
rm -f "${ARCHIVE}"

# Handle PyInstaller one-directory structure
if [ -d "thin-wrap" ] && [ -f "thin-wrap/thin-wrap" ]; then
    rm -rf "$APP_DIR"
    mkdir -p "$(dirname "$APP_DIR")"
    mv thin-wrap "$APP_DIR"
elif [ -f "thin-wrap" ]; then
    mkdir -p "$APP_DIR"
    mv thin-wrap "$APP_DIR/"
else
    echo "ERROR: Cannot find thin-wrap binary after extraction"
    exit 1
fi

chmod +x "${APP_DIR}/thin-wrap"

# Verify binary
if [ ! -x "${APP_DIR}/thin-wrap" ]; then
    echo "ERROR: Binary not executable after extraction: ${APP_DIR}/thin-wrap"
    exit 1
fi

# Store config mode for future updates
echo "$CONFIG_MODE" > "${APP_DIR}/.config_location"

# Create wrapper script with --help enhancement and environment variables
cat > "${BINDIR}/thin-wrap" << EOF
#!/bin/sh
# thin-wrap wrapper – provides environment variables for consistent path reporting
export THIN_WRAP_APP_DIR="${APP_DIR}"
export THIN_WRAP_CONFIG_DIR="${CONFIG_TARGET}"
exec "${APP_DIR}/thin-wrap" "\$@"
EOF
chmod +x "${BINDIR}/thin-wrap"

# Copy default config if missing
if [ ! -f "${CONFIG_TARGET}/config.json" ]; then
    mkdir -p "${CONFIG_TARGET}"
    if [ -f "${APP_DIR}/config.json" ]; then
        cp "${APP_DIR}/config.json" "${CONFIG_TARGET}/config.json"
    fi
fi

# Cleanup
cd - >/dev/null 2>&1 || true
rm -rf "$TMPDIR"

# ---- PATH configuration ----
# On Linux: add to ~/.bashrc (interactive non-login shells) and ~/.profile (login shells)
# On macOS: add to ~/.bash_profile (login shells) and also ~/.bashrc if bash is the shell

add_path_to_file() {
    FILE="$1"
    PATH_LINE="export PATH=\"${BINDIR}:\$PATH\""
    # Skip if line already present
    if grep -qsF "$PATH_LINE" "$FILE" 2>/dev/null; then
        return 0
    fi
    # Skip if already in current PATH (important for update mode where user might have already sourced)
    # but we still want the line in the file for future sessions.
    # So we always add if not already in file.
    echo "" >> "$FILE"
    echo "# thin-wrap install - added by installer" >> "$FILE"
    echo "$PATH_LINE" >> "$FILE"
    echo "Added PATH to $FILE"
}

if [ "$PLATFORM" = "Linux" ]; then
    # Primary: ~/.bashrc (for interactive non-login shells, which is most common)
    add_path_to_file "${HOME}/.bashrc"
    # Secondary: ~/.profile (for login shells, e.g., SSH)
    add_path_to_file "${HOME}/.profile"
elif [ "$PLATFORM" = "Darwin" ]; then
    # macOS: ~/.bash_profile is standard for login shells
    add_path_to_file "${HOME}/.bash_profile"
    # Also add to ~/.bashrc if bash is the current shell (common for Terminal)
    if basename "$SHELL" 2>/dev/null | grep -q bash; then
        add_path_to_file "${HOME}/.bashrc"
    fi
fi

# macOS Gatekeeper note
if [ "$PLATFORM" = "Darwin" ]; then
    echo "macOS: if 'cannot be verified' see README for xattr command."
fi

if [ $UPDATE_MODE -eq 1 ]; then
    echo "Update complete! (${VERSION})"
else
    echo "Installation complete!"
fi
echo "Run: thin-wrap --help"
echo ""
echo "NOTE: To use thin-wrap in this terminal, run:"
if [ "$PLATFORM" = "Linux" ]; then
    echo "  source ~/.bashrc"
elif [ "$PLATFORM" = "Darwin" ]; then
    echo "  source ~/.bash_profile"
fi
echo "Or open a new terminal window."
