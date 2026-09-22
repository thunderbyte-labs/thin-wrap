"""In-memory cache of file-content hashes used to avoid re-sending files.

The LLM keeps the whole conversation in its context, so when a file is
re-sent with byte-identical content, the caller can emit a short notice
instead of the full content and save tokens.

The cache is transactional:

- ``stage`` records the hash of every new/changed file sent in the current
  request, but does not confirm anything yet.
- ``commit`` is called only once the send *and* the reception of the LLM
  reply both succeeded, moving staged hashes into the committed set.
- ``rollback`` discards staged hashes when the request failed or was
  interrupted (Ctrl+C), so no file is ever reported as "already sent" when
  it never actually reached the LLM.

Only the standard library is used (``hashlib``), so there are no new
dependencies.
"""

import hashlib


class FileHashCache:
    """Track, per file path, the md5 of the content last committed to the LLM."""

    def __init__(self) -> None:
        self._committed: dict[str, str] = {}
        self._pending: dict[str, str] = {}

    @staticmethod
    def hash_content(content: str) -> str:
        """Return the hex md5 digest of *content* encoded as UTF-8."""
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def is_unchanged(self, path: str, digest: str) -> bool:
        """True when *path* was already committed (or staged) with *digest*."""
        return self._committed.get(path) == digest or self._pending.get(path) == digest

    def stage(self, path: str, digest: str) -> None:
        """Record the *digest* currently being sent for *path* (unconfirmed)."""
        self._pending[path] = digest

    def commit(self) -> None:
        """Confirm all staged hashes (send + reply succeeded)."""
        self._committed.update(self._pending)
        self._pending.clear()

    def rollback(self) -> None:
        """Discard staged hashes (send failed or was interrupted)."""
        self._pending.clear()

    def clear(self) -> None:
        """Forget everything (e.g. after /clear, /reload or a root switch)."""
        self._committed.clear()
        self._pending.clear()
