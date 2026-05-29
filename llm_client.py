"""Unified LLM client wrapper (using OpenAI library)"""

import os
from typing import Optional
from openai import OpenAI
import config
import text_utils
import logging
from ui import UI
from proxy_wrapper import ProxyWrapper
from datetime import datetime
import json
import httpx

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(
        self, proxy_wrapper: Optional[ProxyWrapper] = None, session_logger=None
    ) -> None:
        self.openai_client: Optional[OpenAI] = None
        self.conversation_history: list[dict[str, str]] = []
        self.proxy_wrapper: Optional[ProxyWrapper] = proxy_wrapper
        self._proxy_context = None
        self._http_client = None
        self.current_model = None
        self.current_model_config = None
        self.session_logger = session_logger

    def setup_api_key(self, model):
        """Get API key for specified model or let user choose"""
        if model is None:
            raise TypeError("model cannot be None")

        self.current_model = model
        models = config.get_models()
        model_config = models[model]
        self.current_model_config = model_config
        api_key = os.getenv(model_config["api_key"]) or model_config["api_key"]
        api_base_url = model_config["api_base_url"]

        if not api_key:
            print(f"{model_config['api_key']} not found.")
            api_key = input(f"Please enter your {model} API key: ").strip()
            if not api_key:
                raise ValueError("No API key provided")

        if self.proxy_wrapper:
            logger.debug(f"Setting up {model} API connection through proxy...")
            try:
                self._initialize_client_with_proxy(api_key, api_base_url)
                logger.info("Proxy-enabled API connection established successfully!")
            except Exception as e:
                logger.error(f"Proxy configuration failed: {e}")
                print("Attempting direct connection without proxy...")
                try:
                    self._initialize_client_direct(api_key, api_base_url)
                    print("✓ Direct connection established successfully!")
                except Exception as e2:
                    print(f"✗ Direct connection also failed: {e2}")
                    raise ConnectionError("Failed to establish API connection")
        else:
            self._initialize_client_direct(api_key, api_base_url)

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
        # Clean up existing proxy context
        self._cleanup_proxy_context()

        # Update proxy wrapper
        self.proxy_wrapper = proxy_wrapper

        # If we have a current model, reinitialize with new proxy
        if self.current_model:
            try:
                self.setup_api_key(self.current_model)
                return True
            except Exception as e:
                print(f"✗ Failed to update proxy: {e}")
                return False
        return True

    def _initialize_client_with_proxy(self, api_key, api_base_url):
        """Initialize client with proxy configuration"""
        try:
            self._proxy_context = self.proxy_wrapper.proxy_connection()
            self._proxy_context.__enter__()
            proxy_info = self.proxy_wrapper.get_connection_info()
            logger.debug(f"Proxy info: {proxy_info}")
            self._setup_openai_client_with_proxy(api_key, api_base_url)
            self._test_connection()
        except Exception as e:
            self._cleanup_proxy_context()
            raise

    def _initialize_client_direct(self, api_key, api_base_url):
        """Initialize client without proxy"""
        try:
            client_kwargs = {
                "api_key": api_key,
                "base_url": api_base_url,
                "timeout": 300.0,
            }
            self.openai_client = OpenAI(**client_kwargs)
            self._test_connection()
        except Exception as e:
            print(f"Error: Invalid API key or connection failed: {e}")
            raise

    def _setup_openai_client_with_proxy(self, api_key, api_base_url):
        """Setup OpenAI client with proxy using OpenAI v1.0+ syntax"""
        client_kwargs = {"api_key": api_key, "base_url": api_base_url, "timeout": 300.0}
        try:
            proxy_config = self.proxy_wrapper.proxy_config
            proxy_url = proxy_config.get_proxy_url()

            if proxy_url:
                try:
                    import httpx

                    proxy_transport = httpx.HTTPTransport(proxy=proxy_url)
                    client_kwargs["http_client"] = httpx.Client(
                        transport=proxy_transport
                    )
                except ImportError:
                    logger.warning("httpx not available for proxy configuration")

            self.openai_client = OpenAI(**client_kwargs)
        except Exception as e:
            logger.error(f"Failed to setup client with proxy: {e}")
            self.openai_client = OpenAI(**client_kwargs)

    def _build_request_params(self, messages, max_tokens=0):
        """Build request parameters.
        Supports both legacy list-style plugins and new dict-style plugins for complex APIs (Qwen Beijing).
        """
        model_config = self.current_model_config
        plugins = model_config.get("plugins", None)

        request_params = {
            "model": model_config.get("model", self.current_model),
            "messages": messages,
        }

        # Scalable dict-style plugins handling
        if plugins and isinstance(plugins, dict):
            for key, value in plugins.items():
                if key == "thinking":
                    request_params["enable_thinking"] = value
                elif key == "tools":
                    request_params["tools"] = [{"type": t} for t in value]
                else:
                    # Any other key (including search_options) is passed as top-level field
                    request_params[key] = value

        # Add max_tokens params
        if max_tokens > 0:
            request_params["max_tokens"] = max_tokens

        if plugins and isinstance(plugins, list):
            request_params["extra_body"] = {"plugins": plugins}

        return request_params

    def _test_connection(self):
        """Test API connection with a simple request"""
        plugins = self.current_model_config.get("plugins", [])

        if isinstance(plugins, dict):
            # Use /responses for dict-style plugins (Qwen Beijing)
            payload = {
                "model": self.current_model_config.get("model"),
                "input": "Hi",
                "enable_thinking": plugins.get("thinking", False),
            }
            # Merge any additional fields from plugins dict (search_options, etc.)
            for k, v in plugins.items():
                if k not in ["thinking", "tools"]:
                    payload[k] = v

            # Use httpx for reliable call (avoids SDK unpacking issues)
            api_key = (
                os.getenv(self.current_model_config["api_key"])
                or self.current_model_config["api_key"]
            )
            api_base_url = self.current_model_config["api_base_url"].rstrip("/")
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{api_base_url}/responses",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
            logger.info(f"{self.current_model} API key validated successfully!")
        else:
            # Normal OpenAI-compatible path
            request_params = self._build_request_params(
                messages=[{"role": "user", "content": "Hi"}], max_tokens=10
            )
            self.openai_client.chat.completions.create(**request_params)
            logger.info(f"{self.current_model} API key validated successfully!")

    def _cleanup_proxy_context(self):
        """Clean up proxy context and related resources"""
        if self._http_client:
            try:
                self._http_client.close()
                self._http_client = None
            except Exception as e:
                logger.debug(f"Error closing HTTP client: {e}")

        if self._proxy_context:
            try:
                self._proxy_context.__exit__(None, None, None)
            except Exception as e:
                logger.debug(f"Error exiting proxy context: {e}")
            finally:
                self._proxy_context = None

    def send_message(self, message):
        """Send processed input to LLM with automatic session saving before and after"""
        try:
            # Add user message to history and save immediately
            self.conversation_history.append(
                {
                    "role": "user",
                    "content": message,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # Save session with user message before API call
            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)

            # Get response from LLM
            response = self._send_message_to_openai_client()
            response = text_utils.clean_text(response)

            # Add assistant response to history and save again
            self.conversation_history.append(
                {
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # Save session with assistant response
            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)

            return response
        except KeyboardInterrupt:
            print(
                f"\n{UI.colorize('Request interrupted by user (Ctrl+C)', 'BRIGHT_YELLOW')}"
            )
            # Request was interrupted - remove the user message that was interrupted
            if (
                self.conversation_history
                and self.conversation_history[-1]["role"] == "user"
            ):
                self.conversation_history.pop()
                # Save the updated session without the interrupted message
                if self.session_logger:
                    self.session_logger.save_session(self.conversation_history)
            # Return empty string to indicate interruption was handled
            return ""
        except Exception as e:
            # Even on error, save the current state
            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)
            return f"Error communicating with {self.current_model}: {e}"

    def _send_message_to_openai_client(self):
        """Send message to LLM — uses /responses for dict-style plugins (Qwen Beijing)"""
        print("⏳ Sending request to LLM client... (Press Ctrl+C to interrupt)")
        try:
            messages = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in self.conversation_history
            ]
            plugins = self.current_model_config.get("plugins", {})
            if not isinstance(plugins, dict):
                # Normal OpenAI-compatible path
                request_params = self._build_request_params(messages=messages)
                response = self.openai_client.chat.completions.create(**request_params)
                return response.choices[0].message.content
            else:
                # === Qwen Beijing special path using /responses ===
                # Prepend a strong instruction to reliably trigger tool use
                user_input = messages[-1]["content"]

                payload = {
                    "model": self.current_model_config.get("model"),
                    "input": user_input,
                    "enable_thinking": plugins.get("thinking", False),
                }
                # Merge everything else from plugins dict (tools, search_options, etc.)
                for k, v in plugins.items():
                    if k not in ["thinking"]:
                        payload[k] = v

                api_key = (
                    os.getenv(self.current_model_config["api_key"])
                    or self.current_model_config["api_key"]
                )
                api_base_url = self.current_model_config["api_base_url"].rstrip("/")

                with httpx.Client(timeout=300.0) as client:
                    response = client.post(
                        f"{api_base_url}/responses",
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                    )
                    result = response.json()

                # ==================== FULL DEBUG PRINT ====================
                print("\n=== RAW DASHSCOPE RESPONSE (full) ===")
                print(json.dumps(result, indent=2))
                print("=== END OF RAW RESPONSE ===\n")

                print("=== OUTPUT ARRAY BREAKDOWN ===")
                if "output" in result and result["output"]:
                    for idx, item in enumerate(result["output"]):
                        print(f"Item {idx} → type: {item.get('type')}")
                        print(f"Item {idx} keys: {list(item.keys())}")
                        if "content" in item:
                            print(f"  → content blocks: {len(item.get('content', []))}")
                        if "summary" in item:
                            print(
                                f"  → summary entries: {len(item.get('summary', []))}"
                            )
                print("=== END OF OUTPUT BREAKDOWN ===\n")

                # Try to extract final answer
                if "output" in result and result["output"]:
                    for item in result["output"]:
                        if isinstance(item, dict) and "content" in item:
                            for block in item["content"]:
                                if (
                                    isinstance(block, dict)
                                    and block.get("type") == "output_text"
                                ):
                                    final_text = block.get("text", "")
                                    print(
                                        f"Extracted final text (output_text): {final_text[:300]}..."
                                    )
                                    return final_text
                        if isinstance(item, dict) and "summary" in item:
                            for s in item["summary"]:
                                if isinstance(s, dict) and "text" in s:
                                    print(
                                        f"Extracted from summary: {s['text'][:300]}..."
                                    )
                                    return s["text"]
                return str(result)  # fallback

        except KeyboardInterrupt:
            # Let the interruption propagate to send_message for proper handling
            raise
        except Exception as e:
            logger.error(f"Error in _send_message_to_openai_client: {e}")
            raise

    def clear_conversation(self):
        """Clear conversation history and save empty session"""
        self.conversation_history = []
        if self.session_logger:
            self.session_logger.save_session(self.conversation_history)

    def load_conversation(self, conversation_history):
        """Load a conversation history into the client"""
        self.conversation_history = conversation_history
        # Save the loaded conversation to ensure it's persisted
        if self.session_logger:
            self.session_logger.save_session(self.conversation_history)

    def get_current_model(self):
        """Get current model information"""
        return self.current_model

    def __del__(self):
        """Cleanup when object is destroyed"""
        self._cleanup_proxy_context()
