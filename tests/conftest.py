"""Shared fixtures for easymd tests."""

import pytest

from easymd.app import EasyMDApp

SAMPLE = "# Title\n\nhello world\nsecond line\n"

SIZE = (100, 30)


@pytest.fixture
def make_app(tmp_path):
    """Factory: build an EasyMDApp around a temp markdown file."""

    def factory(text: str = SAMPLE) -> EasyMDApp:
        md = tmp_path / "t.md"
        md.write_text(text, encoding="utf-8")
        return EasyMDApp(md)

    return factory
