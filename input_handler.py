from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.document import Document
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.completion import Completer
from prompt_toolkit.completion import WordCompleter
import shutil
import os
import config

class CommandCompleter(Completer):
    """Completer for slash commands"""
    def __init__(self, commands):
        # Convert command list to WordCompleter for basic completion
        self.commands = commands
        self.word_completer = WordCompleter(commands, ignore_case=True, sentence=True)
    
    def get_completions(self, document: Document, complete_event):
        text_before = document.text_before_cursor
        
        # Only trigger if we're at the start of a line or after whitespace
        # and the text starts with '/'
        if text_before.strip() and text_before.strip()[0] == '/':
            # Get the current word being typed
            word_before = document.get_word_before_cursor(WORD=True)
            
            # If we're completing a command (word starts with '/')
            if word_before and word_before.startswith('/'):
                # Delegate to WordCompleter for command completion
                for completion in self.word_completer.get_completions(document, complete_event):
                    yield completion
        # Don't trigger for other text (non-command input)

class InputHandler:
    def __init__(self):
        self.terminal_width = self._get_terminal_width()
        # Get commands from config
        command_list = list(config.COMMANDS.keys())
        self.command_completer = CommandCompleter(command_list)

    def _get_terminal_width(self):
        """Get terminal width with cross-platform fallbacks"""
        try:
            return shutil.get_terminal_size().columns
        except OSError:
            try:
                return int(os.environ.get("COLUMNS", config.TERMINAL_WIDTH_FALLBACK))
            except (ValueError, TypeError):
                return config.TERMINAL_WIDTH_FALLBACK

    def get_input_with_editing(self, default: str = ""):
        """Get input with editing capabilities, replicating original behavior."""
        kb = KeyBindings()

        @kb.add('enter')
        def insert_newline(event: KeyPressEvent) -> None:
            """Insert newline on Enter."""
            event.current_buffer.insert_text('\n')

        @kb.add('escape', 'enter')
        def submit_input(event: KeyPressEvent) -> None:
            """Submit on Alt+Enter."""
            event.current_buffer.validate_and_handle()

        @kb.add('c-b')
        def handle_ctrl_b(event: KeyPressEvent) -> None:
            """Handle Ctrl+B to launch menu."""
            event.app.exit(result=("Ctrl+B", event.current_buffer.text))

        prompt_message = FormattedText([
            ('bold fg:ansidefault', "Alt+Enter to send. Ctrl+B for file context management:\n"),
        ])

        style = Style.from_dict({
            '': 'bold #ffd700',
        })

        session = PromptSession(
            multiline=True,
            key_bindings=kb,
            message=prompt_message,
            style=style,
            mouse_support=False,
            completer=self.command_completer,
            complete_while_typing=True
        )

        try:
            return session.prompt(default=default)
        except (KeyboardInterrupt, EOFError):
            return None

