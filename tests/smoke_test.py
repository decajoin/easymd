"""Headless smoke test: drives the app with Textual's Pilot and asserts vim behavior."""

import asyncio
import tempfile
from pathlib import Path

from easymd.app import EasyMDApp

SAMPLE = "# Title\n\nhello world\nsecond line\n"


async def run() -> None:
    tmp = Path(tempfile.mkdtemp()) / "t.md"
    tmp.write_text(SAMPLE, encoding="utf-8")
    app = EasyMDApp(tmp)
    async with app.run_test(size=(120, 40)) as pilot:
        ed = app.editor
        assert ed.mode == "normal", ed.mode

        # Motions: j, gg, G, counts
        await pilot.press("j")
        assert ed.cursor_location[0] == 1
        await pilot.press("G")
        assert ed.cursor_location[0] == ed.document.line_count - 1
        await pilot.press("g", "g")
        assert ed.cursor_location == (0, 0)
        await pilot.press("3", "G")
        assert ed.cursor_location[0] == 2

        # Word motions on "hello world"
        await pilot.press("w")
        assert ed.cursor_location == (2, 6), ed.cursor_location
        await pilot.press("b")
        assert ed.cursor_location == (2, 0)
        await pilot.press("e")
        assert ed.cursor_location == (2, 4)
        await pilot.press("dollar_sign")
        assert ed.cursor_location == (2, len("hello world"))

        # Insert mode
        await pilot.press("g", "g", "i")
        assert ed.mode == "insert"
        await pilot.press("X", "Y")
        await pilot.press("escape")
        assert ed.mode == "normal"
        assert ed.text.startswith("XY# Title"), ed.text[:20]
        assert app.modified

        # dd deletes the first line, p pastes it back below
        await pilot.press("g", "g", "d", "d")
        assert ed.text.startswith("\nhello"), ed.text[:12]
        await pilot.press("p")
        assert ed.document.get_line(1) == "XY# Title", ed.document.get_line(1)

        # yy / p duplicates a line
        before = ed.document.line_count
        await pilot.press("y", "y", "p")
        assert ed.document.line_count == before + 1

        # x deletes a character
        await pilot.press("g", "g", "j", "0", "x")
        assert ed.document.get_line(1) == "Y# Title", ed.document.get_line(1)

        # Search via /
        await pilot.press("slash")
        for ch in "world":
            await pilot.press(ch)
        await pilot.press("enter")
        row, col = ed.cursor_location
        assert ed.document.get_line(row)[col : col + 5] == "world"

        # :w writes the file and clears the modified flag
        await pilot.press("colon", "w", "enter")
        await pilot.pause()
        assert tmp.read_text(encoding="utf-8") == ed.text
        assert not app.modified

        # :q with changes refuses; :q! quits
        await pilot.press("i", "z", "escape")
        await pilot.press("colon", "q", "enter")
        await pilot.pause()
        assert "E37" in app._notice, app._notice

        # Preview eventually picks up the edit
        await pilot.pause(0.5)

        await pilot.press("colon", "q", "exclamation_mark", "enter")
        await pilot.pause()

    print("smoke test passed")


if __name__ == "__main__":
    asyncio.run(run())
