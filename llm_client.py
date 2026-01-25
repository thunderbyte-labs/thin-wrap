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
    def __init__(self, proxy_wrapper: Optional[ProxyWrapper] = None, session_logger = None) -> None:
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
        api_key = os.getenv(model_config["api_key_env"])

        if not api_key:
            print(f"{model_config['api_key_env']} not found in environment variables.")
            api_key = input(f"Please enter your {model} API key: ").strip()
            if not api_key:
                raise ValueError("No API key provided")

        # Setup API connection
        if self.proxy_wrapper:
            logger.info(f"Setting up {model} API connection through proxy...")
            try:
                self._initialize_client_with_proxy(model, api_key, model_config)
                logger.info("Proxy-enabled API connection established successfully!")
            except Exception as e:
                logger.error(f"Proxy configuration failed: {e}")
                print("Attempting direct connection without proxy...")
                try:
                    self._initialize_client_direct(model, api_key, model_config)
                    print("✓ Direct connection established successfully!")
                except Exception as e2:
                    print(f"Direct connection also failed: {e2}")
                    raise ConnectionError("Failed to establish API connection")
        else:
            self._initialize_client_direct(model, api_key, model_config)

    def choose_model(self):
        """Let user choose which LLM model to use"""
        print("Available LLM Models:")
        for i, key in enumerate(config.SUPPORTED_MODELS, 1):
            print(f"  {i}. {key}")

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
            return True
        except Exception as e:
            print(f"✗ Failed to switch to {new_model}: {e}")
            return False

    def _initialize_client_with_proxy(self, model, api_key, model_config):
        """Initialize client with proxy configuration"""
        try:
            self._proxy_context = self.proxy_wrapper.proxy_connection()
            self._proxy_context.__enter__()
            proxy_info = self.proxy_wrapper.get_connection_info()
            logger.debug(f"Proxy info: {proxy_info}")
            self._setup_openai_client(api_key, proxy_info, model)
            self._test_connection()
        except Exception as e:
            self._cleanup_proxy_context()
            raise

    def _initialize_client_direct(self, model, api_key, model_config):
        """Initialize client without proxy"""
        try:
            client_kwargs = {"api_key": api_key, "timeout": 300.0}
            if "api_base" in model_config:
                client_kwargs["base_url"] = model_config["api_base"]
            self.openai_client = OpenAI(**client_kwargs)
            self._test_connection()
            print(f"{model} API key validated successfully!\n")
        except Exception as e:
            print(f"Error: Invalid API key or connection failed: {e}")
            raise

    def _setup_openai_client(self, api_key, proxy_info, model):
        """Setup OpenAI client with proxy using OpenAI v1.0+ syntax"""
        try:
            client_kwargs = {"api_key": api_key, "timeout": 300.0}
            model_config = config.SUPPORTED_MODELS[model]
            if "api_base" in model_config:
                client_kwargs["base_url"] = model_config["api_base"]

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
            logger.error(f"Failed to setup DeepSeek client with proxy: {e}")
            client_kwargs = {"api_key": api_key, "timeout": 300.0}
            if "api_base" in config.SUPPORTED_MODELS[model]:
                client_kwargs["base_url"] = config.SUPPORTED_MODELS[model]["api_base"]
            self.openai_client = OpenAI(**client_kwargs)

    def _test_connection(self):
        """Test API connection with a simple request"""
        self.openai_client.chat.completions.create(
            model=self.current_model,
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}],
        )

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
            self.conversation_history.append({
                "role": "user", 
                "content": message,
                "timestamp": datetime.now().isoformat()
            })
            
            # Save session with user message before API call
            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)
            
            # Get response from LLM
            response = self._send_message_to_openai_client()
            response = text_utils.clean_text(response)
            
            # Add assistant response to history and save again
            self.conversation_history.append({
                "role": "assistant", 
                "content": response,
                "timestamp": datetime.now().isoformat()
            })
            
            # Save session with assistant response
            if self.session_logger:
                self.session_logger.save_session(self.conversation_history)
                
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

    def get_current_model(self):
        """Get current model information"""
        return self.current_model

    def __del__(self):
        """Cleanup when object is destroyed"""
        self._cleanup_proxy_context()
