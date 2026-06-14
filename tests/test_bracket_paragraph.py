"""Bracket match (%) and paragraph motion ({ })."""

from conftest import SIZE


async def test_percent_open_to_close(make_app):
    app = make_app("(abc)\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("percent_sign")
        assert ed.cursor_location == (0, 4)


async def test_percent_close_to_open(make_app):
    app = make_app("(abc)\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("4", "l")  # onto ')'
        await pilot.press("percent_sign")
        assert ed.cursor_location == (0, 0)


async def test_percent_scans_forward_to_bracket(make_app):
    app = make_app("ab(cd)ef\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("percent_sign")  # no bracket under cursor; scan right
        assert ed.cursor_location == (0, 5)


async def test_percent_nested(make_app):
    app = make_app("(a(b)c)\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("percent_sign")  # outer ( → outer )
        assert ed.cursor_location == (0, 6)


async def test_percent_multiline(make_app):
    app = make_app("foo(\nbar\n)baz\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("percent_sign")  # '(' on line 0 → ')' on line 2
        assert ed.cursor_location == (2, 0)


async def test_d_percent_deletes_inclusive(make_app):
    app = make_app("(abc)x\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("d", "percent_sign")
        assert ed.text == "x\n"


async def test_paragraph_forward(make_app):
    app = make_app("a\nb\n\nc\nd\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("right_curly_bracket")
        assert ed.cursor_location == (2, 0)  # the blank line


async def test_paragraph_backward(make_app):
    app = make_app("a\nb\n\nc\nd\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("3", "j")  # row 3 ("c")
        await pilot.press("left_curly_bracket")
        assert ed.cursor_location == (2, 0)


async def test_paragraph_count(make_app):
    app = make_app("a\n\nb\n\nc\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("2", "right_curly_bracket")  # skip two blank lines
        assert ed.cursor_location == (3, 0)


async def test_d_paragraph(make_app):
    app = make_app("a\nb\n\nc\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("d", "right_curly_bracket")
        assert ed.text == "\nc\n"
