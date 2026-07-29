"""Unified LLM client wrapper (using only httpx)

This class provides a clean abstraction over raw HTTP calls while preserving:
- Full proxy support via ProxyWrapper
- OpenAI-compatible /chat/completions endpoints
- Detailed error reporting
- Session persistence through session_logger
"""

import os
from typing import Optional
import config
import text_utils
import logging
from ui import UI
from proxy_wrapper import ProxyWrapper
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)


class LLMClient:
    """Main client for all LLM interactions in Thin Wrap."""

    def __init__(
        self, proxy_wrapper: Optional[ProxyWrapper] = None, session_logger=None
    ) -> None:
        self.conversation_history: list[dict[str, str]] = []
        self.proxy_wrapper: Optional[ProxyWrapper] = proxy_wrapper
        self._http_client: Optional[httpx.Client] = None
        self._proxy_context = None  # for proxy_connection() context manager
        self.current_model = None
        self.current_model_config = None
        self.session_logger = session_logger
        self.api_key: Optional[str] = None
        self.api_base_url: Optional[str] = None

    # ===================================================================
    # PUBLIC API
    # ===================================================================

    def setup_api_key(self, model: str):
        """Initialize connection for the selected model (called on startup and model switch)."""
        if model is None:
            raise TypeError("model cannot be None")

        self.current_model = model
        models = config.get_models()
        model_config = models[model]
        self.current_model_config = model_config

        self.api_key = os.getenv(model_config["api_key"]) or model_config["api_key"]
        self.api_base_url = model_config["api_base_url"].rstrip("/")

        if not self.api_key:
            print(f"{model_config['api_key']} not found.")
            self.api_key = input(f"Please enter your {model} API key: ").strip()
            if not self.api_key:
                raise ValueError("No API key provided")

        if self.proxy_wrapper:
            logger.debug(f"Setting up {model} API connection through proxy...")
            try:
                self._initialize_client_with_proxy()
                logger.info("Proxy-enabled API connection established successfully!")
            except Exception as e:
                logger.error(f"Proxy configuration failed: {e}")
                print("Attempting direct connection without proxy...")
                # Fully disconnect proxy: clean up context + clear wrapper
                self._cleanup_proxy_context()
                self.proxy_wrapper = None
                self._initialize_http_client()  # direct mode (no proxy)
                try:
                    self._test_connection()
                    print("✓ Direct connection established successfully!")
                except Exception as e2:
                    print(
                        f"\n{UI.colorize('Warning:', 'BRIGHT_YELLOW')} "
                        f"Direct connection also failed: {e2}"
                    )
                    print("You can continue and try sending messages - errors may occur.")
        else:
            self._initialize_http_client()
            try:
                self._test_connection()
            except Exception as e:
                print(
                    f"\n{UI.colorize('Warning:', 'BRIGHT_YELLOW')} "
                    f"API connection test failed: {e}"
                )
                print("You can continue and try sending messages - errors may occur.")

    def choose_model(self):
        """Display interactive model selection menu and return selected model key."""
        models = config.get_models()
        print("Available LLM Models:")

        for i, (model_key, details) in enumerate(models.items(), 1):
            endpoint = details.get("api_base_url", "")
            endpoint = (
                endpoint.removeprefix("https://").removeprefix("http://").rstrip("/")
            )
            print(f"{i}. {UI.colorize(model_key, 'BRIGHT_GREEN')}@{endpoint}")

        while True:
            try:
                choice = input(f"\nChoose model (1-{len(models)}): ").strip()
            except KeyboardInterrupt:
                if self.current_model is not None:
                    print()
                    print(
                        f"{UI.colorize('Model selection cancelled.', 'BRIGHT_YELLOW')}"
                    )
                    print(
                        f"{UI.colorize('Keeping current model:', 'BRIGHT_CYAN')} {self.current_model}"
                    )
                    return None
                else:
                    raise

            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(models):
                    return list(models.keys())[choice_idx]
            except ValueError:
                pass
            print(f"Please enter a number between 1 and {len(models)}")

    def switch_model(self, new_model: str) -> bool:
        """Switch to a different model while preserving conversation history."""
        models = config.get_models()
        if new_model not in models:
            print(
                f"Error: Unknown model '{new_model}'. Available: {', '.join(models.keys())}"
            )
            return False

        if new_model == self.current_model:
            print(f"Already using {new_model}")
            return True

        print(f"Switching from {self.current_model} to {new_model}...")

        try:
            self.setup_api_key(new_model)
            print(
                f"✓ Successfully switched to {new_model}. Conversation history preserved."
            )
            return True
        except Exception as e:
            print(f"✗ Failed to switch to {new_model}: {e}")
            return False

    def update_proxy(self, proxy_wrapper: ProxyWrapper) -> bool:
        """Update proxy configuration at runtime."""
        self.proxy_wrapper = proxy_wrapper
        if self.current_model:
            try:
                self.setup_api_key(self.current_model)
                return True
            except Exception as e:
                print(f"✗ Failed to update proxy: {e}")
                return False
        return True

    # ===================================================================
    # PROXY & HTTP CLIENT MANAGEMENT
    # ===================================================================

    def _initialize_client_with_proxy(self):
        """Initialize proxy context manager and HTTP client inside it (exact original behaviour)."""
        try:
            self._proxy_context = self.proxy_wrapper.proxy_connection()
            self._proxy_context.__enter__()
            self._initialize_http_client()
            self._test_connection()
        except Exception as e:
            self._cleanup_proxy_context()
            raise

    def _initialize_http_client(self):
        """Create (or recreate) the httpx client."""
        if self._http_client:
            self._cleanup_http_client()

        client_kwargs = {"timeout": 300.0}

        if self.proxy_wrapper:
            try:
                if (
                    hasattr(self.proxy_wrapper, "proxy_config")
                    and self.proxy_wrapper.proxy_config is not None
                ):
                    proxy_url = self.proxy_wrapper.proxy_config.get_proxy_url()
                    if proxy_url:
                        transport = httpx.HTTPTransport(proxy=proxy_url)
                        client_kwargs["transport"] = transport
                        logger.debug(f"Using proxy: {proxy_url}")
            except Exception as e:
                logger.warning(f"Proxy configuration incomplete: {e}")

        self._http_client = httpx.Client(**client_kwargs)

    def _cleanup_http_client(self):
        """Safely close the httpx client."""
        if self._http_client:
            try:
                self._http_client.close()
            except Exception as e:
                logger.debug(f"Error closing HTTP client: {e}")
            finally:
                self._http_client = None

    def _cleanup_proxy_context(self):
        """Clean up both HTTP client and proxy context manager."""
        self._cleanup_http_client()

        if self._proxy_context:
            try:
                self._proxy_context.__exit__(None, None, None)
            except Exception as e:
                logger.debug(f"Error exiting proxy context: {e}")
            finally:
                self._proxy_context = None

    # ===================================================================
    # REQUEST HELPERS
    # ===================================================================

    def _get_endpoint_and_input_key(self) -> tuple[str, str]:
        """Declarative normalization for endpoint and payload key."""
        model_config = self.current_model_config
        endpoint = model_config.get("endpoint", "/chat/completions")
        input_key = model_config.get("input_key", "messages")
        return endpoint.rstrip("/"), input_key

    def _get_request_url_and_headers(self) -> tuple[str, dict]:
        """Now supports per-model endpoint (OpenCode-style)."""
        endpoint, _ = self._get_endpoint_and_input_key()
        base = self.api_base_url
        url = f"{base}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        return url, headers

    def _build_request_params(self, messages: list, max_tokens: int = 0):
        """Build request payload. For DeepSeek, full messages list is used → prefix caching benefits from stable early turns."""
        model_config = self.current_model_config
        _, input_key = self._get_endpoint_and_input_key()

        request_params = {
            "model": model_config.get("model", self.current_model),
        }

        if input_key == "input":  # currently, this path is only used by qwen
            last_user_content = next(
                (m["content"] for m in reversed(messages) if m.get("role") == "user"),
                messages[-1]["content"] if messages else "",
            )
            request_params["input"] = last_user_content
        else:
            request_params["messages"] = messages

        if max_tokens > 0:
            request_params["max_tokens"] = max_tokens

        extra_arguments = model_config.get("extra_arguments", {})
        if extra_arguments and isinstance(extra_arguments, dict):
            request_params.update(extra_arguments)

        return request_params

    def _extract_response_content(self, raw_response: dict) -> str:
        """Extract final assistant text from both OpenAI /chat/completions and DashScope /responses formats."""
        # === DashScope Responses API (/responses) ===
        if "output" in raw_response and isinstance(raw_response.get("output"), list):
            # Walk backwards to find the final "message" item (after all reasoning/tool calls)
            for item in reversed(raw_response["output"]):
                if item.get("type") == "message" and isinstance(
                    item.get("content"), list
                ):
                    texts = [
                        c.get("text", "")
                        for c in item["content"]
                        if c.get("type") == "output_text"
                    ]
                    return "\n".join(texts).strip()

        # === Standard OpenAI /chat/completions fallback ===
        try:
            return raw_response["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            # Fallback for debugging
            return (
                f"[RAW RESPONSE] {str(raw_response)[:500]}..."
                if len(str(raw_response)) > 500
                else str(raw_response)
            )

    def _test_connection(self):
        """Validate API key with a minimal request + detailed error reporting."""
        payload = self._build_request_params(
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=10,
        )

        url, headers = self._get_request_url_and_headers()

        try:
            response = self._http_client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            # Use same extractor so test passes for both endpoint types
            content = self._extract_response_content(data)
            logger.info(
                f"{self.current_model} API key validated successfully! Sample reply: {content[:60]}..."
            )
        except httpx.HTTPStatusError as e:
            print(f"\n❌ API Error {e.response.status_code} from {self.current_model}")
            print(f"URL: {url}")
            try:
                error_detail = e.response.json()
                print("Error details returned by the provider:")
                import json

                print(json.dumps(error_detail, indent=2))
            except Exception:
                print("Raw error body:")
                print(e.response.text)
            raise
        except Exception as e:
            print(f"Unexpected error during connection test: {e}")
            raise

    # ===================================================================
    # MESSAGE SENDING & CONVERSATION MANAGEMENT
    # ===================================================================

    def _send_message_via_httpx(self) -> tuple[str, Optional[dict]]:
        """Send to LLM and return (text, usage_dict)."""
        print("⏳ Sending request to LLM client... (Press Ctrl+C to interrupt)")

        messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.conversation_history
        ]

        payload = self._build_request_params(messages=messages)
        url, headers = self._get_request_url_and_headers()

        response = self._http_client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Extract usage if present (DeepSeek, OpenAI, OpenRouter, DashScope, Gemini, etc.)
        usage = data.get("usage")

        # Extract response text
        text = self._extract_response_content(data)

        return text, usage

    def send_message(self, message: str) -> tuple[str, Optional[dict]]:
        """
        Send a message and return (response_text, usage_dict).
        usage_dict contient les vrais tokens de l'API (prompt_tokens, completion_tokens, etc.)
        """
        try:
            # Append user message
            self.conversation_history.append(
                {
                    "role": "user",
                    "content": message,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)

            # Get response + usage from API
            response_text, usage = self._send_message_via_httpx()

            # Append assistant response
            self.conversation_history.append(
                {
                    "role": "assistant",
                    "content": response_text,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)

            return response_text, usage

        except KeyboardInterrupt:
            print(
                f"\n{UI.colorize('Request interrupted by user (Ctrl+C)', 'BRIGHT_YELLOW')}"
            )
            if (
                self.conversation_history
                and self.conversation_history[-1]["role"] == "user"
            ):
                self.conversation_history.pop()
                if self.session_logger:
                    self.session_logger.save_session(self.conversation_history)
            return "", None

        except Exception as e:
            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)
            return f"Error communicating with {self.current_model}: {e}", None

    def clear_conversation(self):
        """Clear conversation history and save empty session."""
        self.conversation_history = []
        if self.session_logger:
            self.session_logger.save_session(self.conversation_history)

    def load_conversation(self, conversation_history: list):
        """Load a saved conversation history."""
        self.conversation_history = conversation_history
        if self.session_logger:
            self.session_logger.save_session(self.conversation_history)

    def get_current_model(self) -> Optional[str]:
        """Return currently active model name."""
        return self.current_model

    def __del__(self):
        """Ensure resources are cleaned up when object is destroyed."""
        self._cleanup_proxy_context()

