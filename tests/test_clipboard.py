"""System clipboard via OSC 52 (ctrl+c / ctrl+v)."""

import easymd.editor as ed_mod
from conftest import SIZE
from textual.widgets.text_area import Selection


async def test_ctrl_c_copies_visual_selection(make_app, monkeypatch):
    captured = []
    monkeypatch.setattr(ed_mod, "_clipboard_set", lambda t: captured.append(t) or True)

    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("v", "e")       # visual mode, select to end of "hello"
        await pilot.press("ctrl+c")
        await pilot.pause()

    assert captured == ["hello"]


async def test_ctrl_c_copies_mouse_selection(make_app, monkeypatch):
    """Programmatically set selection simulates what a mouse drag produces."""
    captured = []
    monkeypatch.setattr(ed_mod, "_clipboard_set", lambda t: captured.append(t) or True)

    app = make_app("hello world\n")
    async with app.run_test(size=SIZE) as pilot:
        app.editor.selection = Selection((0, 6), (0, 11))  # "world"
        await pilot.press("ctrl+c")
        await pilot.pause()

    assert captured == ["world"]


async def test_ctrl_c_empty_selection_is_noop(make_app, monkeypatch):
    captured = []
    monkeypatch.setattr(ed_mod, "_clipboard_set", lambda t: captured.append(t) or True)

    app = make_app("hello\n")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("ctrl+c")       # normal mode, no selection
        await pilot.pause()

    assert captured == []


async def test_ctrl_c_does_not_quit(make_app, monkeypatch):
    monkeypatch.setattr(ed_mod, "_clipboard_set", lambda t: True)

    app = make_app("hi\n")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.is_running


async def test_ctrl_v_pastes_in_insert_mode(make_app, monkeypatch):
    monkeypatch.setattr(ed_mod, "_clipboard_get", lambda: "clipped")

    app = make_app("AB\n")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("a")            # insert after 'A'
        await pilot.press("ctrl+v")
        await pilot.press("escape")
        await pilot.pause()
        assert "Aclipped" in app.editor.text


async def test_ctrl_v_pastes_in_normal_mode(make_app, monkeypatch):
    monkeypatch.setattr(ed_mod, "_clipboard_get", lambda: "clipped")

    app = make_app("AB\n")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("ctrl+v")
        await pilot.pause()
        assert "clipped" in app.editor.text


async def test_ctrl_v_empty_clipboard_shows_notice(make_app, monkeypatch):
    monkeypatch.setattr(ed_mod, "_clipboard_get", lambda: "")

    app = make_app("hi\n")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.press("ctrl+v")
        await pilot.pause()
        assert app._notice
