"""Dot-repeat (.) replays the last buffer-modifying change."""

from conftest import SIZE


async def test_dot_repeats_x(make_app):
    app = make_app("abcdef\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("x")
        await pilot.press("full_stop")
        assert ed.text == "cdef\n"


async def test_dot_count_override(make_app):
    app = make_app("abcdef\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("x")
        await pilot.press("3", "full_stop")
        assert ed.text == "ef\n"


async def test_dot_repeats_dw(make_app):
    app = make_app("one two three\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("d", "w")
        assert ed.text == "two three\n"
        await pilot.press("full_stop")
        assert ed.text == "three\n"


async def test_dot_repeats_dd(make_app):
    app = make_app("a\nb\nc\nd\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("d", "d")
        await pilot.press("full_stop")
        assert ed.text == "c\nd\n"


async def test_dot_repeats_insert(make_app):
    app = make_app("X\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("i", "a", "b", "escape")
        assert ed.text == "abX\n"
        await pilot.press("full_stop")
        assert ed.text == "aabbX\n"


async def test_dot_repeats_o(make_app):
    app = make_app("top\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("o", "n", "e", "w", "escape")
        assert ed.text == "top\nnew\n"
        await pilot.press("full_stop")
        assert ed.document.line_count == 4
        assert ed.document.get_line(2) == "new"


async def test_dot_repeats_cw(make_app):
    app = make_app("foo bar\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("c", "w", "X", "escape")
        assert ed.text == "X bar\n"
        await pilot.press("w")  # onto "bar"
        await pilot.press("full_stop")
        assert ed.text == "X X\n"


async def test_dot_repeats_ciw(make_app):
    app = make_app("foo bar baz\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("w")  # onto "bar"
        await pilot.press("c", "i", "w", "X", "escape")
        assert ed.text == "foo X baz\n"
        await pilot.press("w")  # onto "baz"
        await pilot.press("full_stop")
        assert ed.text == "foo X X\n"


async def test_dot_repeats_df(make_app):
    app = make_app("a,b,c,d\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("d", "f", "comma")
        assert ed.text == "b,c,d\n"
        await pilot.press("full_stop")
        assert ed.text == "c,d\n"


async def test_dot_repeats_tilde(make_app):
    app = make_app("abc\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("tilde")
        assert ed.document.get_line(0) == "Abc"
        await pilot.press("full_stop")
        assert ed.document.get_line(0) == "ABc"


async def test_dot_repeats_replace(make_app):
    app = make_app("aaaa\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("r", "x")
        assert ed.document.get_line(0) == "xaaa"
        await pilot.press("l", "full_stop")
        assert ed.document.get_line(0) == "xxaa"


async def test_dot_repeats_paste(make_app):
    app = make_app("ab\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("y", "y", "p")
        assert ed.document.line_count == 3
        await pilot.press("full_stop")
        assert ed.document.line_count == 4


async def test_dot_repeats_change_to_eol(make_app):
    app = make_app("hello world\nfoo bar\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("C", "X", "escape")
        assert ed.document.get_line(0) == "X"
        await pilot.press("j", "0", "full_stop")
        assert ed.document.get_line(1) == "X"
