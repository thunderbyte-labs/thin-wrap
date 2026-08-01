"""Command handling for LLM Terminal Chat"""

import os
import re
from collections.abc import Callable
from pathlib import Path

from prompt_toolkit.completion import PathCompleter

import config
from path_utils import resolve_path
from session_logger import CONVERSATION_NAME_MAX_WORDS, sanitize_conversation_name
from strings import t
from ui import UI


def _extract_full_text(session_data: dict) -> str:
    """Concatenate all message contents from a loaded session."""
    if not session_data:
        return ""
    parts = []
    for msg in session_data.get("conversation_history", []):
        content = msg.get("content", "")
        if content:
            parts.append(content)
    return "\n".join(parts)


def _score_session(
    keywords: list[str], name: str, content: str
) -> tuple[int, list[str]]:
    """
    Score a session and extract up to 3 snippets using whole-word matching.
    - Name matches: +3 per occurrence
    - Content matches: +1 per occurrence
    Returns (score, list_of_snippets)
    """
    if not keywords:
        return 0, []

    score = 0
    snippets = []
    name_lower = name.lower()
    content_lower = content.lower()

    for kw in keywords:
        kw_lower = kw.lower()
        if not kw_lower:
            continue
        pattern = re.compile(r"\b" + re.escape(kw_lower) + r"\b", re.IGNORECASE)

        # Title scoring
        for _ in pattern.finditer(name_lower):
            score += 3

        # Content scoring + snippet extraction (up to 3 total)
        for match in pattern.finditer(content_lower):
            score += 1
            if len(snippets) >= 3:
                continue

            start = match.start()
            ctx_start = max(0, start - 55)
            ctx_end = min(len(content), start + len(kw) + 55)
            snippet = content[ctx_start:ctx_end].replace("\n", " ").strip()
            if snippet and snippet not in snippets:
                snippets.append(snippet)

    return score, snippets[:3]


def _all_keywords_present(name: str, content: str, keywords: list[str]) -> bool:
    """Return True if every keyword appears as a whole word in name or content."""
    if not keywords:
        return True
    for kw in keywords:
        kw_lower = kw.lower()
        pattern = re.compile(r"\b" + re.escape(kw_lower) + r"\b", re.IGNORECASE)
        if not (pattern.search(name) or pattern.search(content)):
            return False
    return True


def _show_conversation_menu(
    items: list[str], item_formatter: Callable[[str], str]
) -> None:
    """Print the numbered conversation list (title and items only)."""
    print(t("prompts.title_value", value=t("prompts.available_conversations")))
    for i, item in enumerate(items, 1):
        print(t("menus.item_format", index=i, item=item_formatter(item)))


def _select_number(
    items: list[str],
    item_formatter: Callable[[str], str],
    allow_back: bool = False,
    back_hint: str | None = None,
) -> str | None:
    """Pick an item by number from the visible list.

    Returns the chosen item, or ``None`` when *allow_back* is set and the
    user presses Enter or types ``n`` to fall back to a wider selection.
    """
    while True:
        print(t("prompts.conversation_enter_number"))
        if allow_back and back_hint:
            print(back_hint)
        user_input = input(t("common.prompt_arrow")).strip().lower()
        if allow_back and (not user_input or user_input in ("n", "no", "back")):
            return None
        if not user_input:
            print(f"{t('common.error_prefix')} {t('common.empty_input')}")
            _show_conversation_menu(items, item_formatter)
            continue
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(items):
                chosen = items[idx]
                print(f"{t('common.selected_prefix')} {item_formatter(chosen)}")
                return chosen
            print(f"{t('common.error_prefix')} {t('common.number_out_of_range')}")
            _show_conversation_menu(items, item_formatter)
            continue
        print(f"{t('common.error_prefix')} {t('prompts.enter_valid_number')}")
        _show_conversation_menu(items, item_formatter)


def _make_search_formatter(
    metadata_cache: dict, ranked_sessions: list[tuple[int, str, list[str]]]
) -> Callable[[str], str]:
    """Build an item formatter that appends score and matching snippets."""

    def search_aware_formatter(path: str) -> str:
        base = format_session(path, metadata_cache.get(path))
        for score, p, snippets in ranked_sessions:
            if p == path:
                score_str = t("sessions.score_label", score=score)
                lines = [f"{base}  [{score_str}]"]
                for snip in snippets:
                    lines.append(t("sessions.snippet_prefix", snippet=snip))
                return "\n".join(lines)
        return base

    return search_aware_formatter


