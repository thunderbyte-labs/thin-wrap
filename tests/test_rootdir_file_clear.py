#!/usr/bin/env python3
"""Test that file lists are cleared when switching root directories."""
import sys
import os
import tempfile
import shutil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from chat import LLMChat

def test_rootdir_file_clearing():
    """Test that file lists are cleared when switching between different roots."""
    # Create temp directories
    temp_dir = tempfile.mkdtemp()
    config_dir = os.path.join(temp_dir, "config")
    os.makedirs(config_dir, exist_ok=True)
    
    # Create two project directories
    project1 = os.path.join(temp_dir, "project1")
    project2 = os.path.join(temp_dir, "project2")
    os.makedirs(project1, exist_ok=True)
    os.makedirs(project2, exist_ok=True)
    
    # Create some test files
    with open(os.path.join(project1, "file1.txt"), "w") as f:
        f.write("test")
    with open(os.path.join(project2, "file2.txt"), "w") as f:
        f.write("test")
    
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
    
    try:
        # Create LLMChat with project1 as root
        chat = LLMChat(root_dir=project1, config_path=config_path)
        assert chat.root_dir == project1
        assert chat.free_chat_mode == False
        
        # Add some files to context (simulate via menu)
        chat.editable_files = [os.path.join(project1, "file1.txt")]
        chat.readable_files = [os.path.join(project1, "file1.txt")]
        
        # Switch to project2 - files should be cleared
        chat.set_root_dir(project2)
        assert chat.root_dir == project2
        assert chat.editable_files == []
        assert chat.readable_files == []
        
        # Add files in project2
        chat.editable_files = [os.path.join(project2, "file2.txt")]
        
        # Switch back to project1 - files should be cleared again
        chat.set_root_dir(project1)
        assert chat.root_dir == project1
        assert chat.editable_files == []
        assert chat.readable_files == []
        
        print("✓ File clearing when switching root directories test passed")
        
        # Test: switching to same directory (different path representation) should not clear files
        # Add files again
        chat.editable_files = [os.path.join(project1, "file1.txt")]
        
        # Create a symlink to project1
        symlink_path = os.path.join(temp_dir, "symlink_to_project1")
        os.symlink(project1, symlink_path)
        
        # Switch via symlink - should recognize it's the same directory and not clear files
        chat.set_root_dir(symlink_path)
        # After resolution, root_dir should be project1
        assert os.path.realpath(chat.root_dir) == project1
        # Files should still be there (same directory)
        assert len(chat.editable_files) == 1
        assert chat.editable_files[0] == os.path.join(project1, "file1.txt")
        
        print("✓ Same directory detection preserves files test passed")
        
    finally:
        # Cleanup
        if 'TEST_KEY' in os.environ:
            del os.environ['TEST_KEY']
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_rootdir_file_clearing()