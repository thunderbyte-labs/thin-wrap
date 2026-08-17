#!/usr/bin/env python3
"""Tests for multi-select in the file context menu (FileMenuApp)."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from rich.style import Style
from textual.events import Click
from textual.widgets import ListView

from menu import FileMenuApp, MultiSelectDirectoryTree
from strings import t


def _touch(base, rel, content=""):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _list_view(app, view_id):
    return app.query_one(f"#{view_id}", ListView)


def _items(app, view_id):
    return list(_list_view(app, view_id).children)


def _paths(app, view_id):
    return [getattr(item, "custom_path", None) for item in _items(app, view_id)]


async def _click_on(app, widget, *, ctrl=False, shift=False, line=None):
    """Dispatch a click on ``widget`` through the app's multi-select handler."""
    style = Style(meta={"line": line}) if line is not None else None
    event = Click(
        widget,
        x=0,
        y=0,
        delta_x=0,
        delta_y=0,
        button=0,
        shift=shift,
        meta=False,
        ctrl=ctrl,
        style=style,
    )
    event.widget = widget
    await app._on_click(event)


async def _tree_line_of(app, pilot, abs_path):
    tree = app.query_one("#navigator", MultiSelectDirectoryTree)
    for _ in range(200):
        await pilot.pause()
        for y in range(tree.last_line + 1):
            node = tree.get_node_at_line(y)
            if (
                node is not None
                and node.data is not None
                and str(node.data.path) == str(abs_path)
            ):
                return y
    raise AssertionError(f"tree node not found: {abs_path}")


async def _ctrl_click_tree(app, pilot, abs_path):
    tree = app.query_one("#navigator", MultiSelectDirectoryTree)
    line = await _tree_line_of(app, pilot, abs_path)
    await _click_on(app, tree, ctrl=True, line=line)


def test_ctrl_click_toggles_and_r_moves_selection(tmp_path):
    _touch(tmp_path, "a.py")
    _touch(tmp_path, "b.py")
    _touch(tmp_path, "c.py")
    app = FileMenuApp(["a.py", "b.py", "c.py"], [], str(tmp_path))

    async def scenario():
        async with app.run_test() as pilot:
            editable = _list_view(app, "editable")
            editable.focus()
            await pilot.pause()
            a, b, c = _items(app, "editable")
            await _click_on(app, a, ctrl=True)
            await pilot.pause()
            assert app._left_selection == {"a.py"}
            assert a.has_class("selected")
            assert not b.has_class("selected")
            await _click_on(app, c, ctrl=True)
            await pilot.pause()
            assert app._left_selection == {"a.py", "c.py"}
            assert c.has_class("selected")

            await pilot.press("r")
            await pilot.pause()
            assert sorted(app.editable_files) == ["b.py"]
            assert sorted(app.readable_files) == ["a.py", "c.py"]
            assert app._left_selection == set()

    asyncio.run(scenario())


def test_ctrl_click_toggles_off(tmp_path):
    _touch(tmp_path, "a.py")
    _touch(tmp_path, "b.py")
    app = FileMenuApp(["a.py", "b.py"], [], str(tmp_path))

    async def scenario():
        async with app.run_test() as pilot:
            a, b = _items(app, "editable")
            await _click_on(app, a, ctrl=True)
            await pilot.pause()
            assert app._left_selection == {"a.py"}
            await _click_on(app, a, ctrl=True)
            await pilot.pause()
            assert app._left_selection == set()
            assert not a.has_class("selected")

    asyncio.run(scenario())


def test_shift_click_range_selects(tmp_path):
    _touch(tmp_path, "a.py")
    _touch(tmp_path, "b.py")
    _touch(tmp_path, "c.py")
    _touch(tmp_path, "d.py")
    app = FileMenuApp(["a.py", "b.py", "c.py", "d.py"], [], str(tmp_path))

    async def scenario():
        async with app.run_test() as pilot:
            a, b, c, d = _items(app, "editable")
            await _click_on(app, a)
            await pilot.pause()
            await _click_on(app, c, shift=True)
            await pilot.pause()
            assert app._left_selection == {"a.py", "b.py", "c.py"}
            assert a.has_class("selected") and c.has_class("selected")
            assert not d.has_class("selected")

    asyncio.run(scenario())


