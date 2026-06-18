"""Unit tests for the translation engine (no real network)."""

import pytest

import easymd.translate as translate
from easymd.config import Config
from easymd.translate import Translator, TranslateError, split_chunks


def _cfg(api_key="sk-test"):
    return Config(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        target_lang="中文",
    )


# --- chunking ---------------------------------------------------------------

def test_split_by_headings():
    md = "# A\n\nbody a\n\n# B\n\nbody b\n"
    chunks = split_chunks(md)
    assert len(chunks) == 2
    assert chunks[0].startswith("# A")
    assert "body a" in chunks[0]
    assert chunks[1].startswith("# B")


def test_leading_content_is_its_own_chunk():
    md = "intro line\n\n# Title\n\nbody\n"
    chunks = split_chunks(md)
    assert chunks[0] == "intro line"
    assert chunks[1].startswith("# Title")


def test_code_fence_is_not_split():
    md = "# T\n\n```python\n# this is a comment, not a heading\nx = 1\n```\n"
    chunks = split_chunks(md)
    # The '# ...' inside the fence must not start a new chunk.
    assert len(chunks) == 1
    assert "x = 1" in chunks[0]


def test_blank_document_yields_no_chunks():
    assert split_chunks("\n\n   \n") == []


# --- caching ----------------------------------------------------------------

async def test_identical_chunks_hit_cache(monkeypatch):
    tr = Translator(_cfg())
    calls = []

    async def fake_call(chunk):
        calls.append(chunk)
        return "T:" + chunk

    monkeypatch.setattr(tr, "_call_deepseek", fake_call)
    out = await tr.translate_document("# A\n\nx\n\n# A\n\nx\n")
    assert calls == ["# A\n\nx"]  # second identical chunk served from cache
    assert out.count("T:# A\n\nx") == 2


# --- DeepSeek client (httpx stubbed) ----------------------------------------

class _FakeResp:
    def __init__(self, status=200, content="你好", text="error body"):
        self.status_code = status
        self._content = content
        self.text = text

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        self.calls += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


async def test_call_parses_content(monkeypatch):
    tr = Translator(_cfg())
    client = _FakeClient([_FakeResp(200, "翻译结果")])
    monkeypatch.setattr(translate.httpx, "AsyncClient", lambda *a, **k: client)
    assert await tr._call_deepseek("hello") == "翻译结果"


async def test_call_retries_then_succeeds(monkeypatch):
    tr = Translator(_cfg())
    client = _FakeClient([_FakeResp(500, text="boom"), _FakeResp(200, "ok译")])
    monkeypatch.setattr(translate.httpx, "AsyncClient", lambda *a, **k: client)
    assert await tr._call_deepseek("hi") == "ok译"
    assert client.calls == 2


async def test_call_failure_falls_back_to_source(monkeypatch):
    tr = Translator(_cfg())
    client = _FakeClient([_FakeResp(500), _FakeResp(500)])
    monkeypatch.setattr(translate.httpx, "AsyncClient", lambda *a, **k: client)
    result = await tr._call_deepseek("original text")
    assert "[翻译失败]" in result
    assert "original text" in result  # source preserved so nothing is lost


# --- guards -----------------------------------------------------------------

async def test_missing_extras_raises(monkeypatch):
    monkeypatch.setattr(translate, "httpx", None)
    tr = Translator(_cfg())
    with pytest.raises(TranslateError) as exc:
        await tr.translate_document("# A\n")
    assert "pip install" in str(exc.value)


async def test_missing_key_raises():
    tr = Translator(_cfg(api_key=None))
    with pytest.raises(TranslateError):
        await tr.translate_document("# A\n")
