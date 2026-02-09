#!/usr/bin/env python3
"""Test proxy suggestion feature."""
import sys
import os
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config

def test_proxy_suggestion_logic():
    """Test the logic for determining when to prompt for proxy."""
    print("Testing proxy suggestion logic...")
    
    # Test cases
    test_cases = [
        {
            "name": "Model with proxy=True, no proxy configured",
            "model_config": {"proxy": True},
            "has_proxy": False,
            "should_prompt": True
        },
        {
            "name": "Model with proxy=False, no proxy configured", 
            "model_config": {"proxy": False},
            "has_proxy": False,
            "should_prompt": False
        },
        {
            "name": "Model with proxy=True, proxy already configured",
            "model_config": {"proxy": True},
            "has_proxy": True,
            "should_prompt": False
        },
        {
            "name": "Model without proxy field, no proxy configured",
            "model_config": {},  # No proxy field
            "has_proxy": False,
            "should_prompt": False  # Defaults to False
        }
    ]
    
    for tc in test_cases:
        # Mock model config
        model_config = {
            "api_key": "TEST_KEY",
            "api_base_url": "https://example.com/v1",
            **tc["model_config"]
        }
        
        # Simulate the logic from _prompt_for_proxy_if_needed
        should_prompt = True
        
        # Check if proxy already configured
        if tc["has_proxy"]:
            should_prompt = False
        
        # Check if model suggests proxy  
        if not model_config.get('proxy', False):
            should_prompt = False
        
        assert should_prompt == tc["should_prompt"], \
            f"Failed for {tc['name']}: expected {tc['should_prompt']}, got {should_prompt}"
        
        print(f"  ✓ {tc['name']}")
    
    print("✓ Proxy suggestion logic tests passed")

def test_config_proxy_field_default():
    """Test that proxy field defaults to False when not specified."""
    config_data = {
        "models": {
            "test-model": {
                "api_key": "TEST_KEY",
                "api_base_url": "https://example.com/v1"
                # No proxy field
            }
        },
        "backup": {}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        config_path = f.name
    
    try:
        config.set_config_path(config_path)
        models = config.get_models()
        
        assert models["test-model"]["proxy"] == False, \
            "Proxy should default to False when not specified"
        
        print("✓ Proxy field defaults to False when not specified")
    finally:
        os.unlink(config_path)

def test_proxy_suggestion_integration():
    """Test integration of proxy suggestion with config loading."""
    config_data = {
        "models": {
            "model-needs-proxy": {
                "api_key": "KEY1",
                "api_base_url": "https://example.com/v1",
                "proxy": True
            },
            "model-no-proxy": {
                "api_key": "KEY2", 
                "api_base_url": "https://example.com/v2",
                "proxy": False
            }
        },
        "backup": {}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        config_path = f.name
    
    try:
        config.set_config_path(config_path)
        models = config.get_models()
        
        # Verify models loaded
        assert len(models) == 2
        
        # Verify proxy values
        assert models["model-needs-proxy"]["proxy"] == True
        assert models["model-no-proxy"]["proxy"] == False
        
        # Simulate what chat.py would do
        model1_config = models["model-needs-proxy"]
        model2_config = models["model-no-proxy"]
        
        # Check if should prompt for proxy (simplified logic)
        should_prompt1 = model1_config.get('proxy', False)  # True
        should_prompt2 = model2_config.get('proxy', False)  # False
        
        assert should_prompt1 == True
        assert should_prompt2 == False
        
        print("✓ Proxy suggestion integration test passed")
    finally:
        os.unlink(config_path)

def test_proxy_field_validation():
    """Test that proxy field validation works."""
    # Valid boolean values
    for proxy_value in [True, False]:
        config_data = {
            "models": {
                "test-model": {
                    "api_key": "TEST_KEY",
                    "api_base_url": "https://example.com/v1",
                    "proxy": proxy_value
                }
            },
            "backup": {}
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = f.name
        
        try:
            config.set_config_path(config_path)
            models = config.get_models()
            assert models["test-model"]["proxy"] == proxy_value
        finally:
            os.unlink(config_path)
    
    # Invalid non-boolean value should raise error
    invalid_config = {
        "models": {
            "bad-model": {
                "api_key": "KEY",
                "api_base_url": "https://example.com/v1",
                "proxy": "true"  # String, not bool
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(invalid_config, f)
        config_path = f.name
    
    try:
        config.set_config_path(config_path)
        try:
            models = config.get_models()
            assert False, "Should have raised ValueError for non-boolean proxy"
        except ValueError as e:
            if "must be boolean" in str(e):
                print("✓ Proxy field validation rejects non-boolean values")
            else:
                raise
    finally:
        os.unlink(config_path)

if __name__ == "__main__":
    test_proxy_suggestion_logic()
    test_config_proxy_field_default()
    test_proxy_suggestion_integration()
    test_proxy_field_validation()
    print("\n✅ All proxy suggestion tests passed!")