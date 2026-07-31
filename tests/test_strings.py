#!/usr/bin/env python3
"""Tests for the centralized strings.json system."""

import sys
import os
import re
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from strings import t, _load

STRINGS_FILE = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")), "strings.json"
)


def _leaf_entries():
    """Yield (dotted_key, text) for every leaf entry (string or {text,...})."""
    data = _load()

    def walk(node, prefix=""):
        for key, value in node.items():
            dotted = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict) and "text" in value:
                yield dotted, value["text"]
            elif isinstance(value, dict):
                yield from walk(value, dotted)
            else:
                yield dotted, value

    yield from walk(data)


def test_strings_file_is_valid_json():
    """strings.json must be parseable JSON."""
    with open(STRINGS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    for required in ("common", "errors", "info", "prompts", "menus", "commands"):
        assert required in data


def test_every_entry_renders():
    """Every template must render with its placeholders filled."""
    for key, text in _leaf_entries():
        assert isinstance(text, str), f"{key} is not a string"
        placeholders = re.findall(r"{(\w+)}", text)
        if placeholders:
            t(key, **{name: "test" for name in placeholders})
        else:
            t(key)


def test_colored_entries_render_without_color_when_no_color_field():
    """Plain entries must not emit ANSI codes, colored ones must."""
    plain = t("common.empty_input")
    assert "\033[" not in plain
    colored = t("common.error_prefix")
    assert "\033[" in colored


def test_all_used_keys_exist():
    """Every t(\"...\") call in source must resolve to a JSON entry."""
    src_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    data = _load()
    used = set()
    for fname in os.listdir(src_root):
        if not fname.endswith(".py"):
            continue
        with open(os.path.join(src_root, fname), "r", encoding="utf-8") as f:
            text = f.read()
        used.update(re.findall(r"\bt\(\s*(['\"])([a-z_][a-z0-9_.]*)\1", text))

    for _, key in used:
        node = data
        for part in key.split("."):
            assert part in node, f"Missing strings.json key referenced in code: {key}"
            node = node[part]
