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
            print(f"\nPress {UI.colorize('Ctrl+B', 'BRIGHT_YELLOW')} to open file context menu.")
            print(f"Use {UI.colorize('Alt+Enter', 'BRIGHT_YELLOW')} to send message, {UI.colorize('Enter', 'BRIGHT_YELLOW')} for new line.")
            print(f"{UI.colorize('Page Up/Down', 'BRIGHT_YELLOW')} for message history (sent messages and temporary drafts).")

    def _handle_clear(self):
        """Clear conversation history"""
        self.llm_client.clear_conversation()
        self.input_handler.clear_history()
        print("Conversation history cleared.")

    def _handle_model(self, args):
        """Switch or show current model - reloads config.json on each call"""
        # get_models() already re-reads the config file, so we don't need to reload explicitly
        print(f"Current model: {self.llm_client.get_current_model()}")
        if not args:
            # No arguments provided - show interactive model selection menu
            print("Interactive model selection:")
            selected_model = self.llm_client.interactive_model_selection()
            if selected_model:
                success = self.llm_client.switch_model(selected_model)
                if success:
                    # Clear conversation and input history when switching models
                    self.llm_client.clear_conversation()
                    self.input_handler.clear_history()
                    print(f"{UI.colorize('Model switched and history cleared.', 'BRIGHT_GREEN')}")
            elif selected_model is None:
                # User cancelled with Ctrl+C while already having a model
                print(f"{UI.colorize('Returning to conversation...', 'BRIGHT_CYAN')}")
        else:
            # Arguments provided - use the old behavior
            new_model = args[0]
            success = self.llm_client.switch_model(new_model)
            if success:
                # Clear conversation and input history when switching models
                self.llm_client.clear_conversation()
                self.input_handler.clear_history()
                print(f"{UI.colorize('Model switched and history cleared.', 'BRIGHT_GREEN')}")

    def _handle_reload(self):
        """Reload a previous conversation from the current project root"""
        sessions = self.session_logger.list_available_sessions()
        if not sessions:
            if self.chat_app.root_dir is not None:
                print(f"{UI.colorize('No previous conversations found for this project root.', 'BRIGHT_YELLOW')}")
            else:
                print(f"{UI.colorize('No previous conversations found in free chat mode.', 'BRIGHT_YELLOW')}")
            root_display = self.chat_app.root_dir if self.chat_app.root_dir is not None else "Free chat mode"
            print(f"Project root: {UI.colorize(root_display, 'BRIGHT_CYAN')}")
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
        
        root_display = self.chat_app.root_dir if self.chat_app.root_dir is not None else "Free chat mode"
        print(f"Project root: {UI.colorize(root_display, 'BRIGHT_CYAN')}")
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
                    conversation_history = session_data.get("conversation_history", [])
                    self.llm_client.load_conversation(conversation_history)
                    # Load user messages into input history
                    self.input_handler.load_from_conversation_history(conversation_history)
                    print(f"Loaded conversation from {format_session(selected_path)}")
                    print(f"Contains {len(conversation_history)} messages")
                    print(f"Loaded {len(self.input_handler.history)} user messages into history")
                else:
                    print("Failed to load conversation.")
        except (KeyboardInterrupt, EOFError):
            print("\nReload cancelled.")

    def handle_files_command(self):
        """Handle Ctrl+B file context menu"""
        # In free chat mode, prompt for root directory selection instead
        if hasattr(self.chat_app, 'free_chat_mode') and self.chat_app.free_chat_mode:
            print("Free chat mode active. Selecting a root directory will enable file context.")
            self._handle_rootdir([])
            return
        
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
        """Show or set project root directory using interactive selection with free chat option"""
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
            # Interactive selection mode with free chat option
            from prompt_toolkit import PromptSession
            from prompt_toolkit.completion import PathCompleter
            
            completer = PathCompleter(expanduser=True)
            session = PromptSession(completer=completer)
            
            free_chat_label = "No root directory - Free chatting without file context"
            
            while True:
                print(f"{UI.colorize('Previous project roots:', 'BRIGHT_CYAN')}")
                print(f"  0. {free_chat_label}")
                for i, item in enumerate(self.chat_app.recent_roots, 1):
                    print(f"  {i}. {item}")
                print("Enter a number to select, or type a new path (Tab for completion, ~ for home):")
                
                try:
                    user_input = session.prompt("> ").strip()
                except (KeyboardInterrupt, EOFError):
                    print("\nSelection cancelled.")
                    return
                
                if not user_input:
                    print(f"{UI.colorize('Error:', 'RED')} Empty input - please try again.")
                    continue
                
                # Numeric selection
                if user_input.isdigit():
                    idx = int(user_input)
                    if idx == 0:
                        print(f"{UI.colorize('Selected:', 'BRIGHT_CYAN')} {free_chat_label}")
                        self.chat_app.set_root_dir(self.chat_app.FREE_CHAT_MODE)
                        return
                    elif 1 <= idx <= len(self.chat_app.recent_roots):
                        chosen = self.chat_app.recent_roots[idx - 1]
                        print(f"{UI.colorize('Selected:', 'BRIGHT_CYAN')} {chosen}")
                        self.chat_app.set_root_dir(chosen)
                        return
                    else:
                        print(f"{UI.colorize('Error:', 'RED')} Number out of range.")
                        continue
                
                # Manual path entry
                try:
                    new_item = Path(user_input).expanduser().resolve(strict=False)
                    if new_item.is_dir():
                        resolved_str = str(new_item)
                        print(f"{UI.colorize('Using:', 'BRIGHT_CYAN')} {resolved_str}")
                        self.chat_app.set_root_dir(resolved_str)
                        return
                    else:
                        print(f"{UI.colorize('Error:', 'RED')} Not a valid directory: {user_input}")
                except Exception as e:
                    print(f"{UI.colorize('Error:', 'RED')} Invalid input: {e}")


