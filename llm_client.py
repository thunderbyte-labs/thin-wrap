"""Unified LLM client wrapper (using only httpx)

This class provides a clean abstraction over raw HTTP calls while preserving:
- Full proxy support via ProxyWrapper
- OpenAI-compatible /chat/completions endpoints
- Detailed error reporting
- Session persistence through session_logger
"""

import contextlib
import logging
import os
from datetime import datetime

import httpx

import config
from proxy_wrapper import ProxyWrapper
from strings import t

logger = logging.getLogger(__name__)


class LLMClient:
    """Main client for all LLM interactions in Thin Wrap."""

    def __init__(
        self, proxy_wrapper: ProxyWrapper | None = None, session_logger=None
    ) -> None:
        self.conversation_history: list[dict[str, str]] = []
        self.proxy_wrapper: ProxyWrapper | None = proxy_wrapper
        self._http_client: httpx.Client | None = None
        self.current_model = None
        self.current_model_config = None
        self.session_logger = session_logger
        self.api_key: str | None = None
        self.api_base_url: str | None = None

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
            print(t("errors.api_key_not_found", env_key=model_config["api_key"]))
            self.api_key = input(t("prompts.api_key_prompt", model=model)).strip()
            if not self.api_key:
                raise ValueError("No API key provided")

        if self.proxy_wrapper:
            logger.debug(f"Setting up {model} API connection through proxy...")
            try:
                self._initialize_client_with_proxy()
                logger.info("Proxy-enabled API connection established successfully!")
            except Exception as e:
                logger.error(f"Proxy configuration failed: {e}")
                print(t("info.direct_without_proxy"))
                self._cleanup_http_client()
                self.proxy_wrapper = None
                self._initialize_http_client()  # direct mode (no proxy)
                try:
                    self._test_connection()
                    print(t("info.direct_connected"))
                except Exception as e2:
                    raise RuntimeError(
                        t("errors.api_connection_failed", model=self.current_model)
                    ) from e2
        else:
            self._initialize_http_client()
            try:
                self._test_connection()
            except Exception as e:
                raise RuntimeError(
                    t("errors.api_connection_failed", model=self.current_model)
                ) from e

    def choose_model(self):
        """Display interactive model selection menu and return selected model key."""
        models = config.get_models()
        print(t("menus.available_models"))

        for i, (model_key, details) in enumerate(models.items(), 1):
            endpoint = details.get("api_base_url", "")
            endpoint = (
                endpoint.removeprefix("https://").removeprefix("http://").rstrip("/")
            )
            print(f"{i}. {t('menus.model_entry', value=model_key)}@{endpoint}")

        while True:
            try:
                choice = input(t("prompts.model_choose", count=len(models))).strip()
            except KeyboardInterrupt:
                if self.current_model is not None:
                    print()
                    print(t("warnings.model_selection_cancelled"))
                    print(f"{t('info.keeping_current_model')} {self.current_model}")
                    return None
                else:
                    raise

            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(models):
                    return list(models.keys())[choice_idx]
            except ValueError:
                pass
            print(t("prompts.model_range_error", count=len(models)))

    def switch_model(self, new_model: str) -> bool:
        """Switch to a different model while preserving conversation history."""
        models = config.get_models()
        if new_model not in models:
            print(
                t(
                    "errors.unknown_model",
                    model=new_model,
                    available=", ".join(models.keys()),
                )
            )
            return False

        if new_model == self.current_model:
            print(t("info.already_using", model=new_model))
            return True

        print(t("info.switching_model", current=self.current_model, new=new_model))

        try:
            self.setup_api_key(new_model)
            print(t("info.switched_model", model=new_model))
            return True
        except Exception as e:
            print(t("errors.failed_to_switch_model", model=new_model, error=e))
            return False

    def update_proxy(self, proxy_wrapper: ProxyWrapper) -> bool:
        """Update proxy configuration at runtime."""
        self.proxy_wrapper = proxy_wrapper
        if self.current_model:
            try:
                self.setup_api_key(self.current_model)
                return True
            except Exception as e:
                print(t("errors.failed_to_update_proxy", error=e))
                return False
        return True

    # ===================================================================
    # PROXY & HTTP CLIENT MANAGEMENT
    # ===================================================================

    def _initialize_client_with_proxy(self):
        """Test proxy setup, then initialise HTTP client and API connection."""
        with contextlib.suppress(Exception):
            # test_connection warned; continue
            self.proxy_wrapper.test_connection()
        self._initialize_http_client()
        self._test_connection()

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
            print(
                t(
                    "errors.api_error",
                    status=e.response.status_code,
                    model=self.current_model,
                )
            )
            print(t("errors.api_error_url", url=url))
            try:
                error_detail = e.response.json()
                print(t("errors.api_error_details"))
                import json

                print(json.dumps(error_detail, indent=2))
            except Exception:
                print(t("errors.api_error_raw"))
                print(e.response.text)
            raise
        except Exception as e:
            print(t("errors.unexpected_connection_error", error=e))
            raise

    # ===================================================================
    # MESSAGE SENDING & CONVERSATION MANAGEMENT
    # ===================================================================

    def _send_message_via_httpx(self) -> tuple[str, dict | None]:
        """Send to LLM and return (text, usage_dict)."""
        print(t("info.request_sending"))

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

    def send_message(self, message: str) -> tuple[str, dict | None]:
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
            print(f"\n{t('info.request_interrupted')}")
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
            return (
                t("errors.error_communicating", model=self.current_model, error=e),
                None,
            )

    def clear_conversation(self):
        """Clear conversation history. The old session stays saved on disk."""
        self.conversation_history = []

    def load_conversation(self, conversation_history: list):
        """Load a saved conversation history."""
        self.conversation_history = conversation_history
        if self.session_logger:
            self.session_logger.save_session(self.conversation_history)

    def get_current_model(self) -> str | None:
        """Return currently active model name."""
        return self.current_model

    def __del__(self):
        """Ensure HTTP client is cleaned up when object is destroyed."""
        self._cleanup_http_client()
