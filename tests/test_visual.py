"""Charwise (v) and linewise (V) visual modes."""

from conftest import SIZE


async def test_visual_yank(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("v", "e", "y")
        assert ed.mode == "normal"
        assert ed._register == ("hello", False)


async def test_visual_delete(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("v", "e", "d")
        assert ed.document.get_line(0) == " world"


async def test_visual_line_select_and_yank(make_app):
    app = make_app("aaa\nbbb\nccc\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("V")
        assert ed.mode == "visual_line"
        start, end = sorted([ed.selection.start, ed.selection.end])
        assert start == (0, 0) and end == (0, 3)
        await pilot.press("j", "y")
        assert ed.mode == "normal"
        assert ed._register == ("aaa\nbbb\n", True)


async def test_visual_line_delete(make_app):
    app = make_app("aaa\nbbb\nccc\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("V", "j", "d")
        assert ed.text == "ccc\n"
        assert ed._register[1] is True


async def test_visual_line_extends_upward(make_app):
    app = make_app("aaa\nbbb\nccc\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("2", "j", "V", "k")
        start, end = sorted([ed.selection.start, ed.selection.end])
        assert end[0] - start[0] == 1
        await pilot.press("escape")
        assert ed.mode == "normal"
        assert ed.selection.start == ed.selection.end


async def test_visual_mode_switching(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("V", "v")
        assert ed.mode == "visual"
        await pilot.press("V")
        assert ed.mode == "visual_line"
        await pilot.press("escape")
        assert ed.mode == "normal"
