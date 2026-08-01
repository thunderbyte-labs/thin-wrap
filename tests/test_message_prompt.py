"""Tests for the app-owned "Message" prompt header."""

import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from input_handler import InputHandler
from strings import t
from thin_wrap import LLMChat

MESSAGE_LINE = t("prompts.input_hint").rstrip("\n")


def _chat():
    return LLMChat.__new__(LLMChat)


def test_print_message_prompt_empty_context(capsys):
    chat = _chat()
    chat.editable_files = []
    chat.readable_files = []
    chat.root_dir = None
    chat._print_message_prompt()
    out = capsys.readouterr().out
    assert MESSAGE_LINE in out
    assert "Editable" not in out
    assert "Readable" not in out
    assert chat._message_prompt_height == 3


def test_print_message_prompt_non_empty_context(capsys):
    chat = _chat()
    chat.editable_files = ["/proj/hello.s"]
    chat.readable_files = ["/proj/notes.md"]
    chat.root_dir = "/proj"
    chat._print_message_prompt()
    out = capsys.readouterr().out
    assert "Editable (1): hello.s" in out
    assert "Readable (1): notes.md" in out
    assert MESSAGE_LINE in out
    # files summary comes before the Message separator
    assert out.index("Editable") < out.index(MESSAGE_LINE)
    assert chat._message_prompt_height == 5


def test_print_message_prompt_printed_once(capsys):
    chat = _chat()
    chat.editable_files = ["/proj/hello.s"]
    chat.readable_files = []
    chat.root_dir = "/proj"
    chat._print_message_prompt()
    out = capsys.readouterr().out
    assert out.count("Message ---------------------") == 1


def test_input_prompt_message_is_empty():
    with patch("input_handler.PromptSession") as mock_session:
        session = Mock()
        session.prompt.return_value = ""
        mock_session.return_value = session
        InputHandler().get_input_with_editing()
    kwargs = mock_session.call_args.kwargs
    assert kwargs["message"] == ""


def test_refresh_message_prompt_redraws_in_place(capsys):
    chat = _chat()
    chat.editable_files = []
    chat.readable_files = []
    chat.root_dir = "/proj"
    chat._print_message_prompt()
    capsys.readouterr()  # discard the initial block

    # empty context block = 3 lines; empty draft adds 1 line from prompt exit
    chat.editable_files = ["/proj/new.s"]
    chat._refresh_message_prompt(draft="")
    out = capsys.readouterr().out
    assert out.startswith("\x1b[4A")  # back up over block(3) + prompt-exit(1)
    assert "\x1b[J" in out
    assert "Editable (1): new.s" in out


def test_refresh_message_prompt_multi_line_draft(capsys):
    chat = _chat()
    chat.editable_files = []
    chat.readable_files = []
    chat.root_dir = None
    chat._print_message_prompt()
    capsys.readouterr()

    chat._refresh_message_prompt(draft="line1\nline2")
    out = capsys.readouterr().out
    # block(3) + draft(2 lines)
    assert out.startswith("\x1b[5A")


def test_refresh_message_prompt_no_header_prints_fresh(capsys):
    chat = _chat()
    chat.editable_files = []
    chat.readable_files = []
    chat.root_dir = None
    chat._message_prompt_height = 0
    chat._refresh_message_prompt()
    out = capsys.readouterr().out
    assert not out.startswith("\x1b[")  # nothing to move up over
    assert MESSAGE_LINE in out


def test_after_file_menu_ok_uses_refresh(capsys):
    chat = _chat()
    chat.editable_files = []
    chat.readable_files = []
    chat.root_dir = "/proj"
    chat._print_message_prompt()
    capsys.readouterr()

    chat.editable_files = ["/proj/a.s"]
    chat._after_file_menu(menu_ok=True)
    out = capsys.readouterr().out
    assert "\x1b[4A" in out
    assert "Editable (1): a.s" in out


def test_after_file_menu_not_ok_prints_fresh(capsys):
    chat = _chat()
    chat.editable_files = []
    chat.readable_files = []
    chat.root_dir = None
    chat._print_message_prompt()
    capsys.readouterr()

    chat._after_file_menu(menu_ok=False)
    out = capsys.readouterr().out
    assert not out.startswith("\x1b[")  # fresh header, no cursor-up
    assert MESSAGE_LINE in out