def test_d_deletes_entire_selection(tmp_path):
    _touch(tmp_path, "a.py")
    _touch(tmp_path, "b.py")
    _touch(tmp_path, "c.py")
    app = FileMenuApp(["a.py", "b.py", "c.py"], ["x.py"], str(tmp_path))

    async def scenario():
        async with app.run_test() as pilot:
            editable = _list_view(app, "editable")
            editable.focus()
            await pilot.pause()
            for item in _items(app, "editable"):
                await _click_on(app, item, ctrl=True)
            await pilot.pause()
            assert app._left_selection == {"a.py", "b.py", "c.py"}
            await pilot.press("d")
            await pilot.pause()
            assert app.editable_files == []
            assert app.readable_files == ["x.py"]
            assert app._left_selection == set()

    asyncio.run(scenario())


def test_zone_lock_blocks_other_zone_and_escape_unlocks(tmp_path):
    _touch(tmp_path, "a.py")
    _touch(tmp_path, "nav1.py")
    _touch(tmp_path, "nav2.py")
    app = FileMenuApp(["a.py"], [], str(tmp_path))

    async def scenario():
        async with app.run_test() as pilot:
            (item,) = _items(app, "editable")
            await _click_on(app, item, ctrl=True)
            await pilot.pause()
            assert app._left_selection == {"a.py"}

            nav1 = os.path.join(tmp_path, "nav1.py")
            await _ctrl_click_tree(app, pilot, nav1)
            # blocked: left zone has an active multi-selection
            assert app._right_selection == set()
            assert app._left_selection == {"a.py"}

            await pilot.press("escape")
            await pilot.pause()
            assert app._left_selection == set()

            await _ctrl_click_tree(app, pilot, nav1)
            nav2 = os.path.join(tmp_path, "nav2.py")
            await _ctrl_click_tree(app, pilot, nav2)
            assert app._right_selection == {nav1, nav2}

    asyncio.run(scenario())


def test_navigator_multiselect_r_adds_all(tmp_path):
    _touch(tmp_path, "nav1.py")
    _touch(tmp_path, "nav2.py")
    app = FileMenuApp([], [], str(tmp_path))

    async def scenario():
        async with app.run_test() as pilot:
            nav1 = os.path.join(tmp_path, "nav1.py")
            nav2 = os.path.join(tmp_path, "nav2.py")
            await _ctrl_click_tree(app, pilot, nav1)
            await _ctrl_click_tree(app, pilot, nav2)
            assert app._right_selection == {nav1, nav2}
            tree = app.query_one("#navigator", MultiSelectDirectoryTree)
            assert tree._selected_paths == {nav1, nav2}

            await pilot.press("r")
            await pilot.pause()
            assert sorted(app.readable_files) == ["nav1.py", "nav2.py"]
            assert app._right_selection == set()

    asyncio.run(scenario())


def test_single_select_behavior_preserved(tmp_path):
    _touch(tmp_path, "a.py")
    _touch(tmp_path, "b.py")
    app = FileMenuApp(["a.py", "b.py"], [], str(tmp_path))

    async def scenario():
        async with app.run_test() as pilot:
            editable = _list_view(app, "editable")
            editable.focus()
            editable.index = 0  # highlight a.py
            await pilot.pause()
            # no multi-selection: single 'r' moves only the highlighted item
            await pilot.press("r")
            await pilot.pause()
            assert sorted(app.editable_files) == ["b.py"]
            assert app.readable_files == ["a.py"]

    asyncio.run(scenario())


def test_real_click_routing_smoke(tmp_path):
    import asyncio

    _touch(tmp_path, "a.py")
    app = FileMenuApp(["a.py"], [], str(tmp_path))

    async def scenario():
        async with app.run_test() as pilot:
            editable = _list_view(app, "editable")
            await pilot.pause()
            item = list(editable.children)[0]
            await pilot.click(item)
            await pilot.pause()
            # plain click resets the zone and sets the shift anchor
            assert app._shift_anchor == ("left", "a.py")
            assert app._left_selection == set()

    asyncio.run(scenario())


def test_footer_labels_shortened():
    assert t("menus.shortcuts.clear_all") == "Clear"
    assert t("menus.shortcuts.tree") == "Dir Tree"


def test_footer_has_multiselect_hints():
    app = FileMenuApp([], [], "/tmp")
    keys = {b.key for b in app.BINDINGS}
    assert "ctrl+click" in keys
    assert "shift+click" in keys
    display = {b.key: b.key_display for b in app.BINDINGS}
    assert display.get("escape") == "Escape"
    assert display.get("ctrl+click") == "Ctrl+click"
    assert display.get("shift+click") == "Shift+click"
