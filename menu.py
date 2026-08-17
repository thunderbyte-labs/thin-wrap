import os

from rich.segment import Segment
from rich.style import Style
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Click
from textual.strip import Strip
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    ListItem,
    ListView,
    Static,
)

from directory_tree import build_directory_tree
from path_utils import resolve_path
from strings import t


class MultiSelectDirectoryTree(DirectoryTree):
    """DirectoryTree with multi-select line highlighting."""

    def __init__(self, path, *, id=None, **kwargs):
        super().__init__(path, id=id, **kwargs)
        self._selected_paths: set[str] = set()

    def set_selected(self, paths: set[str]) -> None:
        """Set the highlighted file paths and repaint."""
        self._selected_paths = set(paths)
        self._updates += 1
        self._clear_line_cache()
        self.refresh()

    def render_line(self, y: int) -> Strip:
        strip = super().render_line(y)
        node = self.get_node_at_line(y)
        if node is not None and node.data is not None:
            path = str(getattr(node.data, "path", ""))
            if path in self._selected_paths:
                highlight = Style(bgcolor="magenta")
                segments = [
                    Segment(
                        text,
                        style + highlight if style else highlight,
                        control,
                    )
                    for text, style, control in strip._segments
                ]
                return Strip(segments, strip.cell_length)
        return strip


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
        Binding(
            "escape",
            "clear_selection_or_quit",
            t("menus.shortcuts.clear_selection"),
            key_display="Escape",
            show=True,
        ),
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
        Binding(
            "ctrl+click",
            "multiselect_toggle",
            t("menus.shortcuts.multiselect_toggle"),
            key_display="Ctrl+click",
            show=True,
        ),
        Binding(
            "shift+click",
            "multiselect_range",
            t("menus.shortcuts.multiselect_range"),
            key_display="Shift+click",
            show=True,
        ),
    ]
    CSS = """
    #columns { height: 100%; }
    #left-pane { width: 2fr; border: none; }
    #file-columns { height: 1fr; }
    #file-columns > Vertical { width: 1fr; border: tall white; }
    #navigator-pane { width: 1fr; border: tall white; }
    #tree-controls { height: 1; border: none; align: left middle; }
    #tree-toggle, #tree-depth, #tree-charcount { padding: 0; width: auto; height: 1; }
    Static { text-align: left; background: $primary-background; color: $text; padding: 0 1; }
    ListView { border: tall $primary; }
    ListItem { height: 1; min-height: 1; padding: 0; }
    ListItem.selected { background: $primary 35%; }
    DirectoryTree { border: tall $primary; }
    Button.tree-btn { width: 3; min-width: 3; height: 1; min-height: 1; padding: 0; margin: 0; border: none; content-align: center middle; }
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
        self.tree_max_depth: int | None = None
        self._left_selection: set[str] = set()
        self._right_selection: set[str] = set()
        self._shift_anchor: tuple[str, str] | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="columns"):
            with Vertical(id="left-pane"):
                with Horizontal(id="tree-controls"):
                    yield Static(id="tree-toggle", markup=False)
                    yield Static(id="tree-depth", markup=False)
                    yield Button("−", id="depth-down", classes="tree-btn")
                    yield Button("+", id="depth-up", classes="tree-btn")
                    yield Static(id="tree-charcount", markup=False)
                with Horizontal(id="file-columns"):
                    with Vertical():
                        yield Static(t("menus.editable_files_menu"))
                        yield ListView(id="editable")
                    with Vertical():
                        yield Static(t("menus.readable_files_menu"))
                        yield ListView(id="readable")
            with Vertical(id="navigator-pane"):
                yield Static(t("menus.navigator_menu"))
                yield MultiSelectDirectoryTree(self.root_dir, id="navigator")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_lists()
        self._refresh_tree_controls()
        self.query_one("#navigator", MultiSelectDirectoryTree).focus()

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
        self._apply_left_highlights()

    # ------------------------------------------------------------------
    # Multi-select helpers
    # ------------------------------------------------------------------

    def _selection(self, zone: str) -> set[str]:
        return self._left_selection if zone == "left" else self._right_selection

    def _other_zone(self, zone: str) -> str:
        return "right" if zone == "left" else "left"

    def _clear_selection(self, zone: str) -> None:
        self._selection(zone).clear()
        self._update_highlights(zone)

    def _set_selection(self, zone: str, paths: set[str]) -> None:
        selection = self._selection(zone)
        selection.clear()
        selection.update(paths)
        self._update_highlights(zone)

    def _toggle_select(self, zone: str, path: str) -> None:
        selection = self._selection(zone)
        if path in selection:
            selection.discard(path)
        else:
            selection.add(path)
        self._update_highlights(zone)

    def _update_highlights(self, zone: str) -> None:
        if zone == "left":
            self._apply_left_highlights()
        else:
            self.query_one("#navigator", MultiSelectDirectoryTree).set_selected(
                self._right_selection
            )

    def _apply_left_highlights(self) -> None:
        for view_id in ("editable", "readable"):
            view = self.query_one(f"#{view_id}", ListView)
            for item in view.children:
                item.set_class(
                    getattr(item, "custom_path", None) in self._left_selection,
                    "selected",
                )

    def _column_paths(self, view_id: str) -> list[str]:
        view = self.query_one(f"#{view_id}", ListView)
        return [getattr(item, "custom_path", None) for item in view.children]

    def _left_range(self, anchor: str, path: str) -> set[str]:
        for view_id in ("editable", "readable"):
            paths = self._column_paths(view_id)
            if anchor in paths and path in paths:
                start = min(paths.index(anchor), paths.index(path))
                end = max(paths.index(anchor), paths.index(path)) + 1
                return {p for p in paths[start:end] if p}
        return {path} if path else set()

    def _right_range(self, anchor: str, path: str) -> set[str]:
        tree = self.query_one("#navigator", MultiSelectDirectoryTree)
        line_of: dict[str, int] = {}
        for y in range(tree.last_line + 1):
            node = tree.get_node_at_line(y)
            if node is not None and node.data is not None:
                node_path = str(getattr(node.data, "path", ""))
                if node_path:
                    line_of[node_path] = y
        if anchor not in line_of or path not in line_of:
            return {path} if path else set()
        start = min(line_of[anchor], line_of[path])
        end = max(line_of[anchor], line_of[path])
        return {p for p, line in line_of.items() if start <= line <= end}

    def _range_paths(self, zone: str, anchor: str, path: str) -> set[str]:
        if zone == "left":
            return self._left_range(anchor, path)
        return self._right_range(anchor, path)

    def _click_target(self, event: Click) -> tuple[str, str] | None:
        """Resolve a click to (zone, path), or None when not a selectable item."""
        widget = event.widget
        node = widget
        while node is not None:
            if isinstance(node, ListItem):
                path = getattr(node, "custom_path", None)
                if path:
                    return "left", path
            node = node.parent
        if isinstance(widget, MultiSelectDirectoryTree):
            meta = event.style.meta if event.style else {}
            line = meta.get("line")
            if line is None:
                return None
            tree_node = widget.get_node_at_line(line)
            if tree_node is not None and tree_node.data is not None:
                path = str(getattr(tree_node.data, "path", ""))
                if path and os.path.isfile(path):
                    return "right", path
        return None

    async def _on_click(self, event: Click) -> None:
        target = self._click_target(event)
        if target is None:
            return
        zone, path = target
        if event.ctrl or event.shift:
            if self._selection(self._other_zone(zone)):
                self.notify(t("menus.multiselect_locked"), severity="warning")
                return
            if event.shift and self._shift_anchor and self._shift_anchor[0] == zone:
                self._set_selection(
                    zone, self._range_paths(zone, self._shift_anchor[1], path)
                )
            else:
                self._toggle_select(zone, path)
                self._shift_anchor = (zone, path)
            return
        # Plain click: reset this zone's selection and start a fresh anchor.
        if self._selection(zone):
            self._clear_selection(zone)
        self._shift_anchor = (zone, path)

    def action_clear_selection_or_quit(self) -> None:
        """Global escape: clear the current multi-selection, else quit."""
        if self._left_selection or self._right_selection:
            self._clear_selection("left")
            self._clear_selection("right")
        else:
            self.exit()

    def action_noop(self) -> None:
        """No-op action for display-only footer bindings."""

    def action_multiselect_toggle(self) -> None:
        """Display-only binding for the Ctrl+click footer hint."""

    def action_multiselect_range(self) -> None:
        """Display-only binding for the Shift+click footer hint."""

    # ------------------------------------------------------------------
    # Tree context controls
    # ------------------------------------------------------------------

    def _tree_count(self, depth: int) -> int:
        """Character count of the final tree string at the given depth."""
        try:
            return len(build_directory_tree(self.root_dir, depth))
        except Exception:
            return 0

    @property
    def _depth_cap(self) -> int:
        """Highest useful depth; the '+' button is disabled at or above it."""
        if self.tree_max_depth is not None:
            return self.tree_max_depth
        return self.MAX_TREE_DEPTH

    def _refresh_tree_controls(self) -> None:
        """Update toggle checkbox, depth label, and live tree character count."""
        marker = "x" if self.tree_context_enabled else " "
        self.query_one("#tree-toggle", Static).update(
            t("menus.tree_context_line", marker=marker)
        )
        self.query_one("#tree-depth", Static).update(
            t("menus.tree_depth_label", depth=self.tree_depth)
        )
        count = self._tree_count(self.tree_depth) if self.tree_context_enabled else 0
        formatted = f"{count:,}".replace(",", " ")
        self.query_one("#tree-charcount", Static).update(
            t("menus.tree_chars_label", count=formatted)
        )
        # The natural-depth cap only makes sense when the tree is actually
        # being generated; otherwise the '+' button is simply bounded by the
        # hard maximum depth.
        if self.tree_context_enabled:
            plus_disabled = self.tree_depth >= self._depth_cap
        else:
            plus_disabled = self.tree_depth >= self.MAX_TREE_DEPTH
        self.query_one("#depth-up", Button).disabled = plus_disabled

    def action_toggle_tree_context(self) -> None:
        """Global 't': toggle the directory tree context feature."""
        self.tree_context_enabled = not self.tree_context_enabled
        self._refresh_tree_controls()

    def action_increase_depth(self) -> None:
        if self.tree_context_enabled and self.tree_depth >= self._depth_cap:
            return
        current = self.tree_depth
        new = current + 1
        if new <= self.MAX_TREE_DEPTH:
            if self.tree_context_enabled and self._tree_count(new) == self._tree_count(
                current
            ):
                # Tree stopped growing: current depth is the natural maximum.
                self.tree_max_depth = current
            else:
                self.tree_depth = new
        self._refresh_tree_controls()

    def action_decrease_depth(self) -> None:
        if self.tree_depth > self.MIN_TREE_DEPTH:
            current = self.tree_depth
            new = current - 1
            if self.tree_context_enabled and self._tree_count(new) == self._tree_count(
                current
            ):
                # Current depth was already useless; the cap is one lower.
                self.tree_depth = new
                self.tree_max_depth = new
            else:
                self.tree_depth = new
        self._refresh_tree_controls()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "depth-up":
            self.action_increase_depth()
        elif event.button.id == "depth-down":
            self.action_decrease_depth()

    # ------------------------------------------------------------------
    # r / e / d actions (multi-select aware)
    # ------------------------------------------------------------------

    def action_delete_selected(self) -> None:
        """Global 'd': delete/remove selected item or from navigator."""
        focused = self.focused
        if isinstance(focused, ListView):
            if self._left_selection:
                for path in list(self._left_selection):
                    if path in self.editable_set:
                        self.editable_files.remove(path)
                        self.editable_set.remove(path)
                    if path in self.readable_set:
                        self.readable_files.remove(path)
                        self.readable_set.remove(path)
                self._clear_selection("left")
                self.refresh_lists()
                return
            if focused.highlighted_child:
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

        if isinstance(focused, MultiSelectDirectoryTree):
            if self._right_selection:
                for abs_path in list(self._right_selection):
                    rel_path = os.path.relpath(abs_path, self.root_dir)
                    if rel_path in self.editable_set:
                        self.editable_files.remove(rel_path)
                        self.editable_set.remove(rel_path)
                    elif rel_path in self.readable_set:
                        self.readable_files.remove(rel_path)
                        self.readable_set.remove(rel_path)
                self._clear_selection("right")
                self.refresh_lists()
                return
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
        if isinstance(focused, ListView):
            if self._left_selection:
                moved = False
                for path in list(self._left_selection):
                    if path in self.editable_set:
                        self.editable_files.remove(path)
                        self.editable_set.remove(path)
                        if path not in self.readable_set:
                            self.readable_files.append(path)
                            self.readable_set.add(path)
                        moved = True
                if moved:
                    self._clear_selection("left")
                    self.refresh_lists()
                return
            if focused.id == "editable" and focused.highlighted_child:
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

        if isinstance(focused, MultiSelectDirectoryTree):
            if self._right_selection:
                added = False
                for abs_path in list(self._right_selection):
                    rel_path = os.path.relpath(abs_path, self.root_dir)
                    if (
                        rel_path not in self.editable_set
                        and rel_path not in self.readable_set
                    ):
                        self.readable_files.append(rel_path)
                        self.readable_set.add(rel_path)
                        added = True
                if added:
                    self._clear_selection("right")
                    self.refresh_lists()
                return
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
        if isinstance(focused, ListView):
            if self._left_selection:
                moved = False
                for path in list(self._left_selection):
                    if path in self.readable_set:
                        self.readable_files.remove(path)
                        self.readable_set.remove(path)
                        if path not in self.editable_set:
                            self.editable_files.append(path)
                            self.editable_set.add(path)
                        moved = True
                if moved:
                    self._clear_selection("left")
                    self.refresh_lists()
                return
            if focused.id == "readable" and focused.highlighted_child:
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

        if isinstance(focused, MultiSelectDirectoryTree):
            if self._right_selection:
                added = False
                for abs_path in list(self._right_selection):
                    rel_path = os.path.relpath(abs_path, self.root_dir)
                    if (
                        rel_path not in self.editable_set
                        and rel_path not in self.readable_set
                    ):
                        self.editable_files.append(rel_path)
                        self.editable_set.add(rel_path)
                        added = True
                if added:
                    self._clear_selection("right")
                    self.refresh_lists()
                return
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
        self._clear_selection("left")
        self.refresh_lists()
