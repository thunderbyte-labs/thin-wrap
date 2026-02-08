#!/usr/bin/env python3
"""Test the exact user scenario: switching roots with files in context."""
import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from chat import LLMChat

def test_user_scenario():
    """
    Simulate user scenario:
    1. Start in thin-wrap root with files added
    2. Switch to footstat root
    3. Verify files are cleared
    """
    temp_dir = tempfile.mkdtemp()
    config_dir = os.path.join(temp_dir, "config")
    os.makedirs(config_dir, exist_ok=True)
    
    # Create mock project directories
    thin_wrap = os.path.join(temp_dir, "thin-wrap")
    footstat = os.path.join(temp_dir, "footstat")
    os.makedirs(thin_wrap, exist_ok=True)
    os.makedirs(footstat, exist_ok=True)
    
    # Create some files in thin-wrap
    with open(os.path.join(thin_wrap, "chat.py"), "w") as f:
        f.write("print('hello')")
    with open(os.path.join(thin_wrap, "command_handler.py"), "w") as f:
        f.write("print('world')")
    with open(os.path.join(thin_wrap, "config.json"), "w") as f:
        f.write('{"test": true}')
    
    # Create minimal config
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
    
    os.environ['TEST_KEY'] = 'dummy'
    
    try:
        # Start in thin-wrap root (simulate via command line)
        chat = LLMChat(root_dir=thin_wrap, config_path=config_path)
        assert chat.root_dir == thin_wrap
        
        # Simulate user adding files via Ctrl+B menu
        # (In real usage, these would be added via FileMenuApp)
        chat.editable_files = [
            os.path.join(thin_wrap, "chat.py"),
            os.path.join(thin_wrap, "command_handler.py")
        ]
        chat.readable_files = [
            os.path.join(thin_wrap, "config.json")
        ]
        
        # Verify files are in context
        assert len(chat.editable_files) == 2
        assert len(chat.readable_files) == 1
        
        # Simulate /rootdir command to switch to footstat
        chat.set_root_dir(footstat)
        assert chat.root_dir == footstat
        
        # Files should be cleared
        assert chat.editable_files == []
        assert chat.readable_files == []
        
        # Verify _print_files_summary doesn't crash
        # (should return early due to empty lists)
        chat._print_files_summary()
        
        print("✓ User scenario test passed: files cleared when switching roots")
        
        # Additional test: switch back to thin-wrap, files should still be cleared
        chat.set_root_dir(thin_wrap)
        assert chat.editable_files == []
        assert chat.readable_files == []
        
        print("✓ Switching back also clears files (fresh start)")
        
    finally:
        if 'TEST_KEY' in os.environ:
            del os.environ['TEST_KEY']
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_user_scenario()