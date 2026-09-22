#!/usr/bin/env python3
"""Tests for the /reload session listing formatting."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from command_handler import format_session
from ui import UI


def _path(stem):
    return os.path.join("/conv", f"session_{stem}.toml.zip")


def test_timestamp_formatting():
    """Timestamps are rendered as YYYY-MM-DD HH:MM:SS."""
    result = format_session(_path("20260801_122513"), meta={"interaction_count": 1})
    assert "2026-08-01 12:25:13" in result


def test_named_session_shows_formatted_timestamp_and_name():
    """A named session keeps a formatted timestamp and shows the name."""
    result = format_session(
        _path("20260801_122513_wesh-la-conv"),
        meta={"interaction_count": 1, "name": "wesh-la-conv"},
    )
    assert "2026-08-01 12:25:13" in result
    assert "wesh-la-conv" in result


def test_name_fallback_from_filename():
    """The name falls back to the filename suffix when metadata has none."""
    result = format_session(
        _path("20260801_122513_wesh-la-conv"), meta={"interaction_count": 1}
    )
    assert "wesh-la-conv" in result


def test_unnamed_shows_no_name():
    """Sessions without a name show '*no name*'."""
    result = format_session(_path("20260801_122513"), meta={"interaction_count": 1})
    assert "*no name*" in result


def test_name_colored_green():
    """The name is colored GREEN when present."""
    result = format_session(
        _path("20260801_122513_wesh-la-conv"),
        meta={"interaction_count": 1, "name": "wesh-la-conv"},
    )
    colored = UI.colorize("wesh-la-conv", "GREEN")
    assert colored in result
    # Unnamed sessions are plain (no ANSI codes)
    plain = format_session(_path("20260801_122513"), meta={"interaction_count": 1})
    assert "\033[" not in plain


def test_message_count_singular_plural():
    """'1 message' vs 'N messages'."""
    singular = format_session(_path("20260801_122513"), meta={"interaction_count": 1})
    assert "1 message" in singular
    assert "1 messages" not in singular
    plural = format_session(_path("20260801_122513"), meta={"interaction_count": 2})
    assert "2 messages" in plural


def test_preview_shown_and_truncated():
    """The preview is appended and truncated to 50 chars."""
    long_preview = "A" * 100
    result = format_session(
        _path("20260801_122513"),
        meta={"interaction_count": 1, "preview": long_preview},
    )
    assert " - " in result
    # timestamp · name (count) - preview
    assert result.count("A") == 47


def test_bad_stem_falls_back_to_raw():
    """Non-timestamp filenames fall back to the raw stem."""
    result = format_session(_path("weird_name"), meta={"interaction_count": 1})
    assert "weird_name" in result


if __name__ == "__main__":
    test_timestamp_formatting()
    test_named_session_shows_formatted_timestamp_and_name()
    test_name_fallback_from_filename()
    test_unnamed_shows_no_name()
    test_name_colored_green()
    test_message_count_singular_plural()
    test_preview_shown_and_truncated()
    test_bad_stem_falls_back_to_raw()
    print("\n✅ All format_session tests passed!")
