#!/usr/bin/env python3
"""Test proxy command functionality."""
import sys
import os
import tempfile
import json
import shutil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from chat import LLMChat

def test_proxy_history():
    """Test loading and saving proxy history."""
    # Create temp directory for config
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
    config_path = os.path.join(config_dir, "config.json")
    with open(config_path, 'w') as f:
        json.dump(config_data, f)
    
    # Set environment variable
    os.environ['TEST_KEY'] = 'dummy'
    
    # Create history.json with both roots and proxies
    history_data = {
        "recent_root_dirs": ["/tmp/project1", "/tmp/project2"],
        "recent_proxies": [
            "socks5://127.0.0.1:1080",
            "http://proxy.example.com:8080"
        ]
    }
    
    # Create the config directory structure expected by platformdirs
    # We'll monkey-patch config.CONVERSATIONS_DIR later
    import platformdirs
    user_data_dir = platformdirs.user_data_dir(config.APP_NAME, appauthor=False, ensure_exists=True)
    # Override the config dir via environment variable? Instead, we'll directly test LLMChat
    # which uses platformdirs internally. We'll need to mock platformdirs.user_config_dir.
    # For simplicity, test the internal methods directly.
    
    # Create a dummy LLMChat instance with a temp config path
    # This will create its own history file
    try:
        root_dir = os.path.join(temp_dir, "project_root")
        os.makedirs(root_dir, exist_ok=True)
        chat = LLMChat(root_dir=root_dir, config_path=config_path)
        # Access the history file path
        history_file = chat.history_file
        
        # Manually write test data
        with open(history_file, 'w') as f:
            json.dump(history_data, f)
        
        # Reload recent_proxies
        chat.recent_proxies = chat._load_recent_proxies(history_file)
        assert len(chat.recent_proxies) == 2
        assert "socks5://127.0.0.1:1080" in chat.recent_proxies
        assert "http://proxy.example.com:8080" in chat.recent_proxies
        
        # Add a new proxy
        chat._add_to_recent_proxies(history_file, "socks5://localhost:9050")
        assert chat.recent_proxies[0] == "socks5://localhost:9050"
        assert len(chat.recent_proxies) == 3  # But limited to 10
        
        # Verify history file contains both roots and proxies
        with open(history_file, 'r') as f:
            saved_data = json.load(f)
        assert "recent_root_dirs" in saved_data
        assert "recent_proxies" in saved_data
        assert saved_data["recent_proxies"][0] == "socks5://localhost:9050"
        
        print("✓ Proxy history loading/saving test passed")
        
    finally:
        if 'TEST_KEY' in os.environ:
            del os.environ['TEST_KEY']
        shutil.rmtree(temp_dir, ignore_errors=True)

def test_proxy_command_parsing():
    """Test that proxy command arguments are parsed correctly."""
    # This is a simple test that the command handler recognizes /proxy
    # We'll test by importing CommandHandler and checking handle_command
    from command_handler import CommandHandler
    import config
    
    # Mock dependencies
    class MockLLMClient:
        def __init__(self):
            self.current_model = None
            self.proxy_wrapper = None
        
        def update_proxy(self, proxy_wrapper):
            return True
    
    class MockSessionLogger:
        pass
    
    class MockInputHandler:
        pass
    
    class MockChatApp:
        def __init__(self):
            self.recent_proxies = []
            self.FREE_CHAT_MODE = "FREE_CHAT_MODE"
        
        def set_proxy(self, proxy_url):
            return True
    
    chat_app = MockChatApp()
    handler = CommandHandler(
        llm_client=MockLLMClient(),
        session_logger=MockSessionLogger(),
        input_handler=MockInputHandler(),
        chat_app=chat_app
    )
    
    # Test that /proxy command is recognized (returns False = don't quit)
    result = handler.handle_command("/proxy")
    assert result is False
    
    print("✓ Proxy command parsing test passed")

if __name__ == "__main__":
    test_proxy_history()
    test_proxy_command_parsing()
    print("\nAll proxy tests passed!")