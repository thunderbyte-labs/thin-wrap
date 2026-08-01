"""Tests for streamed LLM responses and live token-usage display."""

import io
import os
import sys
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx

from llm_client import LLMClient
from thin_wrap import LLMChat


def _client(model_config=None, api_base_url="https://api.example.com"):
    """Build an LLMClient wired to a fake config, ready for mocking HTTP."""
    client = LLMClient()
    client.conversation_history = [{"role": "user", "content": "hi"}]
    client.current_model = "test"
    client.current_model_config = model_config or {
        "model": "test",
        "api_base_url": api_base_url,
        "input_key": "messages",
    }
    client.api_base_url = api_base_url
    client.api_key = "test-key"
    return client


class _FakeStreamResponse:
    """Minimal stand-in for an httpx streaming response."""

    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self._lines)


def _mock_http_client(lines):
    """Return a MagicMock whose .stream() yields the given SSE lines."""
    http = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = _FakeStreamResponse(lines)
    cm.__exit__.return_value = False
    http.stream.return_value = cm
    return http


# =========================================================================
# _build_request_params stream flags
# =========================================================================


def test_build_request_params_stream_chat_completions():
    client = _client()
    params = client._build_request_params(
        messages=[{"role": "user", "content": "hi"}], stream=True
    )
    assert params["stream"] is True
    assert params["stream_options"] == {"include_usage": True}
    assert "input" not in params
    assert params["messages"]


def test_build_request_params_stream_responses_no_stream_options():
    client = _client(
        model_config={
            "model": "qwen-think",
            "input_key": "input",
            "endpoint": "/responses",
            "extra_arguments": {"enable_thinking": True},
        }
    )
    params = client._build_request_params(
        messages=[{"role": "user", "content": "hi"}], stream=True
    )
    assert params["stream"] is True
    assert "stream_options" not in params
    assert params["input"] == "hi"
    assert "messages" not in params
    assert params["enable_thinking"] is True


def test_build_request_params_non_streaming_unaffected():
    client = _client()
    params = client._build_request_params(messages=[{"role": "user", "content": "hi"}])
    assert "stream" not in params
    assert "stream_options" not in params


# =========================================================================
# _extract_stream_chunk
# =========================================================================


def test_extract_stream_chunk_chat_delta():
    client = _client()
    delta, usage = client._extract_stream_chunk(
        {"choices": [{"delta": {"content": "Hello"}}]}
    )
    assert delta == "Hello"
    assert usage is None


def test_extract_stream_chunk_chat_final_usage():
    client = _client()
    usage = {"prompt_tokens": 10, "completion_tokens": 5}
    delta, got = client._extract_stream_chunk({"choices": [], "usage": usage})
    assert delta == ""
    assert got == usage


def test_extract_stream_chunk_responses_delta():
    client = _client()
    delta, usage = client._extract_stream_chunk(
        {"type": "response.output_text.delta", "delta": "World"}
    )
    assert delta == "World"
    assert usage is None


def test_extract_stream_chunk_responses_completed_usage():
    client = _client()
    usage = {"input_tokens": 7, "output_tokens": 3}
    delta, got = client._extract_stream_chunk(
        {"type": "response.completed", "response": {"usage": usage}}
    )
    assert delta == ""
    assert got == usage


def test_extract_stream_chunk_reasoning_ignored():
    client = _client()
    delta, usage = client._extract_stream_chunk(
        {"type": "response.reasoning_summary_text.delta", "delta": "thinking..."}
    )
    assert delta == ""
    assert usage is None


def test_extract_stream_chunk_unknown_event_ignored():
    client = _client()
    delta, usage = client._extract_stream_chunk({"type": "response.created"})
    assert delta == ""
    assert usage is None


# =========================================================================
# _send_message_via_httpx (end-to-end streaming)
# =========================================================================


def test_send_message_via_httpx_streams_chat_completions():
    lines = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2}}',
        "data: [DONE]",
        "",
    ]
    client = _client()
    client._http_client = _mock_http_client(lines)

    seen = []
    text, usage = client._send_message_via_httpx(
        on_progress=lambda t_, u: seen.append((t_, u))
    )

    assert text == "Hello world"
    assert usage == {"prompt_tokens": 3, "completion_tokens": 2}
    assert seen and seen[-1][0] == "Hello world"


def test_send_message_via_httpx_streams_responses_api():
    lines = [
        'data: {"type":"response.output_text.delta","delta":"Bonjour"}',
        'data: {"type":"response.output_text.delta","delta":" !"}',
        'data: {"type":"response.reasoning_summary_text.delta","delta":"skip me"}',
        'data: {"type":"response.completed","response":{"usage":{"input_tokens":4,"output_tokens":2}}}',
        "",
    ]
    client = _client(
        model_config={
            "model": "qwen-think",
            "input_key": "input",
            "endpoint": "/responses",
        }
    )
    client._http_client = _mock_http_client(lines)

    text, usage = client._send_message_via_httpx()

    assert text == "Bonjour !"
    assert usage == {"input_tokens": 4, "output_tokens": 2}


