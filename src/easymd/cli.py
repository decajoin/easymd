"""Command-line entry point for easymd."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .app import EasyMDApp


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="easymd",
        description="Terminal Markdown editor with vim keys and live preview.",
    )
    parser.add_argument(
        "file",
        help="Markdown file to edit (created on first :w if it does not exist)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    args = parser.parse_args()
    EasyMDApp(Path(args.file)).run()


if __name__ == "__main__":
    main()
