
"""User interface and banner display"""
import config

class UI:
    COLORS = {
        'RESET': '\033[0m',
        'BOLD': '\033[1m',
        'DIM': '\033[2m',
        'UNDERLINE': '\033[4m',
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
        'BG_BLACK': '\033[40m',
        'BG_RED': '\033[41m',
        'BG_GREEN': '\033[42m',
        'BG_YELLOW': '\033[43m',
        'BG_BLUE': '\033[44m',
        'BG_MAGENTA': '\033[45m',
        'BG_CYAN': '\033[46m',
        'BG_WHITE': '\033[47m',
    }

    @staticmethod
    def colorize(text, color_name):
        """Apply color to text"""
        if color_name in UI.COLORS:
            return f"{UI.COLORS[color_name]}{text}{UI.COLORS['RESET']}"
        return text

    @staticmethod
    def print_banner(script_directory):
        """Print concise welcome banner"""
        print("=" * config.BANNER_WIDTH)
        print("   LLM Terminal Chat")
        print("=" * config.BANNER_WIDTH)
        print("Commands: /clear, /bye, /help, /save, /model")
        print()
        print("Features:")
        print("  - Multi-LLM support (/model ...)")
        print("  - File context management: Ctrl+Space")
        print("  - Multi-line input")
        print("  - Code editing with versioning")
        print("  - Session logging")
        print("  - Proxy support")
        print()
        print("=" * config.BANNER_WIDTH)
        print()

    @staticmethod
    def show_startup_message():
        """Show startup message"""
        print("Start chatting!\n")

    @staticmethod
    def show_exit_message(log_path=None):
        """Show exit message with optional log path"""
        if log_path:
            print(f"📝 Session log saved to: {log_path}")
        print("Goodbye!")
