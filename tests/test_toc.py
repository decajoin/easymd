"""Table-of-contents panel: parsing, toggle, and jump-to-heading."""

from easymd.app import parse_headings
from conftest import SIZE

DOC = """# Title

intro

## Section A

body a

```python
# not a heading (inside a fence)
x = 1
```

## Section B

### Sub B1

deep
"""


def test_parse_headings_skips_code_fence():
    headings = parse_headings(DOC)
    titles = [t for _level, t, _line in headings]
    assert titles == ["Title", "Section A", "Section B", "Sub B1"]
    # the '# not a heading' line inside the fence is excluded
    assert all("not a heading" not in t for t in titles)


def test_parse_headings_levels_and_lines():
    headings = parse_headings(DOC)
    levels = [lvl for lvl, _t, _line in headings]
    assert levels == [1, 2, 2, 3]
    # "Sub B1" is on the line it appears at
    sub = next(h for h in headings if h[1] == "Sub B1")
    assert DOC.splitlines()[sub[2]].startswith("### Sub B1")


async def _command(pilot, name):
    await pilot.press("colon")
    for ch in name:
        await pilot.press(ch)
    await pilot.press("enter")
    await pilot.pause()


async def test_toc_toggle_visibility(make_app):
    app = make_app(DOC)
    async with app.run_test(size=SIZE) as pilot:
        panel = app.query_one("#toc")
        assert not panel.display
        await _command(pilot, "toc")
        assert panel.display
        assert panel.option_count == 4
        await _command(pilot, "toc")  # toggle off via command
        assert not panel.display


async def test_toc_jump_moves_cursor(make_app):
    app = make_app(DOC)
    async with app.run_test(size=SIZE) as pilot:
        await _command(pilot, "toc")
        # highlight the third heading ("Section B") and select it
        panel = app.query_one("#toc")
        panel.highlighted = 2
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        row, _col = app.editor.cursor_location
        assert app.editor.document.get_line(row).startswith("## Section B")
        assert not panel.display  # closes after jumping


async def test_toc_escape_closes(make_app):
    app = make_app(DOC)
    async with app.run_test(size=SIZE) as pilot:
        await _command(pilot, "toc")
        assert app.query_one("#toc").display
        await pilot.press("escape")
        await pilot.pause()
        assert not app.query_one("#toc").display


async def test_toc_no_headings(make_app):
    app = make_app("just text, no headings\n")
    async with app.run_test(size=SIZE) as pilot:
        await _command(pilot, "toc")
        panel = app.query_one("#toc")
        assert panel.display
        assert app._toc_lines == []
