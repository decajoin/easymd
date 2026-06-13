"""Cursor motions in normal mode."""

from conftest import SIZE


async def test_vertical_and_goto(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("j")
        assert ed.cursor_location[0] == 1
        await pilot.press("G")
        assert ed.cursor_location[0] == ed.document.line_count - 1
        await pilot.press("g", "g")
        assert ed.cursor_location == (0, 0)
        await pilot.press("3", "G")
        assert ed.cursor_location[0] == 2


async def test_word_and_line_motions(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("3", "G")  # "hello world"
        await pilot.press("w")
        assert ed.cursor_location == (2, 6)
        await pilot.press("b")
        assert ed.cursor_location == (2, 0)
        await pilot.press("e")
        assert ed.cursor_location == (2, 4)
        await pilot.press("dollar_sign")
        assert ed.cursor_location == (2, len("hello world"))
        await pilot.press("0")
        assert ed.cursor_location == (2, 0)


async def test_count_prefix(make_app):
    app = make_app("a\nb\nc\nd\ne\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("3", "j")
        assert ed.cursor_location[0] == 3
        await pilot.press("2", "k")
        assert ed.cursor_location[0] == 1
