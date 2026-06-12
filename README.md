# easymd

终端里的 Markdown 编辑器：左侧 vim 式编辑，右侧实时预览。基于 [Textual](https://textual.textualize.io/)。

## 安装

需要 Python 3.10+。

使用 [uv](https://docs.astral.sh/uv/)（推荐）：

```bash
uv sync
uv run easymd demo.md
```

或使用 pip：

```bash
pip install -r requirements.txt
pip install -e .
easymd demo.md        # 文件不存在时会在首次 :w 时创建
```

## 按键参考

### 模式

| 按键 | 作用 |
| --- | --- |
| `i` `a` `A` `I` `o` `O` | 进入插入模式（位置同 vim） |
| `Esc` | 回到普通模式 |
| `v` | 可视模式（`y`/`d`/`c` 作用于选区） |
| `V` | 可视行模式（按整行选择，`y`/`d`/`c` 作用于整行；`v`/`V` 互切） |

### 移动（普通/可视模式，支持数字前缀如 `3j`）

`h j k l`、`w b e`、`0 ^ $`、`gg G`（`3G` 跳第 3 行）、`Ctrl+d/u` 半页、`Ctrl+f/b` 整页

### 编辑

| 按键 | 作用 |
| --- | --- |
| `x` | 删除光标处字符 |
| `dd` / `yy` / `cc` | 删除 / 复制 / 改写整行（支持 `3dd`） |
| `dw` `de` `d$` 等 | 操作符 + 移动（`y`、`c` 同理） |
| `p` / `P` | 在后 / 前粘贴 |
| `u` / `Ctrl+r` | 撤销 / 重做 |

### 命令与搜索

| 命令 | 作用 |
| --- | --- |
| `:w` `:w 文件名` | 保存 |
| `:q` `:q!` `:wq` `:x` | 退出（有未保存修改时 `:q` 会拒绝） |
| `/文本` 然后 `n` / `N` | 搜索 / 下一个 / 上一个 |

## 项目结构

```
src/easymd/
  cli.py     # 命令行入口
  app.py     # 分屏布局、状态栏、命令行、预览同步
  editor.py  # vim 模态层（TextArea 子类）
tests/
  smoke_test.py  # 无头冒烟测试（Textual Pilot 驱动按键）
```

运行测试：`uv run python tests/smoke_test.py`
