#!/bin/sh
set -e

if [ "$(id -u)" -eq 0 ]; then
    echo "ERROR: Do not run uninstall as root."
    exit 1
fi

OS="$(uname -s)"
case "$OS" in
    Linux*)  PROFILE_FILE="${HOME}/.profile" ;;
    Darwin*) PROFILE_FILE="${HOME}/.bash_profile" ;;
    *)       PROFILE_FILE="${HOME}/.profile" ;;
esac

LIBDIR="${HOME}/.local/lib/thin-wrap"
BINDIR="${HOME}/.local/bin"
WRAPPER="${BINDIR}/thin-wrap"

if [ ! -d "$LIBDIR" ]; then
    echo "thin-wrap not found at ${LIBDIR}"
    exit 1
fi

# Detect config location
if [ -f "${LIBDIR}/.config_location" ]; then
    CONFIG_MODE=$(cat "${LIBDIR}/.config_location")
else
    CONFIG_MODE="portable"
fi

if [ "$CONFIG_MODE" = "xdg" ]; then
    CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/thin-wrap"
    CONFIG_DISPLAY="$CONFIG_DIR"
else
    CONFIG_DIR="$LIBDIR"
    CONFIG_DISPLAY="${LIBDIR}/config.json"
fi

echo "=== thin-wrap Uninstaller ==="
echo "Will remove:"
echo "  Binary:    ${LIBDIR}/"
echo "  Wrapper:   ${WRAPPER}"
echo "  Config:    ${CONFIG_DISPLAY} (contains API keys!)"
echo ""

printf "Remove config files too? [y/N]: "
read -r rm_config
printf "Proceed? [y/N]: "
read -r confirm

if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Cancelled."
    exit 0
fi

# Backup config if keeping it but in portable mode (will be deleted with LIBDIR)
if [ "$rm_config" != "y" ] && [ "$rm_config" != "Y" ] && [ "$CONFIG_MODE" = "portable" ]; then
    if [ -f "${LIBDIR}/config.json" ]; then
        BACKUP="${HOME}/thin-wrap-config-backup-$(date +%Y%m%d%H%M%S).json"
        cp "${LIBDIR}/config.json" "$BACKUP"
        echo "Config backed up to: ${BACKUP}"
    fi
fi

# Remove binary and wrapper
rm -rf "$LIBDIR"
rm -f "$WRAPPER"

# Remove config if requested
if [ "$rm_config" = "y" ] || [ "$rm_config" = "Y" ]; then
    if [ "$CONFIG_MODE" = "xdg" ]; then
        rm -rf "$CONFIG_DIR"
    fi
    echo "Config removed."
else
    if [ "$CONFIG_MODE" = "xdg" ]; then
        echo "Config preserved at: ${CONFIG_DIR}"
    fi
fi

# Clean up PATH from profile (optional, best effort)
if grep -q "thin-wrap" "$PROFILE_FILE" 2>/dev/null; then
    echo ""
    echo "Note: PATH export may remain in ${PROFILE_FILE}"
    echo "Remove manually if desired."
fi

echo "Uninstalled."