def _extract_suggested_name(raw: str) -> str | None:
    """Turn an LLM naming response into a valid slug, or ``None`` if unusable.

    Strips quotes/markdown, keeps only alphanumeric words, truncates to the
    conversation-name limit and applies the usual slug sanitization.
    """
    words = re.findall(r"[a-z0-9]+", raw.lower())
    if not words:
        return None
    if len(words) > CONVERSATION_NAME_MAX_WORDS:
        words = words[:CONVERSATION_NAME_MAX_WORDS]
    error_key, slug = sanitize_conversation_name(" ".join(words))
    if error_key:
        return None
    return slug


def format_session(path: str, meta: dict | None = None) -> str:
    """Format a session file path for the /reload listing.

    Displayed as ``{timestamp} · {name} ({count_label})`` with an optional
    preview suffix. The name is colored GREEN when present, otherwise
    ``*no name*`` is shown.
    """
    filename = os.path.basename(path)
    stem = filename.replace("session_", "").replace(".toml.zip", "")
    ts_match = re.fullmatch(r"(\d{8}_\d{6})(?:_(.*))?", stem)
    if ts_match:
        raw_ts = ts_match.group(1)
        timestamp = (
            f"{raw_ts[:4]}-{raw_ts[4:6]}-{raw_ts[6:8]} "
            f"{raw_ts[9:11]}:{raw_ts[11:13]}:{raw_ts[13:15]}"
        )
        filename_name = ts_match.group(2) or ""
    else:
        timestamp = stem
        filename_name = ""

    meta = meta or {}
    name = meta.get("name", "") or filename_name
    name_label = t("sessions.name_value", value=name) if name else t("sessions.no_name")

    count = meta.get("interaction_count", 0)
    if count == 1:
        count_label = t("sessions.message", count=count)
    else:
        count_label = t("sessions.messages", count=count)

    preview = meta.get("preview", "")
    if preview:
        if len(preview) > 50:
            preview = preview[:47] + "..."
        return t(
            "sessions.format_preview",
            timestamp=timestamp,
            name=name_label,
            count_label=count_label,
            preview=preview,
        )
    return t(
        "sessions.format",
        timestamp=timestamp,
        name=name_label,
        count_label=count_label,
    )


