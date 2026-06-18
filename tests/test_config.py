"""Config resolution: env > file > default."""

import pytest

import easymd.config as config


def _clear_env(monkeypatch):
    for var in (
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_BASE_URL",
        "EASYMD_TARGET_LANG",
    ):
        monkeypatch.delenv(var, raising=False)


def test_defaults(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setenv("EASYMD_CONFIG", str(tmp_path / "missing.toml"))
    cfg = config.load_config()
    assert cfg.api_key is None
    assert not cfg.has_key
    assert cfg.model == "deepseek-v4-flash"
    assert cfg.base_url == "https://api.deepseek.com"
    assert cfg.target_lang == "中文"


def test_env_override(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setenv("EASYMD_CONFIG", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    cfg = config.load_config()
    assert cfg.api_key == "sk-env"
    assert cfg.has_key
    assert cfg.model == "deepseek-v4-pro"


def test_base_url_trailing_slash_stripped(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setenv("EASYMD_CONFIG", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.com/")
    assert config.load_config().base_url == "https://example.com"


@pytest.mark.skipif(config.tomllib is None, reason="no TOML reader available")
def test_file_load(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        '[deepseek]\n'
        'api_key = "sk-file"\n'
        'model = "deepseek-v4-pro"\n'
        'target_lang = "日本語"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("EASYMD_CONFIG", str(cfg_file))
    cfg = config.load_config()
    assert cfg.api_key == "sk-file"
    assert cfg.model == "deepseek-v4-pro"
    assert cfg.target_lang == "日本語"


@pytest.mark.skipif(config.tomllib is None, reason="no TOML reader available")
def test_env_beats_file(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[deepseek]\napi_key = "sk-file"\n', encoding="utf-8")
    monkeypatch.setenv("EASYMD_CONFIG", str(cfg_file))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    assert config.load_config().api_key == "sk-env"
