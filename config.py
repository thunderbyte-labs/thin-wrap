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
import json
from pathlib import Path

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

# LLM Configuration - will be loaded from models.json
SUPPORTED_MODELS = {}

def load_models_config(config_path=None):
    """
    Load models configuration from models.json file.
    
    Args:
        config_path: Optional path to models.json. If None, will search in:
                    1. Same directory as the executable/script
                    2. Current working directory
    
    Returns:
        dict: Models configuration
    
    Raises:
        FileNotFoundError: If models.json cannot be found
        json.JSONDecodeError: If models.json is invalid
    """
    global SUPPORTED_MODELS
    
    if config_path:
        config_file = Path(config_path)
    else:
        # Try to find models.json in the script/executable directory
        script_dir = Path(__file__).parent.resolve()
        config_file = script_dir / "models.json"
        
        # If not found, try current working directory
        if not config_file.exists():
            config_file = Path.cwd() / "models.json"
    
    if not config_file.exists():
        raise FileNotFoundError(
            f"models.json not found. Searched in:\n"
            f"  - {Path(__file__).parent.resolve() / 'models.json'}\n"
            f"  - {Path.cwd() / 'models.json'}\n"
            f"Please create models.json or specify path with --config"
        )
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            SUPPORTED_MODELS = json.load(f)
        
        # Validate that each model has required fields
        for model_name, model_config in SUPPORTED_MODELS.items():
            if 'api_key' not in model_config:
                raise ValueError(f"Model '{model_name}' missing 'api_key' field")
            if 'api_base_url' not in model_config:
                raise ValueError(f"Model '{model_name}' missing 'api_base_url' field")
        
        return SUPPORTED_MODELS
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Invalid JSON in {config_file}: {e.msg}",
            e.doc,
            e.pos
        )

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
    '/model': 'Switch AI model',
    '/reload': 'Reload a previous conversation',
    '/rootdir': 'Show or set project root directory',
    '/files': 'Handle Ctrl+B file context menu'
}
