"""Regression tests for vLLM / Qwen reasoning_content handling."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llm_client import LLMClient


def _client(model_config=None):
    client = LLMClient()
    client.current_model = "test"
    client.current_model_config = model_config or {
        "model": "test",
        "api_base_url": "https://api.example.com",
        "input_key": "messages",
    }
    client.api_base_url = "https://api.example.com"
    client.api_key = "test-key"
    return client


def test_extract_response_content_openai_plain():
    client = _client()
    text = client._extract_response_content(
        {"choices": [{"message": {"content": "  hello  "}}]}
    )
    assert text == "hello"


def test_extract_response_content_null_content_uses_reasoning():
    client = _client()
    text = client._extract_response_content(
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "reasoning_content": " step by step ",
                    }
                }
            ]
        }
    )
    assert text == "step by step"


def test_extract_response_content_empty_content_uses_reasoning():
    client = _client()
    text = client._extract_response_content(
        {"choices": [{"message": {"content": "", "reasoning_content": "think"}}]}
    )
    assert text == "think"


def test_extract_stream_chunk_reasoning_then_content():
    client = _client()
    delta, usage = client._extract_stream_chunk(
        {"choices": [{"delta": {"reasoning_content": "think ", "content": "ans"}}]}
    )
    assert delta == "think ans"
    assert usage is None


def test_extract_stream_chunk_content_only_unchanged():
    client = _client()
    delta, usage = client._extract_stream_chunk(
        {"choices": [{"delta": {"content": "Hello"}}]}
    )
    assert delta == "Hello"
    assert usage is None


def test_build_request_params_enable_thinking_false():
    client = _client(
        model_config={
            "model": "local-qwen",
            "extra_arguments": {"chat_template_kwargs": {"enable_thinking": False}},
        }
    )
    params = client._build_request_params(messages=[{"role": "user", "content": "hi"}])
    assert params["chat_template_kwargs"]["enable_thinking"] is False
