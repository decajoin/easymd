"""Configuration for easymd (currently the DeepSeek translation feature).

Resolution order for every setting:
  1. Environment variable
  2. Config file (~/.config/easymd/config.toml or $EASYMD_CONFIG)
  3. Built-in default

The config file may use a [deepseek] table or flat top-level keys:

    [deepseek]
    api_key = "sk-..."        # prefer the DEEPSEEK_API_KEY env var instead
    model = "deepseek-v4-flash"
    target_lang = "中文"
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for 3.10
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None  # file config disabled; env vars still work

DEFAULT_BASE_URL = "https://api.deepseek.com"
# DeepSeek v4 generation: -flash is the cheap/fast tier, -pro the stronger one.
FLASH_MODEL = "deepseek-v4-flash"
PRO_MODEL = "deepseek-v4-pro"
DEFAULT_MODEL = FLASH_MODEL
DEFAULT_TARGET_LANG = "中文"

# Keys we own in the config file and may (re)write via `easymd config`.
WRITABLE_KEYS = ("api_key", "base_url", "model", "target_lang")


def config_path() -> Path:
    override = os.environ.get("EASYMD_CONFIG")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    return Path(base).expanduser() / "easymd" / "config.toml"


def _load_file() -> dict:
    path = config_path()
    if not path.is_file() or tomllib is None:
        return {}
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, ValueError):
        return {}
    # Accept both a [deepseek] table and flat top-level keys.
    section = data.get("deepseek", {})
    return {**data, **section}


@dataclass
class Config:
    api_key: str | None
    base_url: str
    model: str
    target_lang: str

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


def load_config() -> Config:
    file_cfg = _load_file()
    api_key = os.environ.get("DEEPSEEK_API_KEY") or file_cfg.get("api_key")
    base_url = (
        os.environ.get("DEEPSEEK_BASE_URL")
        or file_cfg.get("base_url")
        or DEFAULT_BASE_URL
    )
    model = (
        os.environ.get("DEEPSEEK_MODEL") or file_cfg.get("model") or DEFAULT_MODEL
    )
    target_lang = (
        os.environ.get("EASYMD_TARGET_LANG")
        or file_cfg.get("target_lang")
        or DEFAULT_TARGET_LANG
    )
    return Config(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        model=model,
        target_lang=target_lang,
    )


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def save_config(updates: dict) -> Path:
    """Merge `updates` into the config file and write it back (mode 0600).

    Only WRITABLE_KEYS are persisted; None values are ignored. The file is
    written as flat top-level keys, which the loader also accepts.
    """
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    current = {k: v for k, v in _load_file().items() if k in WRITABLE_KEYS}
    for key, value in updates.items():
        if key in WRITABLE_KEYS and value is not None:
            current[key] = value

    lines = ["# easymd configuration\n"]
    for key in WRITABLE_KEYS:
        value = current.get(key)
        if value:
            lines.append(f'{key} = "{_toml_escape(str(value))}"\n')
    path.write_text("".join(lines), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path
