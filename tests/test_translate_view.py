"""Translation preview state machine (worker-driven, translator stubbed)."""

import easymd.translate as translate
from textual.containers import VerticalScroll
from textual.widgets import Markdown

from conftest import SIZE


class FakeTranslator:
    """Stand-in translator: prefixes the source so output is distinguishable."""

    def __init__(self, prefix="[ZH] "):
        self.prefix = prefix
        self.calls = 0

    async def translate_document(self, text, on_chunk=None):
        self.calls += 1
        result = self.prefix + text
        if on_chunk is not None:
            on_chunk(result, 1, 1)
        return result


async def _command(pilot, name: str) -> None:
    await pilot.press("colon")
    for ch in name:
        await pilot.press(ch)
    await pilot.press("enter")
    await pilot.pause()


async def test_trans_translates_via_worker(make_app):
    app = make_app("# Hello\n\nbody\n")
    async with app.run_test(size=SIZE) as pilot:
        app._translator = FakeTranslator()
        await _command(pilot, "trans")
        await pilot.pause(0.1)  # let the worker finish
        assert app._preview_mode == "translated"
        assert app._translated_md.startswith("[ZH] ")
        assert "Hello" in app._translated_md
        assert app._translated_hash is not None
        assert not app._translation_stale()


async def test_trans_toggles_back(make_app):
    app = make_app("# Hello\n")
    async with app.run_test(size=SIZE) as pilot:
        app._translator = FakeTranslator()
        await _command(pilot, "trans")
        await pilot.pause(0.1)
        assert app._preview_mode == "translated"
        await _command(pilot, "trans")  # toggle off
        assert app._preview_mode == "original"


async def test_cached_translation_switches_without_recall(make_app):
    app = make_app("# Hello\n")
    async with app.run_test(size=SIZE) as pilot:
        fake = FakeTranslator()
        app._translator = fake
        await _command(pilot, "trans")
        await pilot.pause(0.1)
        await _command(pilot, "trans")  # back to original
        await _command(pilot, "trans")  # in again; doc unchanged → cache hit
        await pilot.pause(0.1)
        assert fake.calls == 1  # not re-translated


async def test_editing_marks_stale_then_refresh(make_app):
    app = make_app("# Hi\n\nbody\n")
    async with app.run_test(size=SIZE) as pilot:
        app._translator = FakeTranslator()
        await _command(pilot, "trans")
        await pilot.pause(0.1)
        assert not app._translation_stale()
        await pilot.press("i", "X", "escape")  # edit the source
        await pilot.pause()
        assert app._translation_stale()
        await _command(pilot, "refresh")
        await pilot.pause(0.1)
        assert not app._translation_stale()


async def test_refresh_requires_translation_view(make_app):
    app = make_app("text\n")
    async with app.run_test(size=SIZE) as pilot:
        await _command(pilot, "refresh")
        assert "trans" in app._notice


async def test_missing_extras_reverts_with_notice(make_app, monkeypatch):
    monkeypatch.setattr(translate, "httpx", None)
    app = make_app("# Hi\n")
    async with app.run_test(size=SIZE) as pilot:
        await _command(pilot, "trans")  # real translator, httpx unavailable
        await pilot.pause(0.1)
        assert app._preview_mode == "original"  # reverted, no crash
        assert "pip install" in app._notice


async def test_missing_key_reverts_with_notice(make_app, monkeypatch, tmp_path):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("EASYMD_CONFIG", str(tmp_path / "none.toml"))
    app = make_app("# Hi\n")
    async with app.run_test(size=SIZE) as pilot:
        await _command(pilot, "trans")
        await pilot.pause(0.1)
        assert app._preview_mode == "original"
        assert "key" in app._notice.lower()


async def test_scroll_sync_disabled_in_translation(make_app):
    text = "\n\n".join(f"para {i}" for i in range(40)) + "\n"
    app = make_app(text)
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause(0.3)
        app._translator = FakeTranslator()
        scroller = app.query_one("#preview-scroll", VerticalScroll)
        await _command(pilot, "trans")
        await pilot.pause(0.1)
        before = scroller.scroll_offset.y
        app.editor.move_cursor((38, 0))  # scrolls the editor
        await pilot.pause(0.3)
        assert scroller.scroll_offset.y == before  # preview did not follow


async def test_preview_shows_translation_markdown(make_app):
    app = make_app("# Hello\n")
    async with app.run_test(size=SIZE) as pilot:
        app._translator = FakeTranslator(prefix="译文：")
        await _command(pilot, "trans")
        await pilot.pause(0.2)
        assert app.query_one("#preview", Markdown).source.startswith("译文：")
