# easymd

**English** · [中文](README.zh-CN.md)

A terminal Markdown editor: vim-style editing on the left, live preview on the
right. Built with [Textual](https://textual.textualize.io/).

## Install

Requires Python 3.10+. Install from PyPI with pip or [uv](https://docs.astral.sh/uv/):

```bash
pip install easymd-cli      # or: uv tool install easymd-cli
easymd notes.md             # created on the first :w if it does not exist
```

For one-key translation of the preview (see [Translation](#translation-deepseek)),
add the optional extra:

```bash
pip install 'easymd-cli[translate]'   # or: uv tool install 'easymd-cli[translate]'
```

From source:

```bash
git clone https://github.com/decajoin/easymd && cd easymd
uv sync --group dev
uv run easymd demo.md
uv run pytest            # run the tests
```

## Key reference

### Modes

| Key | Action |
| --- | --- |
| `i` `a` `A` `I` `o` `O` | Enter insert mode (same positions as vim) |
| `R` | Replace mode (overwrite continuously; backspace restores overwritten chars) |
| `Esc` | Back to normal mode |
| `v` | Visual mode (`y`/`d`/`c` act on the selection) |
| `V` | Visual line mode (whole-line selection; `v`/`V` switch between them) |

### Motions (normal/visual mode, count prefixes like `3j`)

`h j k l`, `w b e`, `0 ^ $`, `gg G` (`3G` jumps to line 3), `{ }` paragraphs,
`Ctrl+d/u` half-page, `Ctrl+f/b` full-page.

| Key | Action |
| --- | --- |
| `f` `F` `t` `T` + char | Inline find: to / back to / before / after; works with operators (`df,` `ct.`) |
| `;` / `,` | Repeat the last inline find (same / opposite direction) |
| `%` | Jump to the matching bracket (`( ) [ ] { }`, nested and multiline) |
| `*` / `#` | Search the word under the cursor (forward / backward, whole word), then `n`/`N` |

### Editing

| Key | Action |
| --- | --- |
| `x` | Delete the character under the cursor |
| `r` / `~` | Replace a character / toggle case (count supported) |
| `J` | Join the next line (`3J` joins three) |
| `dd` / `yy` / `cc` | Delete / yank / change whole lines (`3dd` etc.) |
| `D` / `C` / `Y` | Delete to end of line / change to end of line / yank line |
| `dw` `de` `d$` … | Operator + motion (`y`, `c` too; `cw` keeps trailing space, like vim) |
| `diw` `ci"` `ya(` … | Text objects: `i`/`a` + `w` `"` `'` `` ` `` `(` `[` `{`, with `d/c/y` or visual |
| `p` / `P` | Paste after / before |
| `.` | Repeat the last change (count override, e.g. `3.`) |
| `u` / `Ctrl+r` | Undo / redo |

### Commands and search

| Command | Action |
| --- | --- |
| `:w` `:w <file>` | Save |
| `:q` `:q!` `:wq` `:x` | Quit (`:q` refuses if there are unsaved changes) |
| `/text` then `n` / `N` | Search / next / previous (all matches highlighted, current one emphasized) |
| `:trans` | Toggle the preview between translation and original (see below) |
| `:summarize` (`:sum`) | Replace the preview with a whole-document summary (TL;DR) |
| `:transback` | Back to the original preview |
| `:refresh` | Regenerate the active AI preview (translation/summary; only changed parts) |
| `:toc` | Toggle the heading outline on the left; Enter jumps to a heading |
| `:noh` | Clear search highlights |

## Translation (DeepSeek)

With the `[translate]` extra installed, `:trans` translates the whole preview
(into Chinese by default) and caches it; `:trans` again switches back to the
original. The document is split into Markdown blocks and cached by content, so
after editing the status bar shows "translation out of date" and `:refresh`
re-translates only the changed blocks. Translation affects the preview only —
it is never written back to your file.

`:summarize` (alias `:sum`) reuses the same pipeline to produce a short TL;DR in
the same target language as translation. `:refresh` re-runs whichever AI view is
active.

Output streams in token by token, so it appears as it is produced. Results are
cached on disk under `~/.cache/easymd/translate/`, so re-translating the same
content costs nothing (set `EASYMD_CACHE_DIR=` empty to disable, or point it
elsewhere). In translation view the preview scrolls in step with the editor by
heading section; the summary view, being condensed, scrolls independently.

If the `[translate]` extra is missing or no API key is configured, `:trans` /
`:summarize` show a friendly notice in the status bar instead of crashing.

### Configuring the API key

Environment variable first, then the config file `~/.config/easymd/config.toml`:

```bash
export DEEPSEEK_API_KEY=sk-...        # recommended
# or write it to the config file interactively (mode 0600):
easymd config set-key
```

Config file example:

```toml
[deepseek]
api_key = "sk-..."          # or the DEEPSEEK_API_KEY env var (takes priority)
model = "deepseek-v4-flash" # or deepseek-v4-pro
target_lang = "中文"
```

Related: `easymd config show` (resolved config, key masked) and
`easymd config set-model deepseek-v4-pro`. You can also override at launch:
`easymd --pro notes.md`, `easymd --model <id> notes.md`,
`easymd --lang English notes.md`.

## Project layout

```
src/easymd/
  cli.py        # entry point (typer: easymd FILE / easymd config ...)
  app.py        # split layout, status bar, command line, preview sync, AI views
  editor.py     # vim modal layer (TextArea subclass)
  config.py     # read DeepSeek config (env > config.toml > defaults)
  translate.py  # chunking + content cache + DeepSeek client (optional dep)
tests/          # pytest suite (Textual Pilot drives real key presses headless)
```

Run the tests with `uv run pytest`.
