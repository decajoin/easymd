"""Preview scrolling stays aligned with the editor via source-line anchors."""

from textual.containers import VerticalScroll
from textual.widgets import Markdown

SYNC_SIZE = (100, 30)


async def test_source_line_maps_to_block_position(make_app):
    # Headings, a code block and paragraphs: rendered height != source lines.
    text = (
        "# Title\n\n"
        "intro paragraph\n\n"
        "```python\nfor i in range(10):\n    print(i)\n```\n\n"
        + "\n\n".join(f"para {i}" for i in range(20))
        + "\n"
    )
    app = make_app(text)
    async with app.run_test(size=SYNC_SIZE) as pilot:
        await pilot.pause(0.5)
        md = app.query_one("#preview", Markdown)
        # Each block's start line must map to (approximately) its own position.
        for block in md.children:
            source_range = getattr(block, "source_range", None)
            if source_range is None:
                continue
            y = app._preview_y_for_line(source_range[0])
            assert abs(y - block.virtual_region.y) <= 1


async def test_preview_follows_editor_scroll(make_app):
    text = "\n\n".join(f"para {i}" for i in range(40)) + "\n"
    app = make_app(text)
    async with app.run_test(size=SYNC_SIZE) as pilot:
        await pilot.pause(0.5)
        ed = app.editor
        scroller = app.query_one("#preview-scroll", VerticalScroll)
        assert scroller.scroll_offset.y == 0  # nothing scrolled yet

        ed.move_cursor((78, 0))  # near the end forces the editor to scroll
        await pilot.pause(0.4)
        top = app._editor_top_line()
        assert top > 0  # the editor really scrolled

        expected = max(
            0, min(app._preview_y_for_line(top), scroller.max_scroll_y)
        )
        assert abs(scroller.scroll_offset.y - expected) <= 1


async def test_no_scroll_when_cursor_stays_in_view(make_app):
    text = "\n\n".join(f"para {i}" for i in range(40)) + "\n"
    app = make_app(text)
    async with app.run_test(size=SYNC_SIZE) as pilot:
        await pilot.pause(0.5)
        ed = app.editor
        scroller = app.query_one("#preview-scroll", VerticalScroll)
        # Move within the first viewport: the editor does not scroll, so the
        # preview must stay put rather than chase the cursor.
        ed.move_cursor((4, 0))
        await pilot.pause(0.3)
        assert scroller.scroll_offset.y == 0
