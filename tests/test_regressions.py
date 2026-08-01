"""Regression tests for bugs fixed during factorisation cleanup."""

import json
import os
import shutil
import tempfile
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from command_handler import CommandHandler
from file_processor import _report_diff, _write_file, generate_query
from history_store import HistoryStore
from ui import UI
from thin_wrap import LLMChat


# =========================================================================
# history_store
# =========================================================================


def test_history_store_round_trip():
    tmp = tempfile.mkdtemp()
    try:
        test_dir = os.path.join(tmp, "myproject")
        os.makedirs(test_dir)
        hf = Path(tmp) / "history.json"
        store = HistoryStore(hf)
        store.add_root(test_dir)
        store.add_proxy("socks5://127.0.0.1:1080")
        assert test_dir in store.recent_roots
        assert "socks5://127.0.0.1:1080" in store.recent_proxies
        store2 = HistoryStore(hf)
        assert test_dir in store2.recent_roots, "persist + re-load root"
        assert "socks5://127.0.0.1:1080" in store2.recent_proxies, "persist + re-load proxy"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_history_store_preserves_both_keys():
    tmp = tempfile.mkdtemp()
    try:
        hf = Path(tmp) / "history.json"
        hf.write_text(
            json.dumps({"recent_root_dirs": ["/a"], "recent_proxies": ["socks5://x:1"]})
        )
        store = HistoryStore(hf)
        store.add_proxy("socks5://y:2")
        store.add_root("/b")
        raw = json.loads(hf.read_text())
        assert "recent_root_dirs" in raw
        assert "recent_proxies" in raw
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =========================================================================
# command_handler._handle_rootdir (was str.is_dir crash)
# =========================================================================


class _MockChatApp:
    FREE_CHAT_MODE = "FREE_CHAT_MODE"
    recent_roots: list[str] = []
    recent_proxies: list[str] = []

    def set_root_dir(self, path):  # pragma: no cover
        pass

    def set_proxy(self, url: str | None):  # pragma: no cover
        return True


def test_handle_rootdir_with_path_arg(tmp_path):
    chat = _MockChatApp()
    handler = CommandHandler(
        llm_client=MagicMock(),
        session_logger=MagicMock(),
        input_handler=MagicMock(),
        chat_app=chat,
    )
    handler._handle_rootdir([str(tmp_path)])
    # should not raise AttributeError (was: str.is_dir)


# =========================================================================
# command_handler.session_logger propagated after set_root_dir
# =========================================================================


def _minimal_config_for_llmchat(config_path: str):
    with open(config_path, "w") as f:
        json.dump(
            {
                "models": {
                    "t": {
                        "model": "t",
                        "api_key": "TEST_KEY",
                        "api_base_url": "https://x",
                    }
                }
            },
            f,
        )
    os.environ["TEST_KEY"] = "dummy"


