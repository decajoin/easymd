"""The easymd application: editor pane, live Markdown preview, vim command line."""

from __future__ import annotations

from pathlib import Path

from rich.markup import escape
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Input, Markdown, Static, TextArea

from .editor import VimTextArea

MODE_STYLES = {
    "normal": ("NORMAL", "blue"),
    "insert": ("INSERT", "green"),
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
        self._sync_scroll()

    def _sync_scroll(self) -> None:
        try:
            scroller = self.query_one("#preview-scroll", VerticalScroll)
        except Exception:
            return
        ed = self.editor
        total = max(1, ed.document.line_count - 1)
        fraction = ed.cursor_location[0] / total
        scroller.scroll_to(y=fraction * scroller.max_scroll_y, animate=False)

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
