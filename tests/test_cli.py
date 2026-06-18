"""CLI surface: --help/--version and the `easymd config` subcommands."""

from typer.testing import CliRunner

import easymd.cli as cli
from easymd import __version__

runner = CliRunner()


def test_help_mentions_translation():
    result = runner.invoke(cli.run_app, ["--help"])
    assert result.exit_code == 0
    assert ":trans" in result.output
    assert "config set-key" in result.output


def test_version():
    result = runner.invoke(cli.run_app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_config_show_masks_key(monkeypatch, tmp_path):
    monkeypatch.setenv("EASYMD_CONFIG", str(tmp_path / "none.toml"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-abcd1234efgh")
    result = runner.invoke(cli.config_app, ["show"])
    assert result.exit_code == 0
    assert "sk-a" in result.output  # masked head, not the full key
    assert "efgh" in result.output
    assert "sk-abcd1234efgh" not in result.output


def test_config_set_key_writes_file(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    monkeypatch.setenv("EASYMD_CONFIG", str(cfg_file))
    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(lambda *a, **k: "sk-written"))
    result = runner.invoke(cli.config_app, ["set-key"])
    assert result.exit_code == 0
    assert cfg_file.is_file()
    assert "sk-written" in cfg_file.read_text(encoding="utf-8")


def test_config_set_model_writes_file(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.toml"
    monkeypatch.setenv("EASYMD_CONFIG", str(cfg_file))
    result = runner.invoke(cli.config_app, ["set-model", "deepseek-v4-pro"])
    assert result.exit_code == 0
    assert 'model = "deepseek-v4-pro"' in cfg_file.read_text(encoding="utf-8")
