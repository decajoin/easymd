"""v0.2.0 keys: r, J, ~, D, C, Y and the cw special case."""

from conftest import SIZE


async def test_r_replaces_char(make_app):
    app = make_app("hello\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("r", "X")
        assert ed.document.get_line(0) == "Xello"
        assert ed.cursor_location == (0, 0)
        assert ed.mode == "normal"


async def test_r_with_count(make_app):
    app = make_app("hello\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("3", "r", "z")
        assert ed.document.get_line(0) == "zzzlo"
        assert ed.cursor_location == (0, 2)


async def test_r_count_overruns_line_is_noop(make_app):
    app = make_app("hi\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("9", "r", "z")
        assert ed.document.get_line(0) == "hi"


async def test_replace_mode_overwrites(make_app):
    app = make_app("hello\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("R")
        assert ed.mode == "replace"
        await pilot.press("a", "b")
        assert ed.document.get_line(0) == "abllo"
        assert ed.cursor_location == (0, 2)
        await pilot.press("escape")
        assert ed.mode == "normal"
        assert ed.cursor_location == (0, 1)


async def test_replace_mode_appends_past_eol(make_app):
    app = make_app("hi\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("R", "x", "y", "z")
        assert ed.document.get_line(0) == "xyz"


async def test_replace_mode_backspace_restores(make_app):
    app = make_app("hello\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("R", "a", "b")
        assert ed.document.get_line(0) == "abllo"
        await pilot.press("backspace")
        assert ed.document.get_line(0) == "aello"
        assert ed.cursor_location == (0, 1)
        await pilot.press("backspace")
        assert ed.document.get_line(0) == "hello"
        assert ed.cursor_location == (0, 0)
        # Nothing left to restore: backspace just moves the cursor.
        await pilot.press("backspace")
        assert ed.document.get_line(0) == "hello"


async def test_replace_mode_backspace_removes_appended(make_app):
    app = make_app("hi\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("dollar_sign", "R", "x", "y")  # $ parks past 'i'
        assert ed.document.get_line(0) == "hixy"
        await pilot.press("backspace", "backspace")
        assert ed.document.get_line(0) == "hi"


async def test_replace_mode_enter_inserts_newline(make_app):
    app = make_app("ab\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("R", "x", "enter", "y")
        assert ed.document.get_line(0) == "x"
        # After the line break, typing keeps overwriting: y replaces b.
        assert ed.document.get_line(1) == "y"


async def test_join_lines(make_app):
    app = make_app("foo\n    bar\nbaz\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("J")
        assert ed.document.get_line(0) == "foo bar"
        assert ed.cursor_location == (0, 3)


async def test_join_with_count(make_app):
    app = make_app("a\nb\nc\nd\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("3", "J")  # 3J joins three lines (two joins)
        assert ed.document.get_line(0) == "a b c"


async def test_tilde_toggles_case(make_app):
    app = make_app("aBc\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("tilde")
        assert ed.document.get_line(0) == "ABc"
        assert ed.cursor_location == (0, 1)
        await pilot.press("g", "g", "3", "tilde")
        assert ed.document.get_line(0) == "abC"


async def test_shift_d_deletes_to_eol(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("w", "D")
        assert ed.document.get_line(0) == "hello "
        assert ed._register == ("world", False)
        assert ed.mode == "normal"


async def test_shift_c_changes_to_eol(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("w", "C")
        assert ed.document.get_line(0) == "hello "
        assert ed.mode == "insert"


async def test_shift_y_yanks_lines(make_app):
    app = make_app("aaa\nbbb\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("Y")
        assert ed._register == ("aaa\n", True)
        await pilot.press("2", "Y")
        assert ed._register == ("aaa\nbbb\n", True)
        await pilot.press("p")
        assert ed.document.line_count == 5


async def test_cw_behaves_like_ce(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("c", "w")
        # cw must not eat the space between the words.
        assert ed.document.get_line(0) == " world"
        assert ed.mode == "insert"