class CommandHandler:
    def __init__(self, llm_client, session_logger, input_handler, chat_app):
        self.llm_client = llm_client
        self.session_logger = session_logger
        self.input_handler = input_handler
        self.chat_app = chat_app

    def handle_command(self, command: str) -> bool:
        """Handle user commands starting with '/'.

        Returns:
            True if the application should quit (e.g. /bye), False otherwise.
        """
        command = command.strip()
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd == "/help":
            self._handle_help(args)
        elif cmd == "/clear":
            self._handle_clear()
        elif cmd == "/bye":
            return True  # Signal to quit
        elif cmd == "/model":
            self._handle_model(args)
        elif cmd == "/reload":
            self._handle_reload()
        elif cmd == "/files":
            self.handle_files_command()
        elif cmd == "/rootdir":
            self._handle_rootdir(args)
        elif cmd == "/proxy":
            self._handle_proxy(args)
        elif cmd == "/nameconv":
            self._handle_nameconv(args)
        else:
            print(t("commands.unknown_command", cmd=cmd))

        return False

    def _handle_help(self, args):
        """Show help for commands"""
        if args:
            cmd = args[0]
            if cmd in config.COMMANDS:
                print(
                    f"{t('commands.cmd_highlight', value=cmd)}: {config.COMMANDS[cmd]}"
                )
            else:
                print(t("commands.no_help", cmd=cmd))
        else:
            print(t("commands.available_commands"))
            for cmd, desc in config.COMMANDS.items():
                print(f"  {t('commands.cmd_highlight', value=cmd)} - {desc}")
            print(t("commands.help_ctrl_b", shortcut=t("keys.ctrl_b")))
            print(
                t(
                    "commands.help_alt_enter",
                    send_key=t("keys.alt_enter"),
                    newline_key=t("keys.enter"),
                )
            )
            print(t("commands.help_pageup", shortcut=t("keys.page_up_down")))

    def _handle_clear(self):
        """Clear conversation history and start a fresh session."""
        self.llm_client.clear_conversation()
        self.input_handler.clear_history()
        self.chat_app._new_session_logger()
        print(t("commands.clear_history"))

    def _handle_model(self, args):
        """Switch or show current model - reloads config.json on each call"""
        # get_models() already re-reads the config file, so we don't need to reload explicitly
        print(t("info.current_model", model=self.llm_client.get_current_model()))
        if not args:
            # No arguments provided - show interactive model selection menu
            selected_model = self.llm_client.choose_model()
            if selected_model:
                self.chat_app._ensure_proxy_for_model(selected_model)
                success = self.llm_client.switch_model(selected_model)
                if success:
                    self._prompt_clear_after_model_switch()
            elif selected_model is None:
                # User cancelled with Ctrl+C while already having a model
                print(t("info.returning_to_conversation"))
        else:
            # Arguments provided - use the old behavior
            new_model = args[0]
            self.chat_app._ensure_proxy_for_model(new_model)
            success = self.llm_client.switch_model(new_model)
            if success:
                self._prompt_clear_after_model_switch()

    def _prompt_clear_after_model_switch(self):
        """Ask user whether to clear conversation history after a model switch."""
        print(t("prompts.clear_confirm"), end="")
        try:
            response = input().strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{t('warnings.clear_cancelled')}")
            return

        if response == "y" or response == "yes":
            self._handle_clear()
        else:
            print(t("info.history_preserved"))

    def _handle_reload(self):
        """Reload a previous conversation from the current project root"""
        sessions = self.session_logger.list_available_sessions()
        if not sessions:
            if self.chat_app.root_dir is not None:
                print(t("warnings.no_previous_convs_project"))
            else:
                print(t("warnings.no_previous_convs_free_chat"))
            root_display = (
                self.chat_app.root_dir
                if self.chat_app.root_dir is not None
                else t("sessions.free_chat_display")
            )
            print(
                t(
                    "sessions.project_root",
                    root=t("sessions.root_value", value=root_display),
                )
            )
            print(
                t(
                    "sessions.conversation_dir",
                    dir=t(
                        "sessions.dir_value",
                        value=self.session_logger.conversation_dir,
                    ),
                )
            )
            return

        # Load metadata for all sessions
        metadata_cache = {}
        for session_path in sessions:
            meta = self.session_logger.load_session_metadata(session_path)
            if meta:
                metadata_cache[session_path] = meta

        root_display = (
            self.chat_app.root_dir
            if self.chat_app.root_dir is not None
            else t("sessions.free_chat_display")
        )
        print(
            t(
                "sessions.project_root",
                root=t("sessions.root_value", value=root_display),
            )
        )
        print(
            t(
                "sessions.conversation_dir",
                dir=t("sessions.dir_value", value=self.session_logger.conversation_dir),
            )
        )
        print()

        def item_formatter(path: str) -> str:
            return format_session(path, metadata_cache.get(path))

        # Show the full conversation list once
        _show_conversation_menu(sessions, item_formatter)

        try:
            selected_path = None
            while selected_path is None:
                user_input = (
                    input(t("prompts.reload_enter_number_or_search")).strip().lower()
                )

                if not user_input:
                    # Blank → just redisplay the full list and ask again
                    _show_conversation_menu(sessions, item_formatter)
                    continue

                if user_input.isdigit():
                    idx = int(user_input) - 1
                    if 0 <= idx < len(sessions):
                        selected_path = sessions[idx]
                        print(
                            f"{t('common.selected_prefix')} "
                            f"{item_formatter(selected_path)}"
                        )
                        break
                    print(
                        f"{t('common.error_prefix')} {t('common.number_out_of_range')}"
                    )
                    # Re-show the list so the user can see valid numbers
                    _show_conversation_menu(sessions, item_formatter)
                else:
                    # Treat input as keywords
                    keywords = user_input.split()
                    search_result = self._search_flow(
                        sessions, metadata_cache, keywords
                    )
                    if search_result is not None:
                        selected_path = search_result
                        break
                    # None means search was cancelled (Enter in search view),
                    # so we redisplay the full list and continue
                    _show_conversation_menu(sessions, item_formatter)

            if selected_path:
                session_data = self.session_logger.load_session(selected_path)
                if session_data:
                    conversation_history = session_data.get("conversation_history", [])
                    self.llm_client.load_conversation(conversation_history)
                    self.input_handler.load_from_conversation_history(
                        conversation_history
                    )
                    print(
                        t(
                            "sessions.loaded_conversation",
                            session=format_session(
                                selected_path, metadata_cache.get(selected_path)
                            ),
                        )
                    )
                    print(
                        t("sessions.contains_messages", count=len(conversation_history))
                    )
                    print(
                        t(
                            "sessions.loaded_into_history",
                            count=len(self.input_handler.history),
                        )
                    )
                else:
                    print(t("sessions.failed_to_load_conversation"))
        except (KeyboardInterrupt, EOFError):
            print(t("sessions.reload_cancelled"))

    def _rank_sessions(self, sessions, metadata_cache, keywords):
        """Return sessions matching **all** keywords, ranked by score desc.

        Sessions that do not contain every keyword (whole‑word match) are
        excluded.  The returned list contains ``(score, path, snippets)``
        tuples sorted highest score first.
        """
        ranked_sessions = []
        for path in sessions:
            meta = metadata_cache.get(path) or {}
            name = meta.get("name", "") or ""

            # Load full content only once per session
            session_data = self.session_logger.load_session(path)
            content = _extract_full_text(session_data)

            if not _all_keywords_present(name, content, keywords):
                continue

            score, snippets = _score_session(keywords, name, content)
            if score > 0:
                ranked_sessions.append((score, path, snippets))

        # Sort by score descending
        ranked_sessions.sort(key=lambda x: x[0], reverse=True)
        return ranked_sessions

    def _search_flow(self, sessions, metadata_cache, keywords):
        """Keyword search loop; returns a selected path or None to go back.

        The user can select a conversation, refine the search by typing new
        keywords, or press Enter to return to the full list.
        """
        while True:
            ranked = self._rank_sessions(sessions, metadata_cache, keywords)

            if not ranked:
                # No matching sessions with these keywords
                print(t("prompts.reload_no_matches"))
                new_input = input(t("prompts.reload_search_no_matches")).strip().lower()
                if not new_input:
                    # Go back to full list
                    return None
                keywords = new_input.split()
                # Loop again with new keywords
                continue

            # Show ranked results
            print()
            print(t("prompts.reload_showing_matches", count=len(ranked)))
            print()
            search_formatter = _make_search_formatter(metadata_cache, ranked)
            ranked_paths = [path for _, path, _ in ranked]
            _show_conversation_menu(ranked_paths, search_formatter)

            # Single prompt for selection / refine / back
            user_input = input(t("prompts.reload_search_select")).strip().lower()

            if not user_input:
                # Empty → go back to full list
                return None

            if user_input.isdigit():
                idx = int(user_input) - 1
                if 0 <= idx < len(ranked_paths):
                    chosen = ranked_paths[idx]
                    print(f"{t('common.selected_prefix')} {search_formatter(chosen)}")
                    return chosen
                print(f"{t('common.error_prefix')} {t('common.number_out_of_range')}")
                # Re-show the search results (loop will restart without new
                # input, so we manually re-display)
                continue

            # Non-numeric → treat as new keywords, refine search
            keywords = user_input.split()
            # Loop again with new keywords

    def _handle_nameconv(self, args):
        """Name the current conversation (file gets a readable suffix)."""
        if args:
            print(t("commands.nameconv_no_args"))
            return

        while True:
            try:
                name_input = input(t("prompts.nameconv")).strip()
            except (KeyboardInterrupt, EOFError):
                print(t("commands.nameconv_cancelled"))
                return

            if name_input:
                # Manual name entry
                error_key, slug = sanitize_conversation_name(name_input)
                if error_key:
                    print(t(f"errors.{error_key}"))
                    continue
                self.session_logger.set_name(slug)
                print(t("commands.nameconv_success", name=slug))
                return

            # Empty input → ask the AI for a keyword suggestion
            if not self.llm_client.conversation_history:
                print(t("warnings.nameconv_no_content"))
                continue

            try:
                raw = self.llm_client.generate(t("prompts.nameconv_llm_query"))
            except (KeyboardInterrupt, EOFError):
                print(t("commands.nameconv_cancelled"))
                return

            if not raw:
                print(t("errors.nameconv_ai_failed"))
                continue

            slug = _extract_suggested_name(raw)
            if slug is None:
                print(t("errors.nameconv_suggestion_unusable"))
                continue

            # Validate the suggestion: accept / edit / cancel
            print(t("prompts.nameconv_suggestion", name=slug))
            try:
                confirm = input(t("prompts.nameconv_confirm")).strip()
            except (KeyboardInterrupt, EOFError):
                print(t("commands.nameconv_cancelled"))
                return

            if not confirm:
                self.session_logger.set_name(slug)
                print(t("commands.nameconv_success", name=slug))
                return

            if confirm.lower() in ("c", "cancel", "no"):
                print(t("commands.nameconv_cancelled"))
                return

            # Manual modification of the suggestion
            error_key, new_slug = sanitize_conversation_name(confirm)
            if error_key:
                print(t(f"errors.{error_key}"))
                continue
            self.session_logger.set_name(new_slug)
            print(t("commands.nameconv_success", name=new_slug))
            return

    def handle_files_command(self):
        """Handle Ctrl+B file context menu"""
        # In free chat mode, prompt for root directory selection instead
        if hasattr(self.chat_app, "free_chat_mode") and self.chat_app.free_chat_mode:
            print(t("info.free_chat_mode_active"))
            self._handle_rootdir([])
            return

        from menu import FileMenuApp

        try:
            app = FileMenuApp(
                editable_files=self.chat_app.editable_files,
                readable_files=self.chat_app.readable_files,
                root_dir=self.chat_app.root_dir,
            )
            app.run()
            # Update the files lists after menu closes
            self.chat_app.editable_files = app.editable_files
            self.chat_app.readable_files = app.readable_files
        except Exception as e:
            print(t("errors.error_opening_file_menu", error=e))

    def _handle_rootdir(self, args):
        """Show or set project root directory using interactive selection with free chat option"""
        if args:
            # Direct path argument provided
            new_root = resolve_path(args[0])
            if Path(new_root).is_dir():
                try:
                    self.chat_app.set_root_dir(str(new_root))
                except ValueError as e:
                    print(f"{t('common.error_prefix')} {e}")
            else:
                print(
                    f"{t('common.error_prefix')} {t('errors.root_arg_not_valid', root=new_root)}"
                )
            return

        while True:
            try:
                sel_type, sel_value = UI.numbered_selection(
                    items=self.chat_app.recent_roots,
                    title=t("menus.previous_project_roots"),
                    prompt=t("prompts.root_enter"),
                    zero_label=t("menus.free_chat_label"),
                    allow_manual=True,
                    completer=PathCompleter(expanduser=True),
                )
            except (KeyboardInterrupt, EOFError):
                print(t("common.selection_cancelled"))
                return
            if sel_type == "zero":
                self.chat_app.set_root_dir(self.chat_app.FREE_CHAT_MODE)
                return
            if sel_type == "item":
                self.chat_app.set_root_dir(sel_value)
                return
            # manual path entry
            try:
                resolved = resolve_path(sel_value)
                if Path(resolved).is_dir():
                    print(f"{t('common.using_prefix')} {resolved}")
                    self.chat_app.set_root_dir(resolved)
                    return
                print(
                    f"{t('common.error_prefix')} {t('common.not_valid_directory', input=sel_value)}"
                )
            except Exception as e:
                print(
                    f"{t('common.error_prefix')} {t('common.invalid_input', error=e)}"
                )

    def _handle_proxy(self, args):
        """Handle /proxy command to manage proxy settings."""
        if args:
            proxy_arg = args[0]
            if proxy_arg.lower() == "off":
                self.chat_app.set_proxy(None)
            else:
                self.chat_app.set_proxy(proxy_arg)
            return

        while True:
            try:
                sel_type, sel_value = UI.numbered_selection(
                    items=self.chat_app.recent_proxies,
                    title=t("menus.proxy_management"),
                    prompt=t("prompts.proxy_enter"),
                    zero_label=t("menus.disable_proxy_label"),
                    allow_manual=True,
                    completer=None,
                )
            except (KeyboardInterrupt, EOFError):
                print(t("common.selection_cancelled"))
                return
            if sel_type == "zero":
                self.chat_app.set_proxy(None)
                return
            if sel_type == "item":
                self.chat_app.set_proxy(sel_value)
                return
            # manual proxy URL entry -- retry on failure
            if self.chat_app.set_proxy(sel_value):
                return
