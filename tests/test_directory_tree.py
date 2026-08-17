#!/usr/bin/env python3
"""Tests for the smart directory tree generator."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from directory_tree import (
    RATIO_THRESHOLD,
    build_directory_tree,
    tree_char_count,
)
from file_processor import generate_file_query
from menu import FileMenuApp
from tags import Xml


def _mkdirs(base, rel):
    path = os.path.join(base, rel)
    os.makedirs(path, exist_ok=True)
    return path


def _touch(base, rel, content=""):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_root_gitignore_is_respected(tmp_path):
    _touch(tmp_path, ".gitignore", "*.log\nsecret/\n")
    _touch(tmp_path, "app.py", "print(1)")
    _touch(tmp_path, "debug.log", "x")
    _mkdirs(tmp_path, "secret")
    _touch(tmp_path, "secret/keys.py", "k")

    tree = build_directory_tree(tmp_path, max_depth=3)
    assert "app.py" in tree
    assert "debug.log" not in tree
    assert "secret" not in tree


def test_parent_gitignore_is_respected(tmp_path):
    # .gitignore sits above the project root
    _touch(tmp_path, ".gitignore", "ignored_dir/\n*.bin\n")
    proj = _mkdirs(tmp_path, "project")
    _touch(proj, "ok.py", "print(1)")
    _mkdirs(proj, "ignored_dir")
    _touch(proj, "ignored_dir/data.py", "x")
    _touch(proj, "blob.bin", "\x00\x01")

    tree = build_directory_tree(proj, max_depth=3)
    assert "ok.py" in tree
    assert "ignored_dir" not in tree
    assert "blob.bin" not in tree


def test_nested_gitignore_is_respected(tmp_path):
    _touch(tmp_path, "main.py", "print(1)")
    _mkdirs(tmp_path, "sub")
    _touch(tmp_path, "sub/.gitignore", "*.pyc\n")
    _touch(tmp_path, "sub/keep.py", "print(2)")
    _touch(tmp_path, "sub/cache.pyc", "\x00")

    tree = build_directory_tree(tmp_path, max_depth=3)
    assert "main.py" in tree
    assert "keep.py" in tree
    assert "cache.pyc" not in tree


def test_negation_in_gitignore_is_respected(tmp_path):
    _touch(tmp_path, ".gitignore", "*.log\n!important.log\n")
    _touch(tmp_path, "a.log", "x")
    _touch(tmp_path, "important.log", "keep")

    tree = build_directory_tree(tmp_path, max_depth=2)
    assert "a.log" not in tree
    assert "important.log" in tree


def test_git_directory_always_hidden(tmp_path):
    _mkdirs(tmp_path, ".git")
    _touch(tmp_path, ".git/config", "x")
    _touch(tmp_path, "app.py", "print(1)")

    tree = build_directory_tree(tmp_path, max_depth=2)
    assert ".git" not in tree
    assert "app.py" in tree


def test_binary_heavy_directory_is_summarized(tmp_path):
    _mkdirs(tmp_path, "data/training/images")
    _mkdirs(tmp_path, "data/training/texts")
    _mkdirs(tmp_path, "data/training/tokens_896")
    for sub in ("images", "texts", "tokens_896"):
        for i in range(12):
            _touch(tmp_path, f"data/training/{sub}/f{i}.jpg", "\x00\x00")
    # one text file, so ratio is 36/37 > 0.70
    _touch(tmp_path, "data/training/labels.csv", "a,b\n")

    tree = build_directory_tree(tmp_path, max_depth=3)
    assert "data/" in tree
    assert "training/" in tree
    # summarized subdirectories show counts, never individual non-text files
    assert "images/" in tree and "→ 12 files" in tree
    assert "texts/" in tree and "→ 12 files" in tree
    assert "tokens_896/" in tree and "→ 12 files" in tree
    assert "f0.jpg" not in tree
    # text files may still be listed
    assert "labels.csv" in tree


def test_text_heavy_directory_is_expanded(tmp_path):
    _mkdirs(tmp_path, "src")
    for i in range(6):
        _touch(tmp_path, f"src/mod{i}.py", "print(1)")
    _touch(tmp_path, "src/asset.png", "\x00\x00")
    # ratio is 1/7 ≈ 0.14, below the threshold

    tree = build_directory_tree(tmp_path, max_depth=3)
    assert "mod0.py" in tree
    assert "asset.png" in tree  # individual files listed when expanded
    assert "files" not in tree.split("→", 1)[0]


def test_exactly_threshold_is_not_summarized(tmp_path):
    # 7 files: 5 non-text + 2 text -> ratio = 5/7 ≈ 0.714 > 0.70 -> summarized
    for i in range(5):
        _touch(tmp_path, f"b{i}.bin", "\x00")
    _touch(tmp_path, "a.txt", "x")
    _touch(tmp_path, "b.txt", "y")
    assert RATIO_THRESHOLD < 5 / 7
    tree = build_directory_tree(tmp_path, max_depth=2)
    assert "b0.bin" not in tree

    # 7 files: 4 non-text + 3 text -> ratio = 4/7 ≈ 0.571 < 0.70 -> expanded
    for name in list(os.listdir(tmp_path)):
        os.remove(os.path.join(tmp_path, name))
    for i in range(4):
        _touch(tmp_path, f"b{i}.bin", "\x00")
    for i in range(3):
        _touch(tmp_path, f"a{i}.txt", "x")
    tree = build_directory_tree(tmp_path, max_depth=2)
    assert "b0.bin" in tree
    assert "a0.txt" in tree


def test_depth_limit_truncates(tmp_path):
    for i in range(2):
        _touch(tmp_path, f"top{i}.py", "print(1)")
    _mkdirs(tmp_path, "a/b/c")
    _touch(tmp_path, "a/b/c/deep.py", "print(2)")

    tree = build_directory_tree(tmp_path, max_depth=1)
    assert "top0.py" in tree
    assert "deep.py" not in tree
    # subdirs truncated at depth limit show a compact count
    assert "a/" in tree and "→" in tree


def test_text_extensions_and_special_filenames(tmp_path):
    _touch(tmp_path, "Dockerfile", "FROM python")
    _touch(tmp_path, "Makefile", "all:")
    _touch(tmp_path, "README.md", "# hi")
    _touch(tmp_path, "LICENSE", "MIT")
    _touch(tmp_path, "Cargo.toml", "[package]")
    _touch(tmp_path, "script.sh", "#!/bin/sh")
    _touch(tmp_path, "blob.bin", "\x00\x00")

    tree = build_directory_tree(tmp_path, max_depth=2)
    for name in (
        "Dockerfile",
        "Makefile",
        "README.md",
        "LICENSE",
        "Cargo.toml",
        "script.sh",
    ):
        assert name in tree
    # no non-text extension files here; blob.bin appears because the
    # directory is text-heavy (5/6 ratio <= threshold) so it is expanded
    assert "blob.bin" in tree


def test_char_count_matches_len(tmp_path):
    _touch(tmp_path, "app.py", "print(1)")
    tree = build_directory_tree(tmp_path, max_depth=2)
    assert tree_char_count(tree) == len(tree)
    assert tree_char_count("") == 0


def test_empty_dir_renders_root_only(tmp_path):
    tree = build_directory_tree(tmp_path, max_depth=3)
    assert tree == f"{os.path.basename(tmp_path)}/"


def test_dot_gitignore_itself_visible(tmp_path):
    _touch(tmp_path, ".gitignore", "")
    _touch(tmp_path, "app.py", "print(1)")
    tree = build_directory_tree(tmp_path, max_depth=2)
    assert ".gitignore" in tree
    assert "app.py" in tree


def test_binary_heavy_subdir_under_text_heavy_parent(tmp_path):
    # parent has only text files (text-heavy -> expanded), but its subdir
    # is full of binary files -> must render as "name/ -> N files"
    _touch(tmp_path, "notes.md", "# notes")
    _mkdirs(tmp_path, "assets")
    for i in range(10):
        _touch(tmp_path, f"assets/asset{i}.bin", "\x00")

    tree = build_directory_tree(tmp_path, max_depth=3)
    assert "notes.md" in tree
    assert "assets/" in tree
    assert "→ 10 files" in tree
    assert "asset0.bin" not in tree


def test_tree_section_emitted_above_source_code_files(tmp_path):
    _touch(tmp_path, "app.py", "print(1)")
    tree = build_directory_tree(tmp_path, max_depth=2)
    query = generate_file_query(
        str(tmp_path), ["app.py"], [], "do something", directory_tree=tree
    )
    open_tag = f"<{Xml.DIRECTORY_TREE}"
    close_tag = f"</{Xml.DIRECTORY_TREE}>"
    assert open_tag in query
    assert close_tag in query
    assert query.index(open_tag) < query.index(f"<{Xml.SOURCE_CODE_FILES}")


def test_tree_section_omitted_when_disabled(tmp_path):
    _touch(tmp_path, "app.py", "print(1)")
    query = generate_file_query(str(tmp_path), ["app.py"], [], "do something")
    assert f"<{Xml.DIRECTORY_TREE}" not in query
    assert f"</{Xml.DIRECTORY_TREE}>" not in query


def _menu_app(tmp_path):
    import asyncio

    from strings import t as _t

    app = FileMenuApp([], [], str(tmp_path))

    async def scenario():
        async with app.run_test() as pilot:
            app.action_toggle_tree_context()
            await pilot.pause()
            assert app.tree_context_enabled is True
            assert app.query_one("#tree-toggle").content == _t(
                "menus.tree_context_line", marker="x"
            )
            count_text = app.query_one("#tree-charcount").content
            assert "Tree:" in count_text
            assert "0" not in count_text
            assert "chars" in count_text

            app.action_toggle_tree_context()
            await pilot.pause()
            assert app.tree_context_enabled is False
            assert app.query_one("#tree-charcount").content == _t(
                "menus.tree_chars_label", count=0
            )

            app.action_toggle_tree_context()
            app.action_increase_depth()
            await pilot.pause()
            assert app.tree_depth == 6
            assert app.query_one("#tree-depth").content == "Depth: 6"
            app.action_decrease_depth()
            app.action_decrease_depth()
            await pilot.pause()
            assert app.tree_depth == 4
            app.action_toggle_tree_context()

    asyncio.run(scenario())
    return app


def test_menu_toggle_depth_and_char_count(tmp_path):
    _touch(tmp_path, "app.py", "print(1)")
    app = _menu_app(tmp_path)
    assert app.tree_context_enabled is False
    assert app.tree_depth == 4
