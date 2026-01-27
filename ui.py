"""UI utilities for LLM Terminal Chat"""
import os
from pathlib import Path
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import PathCompleter

class UI:
    # ANSI color codes
    COLORS = {
        'BLACK': '\033[30m',
        'RED': '\033[31m',
        'GREEN': '\033[32m',
        'YELLOW': '\033[33m',
        'BLUE': '\033[34m',
        'MAGENTA': '\033[35m',
        'CYAN': '\033[36m',
        'WHITE': '\033[37m',
        'BRIGHT_BLACK': '\033[90m',
        'BRIGHT_RED': '\033[91m',
        'BRIGHT_GREEN': '\033[92m',
        'BRIGHT_YELLOW': '\033[93m',
        'BRIGHT_BLUE': '\033[94m',
        'BRIGHT_MAGENTA': '\033[95m',
        'BRIGHT_CYAN': '\033[96m',
        'BRIGHT_WHITE': '\033[97m',
        'BOLD': '\033[1m',
        'UNDERLINE': '\033[4m',
        'RESET': '\033[0m'
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
            with open(banner_file, 'r', encoding='utf-8') as f:
                banner_content = f.read()
            print(UI.colorize(banner_content, 'BRIGHT_GREEN'))
        else:
            print(UI.colorize("=" * 70, 'BRIGHT_GREEN'))
            print(UI.colorize("LLM Terminal Chat", 'BRIGHT_GREEN'))
            print(UI.colorize("=" * 70, 'BRIGHT_GREEN'))

    @staticmethod
    def show_startup_message():
        """Show startup help message"""
        print("\n" + UI.colorize("Welcome to LLM Terminal Chat!", 'BRIGHT_CYAN'))
        print(UI.colorize("-" * 50, 'GREEN'))
        print(UI.colorize("Type your message and press ", 'BRIGHT_WHITE') + 
              UI.colorize("Alt+Enter", 'BRIGHT_YELLOW') + 
              UI.colorize(" to send.", 'BRIGHT_WHITE'))
        print(UI.colorize("Press ", 'BRIGHT_WHITE') + 
              UI.colorize("Ctrl+B", 'BRIGHT_YELLOW') + 
              UI.colorize(" to manage file context.", 'BRIGHT_WHITE'))
        print(UI.colorize("Type ", 'BRIGHT_WHITE') + 
              UI.colorize("/help", 'BRIGHT_YELLOW') + 
              UI.colorize(" for available commands.", 'BRIGHT_WHITE'))
        print(UI.colorize("-" * 50, 'GREEN'))

    @staticmethod
    def show_exit_message(log_path):
        """Show exit message with log location"""
        if log_path:
            print("\n" + UI.colorize("Session log saved to:", 'BRIGHT_CYAN'))
            print(f"  {log_path}")
        print("\n" + UI.colorize("Goodbye!", 'BRIGHT_GREEN'))

    @staticmethod
    def interactive_selection(prompt_title, prompt_message, no_items_message, items, 
                            item_formatter=lambda x: x, allow_new=False, 
                            new_item_validator=lambda x: True, new_item_error="Invalid item"):
        """
        Generic interactive selection function with history support
        """
        completer = PathCompleter(expanduser=True) if allow_new else None
        session = PromptSession(completer=completer)

        while True:
            if items:
                print(f"{UI.colorize(prompt_title, 'BRIGHT_CYAN')}")
                for i, item in enumerate(items, 1):
                    print(f"  {i}. {item_formatter(item)}")
                print(prompt_message)
            else:
                print(f"{UI.colorize(no_items_message, 'BRIGHT_CYAN')}")
                if allow_new:
                    print("Enter item path:")

            try:
                user_input = session.prompt("> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nSelection cancelled.")
                raise

            if not user_input:
                print(f"{UI.colorize('Error:', 'RED')} Empty input - please try again.")
                continue

            # Numeric selection from items
            if items and user_input.isdigit():
                idx = int(user_input) - 1
                if 0 <= idx < len(items):
                    chosen = items[idx]
                    print(f"{UI.colorize('Selected:', 'BRIGHT_CYAN')} {item_formatter(chosen)}")
                    return chosen
                else:
                    print(f"{UI.colorize('Error:', 'RED')} Number out of range.")
                    continue

            # Manual entry (only if allow_new is True)
            if allow_new:
                try:
                    new_item = Path(user_input).expanduser().resolve(strict=False)
                    if new_item_validator(new_item):
                        resolved_str = str(new_item)
                        print(f"{UI.colorize('Using:', 'BRIGHT_CYAN')} {item_formatter(resolved_str)}")
                        return resolved_str
                    else:
                        print(f"{UI.colorize('Error:', 'RED')} {new_item_error}: {user_input}")
                except Exception as e:
                    print(f"{UI.colorize('Error:', 'RED')} Invalid input: {e}")
            else:
                print(f"{UI.colorize('Error:', 'RED')} Please enter a valid number or enable new item entry.")