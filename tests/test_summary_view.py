"""Summary preview (:summarize), sharing the AI-view machinery with :trans."""

import easymd.translate as translate
from textual.widgets import Markdown

from conftest import SIZE
from test_translate_view import FakeTranslator, _command


async def test_summarize_enters_summary_view(make_app):
    app = make_app("# Title\n\nlots of body text here\n")
    async with app.run_test(size=SIZE) as pilot:
        app._translator = FakeTranslator()
        await _command(pilot, "summarize")
        await pilot.pause(0.1)
        assert app._preview_mode == "summary"
        assert app._summary_md.startswith("TL;DR:")
        assert app._summary_hash is not None
        assert app.query_one("#preview", Markdown).source.startswith("TL;DR:")


async def test_sum_alias_toggles_back(make_app):
    app = make_app("# Title\n")
    async with app.run_test(size=SIZE) as pilot:
        app._translator = FakeTranslator()
        await _command(pilot, "sum")
        await pilot.pause(0.1)
        assert app._preview_mode == "summary"
        await _command(pilot, "sum")  # toggle off
        assert app._preview_mode == "original"


async def test_switch_between_translation_and_summary(make_app):
    app = make_app("# Title\n\nbody\n")
    async with app.run_test(size=SIZE) as pilot:
        app._translator = FakeTranslator()
        await _command(pilot, "trans")
        await pilot.pause(0.1)
        assert app._preview_mode == "translated"
        await _command(pilot, "summarize")  # switch straight to summary
        await pilot.pause(0.1)
        assert app._preview_mode == "summary"
        assert app._summary_md.startswith("TL;DR:")


async def test_summary_refresh_after_edit(make_app):
    app = make_app("# Title\n\nbody\n")
    async with app.run_test(size=SIZE) as pilot:
        app._translator = FakeTranslator()
        await _command(pilot, "summarize")
        await pilot.pause(0.1)
        assert not app._view_stale()
        await pilot.press("i", "X", "escape")
        await pilot.pause()
        assert app._view_stale()  # summary now out of date
        await _command(pilot, "refresh")  # :refresh re-summarizes
        await pilot.pause(0.1)
        assert not app._view_stale()


async def test_summary_missing_extras_reverts(make_app, monkeypatch):
    monkeypatch.setattr(translate, "httpx", None)
    app = make_app("# Title\n")
    async with app.run_test(size=SIZE) as pilot:
        await _command(pilot, "summarize")  # real translator, no httpx
        await pilot.pause(0.1)
        assert app._preview_mode == "original"
        assert "pip install" in app._notice
