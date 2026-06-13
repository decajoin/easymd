"""Text objects: iw/aw, quotes, brackets, with d/c/y and visual mode."""

from conftest import SIZE


async def test_diw_inner_word(make_app):
    app = make_app("foo bar baz\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("w", "l")  # land inside "bar"
        await pilot.press("d", "i", "w")
        assert ed.document.get_line(0) == "foo  baz"
        assert ed._register == ("bar", False)


async def test_daw_takes_trailing_space(make_app):
    app = make_app("foo bar baz\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("w", "d", "a", "w")
        assert ed.document.get_line(0) == "foo baz"


async def test_diw_on_whitespace(make_app):
    app = make_app("foo   bar\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("3", "l")  # onto the whitespace run
        await pilot.press("d", "i", "w")
        assert ed.document.get_line(0) == "foobar"


async def test_ciw_enters_insert(make_app):
    app = make_app("foo bar\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("c", "i", "w")
        assert ed.document.get_line(0) == " bar"
        assert ed.mode == "insert"


async def test_ci_quote(make_app):
    app = make_app('say "hello world" end\n')
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("w", "w", "c", "i", "quotation_mark")
        assert ed.document.get_line(0) == 'say "" end'
        assert ed.mode == "insert"
        assert ed._register == ("hello world", False)


async def test_da_quote_from_before_pair(make_app):
    app = make_app('say "hi" end\n')
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        # Cursor at column 0, before the pair: vim picks the next pair.
        await pilot.press("d", "a", "quotation_mark")
        assert ed.document.get_line(0) == "say  end"


async def test_yi_paren(make_app):
    app = make_app("f(a, b) x\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("2", "l")  # onto "a"
        await pilot.press("y", "i", "left_parenthesis")
        assert ed._register == ("a, b", False)
        assert ed.cursor_location == (0, 2)


async def test_da_paren_multiline(make_app):
    app = make_app("if (foo\n  and bar) baz\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("dollar_sign", "h")  # inside the parens
        await pilot.press("d", "a", "left_parenthesis")
        assert ed.text == "if  baz\n"


async def test_di_paren_on_closing_bracket(make_app):
    app = make_app("(inner) out\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("6", "l")  # on ")"
        await pilot.press("d", "i", "right_parenthesis")
        assert ed.document.get_line(0) == "() out"


async def test_di_backtick(make_app):
    app = make_app("run `code here` now\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("w", "l", "l")
        await pilot.press("d", "i", "grave_accent")
        assert ed.document.get_line(0) == "run `` now"


async def test_visual_inner_paren_then_delete(make_app):
    app = make_app("f(a, b) x\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("2", "l")
        await pilot.press("v", "i", "left_parenthesis")
        assert ed.mode == "visual"
        await pilot.press("d")
        assert ed.document.get_line(0) == "f() x"


async def test_visual_a_word_then_yank(make_app):
    app = make_app("foo bar baz\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("w")
        await pilot.press("v", "a", "w", "y")
        assert ed._register == ("bar ", False)
        assert ed.mode == "normal"


async def test_unknown_object_is_noop(make_app):
    app = make_app("foo bar\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("d", "i", "z")
        assert ed.document.get_line(0) == "foo bar"
        assert ed.mode == "normal"
