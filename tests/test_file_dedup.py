"""Tests for the file-content deduplication cache and query wiring."""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from file_hash_cache import FileHashCache
from file_processor import generate_file_query


def _write_file(root: Path, name: str, content: str) -> str:
    path = root / name
    path.write_text(content, encoding="utf-8")
    return str(path)


# =========================================================================
# FileHashCache unit tests
# =========================================================================


def test_hash_content_is_stable_md5():
    cache = FileHashCache()
    assert cache.hash_content("hello\n") == cache.hash_content("hello\n")
    assert cache.hash_content("hello\n") != cache.hash_content("hello \n")
    assert len(cache.hash_content("x")) == 32


def test_stage_commit_then_is_unchanged():
    cache = FileHashCache()
    digest = cache.hash_content("content")
    cache.stage("/a.py", digest)
    # staged but not committed: still reported unchanged (same digest)
    assert cache.is_unchanged("/a.py", digest)
    cache.commit()
    assert cache.is_unchanged("/a.py", digest)


def test_stage_rollback_forgets_pending():
    cache = FileHashCache()
    cache.stage("/a.py", cache.hash_content("content"))
    cache.rollback()
    assert not cache.is_unchanged("/a.py", cache.hash_content("content"))


def test_rollback_keeps_committed():
    cache = FileHashCache()
    d1 = cache.hash_content("v1")
    cache.stage("/a.py", d1)
    cache.commit()
    d2 = cache.hash_content("v2")
    cache.stage("/b.py", d2)
    cache.rollback()
    assert cache.is_unchanged("/a.py", d1)
    assert not cache.is_unchanged("/b.py", d2)


def test_clear_forgets_everything():
    cache = FileHashCache()
    cache.stage("/a.py", cache.hash_content("content"))
    cache.commit()
    cache.clear()
    assert not cache.is_unchanged("/a.py", cache.hash_content("content"))


# =========================================================================
# generate_file_query dedup behaviour
# =========================================================================


def test_first_send_includes_content_and_stages():
    import tempfile

    cache = FileHashCache()
    with tempfile.TemporaryDirectory() as tmp:
        path = _write_file(Path(tmp), "app.py", "print('hello')\n")
        query = generate_file_query(tmp, [path], [], "do it", file_hash_cache=cache)
        assert "print('hello')" in query
        digest = cache.hash_content("print('hello')\n")
        # staged for commit, not yet committed
        assert cache.is_unchanged(path, digest)


def test_unchanged_file_is_not_re_sent_after_commit(tmp_path):
    cache = FileHashCache()
    path = _write_file(tmp_path, "app.py", "print('hello')\n")

    query1 = generate_file_query(
        str(tmp_path), [path], [], "do it", file_hash_cache=cache
    )
    assert "print('hello')" in query1
    cache.commit()

    query2 = generate_file_query(
        str(tmp_path), [path], [], "again", file_hash_cache=cache
    )
    assert "print('hello')" not in query2
    assert "FILE DEDUPLICATION NOTICE" in query2
    assert "THIN-WRAP FILE DEDUPLICATION" not in query2


def test_changed_file_is_re_sent_after_commit(tmp_path):
    cache = FileHashCache()
    path = _write_file(tmp_path, "app.py", "print('v1')\n")

    generate_file_query(str(tmp_path), [path], [], "do it", file_hash_cache=cache)
    cache.commit()

    # modify the file
    _write_file(tmp_path, "app.py", "print('v2')\n")
    query = generate_file_query(
        str(tmp_path), [path], [], "again", file_hash_cache=cache
    )
    assert "print('v2')" in query
    assert "print('v1')" not in query


def test_unchanged_after_rollback_is_re_sent(tmp_path):
    cache = FileHashCache()
    path = _write_file(tmp_path, "app.py", "print('hello')\n")

    generate_file_query(str(tmp_path), [path], [], "do it", file_hash_cache=cache)
    cache.rollback()  # send failed / interrupted

    query = generate_file_query(
        str(tmp_path), [path], [], "retry", file_hash_cache=cache
    )
    assert "print('hello')" in query
    assert "DEDUPLICATION" not in query


def test_no_cache_always_includes_content(tmp_path):
    path = _write_file(tmp_path, "app.py", "print('hello')\n")
    query1 = generate_file_query(str(tmp_path), [path], [], "do it")
    query2 = generate_file_query(str(tmp_path), [path], [], "again")
    assert "print('hello')" in query1
    assert "print('hello')" in query2
    assert "DEDUPLICATION" not in query2


def test_editable_file_is_deduped_too(tmp_path):
    cache = FileHashCache()
    path = _write_file(tmp_path, "app.py", "print('hello')\n")

    generate_file_query(str(tmp_path), [], [path], "do it", file_hash_cache=cache)
    cache.commit()

    query = generate_file_query(
        str(tmp_path), [], [path], "again", file_hash_cache=cache
    )
    assert "print('hello')" not in query
    assert "FILE DEDUPLICATION NOTICE" in query
    assert "THIN-WRAP FILE DEDUPLICATION" not in query
