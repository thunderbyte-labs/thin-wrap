#!/usr/bin/env python3.11

"""Main LLM Terminal Chat application"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import PathCompleter
import platformdirs

# Local application imports (after third-party and standard library)
import config
config.setup_logging()

from command_handler import CommandHandler
from file_processor import generate_query
from input_handler import InputHandler
from llm_client import LLMClient
from proxy_wrapper import create_proxy_wrapper, validate_proxy_url
from session_logger import SessionLogger
from text_utils import clean_text, estimate_tokens
from ui import UI

logger = logging.getLogger(__name__)

class LLMChat:
    def __init__(self, root_dir=None, readable_files=None, editable_files=None, first_message=None, proxy_url=None):
        logger.debug("Initializing LLMChat")
        self.script_directory = os.path.dirname(os.path.abspath(__file__))

        config_dir = Path(platformdirs.user_config_dir(config.APP_NAME))
        config_dir.mkdir(parents=True, exist_ok=True)
        history_file = config_dir / "history.json"
        self.recent_roots = self._load_recent_roots(history_file)
        self.history_file = history_file

        # Process root directory
        if root_dir is not None:
            root_path = Path(root_dir).expanduser().resolve()
            if not root_path.is_dir():
                raise ValueError(f"Specified root_dir is not a valid directory: {root_path}")
            self.root_dir = str(root_path)
            self._add_to_recent_roots(history_file, self.root_dir)
            print(f"{UI.colorize('Info:', 'BRIGHT_CYAN')} Using specified project root: {self.root_dir}")
        else:
            self.root_dir = self._interactive_root_selection()
            self._add_to_recent_roots(history_file, self.root_dir)

        # Resolve file paths
        root_path = Path(self.root_dir)
        self.editable_files = [str((Path(p).resolve() if Path(p).is_absolute() else (root_path / p)).resolve()) 
                              for p in (editable_files or [])]
        self.readable_files = [str((Path(p).resolve() if Path(p).is_absolute() else (root_path / p)).resolve())
                              for p in (readable_files or [])]
        self.first_message = "" if not first_message else first_message
        self.proxy_wrapper = create_proxy_wrapper(proxy_url) if proxy_url else None

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
        """Save current recent_roots list."""
        try:
            data = {"recent_root_dirs": self.recent_roots[:10]}
            history_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
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

    def _interactive_root_selection(self) -> str:
        """Interactive prompt for root selection with history and Tab autocompletion."""
        return UI.interactive_selection(
            prompt_title="Previous project roots:",
            prompt_message="Enter a number to select, or type a new path (Tab for completion, ~ for home):",
            no_items_message="No previous roots found.",
            items=self.recent_roots,
            item_formatter=lambda x: x,
            allow_new=True,
            new_item_validator=lambda p: p.is_dir(),
            new_item_error="Not a valid directory"
        )

    def set_root_dir(self, new_root: str, ask_to_reload: bool = True) -> None:
        """
        Change the current project root directory and update all dependent components.
        
        Args:
            new_root: New root directory path
            ask_to_reload: Whether to prompt user to reload a conversation from the new root
        """
        root_path = Path(new_root).expanduser().resolve()
        if not root_path.is_dir():
            raise ValueError(f"Specified root_dir is not a valid directory: {root_path}")
        
        old_root = self.root_dir
        self.root_dir = str(root_path)
        
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
            self._send_message(user_input)
            
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
        """Send message to LLM with specified token limit"""
        model = self.llm_client.get_current_model()
        logger.debug(f"Using model: {model}")

        print(f"{UI.colorize('-' * 65, 'GREEN')}")

        query, response_parser = generate_query(
            self.root_dir, self.readable_files, self.editable_files, message
        )
        query = clean_text(query)

        # Send message to LLM client (which handles automatic session saving)
        response = self.llm_client.send_message(query)
        self._report_token_usage(query, response)

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

            print(f"\n📊 Response's tokens statistics (estimated):")
            print(f"   Input      | Actual Output")
            print(f"   {input_tokens:<10} | {output_tokens:<10}")
            print(f"{UI.colorize('-' * 65, 'GREEN')}")

        except Exception as e:
            print(f"   ⚠️ Could not estimate token usage: {e}")

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
        """
    )

    parser.add_argument("-rd", "--root-dir", help="Root directory of the code project.")
    parser.add_argument("-r", "--read", nargs="+", help="List of readable files")
    parser.add_argument("-e", "--edit", nargs="+", help="List of editable files")
    parser.add_argument("-m", "--message", help="First message ready to send to the assistant")
    parser.add_argument("-p", "--proxy", metavar="PROXY_URL", help="Proxy URL (e.g., socks5://127.0.0.1:1080)")

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
            proxy_url=args.proxy
        )
        chat.run()

    except KeyboardInterrupt:
        print(f"\n{UI.colorize('Goodbye!', 'BRIGHT_GREEN')}")
        logger.debug("Exiting due to KeyboardInterrupt")
        sys.exit(0)


if __name__ == "__main__":
    main()

