"""
CROSS-PLATFORM COMPATIBILITY NOTES:
- This configuration is designed to work on Windows, macOS, and Linux
- Editor selection prioritizes cross-platform options first (notepad on Windows, nano/vim on Unix)
- Proxy configuration uses cross-platform libraries (requests, httpx)
- File paths use os.path for cross-platform compatibility
- Logging and temp file handling use cross-platform Python stdlib
"""

"""Configuration constants and settings for LLM Terminal Chat"""
import os
import logging
from rich.logging import RichHandler
import platform
from platformdirs import user_data_dir

# Application Configuration
APP_NAME = "thin-wrap"

# Session Storage
SESSION_BASE_DIR = user_data_dir(APP_NAME, appauthor=False, ensure_exists=True)
CONVERSATIONS_DIR = os.path.join(SESSION_BASE_DIR, "conversations")

# Logging Configuration
LOG_LEVEL = logging.INFO

#LOG_FORMAT = '%(asctime)s|%(levelname)s|%(filename)s:%(lineno)d|%(message)s' #for non rich.logging.RichHandler's handler
LOG_FORMAT = '%(message)s' # for RichHandler

#LOG_FILE = 'llm_chat_debug.log' #for logging.FileHandler's handler 
#LOG_HANDLER_FILE = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')  # Output to file
#LOG_HANDLER_DEFAULT = logging.StreamHandler() # Defaults handler (equivalent to not specifying anything)
LOG_HANDLER_RICH =  RichHandler(rich_tracebacks=True, tracebacks_show_locals=True, markup=True, show_time=True, show_path=True)

def setup_logging():
    """Configure logging for the entire application"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format=LOG_FORMAT,
        handlers=[
            LOG_HANDLER_RICH,
            #LOG_HANDLER_DEFAULT,
            #LOG_HANDLER_FILE,
            ]
    )

# LLM Configuration
SUPPORTED_MODELS = {
    "claude-sonnet-4-20250514": {
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1/"
    },
    "deepseek-reasoner": {
        "api_key_env": "DEEPSEEK_API_KEY", 
        "api_base": "https://api.deepseek.com/v1"
    },
    "x-ai/grok-4.1-fast": {
        "api_key_env": "OPENROUTER_API_KEY", 
        "api_base": "https://openrouter.ai/api/v1"
    },
    "anthropic/claude-sonnet-4.5": {
        "api_key_env": "OPENROUTER_API_KEY", 
        "api_base": "https://openrouter.ai/api/v1"
    },
    "hera/qwen": {
        "api_key_env": "HERA_API_KEY", 
        "api_base": "https://hera-llm.thunderbyte.ovh/v1"
    },
    "baidu/ernie-4.5-300b-a47b": {
        "api_key_env": "OPENROUTER_API_KEY",
        "api_base": "https://openrouter.ai/api/v1",
    }
}

# Token Configuration
MIN_TOKENS = 100
MAX_TOKENS = 16000


# History and Logging
HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".llm_chat_history")
HISTORY_LENGTH = 1000
LOG_PREFIX = "llm_session_"

# UI Configuration
BANNER_WIDTH = 70
PREVIEW_MAX_LENGTH = 500

# Text Processing
UNICODE_REPLACEMENTS = {
    '\u201c': '"',
    '\u201d': '"',
    '\u2018': "'",
    '\u2019': "'",
    '\u2013': '-',
    '\u2014': '--',
    '\u2026': '...',
    '\u00a0': ' ',
}

# Terminal Configuration
TERMINAL_WIDTH_FALLBACK = 120

# Proxy Configuration
PROXY_CONNECTION_TIMEOUT = 30
PROXY_VERIFICATION_TIMEOUT = 10
PROXY_RETRY_ATTEMPTS = 3

# Commands
COMMANDS = {
    '/clear': 'Clear session context',
    '/bye': 'Exit (auto-saves session log)',
    '/?': 'Help for a command', 
    '/help': 'Help for a command',
    '/model': 'Switch AI model (claude/deepseek)',
    '/reload': 'Reload a previous conversation',
    '/rootdir': 'Show or set project root directory',
    '/files': 'Handle Ctrl+B file context menu'
}


