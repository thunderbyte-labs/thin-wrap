#!/bin/sh
# thin-wrap uninstaller - supports legacy portable + new XDG installs

set -e

if [ "$(id -u)" -eq 0 ]; then
    echo "ERROR: Do not run uninstall as root."
    exit 1
fi

LIBDIR="${HOME}/.local/lib/thin-wrap"
BINDIR="${HOME}/.local/bin"
WRAPPER="${BINDIR}/thin-wrap"

if [ ! -d "$LIBDIR" ]; then
    echo "thin-wrap not found (${LIBDIR} does not exist)"
    exit 1
fi

# Detect install type
if [ -f "${LIBDIR}/.config_location" ]; then
    CONFIG_MODE=$(cat "${LIBDIR}/.config_location")
else
    CONFIG_MODE="portable"
fi

if [ "$CONFIG_MODE" = "xdg" ]; then
    CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/thin-wrap"
    CONFIG_LABEL="XDG: $CONFIG_DIR"
else
    CONFIG_DIR="$LIBDIR"
    CONFIG_LABEL="Portable: ${LIBDIR}/config.json"
fi

echo "=== thin-wrap Uninstaller ==="
echo ""
echo "This will remove:"
echo "  • Program files : ${LIBDIR}/"
echo "  • Wrapper       : ${WRAPPER}"
echo "  • Config        : ${CONFIG_LABEL}"
echo ""

printf "Also delete configuration? [y/N]: "
read -r DELETE_CONFIG

printf "Proceed with uninstall? [y/N]: "
read -r CONFIRM

if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Uninstall cancelled."
    exit 0
fi

echo "Removing thin-wrap..."

# Remove program
rm -rf "$LIBDIR"
rm -f "$WRAPPER"

# Remove config if requested
if [ "$DELETE_CONFIG" = "y" ] || [ "$DELETE_CONFIG" = "Y" ]; then
    if [ "$CONFIG_MODE" = "xdg" ] && [ -d "$CONFIG_DIR" ]; then
        rm -rf "$CONFIG_DIR"
        echo "Configuration directory removed."
    else
        echo "Configuration removed."
    fi
else
    if [ "$CONFIG_MODE" = "xdg" ]; then
        echo "Configuration left at: $CONFIG_DIR"
    fi
fi

echo ""
echo "thin-wrap has been successfully uninstalled."