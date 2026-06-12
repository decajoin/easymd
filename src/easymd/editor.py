"""Vim-style modal editing layer on top of Textual's TextArea."""

from __future__ import annotations

import re

from textual import events
from textual.message import Message
from textual.widgets import TextArea
from textual.widgets.text_area import Selection

# A vim "word": a run of word chars, or a run of punctuation.
WORD_RE = re.compile(r"\w+|[^\w\s]+")

NORMAL = "normal"
INSERT = "insert"
VISUAL = "visual"
VISUAL_LINE = "visual_line"


class VimTextArea(TextArea):
    """TextArea with a vim-like modal key layer (normal / insert / visual)."""

    class ModeChanged(Message):
        def __init__(self, mode: str) -> None:
            super().__init__()
            self.mode = mode

    class CommandRequested(Message):
        """User pressed `:` or `/` in normal mode; the app owns the command line."""

        def __init__(self, prefix: str) -> None:
            super().__init__()
            self.prefix = prefix

    def __init__(self, text: str = "", **kwargs) -> None:
        kwargs.setdefault("tab_behavior", "indent")
        super().__init__(text, **kwargs)
        self.mode = NORMAL
        self._count = ""
        self._pending = ""  # pending operator/prefix: d, y, c or g
        self._register: tuple[str, bool] = ("", False)  # (text, linewise)
        self._search = ""
        self._line_anchor = 0  # anchor row for visual line mode

    # ------------------------------------------------------------------
    # Modes

    def _set_mode(self, mode: str) -> None:
        if mode == self.mode:
            return
        self.mode = mode
        self._count = ""
        self._pending = ""
        self.post_message(self.ModeChanged(mode))

    # ------------------------------------------------------------------
    # Key dispatch

    async def _on_key(self, event: events.Key) -> None:
        if self.mode == INSERT:
            if event.key == "escape":
                event.stop()
                event.prevent_default()
                row, col = self.cursor_location
                if col > 0:
                    self.move_cursor((row, col - 1))
                self._set_mode(NORMAL)
                return
            await super()._on_key(event)
            return
        # Normal / visual mode: nothing reaches the underlying TextArea.
        event.stop()
        event.prevent_default()
        self._handle_modal_key(event)

    def _handle_modal_key(self, event: events.Key) -> None:
        key = event.key
        char = event.character if event.is_printable else None

        if key == "escape":
            if self.mode in (VISUAL, VISUAL_LINE):
                self.selection = Selection.cursor(self.cursor_location)
            self._set_mode(NORMAL)
            self._count = ""
            self._pending = ""
            return

        # Count prefix; a lone 0 is the line-start motion, not a count.
        if char and char.isdigit() and not (char == "0" and not self._count):
            self._count += char
            return

        n = int(self._count) if self._count else 1
        explicit_count = bool(self._count)
        self._count = ""
        pending, self._pending = self._pending, ""

        if pending == "g":
            if char == "g":
                last = self.document.line_count - 1
                row = min(n - 1, last) if explicit_count else 0
                self._move((row, 0))
            return

        if pending in ("d", "y", "c"):
            self._handle_operator(pending, char, key, n, explicit_count)
            return

        # Visual-mode operators act on the selection.
        if char in ("d", "x", "y", "c"):
            if self.mode == VISUAL:
                self._visual_operate(char)
                return
            if self.mode == VISUAL_LINE:
                self._visual_line_operate(char)
                return

        # Plain motions (extend the selection in visual mode).
        target = self._motion_target(char or key, n, explicit_count)
        if target is not None:
            self._move(target)
            return

        self._handle_command_key(char, key, n, explicit_count)

    def _move(self, target: tuple[int, int]) -> None:
        if self.mode == VISUAL_LINE:
            self.move_cursor(target)
            self._update_linewise_selection()
        else:
            self.move_cursor(target, select=self.mode == VISUAL)

    def _update_linewise_selection(self) -> None:
        """Expand the selection to whole lines between the anchor and the cursor."""
        row = self.cursor_location[0]
        anchor = self._line_anchor
        doc = self.document
        if row >= anchor:
            self.selection = Selection(
                (anchor, 0), (row, len(doc.get_line(row)))
            )
        else:
            self.selection = Selection(
                (anchor, len(doc.get_line(anchor))), (row, 0)
            )

    # ------------------------------------------------------------------
    # Normal-mode commands

    def _handle_command_key(
        self, char: str | None, key: str, n: int, explicit_count: bool
    ) -> None:
        doc = self.document
        row, col = self.cursor_location

        if char == "i":
            self._set_mode(INSERT)
        elif char == "a":
            line = doc.get_line(row)
            if col < len(line):
                self.move_cursor((row, col + 1))
            self._set_mode(INSERT)
        elif char == "A":
            self.move_cursor((row, len(doc.get_line(row))))
            self._set_mode(INSERT)
        elif char == "I":
            line = doc.get_line(row)
            self.move_cursor((row, len(line) - len(line.lstrip())))
            self._set_mode(INSERT)
        elif char == "o":
            self.move_cursor((row, len(doc.get_line(row))))
            self.insert("\n")
            self._set_mode(INSERT)
        elif char == "O":
            self.move_cursor((row, 0))
            self.insert("\n")
            self.move_cursor((row, 0))
            self._set_mode(INSERT)
        elif char == "x":
            line = doc.get_line(row)
            end = min(len(line), col + n)
            if end > col:
                self._register = (self.get_text_range((row, col), (row, end)), False)
                self.delete((row, col), (row, end))
        elif char in ("d", "y", "c"):
            self._pending = char
            if explicit_count:
                self._count = str(n)
        elif char == "g":
            self._pending = "g"
            if explicit_count:
                self._count = str(n)
        elif char == "v":
            if self.mode == VISUAL:
                self.selection = Selection.cursor(self.cursor_location)
                self._set_mode(NORMAL)
            else:
                # From normal or visual line; keep the selection when switching.
                self._set_mode(VISUAL)
        elif char == "V":
            if self.mode == VISUAL_LINE:
                self.selection = Selection.cursor(self.cursor_location)
                self._set_mode(NORMAL)
            else:
                # Anchor on the selection start when coming from charwise visual.
                if self.mode == VISUAL:
                    self._line_anchor = min(
                        self.selection.start[0], self.selection.end[0]
                    )
                else:
                    self._line_anchor = row
                self._set_mode(VISUAL_LINE)
                self._update_linewise_selection()
        elif char == "p":
            self._paste(after=True, n=n)
        elif char == "P":
            self._paste(after=False, n=n)
        elif char == "u":
            self.undo()
        elif key == "ctrl+r":
            self.redo()
        elif char in (":", "/"):
            self.post_message(self.CommandRequested(char))
        elif char == "n":
            self.search_next()
        elif char == "N":
            self.search_next(reverse=True)
        elif key in ("ctrl+d", "ctrl+u"):
            half = max(1, self.size.height // 2)
            delta = half if key == "ctrl+d" else -half
            new_row = max(0, min(doc.line_count - 1, row + delta))
            self._move((new_row, min(col, len(doc.get_line(new_row)))))
        elif key in ("ctrl+f", "pagedown"):
            self.action_cursor_page_down()
        elif key in ("ctrl+b", "pageup"):
            self.action_cursor_page_up()

    # ------------------------------------------------------------------
    # Motions

    def _motion_target(
        self, sym: str, n: int, explicit_count: bool
    ) -> tuple[int, int] | None:
        doc = self.document
        row, col = self.cursor_location
        last = doc.line_count - 1

        def clamp(r: int, c: int) -> tuple[int, int]:
            return (r, min(c, len(doc.get_line(r))))

        if sym in ("h", "left"):
            return (row, max(0, col - n))
        if sym in ("l", "right"):
            return clamp(row, col + n)
        if sym in ("j", "down"):
            return clamp(min(last, row + n), col)
        if sym in ("k", "up"):
            return clamp(max(0, row - n), col)
        if sym in ("0", "home"):
            return (row, 0)
        if sym == "^":
            line = doc.get_line(row)
            return (row, len(line) - len(line.lstrip()))
        if sym in ("$", "end"):
            return (row, len(doc.get_line(row)))
        if sym == "G":
            return (min(n - 1, last) if explicit_count else last, 0)
        if sym == "w":
            return self._next_word(n, end=False)
        if sym == "e":
            return self._next_word(n, end=True)
        if sym == "b":
            return self._prev_word(n)
        return None

    def _next_word(self, n: int, end: bool) -> tuple[int, int]:
        row, col = self.cursor_location
        for _ in range(n):
            row, col = self._scan_forward(row, col, end)
        return (row, col)

    def _scan_forward(self, row: int, col: int, end: bool) -> tuple[int, int]:
        doc = self.document
        for r in range(row, doc.line_count):
            for m in WORD_RE.finditer(doc.get_line(r)):
                pos = m.start() if not end else m.end() - 1
                if r > row or pos > col:
                    return (r, pos)
        last = doc.line_count - 1
        return (last, max(0, len(doc.get_line(last)) - (1 if end else 0)))

    def _prev_word(self, n: int) -> tuple[int, int]:
        row, col = self.cursor_location
        for _ in range(n):
            row, col = self._scan_back(row, col)
        return (row, col)

    def _scan_back(self, row: int, col: int) -> tuple[int, int]:
        doc = self.document
        for r in range(row, -1, -1):
            best = None
            for m in WORD_RE.finditer(doc.get_line(r)):
                if r < row or m.start() < col:
                    best = m.start()
                else:
                    break
            if best is not None:
                return (r, best)
        return (0, 0)

    # ------------------------------------------------------------------
    # Operators (d / y / c)

    def _line_range_text(self, row: int, end_row: int) -> str:
        end_col = len(self.document.get_line(end_row))
        return self.get_text_range((row, 0), (end_row, end_col))

    def _delete_lines(self, n: int) -> None:
        doc = self.document
        row, _ = self.cursor_location
        last = doc.line_count - 1
        end_row = min(row + n - 1, last)
        self._register = (self._line_range_text(row, end_row) + "\n", True)
        if end_row < last:
            self.delete((row, 0), (end_row + 1, 0))
        elif row > 0:
            # Deleting through the last line: eat the preceding newline instead.
            self.delete(
                (row - 1, len(doc.get_line(row - 1))),
                (end_row, len(doc.get_line(end_row))),
            )
        else:
            self.delete((0, 0), (end_row, len(doc.get_line(end_row))))
        new_last = self.document.line_count - 1
        self.move_cursor((min(row, new_last), 0))

    def _handle_operator(
        self, op: str, char: str | None, key: str, n: int, explicit_count: bool
    ) -> None:
        # Doubled operator (dd / yy / cc) works on whole lines.
        if char == op:
            row, _ = self.cursor_location
            end_row = min(row + n - 1, self.document.line_count - 1)
            if op == "y":
                self._register = (self._line_range_text(row, end_row) + "\n", True)
            elif op == "d":
                self._delete_lines(n)
            else:  # cc: clear the lines' content and start inserting
                self._register = (self._line_range_text(row, end_row) + "\n", True)
                end_col = len(self.document.get_line(end_row))
                self.delete((row, 0), (end_row, end_col))
                self.move_cursor((row, 0))
                self._set_mode(INSERT)
            return

        target = self._motion_target(char or key, n, explicit_count)
        if target is None:
            return
        start = self.cursor_location
        if target < start:
            start, target = target, start
        elif char == "e":
            # 'e' is an inclusive motion: take the character under the target too.
            target = (target[0], target[1] + 1)
        text = self.get_text_range(start, target)
        if not text:
            return
        self._register = (text, False)
        if op == "y":
            self.move_cursor(start)
            return
        self.delete(start, target)
        if op == "c":
            self._set_mode(INSERT)

    def _visual_line_operate(self, char: str) -> None:
        sel = self.selection
        row, end_row = sorted([sel.start[0], sel.end[0]])
        self._register = (self._line_range_text(row, end_row) + "\n", True)
        if char == "y":
            self.move_cursor((row, 0))
        elif char == "c":
            end_col = len(self.document.get_line(end_row))
            self.delete((row, 0), (end_row, end_col))
            self.move_cursor((row, 0))
        else:  # d / x: remove the lines entirely, dd-style
            self.move_cursor((row, 0))
            self._delete_lines(end_row - row + 1)
        self._set_mode(INSERT if char == "c" else NORMAL)

    def _visual_operate(self, char: str) -> None:
        sel = self.selection
        start, end = sorted([sel.start, sel.end])
        # Vim's visual selection includes the character under the cursor.
        line_len = len(self.document.get_line(end[0]))
        end = (end[0], min(line_len, end[1] + 1))
        text = self.get_text_range(start, end)
        self._register = (text, False)
        if char == "y":
            self.move_cursor(start)
        else:  # d / x / c
            self.delete(start, end)
        self._set_mode(INSERT if char == "c" else NORMAL)

    # ------------------------------------------------------------------
    # Paste

    def _paste(self, after: bool, n: int = 1) -> None:
        text, linewise = self._register
        if not text:
            return
        text = text * n
        doc = self.document
        row, col = self.cursor_location
        if linewise:
            if after:
                if row == doc.line_count - 1:
                    eol = (row, len(doc.get_line(row)))
                    self.insert("\n" + text.rstrip("\n"), eol)
                else:
                    self.insert(text, (row + 1, 0))
                self.move_cursor((row + 1, 0))
            else:
                self.insert(text, (row, 0))
                self.move_cursor((row, 0))
        else:
            line = doc.get_line(row)
            loc = (row, min(col + 1, len(line))) if after and line else (row, col)
            self.insert(text, loc, maintain_selection_offset=False)

    # ------------------------------------------------------------------
    # Search

    def set_search(self, pattern: str) -> None:
        self._search = pattern
        self.search_next()

    def search_next(self, reverse: bool = False) -> None:
        if not self._search:
            return
        doc = self.document
        matches: list[tuple[int, int]] = []
        for r in range(doc.line_count):
            line = doc.get_line(r)
            i = line.find(self._search)
            while i >= 0:
                matches.append((r, i))
                i = line.find(self._search, i + 1)
        if not matches:
            return
        here = self.cursor_location
        if reverse:
            before = [m for m in matches if m < here]
            target = before[-1] if before else matches[-1]
        else:
            after = [m for m in matches if m > here]
            target = after[0] if after else matches[0]
        self.move_cursor(target)
