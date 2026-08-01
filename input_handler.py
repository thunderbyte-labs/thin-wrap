import os
import shutil

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, WordCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.filters import has_focus
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import Float, FloatContainer, HSplit, Layout, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.styles import Style

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
        if text_before.strip() and text_before.strip()[0] == "/":
            # Get the current word being typed
            word_before = document.get_word_before_cursor(WORD=True)

            # If we're completing a command (word starts with '/')
            if word_before and word_before.startswith("/"):
                # Delegate to WordCompleter for command completion
                yield from self.word_completer.get_completions(document, complete_event)
        # Don't trigger for other text (non-command input)


class InputHandler:
    def __init__(self):
        self.terminal_width = self._get_terminal_width()
        # Get commands from config
        command_list = list(config.COMMANDS.keys())
        self.command_completer = CommandCompleter(command_list)
        # Message history for navigation
        self.history = []  # Messages envoyés
        self.draft_stack = []  # Messages temporaires non envoyés (brouillons)
        self.history_index = -1  # -1 means not currently navigating

    def _get_terminal_width(self):
        """Get terminal width with cross-platform fallbacks"""
        try:
            return shutil.get_terminal_size().columns
        except OSError:
            try:
                return int(os.environ.get("COLUMNS", config.TERMINAL_WIDTH_FALLBACK))
            except (ValueError, TypeError):
                return config.TERMINAL_WIDTH_FALLBACK

    def add_to_history(self, text: str):
        """Add a message to history and clear temporary drafts."""
        if text.strip():
            self.history.append(text)
            # Clear draft stack when a message is sent
            self.draft_stack = []
            self.history_index = -1
            # Keep history size limited
            if len(self.history) > 100:
                self.history.pop(0)

    def clear_history(self):
        """Clear message history."""
        self.history = []
        self.draft_stack = []
        self.history_index = -1

    def load_history(self, messages: list[str]):
        """Load messages into history."""
        self.history = [msg for msg in messages if msg.strip()]
        self.draft_stack = []
        self.history_index = -1

    def clear_draft_stack(self):
        """Clear temporary draft stack."""
        self.draft_stack = []
        self.history_index = -1

    def load_from_conversation_history(self, conversation_history: list[dict]):
        """Load user messages from conversation history."""
        user_messages = []
        for msg in conversation_history:
            if msg.get("role") == "user" and msg.get("content"):
                user_messages.append(msg["content"])
        self.load_history(user_messages)

    def _get_combined_item(self, index: int) -> str:
        """Get item from combined navigation (draft_stack + history).
        draft_stack[0] is most recent draft, history[-1] is most recent sent message.
        """
        if index < len(self.draft_stack):
            return self.draft_stack[index]
        else:
            hist_index = index - len(self.draft_stack)
            # history[-1] is most recent, history[0] is oldest
            # So we need to access from the end: history[-(hist_index + 1)]
            return self.history[-(hist_index + 1)]

    def _get_combined_count(self) -> int:
        """Get total count of items in combined navigation."""
        return len(self.draft_stack) + len(self.history)

    def get_input_with_editing(self, default: str = "", context_provider=None):
        """Get input with editing capabilities, replicating original behavior.

        *context_provider* (optional) is called on every render to return the
        files-context block (ANSI string) rendered in a window directly below
        the input, so it stays one line under the message being typed.
        """
        kb = KeyBindings()

        @kb.add("enter")
        def insert_newline(event: KeyPressEvent) -> None:
            """Insert newline on Enter."""
            event.current_buffer.insert_text("\n")

        @kb.add("escape", "enter")
        def submit_input(event: KeyPressEvent) -> None:
            """Submit on Alt+Enter."""
            event.app.exit(result=event.current_buffer.text)

        @kb.add("c-b")
        def handle_ctrl_b(event: KeyPressEvent) -> None:
            """Handle Ctrl+B to launch menu."""
            event.app.exit(result=("Ctrl+B", event.current_buffer.text))

        @kb.add("pageup")
        def navigate_history_up(event: KeyPressEvent) -> None:
            """Navigate to previous message in combined history (drafts + sent)."""
            total_items = self._get_combined_count()
            current_text = event.current_buffer.text

            if self.history_index == -1:
                # At bottom - not currently navigating
                if current_text.strip():
                    # Save current text as temporary draft before navigating
                    self.draft_stack.insert(
                        0, current_text
                    )  # Add to beginning (most recent)
                    # Keep draft stack size limited
                    if len(self.draft_stack) > 20:
                        self.draft_stack.pop()

                # Start navigation from the most recent item if we have any
                if total_items > 0:
                    self.history_index = 0
                    event.current_buffer.text = self._get_combined_item(
                        self.history_index
                    )
                else:
                    # No items to navigate to
                    return
            else:
                # Already navigating - move to older item
                if self.history_index < total_items - 1:
                    self.history_index += 1
                    event.current_buffer.text = self._get_combined_item(
                        self.history_index
                    )
                # else: already at oldest item, stay there

            event.current_buffer.cursor_position = len(event.current_buffer.text)

        @kb.add("pagedown")
        def navigate_history_down(event: KeyPressEvent) -> None:
            """Navigate to next message or save current text as temporary draft."""
            current_text = event.current_buffer.text

            if self.history_index == -1:
                # Not currently navigating
                if current_text.strip():
                    # Save current text as temporary draft and clear buffer
                    self.draft_stack.insert(
                        0, current_text
                    )  # Add to beginning (most recent)
                    event.current_buffer.text = ""
                    # Keep draft stack size limited
                    if len(self.draft_stack) > 20:
                        self.draft_stack.pop()
                # If buffer is empty and there are items, don't start navigation automatically
                # User can use Page Up to start navigation
            else:
                # Currently navigating - move to newer item (toward bottom/current)
                if self.history_index > 0:
                    self.history_index -= 1
                    event.current_buffer.text = self._get_combined_item(
                        self.history_index
                    )
                else:
                    # At newest item (index 0) - exit navigation
                    self.history_index = -1
                    event.current_buffer.text = ""

            event.current_buffer.cursor_position = len(event.current_buffer.text)

        style = Style.from_dict(
            {
                "": "bold #ffd700",
            }
        )

        # The "Message" separator is rendered by the app before this prompt, so
        # the input uses an empty message. The files context is rendered below
        # the input (one line gap) so it follows the message being typed.
        buffer = Buffer(
            multiline=True,
            completer=self.command_completer,
            complete_while_typing=True,
        )

        def context_text():
            if context_provider:
                return ANSI(context_provider())
            return ""

        input_window = Window(
            BufferControl(buffer=buffer),
            wrap_lines=True,
            dont_extend_height=True,
        )
        context_window = Window(
            FormattedTextControl(context_text),
            wrap_lines=False,
            dont_extend_height=True,
        )
        layout = Layout(
            FloatContainer(
                HSplit([input_window, context_window]),
                floats=[
                    Float(
                        xcursor=True,
                        ycursor=True,
                        transparent=True,
                        content=CompletionsMenu(
                            max_height=16,
                            scroll_offset=1,
                            extra_filter=has_focus(buffer),
                        ),
                    ),
                ],
            )
        )

        app = Application(
            layout=layout,
            key_bindings=kb,
            style=style,
            mouse_support=False,
            erase_when_done=True,
        )
        app.layout.focus(input_window)
        buffer.text = default
        buffer.cursor_position = len(default)

        try:
            return app.run()
        except (KeyboardInterrupt, EOFError):
            return None
