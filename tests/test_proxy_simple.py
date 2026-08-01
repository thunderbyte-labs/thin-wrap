#!/usr/bin/env python3
"""Offline tests for proxy command functionality (adapted from test_proxy_simple.py).

These tests verify that the set_proxy method works correctly at the LLMChat level,
using mocked proxy_wrapper and validate_proxy_url to avoid network calls.
They complement the other proxy test files by testing the actual integration of
set_proxy with LLMChat, rather than command parsing or suggestion logic.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def mock_proxy_wrapper():
    """Fixture that patches proxy_wrapper.create_proxy_wrapper and validate_proxy_url."""
    mock_wrapper = mock.MagicMock()
    mock_wrapper.test_connection.return_value = True
    mock_wrapper.get_connection_info.return_value = {
        "proxy_url": "socks5://127.0.0.1:1080"
    }

    with (
        mock.patch("proxy_wrapper.create_proxy_wrapper", return_value=mock_wrapper),
        mock.patch("proxy_wrapper.validate_proxy_url", return_value=None),
    ):
        yield


@pytest.fixture
def temp_config():
    """Create a temporary config directory and config file with a valid model entry."""
    temp_dir = tempfile.mkdtemp()
    config_dir = os.path.join(temp_dir, "config")
    os.makedirs(config_dir, exist_ok=True)

    config_data = {
        "models": {
            "test-model": {
                "model": "test-model",
                "api_key": "TEST_KEY",
                "api_base_url": "https://example.com/v1",
            }
        }
    }
    config_path = os.path.join(config_dir, "config.json")
    with open(config_path, "w") as f:
        json.dump(config_data, f)

    os.environ["TEST_KEY"] = "dummy"

    yield temp_dir, config_path

    del os.environ["TEST_KEY"]
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_set_proxy_with_valid_url(mock_proxy_wrapper, temp_config):
    """Test set_proxy with a valid SOCKS5 URL."""
    from thin_wrap import LLMChat

    root_dir, config_path = temp_config
    chat = LLMChat(root_dir=root_dir, config_path=config_path)

    # Clear existing proxy history to ensure a clean test state
    chat.recent_proxies.clear()

    result = chat.set_proxy("socks5://127.0.0.1:1080")
    assert result is True, "set_proxy should succeed with mocked wrapper"

    # New proxy is prepended to the list, so it should be at index 0
    assert chat.recent_proxies[0] == "socks5://127.0.0.1:1080"
    assert len(chat.recent_proxies) == 1


def test_set_proxy_with_off(mock_proxy_wrapper, temp_config):
    """Test set_proxy with 'off' disables proxy."""
    from thin_wrap import LLMChat

    root_dir, config_path = temp_config
    chat = LLMChat(root_dir=root_dir, config_path=config_path)

    result = chat.set_proxy("off")
    assert result is True, "set_proxy should succeed disabling proxy"


def test_proxy_history_updated(mock_proxy_wrapper, temp_config):
    """Test that recent_proxies history is properly updated."""
    from thin_wrap import LLMChat

    root_dir, config_path = temp_config
    chat = LLMChat(root_dir=root_dir, config_path=config_path)

    # Clear any preloaded history to isolate the test
    chat.recent_proxies.clear()

    chat.set_proxy("socks5://127.0.0.1:1080")

    # The proxy we just set should be the only entry, at the front
    assert len(chat.recent_proxies) == 1
    assert chat.recent_proxies[0] == "socks5://127.0.0.1:1080"
