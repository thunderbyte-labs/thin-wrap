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
from platformdirs import user_data_dir
import json
from pathlib import Path
import sys

# Application Configuration
APP_NAME = "thin-wrap"

# Session Storage
SESSION_BASE_DIR = user_data_dir(APP_NAME, appauthor=False, ensure_exists=True)
CONVERSATIONS_DIR = os.path.join(SESSION_BASE_DIR, "conversations")

# Logging Configuration
LOG_LEVEL = logging.INFO

# LOG_FORMAT = '%(asctime)s|%(levelname)s|%(filename)s:%(lineno)d|%(message)s' #for non rich.logging.RichHandler's handler
LOG_FORMAT = "%(message)s"  # for RichHandler

# LOG_FILE = 'llm_chat_debug.log' #for logging.FileHandler's handler
# LOG_HANDLER_FILE = logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')  # Output to file
# LOG_HANDLER_DEFAULT = logging.StreamHandler() # Defaults handler (equivalent to not specifying anything)
LOG_HANDLER_RICH = RichHandler(
    rich_tracebacks=True,
    tracebacks_show_locals=True,
    markup=True,
    show_time=True,
    show_path=True,
)


def setup_logging():
    """Configure logging for the entire application"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format=LOG_FORMAT,
        handlers=[
            LOG_HANDLER_RICH,
            # LOG_HANDLER_DEFAULT,
            # LOG_HANDLER_FILE,
        ],
    )


# LLM Configuration - will be loaded from config.json
# Use get_models() instead of accessing SUPPORTED_MODELS directly

# Global variable to store config file path once determined
_CONFIG_PATH = None


def set_config_path(config_path: str | None = None) -> None:
    """
    Set the configuration file path.

    Args:
        config_path: Path to config.json file. If None, will be determined automatically
    """
    global _CONFIG_PATH
    _CONFIG_PATH = config_path


def _get_script_dir() -> Path:
    """Get directory where script/executable is located (supports pyinstaller)."""
    if getattr(sys, "frozen", False):
        # Running as compiled executable (pyinstaller)
        return Path(sys.executable).parent.resolve()
    else:
        # Running as script
        return Path(__file__).parent.resolve()


def _load_config_internal(config_path: str | None = None) -> dict:
    """
    Internal method to load configuration from config.json file.

    Args:
        config_path: Optional path to config.json. If None, will search in:
                    1. Same directory as the executable/script
                    2. Current working directory
                    3. Interactive selection if not found

    Returns:
        dict: Complete configuration dictionary

    Raises:
        FileNotFoundError: If config.json cannot be found
        json.JSONDecodeError: If config.json is invalid
        ValueError: If config.json is missing required sections
    """
    global _CONFIG_PATH

    search_path = config_path or _CONFIG_PATH

    if search_path:
        config_file = Path(search_path).expanduser().resolve()
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")
    else:
        script_dir = _get_script_dir()
        config_file = script_dir / "config.json"

        if not config_file.exists():
            config_file = Path.cwd() / "config.json"

        if not config_file.exists():
            try:
                from ui import UI

                print(f"{UI.colorize('Config file not found.', 'BRIGHT_YELLOW')}")
                print(f"Searched in:")
                print(f"  - {script_dir / 'config.json'}")
                print(f"  - {Path.cwd() / 'config.json'}")

                config_file_path = UI.interactive_selection(
                    prompt_title="Config file selection:",
                    prompt_message="Enter path to config.json file (Tab for completion, ~ for home):",
                    no_items_message="No config file found.",
                    items=[],
                    item_formatter=lambda x: x,
                    allow_new=True,
                    new_item_validator=lambda p: p.is_file()
                    and p.name == "config.json",
                    new_item_error="Not a valid config.json file",
                )

                if not config_file_path:
                    raise FileNotFoundError("No config file selected.")

                config_file = Path(config_file_path).expanduser().resolve()
            except ImportError:
                raise FileNotFoundError(
                    f"config.json not found. Searched in:\n"
                    f"  - {script_dir / 'config.json'}\n"
                    f"  - {Path.cwd() / 'config.json'}\n"
                    f"Please create config.json or specify path with --config"
                )

    _CONFIG_PATH = str(config_file)

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Invalid JSON in {config_file}: {e.msg}", e.doc, e.pos
        )

    if "models" not in config_data:
        raise ValueError(f"Config file {config_file} must have 'models' section")

    # STRICT VALIDATION FOR NEW FORMAT
    for model_name, model_config in config_data["models"].items():
        if "model" not in model_config:
            raise ValueError(
                f"Model '{model_name}' is missing required 'model' field. "
                f"Every entry must now contain 'model': 'actual-model-name'"
            )
        if "api_key" not in model_config:
            raise ValueError(f"Model '{model_name}' missing 'api_key' field")
        if "api_base_url" not in model_config:
            raise ValueError(f"Model '{model_name}' missing 'api_base_url' field")

        if "proxy" in model_config:
            if not isinstance(model_config["proxy"], bool):
                raise ValueError(f"Model '{model_name}' proxy field must be boolean")
        else:
            model_config["proxy"] = False

        # NEW: allow plugins as list (old) OR dict (new Qwen Beijing)
        if "plugins" in model_config:
            plugins_value = model_config["plugins"]
            if not isinstance(plugins_value, (list, dict)):
                raise ValueError(
                    f"Model '{model_name}' plugins field must be a list or dict, got {type(plugins_value)}"
                )
        else:
            model_config["plugins"] = []

    if "backup" not in config_data:
        config_data["backup"] = {}

    backup_config = config_data["backup"]
    # New master switch: enabled (default true)
    if "enabled" in backup_config:
        if not isinstance(backup_config["enabled"], bool):
            raise ValueError("backup.enabled must be a boolean")
    else:
        backup_config.setdefault("enabled", True)

    backup_config.setdefault("timestamp_format", "%Y%m%d%H%M%S")
    backup_config.setdefault("extra_string", "thin-wrap")

    # Renamed: overwrite_original replaces backup_old_file.
    # Backward compatibility: if overwrite_original is not set, use backup_old_file (if present) else default True.
    if "overwrite_original" not in backup_config:
        if "backup_old_file" in backup_config:
            # Support legacy configs that still use the old key name
            if not isinstance(backup_config["backup_old_file"], bool):
                raise ValueError("backup.backup_old_file must be a boolean")
            backup_config["overwrite_original"] = backup_config.pop("backup_old_file")
        else:
            backup_config["overwrite_original"] = True
    else:
        if not isinstance(backup_config["overwrite_original"], bool):
            raise ValueError("backup.overwrite_original must be a boolean")

    return config_data


def get_models() -> dict:
    """
    Get the models configuration from config.json.
    Re-reads the file every time it's called to pick up changes.

    Returns:
        dict: Models configuration dictionary

    Raises:
        FileNotFoundError: If config.json cannot be found
        json.JSONDecodeError: If config.json is invalid
        ValueError: If config.json is missing required sections
    """
    config_data = _load_config_internal()
    return config_data.get("models", {})


def backup() -> dict:
    """
    Get the backup configuration from config.json.
    Re-reads the file every time it's called to pick up changes.

    Returns:
        dict: Backup configuration dictionary with keys:
            - enabled: bool, master switch to disable all backup creation (default True)
            - timestamp_format: str, format for datetime timestamp
            - extra_string: str or None, extra string to include in backup filename
            - overwrite_original: bool, whether to rename the original file to a timestamped backup
              before writing the new content (default True). If False, new content is written to a
              separate timestamped file and the original is left unchanged.
              Only meaningful when enabled is True.

    Raises:
        FileNotFoundError: If config.json cannot be found
        json.JSONDecodeError: If config.json is invalid
        ValueError: If config.json is missing required sections
    """
    config_data = _load_config_internal()
    return config_data.get("backup", {})


# UI Configuration
BANNER_WIDTH = 70

# Text Processing
UNICODE_REPLACEMENTS = {
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
    "\u2013": "-",
    "\u2014": "--",
    "\u2026": "...",
    "\u00a0": " ",
}

# Terminal Configuration
TERMINAL_WIDTH_FALLBACK = 120

# Commands
COMMANDS = {
    "/clear": "Clear session context",
    "/bye": "Exit (auto-saves session log)",
    "/?": "Help for a command",
    "/help": "Help for a command",
    "/model": "Switch AI model",
    "/reload": "Reload a previous conversation",
    "/rootdir": "Show or set project root directory (option 0 for free chat mode)",
    "/files": "Handle Ctrl+B file context menu",
    "/proxy": "Manage proxy (off to disable, number for previous, or new URL like socks5://127.0.0.1:1080)",
}

