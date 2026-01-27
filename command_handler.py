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
                print(f"{UI.colorize(cmd, 'BRIGHT_YELLOW')}: {config.COMMANDS[cmd]}")
            else:
                print(f"No help available for '{cmd}'")
        else:
            print("Available commands:")
            for cmd, desc in config.COMMANDS.items():
                print(f"  {UI.colorize(cmd, 'BRIGHT_YELLOW')} - {desc}")
            print(f"\nPress {UI.colorize('Ctrl+Space', 'BRIGHT_YELLOW')} to open file context menu.")
            print(f"Use {UI.colorize('Alt+Enter', 'BRIGHT_YELLOW')} to send message, {UI.colorize('Enter', 'BRIGHT_YELLOW')} for new line.")

    def _handle_clear(self):
        """Clear conversation history"""
        self.llm_client.clear_conversation()
        print("Conversation history cleared.")

    def _handle_model(self, args):
        """Switch or show current model"""
        if args:
            new_model = args[0]
            self.llm_client.switch_model(new_model)
        else:
            current = self.llm_client.get_current_model()
            print(f"Current model: {current}")

    def _handle_reload(self):
        """Reload a previous conversation from the current project root"""
        sessions = self.session_logger.list_available_sessions()
        if not sessions:
            print(f"{UI.colorize('No previous conversations found for this project root.', 'BRIGHT_YELLOW')}")
            print(f"Project root: {UI.colorize(self.chat_app.root_dir, 'BRIGHT_CYAN')}")
            print(f"Conversation directory: {UI.colorize(self.session_logger.conversation_dir, 'BRIGHT_CYAN')}")
            return
        
        # Format session names for display
        # Here we might wrap inside a light LLM call that would be able to read and give a 10 words summary of the conversation
        def format_session(path):
            filename = os.path.basename(path)
            # Remove the .toml.zip extension and session_ prefix
            name = filename.replace('session_', '').replace('.toml.zip', '')
            # Format as YYYY-MM-DD HH:MM:SS
            try:
                # Parse the timestamp format: YYYYMMDD_HHMMSS
                if '_' in name:
                    date_part, time_part = name.split('_', 1)
                    if len(date_part) == 8 and len(time_part) == 6:
                        # Format: YYYY-MM-DD HH:MM:SS
                        return f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"
            except:
                pass
            return name  # Return original if parsing fails
        
        print(f"Project root: {UI.colorize(self.chat_app.root_dir, 'BRIGHT_CYAN')}")
        print(f"Conversation directory: {UI.colorize(self.session_logger.conversation_dir, 'BRIGHT_CYAN')}")
        print()
        
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
        """Show or set project root directory using interactive selection"""
        if args:
            # Direct path argument provided
            new_root = Path(args[0]).expanduser().resolve()
            if new_root.is_dir():
                try:
                    self.chat_app.set_root_dir(str(new_root))
                except ValueError as e:
                    print(f"{UI.colorize('Error:', 'RED')} {e}")
            else:
                print(f"{UI.colorize('Error:', 'RED')} {new_root} is not a valid directory")
        else:
            # Interactive selection mode
            try:
                selected_root = UI.interactive_selection(
                    prompt_title="Previous project roots:",
                    prompt_message="Enter a number to select, or type a new path (Tab for completion, ~ for home):",
                    no_items_message="No previous roots found.",
                    items=self.chat_app.recent_roots,
                    item_formatter=lambda x: x,
                    allow_new=True,
                    new_item_validator=lambda p: p.is_dir(),
                    new_item_error="Not a valid directory"
                )
                
                if selected_root:
                    self.chat_app.set_root_dir(selected_root)
            except (KeyboardInterrupt, EOFError):
                print("\nRoot directory change cancelled.")


