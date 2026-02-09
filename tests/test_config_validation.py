#!/usr/bin/env python3
"""Test configuration validation and loading."""
import sys
import os
import tempfile
import json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config

def test_config_validation():
    """Test that config validation works correctly."""
    # Valid config with proxy fields
    valid_config = {
        "models": {
            "model-with-proxy": {
                "api_key": "TEST_KEY",
                "api_base_url": "https://example.com/v1",
                "proxy": True
            },
            "model-without-proxy": {
                "api_key": "TEST_KEY2",
                "api_base_url": "https://example.com/v2",
                "proxy": False
            },
            "model-no-proxy-field": {
                "api_key": "TEST_KEY3",
                "api_base_url": "https://example.com/v3"
            }
        },
        "backup": {
            "timestamp_format": "%Y%m%d%H%M%S",
            "extra_string": "test",
            "backup_old_file": True
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(valid_config, f)
        config_path = f.name
    
    try:
        # Set config path and load
        config.set_config_path(config_path)
        models = config.get_models()
        
        # Verify all models loaded
        assert len(models) == 3
        assert "model-with-proxy" in models
        assert "model-without-proxy" in models
        assert "model-no-proxy-field" in models
        
        # Verify proxy field values
        assert models["model-with-proxy"]["proxy"] == True
        assert models["model-without-proxy"]["proxy"] == False
        assert models["model-no-proxy-field"]["proxy"] == False  # default
        
        # Verify backup config
        backup_conf = config.backup()
        assert backup_conf["timestamp_format"] == "%Y%m%d%H%M%S"
        assert backup_conf["extra_string"] == "test"
        assert backup_conf["backup_old_file"] == True
        
        print("✓ Config validation with proxy fields works")
        
    finally:
        os.unlink(config_path)

def test_config_missing_required_fields():
    """Test that config validation catches missing required fields."""
    # Missing api_key
    invalid_config = {
        "models": {
            "bad-model": {
                "api_base_url": "https://example.com/v1"
                # Missing api_key
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
            assert False, "Should have raised ValueError for missing api_key"
        except ValueError as e:
            if "missing 'api_key' field" in str(e):
                print("✓ Correctly catches missing api_key field")
            else:
                raise
    finally:
        os.unlink(config_path)

def test_config_invalid_proxy_type():
    """Test that config validation rejects non-boolean proxy field."""
    invalid_config = {
        "models": {
            "bad-model": {
                "api_key": "KEY",
                "api_base_url": "https://example.com/v1",
                "proxy": "yes"  # string instead of bool
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
                print("✓ Correctly rejects non-boolean proxy field")
            else:
                raise
    finally:
        os.unlink(config_path)

def test_config_backup_defaults():
    """Test that backup section gets proper defaults."""
    config_without_backup = {
        "models": {
            "test-model": {
                "api_key": "TEST_KEY",
                "api_base_url": "https://example.com/v1"
            }
        }
        # No backup section
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_without_backup, f)
        config_path = f.name
    
    try:
        config.set_config_path(config_path)
        backup_conf = config.backup()
        
        # Should have defaults
        assert backup_conf["timestamp_format"] == "%Y%m%d%H%M%S"
        assert backup_conf["extra_string"] == "thin-wrap"
        assert backup_conf["backup_old_file"] == True
        
        print("✓ Backup defaults applied correctly")
    finally:
        os.unlink(config_path)

def test_config_reloading():
    """Test that config is reloaded each time get_models() is called."""
    initial_config = {
        "models": {
            "model1": {
                "api_key": "KEY1",
                "api_base_url": "https://example.com/v1"
            }
        },
        "backup": {}
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(initial_config, f)
        config_path = f.name
    
    try:
        config.set_config_path(config_path)
        
        # First load
        models1 = config.get_models()
        assert len(models1) == 1
        
        # Modify config file
        updated_config = {
            "models": {
                "model1": {
                    "api_key": "KEY1",
                    "api_base_url": "https://example.com/v1"
                },
                "model2": {
                    "api_key": "KEY2",
                    "api_base_url": "https://example.com/v2"
                }
            },
            "backup": {}
        }
        
        with open(config_path, 'w') as f:
            json.dump(updated_config, f)
        
        # Second load should pick up changes
        models2 = config.get_models()
        assert len(models2) == 2
        assert "model2" in models2
        
        print("✓ Config reloading works correctly")
    finally:
        os.unlink(config_path)

if __name__ == "__main__":
    test_config_validation()
    test_config_missing_required_fields()
    test_config_invalid_proxy_type()
    test_config_backup_defaults()
    test_config_reloading()
    print("\n✅ All config validation tests passed!")