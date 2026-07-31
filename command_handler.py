"""Command handling for LLM Terminal Chat"""

import os
from pathlib import Path
from ui import UI
import config
from proxy_wrapper import validate_proxy_url
from strings import t


class CommandHandler:
    def __init__(self, llm_client, session_logger, input_handler, chat_app):
        self.llm_client = llm_client
        self.session_logger = session_logger
        self.input_handler = input_handler
        self.chat_app = chat_app

    def handle_command(self, command):
        """Handle user commands starting with '/'"""
        command = command.strip()
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ["/help", "/?"]:
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
        """Clear conversation history without user confirmation."""
        self.llm_client.clear_conversation()
        self.input_handler.clear_history()
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
            print(t("warnings.history_preserved"))

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

        def format_session(path):
            filename = os.path.basename(path)
            # Remove the .toml.zip extension and session_ prefix
            name = filename.replace("session_", "").replace(".toml.zip", "")
            # Format as YYYY-MM-DD HH:MM:SS
            try:
                # Parse the timestamp format: YYYYMMDD_HHMMSS
                if "_" in name:
                    date_part, time_part = name.split("_", 1)
                    if len(date_part) == 8 and len(time_part) == 6:
                        # Format: YYYY-MM-DD HH:MM:SS
                        timestamp = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
                    else:
                        timestamp = name
                else:
                    timestamp = name
            except:
                timestamp = name

            # Add metadata if available
            meta = metadata_cache.get(path)
            if meta:
                count = meta.get("interaction_count", 0)
                preview = meta.get("preview", "")
                if preview:
                    # Truncate preview to 50 chars for display
                    if len(preview) > 50:
                        preview = preview[:47] + "..."
                    return t(
                        "sessions.format_with_preview",
                        timestamp=timestamp,
                        count=count,
                        preview=preview,
                    )
                else:
                    return t("sessions.format", timestamp=timestamp, count=count)
            else:
                return timestamp

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
                item_formatter=format_session,
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
                            session=format_session(selected_path),
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
            new_root = Path(args[0]).expanduser().resolve()
            if new_root.is_dir():
                try:
                    self.chat_app.set_root_dir(str(new_root))
                except ValueError as e:
                    print(f"{t('common.error_prefix')} {e}")
            else:
                print(
                    f"{t('common.error_prefix')} {t('errors.root_arg_not_valid', root=new_root)}"
                )
        else:
            # Interactive selection mode with free chat option
            from prompt_toolkit import PromptSession
            from prompt_toolkit.completion import PathCompleter

            completer = PathCompleter(expanduser=True)
            session = PromptSession(completer=completer)

            while True:
                print(t("menus.previous_project_roots"))
                print(t("menus.option_zero", label=t("menus.free_chat_label")))
                for i, item in enumerate(self.chat_app.recent_roots, 1):
                    print(t("menus.item_format", index=i, item=item))
                print(t("prompts.root_enter"))

                try:
                    user_input = session.prompt(t("common.prompt_arrow")).strip()
                except (KeyboardInterrupt, EOFError):
                    print(t("common.selection_cancelled"))
                    return

                if not user_input:
                    print(f"{t('common.error_prefix')} {t('common.empty_input')}")
                    continue

                # Numeric selection
                if user_input.isdigit():
                    idx = int(user_input)
                    if idx == 0:
                        print(
                            f"{t('common.selected_prefix')} {t('menus.free_chat_label')}"
                        )
                        self.chat_app.set_root_dir(self.chat_app.FREE_CHAT_MODE)
                        return
                    elif 1 <= idx <= len(self.chat_app.recent_roots):
                        chosen = self.chat_app.recent_roots[idx - 1]
                        print(f"{t('common.selected_prefix')} {chosen}")
                        self.chat_app.set_root_dir(chosen)
                        return
                    else:
                        print(
                            f"{t('common.error_prefix')} {t('common.number_out_of_range')}"
                        )
                        continue

                # Manual path entry
                try:
                    new_item = Path(user_input).expanduser().resolve(strict=False)
                    if new_item.is_dir():
                        resolved_str = str(new_item)
                        print(f"{t('common.using_prefix')} {resolved_str}")
                        self.chat_app.set_root_dir(resolved_str)
                        return
                    else:
                        print(
                            f"{t('common.error_prefix')} {t('common.not_valid_directory', input=user_input)}"
                        )
                except Exception as e:
                    print(
                        f"{t('common.error_prefix')} {t('common.invalid_input', error=e)}"
                    )

    def _handle_proxy(self, args):
        """Handle /proxy command to manage proxy settings."""
        if args:
            # Direct proxy URL or "off" argument provided
            proxy_arg = args[0]
            if proxy_arg.lower() == "off":
                self.chat_app.set_proxy(None)
            else:
                self.chat_app.set_proxy(proxy_arg)
        else:
            # Interactive selection mode
            from prompt_toolkit import PromptSession
            from prompt_toolkit.completion import PathCompleter

            completer = PathCompleter(expanduser=True)
            session = PromptSession(completer=completer)

            disable_label = t("menus.disable_proxy_label")

            while True:
                print(t("menus.proxy_management"))
                print(t("menus.option_zero", label=disable_label))
                for i, proxy in enumerate(self.chat_app.recent_proxies, 1):
                    print(t("menus.item_format", index=i, item=proxy))
                print(t("prompts.proxy_enter"))

                try:
                    user_input = session.prompt(t("common.prompt_arrow")).strip()
                except (KeyboardInterrupt, EOFError):
                    print(t("common.selection_cancelled"))
                    return

                if not user_input:
                    print(f"{t('common.error_prefix')} {t('common.empty_input')}")
                    continue

                # Numeric selection
                if user_input.isdigit():
                    idx = int(user_input)
                    if idx == 0:
                        print(f"{t('common.selected_prefix')} {disable_label}")
                        self.chat_app.set_proxy(None)
                        return
                    elif 1 <= idx <= len(self.chat_app.recent_proxies):
                        chosen = self.chat_app.recent_proxies[idx - 1]
                        print(f"{t('common.selected_prefix')} {chosen}")
                        self.chat_app.set_proxy(chosen)
                        return
                    else:
                        print(
                            f"{t('common.error_prefix')} {t('common.number_out_of_range')}"
                        )
                        continue

                # Manual proxy URL entry
                self.chat_app.set_proxy(user_input)
                return
