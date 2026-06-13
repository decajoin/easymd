"""Command line (:) and search (/)."""

from conftest import SIZE


async def test_write_clears_modified(make_app, tmp_path):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("i", "z", "escape")
        assert app.modified
        await pilot.press("colon", "w", "enter")
        await pilot.pause()
        assert (tmp_path / "t.md").read_text(encoding="utf-8") == ed.text
        assert not app.modified


async def test_quit_refuses_unsaved(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("i", "z", "escape")
        await pilot.press("colon", "q", "enter")
        await pilot.pause()
        assert "E37" in app._notice


async def test_unknown_command_notice(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("colon", "z", "z", "enter")
        await pilot.pause()
        assert "E492" in app._notice


async def test_search_and_next(make_app):
    app = make_app("alpha\nbeta\nalpha\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("slash")
        for ch in "alpha":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        assert ed.cursor_location == (2, 0)  # next match after the cursor
        await pilot.press("n")
        assert ed.cursor_location == (0, 0)  # wraps around
        await pilot.press("N")
        assert ed.cursor_location == (2, 0)


async def test_cmdline_escape_cancels(make_app):
    app = make_app()
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("colon")
        await pilot.pause()
        cmdline = app.query_one("#cmdline")
        assert cmdline.display
        await pilot.press("escape")
        await pilot.pause()
        assert not cmdline.display
        assert app.focused is app.editor
