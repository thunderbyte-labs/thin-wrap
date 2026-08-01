#!/usr/bin/env python3
"""Tests for the /nameconv feature (conversation naming)."""

import os
import shutil
import sys
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from command_handler import CommandHandler, _extract_suggested_name
from session_logger import SessionLogger, sanitize_conversation_name

HISTORY = [
    {
        "timestamp": "2025-01-01T00:00:00",
        "role": "user",
        "content": "hello",
    },
    {
        "timestamp": "2025-01-01T00:00:01",
        "role": "assistant",
        "content": "hi",
    },
]


def test_sanitize_valid_name():
    """Valid names are lowercased and spaces become dashes."""
    assert sanitize_conversation_name("hello world") == (None, "hello-world")
    assert sanitize_conversation_name("Bug Fix Session 42") == (
        None,
        "bug-fix-session-42",
    )


def test_sanitize_collapses_spaces():
    """Leading, trailing and consecutive spaces are collapsed."""
    assert sanitize_conversation_name("  hello    world  ") == (None, "hello-world")


def test_sanitize_rejects_invalid_chars():
    """Only a-z, 0-9 and spaces are allowed."""
    error, slug = sanitize_conversation_name("hello/world")
    assert error == "nameconv_invalid_chars"
    assert slug is None
    error, _ = sanitize_conversation_name("a b@c")
    assert error == "nameconv_invalid_chars"


def test_sanitize_rejects_empty():
    """Empty names are rejected."""
    assert sanitize_conversation_name("")[0] == "nameconv_empty"
    assert sanitize_conversation_name("   ")[0] == "nameconv_empty"


def test_sanitize_rejects_too_many_words():
    """Names over 12 words are rejected."""
    name = " ".join(f"w{i}" for i in range(13))
    error, slug = sanitize_conversation_name(name)
    assert error == "nameconv_too_many_words"
    assert slug is None
    # 12 words is the maximum allowed
    name12 = " ".join(f"w{i}" for i in range(12))
    error, slug = sanitize_conversation_name(name12)
    assert error is None
    assert len(slug.split("-")) == 12


def test_set_name_renames_existing_file():
    """set_name renames the on-disk file and updates the session path."""
    original = config.CONVERSATIONS_DIR
    temp_dir = tempfile.mkdtemp()
    config.CONVERSATIONS_DIR = temp_dir

    try:
        logger = SessionLogger(script_directory="/tmp", root_dir=None)
        old_path = logger.get_session_path()
        logger.save_session(HISTORY)
        assert os.path.exists(old_path)

        new_path = logger.set_name("my-conversation")
        assert new_path.endswith(f"{logger._ts_str}_my-conversation.toml.zip")
        assert logger.get_session_path() == new_path
        assert not os.path.exists(old_path)
        assert os.path.exists(new_path)

        # Subsequent saves write to the renamed file
        logger.save_session(HISTORY)
        assert os.path.exists(new_path)
        print("✓ set_name renames the file and stays persistent")
    finally:
        config.CONVERSATIONS_DIR = original
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_set_name_before_first_save():
    """set_name works even when no file exists yet."""
    original = config.CONVERSATIONS_DIR
    temp_dir = tempfile.mkdtemp()
    config.CONVERSATIONS_DIR = temp_dir

    try:
        logger = SessionLogger(script_directory="/tmp", root_dir=None)
        assert not os.path.exists(logger.get_session_path())
        new_path = logger.set_name("brand-new")
        # First save creates the file with the final name
        logger.save_session(HISTORY)
        assert os.path.exists(new_path)
        assert new_path.endswith("_brand-new.toml.zip")
        print("✓ set_name works before the first save")
    finally:
        config.CONVERSATIONS_DIR = original
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_set_name_replaces_previous_name():
    """A second set_name replaces the previous name instead of stacking."""
    original = config.CONVERSATIONS_DIR
    temp_dir = tempfile.mkdtemp()
    config.CONVERSATIONS_DIR = temp_dir

    try:
        logger = SessionLogger(script_directory="/tmp", root_dir=None)
        logger.save_session(HISTORY)
        first = logger.set_name("first-name")
        assert os.path.exists(first)
        second = logger.set_name("second-name")
        assert second.endswith("_second-name.toml.zip")
        assert not os.path.exists(first)
        assert os.path.exists(second)
        print("✓ set_name replaces the previous name")
    finally:
        config.CONVERSATIONS_DIR = original
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_name_in_metadata():
    """The conversation name is stored in and read from metadata."""
    original = config.CONVERSATIONS_DIR
    temp_dir = tempfile.mkdtemp()
    config.CONVERSATIONS_DIR = temp_dir

    try:
        logger = SessionLogger(script_directory="/tmp", root_dir=None)
        logger.save_session(HISTORY)
        logger.set_name("named-session")
        saved_path = logger.save_session(HISTORY)

        metadata = logger.load_session_metadata(saved_path)
        assert metadata is not None
        assert metadata["name"] == "named-session"
        print("✓ name is persisted in session metadata")
    finally:
        config.CONVERSATIONS_DIR = original
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_empty_history_not_saved():
    """Empty conversations are never persisted (and never deleted)."""
    original = config.CONVERSATIONS_DIR
    temp_dir = tempfile.mkdtemp()
    config.CONVERSATIONS_DIR = temp_dir

    try:
        logger = SessionLogger(script_directory="/tmp", root_dir=None)
        path = logger.get_session_path()
        assert not os.path.exists(path)

        # Saving an empty history creates nothing
        result = logger.save_session([])
        assert result is None
        assert not os.path.exists(path)

        # Saving non-empty creates the file
        logger.save_session(HISTORY)
        assert os.path.exists(path)

        # Saving empty afterwards must not delete the existing file
        result = logger.save_session([])
        assert result is None
        assert os.path.exists(path)
        print("✓ empty histories are never persisted")
    finally:
        config.CONVERSATIONS_DIR = original
        shutil.rmtree(temp_dir, ignore_errors=True)


