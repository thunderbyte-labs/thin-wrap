#!/usr/bin/env python3
"""Simple test of proxy command without network."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Mock the proxy_wrapper module before importing chat
import unittest.mock as mock

# Create a mock proxy wrapper that passes validation
mock_wrapper = mock.MagicMock()
mock_wrapper.proxy_connection.return_value.__enter__.return_value = mock_wrapper
mock_wrapper.proxy_connection.return_value.__exit__.return_value = None
mock_wrapper.get_connection_info.return_value = {'proxy_url': 'socks5://127.0.0.1:1080'}

# Mock create_proxy_wrapper to return our mock
with mock.patch('proxy_wrapper.create_proxy_wrapper', return_value=mock_wrapper):
    with mock.patch('proxy_wrapper.validate_proxy_url', return_value=None):
        # Now import chat
        from chat import LLMChat
        import config
        import json
        import tempfile
        import shutil
        
        # Create temp config
        temp_dir = tempfile.mkdtemp()
        config_dir = os.path.join(temp_dir, "config")
        os.makedirs(config_dir, exist_ok=True)
        
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
        
        os.environ['TEST_KEY'] = 'dummy'
        
        try:
            # Create LLMChat with a root dir to avoid interactive prompt
            root_dir = temp_dir
            chat = LLMChat(root_dir=root_dir, config_path=config_path)
            
            # Test set_proxy with a URL
            print("Testing set_proxy with valid URL...")
            result = chat.set_proxy("socks5://127.0.0.1:1080")
            assert result is True, "set_proxy should succeed with mocked wrapper"
            print("✓ set_proxy succeeded")
            
            # Test set_proxy with 'off'
            print("Testing set_proxy with 'off'...")
            result = chat.set_proxy('off')
            assert result is True, "set_proxy should succeed disabling proxy"
            print("✓ proxy disabled")
            
            # Test recent_proxies history
            print("Testing proxy history...")
            assert len(chat.recent_proxies) == 1
            assert chat.recent_proxies[0] == "socks5://127.0.0.1:1080"
            print("✓ proxy history updated")
            
            print("\nAll simple proxy tests passed!")
            
        finally:
            if 'TEST_KEY' in os.environ:
                del os.environ['TEST_KEY']
            shutil.rmtree(temp_dir, ignore_errors=True)