def test_command_handler_session_logger_after_set_root_dir(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    cf = config_dir / "config.json"
    _minimal_config_for_llmchat(str(cf))

    root1 = tmp_path / "a"
    root1.mkdir()
    root2 = tmp_path / "b"
    root2.mkdir()

    chat = LLMChat(root_dir=str(root1), config_path=str(cf))
    old_sl = chat.command_handler.session_logger
    chat.set_root_dir(str(root2))
    assert chat.command_handler.session_logger is not old_sl, (
        "command_handler.session_logger must be updated after root switch"
    )
    assert chat.command_handler.session_logger is chat.session_logger


# =========================================================================
# set_root_dir old_root resolve crash on broken symlink
# =========================================================================


def test_set_root_dir_with_broken_symlink_old_root(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    cf = config_dir / "config.json"
    _minimal_config_for_llmchat(str(cf))

    root1 = tmp_path / "old_project"
    root1.mkdir()
    chat = LLMChat(root_dir=str(root1), config_path=str(cf))

    root2 = tmp_path / "new_root"
    root2.mkdir()
    # internal resolve_path(old_root) should cope with a broken path
    shutil.rmtree(str(root1))  # old root no longer exists
    chat.set_root_dir(str(root2))
    # should not raise


# =========================================================================
# file_processor helpers
# =========================================================================


def test_report_diff_new_file():
    _report_diff(None, "hello\nworld\n", "f.py")
    # should print insertions, not crash


def test_report_diff_modified_file():
    _report_diff("old line\n", "new line\nanother\n", "f.py")
    # should print insertions and deletions


def test_report_diff_no_changes():
    _report_diff("same\n", "same\n", "f.py")
    # should print no_changes


def test_write_file_atomic_and_creates_dirs(tmp_path):
    target = tmp_path / "deep" / "nest" / "file.txt"
    _write_file(target, "payload", preserve_permissions_from=None)
    assert target.read_text() == "payload"


# =========================================================================
# generate_query force_plain
# =========================================================================


def test_generate_query_force_plain():
    query, parser = generate_query("unused", [], [], "hi", force_plain=True)
    assert query == "hi"
    assert parser is not None
    # free-chat path yields plain query without prompting


# =========================================================================
# token-usage table (regression: wide cache-display overflow)
# =========================================================================


@patch("thin_wrap.t")
def test_token_table_large_values(mock_t):
    # make t() return the key so we can inspect calls
    mock_t.side_effect = lambda key, **kw: key

    from thin_wrap import LLMChat as _LLMChat_cls

    chat = _LLMChat_cls.__new__(_LLMChat_cls)
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "prompt_cache_hit_tokens": 100,
    }
    chat._report_token_usage("q", "r", usage=usage, duration_ms=1500)
    # should not crash on 13-char cache_display like "100 (100%)"


# =========================================================================
# UI.numbered_selection smoke (non-interactive path tested via prompt_toolkit)
# =========================================================================


@patch("ui.PromptSession")
def test_numbered_selection_item_choice(mock_session_cls):
    mock_session = MagicMock()
    mock_session.prompt.return_value = "2"
    mock_session_cls.return_value = mock_session

    with patch("ui.t", side_effect=lambda k, **kw: k):
        st, v = UI.numbered_selection(
            items=["a", "b", "c"],
            title="T",
            prompt="P",
            zero_label="Z",
        )
    assert st == "item"
    assert v == "b"


@patch("ui.PromptSession")
def test_numbered_selection_zero_choice(mock_session_cls):
    mock_session = MagicMock()
    mock_session.prompt.return_value = "0"
    mock_session_cls.return_value = mock_session

    with patch("ui.t", side_effect=lambda k, **kw: k):
        st, v = UI.numbered_selection(
            items=["a", "b"],
            title="T",
            prompt="P",
            zero_label="Z",
        )
    assert st == "zero"
    assert v is None


@patch("ui.PromptSession")
def test_numbered_selection_manual_entry(mock_session_cls):
    mock_session = MagicMock()
    mock_session.prompt.return_value = "my-custom-path"
    mock_session_cls.return_value = mock_session

    with patch("ui.t", side_effect=lambda k, **kw: k):
        st, v = UI.numbered_selection(
            items=["a"],
            title="T",
            prompt="P",
            zero_label="Z",
            allow_manual=True,
        )
    assert st == "manual"
    assert v == "my-custom-path"


# =========================================================================
# config cache
# =========================================================================


def test_config_cache_hit(tmp_path, monkeypatch):
    cf = tmp_path / "config.json"
    _minimal_config_for_llmchat(str(cf))

    with patch("config._CONFIG_PATH", str(cf)):
        config.invalidate()
        m1 = config.get_models()
        m2 = config.get_models()
        assert m1 is m2, "cache should return same dict for unchanged file"


def test_config_invalidate_clears_cache(tmp_path, monkeypatch):
    cf = tmp_path / "config.json"
    _minimal_config_for_llmchat(str(cf))

    with patch("config._CONFIG_PATH", str(cf)):
        config.invalidate()
        m1 = config.get_models()
        config.invalidate()
        m2 = config.get_models()
        assert m1 is not m2, "invalidate should force re-read"
