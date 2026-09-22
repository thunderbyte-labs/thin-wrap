#!/usr/bin/env python3
"""Tests for /reload keyword search: scoring, snippets and flow."""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from command_handler import (
    CommandHandler,
    _extract_full_text,
    _make_search_formatter,
    _score_session,
)

# =========================================================================
# _extract_full_text
# =========================================================================


def test_extract_full_text_empty():
    assert _extract_full_text(None) == ""
    assert _extract_full_text({}) == ""


def test_extract_full_text_concatenates():
    data = {
        "conversation_history": [
            {"content": "hello"},
            {"role": "user", "content": "world"},
            {"role": "assistant", "content": ""},
        ]
    }
    assert _extract_full_text(data) == "hello\nworld"


# =========================================================================
# _score_session
# =========================================================================


def test_score_session_title_match_weighs_more():
    score, snippets = _score_session(
        ["python"], name="python project", content="no match here"
    )
    assert score == 3
    assert snippets == []


def test_score_session_content_match():
    score, snippets = _score_session(
        ["api"], name="", content="The API endpoint works."
    )
    assert score == 1
    assert len(snippets) == 1
    assert "API" in snippets[0]


def test_score_session_no_match():
    score, snippets = _score_session(["zebra"], name="", content="nothing here")
    assert score == 0
    assert snippets == []


def test_score_session_empty_keywords():
    score, snippets = _score_session([], name="name", content="content")
    assert score == 0
    assert snippets == []


def test_score_session_case_insensitive():
    score, _ = _score_session(["DOCKER"], name="", content="Docker config docker run")
    assert score == 2


def test_score_session_title_and_content_combined():
    score, _ = _score_session(
        ["fix"], name="fix login bug", content="fix the bug and fix again"
    )
    assert score == 3 + 2


def test_score_session_max_three_snippets():
    content = " ".join(f"word{i} kw" for i in range(10))
    score, snippets = _score_session(["kw"], name="", content=content)
    assert len(snippets) == 3


def test_score_session_whole_word_only():
    """Partial-word matches are ignored (whole-word matching)."""
    score, _ = _score_session(["cat"], name="", content="catalog category")
    assert score == 0


# =========================================================================
# _handle_reload search flow
# =========================================================================


class _MockChatApp:
    FREE_CHAT_MODE = "FREE_CHAT_MODE"
    root_dir = "/proj"


def _make_handler():
    chat = _MockChatApp()
    session_logger = MagicMock()
    session_logger.list_available_sessions.return_value = [
        "/conv/a.toml.zip",
        "/conv/b.toml.zip",
    ]
    session_logger.load_session_metadata.side_effect = lambda p: {
        "name": "alpha" if "a" in p else "beta",
        "interaction_count": 1,
    }
    session_logger.load_session.side_effect = lambda p: {
        "conversation_history": [
            {
                "content": "talking about docker containers here"
                if "a" in p
                else "plain chat"
            }
        ]
    }
    return chat, CommandHandler(
        llm_client=MagicMock(),
        session_logger=session_logger,
        input_handler=MagicMock(),
        chat_app=chat,
    )


def test_reload_selects_by_number_from_visible_list():
    """Typing a number selects straight from the visible full list."""
    chat, handler = _make_handler()
    with patch("builtins.input", side_effect=["1"]):
        handler._handle_reload()
    handler.llm_client.load_conversation.assert_called_once_with(
        [{"content": "talking about docker containers here"}]
    )


def test_reload_search_selects_matching_session():
    """Typing keywords ranks the matching session, which is then selectable."""
    chat, handler = _make_handler()
    with patch("builtins.input", side_effect=["docker", "1"]):
        handler._handle_reload()
    handler.llm_client.load_conversation.assert_called_once_with(
        [{"content": "talking about docker containers here"}]
    )


def test_reload_no_match_offers_search_again():
    """A dead-end search lets the user type new keywords until something matches."""
    chat, handler = _make_handler()
    with patch("builtins.input", side_effect=["zzz", "docker", "1"]):
        handler._handle_reload()
    handler.llm_client.load_conversation.assert_called_once_with(
        [{"content": "talking about docker containers here"}]
    )


def test_reload_no_match_can_go_back_to_full_list():
    """A dead-end search can press Enter to fall back to the full list."""
    chat, handler = _make_handler()
    with patch("builtins.input", side_effect=["zzz", "", "2"]):
        handler._handle_reload()
    handler.llm_client.load_conversation.assert_called_once_with(
        [{"content": "plain chat"}]
    )


def test_reload_conclusive_search_can_go_back_with_empty():
    """From conclusive results, an empty Enter falls back to the full list."""
    chat, handler = _make_handler()
    with patch("builtins.input", side_effect=["docker", "", "1"]):
        handler._handle_reload()
    handler.llm_client.load_conversation.assert_called_once_with(
        [{"content": "talking about docker containers here"}]
    )


