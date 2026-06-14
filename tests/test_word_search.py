"""Word search under cursor: * and #."""

from conftest import SIZE


async def test_star_jumps_to_next_occurrence(make_app):
    app = make_app("foo bar foo baz\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("asterisk")
        assert ed.cursor_location == (0, 8)


async def test_star_wraps_around(make_app):
    app = make_app("foo bar foo\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("2", "w")  # second "foo" at col 8
        assert ed.cursor_location == (0, 8)
        await pilot.press("asterisk")  # only earlier match → wraps to col 0
        assert ed.cursor_location == (0, 0)


async def test_hash_searches_backward(make_app):
    app = make_app("foo bar foo\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("2", "w")  # on second "foo"
        await pilot.press("number_sign")
        assert ed.cursor_location == (0, 0)


async def test_star_matches_whole_word_only(make_app):
    app = make_app("foo foobar foo\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("asterisk")  # must skip "foobar"
        assert ed.cursor_location == (0, 11)


async def test_star_then_n_continues(make_app):
    app = make_app("x foo y foo z foo\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("w")  # first "foo" at col 2
        assert ed.cursor_location == (0, 2)
        await pilot.press("asterisk")  # next foo at col 8
        assert ed.cursor_location == (0, 8)
        await pilot.press("n")  # next foo at col 14
        assert ed.cursor_location == (0, 14)


async def test_star_skips_when_not_on_word(make_app):
    app = make_app("foo === foo\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("4", "l")  # onto the '=' run
        await pilot.press("asterisk")  # uses next word "foo"
        assert ed.cursor_location == (0, 8)
