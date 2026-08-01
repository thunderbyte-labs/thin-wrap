"""Command handling for LLM Terminal Chat"""

import os
import re
from pathlib import Path

from prompt_toolkit.completion import PathCompleter

import config
from path_utils import resolve_path
from session_logger import sanitize_conversation_name
from strings import t
from ui import UI


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
    name_label = UI.colorize(name, "GREEN") if name else t("sessions.no_name")

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
                success = self.llm_client.switch_model(selected_model)
                if success:
                    self._prompt_clear_after_model_switch()
            elif selected_model is None:
                # User cancelled with Ctrl+C while already having a model
                print(t("info.returning_to_conversation"))
        else:
            # Arguments provided - use the old behavior
            new_model = args[0]
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

        # Format session names for display
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

        try:
            selected_path = UI.interactive_selection(
                prompt_title=t("prompts.available_conversations"),
                prompt_message=t("prompts.conversation_enter_number"),
                no_items_message=t("prompts.no_conversations_available"),
                items=sessions,
                item_formatter=lambda p: format_session(p, metadata_cache.get(p)),
                allow_new=False,
            )

            if selected_path:
                session_data = self.session_logger.load_session(selected_path)
                if session_data:
                    # Load the conversation history
                    conversation_history = session_data.get("conversation_history", [])
                    self.llm_client.load_conversation(conversation_history)
                    # Load user messages into input history
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

            error_key, slug = sanitize_conversation_name(name_input)
            if error_key:
                print(t(f"errors.{error_key}"))
                continue

            self.session_logger.set_name(slug)
            print(t("commands.nameconv_success", name=slug))
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
            # manual proxy URL entry — retry on failure
            if self.chat_app.set_proxy(sel_value):
                return