# =========================================================================
# AI-suggested names (_extract_suggested_name + /nameconv AI flow)
# =========================================================================


def test_extract_suggested_name_clean():
    """A plain keyword response becomes a lowercase slug."""
    assert _extract_suggested_name("Why Jesus is King?") == "why-jesus-is-king"


def test_extract_suggested_name_strips_markdown_and_quotes():
    """Markdown, quotes and dashes are stripped from the suggestion."""
    assert _extract_suggested_name("**why jesus is king**") == "why-jesus-is-king"
    assert _extract_suggested_name("'hello world'") == "hello-world"


def test_extract_suggested_name_truncates_to_limit():
    """More than 12 words are truncated to the allowed maximum."""
    raw = " ".join(f"w{i}" for i in range(20))
    slug = _extract_suggested_name(raw)
    assert len(slug.split("-")) == 12


def test_extract_suggested_name_rejects_garbage():
    """Non-alphanumeric responses are considered unusable."""
    assert _extract_suggested_name("!!!") is None
    assert _extract_suggested_name("🤖😀✨") is None
    assert _extract_suggested_name("") is None


def _make_nameconv_handler(generate_result, history):
    session_logger = MagicMock()
    llm_client = MagicMock()
    llm_client.conversation_history = history
    llm_client.generate.return_value = generate_result
    handler = CommandHandler(
        llm_client=llm_client,
        session_logger=session_logger,
        input_handler=MagicMock(),
        chat_app=MagicMock(),
    )
    return handler, session_logger


def test_nameconv_manual_still_works():
    """Typing a name keeps the original manual behavior."""
    handler, session_logger = _make_nameconv_handler(None, [])
    with patch("builtins.input", side_effect=["my name"]):
        handler._handle_nameconv([])
    session_logger.set_name.assert_called_once_with("my-name")


def test_nameconv_ai_suggestion_accepted():
    """Empty input asks the AI; pressing Enter accepts the suggestion."""
    handler, session_logger = _make_nameconv_handler(
        "Why Jesus is King?", [{"role": "user", "content": "hi"}]
    )
    with patch("builtins.input", side_effect=["", ""]):
        handler._handle_nameconv([])
    session_logger.set_name.assert_called_once_with("why-jesus-is-king")


