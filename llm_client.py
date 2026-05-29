"""Unified LLM client wrapper (using only httpx)"""

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
    def __init__(
        self, proxy_wrapper: Optional[ProxyWrapper] = None, session_logger=None
    ) -> None:
        self.conversation_history: list[dict[str, str]] = []
        self.proxy_wrapper: Optional[ProxyWrapper] = proxy_wrapper
        self._http_client: Optional[httpx.Client] = None
        self.current_model = None
        self.current_model_config = None
        self.session_logger = session_logger
        self.api_key: Optional[str] = None
        self.api_base_url: Optional[str] = None

    def setup_api_key(self, model):
        """Get API key for specified model or let user choose"""
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

        self._initialize_http_client()

        if self.proxy_wrapper:
            logger.debug(f"Setting up {model} API connection through proxy...")
            try:
                self._test_connection()
                logger.info("Proxy-enabled API connection established successfully!")
            except Exception as e:
                logger.error(f"Proxy configuration failed: {e}")
                print("Attempting direct connection without proxy...")
                self._cleanup_http_client()
                self._initialize_http_client()  # re-init without proxy
                try:
                    self._test_connection()
                    print("✓ Direct connection established successfully!")
                except Exception as e2:
                    print(f"✗ Direct connection also failed: {e2}")
                    raise ConnectionError("Failed to establish API connection")
        else:
            self._test_connection()

    def _initialize_http_client(self):
        """Create or recreate the httpx client (with or without proxy)"""
        if self._http_client:
            self._cleanup_http_client()

        client_kwargs = {"timeout": 300.0}

        if self.proxy_wrapper:
            proxy_url = self.proxy_wrapper.proxy_config.get_proxy_url()
            if proxy_url:
                transport = httpx.HTTPTransport(proxy=proxy_url)
                client_kwargs["transport"] = transport
                logger.debug(f"Using proxy: {proxy_url}")

        self._http_client = httpx.Client(**client_kwargs)

    def _cleanup_http_client(self):
        """Close the httpx client"""
        if self._http_client:
            try:
                self._http_client.close()
            except Exception as e:
                logger.debug(f"Error closing HTTP client: {e}")
            finally:
                self._http_client = None

    def _send_message_via_httpx(self):
        """Send message using raw httpx POST to /chat/completions"""
        print("⏳ Sending request to LLM client... (Press Ctrl+C to interrupt)")

        messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.conversation_history
        ]

        payload = self._build_request_params(messages=messages)

        response = self._http_client.post(
            f"{self.api_base_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()

        return data["choices"][0]["message"]["content"]

    def choose_model(self):
        """Display interactive model selection menu (model@full.endpoint format)"""
        models = config.get_models()
        print("Available LLM Models:")

        for i, (model_key, details) in enumerate(models.items(), 1):
            endpoint = details.get("api_base_url", "")
            endpoint = (
                endpoint.removeprefix("https://").removeprefix("http://").rstrip("/")
            )
            print(f"{i}. {UI.colorize(model_key,'BRIGHT_GREEN')}@{endpoint}")

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

    def switch_model(self, new_model):
        """Switch to a different LLM model/model"""
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

    def update_proxy(self, proxy_wrapper):
        """Update proxy configuration."""
        self.proxy_wrapper = proxy_wrapper
        if self.current_model:
            try:
                self.setup_api_key(self.current_model)
                return True
            except Exception as e:
                print(f"✗ Failed to update proxy: {e}")
                return False
        return True

    def _build_request_params(self, messages, max_tokens=0):
        """Build request parameters for /chat/completions (standard OpenAI-compatible format)"""
        model_config = self.current_model_config
        extra_arguments = model_config.get("extra_arguments", {})

        request_params = {
            "model": model_config.get("model", self.current_model),
            "messages": messages,
        }

        if max_tokens > 0:
            request_params["max_tokens"] = max_tokens

        if extra_arguments and isinstance(extra_arguments, dict):
            request_params.update(extra_arguments)

        return request_params

    def _test_connection(self):
        """Test API connection with a simple request using httpx"""
        payload = self._build_request_params(
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=10,
        )

        response = self._http_client.post(
            f"{self.api_base_url}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        logger.info(f"{self.current_model} API key validated successfully!")

    def send_message(self, message):
        """Send processed input to LLM with automatic session saving before and after"""
        try:
            self.conversation_history.append(
                {
                    "role": "user",
                    "content": message,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)

            response = self._send_message_via_httpx()
            response = text_utils.clean_text(response)

            self.conversation_history.append(
                {
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)

            return response

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
            return ""

        except Exception as e:
            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)
            return f"Error communicating with {self.current_model}: {e}"

    def clear_conversation(self):
        """Clear conversation history and save empty session"""
        self.conversation_history = []
        if self.session_logger:
            self.session_logger.save_session(self.conversation_history)

    def load_conversation(self, conversation_history):
        """Load a conversation history into the client"""
        self.conversation_history = conversation_history
        if self.session_logger:
            self.session_logger.save_session(self.conversation_history)

    def get_current_model(self):
        """Get current model information"""
        return self.current_model

    def __del__(self):
        """Cleanup when object is destroyed"""
        self._cleanup_http_client()
