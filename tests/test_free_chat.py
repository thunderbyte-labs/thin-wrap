#!/usr/bin/env python3
"""Test free chat mode functionality."""
import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from session_logger import SessionLogger

def test_session_logger_free_chat():
    """Test SessionLogger with root_dir=None (free chat mode)."""
    # Temporarily override CONVERSATIONS_DIR to a temp directory
    original = config.CONVERSATIONS_DIR
    temp_dir = tempfile.mkdtemp()
    config.CONVERSATIONS_DIR = temp_dir
    
    try:
        # Create SessionLogger with root_dir=None
        logger = SessionLogger(script_directory="/tmp", root_dir=None)
        assert logger.root_dir is None
        # conversation_dir should be free_chat subdirectory
        expected = os.path.join(temp_dir, "free_chat")
        assert logger.conversation_dir == expected
        # session_path should be inside that directory
        assert logger.session_path.startswith(expected)
        # Save a dummy session
        dummy_history = [
            {"role": "user", "content": "hello", "timestamp": "2025-01-01T00:00:00"},
            {"role": "assistant", "content": "hi", "timestamp": "2025-01-01T00:00:01"}
        ]
        saved_path = logger.save_session(dummy_history)
        assert saved_path is not None
        # Load it back
        loaded = logger.load_session(saved_path)
        assert loaded is not None
        # metadata root_dir should be "free_chat"
        assert loaded["metadata"]["root_dir"] == "free_chat"
        # List sessions
        sessions = logger.list_available_sessions()
        assert len(sessions) == 1
        print("✓ SessionLogger free chat mode test passed")
    finally:
        config.CONVERSATIONS_DIR = original
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_session_logger_free_chat()