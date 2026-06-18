"""Command-line interface for easymd.

`easymd FILE` opens the editor. `easymd config ...` manages the DeepSeek
settings used by the in-editor :trans translation command.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt

from . import __version__
from .config import PRO_MODEL, config_path, load_config, save_config

run_app = typer.Typer(
    add_completion=False,
    rich_markup_mode="rich",
    help=(
        "Terminal Markdown editor: vim-style editing on the left, live preview "
        "on the right. Press [bold]:trans[/bold] inside the editor to translate "
        "the preview via DeepSeek.\n\n"
        "First time translating? Run [bold]easymd config set-key[/bold] or set "
        "[bold]DEEPSEEK_API_KEY[/bold]."
    ),
)
config_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
    help="Manage easymd configuration (~/.config/easymd/config.toml).",
)

console = Console()
err_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"easymd {__version__}")
        raise typer.Exit()


@run_app.command()
def run(
    file: str = typer.Argument(
        ..., help="Markdown file to edit (created on first :w if it does not exist)."
    ),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="DeepSeek model id to use for :trans."
    ),
    pro: bool = typer.Option(
        False, "--pro", help=f"Use the stronger model ({PRO_MODEL}) for :trans."
    ),
    lang: Optional[str] = typer.Option(
        None, "--lang", help="Target language for :trans (default 中文)."
    ),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Open FILE in the editor (left) with a live Markdown preview (right).

    Inside the editor, [bold]:trans[/bold] translates the preview via DeepSeek
    and [bold]:trans[/bold] again toggles back; [bold]:refresh[/bold] re-runs it.
    Configure the API key with [bold]easymd config set-key[/bold] or the
    [bold]DEEPSEEK_API_KEY[/bold] environment variable.
    """
    from .app import EasyMDApp  # deferred: keep --help/-version snappy

    cfg = load_config()
    if model:
        cfg.model = model
    elif pro:
        cfg.model = PRO_MODEL
    if lang:
        cfg.target_lang = lang
    EasyMDApp(Path(file), config=cfg).run()


@config_app.command("set-key")
def config_set_key(
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Also set the default model."
    ),
) -> None:
    """Store your DeepSeek API key in the config file (mode 0600)."""
    key = Prompt.ask("DeepSeek API key", password=True).strip()
    if not key:
        err_console.print("[yellow]No key entered, nothing changed.[/yellow]")
        raise typer.Exit(code=1)
    path = save_config({"api_key": key, "model": model})
    console.print(f"[green]Saved[/green] to {path}")


@config_app.command("set-model")
def config_set_model(
    model: str = typer.Argument(..., help="Model id, e.g. deepseek-v4-pro."),
) -> None:
    """Set the default model in the config file."""
    path = save_config({"model": model})
    console.print(f"[green]Saved[/green] model = {model}  ({path})")


@config_app.command("show")
def config_show() -> None:
    """Show the resolved configuration (the API key is masked)."""
    cfg = load_config()
    masked = "—"
    if cfg.api_key:
        key = cfg.api_key
        masked = f"{key[:4]}…{key[-4:]}" if len(key) > 8 else "set"
    console.print(f"config file : {config_path()}")
    console.print(f"api_key     : {masked}")
    console.print(f"base_url    : {cfg.base_url}")
    console.print(f"model       : {cfg.model}")
    console.print(f"target_lang : {cfg.target_lang}")


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "config":
        config_app(args=argv[1:], prog_name="easymd config")
    else:
        run_app(args=argv, prog_name="easymd")


if __name__ == "__main__":  # pragma: no cover
    main()
