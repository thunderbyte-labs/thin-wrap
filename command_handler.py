
"""Command handling functionality"""
import os
import config
from menu import FileMenuApp

class CommandHandler:
    def __init__(self, llm_client, session_logger, input_handler, chat):
        self.llm_client = llm_client
        self.session_logger = session_logger
        self.input_handler = input_handler
        self.chat = chat

    def handle_command(self, user_input):
        """Handle special commands"""
        command_parts = user_input.strip().split(maxsplit=1)
        command = command_parts[0].lower()

        try:
            if command == '/bye':
                return self._handle_bye_command()
            elif command == '/clear':
                return self._handle_clear_command()
            elif command == '/save':
                return self._handle_save_command()
            elif command in ['/help', '/?']:
                return self._handle_help_command()
            elif command == '/model':
                parts = user_input.lower().strip().split()
                return self._handle_model_command(parts)
            elif command == '/files':
                return self.handle_files_command()
            elif command == '/rootdir':
                arg = command_parts[1] if len(command_parts) > 1 else None
                return self._handle_rootdir_command(arg)
            else:
                print(f"Unknown command: {user_input}")
                print("Type /help for available commands.\n")
                return False
        except KeyboardInterrupt:
            return True
        except Exception as e:
            print(f"Error handling command: {e}")
            return False

    def handle_files_command(self):
        """Handle /files command - launch the three-column menu"""
        FileMenuApp(
            editable_files=self.chat.editable_files,
            readable_files=self.chat.readable_files,
            root_dir=self.chat.root_dir
        ).run()
        return False

    def _handle_rootdir_command(self, new_path):
        """Handle /rootdir command - show current or set new project root"""
        if new_path is None:
            print(f"Current project root directory: {self.chat.root_dir}")
            return False

        expanded_path = os.path.expanduser(new_path.strip())
        abs_path = os.path.abspath(expanded_path)

        if not os.path.isdir(abs_path):
            print(f"Invalid directory (does not exist or not a directory): {abs_path}")
            return False

        old_root = self.chat.root_dir
        self.chat.root_dir = abs_path
        print(f"Project root directory changed from:\n  {old_root}\n→ {abs_path}")
        return False

    def _handle_model_command(self, command_parts):
        """Handle /model command to switch LLM models"""
        if len(command_parts) < 2:
            current_model = self.llm_client.get_current_model()
            print(f"Current model: {current_model}")
            print("Available models:")
            for key in config.SUPPORTED_MODELS:
                status = " (current)" if key == current_model else ""
                print(f"  {key}")
            print("Usage: /model <model>")
            return False
        
        new_model = command_parts[1].lower()
        
        if new_model not in config.SUPPORTED_MODELS:
            print(f"✗ Unknown model model: {new_model}")
            print("Available models:")
            for key in config.SUPPORTED_MODELS:
                print(f"  {key}")
            return False
            
        success = self.llm_client.switch_model(new_model)
        
        if success:
            print(f"✓ Switched to {new_model}")
        else:
            print(f"✗ Failed to switch to {new_model}")
            
        return False

    def _handle_bye_command(self):
        """Handle /bye command"""
        try:
            self.session_logger.save_session_log()
            return True
        except Exception as e:
            print(f"Error saving session log: {e}")
            return True

    def _handle_clear_command(self):
        """Handle /clear command"""
        try:
            self.llm_client.clear_conversation()
            print("Conversation history cleared.\n")
            return False
        except Exception as e:
            print(f"Error clearing conversation: {e}")
            return False

    def _handle_save_command(self):
        """Handle /save command"""
        try:
            log_path = self.session_logger.save_session_log()
            if log_path:
                print(f"Session log saved to: {log_path}")
            else:
                print("⚠️  No interactions to save yet.")
            return False
        except Exception as e:
            print(f"Error saving session log: {e}")
            return False

    def _handle_help_command(self):
        """Handle /help command"""
        try:
            print("Commands:")
            for command, description in config.COMMANDS.items():
                print(f"  {command:<15} {description}")
            print("\nAdditional commands:")
            print("  /files          Open file context menu (editable/readable/navigator)")
            print("  /rootdir [path] Show current project root or set a new one")
            return False
        except Exception as e:
            print(f"Error displaying help: {e}")
            return False
