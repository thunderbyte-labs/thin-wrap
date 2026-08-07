"""Tests for the app-owned "Message" prompt header and file-context block."""

import os
import re
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
    assert "Editable (1):" in block
    assert "Readable (1):" in block
    assert "hello.s" in block
    assert "notes.md" in block
    # labels green, values default color
    assert "\x1b[32mFile context:\x1b[0m" in block
    assert "\x1b[32mEditable (1):\x1b[0m hello.s" in block
    assert "\x1b[32mReadable (1):\x1b[0m notes.md" in block
    assert "\x1b[32mhello.s" not in block  # value is not green


def test_file_context_block_none_value_default_color(capsys):
    chat = _chat()
    chat.editable_files = []
    chat.readable_files = ["/proj/notes.md"]
    chat.root_dir = "/proj"
    block = chat._file_context_block()
    assert "\x1b[32mEditable:\x1b[0m None" in block
    assert "\x1b[32mReadable (1):\x1b[0m notes.md" in block


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
    assert "Editable (1):" in out
    assert "hello.s" in out


def test_print_file_context_block_empty_is_noop(capsys):
    chat = _chat()
    chat.editable_files = []
    chat.readable_files = []
    chat.root_dir = None
    chat._print_file_context_block()
    assert capsys.readouterr().out == ""


def test_erase_pending_message_prompt(capsys):
    chat = _chat()
    chat._message_prompt_shown = True
    chat._erase_pending_message_prompt()
    out = capsys.readouterr().out
    assert "\x1b[3A\x1b[J" in out


def test_erase_pending_message_prompt_no_header(capsys):
    chat = _chat()
    chat._erase_pending_message_prompt()
    assert capsys.readouterr().out == ""


def test_print_command_header_echoes_command(capsys):
    chat = _chat()
    chat._print_command_header("/reload")
    out = capsys.readouterr().out
    assert "Command: /reload" in out
    assert "\x1b[92m" in out  # BRIGHT_GREEN header


def test_print_command_header_strips_whitespace(capsys):
    chat = _chat()
    chat._print_command_header("  /nameconv  ")
    assert "Command: /nameconv" in capsys.readouterr().out


def test_command_header_is_50_chars_with_symmetric_dashes(capsys):
    for cmd in ("/h", "/help", "/reload", "/nameconv", "/rootdir"):
        chat = _chat()
        chat._print_command_header(cmd)
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if "Command:" in line]
    assert len(lines) == len(("/h", "/help", "/reload", "/nameconv", "/rootdir"))
    for line in lines:
        plain = line.replace("\x1b[92m", "").replace("\x1b[0m", "")
        assert len(plain) == 50, plain
        dash_runs = re.findall(r"-+", plain)
        assert len(dash_runs) == 2, plain
        assert abs(len(dash_runs[0]) - len(dash_runs[1])) <= 1, plain


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
