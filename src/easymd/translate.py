"""Markdown-aware translation via the DeepSeek API.

The document is split into Markdown "chunks" (a heading and its body; fenced
code blocks stay intact) and each chunk is translated separately, which keeps
prompts small and lets unchanged chunks be served from a content-hash cache.

httpx is an optional dependency (the ``translate`` extra). When it is missing,
translate_document raises TranslateError with an install hint rather than
crashing the editor.
"""

from __future__ import annotations

import hashlib
import re
from typing import Callable

try:  # optional dependency: pip install easymd-cli[translate]
    import httpx
except ModuleNotFoundError:  # pragma: no cover - exercised via monkeypatch
    httpx = None

from .config import Config

EXTRAS_HINT = "翻译需要额外依赖：pip install easymd-cli[translate]"
NO_KEY_HINT = "未配置 DeepSeek API key（设 DEEPSEEK_API_KEY 或写入 config.toml）"

FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^#{1,6}\s")

# (translated_chunk, done_count, total_count)
ProgressCallback = Callable[[str, int, int], None]


class TranslateError(RuntimeError):
    """Raised when translation cannot proceed (missing extra, key, etc.)."""


def split_chunks(markdown: str) -> list[str]:
    """Split Markdown into translatable chunks at top-level heading boundaries.

    A fenced code block never starts a new chunk and is never split. Content
    before the first heading becomes its own leading chunk. Blank-only chunks
    are dropped.
    """
    chunks: list[str] = []
    current: list[str] = []
    in_fence = False

    def flush() -> None:
        block = "\n".join(current).strip("\n")
        if block.strip():
            chunks.append(block)

    for line in markdown.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            current.append(line)
            continue
        if not in_fence and HEADING_RE.match(line) and current:
            flush()
            current = [line]
        else:
            current.append(line)
    flush()
    return chunks


def _chunk_key(chunk: str) -> str:
    return hashlib.sha256(chunk.encode("utf-8")).hexdigest()


class Translator:
    """Translate Markdown via DeepSeek, caching chunks by content hash."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._cache: dict[str, str] = {}

    def _translate_system_prompt(self) -> str:
        lang = self.config.target_lang
        return (
            f"You are a Markdown translator. Translate the user's Markdown into "
            f"{lang}. Strictly preserve all Markdown syntax: headings, fenced "
            "code blocks (translate comments only, never the code), inline code, "
            "links, images, tables, lists and emphasis. Do not add explanations "
            "and do not wrap the result in code fences. Output only the "
            "translated Markdown."
        )

    def _summary_system_prompt(self) -> str:
        lang = self.config.target_lang
        return (
            f"You are a technical writer. Summarize the user's Markdown document "
            f"into a concise TL;DR written in {lang}. Produce a short Markdown "
            "summary — 3 to 6 bullet points, or a brief paragraph — capturing the "
            "key points and far shorter than the source. Output only the Markdown "
            "summary, with no preamble."
        )

    async def translate_document(
        self, text: str, on_chunk: ProgressCallback | None = None
    ) -> str:
        """Translate the whole document, chunk by chunk.

        Calls on_chunk(translated, done, total) after each chunk so the caller
        can render progressively. Raises TranslateError if the feature is not
        usable (missing extra or API key).
        """
        if httpx is None:
            raise TranslateError(EXTRAS_HINT)
        if not self.config.has_key:
            raise TranslateError(NO_KEY_HINT)

        chunks = split_chunks(text)
        total = len(chunks)
        out: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            translated = await self._translate_chunk(chunk)
            out.append(translated)
            if on_chunk is not None:
                on_chunk(translated, index, total)
        return "\n\n".join(out)

    async def summarize_document(
        self, text: str, on_chunk: ProgressCallback | None = None
    ) -> str:
        """Summarize the whole document into a short TL;DR (cached by content)."""
        if httpx is None:
            raise TranslateError(EXTRAS_HINT)
        if not self.config.has_key:
            raise TranslateError(NO_KEY_HINT)
        key = "sum:" + _chunk_key(text)
        cached = self._cache.get(key)
        if cached is None:
            cached = await self._post(self._summary_system_prompt(), text)
            self._cache[key] = cached
        if on_chunk is not None:
            on_chunk(cached, 1, 1)
        return cached

    async def _translate_chunk(self, chunk: str) -> str:
        key = _chunk_key(chunk)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        translated = await self._call_deepseek(chunk)
        self._cache[key] = translated
        return translated

    async def _call_deepseek(self, chunk: str) -> str:
        return await self._post(self._translate_system_prompt(), chunk)

    async def _post(self, system_prompt: str, user_text: str) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.0,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.config.base_url}/chat/completions"

        last_error = "unknown error"
        async with httpx.AsyncClient(timeout=60.0) as client:
            for _attempt in range(2):  # one retry
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                except httpx.HTTPError as exc:
                    last_error = str(exc)
                    continue
                if resp.status_code != 200:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    continue
                try:
                    return resp.json()["choices"][0]["message"]["content"].strip()
                except (KeyError, IndexError, ValueError) as exc:
                    last_error = f"bad response: {exc}"
                    break
        # A single failed call must not abort the whole document.
        return f"> [翻译失败] {last_error}\n\n{user_text}"
