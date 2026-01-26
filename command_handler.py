"""Command handling for LLM Terminal Chat"""
import os
from pathlib import Path
from ui import UI
import config

class CommandHandler:
    def __init__(self, llm_client, session_logger, input_handler, chat_app):
        self.llm_client = llm_client
        self.session_logger = session_logger
        self.input_handler = input_handler
        self.chat_app = chat_app

    def handle_command(self, command):
        """Handle user commands starting with '/'"""
        command = command.strip()
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ['/help', '/?']:
            self._handle_help(args)
        elif cmd == '/clear':
            self._handle_clear()
        elif cmd == '/bye':
            return True  # Signal to quit
        elif cmd == '/save':
            self._handle_save()
        elif cmd == '/model':
            self._handle_model(args)
        elif cmd == '/reload':
            self._handle_reload()
        elif cmd == '/files':
            self.handle_files_command()
        elif cmd == '/rootdir':
            self._handle_rootdir(args)
        else:
            print(f"Unknown command: {cmd}. Type /help for available commands.")
        
        return False

    def _handle_help(self, args):
        """Show help for commands"""
        if args:
            cmd = args[0]
            if cmd in config.COMMANDS:
                print(f"{cmd}: {config.COMMANDS[cmd]}")
            else:
                print(f"No help available for '{cmd}'")
        else:
            print("Available commands:")
            for cmd, desc in config.COMMANDS.items():
                print(f"  {cmd:<15} - {desc}")
            print("\nPress Ctrl+Space to open file context menu")
            print("Use Alt+Enter to send message, Enter for new line")

    def _handle_clear(self):
        """Clear conversation history"""
        self.llm_client.clear_conversation()
        print("Conversation history cleared.")

    def _handle_save(self):
        """Manually save current session"""
        if self.llm_client.conversation_history:
            self.session_logger.save_session(self.llm_client.conversation_history)
            log_path = self.session_logger.get_session_path()
            print(f"Session saved to: {log_path}")
        else:
            print("No conversation to save.")

    def _handle_model(self, args):
        """Switch or show current model"""
        if args:
            new_model = args[0]
            self.llm_client.switch_model(new_model)
        else:
            current = self.llm_client.get_current_model()
            print(f"Current model: {current}")

    def _handle_reload(self):
        """Reload a previous conversation"""
        sessions = self.session_logger.list_available_sessions()
        if not sessions:
            print("No previous conversations found for this project root.")
            return
        
        # Format session names for display
        def format_session(path):
            filename = os.path.basename(path)
            # Remove the .toml.zip extension and session_ prefix
            name = filename.replace('session_', '').replace('.toml.zip', '')
            # Format as YYYY-MM-DD HH:MM:SS
            try:
                date_part = name[:8]
                time_part = name[8:14]
                return f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
            except:
                return name
        
        try:
            selected_path = UI.interactive_selection(
                prompt_title="Available conversations:",
                prompt_message="Enter a number to select:",
                no_items_message="No conversations available",
                items=sessions,
                item_formatter=format_session,
                allow_new=False
            )
            
            if selected_path:
                session_data = self.session_logger.load_session(selected_path)
                if session_data:
                    # Load the conversation history
                    self.llm_client.load_conversation(session_data.get("conversation_history", []))
                    print(f"Loaded conversation from {format_session(selected_path)}")
                    print(f"Contains {len(session_data.get('conversation_history', []))} messages")
                else:
                    print("Failed to load conversation.")
        except (KeyboardInterrupt, EOFError):
            print("\nReload cancelled.")

    def handle_files_command(self):
        """Handle Ctrl+Space file context menu"""
        from menu import FileMenuApp
        try:
            app = FileMenuApp(
                editable_files=self.chat_app.editable_files,
                readable_files=self.chat_app.readable_files,
                root_dir=self.chat_app.root_dir
            )
            app.run()
            # Update the files lists after menu closes
            self.chat_app.editable_files = app.editable_files
            self.chat_app.readable_files = app.readable_files
        except Exception as e:
            print(f"Error opening file menu: {e}")

    def _handle_rootdir(self, args):
        """Show or set project root directory"""
        if args:
            new_root = Path(args[0]).expanduser().resolve()
            if new_root.is_dir():
                self.chat_app.root_dir = str(new_root)
                print(f"Project root set to: {self.chat_app.root_dir}")
            else:
                print(f"Error: {new_root} is not a valid directory")
        else:
            print(f"Current project root: {self.chat_app.root_dir}")
