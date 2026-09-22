"""Configuration constants and settings for LLM Terminal Chat.

CROSS-PLATFORM COMPATIBILITY NOTES:
- This configuration is designed to work on Windows, macOS, and Linux
- Editor selection prioritizes cross-platform options first (notepad on Windows, nano/vim on Unix)
- Proxy configuration uses cross-platform libraries (requests, httpx)
- File paths use os.path for cross-platform compatibility
- Logging and temp file handling use cross-platform Python stdlib
"""

import json
import logging
import os
import sys
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir
from rich.logging import RichHandler

from strings import t

# Application Configuration
APP_NAME = "thin-wrap"

# App directories (appauthor=False for consistent cross-platform paths)
CONFIG_DIR = user_config_dir(APP_NAME, appauthor=False)
DATA_DIR = user_data_dir(APP_NAME, appauthor=False, ensure_exists=True)
CONVERSATIONS_DIR = os.path.join(DATA_DIR, "conversations")

# Logging Configuration
LOG_LEVEL = logging.WARNING

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
_CONFIG_PATH: str | None = None

# Cache keyed by (path, st_mtime_ns) → validated config dict
_CONFIG_CACHE: dict[tuple[str, int], dict] = {}


def set_config_path(config_path: str | None = None) -> None:
    """
    Set the configuration file path.

    Args:
        config_path: Path to config.json file. If None, will be determined automatically
    """
    global _CONFIG_PATH
    _CONFIG_PATH = config_path
    invalidate()


def invalidate() -> None:
    """Clear the config cache so the next call to get_models/backup re-reads disk."""
    global _CONFIG_CACHE
    _CONFIG_CACHE.clear()


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

                print(t("errors.config_not_found"))
                print(t("errors.searched_in"))
                print(f"  - {script_dir / 'config.json'}")
                print(f"  - {Path.cwd() / 'config.json'}")

                config_file_path = UI.interactive_selection(
                    prompt_title=t("prompts.config_selection_title"),
                    prompt_message=t("prompts.config_selection_prompt"),
                    no_items_message=t("prompts.no_config_found"),
                    items=[],
                    item_formatter=lambda x: x,
                    allow_new=True,
                    new_item_validator=lambda p: (
                        p.is_file() and p.name == "config.json"
                    ),
                    new_item_error=t("prompts.config_new_item_error"),
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
                ) from None

    _CONFIG_PATH = str(config_file)

    cache_key = (
        str(config_file),
        os.stat(config_file).st_mtime_ns,
    )
    if cache_key in _CONFIG_CACHE:
        return _CONFIG_CACHE[cache_key]

    try:
        with open(config_file, encoding="utf-8") as f:
            config_data = json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Invalid JSON in {config_file}: {e.msg}", e.doc, e.pos
        ) from None

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
        config_data["backup"] = {"enabled": False}

    backup_config = config_data["backup"]

    # Si "enabled" n'est pas explicitement présent → False par défaut
    if "enabled" not in backup_config:
        backup_config["enabled"] = False

    if not isinstance(backup_config["enabled"], bool):
        raise ValueError(
            f"backup.enabled must be a boolean.\nConfig file: {_CONFIG_PATH}"
        )

    if backup_config["enabled"]:
        # Strict: les 3 champs sont obligatoires uniquement quand enabled=True
        for field in ("timestamp_format", "extra_string", "overwrite_original"):
            if field not in backup_config:
                raise ValueError(
                    f"backup.{field} is required when backup.enabled is true.\n"
                    f"Config file: {_CONFIG_PATH}"
                )

        if not isinstance(backup_config["overwrite_original"], bool):
            raise ValueError(
                f"backup.overwrite_original must be a boolean.\nConfig file: {_CONFIG_PATH}"
            )

    # Support legacy backup_old_file → overwrite_original
    if "overwrite_original" not in backup_config and "backup_old_file" in backup_config:
        if not isinstance(backup_config["backup_old_file"], bool):
            raise ValueError(
                f"backup.backup_old_file must be a boolean.\nConfig file: {_CONFIG_PATH}"
            )
        backup_config["overwrite_original"] = backup_config.pop("backup_old_file")

    _CONFIG_CACHE[cache_key] = config_data
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
        dict: Backup configuration with keys:
            - enabled: bool (defaults to True when backup section exists)
            - timestamp_format: str (required when enabled=True)
            - extra_string: str (required when enabled=True)
            - overwrite_original: bool (required when enabled=True)

    Raises:
        FileNotFoundError, json.JSONDecodeError, ValueError
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
    "/clear": t("commands.descriptions.clear"),
    "/bye": t("commands.descriptions.bye"),
    "/help": t("commands.descriptions.help"),
    "/model": t("commands.descriptions.model"),
    "/reload": t("commands.descriptions.reload"),
    "/rootdir": t("commands.descriptions.rootdir"),
    "/files": t("commands.descriptions.files"),
    "/proxy": t("commands.descriptions.proxy"),
    "/nameconv": t("commands.descriptions.nameconv"),
}
