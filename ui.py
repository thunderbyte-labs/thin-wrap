"""UI utilities for LLM Terminal Chat"""

import logging
import os
import re
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import PathCompleter
from rich.console import Console
from rich.markdown import Markdown

from strings import t

logger = logging.getLogger(__name__)

# Matches inline markdown links "[label](url)" while excluding images "![alt](src)"
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\((https?://[^)\s]+)\)")


def make_links_visible(text: str) -> str:
    """Make link targets visible as plain text for terminals without OSC 8 support.

    Transforms "[label](url)" into "[label](url) (url)" so the URL can be
    auto-detected and Ctrl+Clicked (or copied) in any terminal, including those
    that fail to honor OSC 8 hyperlinks (e.g. Konsole).
    """
    return MARKDOWN_LINK_RE.sub(
        lambda m: f"[{m.group(1)}]({m.group(2)}) ({m.group(2)})", text
    )


class UI:
    # ANSI color codes
    COLORS = {
        "BLACK": "\033[30m",
        "RED": "\033[31m",
        "GREEN": "\033[32m",
        "YELLOW": "\033[33m",
        "BLUE": "\033[34m",
        "MAGENTA": "\033[35m",
        "CYAN": "\033[36m",
        "WHITE": "\033[37m",
        "BRIGHT_BLACK": "\033[90m",
        "BRIGHT_RED": "\033[91m",
        "BRIGHT_GREEN": "\033[92m",
        "BRIGHT_YELLOW": "\033[93m",
        "BRIGHT_BLUE": "\033[94m",
        "BRIGHT_MAGENTA": "\033[95m",
        "BRIGHT_WHITE": "\033[97m",
        "BOLD": "\033[1m",
        "UNDERLINE": "\033[4m",
        "RESET": "\033[0m",
    }

    @staticmethod
    def colorize(text, color):
        """Add color to text using ANSI codes"""
        if color in UI.COLORS:
            return f"{UI.COLORS[color]}{text}{UI.COLORS['RESET']}"
        return text

    @staticmethod
    def print_banner(script_directory):
        """Print application banner"""
        banner_file = os.path.join(script_directory, "banner.txt")
        if os.path.exists(banner_file):
            with open(banner_file, encoding="utf-8") as f:
                banner_content = f.read()
            print(t("startup.banner_content", value=banner_content))
        else:
            print(t("separators.banner_line"))
            print(t("startup.banner_title"))
            print(t("separators.banner_line"))

    @staticmethod
    def show_startup_message():
        """Show startup help message"""
        print("\n" + t("startup.welcome"))
        print(t("separators.startup_line"))
        print()
        print(t("startup.send_part1") + t("keys.alt_enter") + t("startup.send_part2"))
        print(t("startup.files_part1") + t("keys.ctrl_b") + t("startup.files_part2"))
        print(t("startup.help_part1") + t("keys.slash_help") + t("startup.help_part2"))

    @staticmethod
    def show_exit_message(log_path):
        """Show exit message with log location"""
        if log_path:
            print("\n" + t("startup.session_log_saved"))
            print(f"{log_path}")
        print("\n" + t("common.goodbye"))

    @staticmethod
    def render_markdown(text):
        """Render markdown text with glow-like formatting."""
        if not text:
            return
        try:
            console = Console()
            md = Markdown(make_links_visible(text))
            console.print(md)
        except Exception:
            # Log error with traceback and fallback to plain print if markdown rendering fails
            logger.exception("Failed to render markdown")
            print(make_links_visible(text))

    @staticmethod
    def interactive_selection(
        prompt_title,
        prompt_message,
        no_items_message,
        items,
        item_formatter=lambda x: x,
        allow_new=False,
        new_item_validator=lambda x: True,
        new_item_error=None,
    ):
        """
        Generic interactive selection function with history support
        """
        if new_item_error is None:
            new_item_error = t("prompts.new_item_error")
        completer = PathCompleter(expanduser=True) if allow_new else None
        session = PromptSession(completer=completer)

        while True:
            if items:
                print(t("prompts.title_value", value=prompt_title))
                for i, item in enumerate(items, 1):
                    print(t("menus.item_format", index=i, item=item_formatter(item)))
                print(prompt_message)
            else:
                print(t("prompts.no_items_value", value=no_items_message))
                if allow_new:
                    print(t("prompts.enter_item_path"))

            try:
                user_input = session.prompt(t("common.prompt_arrow")).strip()
            except (KeyboardInterrupt, EOFError):
                print(t("common.selection_cancelled"))
                raise

            if not user_input:
                print(f"{t('common.error_prefix')} {t('common.empty_input')}")
                continue

            # Numeric selection from items
            if items and user_input.isdigit():
                idx = int(user_input) - 1
                if 0 <= idx < len(items):
                    chosen = items[idx]
                    print(f"{t('common.selected_prefix')} {item_formatter(chosen)}")
                    return chosen
                else:
                    print(
                        f"{t('common.error_prefix')} {t('common.number_out_of_range')}"
                    )
                    continue

            # Manual entry (only if allow_new is True)
            if allow_new:
                try:
                    new_item = Path(user_input).expanduser().resolve(strict=False)
                    if new_item_validator(new_item):
                        resolved_str = str(new_item)
                        print(
                            f"{t('common.using_prefix')} {item_formatter(resolved_str)}"
                        )
                        return resolved_str
                    else:
                        print(
                            f"{t('common.error_prefix')} {new_item_error}: {user_input}"
                        )
                except Exception as e:
                    print(
                        f"{t('common.error_prefix')} {t('common.invalid_input', error=e)}"
                    )
            else:
                print(f"{t('common.error_prefix')} {t('prompts.enter_valid_number')}")

    @staticmethod
    def numbered_selection(
        items,
        *,
        title,
        prompt,
        zero_label=None,
        allow_manual=False,
        completer=None,
        item_formatter=lambda x: x,
    ):
        """
        Generic numbered-menu selection with an optional "option 0".

        Returns ``(selection_type, value)`` where *selection_type* is one of
        ``'zero'``, ``'item'`` (a pre-existing list entry) or ``'manual'``
        (raw user input).  Raises ``KeyboardInterrupt`` on cancel.
        """
        session = PromptSession(completer=completer) if completer else PromptSession()

        while True:
            print(title)
            if zero_label is not None:
                print(t("menus.option_zero", label=zero_label))
            for i, item in enumerate(items, 1):
                print(t("menus.item_format", index=i, item=item_formatter(item)))
            print(prompt)

            try:
                user_input = session.prompt(t("common.prompt_arrow")).strip()
            except (KeyboardInterrupt, EOFError):
                print(t("common.selection_cancelled"))
                raise

            if not user_input:
                print(f"{t('common.error_prefix')} {t('common.empty_input')}")
                continue

            if user_input.isdigit():
                idx = int(user_input)
                if idx == 0 and zero_label is not None:
                    print(f"{t('common.selected_prefix')} {zero_label}")
                    return ("zero", None)
                if 1 <= idx <= len(items):
                    chosen = items[idx - 1]
                    print(f"{t('common.selected_prefix')} {item_formatter(chosen)}")
                    return ("item", chosen)
                print(f"{t('common.error_prefix')} {t('common.number_out_of_range')}")
                continue

            if allow_manual:
                return ("manual", user_input)

            print(f"{t('common.error_prefix')} {t('prompts.enter_valid_number')}")
