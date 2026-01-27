
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.document import Document
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import FormattedText
from ui import UI
import shutil
import os
import config

class InputHandler:
    def __init__(self):
        self.terminal_width = self._get_terminal_width()

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
            mouse_support=False
        )

        try:
            return session.prompt(default=default)
        except (KeyboardInterrupt, EOFError):
            return None
