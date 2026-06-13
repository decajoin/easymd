"""Insert mode, delete/yank/paste and undo plumbing."""

from conftest import SIZE


async def test_insert_and_escape(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("i")
        assert ed.mode == "insert"
        await pilot.press("X", "Y")
        await pilot.press("escape")
        assert ed.mode == "normal"
        assert ed.text.startswith("XY# Title")
        assert app.modified


async def test_delete_line_and_paste(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("d", "d")
        assert not ed.text.startswith("# Title")
        await pilot.press("p")
        assert ed.document.get_line(1) == "# Title"


async def test_yank_line_count_paste(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        before = ed.document.line_count
        await pilot.press("y", "y", "p")
        assert ed.document.line_count == before + 1
        assert ed.document.get_line(1) == "# Title"


async def test_x_deletes_chars(make_app):
    app = make_app("abcdef\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("x")
        assert ed.document.get_line(0) == "bcdef"
        await pilot.press("2", "x")
        assert ed.document.get_line(0) == "def"


async def test_open_lines(make_app):
    app = make_app("one\ntwo\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("o")
        assert ed.mode == "insert"
        assert ed.cursor_location == (1, 0)
        await pilot.press("escape", "g", "g", "O")
        assert ed.cursor_location == (0, 0)
        assert ed.document.line_count == 5


async def test_operator_with_motion(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("d", "w")
        assert ed.document.get_line(0) == "world"
        await pilot.press("u")
        assert ed.document.get_line(0) == "hello world"
