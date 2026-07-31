#!/usr/bin/env python

"""Main LLM Terminal Chat application"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import cast, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import PathCompleter
import platformdirs

# Local application imports (after third-party and standard library)
import config

config.setup_logging()

from command_handler import CommandHandler
from file_processor import generate_query, generate_plain_query, parse_plain_response
from input_handler import InputHandler
from llm_client import LLMClient
from path_utils import resolve_path
from proxy_wrapper import create_proxy_wrapper, validate_proxy_url, normalize_proxy_url
from session_logger import SessionLogger
from strings import t
from text_utils import clean_text, estimate_tokens
from ui import UI

logger = logging.getLogger(__name__)


def enforce_non_root():
    """Block root execution for security (Dilemma F)."""
    try:
        if os.geteuid() == 0:
            print(t("errors.root_refusal"), file=sys.stderr)
            print(t("errors.root_refusal_hint"), file=sys.stderr)
            sys.exit(1)
    except AttributeError:
        pass  # Non-POSIX systems (Windows) don't have geteuid


def resolve_config_path():
    """
    Resolve config.json path from wrapper env var or XDG directories.
    Returns path string or None to trigger default search.
    Priority: THIN_WRAP_CONFIG_DIR > XDG_CONFIG_HOME > None
    """
    # 1. Wrapper script sets this (portable or XDG location)
    env_dir = os.environ.get("THIN_WRAP_CONFIG_DIR")
    if env_dir:
        env_path = Path(env_dir) / "config.json"
        # Ensure directory exists (first-run edge case)
        env_path.parent.mkdir(parents=True, exist_ok=True)
        return str(env_path)

    # 2. XDG standard location (fallback if no wrapper)
    xdg_home = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    xdg_path = Path(xdg_home) / "thin-wrap" / "config.json"
    if xdg_path.exists():
        return str(xdg_path)

    # 3. Return None to let config.py search script dir/CWD
    return None


class LLMChat:
    FREE_CHAT_MODE = "FREE_CHAT_MODE"

    def __init__(
        self,
        root_dir=None,
        readable_files=None,
        editable_files=None,
        first_message=None,
        proxy_url=None,
        config_path=None,
    ):
        logger.debug("Initializing LLMChat")
        self.script_directory = os.path.dirname(os.path.abspath(__file__))
        self.config_path = config_path

        # Set config path first
        config.set_config_path(config_path)

        # Load models configuration
        try:
            models = config.get_models()
            logger.debug(f"Loaded {len(models)} models from configuration")
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            print(f"{t('errors.models_config_load')} {e}")
            sys.exit(1)

        config_dir = Path(platformdirs.user_config_dir(config.APP_NAME))
        config_dir.mkdir(parents=True, exist_ok=True)
        history_file = config_dir / "history.json"
        self.recent_roots = self._load_recent_roots(history_file)
        self.recent_proxies = self._load_recent_proxies(history_file)
        self.history_file = history_file

        # Process root directory
        if root_dir is not None:
            root_path = resolve_path(root_dir)
            if not Path(root_path).is_dir():
                raise ValueError(
                    f"Specified root_dir is not a valid directory: {root_path}"
                )
            self.root_dir = root_path
            self.free_chat_mode = False
            self._add_to_recent_roots(history_file, self.root_dir)
            print(
                f"{t('common.info_prefix')} {t('info.using_project_root', path=self.root_dir)}"
            )
        else:
            self.root_dir = self._interactive_root_selection()
            # Check if free chat mode was selected
            if self.root_dir == self.FREE_CHAT_MODE:
                self.free_chat_mode = True
                self.root_dir = None
            else:
                self.free_chat_mode = False
                self._add_to_recent_roots(history_file, self.root_dir)

        # Resolve file paths
        if self.free_chat_mode:
            # In free chat mode, no file context
            self.editable_files = []
            self.readable_files = []
        else:
            assert (
                self.root_dir is not None
            ), "root_dir must be set when free_chat_mode is False"
            self.editable_files = self._resolve_file_list(
                editable_files or [], self.root_dir
            )
            self.readable_files = self._resolve_file_list(
                readable_files or [], self.root_dir
            )
        self.first_message = "" if not first_message else first_message
        self.proxy_wrapper = create_proxy_wrapper(proxy_url) if proxy_url else None

        # Add to proxy history if valid
        if proxy_url and validate_proxy_url(proxy_url) is None:
            self._add_to_recent_proxies(self.history_file, proxy_url)

        # Initialize components
        self.session_logger = SessionLogger(self.script_directory, self.root_dir)
        self.input_handler = InputHandler()
        self.llm_client = LLMClient(self.proxy_wrapper, self.session_logger)
        self.command_handler = CommandHandler(
            self.llm_client, self.session_logger, self.input_handler, self
        )
        logger.debug("Initialized all LLMChat components")

    def _resolve_file_list(self, files: list[str], root_dir: str) -> list[str]:
        """Resolve a list of file paths, skipping any that fail to resolve."""
        resolved = []
        for f in files:
            try:
                resolved.append(resolve_path(f, root_dir))
            except Exception as e:
                logger.warning(f"Skipping unresolvable file {f}: {e}")
        return resolved

    def _load_recent_roots(self, history_file: Path) -> list[str]:
        """Load recent root_dirs from history file."""
        try:
            if history_file.exists():
                data = json.loads(history_file.read_text(encoding="utf-8"))
                return [r for r in data.get("recent_root_dirs", []) if Path(r).is_dir()]
        except Exception as e:
            logger.debug(f"Failed to load root history: {e}")
        return []

    def _save_recent_roots(self, history_file: Path) -> None:
        """Save current recent_roots list along with existing proxies."""
        try:
            # Load existing data to preserve proxies
            existing_data = {}
            if history_file.exists():
                existing_data = json.loads(history_file.read_text(encoding="utf-8"))

            # Update roots, keep proxies and any other fields
            existing_data["recent_root_dirs"] = self.recent_roots[:10]

            history_file.write_text(
                json.dumps(existing_data, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.debug(f"Failed to save root history: {e}")

    def _add_to_recent_roots(self, history_file: Path, root: str) -> None:
        """Add root to history: move to front if already present, limit to 10."""
        root = str(Path(root).resolve())
        if root in self.recent_roots:
            self.recent_roots.remove(root)
        self.recent_roots.insert(0, root)
        self.recent_roots = self.recent_roots[:10]
        self._save_recent_roots(history_file)

    def _load_recent_proxies(self, history_file: Path) -> list[str]:
        """Load recent proxy URLs from history file and normalize them to prevent duplicates."""
        try:
            if history_file.exists():
                data = json.loads(history_file.read_text(encoding="utf-8"))
                valid_proxies = []
                seen = set()  # Deduplicate after normalization
                for proxy in data.get("recent_proxies", []):
                    error_msg = validate_proxy_url(proxy)
                    if error_msg is None:
                        normalized = normalize_proxy_url(proxy)
                        if normalized not in seen:
                            seen.add(normalized)
                            valid_proxies.append(normalized)  # Store clean version
                return valid_proxies
        except Exception as e:
            logger.debug(f"Failed to load proxy history: {e}")
        return []

    def _save_recent_proxies(self, history_file: Path) -> None:
        """Save current recent_proxies list (already normalized) along with existing roots."""
        try:
            existing_data = {}
            if history_file.exists():
                existing_data = json.loads(history_file.read_text(encoding="utf-8"))
            existing_data["recent_proxies"] = self.recent_proxies[:10]
            history_file.write_text(
                json.dumps(existing_data, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.debug(f"Failed to save proxy history: {e}")

    def _add_to_recent_proxies(self, history_file: Path, proxy_url: str) -> None:
        """Add proxy URL to history using normalized form to prevent duplicates."""
        if not proxy_url:
            return

        # Normalize before any comparison or storage
        normalized = normalize_proxy_url(proxy_url)

        # Remove existing entry (if present in either original or normalized form)
        if normalized in self.recent_proxies:
            self.recent_proxies.remove(normalized)
        elif proxy_url in self.recent_proxies:  # fallback for very old entries
            self.recent_proxies.remove(proxy_url)

        self.recent_proxies.insert(0, normalized)  # Store clean normalized version
        self.recent_proxies = self.recent_proxies[:10]
        self._save_recent_proxies(history_file)

    def _interactive_root_selection(self) -> str:
        """Interactive prompt for root selection with history, Tab autocompletion, and free chat option."""

        completer = PathCompleter(expanduser=True)
        session = PromptSession(completer=completer)

        free_chat_label = t("menus.free_chat_label")

        while True:
            print(t("menus.previous_project_roots"))
            print(t("menus.option_zero", label=free_chat_label))
            for i, item in enumerate(self.recent_roots, 1):
                print(t("menus.item_format", index=i, item=item))
            print(t("prompts.root_enter"))
            try:
                user_input = session.prompt(t("common.prompt_arrow")).strip()
            except (KeyboardInterrupt, EOFError):
                print(t("common.selection_cancelled"))
                raise

            if not user_input:
                print(f"{t('common.error_prefix')} {t('common.empty_input')}")
                continue

            # Numeric selection
            if user_input.isdigit():
                idx = int(user_input)
                if idx == 0:
                    print(f"{t('common.selected_prefix')} {free_chat_label}")
                    return self.FREE_CHAT_MODE
                elif 1 <= idx <= len(self.recent_roots):
                    chosen = self.recent_roots[idx - 1]
                    print(f"{t('common.selected_prefix')} {chosen}")
                    return chosen
                else:
                    print(
                        f"{t('common.error_prefix')} {t('common.number_out_of_range')}"
                    )
                    continue
            # Manual path entry
            try:
                resolved_str = resolve_path(user_input)
                if Path(resolved_str).is_dir():
                    print(f"{t('common.using_prefix')} {resolved_str}")
                    return resolved_str
                else:
                    print(
                        f"{t('common.error_prefix')} {t('common.not_valid_directory', input=user_input)}"
                    )
            except Exception as e:
                print(
                    f"{t('common.error_prefix')} {t('common.invalid_input', error=e)}"
                )

    def set_root_dir(self, new_root: str, ask_to_reload: bool = True) -> None:
        """
        Change the current project root directory or switch to free chat mode.
        Args:
            new_root: New root directory path, or FREE_CHAT_MODE for free chat
            ask_to_reload: Whether to prompt user to reload a conversation from the new root
        """
        if new_root == self.FREE_CHAT_MODE:
            # Switch to free chat mode
            old_root = self.root_dir
            self.root_dir = None
            self.free_chat_mode = True
            self.editable_files = []
            self.readable_files = []

            # Update session logger with None root (free chat mode)
            self.session_logger = SessionLogger(self.script_directory, self.root_dir)
            self.llm_client.session_logger = self.session_logger

            print(f"{t('common.success_prefix')} {t('commands.switched_free_chat')}")
            return

        # Otherwise, it's a directory path
        root_path = resolve_path(new_root)
        if not Path(root_path).is_dir():
            raise ValueError(
                f"Specified root_dir is not a valid directory: {root_path}"
            )

        old_root = self.root_dir
        self.root_dir = root_path
        self.free_chat_mode = False

        # Clear file lists when switching to a different project root
        # Only clear if actually changing to a different directory (not same directory via different path)
        should_clear_files = True
        if old_root is not None:
            # Compare resolved paths to see if it's the same directory
            old_resolved = resolve_path(old_root)
            if old_resolved == root_path:
                should_clear_files = False

        if should_clear_files:
            self.editable_files = []
            self.readable_files = []

        # Update history
        self._add_to_recent_roots(self.history_file, self.root_dir)

        # Update session logger with new root
        self.session_logger = SessionLogger(self.script_directory, self.root_dir)

        # Update LLM client's session logger reference
        self.llm_client.session_logger = self.session_logger

        print(
            f"{t('common.success_prefix')} {t('commands.root_changed', old=old_root, new=self.root_dir)}"
        )

        # If there are sessions available in the new root, ask if user wants to reload
        if ask_to_reload:
            sessions = self.session_logger.list_available_sessions()
            if sessions:
                print(
                    f"\n{t('common.note_prefix')} {t('info.note_convs_found', count=len(sessions))}"
                )
                print(t("info.use_reload", cmd=t("keys.reload")))

    def set_proxy(self, proxy_url: str | None, ask_to_reload: bool = True) -> bool:
        """
        Set proxy URL or disable proxy.

        Args:
            proxy_url: Proxy URL string, None or 'off' to disable
            ask_to_reload: Whether to ask about reloading sessions (not used for proxy)

        Returns:
            bool: True if successful, False otherwise
        """
        from proxy_wrapper import create_proxy_wrapper, validate_proxy_url

        # Handle disable proxy
        if proxy_url is None or proxy_url.lower() == "off":
            print(t("info.proxy_disabling"))
            # Clean up existing proxy wrapper
            old_proxy = self.proxy_wrapper
            self.proxy_wrapper = None
            # Update LLM client
            if self.llm_client.update_proxy(None):
                print(f"{t('common.success_prefix')} {t('info.proxy_disabled')}")
                return True
            else:
                # Restore old proxy on failure
                self.proxy_wrapper = old_proxy
                print(f"{t('common.error_prefix')} {t('errors.disable_proxy_failed')}")
                return False
        # Validate proxy URL format
        error_msg = validate_proxy_url(proxy_url)
        if error_msg:
            print(
                f"{t('common.error_prefix')} {t('common.invalid_proxy_url', error=error_msg)}"
            )
            return False
        # Test proxy connection
        print(t("info.proxy_testing"))
        try:
            # Create temporary proxy wrapper to test
            test_wrapper = create_proxy_wrapper(proxy_url)
            if test_wrapper is None:
                print(
                    f"{t('common.error_prefix')} {t('errors.create_proxy_wrapper_failed')}"
                )
                return False

            # Try to enter proxy context (which tests connection)
            test_wrapper.proxy_connection()

            # Connection test passed, now switch
            old_proxy = self.proxy_wrapper
            self.proxy_wrapper = test_wrapper

            if self.llm_client.update_proxy(test_wrapper):
                # Add to recent proxies history
                self._add_to_recent_proxies(self.history_file, proxy_url)
                print(
                    f"{t('common.success_prefix')} {t('info.proxy_switched', url=proxy_url)}"
                )
                return True
            else:
                # Restore old proxy on failure
                self.proxy_wrapper = old_proxy
                print(
                    f"{t('common.error_prefix')} {t('errors.llm_update_proxy_failed')}"
                )
                return False
        except Exception as e:
            print(
                f"{t('common.error_prefix')} {t('errors.proxy_connection_test_failed', error=e)}"
            )
            return False

    def _print_files_summary(self):
        """Print a compact summary of editable and readable files."""
        if not self.editable_files and not self.readable_files:
            return

        def format_files(file_list, label):
            if not file_list:
                return t("files.none", label=label)
            # Convert to relative paths
            rel_paths = []
            for f in file_list:
                try:
                    rel_path = os.path.relpath(f, self.root_dir)
                except ValueError:
                    rel_path = f
                rel_paths.append(rel_path)
            # Truncate if too many
            max_show = 5
            if len(rel_paths) <= max_show:
                files_str = ", ".join(rel_paths)
                return t(
                    "files.list", label=label, count=len(rel_paths), files=files_str
                )
            else:
                shown = rel_paths[:max_show]
                files_str = ", ".join(shown) + t(
                    "files.and_more", count=len(rel_paths) - max_show
                )
                return t(
                    "files.list", label=label, count=len(rel_paths), files=files_str
                )

        print()
        print(format_files(self.editable_files, t("files.label_editable")))
        print(format_files(self.readable_files, t("files.label_readable")))
        print()

    def _prompt_for_proxy_if_needed(self, selected_model: str) -> bool:
        """
        Prompt for proxy selection if the selected model suggests proxy and no proxy is configured.

        Args:
            selected_model: Name of the selected model

        Returns:
            bool: True if proxy was configured or not needed, False if user cancelled
        """
        # Check if proxy already configured
        if self.proxy_wrapper is not None:
            return True
        # Get model config to check if proxy suggested
        models = config.get_models()
        model_config = models.get(selected_model)
        if not model_config:
            return True

        # Check if model suggests proxy
        if not model_config.get("proxy", False):
            return True

        # Model suggests proxy but none configured - prompt user
        print(f"\n{t('info.proxy_suggested_title')}")
        print(t("info.proxy_suggested_model", model=selected_model))
        print(t("info.proxy_configure_now"))
        # Use the existing command handler for proxy selection
        try:
            self.command_handler._handle_proxy([])
        except KeyboardInterrupt:
            print(f"\n{t('warnings.proxy_selection_cancelled')}")
            return False
        # Return True regardless - if user selected "No proxy", proxy_wrapper remains None
        return True

    def run(self):
        """Main chat loop"""
        logger.debug("Starting run method")
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            logger.debug("Reconfigured stdout and stderr to UTF-8")
        except AttributeError:
            logger.warning(
                "Reconfigure stdout/stderr not supported in this Python version"
            )
            pass

        UI.print_banner(self.script_directory)
        logger.debug("Printed application banner")

        if self.proxy_wrapper:
            print(t("info.proxy_mode_enabled"))
            proxy_info = self.proxy_wrapper.get_connection_info()
            if proxy_info.get("proxy_url"):
                print(t("info.proxy_url", url=proxy_info["proxy_url"]))
            print()
            logger.debug("Displayed proxy information")

        try:
            model = self.llm_client.choose_model()
        except KeyboardInterrupt as e:
            print(f"\n{t('info.exiting_during_setup')}")
            self._save_and_exit()
            return
        # Prompt for proxy if model suggests it and no proxy configured
        if model is None:
            # This shouldn't happen during initialization, but handle gracefully
            logger.warning("Model selection returned None, skipping proxy prompt")
        else:
            try:
                if not self._prompt_for_proxy_if_needed(model):
                    # User cancelled proxy selection, continue without proxy
                    print(t("warnings.continuing_without_proxy"))
            except KeyboardInterrupt:
                print(f"\n{t('warnings.proxy_setup_cancelled')}")
        # Now set up API key (may fail if proxy still needed but not configured)
        try:
            self.llm_client.setup_api_key(model)
            logger.debug("Set up API key successfully")
        except KeyboardInterrupt as e:
            print(f"\n{t('info.exiting_during_setup')}")
            self._save_and_exit()
            return

        UI.show_startup_message()
        self._print_files_summary()
        logger.debug("Showed startup message")

        next_default = self.first_message

        while True:
            logger.debug("Entering main chat loop iteration")
            user_input = self.input_handler.get_input_with_editing(default=next_default)
            next_default = ""
            if isinstance(user_input, tuple) and user_input[0] == "Ctrl+B":
                next_default = user_input[1]
                self.command_handler.handle_files_command()
                self._print_files_summary()
                continue

            if not user_input:
                logger.debug("Empty user input, continuing")
                print(t("info.empty_message_hint"))
                continue

            logger.debug(f"Processing user input: {user_input[:50]}...")

            if user_input.startswith("/"):
                logger.debug("Detected command input")
                should_quit = self.command_handler.handle_command(user_input)
                if should_quit:
                    logger.debug("Command requested quit")
                    break
                continue

            logger.debug("Handling non-command user message")
            send_result = self._send_message(user_input)

            # If user chose to insert files, return to editor with the message
            if send_result == "insert_files":
                next_default = user_input
                continue
            else:
                self.input_handler.add_to_history(user_input)
        logger.debug("Exiting main chat loop")
        self._save_and_exit()

    def _save_and_exit(self):
        """Save session and exit cleanly"""
        logger.debug("Saving session and preparing to exit")
        # Save final state before exit
        self.session_logger.save_session(self.llm_client.conversation_history)
        log_path = self.session_logger.get_session_path()
        UI.show_exit_message(log_path)
        logger.debug(f"Session saved to: {log_path}")

    def _send_message(self, message):
        """
        Send message to LLM with specified token limit.
        Returns:
            'insert_files' if user chose to insert files (abort send),
            None otherwise
        """
        model = self.llm_client.get_current_model()
        logger.debug(f"Using model: {model}")

        print(t("separators.message_line"))

        if self.free_chat_mode:
            # Free chat mode: plain message without file context
            query = generate_plain_query(message)
            response_parser = parse_plain_response
        else:
            # In non-free chat mode, root_dir must be a string
            root_dir_str = cast(str, self.root_dir)
            query, response_parser = generate_query(
                root_dir_str, self.readable_files, self.editable_files, message
            )
            # Check if user chose to insert files (abort send)
            if query is None and response_parser is None:
                return "insert_files"

        assert query is not None
        query = clean_text(query)

        # Measure time taken for LLM client interaction
        start_time_ns = time.perf_counter_ns()
        response, usage = self.llm_client.send_message(query)
        end_time_ns = time.perf_counter_ns()
        duration_ms = (
            end_time_ns - start_time_ns
        ) / 1_000_000.0  # Millisecond precision

        self._report_token_usage(query, response, usage, duration_ms=duration_ms)

        assert response is not None
        comments = response_parser(response)

        if comments:
            print("\n" + t("info.llm_explanation"))
            UI.render_markdown(comments)
        else:
            print(t("info.no_explanation"))

        print(t("separators.response_line"))
        print()
        logger.debug("Message sent and response processed successfully")

    def _report_token_usage(
        self,
        query: str,
        response: str,
        usage: Optional[dict] = None,
        duration_ms: Optional[float] = None,
    ):
        """Affiche un tableau clair avec Input, Output, Cache Hit, Time (s), et Output/s."""
        try:
            if usage and isinstance(usage, dict):
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)

                # Cache hit (compatible DeepSeek + OpenAI/OpenRouter/Gemini)
                cached_tokens = usage.get("prompt_cache_hit_tokens", 0) or usage.get(
                    "prompt_tokens_details", {}
                ).get("cached_tokens", 0)
                source = "API"
            else:
                input_tokens = estimate_tokens(query)
                output_tokens = estimate_tokens(response)
                cached_tokens = 0
                source = "estimated"

            duration_seconds = 0.0
            output_tokens_per_second = 0.0
            duration_display = "-"
            ops_display = "-"

            if duration_ms is not None and duration_ms > 0:
                duration_seconds = duration_ms / 1000.0
                duration_display = f"{duration_seconds:.1f}"
                if output_tokens > 0:
                    output_tokens_per_second = 1000.0 * output_tokens / duration_ms
                    ops_display = f"{output_tokens_per_second:.1f}"

            print(t("tokens.token_usage_title", source=source))
            # Headers for 5 columns, total width (excluding '   ' prefix) is 62 characters
            # This aligns the table's content width with the '─' * 65 line when considering the '   ' prefix
            print(t("tokens.token_header"))
            print(t("tokens.token_separator"))

            if cached_tokens > 0 and input_tokens > 0:
                ratio = (cached_tokens / input_tokens) * 100
                # Compacted to fit 12 characters: e.g., '12345 (100%)'
                cache_display = f"{cached_tokens} ({ratio:.0f}%)"
            else:
                cache_display = "-"

            print(
                f"   {input_tokens:<11} | {output_tokens:<11} | {cache_display:<12} | {duration_display:<11} | {ops_display:<12}"
            )

        except Exception as e:
            print(t("tokens.token_error", error=e))


def get_location_info() -> str:
    """
    Return a cleanly structured, multi-line string containing all
    relevant file and directory locations for --help output.
    This is the single source of truth for both the installed binary
    and direct 'python thin_wrap.py' execution.
    """
    # Binary location - respects wrapper environment variable when present
    app_dir = os.environ.get("THIN_WRAP_APP_DIR")
    if app_dir and Path(app_dir).is_dir():
        binary_path = str(Path(app_dir) / "thin-wrap")
    else:
        # Direct Python execution (git clone / development)
        binary_path = os.path.realpath(sys.argv[0])

    # Config location - reuses the exact same logic as the rest of the application
    config_path_obj = resolve_config_path()
    if config_path_obj:
        config_desc = str(config_path_obj)
    else:
        config_desc = t("help.location_config_default")

    # Data locations (using the same platformdirs logic as the application)
    config_dir = Path(platformdirs.user_config_dir(config.APP_NAME))
    data_dir = Path(platformdirs.user_data_dir(config.APP_NAME))

    history_file = config_dir / "history.json"
    conversations_base = data_dir / "conversations"

    return t(
        "help.location_block",
        binary=binary_path,
        config=config_desc,
        history_file=history_file,
        conversations_base=conversations_base,
    )


def parse_arguments():
    """Parse command line arguments"""
    logger.debug("Parsing command line arguments")

    locations = get_location_info()

    parser = argparse.ArgumentParser(
        description=t("help.app_description"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=t("help.examples") + locations,
    )

    parser.add_argument(
        "-p",
        "--proxy",
        metavar="PROXY_URL",
        help=t("help.arg_proxy"),
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="CONFIG_PATH",
        help=t("help.arg_config"),
    )
    parser.add_argument("-rd", "--root-dir", help=t("help.arg_root_dir"))
    parser.add_argument("-r", "--read", nargs="+", help=t("help.arg_read"))
    parser.add_argument("-e", "--edit", nargs="+", help=t("help.arg_edit"))
    parser.add_argument("-m", "--message", help=t("help.arg_message"))

    return parser.parse_args()


def main():
    """Entry point"""
    logger.debug("Entering main function")

    enforce_non_root()

    try:
        args = parse_arguments()

        if args.proxy:
            proxy_url = args.proxy.rstrip("/")
            error_msg = validate_proxy_url(proxy_url)
            if error_msg:
                print(
                    f"{t('common.error_prefix')} {t('common.invalid_proxy_url', error=error_msg)}"
                )
                logger.error(f"Invalid proxy URL provided: {args.proxy} -- {error_msg}")
                sys.exit(1)
            logger.debug(f"Proxy enabled: {proxy_url}")

        # Config resolution: CLI arg > env/XDG > default search
        if args.config:
            effective_config_path = args.config
            logger.debug(f"Using config from --config arg: {effective_config_path}")
        else:
            effective_config_path = resolve_config_path()
            if effective_config_path:
                logger.debug(f"Using resolved config path: {effective_config_path}")
            else:
                logger.debug("No env/XDG config found; using default search")

        chat = LLMChat(
            root_dir=args.root_dir,
            readable_files=args.read,
            editable_files=args.edit,
            first_message=args.message,
            proxy_url=args.proxy,
            config_path=effective_config_path,  # Prevails if set, None otherwise
        )
        chat.run()

    except KeyboardInterrupt:
        print(f"\n{t('common.goodbye')}")
        logger.debug("Exiting due to KeyboardInterrupt")
        sys.exit(0)


if __name__ == "__main__":
    main()
