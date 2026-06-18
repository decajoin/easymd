"""Translation preview state machine (PR1: placeholder translation, no network)."""

from textual.containers import VerticalScroll
from textual.widgets import Markdown

from conftest import SIZE


async def _command(pilot, name: str) -> None:
    """Type `:<name>` into the command line and submit it."""
    await pilot.press("colon")
    for ch in name:
        await pilot.press(ch)
    await pilot.press("enter")
    await pilot.pause()


async def test_trans_enters_translation_view(make_app):
    app = make_app("# Hello\n\nbody text\n")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert app._preview_mode == "original"
        await _command(pilot, "trans")
        assert app._preview_mode == "translated"
        assert app._translated_hash is not None
        # Placeholder translation echoes the source into the preview.
        assert app.query_one("#preview", Markdown).source == "# Hello\n\nbody text\n"


async def test_trans_toggles_back(make_app):
    app = make_app("# Hello\n")
    async with app.run_test(size=SIZE) as pilot:
        await _command(pilot, "trans")
        assert app._preview_mode == "translated"
        await _command(pilot, "trans")
        assert app._preview_mode == "original"


async def test_transback_returns_to_original(make_app):
    app = make_app("# Hello\n")
    async with app.run_test(size=SIZE) as pilot:
        await _command(pilot, "trans")
        await _command(pilot, "transback")
        assert app._preview_mode == "original"


async def test_editing_marks_translation_stale(make_app):
    app = make_app("# Hello\n\nbody\n")
    async with app.run_test(size=SIZE) as pilot:
        await _command(pilot, "trans")
        assert not app._translation_stale()
        await pilot.press("i", "X", "escape")  # edit the source
        await pilot.pause()
        assert app._translation_stale()
        await _command(pilot, "refresh")
        assert not app._translation_stale()


async def test_refresh_requires_translation_view(make_app):
    app = make_app("text\n")
    async with app.run_test(size=SIZE) as pilot:
        await _command(pilot, "refresh")
        assert "trans" in app._notice


async def test_scroll_sync_disabled_in_translation(make_app):
    text = "\n\n".join(f"para {i}" for i in range(40)) + "\n"
    app = make_app(text)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.4)
        scroller = app.query_one("#preview-scroll", VerticalScroll)
        await _command(pilot, "trans")
        await pilot.pause(0.3)
        before = scroller.scroll_offset.y
        app.editor.move_cursor((38, 0))  # scrolls the editor far down
        await pilot.pause(0.3)
        # The preview must not follow while in translation view.
        assert scroller.scroll_offset.y == before


async def test_original_mode_scroll_still_syncs(make_app):
    text = "\n\n".join(f"para {i}" for i in range(40)) + "\n"
    app = make_app(text)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.4)
        scroller = app.query_one("#preview-scroll", VerticalScroll)
        app.editor.move_cursor((38, 0))
        await pilot.pause(0.3)
        assert scroller.scroll_offset.y > 0  # original view still tracks
