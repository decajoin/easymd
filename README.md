# easymd

终端里的 Markdown 编辑器：左侧 vim 式编辑，右侧实时预览。基于 [Textual](https://textual.textualize.io/)。

## 安装

需要 Python 3.10+。推荐用 pip 或 [uv](https://docs.astral.sh/uv/) 从 PyPI 安装：

```bash
pip install easymd-cli      # 或: uv tool install easymd-cli
easymd 笔记.md               # 文件不存在时会在首次 :w 时创建
```

需要在编辑器里一键翻译预览（见下文「翻译预览」）时，装上可选依赖：

```bash
pip install 'easymd-cli[translate]'   # 或: uv tool install 'easymd-cli[translate]'
```

从源码开发：

```bash
git clone https://github.com/decajoin/easymd && cd easymd
uv sync --group dev
uv run easymd demo.md
uv run pytest            # 运行测试
```

## 按键参考

### 模式

| 按键 | 作用 |
| --- | --- |
| `i` `a` `A` `I` `o` `O` | 进入插入模式（位置同 vim） |
| `R` | 替换模式（连续覆写，退格可恢复被覆写的字符） |
| `Esc` | 回到普通模式 |
| `v` | 可视模式（`y`/`d`/`c` 作用于选区） |
| `V` | 可视行模式（按整行选择，`y`/`d`/`c` 作用于整行；`v`/`V` 互切） |

### 移动（普通/可视模式，支持数字前缀如 `3j`）

`h j k l`、`w b e`、`0 ^ $`、`gg G`（`3G` 跳第 3 行）、`{ }` 段落、`Ctrl+d/u` 半页、`Ctrl+f/b` 整页

| 按键 | 作用 |
| --- | --- |
| `f` `F` `t` `T` + 字符 | 行内查找：到 / 反向到 / 到前一格 / 反向到后一格；可配 operator（`df,` `ct.`） |
| `;` / `,` | 重复上次行内查找（同向 / 反向） |
| `%` | 跳到匹配的括号（`( ) [ ] { }`，支持嵌套与跨行） |
| `*` / `#` | 搜索光标处单词（向后 / 向前，全词匹配），再用 `n`/`N` 继续 |

### 编辑

| 按键 | 作用 |
| --- | --- |
| `x` | 删除光标处字符 |
| `r` / `~` | 替换光标处字符 / 切换大小写（支持计数） |
| `J` | 合并下一行（`3J` 合并三行） |
| `dd` / `yy` / `cc` | 删除 / 复制 / 改写整行（支持 `3dd`） |
| `D` / `C` / `Y` | 删除至行尾 / 改写至行尾 / 复制整行 |
| `dw` `de` `d$` 等 | 操作符 + 移动（`y`、`c` 同理；`cw` 同 vim 不吃尾随空格） |
| `diw` `ci"` `ya(` 等 | 文本对象：`i`/`a` + `w` `"` `'` `` ` `` `(` `[` `{`，配 `d/c/y` 或可视模式 |
| `p` / `P` | 在后 / 前粘贴 |
| `.` | 重复上次修改（支持计数覆盖，如 `3.`） |
| `u` / `Ctrl+r` | 撤销 / 重做 |

### 命令与搜索

| 命令 | 作用 |
| --- | --- |
| `:w` `:w 文件名` | 保存 |
| `:q` `:q!` `:wq` `:x` | 退出（有未保存修改时 `:q` 会拒绝） |
| `/文本` 然后 `n` / `N` | 搜索 / 下一个 / 上一个 |
| `:trans` | 切换右侧预览为译文 / 原文（见「翻译预览」） |
| `:summarize`（`:sum`） | 把右侧预览换成全文摘要（TL;DR，目标语言同翻译） |
| `:transback` | 切回原文预览 |
| `:refresh` | 重新生成当前 AI 预览（译文/摘要，只重做改动部分） |
| `:toc` | 开/关左侧标题大纲，回车跳到标题 |
| `:noh` | 清除搜索高亮 |

## 翻译预览（DeepSeek）

装了 `[translate]` 可选依赖后，`:trans` 会把右侧预览整篇译成中文（默认）并缓存，
再次 `:trans` 切回原文。译文按 Markdown 语义块切分、按内容缓存：编辑原文后状态栏会
提示「译文已过期」，用 `:refresh` 只重翻改动的段落。译文模式下两栏不联动滚动，用滚轮
独立翻页。翻译结果只影响预览，不会写回你的文件。

### 配置 API key

优先用环境变量，其次配置文件 `~/.config/easymd/config.toml`：

```bash
export DEEPSEEK_API_KEY=sk-...        # 推荐
# 或交互式写入配置文件（权限 600）：
easymd config set-key
```

配置文件示例：

```toml
[deepseek]
api_key = "sk-..."          # 也可用 DEEPSEEK_API_KEY 环境变量（优先）
model = "deepseek-v4-flash" # 可选 deepseek-v4-pro
target_lang = "中文"
```

相关命令：`easymd config show`（查看解析后的配置，key 已脱敏）、
`easymd config set-model deepseek-v4-pro`。也可在启动时覆盖：
`easymd --pro 笔记.md`、`easymd --model <id> 笔记.md`、`easymd --lang English 笔记.md`。

`:summarize`（别名 `:sum`）复用同一套机制,把整篇生成一段简短 TL;DR 显示在预览窗,
目标语言和翻译一致(默认中文)。`:refresh` 会重做当前激活的 AI 预览(译文或摘要)。

译文逐 token 流式刷新,体感更快;结果按段落落盘缓存到 `~/.cache/easymd/translate/`,
重复翻译同一内容不再花钱(设 `EASYMD_CACHE_DIR=` 为空可禁用,或指向别处)。译文模式下
预览按标题分节与左侧编辑器联动滚动;摘要是浓缩内容,不做滚动联动。

未装 `[translate]` 依赖或未配置 key 时，`:trans` / `:summarize` 会在状态栏给出友好提示而不会崩溃。

## 项目结构

```
src/easymd/
  cli.py        # 命令行入口（typer：easymd FILE / easymd config ...）
  app.py        # 分屏布局、状态栏、命令行、预览同步、翻译视图状态机
  editor.py     # vim 模态层（TextArea 子类）
  config.py     # 读取 DeepSeek 配置（env > config.toml > 默认）
  translate.py  # 分块 + 内容缓存 + DeepSeek 客户端（可选依赖）
tests/          # pytest 套件（Textual Pilot 无头驱动真实按键）
```

运行测试：`uv run pytest`