def test_send_message_via_httpx_retries_without_stream_options():
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    error = httpx.HTTPStatusError(
        "400 Client Error",
        request=request,
        response=httpx.Response(400, request=request),
    )
    failing_cm = MagicMock()
    failing_cm.__enter__.side_effect = error
    failing_cm.__exit__.return_value = False
    ok_cm = MagicMock()
    ok_cm.__enter__.return_value = _FakeStreamResponse(
        ['data: {"choices":[{"delta":{"content":"ok"}}]}', "data: [DONE]", ""]
    )
    ok_cm.__exit__.return_value = False

    http = MagicMock()
    http.stream.side_effect = [failing_cm, ok_cm]

    client = _client()
    client._http_client = http

    text, usage = client._send_message_via_httpx()
    assert text == "ok"
    assert usage is None

    payloads = [call.kwargs["json"] for call in http.stream.call_args_list]
    assert len(payloads) == 2
    assert payloads[0]["stream_options"] == {"include_usage": True}
    assert "stream_options" not in payloads[1]


def test_send_message_via_httpx_shows_ttf(capsys):
    lines = [
        'data: {"choices":[{"delta":{"content":"Hi"}}]}',
        'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":1}}',
        "data: [DONE]",
        "",
    ]
    client = _client()
    client._http_client = _mock_http_client(lines)

    text, usage = client._send_message_via_httpx()

    out = capsys.readouterr().out
    assert "TTF :" in out
    assert "Thinking" in out
    assert text == "Hi"
    assert usage == {"prompt_tokens": 3, "completion_tokens": 1}


def test_send_message_via_httpx_tolerates_junk_lines():
    lines = [
        "event: response.created",
        ": comment",
        'data: {"choices":[{"delta":{"content":"ok"}}]}',
        "data: not-json",
        "data: [DONE]",
    ]
    client = _client()
    client._http_client = _mock_http_client(lines)

    text, usage = client._send_message_via_httpx()
    assert text == "ok"
    assert usage is None


# =========================================================================
# thin_wrap token display helpers
# =========================================================================


def _chat():
    return LLMChat.__new__(LLMChat)


def test_format_token_row_with_cache():
    chat = _chat()
    row = chat._format_token_row(100, 50, cached_tokens=25, duration_ms=1500)
    assert "100" in row and "50" in row
    assert "25 (25%)" in row
    assert "1.5" in row
    assert "33.3" in row  # 50 tokens / 1.5s


def test_format_token_row_empty_duration():
    chat = _chat()
    row = chat._format_token_row(100, 50, cached_tokens=0, duration_ms=None)
    assert "-" in row
    assert "100" in row


def test_token_usage_numbers_api_keys_both_formats():
    chat = _chat()
    i, o, c, source = chat._token_usage_numbers(
        "q",
        "r",
        {"prompt_tokens": 10, "completion_tokens": 5, "prompt_cache_hit_tokens": 4},
    )
    assert (i, o, c, source) == (10, 5, 4, "API")

    i, o, c, source = chat._token_usage_numbers(
        "q",
        "r",
        {
            "input_tokens": 7,
            "output_tokens": 3,
            "input_tokens_details": {"cached_tokens": 2},
        },
    )
    assert (i, o, c, source) == (7, 3, 2, "API")


def test_token_usage_numbers_falls_back_to_estimates():
    chat = _chat()
    i, o, c, source = chat._token_usage_numbers("query text", "some reply", None)
    assert source == "estimated"
    assert i > 0 and o > 0
    assert c == 0


# =========================================================================
# live table redraw must not drift upward (regression: off-by-one cursor-up)
# =========================================================================


class _FakeStreamingLLM:
    def __init__(self):
        self.response = "word number 0 word number 1 word number 2 word number 3"
        self.usage = {
            "prompt_tokens": 13,
            "completion_tokens": 38,
            "prompt_cache_hit_tokens": 5,
        }

    def get_current_model(self):
        return "test"

    def send_message(self, query, on_progress=None):
        acc = ""
        for i in range(4):
            acc += f"word number {i} "
            on_progress(acc, None)
            time.sleep(0.12)  # > throttle window so every chunk redraws
        return self.response, self.usage


def test_live_table_redraw_never_drifts_upward():
    from thin_wrap import LLMChat as _LLMChat_cls

    chat = _LLMChat_cls.__new__(_LLMChat_cls)
    chat.llm_client = _FakeStreamingLLM()
    chat.root_dir = None
    chat.readable_files = []
    chat.editable_files = []
    chat.free_chat_mode = True

    buf = io.StringIO()
    with (
        patch("thin_wrap.UI.render_markdown", side_effect=lambda text: None),
        patch("sys.stdout", buf),
    ):
        chat._send_message("raconte moi")

    out = buf.getvalue()
    # The block is len(lines)=5 rows; the cursor sits on the last row after a
    # draw, so redraws must back up 4 rows, never 5 (5 erases the line above).
    assert "\x1b[5A" not in out
    draws = out.count("\r\x1b[2KUsage")
    cursor_ups = out.count("\x1b[4A")
    assert draws >= 3, "expected several live redraws"
    assert cursor_ups == draws - 1, "one cursor-up per redraw, each exactly 4 rows"
