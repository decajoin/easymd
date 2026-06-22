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
import json
import os
import re
from pathlib import Path
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
# Accumulated text so far during streaming.
DeltaCallback = Callable[[str], None]


def _default_cache_dir() -> Path | None:
    """Persistent cache location, or None if disabled (EASYMD_CACHE_DIR="")."""
    override = os.environ.get("EASYMD_CACHE_DIR")
    if override == "":
        return None
    base = override or os.environ.get("XDG_CACHE_HOME") or "~/.cache"
    return Path(base).expanduser() / "easymd" / "translate"


class TranslateError(RuntimeError):
    """Raised when translation cannot proceed (missing extra, key, etc.)."""


class _CallFailed(Exception):
    """A single API call failed; carries the text to show without caching."""

    def __init__(self, fallback: str) -> None:
        super().__init__(fallback)
        self.fallback = fallback


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


class Translator:
    """Translate Markdown via DeepSeek, caching chunks by content hash."""

    def __init__(self, config: Config, cache_dir: Path | None = ...) -> None:
        self.config = config
        self._cache: dict[str, str] = {}
        self._cache_dir = _default_cache_dir() if cache_dir is ... else cache_dir

    def _key(self, text: str) -> str:
        # The cache key folds in model and target language so switching either
        # (e.g. --lang English, --pro) does not return a stale result.
        base = f"{self.config.model}\x00{self.config.target_lang}\x00{text}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    # --- two-level cache (memory + optional disk) ---------------------------

    def _cache_get(self, key: str) -> str | None:
        if key in self._cache:
            return self._cache[key]
        disk = self._disk_read(key)
        if disk is not None:
            self._cache[key] = disk
        return disk

    def _cache_set(self, key: str, value: str) -> None:
        self._cache[key] = value
        self._disk_write(key, value)

    def _disk_path(self, key: str) -> Path | None:
        return self._cache_dir / f"{key}.md" if self._cache_dir else None

    def _disk_read(self, key: str) -> str | None:
        path = self._disk_path(key)
        if path is None or not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _disk_write(self, key: str, value: str) -> None:
        path = self._disk_path(key)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
        except OSError:
            pass

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
        self,
        text: str,
        on_chunk: ProgressCallback | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> str:
        """Translate the whole document, chunk by chunk.

        on_chunk(translated, done, total) fires after each chunk; on_delta gets
        the full text-so-far as tokens stream in. Raises TranslateError if the
        feature is unusable (missing extra or API key).
        """
        if httpx is None:
            raise TranslateError(EXTRAS_HINT)
        if not self.config.has_key:
            raise TranslateError(NO_KEY_HINT)

        chunks = split_chunks(text)
        total = len(chunks)
        done: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            translated = await self._translate_chunk(chunk, done, on_delta)
            done.append(translated)
            if on_chunk is not None:
                on_chunk(translated, index, total)
        return "\n\n".join(done)

    async def summarize_document(
        self,
        text: str,
        on_chunk: ProgressCallback | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> str:
        """Summarize the whole document into a short TL;DR (cached by content)."""
        if httpx is None:
            raise TranslateError(EXTRAS_HINT)
        if not self.config.has_key:
            raise TranslateError(NO_KEY_HINT)
        key = "sum:" + self._key(text)
        cached = self._cache_get(key)
        if cached is None:
            try:
                cached = await self._post(
                    self._summary_system_prompt(), text, on_delta=on_delta
                )
            except _CallFailed as exc:
                if on_chunk is not None:
                    on_chunk(exc.fallback, 1, 1)
                return exc.fallback  # show the failure, do not cache it
            self._cache_set(key, cached)
        if on_chunk is not None:
            on_chunk(cached, 1, 1)
        return cached

    async def _translate_chunk(
        self,
        chunk: str,
        done: list[str] | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> str:
        key = self._key(chunk)
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        delta_cb = None
        if on_delta is not None:
            prefix = done or []

            def delta_cb(partial: str) -> None:
                on_delta("\n\n".join([*prefix, partial]))

        try:
            translated = await self._post(
                self._translate_system_prompt(), chunk, on_delta=delta_cb
            )
        except _CallFailed as exc:
            return exc.fallback  # show the failure, do not cache it
        self._cache_set(key, translated)
        return translated

    async def _call_deepseek(self, chunk: str) -> str:
        try:
            return await self._post(self._translate_system_prompt(), chunk)
        except _CallFailed as exc:
            return exc.fallback

    async def _post(
        self,
        system_prompt: str,
        user_text: str,
        on_delta: DeltaCallback | None = None,
    ) -> str:
        if on_delta is not None:
            return await self._post_stream(system_prompt, user_text, on_delta)
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
        # Signal failure so the caller can show it without caching it.
        raise _CallFailed(f"> [翻译失败] {last_error}\n\n{user_text}")

    async def _post_stream(
        self, system_prompt: str, user_text: str, on_delta: DeltaCallback
    ) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.0,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.config.base_url}/chat/completions"
        acc = ""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST", url, json=payload, headers=headers
                ) as resp:
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode("utf-8", "replace")
                        raise _CallFailed(
                            f"> [翻译失败] HTTP {resp.status_code}: "
                            f"{body[:200]}\n\n{user_text}"
                        )
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            delta = json.loads(data)["choices"][0]["delta"]
                        except (KeyError, IndexError, ValueError):
                            continue
                        piece = delta.get("content") or ""
                        if piece:
                            acc += piece
                            on_delta(acc)
        except httpx.HTTPError as exc:
            # Partial output is incomplete; show it but do not cache it.
            raise _CallFailed(
                acc.strip() or f"> [翻译失败] {exc}\n\n{user_text}"
            ) from exc
        if not acc.strip():
            raise _CallFailed(f"> [翻译失败] empty response\n\n{user_text}")
        return acc.strip()
