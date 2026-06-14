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
REPLACE = "replace"
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
        self._search_whole = False  # whole-word match (set by * and #)
        self._line_anchor = 0  # anchor row for visual line mode
        # Chars overwritten in the current R session, for backspace-restore:
        # (location, original char) or (location, None) when appended.
        self._replace_stack: list[tuple[tuple[int, int], str | None]] = []
        # Inline find (f/F/t/T) state for ; and , repeats: (cmd, char).
        self._last_find: tuple[str, str] | None = None
        # Dot-repeat: the last buffer-modifying change, as a replayable dict.
        self._last_change: dict | None = None
        self._change_capture: dict | None = None  # insert change being recorded
        self._insert_text = ""  # text typed during the captured insert
        self._replaying = False  # guard so replay does not re-record

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
                self._finalize_insert_change()
                row, col = self.cursor_location
                if col > 0:
                    self.move_cursor((row, col - 1))
                self._set_mode(NORMAL)
                return
            if self._change_capture is not None:
                if event.key == "enter":
                    self._insert_text += "\n"
                elif event.key == "backspace":
                    self._insert_text = self._insert_text[:-1]
                elif event.is_printable and event.character:
                    self._insert_text += event.character
            await super()._on_key(event)
            return
        if self.mode == REPLACE:
            event.stop()
            event.prevent_default()
            self._handle_replace_key(event)
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

        if pending == "r":
            if char:
                self._replace_chars(char, n if explicit_count else 1)
            return

        if pending in ("d", "y", "c"):
            if char in ("i", "a"):
                self._pending = pending + char
                return
            self._handle_operator(pending, char, key, n, explicit_count)
            return

        # Resolve a pending inline find (f/F/t/T), possibly after an operator
        # (df, / yt) — pending is the op prefix plus the find command.
        if pending and pending[-1] in "fFtT":
            if char:
                self._resolve_find(pending[:-1], pending[-1], char, n)
            return

        # Second half of a text object: d/y/c/v + i/a + object key.
        if len(pending) == 2:
            op, around = pending[0], pending[1] == "a"
            object_range = self._text_object_range(char, around=around)
            if object_range is not None:
                self._apply_text_object(op, *object_range)
                if op == "d":
                    self._record(
                        {"type": "delete_textobj", "obj": char, "around": around}
                    )
                elif op == "c":
                    self._begin_insert_change(
                        {"type": "change_textobj", "obj": char, "around": around}
                    )
            return

        # Visual-mode operators act on the selection.
        if char in ("d", "x", "y", "c"):
            if self.mode == VISUAL:
                self._visual_operate(char)
                return
            if self.mode == VISUAL_LINE:
                self._visual_line_operate(char)
                return

        # Text objects in (charwise) visual mode: i/a + object key.
        if self.mode == VISUAL and char in ("i", "a"):
            self._pending = "v" + char
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
            self._begin_insert_change({"type": "insert", "kind": "i", "n": n})
            self._set_mode(INSERT)
        elif char == "a":
            line = doc.get_line(row)
            if col < len(line):
                self.move_cursor((row, col + 1))
            self._begin_insert_change({"type": "insert", "kind": "a", "n": n})
            self._set_mode(INSERT)
        elif char == "A":
            self.move_cursor((row, len(doc.get_line(row))))
            self._begin_insert_change({"type": "insert", "kind": "A", "n": n})
            self._set_mode(INSERT)
        elif char == "I":
            line = doc.get_line(row)
            self.move_cursor((row, len(line) - len(line.lstrip())))
            self._begin_insert_change({"type": "insert", "kind": "I", "n": n})
            self._set_mode(INSERT)
        elif char == "o":
            self.move_cursor((row, len(doc.get_line(row))))
            self.insert("\n")
            self._begin_insert_change({"type": "insert", "kind": "o", "n": n})
            self._set_mode(INSERT)
        elif char == "O":
            self.move_cursor((row, 0))
            self.insert("\n")
            self.move_cursor((row, 0))
            self._begin_insert_change({"type": "insert", "kind": "O", "n": n})
            self._set_mode(INSERT)
        elif char == "x":
            self._do_x(n)
            self._record({"type": "x", "n": n})
        elif char == "r":
            self._pending = "r"
            if explicit_count:
                self._count = str(n)
        elif char == "R":
            self._replace_stack.clear()
            self._set_mode(REPLACE)
        elif char == "J":
            joins = max(1, n - 1) if explicit_count else 1
            self._join_lines(joins)
            self._record({"type": "join", "n": joins})
        elif char == "~":
            self._do_tilde(n)
            self._record({"type": "tilde", "n": n})
        elif char == "D":
            self._operate_range("d", (row, col), (row, len(doc.get_line(row))))
            self._record({"type": "delete_eol"})
        elif char == "C":
            self._operate_range("c", (row, col), (row, len(doc.get_line(row))))
            self._begin_insert_change({"type": "change_eol"})
        elif char == "Y":
            end_row = min(row + n - 1, doc.line_count - 1)
            self._register = (self._line_range_text(row, end_row) + "\n", True)
        elif char in ("f", "F", "t", "T"):
            self._pending = char
            if explicit_count:
                self._count = str(n)
        elif char == ";":
            self._repeat_find(reverse=False, n=n)
        elif char == ",":
            self._repeat_find(reverse=True, n=n)
        elif char in ("*", "#"):
            self._search_word(reverse=char == "#")
        elif char == ".":
            self._repeat_change(n, explicit_count)
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
            self._record({"type": "paste", "after": True, "n": n})
        elif char == "P":
            self._paste(after=False, n=n)
            self._record({"type": "paste", "after": False, "n": n})
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
        if sym == "}":
            return self._paragraph(forward=True, n=n)
        if sym == "{":
            return self._paragraph(forward=False, n=n)
        if sym == "%":
            return self._match_bracket()
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
        # Inline find after an operator (df, / ct.): wait for the target char.
        if char in ("f", "F", "t", "T"):
            self._pending = op + char
            if explicit_count:
                self._count = str(n)
            return
        # Repeat the last inline find as the operator's motion (d; / c,).
        if char in (";", ","):
            self._operate_find_repeat(op, char == ",", n)
            return

        # Doubled operator (dd / yy / cc) works on whole lines.
        if char == op:
            row, _ = self.cursor_location
            end_row = min(row + n - 1, self.document.line_count - 1)
            if op == "y":
                self._register = (self._line_range_text(row, end_row) + "\n", True)
            elif op == "d":
                self._delete_lines(n)
                self._record({"type": "delete_lines", "n": n})
            else:  # cc: clear the lines' content and start inserting
                self._register = (self._line_range_text(row, end_row) + "\n", True)
                end_col = len(self.document.get_line(end_row))
                self.delete((row, 0), (end_row, end_col))
                self.move_cursor((row, 0))
                self._begin_insert_change({"type": "change_line", "n": n})
                self._set_mode(INSERT)
            return

        # Vim quirk: cw behaves like ce (it does not eat trailing whitespace).
        if op == "c" and char == "w":
            char = "e"
        target = self._motion_target(char or key, n, explicit_count)
        if target is None:
            return
        start = self.cursor_location
        # f/F/t/T were handled above; % and forward inclusive motions take the
        # character under the target too.
        inclusive = char in ("e", "%")
        if target < start:
            start, target = target, start
            if char == "%":  # cursor's bracket is part of the d% range
                target = (target[0], target[1] + 1)
        elif inclusive:
            target = (target[0], target[1] + 1)
        self._operate_range(op, start, target)
        if op == "d":
            self._record(
                {"type": "delete_motion", "motion": char, "key": key, "n": n}
            )
        elif op == "c":
            self._begin_insert_change(
                {"type": "change_motion", "motion": char, "key": key, "n": n}
            )

    def _operate_range(
        self, op: str, start: tuple[int, int], end: tuple[int, int]
    ) -> None:
        """Yank, delete or change an arbitrary charwise range."""
        text = self.get_text_range(start, end)
        if not text:
            return
        self._register = (text, False)
        if op == "y":
            self.move_cursor(start)
            return
        self.delete(start, end)
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
    # Replace mode (R)

    def _handle_replace_key(self, event: events.Key) -> None:
        key = event.key
        if key == "escape":
            row, col = self.cursor_location
            if col > 0:
                self.move_cursor((row, col - 1))
            self._set_mode(NORMAL)
            return
        if key == "backspace":
            self._replace_backspace()
            return
        if key == "enter":
            self._replace_stack.append((self.cursor_location, None))
            self.insert("\n")
            return
        if key in ("left", "right", "up", "down", "home", "end"):
            # Moving the cursor starts a fresh overwrite run, as in vim.
            self._replace_stack.clear()
            target = self._motion_target(key, 1, False)
            if target is not None:
                self.move_cursor(target)
            return
        if event.is_printable and event.character:
            self._overwrite_char(event.character)

    def _overwrite_char(self, char: str) -> None:
        row, col = self.cursor_location
        line = self.document.get_line(row)
        if col < len(line):
            self._replace_stack.append(((row, col), line[col]))
            self.replace(
                char, (row, col), (row, col + 1), maintain_selection_offset=False
            )
        else:  # past end of line: R appends, like vim
            self._replace_stack.append(((row, col), None))
            self.insert(char)

    def _replace_backspace(self) -> None:
        """Backspace in R mode restores what the current run overwrote."""
        if not self._replace_stack:
            row, col = self.cursor_location
            if col > 0:
                self.move_cursor((row, col - 1))
            return
        (row, col), original = self._replace_stack.pop()
        if original is None:
            # An appended char (or newline): just remove it again.
            line = self.document.get_line(row)
            end = (row + 1, 0) if col >= len(line) else (row, col + 1)
            self.delete((row, col), end)
        else:
            self.replace(
                original, (row, col), (row, col + 1), maintain_selection_offset=False
            )
        self.move_cursor((row, col))

    # ------------------------------------------------------------------
    # Single-key edits (r / J)

    def _replace_chars(self, char: str, n: int) -> None:
        """Vim r: overwrite n characters under the cursor with `char`."""
        row, col = self.cursor_location
        line = self.document.get_line(row)
        if col + n > len(line):  # vim refuses if the count overruns the line
            return
        self.replace(
            char * n, (row, col), (row, col + n), maintain_selection_offset=False
        )
        self.move_cursor((row, col + n - 1))
        self._record({"type": "replace", "char": char, "n": n})

    def _do_x(self, n: int) -> None:
        """Delete n characters under and after the cursor."""
        row, col = self.cursor_location
        line = self.document.get_line(row)
        end = min(len(line), col + n)
        if end > col:
            self._register = (self.get_text_range((row, col), (row, end)), False)
            self.delete((row, col), (row, end))

    def _do_tilde(self, n: int) -> None:
        """Toggle case of n characters under the cursor and advance."""
        row, col = self.cursor_location
        line = self.document.get_line(row)
        end = min(len(line), col + n)
        if end > col:
            swapped = line[col:end].swapcase()
            self.replace(
                swapped, (row, col), (row, end), maintain_selection_offset=False
            )
            self.move_cursor((row, min(end, max(0, len(line) - 1))))

    def _join_lines(self, joins: int) -> None:
        """Vim J: join with the next line, collapsing its indent to one space."""
        for _ in range(joins):
            doc = self.document
            row, _ = self.cursor_location
            if row >= doc.line_count - 1:
                return
            current = doc.get_line(row)
            nxt = doc.get_line(row + 1)
            glue = " " if current and nxt.strip() else ""
            self.replace(
                glue + nxt.lstrip(),
                (row, len(current)),
                (row + 1, len(nxt)),
                maintain_selection_offset=False,
            )
            self.move_cursor((row, len(current)))

    # ------------------------------------------------------------------
    # Text objects (iw/aw, quotes, brackets)

    def _apply_text_object(
        self, op: str, start: tuple[int, int], end: tuple[int, int]
    ) -> None:
        if op == "v":
            # Our visual operators re-add the character under the cursor, so
            # park the selection end one character before the exclusive end.
            self.selection = Selection(start, self._loc_before(end))
            return
        self._operate_range(op, start, end)

    def _loc_before(self, loc: tuple[int, int]) -> tuple[int, int]:
        row, col = loc
        if col > 0:
            return (row, col - 1)
        if row > 0:
            return (row - 1, len(self.document.get_line(row - 1)))
        return loc

    def _text_object_range(
        self, obj: str | None, around: bool
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        if obj == "w":
            return self._word_object(around)
        if obj in ('"', "'", "`"):
            return self._quote_object(obj, around)
        if obj in ("(", ")", "b"):
            return self._bracket_object("(", ")", around)
        if obj in ("[", "]"):
            return self._bracket_object("[", "]", around)
        if obj in ("{", "}", "B"):
            return self._bracket_object("{", "}", around)
        return None

    def _word_object(
        self, around: bool
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        row, col = self.cursor_location
        line = self.document.get_line(row)
        if not line:
            return None
        col = min(col, len(line) - 1)
        for match in WORD_RE.finditer(line):
            if match.start() <= col < match.end():
                start, end = match.start(), match.end()
                if around:
                    # aw takes trailing whitespace, or leading if there is none.
                    new_end = end
                    while new_end < len(line) and line[new_end] == " ":
                        new_end += 1
                    if new_end == end:
                        while start > 0 and line[start - 1] == " ":
                            start -= 1
                    end = new_end
                return ((row, start), (row, end))
        # Cursor on whitespace: iw is the whitespace run, aw adds the next word.
        start = col
        while start > 0 and line[start - 1] == " ":
            start -= 1
        end = col
        while end < len(line) and line[end] == " ":
            end += 1
        if around:
            match = WORD_RE.match(line, end)
            if match:
                end = match.end()
        return ((row, start), (row, end))

    def _quote_object(
        self, quote: str, around: bool
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        row, col = self.cursor_location
        line = self.document.get_line(row)
        positions = [i for i, ch in enumerate(line) if ch == quote]
        for open_at, close_at in zip(positions[0::2], positions[1::2]):
            if col <= close_at:
                if around:
                    return ((row, open_at), (row, close_at + 1))
                return ((row, open_at + 1), (row, close_at))
        return None

    def _bracket_object(
        self, open_ch: str, close_ch: str, around: bool
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        row, col = self.cursor_location
        line = self.document.get_line(row)
        under = line[col] if col < len(line) else ""
        if under == open_ch:
            open_at = (row, col)
        else:
            # When sitting on the closing bracket, search left of it so the
            # scan finds this pair's opening bracket rather than an outer one.
            from_col = col - 1 if under == close_ch else col
            open_at = self._scan_bracket_back(open_ch, close_ch, row, from_col)
        if open_at is None:
            return None
        close_at = self._scan_bracket_fwd(
            open_ch, close_ch, open_at[0], open_at[1] + 1
        )
        if close_at is None:
            return None
        if around:
            return (open_at, (close_at[0], close_at[1] + 1))
        return ((open_at[0], open_at[1] + 1), close_at)

    def _scan_bracket_back(
        self, open_ch: str, close_ch: str, row: int, col: int
    ) -> tuple[int, int] | None:
        doc = self.document
        depth = 0
        for r in range(row, -1, -1):
            line = doc.get_line(r)
            start = min(col, len(line) - 1) if r == row else len(line) - 1
            for i in range(start, -1, -1):
                if line[i] == close_ch:
                    depth += 1
                elif line[i] == open_ch:
                    if depth == 0:
                        return (r, i)
                    depth -= 1
        return None

    def _scan_bracket_fwd(
        self, open_ch: str, close_ch: str, row: int, col: int
    ) -> tuple[int, int] | None:
        doc = self.document
        depth = 0
        for r in range(row, doc.line_count):
            line = doc.get_line(r)
            for i in range(col if r == row else 0, len(line)):
                if line[i] == open_ch:
                    depth += 1
                elif line[i] == close_ch:
                    if depth == 0:
                        return (r, i)
                    depth -= 1
        return None

    # ------------------------------------------------------------------
    # Dot-repeat (.)

    def _record(self, change: dict) -> None:
        """Remember the last buffer change for `.` (no-op while replaying)."""
        if not self._replaying:
            self._last_change = change
            self._change_capture = None

    def _begin_insert_change(self, change: dict) -> None:
        """Start capturing typed text for a change that enters insert mode."""
        if self._replaying:
            return
        self._change_capture = change
        self._insert_text = ""

    def _finalize_insert_change(self) -> None:
        """On leaving insert mode, freeze the captured text into the change."""
        if self._change_capture is not None:
            self._change_capture["text"] = self._insert_text
            self._last_change = self._change_capture
            self._change_capture = None

    def _advance(self, pos: tuple[int, int], text: str) -> tuple[int, int]:
        """Location of the last character of `text` inserted at `pos`."""
        if "\n" not in text:
            return (pos[0], pos[1] + len(text) - 1)
        rows = text.split("\n")
        return (pos[0] + len(rows) - 1, max(0, len(rows[-1]) - 1))

    def _insert_text_at_cursor(self, text: str) -> None:
        if not text:
            return
        pos = self.cursor_location
        self.insert(text, pos, maintain_selection_offset=False)
        self.move_cursor(self._advance(pos, text))

    def _repeat_change(self, count: int, explicit: bool) -> None:
        change = self._last_change
        if not change:
            return
        self._replaying = True
        try:
            n = count if explicit else change.get("n", 1)
            self._dispatch_repeat(change, n)
        finally:
            self._replaying = False

    def _dispatch_repeat(self, change: dict, n: int) -> None:
        t = change["type"]
        if t == "x":
            self._do_x(n)
        elif t == "tilde":
            self._do_tilde(n)
        elif t == "join":
            self._join_lines(n)
        elif t == "replace":
            self._replace_chars(change["char"], n)
        elif t == "paste":
            self._paste(change["after"], n)
        elif t == "delete_lines":
            self._delete_lines(n)
        elif t == "delete_eol":
            row, col = self.cursor_location
            self._operate_range(
                "d", (row, col), (row, len(self.document.get_line(row)))
            )
        elif t == "delete_motion":
            self._handle_operator("d", change["motion"], change["key"], n, True)
        elif t == "delete_textobj":
            rng = self._text_object_range(change["obj"], change["around"])
            if rng:
                self._operate_range("d", *rng)
        elif t == "delete_find":
            self._operate_find_with("d", change["cmd"], change["char"], n)
        elif t == "insert":
            self._replay_insert(change, n)
        elif t == "change_motion":
            self._handle_operator("d", change["motion"], change["key"], n, True)
            self._insert_text_at_cursor(change.get("text", ""))
        elif t == "change_textobj":
            rng = self._text_object_range(change["obj"], change["around"])
            if rng:
                self._operate_range("d", *rng)
            self._insert_text_at_cursor(change.get("text", ""))
        elif t == "change_find":
            self._operate_find_with("d", change["cmd"], change["char"], n)
            self._insert_text_at_cursor(change.get("text", ""))
        elif t == "change_eol":
            row, col = self.cursor_location
            self._operate_range(
                "d", (row, col), (row, len(self.document.get_line(row)))
            )
            self._insert_text_at_cursor(change.get("text", ""))
        elif t == "change_line":
            row, _ = self.cursor_location
            end_row = min(row + n - 1, self.document.line_count - 1)
            self.delete((row, 0), (end_row, len(self.document.get_line(end_row))))
            self.move_cursor((row, 0))
            self._insert_text_at_cursor(change.get("text", ""))

    def _replay_insert(self, change: dict, n: int) -> None:
        kind = change["kind"]
        text = change.get("text", "") * max(1, n)
        row, col = self.cursor_location
        line = self.document.get_line(row)
        if kind == "a":
            pos = (row, min(col + 1, len(line)))
        elif kind == "A":
            pos = (row, len(line))
        elif kind == "I":
            pos = (row, len(line) - len(line.lstrip()))
        elif kind == "o":
            self.insert("\n", (row, len(line)))
            pos = (row + 1, 0)
        elif kind == "O":
            self.insert("\n", (row, 0))
            pos = (row, 0)
        else:  # "i"
            pos = (row, col)
        if text:
            self.insert(text, pos, maintain_selection_offset=False)
            self.move_cursor(self._advance(pos, text))

    # ------------------------------------------------------------------
    # Inline find (f/F/t/T, ; ,)

    _FIND_FLIP = {"f": "F", "F": "f", "t": "T", "T": "t"}

    def _find_motion(
        self, cmd: str, char: str, n: int, repeat: bool = False
    ) -> tuple[int, int] | None:
        """Column of the n-th f/F/t/T match on the current line, or None."""
        row, col = self.cursor_location
        line = self.document.get_line(row)
        forward = cmd in ("f", "t")
        till = cmd in ("t", "T")
        idx = col
        # A repeated t/T must step over the adjacent target so ; advances.
        if repeat and till:
            idx = col + 1 if forward else col - 1
        for _ in range(n):
            idx = line.find(char, idx + 1) if forward else line.rfind(char, 0, idx)
            if idx == -1:
                return None
        if till:
            idx += -1 if forward else 1
        return (row, idx)

    def _operate_to_target_inclusive(
        self, op: str, target: tuple[int, int]
    ) -> None:
        start = self.cursor_location
        if target >= start:
            self._operate_range(op, start, (target[0], target[1] + 1))
        else:
            self._operate_range(op, target, start)

    def _resolve_find(self, op: str, cmd: str, char: str, n: int) -> None:
        target = self._find_motion(cmd, char, n)
        if target is None:
            return
        self._last_find = (cmd, char)
        if not op:
            self._move(target)
            return
        self._operate_to_target_inclusive(op, target)
        if op == "d":
            self._record(
                {"type": "delete_find", "cmd": cmd, "char": char, "n": n}
            )
        elif op == "c":
            self._begin_insert_change(
                {"type": "change_find", "cmd": cmd, "char": char, "n": n}
            )

    def _operate_find_with(self, op: str, cmd: str, char: str, n: int) -> None:
        target = self._find_motion(cmd, char, n)
        if target is not None:
            self._operate_to_target_inclusive(op, target)

    def _repeat_find(self, reverse: bool, n: int) -> None:
        if not self._last_find:
            return
        cmd, char = self._last_find
        if reverse:
            cmd = self._FIND_FLIP[cmd]
        target = self._find_motion(cmd, char, n, repeat=True)
        if target is not None:
            self._move(target)

    def _operate_find_repeat(self, op: str, reverse: bool, n: int) -> None:
        if not self._last_find:
            return
        cmd, char = self._last_find
        if reverse:
            cmd = self._FIND_FLIP[cmd]
        target = self._find_motion(cmd, char, n, repeat=True)
        if target is not None:
            self._operate_to_target_inclusive(op, target)

    # ------------------------------------------------------------------
    # Bracket match (%) and paragraph motion ({ })

    def _match_bracket(self) -> tuple[int, int] | None:
        row, col = self.cursor_location
        line = self.document.get_line(row)
        opens = {"(": ")", "[": "]", "{": "}"}
        closes = {v: k for k, v in opens.items()}
        i = col
        while i < len(line) and line[i] not in opens and line[i] not in closes:
            i += 1
        if i >= len(line):
            return None
        ch = line[i]
        if ch in opens:
            return self._scan_bracket_fwd(ch, opens[ch], row, i + 1)
        return self._scan_bracket_back(closes[ch], ch, row, i - 1)

    def _paragraph(self, forward: bool, n: int) -> tuple[int, int]:
        doc = self.document
        row = self.cursor_location[0]
        last = doc.line_count - 1

        def blank(r: int) -> bool:
            return doc.get_line(r).strip() == ""

        for _ in range(n):
            if forward:
                r = row + 1
                while r < last and not blank(r):
                    r += 1
                row = r
            else:
                r = row - 1
                while r > 0 and not blank(r):
                    r -= 1
                row = r
        return (row, 0)

    # ------------------------------------------------------------------
    # Word search (* #)

    @staticmethod
    def _is_word_char(ch: str) -> bool:
        return ch.isalnum() or ch == "_"

    def _word_under_cursor(self) -> str | None:
        row, col = self.cursor_location
        line = self.document.get_line(row)
        if col >= len(line):
            return None
        if not self._is_word_char(line[col]):
            j = col
            while j < len(line) and not self._is_word_char(line[j]):
                j += 1
            if j >= len(line):
                return None
            col = j
        start = col
        while start > 0 and self._is_word_char(line[start - 1]):
            start -= 1
        end = col
        while end < len(line) and self._is_word_char(line[end]):
            end += 1
        return line[start:end]

    def _search_word(self, reverse: bool) -> None:
        word = self._word_under_cursor()
        if not word:
            return
        self._search = word
        self._search_whole = True
        self.search_next(reverse=reverse)

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
        self._search_whole = False  # plain / search matches substrings
        self.search_next()

    def search_next(self, reverse: bool = False) -> None:
        if not self._search:
            return
        matches = self._search_matches()
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

    def _search_matches(self) -> list[tuple[int, int]]:
        pat = self._search
        plen = len(pat)
        matches: list[tuple[int, int]] = []
        for r in range(self.document.line_count):
            line = self.document.get_line(r)
            i = line.find(pat)
            while i >= 0:
                if not self._search_whole or self._is_whole_word(line, i, plen):
                    matches.append((r, i))
                i = line.find(pat, i + 1)
        return matches

    def _is_whole_word(self, line: str, i: int, plen: int) -> bool:
        left = i == 0 or not self._is_word_char(line[i - 1])
        right = i + plen >= len(line) or not self._is_word_char(line[i + plen])
        return left and right
