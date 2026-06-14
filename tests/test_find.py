"""Inline find: f/F/t/T and the ; , repeats, standalone and with operators."""

from conftest import SIZE


async def test_f_finds_forward(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("f", "o")
        assert ed.cursor_location == (0, 4)


async def test_f_missing_char_is_noop(make_app):
    app = make_app("hello\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("f", "z")
        assert ed.cursor_location == (0, 0)


async def test_semicolon_and_comma_repeat(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("f", "o")
        assert ed.cursor_location == (0, 4)
        await pilot.press("semicolon")  # next 'o'
        assert ed.cursor_location == (0, 7)
        await pilot.press("comma")  # back to previous 'o'
        assert ed.cursor_location == (0, 4)


async def test_F_finds_backward(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("dollar_sign")  # col 11 (one past end)
        await pilot.press("F", "o")
        assert ed.cursor_location == (0, 7)


async def test_t_till_forward(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("t", "o")
        assert ed.cursor_location == (0, 3)


async def test_t_semicolon_advances(make_app):
    app = make_app("a.b.c.d\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("t", "full_stop")
        assert ed.cursor_location == (0, 0)  # till first '.'
        await pilot.press("semicolon")  # must not get stuck
        assert ed.cursor_location == (0, 2)


async def test_T_till_backward(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("dollar_sign")
        await pilot.press("T", "o")
        assert ed.cursor_location == (0, 8)  # just after last 'o'


async def test_count_with_find(make_app):
    app = make_app("a.b.c.d.e\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("3", "f", "full_stop")
        assert ed.cursor_location == (0, 5)  # third '.'


async def test_df_deletes_through_char(make_app):
    app = make_app("hello, world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("d", "f", "comma")
        assert ed.text == " world\n"


async def test_dt_deletes_up_to_char(make_app):
    app = make_app("hello, world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("d", "t", "comma")
        assert ed.text == ", world\n"


async def test_ct_changes_and_inserts(make_app):
    app = make_app("hello, world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("c", "t", "comma")
        assert ed.mode == "insert"
        await pilot.press("X")
        await pilot.press("escape")
        assert ed.text == "X, world\n"


async def test_dF_deletes_backward(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("dollar_sign")  # col 11 (one past end)
        await pilot.press("d", "F", "w")
        # deletes from 'w' (incl) up to the cursor column → "hello "
        assert ed.text == "hello \n"


async def test_find_in_visual_extends(make_app):
    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        ed = app.editor
        await pilot.press("v", "f", "o", "d")
        # visual to first 'o' (incl), delete → " world"
        assert ed.text == " world\n"