def test_nameconv_ai_suggestion_modified():
    """The suggestion can be edited before applying."""
    handler, session_logger = _make_nameconv_handler(
        "Why Jesus is King?", [{"role": "user", "content": "hi"}]
    )
    with patch("builtins.input", side_effect=["", "why pythagore"]):
        handler._handle_nameconv([])
    session_logger.set_name.assert_called_once_with("why-pythagore")


def test_nameconv_ai_suggestion_cancelled():
    """Typing 'c' cancels without renaming."""
    handler, session_logger = _make_nameconv_handler(
        "Why Jesus is King?", [{"role": "user", "content": "hi"}]
    )
    with patch("builtins.input", side_effect=["", "c"]):
        handler._handle_nameconv([])
    session_logger.set_name.assert_not_called()


def test_nameconv_ai_no_content_falls_back_to_manual():
    """An empty conversation warns and falls back to manual naming."""
    handler, session_logger = _make_nameconv_handler("ignored", [])
    with patch("builtins.input", side_effect=["", "hello world"]):
        handler._handle_nameconv([])
    session_logger.set_name.assert_called_once_with("hello-world")


def test_nameconv_ai_failure_falls_back_to_manual():
    """An AI error falls back to manual naming without retrying."""
    handler, session_logger = _make_nameconv_handler(
        None, [{"role": "user", "content": "hi"}]
    )
    with patch("builtins.input", side_effect=["", "hello world"]):
        handler._handle_nameconv([])
    session_logger.set_name.assert_called_once_with("hello-world")


def test_nameconv_ai_unusable_falls_back_to_manual():
    """An unusable suggestion falls back to manual naming."""
    handler, session_logger = _make_nameconv_handler(
        "!!!", [{"role": "user", "content": "hi"}]
    )
    with patch("builtins.input", side_effect=["", "hello world"]):
        handler._handle_nameconv([])
    session_logger.set_name.assert_called_once_with("hello-world")


def test_collision_rolls_over_minute():
    """Collision avoidance rolls the timestamp over the minute boundary."""
    from datetime import datetime
    from unittest.mock import patch

    original = config.CONVERSATIONS_DIR
    temp_dir = tempfile.mkdtemp()
    config.CONVERSATIONS_DIR = temp_dir

    try:
        conv_dir = os.path.join(temp_dir, "free_chat")
        os.makedirs(conv_dir, exist_ok=True)
        # Occupied timestamp at second 59 → next free slot is the next minute
        with open(os.path.join(conv_dir, "session_20260801_123459.toml.zip"), "w"):
            pass

        fixed = datetime(2026, 8, 1, 12, 34, 59)
        with patch("session_logger.datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            logger = SessionLogger(script_directory="/tmp", root_dir=None)
            assert logger._ts_str == "20260801_123500"
        print("✓ collision avoidance rolls over the minute boundary")
    finally:
        config.CONVERSATIONS_DIR = original
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_sanitize_valid_name()
    test_sanitize_collapses_spaces()
    test_sanitize_rejects_invalid_chars()
    test_sanitize_rejects_empty()
    test_sanitize_rejects_too_many_words()
    test_set_name_renames_existing_file()
    test_set_name_before_first_save()
    test_set_name_replaces_previous_name()
    test_name_in_metadata()
    test_empty_history_not_saved()
    test_extract_suggested_name_clean()
    test_extract_suggested_name_strips_markdown_and_quotes()
    test_extract_suggested_name_truncates_to_limit()
    test_extract_suggested_name_rejects_garbage()
    test_nameconv_manual_still_works()
    test_nameconv_ai_suggestion_accepted()
    test_nameconv_ai_suggestion_modified()
    test_nameconv_ai_suggestion_cancelled()
    test_nameconv_ai_no_content_falls_back_to_manual()
    test_nameconv_ai_failure_falls_back_to_manual()
    test_nameconv_ai_unusable_falls_back_to_manual()
    test_collision_rolls_over_minute()
    print("\n✅ All nameconv tests passed!")
