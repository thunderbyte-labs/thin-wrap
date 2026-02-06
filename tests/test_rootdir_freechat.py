#!/usr/bin/env python3
"""Test root directory switching with free chat mode option."""
import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from chat import LLMChat

def test_set_root_dir_free_chat():
    """Test set_root_dir with FREE_CHAT_MODE."""
    # Create a temp directory for config and sessions
    temp_dir = tempfile.mkdtemp()
    config_dir = os.path.join(temp_dir, "config")
    os.makedirs(config_dir, exist_ok=True)
    
    # Create a minimal config.json
    config_data = {
        "models": {
            "test-model": {
                "api_key": "TEST_KEY",
                "api_base_url": "https://example.com/v1"
            }
        }
    }
    import json
    config_path = os.path.join(config_dir, "config.json")
    with open(config_path, 'w') as f:
        json.dump(config_data, f)
    
    # Set environment variable for API key
    os.environ['TEST_KEY'] = 'dummy'
    
    # Create a dummy root directory
    dummy_root = os.path.join(temp_dir, "project")
    os.makedirs(dummy_root, exist_ok=True)
    
    try:
        # Create LLMChat with a root directory (not free chat mode)
        chat = LLMChat(root_dir=dummy_root, config_path=config_path)
        assert chat.root_dir == dummy_root
        assert chat.free_chat_mode == False
        
        # Test switching to free chat mode
        chat.set_root_dir(chat.FREE_CHAT_MODE)
        assert chat.root_dir is None
        assert chat.free_chat_mode == True
        assert chat.editable_files == []
        assert chat.readable_files == []
        
        # Test switching back to a directory
        chat.set_root_dir(dummy_root)
        assert chat.root_dir == dummy_root
        assert chat.free_chat_mode == False
        
        print("✓ set_root_dir free chat mode switching test passed")
    finally:
        # Cleanup
        if 'TEST_KEY' in os.environ:
            del os.environ['TEST_KEY']
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_set_root_dir_free_chat()