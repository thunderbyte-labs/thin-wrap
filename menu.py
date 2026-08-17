import os

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    ListItem,
    ListView,
    Static,
)

from directory_tree import build_directory_tree
from path_utils import resolve_path
from strings import t


class FileMenuApp(App):
    """Three-column file context menu."""

    DEFAULT_TREE_DEPTH = 5
    MIN_TREE_DEPTH = 1
    MAX_TREE_DEPTH = 20

    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding(
            "ctrl+b", "quit", t("menus.shortcuts.quit"), key_display="Ctrl+B", show=True
        ),
        Binding("escape", "quit", t("menus.shortcuts.quit")),
        Binding("r", "to_readable", t("menus.shortcuts.readable")),
        Binding("e", "to_editable", t("menus.shortcuts.editable")),
        Binding("d", "delete_selected", t("menus.shortcuts.delete")),
        Binding(
            "ctrl+d",
            "clear_lists",
            t("menus.shortcuts.clear_all"),
            key_display="Ctrl+D",
            show=True,
        ),
        Binding("t", "toggle_tree_context", t("menus.shortcuts.tree")),
    ]
    CSS = """
    #columns { height: 100%; }
    #left-pane { width: 2fr; border: none; }
    #file-columns { height: 1fr; }
    #file-columns > Vertical { width: 1fr; border: tall white; }
    #navigator-pane { width: 1fr; border: tall white; }
    #tree-controls { height: 1; border: none; align: left middle; padding: 0 1; }
    Static { text-align: left; background: $primary-background; color: $text; padding: 0 1; }
    ListView { border: tall $primary; }
    ListItem { height: 1; min-height: 1; padding: 0; }
    DirectoryTree { border: tall $primary; }
    Button.tree-btn { width: 3; min-width: 3; height: 1; min-height: 1; padding: 0; }
    """

    def __init__(
        self, editable_files: list[str], readable_files: list[str], root_dir: str
    ):
        super().__init__()
        self.editable_files = editable_files
        self.readable_files = readable_files
        self.root_dir = resolve_path(root_dir)
        self.editable_set = set(editable_files)
        self.readable_set = set(readable_files)
        self.tree_context_enabled = False
        self.tree_depth = self.DEFAULT_TREE_DEPTH

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="columns"):
            with Vertical(id="left-pane"):
                with Horizontal(id="tree-controls"):
                    yield Static(id="tree-toggle")
                    yield Button("−", id="depth-down", classes="tree-btn")
                    yield Static(id="tree-depth")
                    yield Button("+", id="depth-up", classes="tree-btn")
                    yield Static(id="tree-charcount")
                with Horizontal(id="file-columns"):
                    with Vertical():
                        yield Static(t("menus.editable_files_menu"))
                        yield ListView(id="editable")
                    with Vertical():
                        yield Static(t("menus.readable_files_menu"))
                        yield ListView(id="readable")
            with Vertical(id="navigator-pane"):
                yield Static(t("menus.navigator_menu"))
                yield DirectoryTree(self.root_dir, id="navigator")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_lists()
        self._refresh_tree_controls()
        self.query_one("#navigator", DirectoryTree).focus()

    def refresh_lists(self) -> None:
        """Refresh left and middle columns with sorted relative paths."""

        def populate_list(view_id: str, paths: list[str]):
            view = self.query_one(f"#{view_id}", ListView)
            view.clear()
            for path in sorted(paths):
                item = ListItem(Static(path))
                item.custom_path = path
                view.append(item)

        populate_list("editable", self.editable_files)
        populate_list("readable", self.readable_files)

    def _refresh_tree_controls(self) -> None:
        """Update toggle checkbox, depth label, and live tree character count."""
        marker = "x" if self.tree_context_enabled else " "
        self.query_one("#tree-toggle", Static).update(
            t("menus.tree_context_line", marker=marker)
        )
        self.query_one("#tree-depth", Static).update(
            t("menus.tree_depth_label", depth=self.tree_depth)
        )
        count = 0
        if self.tree_context_enabled:
            try:
                tree = build_directory_tree(self.root_dir, self.tree_depth)
                count = len(tree)
            except Exception:
                count = 0
        self.query_one("#tree-charcount", Static).update(
            t("menus.tree_chars_label", count=count)
        )

    def action_toggle_tree_context(self) -> None:
        """Global 't': toggle the directory tree context feature."""
        self.tree_context_enabled = not self.tree_context_enabled
        self._refresh_tree_controls()

    def action_increase_depth(self) -> None:
        if self.tree_depth < self.MAX_TREE_DEPTH:
            self.tree_depth += 1
            self._refresh_tree_controls()

    def action_decrease_depth(self) -> None:
        if self.tree_depth > self.MIN_TREE_DEPTH:
            self.tree_depth -= 1
            self._refresh_tree_controls()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "depth-up":
            self.action_increase_depth()
        elif event.button.id == "depth-down":
            self.action_decrease_depth()

    def action_delete_selected(self) -> None:
        """Global 'd': delete/remove selected item or from navigator."""
        focused = self.focused
        if isinstance(focused, ListView) and focused.highlighted_child:
            path = getattr(focused.highlighted_child, "custom_path", None)
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
            path = getattr(focused.highlighted_child, "custom_path", None)
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
                if (
                    rel_path not in self.editable_set
                    and rel_path not in self.readable_set
                ):
                    self.readable_files.append(rel_path)
                    self.readable_set.add(rel_path)
                    self.refresh_lists()

    def action_to_editable(self) -> None:
        """Global 'e': move from readable to editable or add from navigator."""
        focused = self.focused
        if focused and focused.id == "readable" and focused.highlighted_child:
            path = getattr(focused.highlighted_child, "custom_path", None)
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
                if (
                    rel_path not in self.editable_set
                    and rel_path not in self.readable_set
                ):
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
