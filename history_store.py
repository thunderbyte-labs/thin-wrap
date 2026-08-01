"""Persistent history for recent roots and proxies, stored in a single JSON file."""

import json
import logging
from pathlib import Path

from proxy_wrapper import validate_proxy_url, normalize_proxy_url

logger = logging.getLogger(__name__)


class HistoryStore:
    """Loads, saves and maintains recent_root_dirs and recent_proxies lists."""

    def __init__(self, history_file: Path) -> None:
        self.history_file = history_file
        self.recent_roots: list[str] = []
        self.recent_proxies: list[str] = []
        self._load()

    # -----------------------------------------------------------------
    # public API
    # -----------------------------------------------------------------

    def add_root(self, root: str) -> None:
        """Normalise, deduplicate and persist *root* at the front."""
        root = str(Path(root).resolve())
        if root in self.recent_roots:
            self.recent_roots.remove(root)
        self.recent_roots.insert(0, root)
        self.recent_roots = self.recent_roots[:10]
        self._save()

    def add_proxy(self, proxy_url: str) -> None:
        """Normalise, deduplicate and persist *proxy_url* at the front."""
        if not proxy_url:
            return
        normalized = normalize_proxy_url(proxy_url)
        if normalized in self.recent_proxies:
            self.recent_proxies.remove(normalized)
        elif proxy_url in self.recent_proxies:
            self.recent_proxies.remove(proxy_url)
        self.recent_proxies.insert(0, normalized)
        self.recent_proxies = self.recent_proxies[:10]
        self._save()

    def load(self) -> None:
        """Re-read the on-disk history file (useful after external writes)."""
        self._load()

    # -----------------------------------------------------------------
    # internal persistence
    # -----------------------------------------------------------------

    def _load(self) -> None:
        try:
            if self.history_file.exists():
                data = json.loads(self.history_file.read_text(encoding="utf-8"))
                self.recent_roots = [
                    r
                    for r in data.get("recent_root_dirs", [])
                    if Path(r).is_dir()
                ]
                valid_proxies: list[str] = []
                seen: set[str] = set()
                for proxy in data.get("recent_proxies", []):
                    if validate_proxy_url(proxy) is None:
                        n = normalize_proxy_url(proxy)
                        if n not in seen:
                            seen.add(n)
                            valid_proxies.append(n)
                self.recent_proxies = valid_proxies
        except Exception as e:
            logger.debug(f"Failed to load history: {e}")

    def _save(self) -> None:
        try:
            existing: dict = {}
            if self.history_file.exists():
                existing = json.loads(self.history_file.read_text(encoding="utf-8"))
            existing["recent_root_dirs"] = self.recent_roots[:10]
            existing["recent_proxies"] = self.recent_proxies[:10]
            self.history_file.write_text(
                json.dumps(existing, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.debug(f"Failed to save history: {e}")
