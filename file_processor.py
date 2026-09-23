import datetime
import difflib
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

import config
from file_hash_cache import FileHashCache
from path_utils import resolve_path
from strings import t
from tags import Xml

logger = logging.getLogger(__name__)

_FILE_UNCHANGED_NOTICE = (
    "[FILE DEDUPLICATION NOTICE: the content of this file is "
    "byte-for-byte identical (md5 {digest}) to the copy of this file already "
    "sent to you earlier in this conversation. Do NOT request its content "
    "again. Reuse the exact copy you already received.]"
)


def _file_body(path: str, content: str, cache: FileHashCache | None) -> str:
    """Return the body to embed for *path*, or a short notice when unchanged.

    When *cache* is set and the file's current content hashes identically to
    the last committed version, the full content is replaced by a notice so
    tokens are not wasted re-sending it. New or changed files are staged for
    commit once the send (and the LLM's reply) succeed.
    """
    if cache is None:
        return content
    digest = cache.hash_content(content)
    if cache.is_unchanged(path, digest):
        return _FILE_UNCHANGED_NOTICE.format(digest=digest)
    cache.stage(path, digest)
    return content


def _read_file_content(full_path: str, root_dir: str) -> str:
    """Read file content with robust error handling and path resolution."""
    try:
        # Resolve the path first
        resolved_path = resolve_path(full_path, root_dir)
        path = Path(resolved_path)

        if not path.exists():
            raise FileNotFoundError(
                f"File does not exist: {full_path} (resolved to: {resolved_path})"
            )

        return path.read_text(encoding="utf-8")
    except PermissionError:
        raise PermissionError(
            f"Cannot read file due to permissions: {full_path}"
        ) from None
    except UnicodeDecodeError:
        raise UnicodeDecodeError(
            "utf-8", b"", 0, 0, f"Cannot decode file with UTF-8: {full_path}"
        ) from None
    except Exception as e:
        raise Exception(f"Error reading file {full_path}: {str(e)}") from e
