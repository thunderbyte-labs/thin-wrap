"""Tests for the app-owned "Message" prompt header and file-context block."""

import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from prompt_toolkit.formatted_text import to_plain_text

import input_handler
from input_handler import InputHandler
from strings import t
from thin_wrap import LLMChat

MESSAGE_LINE = t("prompts.input_hint").rstrip("\n")


def _chat():
    return LLMChat.__new__(LLMChat)


def test_print_message_prompt_is_only_the_separator(capsys):
    chat = _chat()
    chat.editable_files = ["/proj/hello.s"]
    chat.readable_files = []
    chat.root_dir = "/proj"
    chat._print_message_prompt()
    out = capsys.readouterr().out
    assert MESSAGE_LINE in out
    assert "Editable" not in out
    assert "Readable" not in out
    assert "File context:" not in out


def test_file_context_block_formats_files(capsys):
    chat = _chat()
    chat.editable_files = ["/proj/hello.s"]
    chat.readable_files = ["/proj/notes.md"]
    chat.root_dir = "/proj"
    block = chat._file_context_block()
    assert "File context:" in block
    assert "Editable (1): hello.s" in block
    assert "Readable (1): notes.md" in block
    assert "\x1b[32m" in block  # GREEN


def test_file_context_block_empty_when_no_files():
    chat = _chat()
    chat.editable_files = []
    chat.readable_files = []
    chat.root_dir = None
    assert chat._file_context_block() == ""


def test_print_file_context_block_writes_scrollback(capsys):
    chat = _chat()
    chat.editable_files = ["/proj/hello.s"]
    chat.readable_files = []
    chat.root_dir = "/proj"
    chat._print_file_context_block()
    out = capsys.readouterr().out
    assert "File context:" in out
    assert "Editable (1): hello.s" in out


def test_print_file_context_block_empty_is_noop(capsys):
    chat = _chat()
    chat.editable_files = []
    chat.readable_files = []
    chat.root_dir = None
    chat._print_file_context_block()
    assert capsys.readouterr().out == ""


def test_exit_cleanly_erases_message_header(capsys):
    chat = _chat()
    chat._message_prompt_shown = True
    chat.session_logger = Mock()
    chat.session_logger.get_session_path.return_value = "/tmp/nonexistent"
    with patch("thin_wrap.UI.show_exit_message"):
        chat._exit_cleanly()
    out = capsys.readouterr().out
    assert "\x1b[4A\x1b[J" in out


def test_exit_cleanly_no_erase_without_header(capsys):
    chat = _chat()
    chat.session_logger = Mock()
    chat.session_logger.get_session_path.return_value = "/tmp/nonexistent"
    with patch("thin_wrap.UI.show_exit_message"):
        chat._exit_cleanly()
    out = capsys.readouterr().out
    assert "\x1b[4A" not in out


def test_input_context_provider_wired_into_layout():
    captured = {}
    real_ftc = input_handler.FormattedTextControl

    def fake_ftc(text, **kwargs):
        captured["text"] = text
        return real_ftc(text, **kwargs)

    def provider():
        return "\x1b[32m\nFile context:\nEditable (1): a.s\x1b[0m"

    with (
        patch("input_handler.Application") as mock_app_cls,
        patch("input_handler.FormattedTextControl", side_effect=fake_ftc),
    ):
        mock_app = Mock()
        mock_app_cls.return_value = mock_app
        mock_app.run.return_value = "the message"

        result = InputHandler().get_input_with_editing(
            default="draft", context_provider=provider
        )

    assert result == "the message"
    assert callable(captured["text"])
    assert "File context" in to_plain_text(captured["text"]())
    assert "Editable (1): a.s" in to_plain_text(captured["text"]())
    assert mock_app_cls.call_args.kwargs["erase_when_done"] is True
