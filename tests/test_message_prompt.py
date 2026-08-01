"""Tests for the app-owned "Message" prompt header."""

import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from input_handler import InputHandler
from strings import t
from thin_wrap import LLMChat


def _chat():
    return LLMChat.__new__(LLMChat)


def test_print_message_prompt_empty_context(capsys):
    chat = _chat()
    chat.editable_files = []
    chat.readable_files = []
    chat.root_dir = None
    chat._print_message_prompt()
    out = capsys.readouterr().out
    assert t("prompts.input_hint") in out
    assert "Editable" not in out
    assert "Readable" not in out


def test_print_message_prompt_non_empty_context(capsys):
    chat = _chat()
    chat.editable_files = ["/proj/hello.s"]
    chat.readable_files = ["/proj/notes.md"]
    chat.root_dir = "/proj"
    chat._print_message_prompt()
    out = capsys.readouterr().out
    assert "Editable (1): hello.s" in out
    assert "Readable (1): notes.md" in out
    assert t("prompts.input_hint") in out
    # files summary comes before the Message separator
    assert out.index("Editable") < out.index(t("prompts.input_hint"))


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
