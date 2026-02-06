#!/usr/bin/env python3.11

"""Main LLM Terminal Chat application"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import cast

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
from proxy_wrapper import create_proxy_wrapper, validate_proxy_url
from session_logger import SessionLogger
from text_utils import clean_text, estimate_tokens
from ui import UI

logger = logging.getLogger(__name__)

class LLMChat:
    FREE_CHAT_MODE = "FREE_CHAT_MODE"
    
    def __init__(self, root_dir=None, readable_files=None, editable_files=None, first_message=None, proxy_url=None, config_path=None):
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
            print(f"{UI.colorize('Error loading models configuration:', 'RED')} {e}")
            sys.exit(1)

        config_dir = Path(platformdirs.user_config_dir(config.APP_NAME))
        config_dir.mkdir(parents=True, exist_ok=True)
        history_file = config_dir / "history.json"
        self.recent_roots = self._load_recent_roots(history_file)
        self.recent_proxies = self._load_recent_proxies(history_file)
        self.history_file = history_file

        # Process root directory
        if root_dir is not None:
            root_path = Path(root_dir).expanduser().resolve()
            if not root_path.is_dir():
                raise ValueError(f"Specified root_dir is not a valid directory: {root_path}")
            self.root_dir = str(root_path)
            self.free_chat_mode = False
            self._add_to_recent_roots(history_file, self.root_dir)
            print(f"{UI.colorize('Info:', 'BRIGHT_CYAN')} Using specified project root: {self.root_dir}")
        else:
            self.root_dir = self._interactive_root_selection()
            # Check if free chat mode was selected
            if self.root_dir == self.FREE_CHAT_MODE:
                self.free_chat_mode = True
                self.root_dir = None
                print(f"{UI.colorize('Info:', 'BRIGHT_CYAN')} Free chat mode enabled (no file context)")
            else:
                self.free_chat_mode = False
                self._add_to_recent_roots(history_file, self.root_dir)

        # Resolve file paths
        if self.free_chat_mode:
            # In free chat mode, no file context
            self.editable_files = []
            self.readable_files = []
        else:
            assert self.root_dir is not None, "root_dir must be set when free_chat_mode is False"
            root_path = Path(self.root_dir)
            self.editable_files = [str((Path(p).resolve() if Path(p).is_absolute() else (root_path / p)).resolve()) 
                                  for p in (editable_files or [])]
            self.readable_files = [str((Path(p).resolve() if Path(p).is_absolute() else (root_path / p)).resolve())
                                  for p in (readable_files or [])]
        self.first_message = "" if not first_message else first_message
        self.proxy_wrapper = create_proxy_wrapper(proxy_url) if proxy_url else None
        
        # Add to proxy history if valid
        if proxy_url and validate_proxy_url(proxy_url) is None:
            self._add_to_recent_proxies(self.history_file, proxy_url)

        # Initialize components
        self.session_logger = SessionLogger(self.script_directory, self.root_dir)
        self.input_handler = InputHandler()
        self.llm_client = LLMClient(self.proxy_wrapper, self.session_logger)
        self.command_handler = CommandHandler(self.llm_client, self.session_logger, self.input_handler, self)
        logger.debug("Initialized all LLMChat components")

    def _load_recent_roots(self, history_file: Path) -> list[str]:
        """Load recent root_dirs from history file."""
        try:
            if history_file.exists():
                data = json.loads(history_file.read_text(encoding='utf-8'))
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
                existing_data = json.loads(history_file.read_text(encoding='utf-8'))
            
            # Update roots, keep proxies and any other fields
            existing_data["recent_root_dirs"] = self.recent_roots[:10]
            
            history_file.write_text(json.dumps(existing_data, indent=2), encoding='utf-8')
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
        """Load recent proxy URLs from history file."""
        try:
            if history_file.exists():
                data = json.loads(history_file.read_text(encoding='utf-8'))
                # Only return proxies that are valid (format-wise)
                valid_proxies = []
                for proxy in data.get("recent_proxies", []):
                    error_msg = validate_proxy_url(proxy)
                    if error_msg is None:
                        valid_proxies.append(proxy)
                return valid_proxies
        except Exception as e:
            logger.debug(f"Failed to load proxy history: {e}")
        return []

    def _save_recent_proxies(self, history_file: Path) -> None:
        """Save current recent_proxies list along with existing roots."""
        try:
            # Load existing data to preserve roots
            existing_data = {}
            if history_file.exists():
                existing_data = json.loads(history_file.read_text(encoding='utf-8'))
            
            # Update proxies, keep roots and any other fields
            existing_data["recent_proxies"] = self.recent_proxies[:10]
            
            history_file.write_text(json.dumps(existing_data, indent=2), encoding='utf-8')
        except Exception as e:
            logger.debug(f"Failed to save proxy history: {e}")

    def _add_to_recent_proxies(self, history_file: Path, proxy_url: str) -> None:
        """Add proxy URL to history: move to front if already present, limit to 10."""
        if proxy_url in self.recent_proxies:
            self.recent_proxies.remove(proxy_url)
        self.recent_proxies.insert(0, proxy_url)
        self.recent_proxies = self.recent_proxies[:10]
        self._save_recent_proxies(history_file)

    def _interactive_root_selection(self) -> str:
        """Interactive prompt for root selection with history, Tab autocompletion, and free chat option."""
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import PathCompleter
        
        completer = PathCompleter(expanduser=True)
        session = PromptSession(completer=completer)
        
        free_chat_label = "No root directory - Free chatting without file context"
        
        while True:
            print(f"{UI.colorize('Previous project roots:', 'BRIGHT_CYAN')}")
            print(f"  0. {free_chat_label}")
            for i, item in enumerate(self.recent_roots, 1):
                print(f"  {i}. {item}")
            print("Enter a number to select, or type a new path (Tab for completion, ~ for home):")
            
            try:
                user_input = session.prompt("> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nSelection cancelled.")
                raise
            
            if not user_input:
                print(f"{UI.colorize('Error:', 'RED')} Empty input - please try again.")
                continue
            
            # Numeric selection
            if user_input.isdigit():
                idx = int(user_input)
                if idx == 0:
                    print(f"{UI.colorize('Selected:', 'BRIGHT_CYAN')} {free_chat_label}")
                    return self.FREE_CHAT_MODE
                elif 1 <= idx <= len(self.recent_roots):
                    chosen = self.recent_roots[idx - 1]
                    print(f"{UI.colorize('Selected:', 'BRIGHT_CYAN')} {chosen}")
                    return chosen
                else:
                    print(f"{UI.colorize('Error:', 'RED')} Number out of range.")
                    continue
            
            # Manual path entry
            try:
                new_item = Path(user_input).expanduser().resolve(strict=False)
                if new_item.is_dir():
                    resolved_str = str(new_item)
                    print(f"{UI.colorize('Using:', 'BRIGHT_CYAN')} {resolved_str}")
                    return resolved_str
                else:
                    print(f"{UI.colorize('Error:', 'RED')} Not a valid directory: {user_input}")
            except Exception as e:
                print(f"{UI.colorize('Error:', 'RED')} Invalid input: {e}")

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
            
            print(f"{UI.colorize('Success:', 'BRIGHT_GREEN')} Switched to free chat mode (no file context)")
            return
        
        # Otherwise, it's a directory path
        root_path = Path(new_root).expanduser().resolve()
        if not root_path.is_dir():
            raise ValueError(f"Specified root_dir is not a valid directory: {root_path}")
        
        old_root = self.root_dir
        self.root_dir = str(root_path)
        self.free_chat_mode = False
        
        # Clear file lists when switching to a different project root
        # Only clear if actually changing to a different directory (not same directory via different path)
        should_clear_files = True
        if old_root is not None:
            # Compare resolved paths to see if it's the same directory
            old_resolved = Path(old_root).resolve()
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
        
        print(f"{UI.colorize('Success:', 'BRIGHT_GREEN')} Project root changed from '{old_root}' to '{self.root_dir}'")
        
        # If there are sessions available in the new root, ask if user wants to reload
        if ask_to_reload:
            sessions = self.session_logger.list_available_sessions()
            if sessions:
                print(f"\n{UI.colorize('Note:', 'BRIGHT_CYAN')} Found {len(sessions)} conversation(s) in the new project root.")
                print(f"Use {UI.colorize('/reload', 'BRIGHT_YELLOW')} to load one of these conversations.")

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
        if proxy_url is None or proxy_url.lower() == 'off':
            print(f"{UI.colorize('Disabling proxy...', 'BRIGHT_CYAN')}")
            # Clean up existing proxy wrapper
            old_proxy = self.proxy_wrapper
            self.proxy_wrapper = None
            
            # Update LLM client
            if self.llm_client.update_proxy(None):
                print(f"{UI.colorize('Success:', 'BRIGHT_GREEN')} Proxy disabled")
                return True
            else:
                # Restore old proxy on failure
                self.proxy_wrapper = old_proxy
                print(f"{UI.colorize('Error:', 'RED')} Failed to disable proxy")
                return False
        
        # Validate proxy URL format
        error_msg = validate_proxy_url(proxy_url)
        if error_msg:
            print(f"{UI.colorize('Error:', 'RED')} Invalid proxy URL: {error_msg}")
            return False
        
        # Test proxy connection
        print(f"{UI.colorize('Testing proxy connection...', 'BRIGHT_CYAN')}")
        try:
            # Create temporary proxy wrapper to test
            test_wrapper = create_proxy_wrapper(proxy_url)
            if test_wrapper is None:
                print(f"{UI.colorize('Error:', 'RED')} Failed to create proxy wrapper")
                return False
            
            # Try to enter proxy context (which tests connection)
            with test_wrapper.proxy_connection():
                print(f"{UI.colorize('Proxy connection test successful!', 'BRIGHT_GREEN')}")
            
            # Connection test passed, now switch
            old_proxy = self.proxy_wrapper
            self.proxy_wrapper = test_wrapper
            
            if self.llm_client.update_proxy(test_wrapper):
                # Add to recent proxies history
                self._add_to_recent_proxies(self.history_file, proxy_url)
                print(f"{UI.colorize('Success:', 'BRIGHT_GREEN')} Proxy switched to: {proxy_url}")
                return True
            else:
                # Restore old proxy on failure
                self.proxy_wrapper = old_proxy
                print(f"{UI.colorize('Error:', 'RED')} Failed to update LLM client with new proxy")
                return False
                
        except Exception as e:
            print(f"{UI.colorize('Error:', 'RED')} Proxy connection test failed: {e}")
            return False

    def _print_files_summary(self):
        """Print a compact summary of editable and readable files."""
        if not self.editable_files and not self.readable_files:
            return

        def format_files(file_list, label):
            if not file_list:
                return f"{label}: None"
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
                files_str = ', '.join(rel_paths)
                return f"{label} ({len(rel_paths)}): {files_str}"
            else:
                shown = rel_paths[:max_show]
                files_str = ', '.join(shown) + f" ... and {len(rel_paths)-max_show} more"
                return f"{label} ({len(rel_paths)}): {files_str}"

        print()
        print(format_files(self.editable_files, "Editable"))
        print(format_files(self.readable_files, "Readable"))
        print()

    def run(self):
        """Main chat loop"""
        logger.debug("Starting run method")
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            logger.debug("Reconfigured stdout and stderr to UTF-8")
        except AttributeError:
            logger.warning("Reconfigure stdout/stderr not supported in this Python version")
            pass

        UI.print_banner(self.script_directory)
        logger.debug("Printed application banner")

        if self.proxy_wrapper:
            print(f"{UI.colorize('PROXY MODE ENABLED', 'BRIGHT_GREEN')}")
            proxy_info = self.proxy_wrapper.get_connection_info()
            if proxy_info.get("proxy_url"):
                print(f"Proxy URL: {proxy_info['proxy_url']}")
            print()
            logger.debug("Displayed proxy information")

        try:
            model = self.llm_client.choose_model()
            self.llm_client.setup_api_key(model)
            logger.debug("Set up API key successfully")
        except KeyboardInterrupt as e:
            print(f"\n{UI.colorize('Exiting during setup...', 'BRIGHT_WHITE')}")
            self._save_and_exit()
            return

        UI.show_startup_message()
        if self.free_chat_mode:
            print(f"{UI.colorize('Free chat mode enabled - no file context.', 'BRIGHT_CYAN')}")
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
                print(UI.colorize("Empty message or KeyboardInterrupt. Type /help to see command or /bye (then Alt+Enter) to quit.\n\n", "BOLD"))
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
            if send_result == 'insert_files':
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

        print(f"{UI.colorize('-' * 65, 'GREEN')}")

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
                return 'insert_files'
        
        assert query is not None
        query = clean_text(query)

        # Send message to LLM client (which handles automatic session saving)
        response = self.llm_client.send_message(query)
        self._report_token_usage(query, response)

        assert response is not None
        comments = response_parser(response)

        if comments:
            print("\n" + UI.colorize("LLM Explanation / Reasoning:", "BRIGHT_CYAN"))
            print(comments)
        else:
            print("\nNo explanation provided by the LLM.")

        print(f"{UI.colorize('=' * 65, 'BRIGHT_GREEN')}")
        print()
        logger.debug("Message sent and response processed successfully")

    def _report_token_usage(self, query, response):
        """Report token usage"""
        try:
            input_tokens = estimate_tokens(query)
            output_tokens = estimate_tokens(response)

            print(f"\n? Response's tokens statistics:")
            print(f"   Input      | Output")
            print(f"   {input_tokens:<10} | {output_tokens:<10}")
            print(f"{UI.colorize('-' * 65, 'GREEN')}")

        except Exception as e:
            print(f"   ?? Could not estimate token usage: {e}")

def parse_arguments():
    """Parse command line arguments"""
    logger.debug("Parsing command line arguments")
    parser = argparse.ArgumentParser(
        description="LLM Terminal Chat connected with most of LLM API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python chat.py
  python chat.py --proxy socks5://127.0.0.1:1080
  python chat.py --config /path/to/config.json
        """
    )

    parser.add_argument("-rd", "--root-dir", help="Root directory of the code project.")
    parser.add_argument("-r", "--read", nargs="+", help="List of readable files")
    parser.add_argument("-e", "--edit", nargs="+", help="List of editable files")
    parser.add_argument("-m", "--message", help="First message ready to send to the assistant")
    parser.add_argument("-p", "--proxy", metavar="PROXY_URL", help="Proxy URL (e.g., socks5://127.0.0.1:1080)")
    parser.add_argument("-c", "--config", metavar="CONFIG_PATH", help="Path to config.json configuration file")

    return parser.parse_args()

def main():
    """Entry point"""
    logger.debug("Entering main function")
    try:
        args = parse_arguments()

        if args.proxy:
            proxy_url = args.proxy.rstrip("/")
            error_msg = validate_proxy_url(proxy_url)
            if error_msg:
                print(f"{UI.colorize('Error:', 'RED')} Invalid proxy URL: {error_msg}")
                logger.error(f"Invalid proxy URL provided: {args.proxy} -- {error_msg}")
                sys.exit(1)
            logger.debug(f"Proxy enabled: {proxy_url}")
        
        chat = LLMChat(
            root_dir=args.root_dir,
            readable_files=args.read,
            editable_files=args.edit,
            first_message=args.message,
            proxy_url=args.proxy,
            config_path=args.config
        )
        chat.run()

    except KeyboardInterrupt:
        print(f"\n{UI.colorize('Goodbye!', 'BRIGHT_GREEN')}")
        logger.debug("Exiting due to KeyboardInterrupt")
        sys.exit(0)


if __name__ == "__main__":
    main()

