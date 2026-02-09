#!/usr/bin/env python3
"""Test session metadata functionality."""
import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from session_logger import SessionLogger

def test_session_metadata_preview():
    """Test that session metadata includes preview field."""
    # Temporarily override CONVERSATIONS_DIR
    original = config.CONVERSATIONS_DIR
    temp_dir = tempfile.mkdtemp()
    config.CONVERSATIONS_DIR = temp_dir
    
    try:
        # Create SessionLogger with a temp root directory
        root_dir = tempfile.mkdtemp()
        logger = SessionLogger(script_directory="/tmp", root_dir=root_dir)
        
        # Create conversation history with user message
        conversation_history = [
            {
                "timestamp": "2025-01-01T00:00:00",
                "role": "user",
                "content": "Hello, this is a test message with some content that should be truncated for the preview."
            },
            {
                "timestamp": "2025-01-01T00:00:01",
                "role": "assistant",
                "content": "This is the assistant response."
            },
            {
                "timestamp": "2025-01-01T00:00:02",
                "role": "user",
                "content": "Second user message that shouldn't appear in preview."
            }
        ]
        
        # Save session
        saved_path = logger.save_session(conversation_history)
        assert saved_path is not None
        
        # Load metadata
        metadata = logger.load_session_metadata(saved_path)
        assert metadata is not None
        
        # Check metadata fields
        assert "session_start_time" in metadata
        assert "last_saved_time" in metadata
        assert "interaction_count" in metadata
        assert "preview" in metadata
        assert "root_dir" in metadata
        
        # Verify interaction count (2 user messages)
        assert metadata["interaction_count"] == 2
        
        # Verify preview contains first user message
        preview = metadata["preview"]
        assert preview != ""
        assert "Hello" in preview
        assert "test message" in preview
        # Should not contain second user message
        assert "Second user message" not in preview
        # Should be truncated (max 200 chars)
        assert len(preview) <= 200
        
        print("✓ Session metadata includes preview field")
        
        # Test with no user messages
        conversation_history2 = [
            {
                "timestamp": "2025-01-01T00:00:00",
                "role": "assistant",
                "content": "Only assistant message."
            }
        ]
        
        logger2 = SessionLogger(script_directory="/tmp", root_dir=root_dir)
        saved_path2 = logger2.save_session(conversation_history2)
        metadata2 = logger2.load_session_metadata(saved_path2)
        
        assert metadata2["interaction_count"] == 0
        assert metadata2["preview"] == ""  # Empty preview for no user messages
        
        print("✓ Empty preview for sessions with no user messages")
        
    finally:
        config.CONVERSATIONS_DIR = original
        shutil.rmtree(temp_dir, ignore_errors=True)
        if 'root_dir' in locals() and os.path.exists(root_dir):
            shutil.rmtree(root_dir, ignore_errors=True)

def test_session_metadata_free_chat():
    """Test session metadata in free chat mode (root_dir=None)."""
    original = config.CONVERSATIONS_DIR
    temp_dir = tempfile.mkdtemp()
    config.CONVERSATIONS_DIR = temp_dir
    
    try:
        # Create SessionLogger with root_dir=None (free chat)
        logger = SessionLogger(script_directory="/tmp", root_dir=None)
        
        conversation_history = [
            {
                "timestamp": "2025-01-01T00:00:00",
                "role": "user",
                "content": "Free chat message"
            }
        ]
        
        saved_path = logger.save_session(conversation_history)
        metadata = logger.load_session_metadata(saved_path)
        
        # root_dir in metadata should be "free_chat" string
        assert metadata["root_dir"] == "free_chat"
        
        print("✓ Free chat mode metadata has correct root_dir")
        
    finally:
        config.CONVERSATIONS_DIR = original
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_load_session_metadata_method():
    """Test the load_session_metadata method specifically."""
    original = config.CONVERSATIONS_DIR
    temp_dir = tempfile.mkdtemp()
    config.CONVERSATIONS_DIR = temp_dir
    
    try:
        root_dir = tempfile.mkdtemp()
        logger = SessionLogger(script_directory="/tmp", root_dir=root_dir)
        
        conversation_history = [
            {
                "timestamp": "2025-01-01T00:00:00",
                "role": "user",
                "content": "Test message"
            }
        ]
        
        saved_path = logger.save_session(conversation_history)
        
        # Test load_session_metadata returns dict with expected keys
        metadata = logger.load_session_metadata(saved_path)
        assert isinstance(metadata, dict)
        
        expected_keys = ["session_start_time", "last_saved_time", 
                        "interaction_count", "preview", "root_dir"]
        for key in expected_keys:
            assert key in metadata, f"Missing key in metadata: {key}"
        
        # Test with non-existent path
        non_existent = "/tmp/nonexistent_session.toml.zip"
        metadata_none = logger.load_session_metadata(non_existent)
        assert metadata_none is None
        
        print("✓ load_session_metadata method works correctly")
        
    finally:
        config.CONVERSATIONS_DIR = original
        shutil.rmtree(temp_dir, ignore_errors=True)
        if 'root_dir' in locals() and os.path.exists(root_dir):
            shutil.rmtree(root_dir, ignore_errors=True)

def test_session_preview_truncation():
    """Test that preview is properly truncated."""
    original = config.CONVERSATIONS_DIR
    temp_dir = tempfile.mkdtemp()
    config.CONVERSATIONS_DIR = temp_dir
    
    try:
        root_dir = tempfile.mkdtemp()
        logger = SessionLogger(script_directory="/tmp", root_dir=root_dir)
        
        # Create a very long message
        long_message = "A" * 300  # 300 characters
        
        conversation_history = [
            {
                "timestamp": "2025-01-01T00:00:00",
                "role": "user",
                "content": long_message
            }
        ]
        
        saved_path = logger.save_session(conversation_history)
        metadata = logger.load_session_metadata(saved_path)
        
        preview = metadata["preview"]
        # Preview should be truncated to 200 chars
        assert len(preview) <= 200
        # Should start with the message
        assert preview.startswith("A")
        
        # Test with multi-line message
        multi_line_msg = "Line 1\nLine 2\nLine 3"
        conversation_history2 = [
            {
                "timestamp": "2025-01-01T00:00:00",
                "role": "user",
                "content": multi_line_msg
            }
        ]
        
        logger2 = SessionLogger(script_directory="/tmp", root_dir=root_dir)
        saved_path2 = logger2.save_session(conversation_history2)
        metadata2 = logger2.load_session_metadata(saved_path2)
        
        # Newlines should be replaced with spaces in preview
        preview2 = metadata2["preview"]
        assert "\n" not in preview2
        assert "Line 1 Line 2 Line 3" in preview2.replace("  ", " ").strip()
        
        print("✓ Preview truncation and formatting works correctly")
        
    finally:
        config.CONVERSATIONS_DIR = original
        shutil.rmtree(temp_dir, ignore_errors=True)
        if 'root_dir' in locals() and os.path.exists(root_dir):
            shutil.rmtree(root_dir, ignore_errors=True)

if __name__ == "__main__":
    test_session_metadata_preview()
    test_session_metadata_free_chat()
    test_load_session_metadata_method()
    test_session_preview_truncation()
    print("\n✅ All session metadata tests passed!")