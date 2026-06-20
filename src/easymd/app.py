"""The easymd application: editor pane, live Markdown preview, vim command line."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from rich.markup import escape
from textual import events, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.geometry import Offset
from textual.message import Message
from textual.widgets import Input, Markdown, OptionList, Static, TextArea
from textual.widgets.option_list import Option

from .config import Config, load_config
from .editor import VimTextArea
from .translate import Translator, TranslateError

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


class TocPanel(OptionList):
    """Heading outline; escape closes it back to the editor."""

    class Cancelled(Message):
        pass

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.post_message(self.Cancelled())
            return
        await super()._on_key(event)


_HEADING_RE = re.compile(r"(#{1,6})\s+(.*)")


def parse_headings(text: str) -> list[tuple[int, str, int]]:
    """Return (level, title, line_index) for each heading outside code fences."""
    out: list[tuple[int, str, int]] = []
    in_fence = False
    for i, line in enumerate(text.splitlines()):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if match:
            out.append((len(match.group(1)), match.group(2).strip(), i))
    return out


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
    #toc {
        width: 30;
        border-right: heavy $accent;
        display: none;
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

    def __init__(self, path: Path, config: Config | None = None) -> None:
        super().__init__()
        self.path = path
        self._saved_text = (
            path.read_text(encoding="utf-8") if path.exists() else ""
        )
        self._preview_timer = None
        self._notice = ""
        self._config = config or load_config()
        self._translator = Translator(self._config)
        # Preview window state: "original" shows editor.text, "translated"
        # shows the cached translation (untouched by edits until :refresh).
        self._preview_mode = "original"  # "original" | "translated" | "summary"
        self._translated_md = ""
        self._translated_hash: str | None = None  # doc hash when translated
        self._summary_md = ""
        self._summary_hash: str | None = None  # doc hash when summarized
        self._toc_lines: list[int] = []  # option index -> document line

    # ------------------------------------------------------------------
    # Layout

    def compose(self) -> ComposeResult:
        editor = VimTextArea(self._saved_text, id="editor", show_line_numbers=True)
        try:
            editor.language = "markdown"
        except Exception:
            pass  # syntax highlighting is optional (needs textual[syntax])
        with Horizontal(id="main"):
            yield TocPanel(id="toc")
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
        preview_flag = ""
        if self._preview_mode in self._AI:
            label = self._AI[self._preview_mode][0]
            preview_flag = (
                f" [yellow]{label}·已过期 :refresh[/]"
                if self._view_stale()
                else f" [cyan]{label}[/]"
            )
        search_flag = ""
        if ed._search and ed._search_total:
            search_flag = (
                f" [dim]/{escape(ed._search)} "
                f"{ed._search_index}/{ed._search_total}[/]"
            )
        notice = f"  {escape(self._notice)}" if self._notice else ""
        status.update(
            f"[bold white on {color}] {label} [/] "
            f"{escape(self.path.name)}{flag}{preview_flag}{search_flag}{notice}"
            f"[dim]  {row + 1}:{col + 1}[/]"
        )

    # ------------------------------------------------------------------
    # Editor events

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        # In translation view the preview holds the cached translation until the
        # user runs :refresh, so edits only refresh the status (staleness mark).
        if self._preview_mode == "original":
            self._render_preview_soon(0.25)
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

    def _render_preview_soon(self, delay: float = 0.0) -> None:
        if self._preview_timer is not None:
            self._preview_timer.stop()
        # Textual's timer divides by the interval, so 0 is not allowed; a tiny
        # positive delay is effectively immediate for an instant view toggle.
        self._preview_timer = self.set_timer(max(delay, 0.01), self._refresh_preview)

    async def _refresh_preview(self) -> None:
        if self._preview_mode == "translated":
            content = self._translated_md
        elif self._preview_mode == "summary":
            content = self._summary_md
        else:
            content = self.editor.text
        await self.query_one("#preview", Markdown).update(content)
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

    def _translated_scroll_y(self) -> float | None:
        """Preview y aligning the editor's current section with the translation.

        Both documents keep the same heading structure, so we map the heading
        the editor's top line sits under to the same heading in the preview.
        """
        headings = parse_headings(self.editor.text)
        if not headings:
            return None
        top = self._editor_top_line()
        section = -1
        for index, (_level, _title, line) in enumerate(headings):
            if line <= top:
                section = index
            else:
                break
        if section < 0:
            return 0.0
        try:
            md = self.query_one("#preview", Markdown)
        except Exception:
            return None
        seen = -1
        for block in md.children:
            source = getattr(block, "source", "") or ""
            if source.lstrip().startswith("#"):
                seen += 1
                if seen == section:
                    return float(block.virtual_region.y)
        return None

    def _sync_scroll(self) -> None:
        # The summary view is condensed and has no line correspondence.
        if self._preview_mode == "summary":
            return
        try:
            scroller = self.query_one("#preview-scroll", VerticalScroll)
        except Exception:
            return
        if self._preview_mode == "translated":
            # The translation preserves headings, so align by section heading.
            y = self._translated_scroll_y()
            if y is not None:
                scroller.scroll_to(
                    y=max(0, min(y, scroller.max_scroll_y)), animate=False
                )
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
    # Table of contents (:toc)

    def _toggle_toc(self) -> None:
        panel = self.query_one("#toc", TocPanel)
        if panel.display:
            self._hide_toc()
        else:
            self._show_toc()

    def _show_toc(self) -> None:
        panel = self.query_one("#toc", TocPanel)
        panel.clear_options()
        self._toc_lines = []
        for level, title, line in parse_headings(self.editor.text):
            panel.add_option(Option(f"{'  ' * (level - 1)}{escape(title)}"))
            self._toc_lines.append(line)
        if not self._toc_lines:
            panel.add_option(Option("[dim]（无标题）[/]"))
        panel.display = True
        panel.focus()
        if self._toc_lines:
            panel.highlighted = 0

    def _hide_toc(self) -> None:
        self.query_one("#toc", TocPanel).display = False
        self.editor.focus()

    def on_toc_panel_cancelled(self, event: TocPanel.Cancelled) -> None:
        self._hide_toc()

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        index = event.option_index
        if 0 <= index < len(self._toc_lines):
            self.editor.move_cursor((self._toc_lines[index], 0))
        self._hide_toc()

    # ------------------------------------------------------------------
    # AI preview: translation (:trans) and summary (:summarize)
    #
    # Both swap the right pane for AI-generated Markdown, cached by document
    # hash, produced in a worker and reverting to the original view on error.

    _AI = {
        "translated": ("译文", "翻译中…", "译文已更新"),
        "summary": ("摘要", "生成摘要中…", "摘要已更新"),
    }

    def _doc_hash(self) -> str:
        return hashlib.sha256(self.editor.text.encode("utf-8")).hexdigest()

    def _ai_md(self, mode: str) -> str:
        return self._translated_md if mode == "translated" else self._summary_md

    def _ai_hash(self, mode: str) -> str | None:
        return self._translated_hash if mode == "translated" else self._summary_hash

    def _set_ai(self, mode: str, md: str, hash_: str | None) -> None:
        if mode == "translated":
            self._translated_md, self._translated_hash = md, hash_
        else:
            self._summary_md, self._summary_hash = md, hash_

    def _view_stale(self) -> bool:
        mode = self._preview_mode
        if mode not in self._AI:
            return False
        h = self._ai_hash(mode)
        return h is not None and h != self._doc_hash()

    def _translation_stale(self) -> bool:  # back-compat for callers/tests
        return self._preview_mode == "translated" and self._view_stale()

    def _toggle_ai_view(self, mode: str) -> None:
        if self._preview_mode == mode:
            self._exit_translation_view()
            return
        self._preview_mode = mode
        # An up-to-date cached result switches in instantly; otherwise show a
        # placeholder and generate in the background.
        if self._ai_md(mode) and self._ai_hash(mode) == self._doc_hash():
            self._render_preview_soon(0.0)
        else:
            self._start_ai(mode)

    # Named wrappers keep the command table and existing tests readable.
    def _enter_translation_view(self) -> None:
        self._toggle_ai_view("translated")

    def _enter_summary_view(self) -> None:
        self._toggle_ai_view("summary")

    def _exit_translation_view(self) -> None:
        self._preview_mode = "original"
        self._render_preview_soon(0.0)

    def _refresh_translation(self) -> None:
        if self._preview_mode not in self._AI:
            self._notice = "E: 不在译文/摘要预览（先 :trans 或 :summarize）"
            return
        self._start_ai(self._preview_mode)

    def _start_ai(self, mode: str) -> None:
        self._set_ai(mode, f"> {self._AI[mode][1]}", None)
        self._render_preview_soon(0.0)
        self._ai_worker(mode)

    @work(exclusive=True, group="ai")
    async def _ai_worker(self, mode: str) -> None:
        source_hash = self._doc_hash()
        label, progress, done_msg = self._AI[mode]
        parts: list[str] = []

        def on_chunk(text: str, done: int, total: int) -> None:
            parts.append(text)
            self._set_ai(mode, "\n\n".join(parts), None)
            self._notice = f"{label}中… {done}/{total}"
            self._render_preview_soon(0.0)
            self._update_status()

        last_render = 0.0

        def on_delta(partial: str) -> None:
            nonlocal last_render
            self._set_ai(mode, partial, None)
            now = time.monotonic()
            if now - last_render > 0.1:  # throttle live token rendering
                last_render = now
                self._render_preview_soon(0.0)

        call = (
            self._translator.translate_document
            if mode == "translated"
            else self._translator.summarize_document
        )
        try:
            await call(self.editor.text, on_chunk, on_delta)
        except TranslateError as error:
            # Friendly fallback: revert to the original view, surface the reason.
            self._preview_mode = "original"
            self._set_ai(mode, "", None)
            self._notice = str(error)
            self._render_preview_soon(0.0)
            self._update_status()
            return
        self._set_ai(mode, "\n\n".join(parts), source_hash)
        self._notice = done_msg
        self._render_preview_soon(0.0)
        self._update_status()

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
        elif name == "trans":
            if self._preview_mode == "translated":
                self._exit_translation_view()
            else:
                self._enter_translation_view()
        elif name in ("summarize", "sum"):
            self._enter_summary_view()
        elif name in ("transback", "transorig"):
            self._exit_translation_view()
        elif name == "refresh":
            self._refresh_translation()
        elif name in ("noh", "nohlsearch"):
            self.editor.clear_search()
        elif name == "toc":
            self._toggle_toc()
        elif name in ("q", "q!", "qa", "qa!"):
            if name.endswith("!") or not self.modified:
                self.exit()
            else:
                self._notice = "E37: No write since last change (add ! to override)"
        else:
            self._notice = f"E492: Not an editor command: {name}"
        self._update_status()
