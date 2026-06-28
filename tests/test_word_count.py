"""Word count shown in the status bar."""

from conftest import SIZE


async def test_word_count_value(make_app):
    # "hello" + "world" = 2 EN words; "你" + "好" = 2 CJK chars → total 4
    app = make_app("hello world 你好\n")
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert app._word_count() == 4


async def test_word_count_updates_after_edit(make_app):
    app = make_app("hello\n")
    async with app.run_test(size=SIZE) as pilot:
        before = app._word_count()
        await pilot.press("G", "o", "w", "o", "r", "l", "d", "escape")
        await pilot.pause()
        assert app._word_count() > before


async def test_word_count_cache_invalidated_on_edit(make_app):
    app = make_app("hi\n")
    async with app.run_test(size=SIZE) as pilot:
        _ = app._word_count()                      # populate cache
        assert app._word_count_cache is not None
        await pilot.press("o", "新", "escape")     # type a CJK char
        await pilot.pause()
        assert app._word_count_cache is not None   # rebuilt
        assert app._word_count() >= 2              # "hi" + "新"
