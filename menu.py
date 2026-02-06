import os
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DirectoryTree, ListView, ListItem, Static
from textual.containers import Horizontal, Vertical
from textual.binding import Binding

class FileMenuApp(App):
    """Three-column file context menu."""
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+b", "quit", "Quit", key_display="Ctrl+B", show=True),
        Binding("escape", "quit", "Quit"),
        Binding("r", "to_readable", "Readable"),
        Binding("e", "to_editable", "Editable"),
        Binding("d", "delete_selected", "Delete"),
        Binding("ctrl+d", "clear_lists", "Clear All", key_display="Ctrl+D", show=True),
    ]
    CSS = """
    Horizontal { height: 100%; }
    Vertical { width: 1fr; border: tall white; }
    Static { text-align: left; background: $primary-background; color: $text; padding: 0 1; }
    ListView { border: tall $primary; }
    ListItem { height: 1; min-height: 1; padding: 0; }
    DirectoryTree { border: tall $primary; }
    """

    def __init__(self, editable_files: list[str], readable_files: list[str], root_dir: str):
        super().__init__()
        self.editable_files = editable_files
        self.readable_files = readable_files
        self.root_dir = os.path.abspath(root_dir)
        self.editable_set = set(editable_files)
        self.readable_set = set(readable_files)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical():
                yield Static("Editable Files\n(d: delete, r: move to readable)")
                yield ListView(id="editable")
            with Vertical():
                yield Static("Readable Files\n(d: delete, e: move to editable)")
                yield ListView(id="readable")
            with Vertical():
                yield Static("Navigator (Project Files)\nr: readable\ne: editable\nd: remove")
                yield DirectoryTree(self.root_dir, id="navigator")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_lists()
        self.query_one("#navigator", DirectoryTree).focus()

    def refresh_lists(self) -> None:
        """Refresh left and middle columns with sorted relative paths."""
        def populate_list(view_id: str, paths: list[str]):
            view = self.query_one(f"#{view_id}", ListView)
            view.clear()
            for path in sorted(paths):
                item = ListItem(Static(path))
                setattr(item, 'custom_path', path)
                view.append(item)

        populate_list("editable", self.editable_files)
        populate_list("readable", self.readable_files)

    def action_delete_selected(self) -> None:
        """Global 'd': delete/remove selected item or from navigator."""
        focused = self.focused
        if isinstance(focused, ListView) and focused.highlighted_child:
            path = getattr(focused.highlighted_child, 'custom_path', None)
            if path is None:
                return
            if focused.id == "editable":
                self.editable_files.remove(path)
                self.editable_set.remove(path)
            elif focused.id == "readable":
                self.readable_files.remove(path)
                self.readable_set.remove(path)
            self.refresh_lists()
            return

        if isinstance(focused, DirectoryTree):
            node = focused.cursor_node
            if node and node.data and os.path.isfile(node.data.path):
                rel_path = os.path.relpath(node.data.path, self.root_dir)
                if rel_path in self.editable_set:
                    self.editable_files.remove(rel_path)
                    self.editable_set.remove(rel_path)
                elif rel_path in self.readable_set:
                    self.readable_files.remove(rel_path)
                    self.readable_set.remove(rel_path)
                self.refresh_lists()

    def action_to_readable(self) -> None:
        """Global 'r': move from editable to readable or add from navigator."""
        focused = self.focused
        if focused and focused.id == "editable" and focused.highlighted_child:
            path = getattr(focused.highlighted_child, 'custom_path', None)
            if path is None:
                return
            self.editable_files.remove(path)
            self.editable_set.remove(path)
            if path not in self.readable_set:
                self.readable_files.append(path)
                self.readable_set.add(path)
            self.refresh_lists()
            return

        if isinstance(focused, DirectoryTree):
            node = focused.cursor_node
            if node and node.data and os.path.isfile(node.data.path):
                rel_path = os.path.relpath(node.data.path, self.root_dir)
                if rel_path not in self.editable_set and rel_path not in self.readable_set:
                    self.readable_files.append(rel_path)
                    self.readable_set.add(rel_path)
                    self.refresh_lists()

    def action_to_editable(self) -> None:
        """Global 'e': move from readable to editable or add from navigator."""
        focused = self.focused
        if focused and focused.id == "readable" and focused.highlighted_child:
            path = getattr(focused.highlighted_child, 'custom_path', None)
            if path is None:
                return
            self.readable_files.remove(path)
            self.readable_set.remove(path)
            if path not in self.editable_set:
                self.editable_files.append(path)
                self.editable_set.add(path)
            self.refresh_lists()
            return

        if isinstance(focused, DirectoryTree):
            node = focused.cursor_node
            if node and node.data and os.path.isfile(node.data.path):
                rel_path = os.path.relpath(node.data.path, self.root_dir)
                if rel_path not in self.editable_set and rel_path not in self.readable_set:
                    self.editable_files.append(rel_path)
                    self.editable_set.add(rel_path)
                    self.refresh_lists()

    def action_clear_lists(self) -> None:
        """Clear all editable and readable lists."""
        self.editable_files.clear()
        self.readable_files.clear()
        self.editable_set.clear()
        self.readable_set.clear()
        self.refresh_lists()
