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

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, proxy_wrapper: Optional[ProxyWrapper] = None, session_logger=None) -> None:
        self.openai_client: Optional[OpenAI] = None
        self.conversation_history: list[dict[str, str]] = []
        self.proxy_wrapper: Optional[ProxyWrapper] = proxy_wrapper
        self._proxy_context = None
        self._http_client = None
        self.current_model = None
        self.session_logger = session_logger

    def setup_api_key(self, model):
        """Get API key for specified model or let user choose"""
        if model is None:
            raise TypeError("model cannot be None")

        self.current_model = model
        model_config = config.SUPPORTED_MODELS[model]
        api_key = os.getenv(model_config["api_key"]) or model_config["api_key"]
        api_base_url = model_config["api_base_url"]

        if not api_key:
            print(f"{model_config['api_key']} not found.")
            api_key = input(f"Please enter your {model} API key: ").strip()
            if not api_key:
                raise ValueError("No API key provided")

        # Setup API connection
        if self.proxy_wrapper:
            logger.info(f"Setting up {model} API connection through proxy...")
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
                    print(f"Direct connection also failed: {e2}")
                    raise ConnectionError("Failed to establish API connection")
        else:
            self._initialize_client_direct(api_key, api_base_url)

    def choose_model(self):
        """Let user choose which LLM model to use"""
        # Reload models configuration to pick up any changes
        try:
            config.load_models_config()
            logger.debug(f"Reloaded {len(config.SUPPORTED_MODELS)} models from configuration")
        except Exception as e:
            logger.warning(f"Failed to reload models configuration: {e}")
        
        return self.interactive_model_selection()

    def interactive_model_selection(self):
        """Display interactive model selection menu and return selected model"""
        print("Available LLM Models:")
        for i, (model, details) in enumerate(config.SUPPORTED_MODELS.items(), 1):
            endpoint = details.get('api_base_url')
            endpoint = endpoint.removeprefix("https://").removeprefix("http://").rstrip('/')
            print(f"{i}. {UI.colorize(model,'BRIGHT_GREEN')}@{endpoint}")
        while True:
            choice = input(f"Choose model (1-{len(config.SUPPORTED_MODELS)}): ").strip()
            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(config.SUPPORTED_MODELS):
                    return list(config.SUPPORTED_MODELS.keys())[choice_idx]
            except ValueError:
                pass
            print(f"Please enter a number between 1 and {len(config.SUPPORTED_MODELS)}")

    def switch_model(self, new_model):
        """Switch to a different LLM model/model"""
        # Reload models configuration to pick up any changes
        try:
            config.load_models_config()
            logger.debug(f"Reloaded {len(config.SUPPORTED_MODELS)} models from configuration")
        except Exception as e:
            logger.warning(f"Failed to reload models configuration: {e}")
        
        if new_model not in config.SUPPORTED_MODELS:
            print(f"Error: Unknown model '{new_model}'. Available: {', '.join(config.SUPPORTED_MODELS.keys())}")
            return False

        if new_model == self.current_model:
            print(f"Already using {new_model}")
            return True

        print(f"Switching from {self.current_model} to {new_model}...")

        try:
            self.setup_api_key(new_model)
            print(f"✓ Successfully switched to {new_model}. Conversation history preserved.")
            # Clear tokenizer cache when switching models
            text_utils.clear_tokenizer_cache()
            return True
        except Exception as e:
            print(f"✗ Failed to switch to {new_model}: {e}")
            return False

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
            client_kwargs = {"api_key": api_key, "base_url": api_base_url, "timeout": 300.0}
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
                    client_kwargs["http_client"] = httpx.Client(transport=proxy_transport)
                except ImportError:
                    logger.warning("httpx not available for proxy configuration")

            self.openai_client = OpenAI(**client_kwargs)
        except Exception as e:
            logger.error(f"Failed to setup client with proxy: {e}")
            self.openai_client = OpenAI(**client_kwargs)

    def _test_connection(self):
        """Test API connection with a simple request"""
        self.openai_client.chat.completions.create(
            model=self.current_model,
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}],
        )
        print(f"{self.current_model} API key validated successfully!\n")

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
                {"role": "user", "content": message, "timestamp": datetime.now().isoformat()}
            )

            # Save session with user message before API call
            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)

            # Get response from LLM
            response = self._send_message_to_openai_client()
            response = text_utils.clean_text(response)

            # Add assistant response to history and save again
            self.conversation_history.append(
                {"role": "assistant", "content": response, "timestamp": datetime.now().isoformat()}
            )

            # Save session with assistant response
            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)

            # Clear tokenizer cache after each successful response to prevent memory buildup
            text_utils.clear_tokenizer_cache()

            return response
        except KeyboardInterrupt:
            print(f"\n{UI.colorize('Request interrupted by user (Ctrl+C)', 'BRIGHT_YELLOW')}")
            # Request was interrupted - remove the user message that was interrupted
            if self.conversation_history and self.conversation_history[-1]["role"] == "user":
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
            # Clear tokenizer cache on error as well
            text_utils.clear_tokenizer_cache()
            return f"Error communicating with {self.current_model}: {e}"

    def _send_message_to_openai_client(self):
        """Send message to OpenAI API using OpenAI v1.0+ syntax"""
        print("⏳ Sending request to LLM client... (Press Ctrl+C to interrupt)")
        try:
            # Prepare messages without timestamps for API
            messages = [{"role": msg["role"], "content": msg["content"]} for msg in self.conversation_history]
            response = self.openai_client.chat.completions.create(
                model=self.current_model,
                messages=messages,
            )
            return response.choices[0].message.content
        except KeyboardInterrupt:
            # Let the interruption propagate to send_message for proper handling
            raise

    def clear_conversation(self):
        """Clear conversation history and save empty session"""
        self.conversation_history = []
        if self.session_logger:
            self.session_logger.save_session(self.conversation_history)
        # Clear tokenizer cache when clearing conversation
        text_utils.clear_tokenizer_cache()

    def load_conversation(self, conversation_history):
        """Load a conversation history into the client"""
        self.conversation_history = conversation_history
        # Save the loaded conversation to ensure it's persisted
        if self.session_logger:
            self.session_logger.save_session(self.conversation_history)
        # Clear tokenizer cache when loading a new conversation
        text_utils.clear_tokenizer_cache()

    def get_current_model(self):
        """Get current model information"""
        return self.current_model

    def __del__(self):
        """Cleanup when object is destroyed"""
        self._cleanup_proxy_context()
        # Clear tokenizer cache on destruction to prevent memory leaks
        try:
            text_utils.clear_tokenizer_cache()
        except Exception:
            pass  # Ignore errors during cleanup
