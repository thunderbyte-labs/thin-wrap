#!/bin/bash
# Shared format + lint gate (single source of truth for ruff invocations).
# Used by test_all.sh / CI in --check mode, and by developers in apply mode.
#
# Usage:
#   ./check_all.sh          # apply: ruff format + ruff check --fix
#   ./check_all.sh --check  # verify: fail if formatting/lint would change anything

set -u
cd "$(dirname "$0")"

if [ "${1:-}" = "--check" ]; then
    MODE="check"
else
    MODE="apply"
fi

# Resolve ruff: prefer the project venv, fall back to PATH (covers global/uv installs).
if [ -x ".venv/bin/ruff" ]; then
    RUFF=".venv/bin/ruff"
else
    RUFF="$(command -v ruff 2>/dev/null || true)"
fi

if [ -z "$RUFF" ]; then
    echo "❌ ruff is not installed. Install it with: pip install ruff==0.16.1" >&2
    exit 1
fi

if [ "$MODE" = "check" ]; then
    echo "Checking formatting (ruff format --check) ..."
    if ! "$RUFF" format --check .; then
        echo "❌ Formatting would change some files. Run: ./check_all.sh" >&2
        exit 1
    fi
    echo "Checking lint (ruff check) ..."
    if ! "$RUFF" check .; then
        echo "❌ Lint errors found. Run: ./check_all.sh" >&2
        exit 1
    fi
    echo "✅ Formatting and lint are clean."
else
    echo "Formatting (ruff format) ..."
    "$RUFF" format .
    echo "Fixing lint (ruff check --fix) ..."
    "$RUFF" check --fix .
fi
