"""The easymd application: editor pane, live Markdown preview, vim command line."""

from __future__ import annotations

from pathlib import Path

from rich.markup import escape
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.geometry import Offset
from textual.message import Message
from textual.widgets import Input, Markdown, Static, TextArea

from .editor import VimTextArea

MODE_STYLES = {
    "normal": ("NORMAL", "blue"),
    "insert": ("INSERT", "green"),
    "replace": ("REPLACE", "red"),
    "visual": ("VISUAL", "magenta"),
    "visual_line": ("V-LINE", "magenta"),
}


class CommandLine(Input):
    """The `:` / `/` command line; escape cancels back to the editor."""

    class Cancelled(Message):
        pass

    def __init__(self, **kwargs) -> None:
        # Focus must not select the prefix, or the first keystroke replaces it.
        kwargs.setdefault("select_on_focus", False)
        super().__init__(**kwargs)

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.post_message(self.Cancelled())
            return
        await super()._on_key(event)


class EasyMDApp(App):
    TITLE = "easymd"

    CSS = """
    #main { height: 1fr; }
    #editor { width: 1fr; border: none; }
    #preview-scroll {
        width: 1fr;
        border-left: heavy $accent;
        padding: 0 1;
        scrollbar-size-vertical: 1;
    }
    #status { dock: bottom; height: 1; background: $panel; padding: 0 1; }
    #cmdline {
        dock: bottom;
        height: 1;
        border: none;
        padding: 0 1;
        background: $surface;
        display: none;
    }
    """

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self._saved_text = (
            path.read_text(encoding="utf-8") if path.exists() else ""
        )
        self._preview_timer = None
        self._notice = ""

    # ------------------------------------------------------------------
    # Layout

    def compose(self) -> ComposeResult:
        editor = VimTextArea(self._saved_text, id="editor", show_line_numbers=True)
        try:
            editor.language = "markdown"
        except Exception:
            pass  # syntax highlighting is optional (needs textual[syntax])
        with Horizontal(id="main"):
            yield editor
            with VerticalScroll(id="preview-scroll"):
                yield Markdown(self._saved_text, id="preview")
        yield Static(id="status")
        yield CommandLine(id="cmdline")

    def on_mount(self) -> None:
        self.editor.focus()
        self._update_status()
        # Keep the preview aligned whenever the editor scrolls (cursor moves
        # that scroll the viewport, wheel scrolling, page motions, …).
        self.watch(self.editor, "scroll_y", self._on_editor_scroll, init=False)

    def _on_editor_scroll(self, *_args) -> None:
        self._sync_scroll()

    @property
    def editor(self) -> VimTextArea:
        return self.query_one("#editor", VimTextArea)

    @property
    def modified(self) -> bool:
        return self.editor.text != self._saved_text

    # ------------------------------------------------------------------
    # Status bar

    def _update_status(self) -> None:
        try:
            status = self.query_one("#status", Static)
        except Exception:
            return
        ed = self.editor
        label, color = MODE_STYLES[ed.mode]
        row, col = ed.cursor_location
        flag = " ●" if self.modified else ""
        notice = f"  {escape(self._notice)}" if self._notice else ""
        status.update(
            f"[bold white on {color}] {label} [/] "
            f"{escape(self.path.name)}{flag}{notice}"
            f"[dim]  {row + 1}:{col + 1}[/]"
        )

    # ------------------------------------------------------------------
    # Editor events

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if self._preview_timer is not None:
            self._preview_timer.stop()
        self._preview_timer = self.set_timer(0.25, self._refresh_preview)
        self._update_status()

    def on_text_area_selection_changed(
        self, event: TextArea.SelectionChanged
    ) -> None:
        self._update_status()
        self._sync_scroll()

    def on_vim_text_area_mode_changed(
        self, event: VimTextArea.ModeChanged
    ) -> None:
        self._notice = ""
        self._update_status()

    async def _refresh_preview(self) -> None:
        await self.query_one("#preview", Markdown).update(self.editor.text)
        # Re-sync once the new blocks have been laid out and measured.
        self.call_after_refresh(self._sync_scroll)

    def _editor_top_line(self) -> int:
        """The document line currently at the top of the editor viewport."""
        ed = self.editor
        top = ed.scroll_offset.y
        try:
            # Account for soft-wrapped lines: a visual row maps to a doc line.
            return ed.wrapped_document.offset_to_location(Offset(0, top))[0]
        except Exception:
            return top

    def _preview_y_for_line(self, line: int) -> float | None:
        """Map a source line to a y offset in the preview via block anchors.

        Each rendered block knows the source range it came from and its own
        position, so we interpolate piecewise-linearly between block edges —
        this keeps tall blocks (code, tables) aligned, unlike a flat ratio.
        """
        try:
            md = self.query_one("#preview", Markdown)
        except Exception:
            return None
        anchors: list[tuple[int, int]] = []
        for block in md.children:
            source_range = getattr(block, "source_range", None)
            if source_range is None:
                continue
            start, end = source_range
            y0 = block.virtual_region.y
            anchors.append((start, y0))
            anchors.append((end, y0 + max(1, block.region.height)))
        if not anchors:
            return None
        anchors.sort()
        if line <= anchors[0][0]:
            return float(anchors[0][1])
        if line >= anchors[-1][0]:
            return float(anchors[-1][1])
        for (l0, y0), (l1, y1) in zip(anchors, anchors[1:]):
            if l0 <= line <= l1:
                if l1 == l0:
                    return float(y0)
                return y0 + (line - l0) / (l1 - l0) * (y1 - y0)
        return float(anchors[-1][1])

    def _sync_scroll(self) -> None:
        try:
            scroller = self.query_one("#preview-scroll", VerticalScroll)
        except Exception:
            return
        y = self._preview_y_for_line(self._editor_top_line())
        if y is None:
            return
        preview_max = scroller.max_scroll_y
        target = max(0, min(y, preview_max))
        # Within the editor's final screenful, ease the preview toward its own
        # bottom. A tail that renders taller than its source would otherwise be
        # unreachable: the editor runs out of scroll before the preview does.
        ed = self.editor
        ed_max = ed.max_scroll_y
        if ed_max > 0:
            remaining = ed_max - ed.scroll_offset.y
            view = max(1, ed.size.height)
            if remaining < view:
                t = 1 - remaining / view
                target += t * (preview_max - target)
        scroller.scroll_to(y=max(0, min(target, preview_max)), animate=False)

    # ------------------------------------------------------------------
    # Command line (: and /)

    def on_vim_text_area_command_requested(
        self, event: VimTextArea.CommandRequested
    ) -> None:
        cmdline = self.query_one("#cmdline", CommandLine)
        cmdline.display = True
        cmdline.value = event.prefix
        cmdline.cursor_position = len(cmdline.value)
        cmdline.focus()

    def _hide_cmdline(self) -> None:
        cmdline = self.query_one("#cmdline", CommandLine)
        cmdline.value = ""
        cmdline.display = False
        self.editor.focus()

    def on_command_line_cancelled(self, event: CommandLine.Cancelled) -> None:
        self._hide_cmdline()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value
        self._hide_cmdline()
        if value.startswith("/"):
            pattern = value[1:]
            if pattern:
                self.editor.set_search(pattern)
        elif value.startswith(":"):
            self._run_command(value[1:].strip())

    def _run_command(self, command: str) -> None:
        parts = command.split()
        if not parts:
            return
        name, args = parts[0], parts[1:]
        if name in ("w", "w!", "wq", "x"):
            target = Path(args[0]) if args else self.path
            try:
                target.write_text(self.editor.text, encoding="utf-8")
            except OSError as error:
                self._notice = f"E212: Can't open file for writing: {error}"
                self._update_status()
                return
            if target == self.path:
                self._saved_text = self.editor.text
            self._notice = f'"{target}" written'
            if name in ("wq", "x"):
                self.exit()
        elif name in ("q", "q!", "qa", "qa!"):
            if name.endswith("!") or not self.modified:
                self.exit()
            else:
                self._notice = "E37: No write since last change (add ! to override)"
        else:
            self._notice = f"E492: Not an editor command: {name}"
        self._update_status()