def test_reload_back_from_results_then_search_again():
    """Backing out of results lets the user search again from the full list."""
    chat, handler = _make_handler()
    with patch("builtins.input", side_effect=["docker", "", "docker", "1"]):
        handler._handle_reload()
    handler.llm_client.load_conversation.assert_called_once_with(
        [{"content": "talking about docker containers here"}]
    )


def test_reload_blank_input_redraws_list():
    """Blank input at the main prompt just redraws the full list."""
    chat, handler = _make_handler()
    with patch("builtins.input", side_effect=["", "1"]):
        handler._handle_reload()
    handler.llm_client.load_conversation.assert_called_once_with(
        [{"content": "talking about docker containers here"}]
    )


def test_reload_whitespace_input_redraws_list():
    """Whitespace-only input at the main prompt just redraws the full list."""
    chat, handler = _make_handler()
    with patch("builtins.input", side_effect=["   ", "1"]):
        handler._handle_reload()
    handler.llm_client.load_conversation.assert_called_once_with(
        [{"content": "talking about docker containers here"}]
    )


def test_reload_shows_menu_before_input_prompt(capsys):
    """The list is shown before the number-or-keywords prompt appears."""
    chat, handler = _make_handler()
    responses = iter(["1"])

    def fake_input(prompt=""):
        if prompt:
            print(prompt, end="")
        return next(responses)

    with patch("builtins.input", side_effect=fake_input):
        handler._handle_reload()
    out = capsys.readouterr().out
    assert out.index("Available conversations:") < out.index(
        "Enter a conversation number or search keywords:"
    )


def test_reload_cancel_at_prompt():
    """Ctrl+C at the prompt cancels cleanly."""
    chat, handler = _make_handler()
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        handler._handle_reload()  # should not raise


def test_rank_sessions_sorts_by_score():
    """Ranking sorts by score descending (title beats content)."""
    chat = _MockChatApp()
    session_logger = MagicMock()
    session_logger.load_session.side_effect = lambda p: {
        "conversation_history": [{"content": "mentions docker" if p == "/b" else ""}]
    }
    handler = CommandHandler(
        llm_client=MagicMock(),
        session_logger=session_logger,
        input_handler=MagicMock(),
        chat_app=chat,
    )
    metadata_cache = {"/a": {"name": "docker project"}, "/b": {}}
    ranked = handler._rank_sessions(["/a", "/b"], metadata_cache, ["docker"])
    # /a: title match → 3 ; /b: content match → 1
    assert [path for _, path, _ in ranked] == ["/a", "/b"]
    assert [score for score, _, _ in ranked] == [3, 1]


def test_rank_sessions_requires_all_keywords():
    """Sessions missing any keyword are excluded from the results."""
    chat = _MockChatApp()
    session_logger = MagicMock()
    session_logger.load_session.side_effect = lambda p: {
        "conversation_history": [{"content": "docker only" if p == "/a" else ""}]
    }
    handler = CommandHandler(
        llm_client=MagicMock(),
        session_logger=session_logger,
        input_handler=MagicMock(),
        chat_app=chat,
    )
    metadata_cache = {"/a": {"name": ""}, "/b": {"name": ""}}
    ranked = handler._rank_sessions(
        ["/a", "/b"], metadata_cache, ["docker", "kubernetes"]
    )
    assert ranked == []


def test_search_formatter_includes_score_and_snippet():
    """The search formatter appends score and a matching snippet."""
    ranked = [(3, "/conv/a.toml.zip", ["docker containers here"])]
    metadata = {"/conv/a.toml.zip": {"name": "alpha", "interaction_count": 1}}
    formatter = _make_search_formatter(metadata, ranked)
    rendered = formatter("/conv/a.toml.zip")
    assert "score: 3" in rendered
    assert "docker" in rendered


if __name__ == "__main__":
    test_extract_full_text_empty()
    test_extract_full_text_concatenates()
    test_score_session_title_match_weighs_more()
    test_score_session_content_match()
    test_score_session_no_match()
    test_score_session_empty_keywords()
    test_score_session_case_insensitive()
    test_score_session_title_and_content_combined()
    test_score_session_max_three_snippets()
    test_score_session_whole_word_only()
    test_reload_selects_by_number_from_visible_list()
    test_reload_search_selects_matching_session()
    test_reload_no_match_offers_search_again()
    test_reload_no_match_can_go_back_to_full_list()
    test_reload_conclusive_search_can_go_back_with_empty()
    test_reload_back_from_results_then_search_again()
    test_reload_blank_input_redraws_list()
    test_reload_whitespace_input_redraws_list()
    test_reload_cancel_at_prompt()
    test_rank_sessions_sorts_by_score()
    test_rank_sessions_requires_all_keywords()
    test_search_formatter_includes_score_and_snippet()
    print("\n✅ All reload search tests passed!")
