"""Centralized file path resolution utilities."""

import os
from pathlib import Path


def resolve_path(path: str, root_dir: str | None = None) -> str:
    """
    Resolve a path to an absolute, normalized path.

    Args:
        path: Input path (absolute or relative)
        root_dir: Root directory for resolving relative paths

    Returns:
        Resolved absolute path string
    """
    path_obj = Path(path).expanduser()

    if not path_obj.is_absolute() and root_dir:
        path_obj = Path(root_dir) / path_obj

    try:
        return str(path_obj.resolve())
    except (OSError, RuntimeError, ValueError):
        return os.path.abspath(str(path_obj))
