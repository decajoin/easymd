"""Search highlighting: all matches styled, the current one distinctly."""

from conftest import SIZE


def _search_names(editor) -> list[str]:
    names = []
    for line_highlights in editor._highlights.values():
        for _start, _end, name in line_highlights:
            if name in ("search", "search_current"):
                names.append(name)
    return names


async def _search(pilot, text: str) -> None:
    await pilot.press("slash")
    for ch in text:
        await pilot.press(ch)
    await pilot.press("enter")
    await pilot.pause()


async def test_all_matches_highlighted(make_app):
    app = make_app("foo bar\nfoo baz\nfoo qux\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await _search(pilot, "foo")
        names = _search_names(ed)
        assert len(names) == 3  # one per match
        assert names.count("search_current") == 1  # exactly one current
        assert ed._search_total == 3


async def test_current_follows_n(make_app):
    app = make_app("x foo\ny foo\nz foo\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await _search(pilot, "foo")
        first = ed.cursor_location
        assert ed._search_index >= 1
        await pilot.press("n")
        await pilot.pause()
        assert ed.cursor_location != first
        # still exactly one current match, on the new cursor position
        assert _search_names(ed).count("search_current") == 1


async def test_no_matches_no_highlight(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await _search(pilot, "zzz")
        assert _search_names(ed) == []
        assert ed._search_total == 0


async def test_noh_clears_highlight(make_app):
    app = make_app("foo foo\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await _search(pilot, "foo")
        assert _search_names(ed)
        await pilot.press("colon", "n", "o", "h", "enter")
        await pilot.pause()
        assert _search_names(ed) == []


async def test_highlights_survive_editing(make_app):
    app = make_app("foo\nfoo\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await _search(pilot, "foo")
        assert len(_search_names(ed)) == 2
        # Append another "foo" line; the highlight map is rebuilt on edit.
        await pilot.press("G", "o", "f", "o", "o", "escape")
        await pilot.pause()
        assert len(_search_names(ed)) == 3


async def test_star_highlights_word(make_app):
    app = make_app("alpha beta alpha\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("asterisk")  # search word under cursor
        await pilot.pause()
        names = _search_names(ed)
        assert len(names) == 2
        assert "search_current" in names
