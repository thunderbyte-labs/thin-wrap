"""Centralized user-facing strings loaded from strings.json.

All user-visible text lives in strings.json so that a UX designer can
review and edit copy without touching the Python source.

Usage:
    from strings import t
    print(t("common.error_prefix"))
    print(t("info.proxy_switched", url="socks5://localhost:1080"))
"""

import json
from pathlib import Path

_STRINGS = None


def _load() -> dict:
    """Load strings.json once and cache it."""
    global _STRINGS
    if _STRINGS is None:
        base = Path(__file__).parent.resolve()
        _STRINGS = json.loads((base / "strings.json").read_text(encoding="utf-8"))
    return _STRINGS


def t(key: str, **kwargs) -> str:
    """Return the string for the given dotted key.

    Entries may be either a plain string or an object with
    "text" and optional "color" fields. Placeholders ({name}) are
    replaced using str.format with the given kwargs.
    """
    entry = _load()
    for part in key.split("."):
        entry = entry[part]

    if isinstance(entry, dict):
        text = entry["text"]
        color = entry.get("color")
    else:
        text = entry
        color = None

    if kwargs:
        text = text.format(**kwargs)

    if color:
        from ui import UI  # local import to avoid circular dependency

        return UI.colorize(text, color)
    return text
