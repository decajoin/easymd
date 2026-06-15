# 发版流程

本项目以 `easymd-cli` 发布在 PyPI（命令名是 `easymd`，包名因 `easymd` 被占用而加了 `-cli` 后缀）。
纯 Python 包，一个 wheel 全平台通用。已发布版本：0.1.0（首发）、0.1.1（Python 下限放宽到 3.10）。

## 发版步骤

### 1. 更新版本号（两处，必须同步改）

- `pyproject.toml` 的 `version`
- `src/easymd/__init__.py` 的 `__version__`

版本规则按 semver：修 bug 升 patch（0.1.x），加功能升 minor（0.x.0）。
**PyPI 不允许覆盖已发布的版本号**——传错了只能升号重发，所以上传前务必走完检查。

### 2. 发版前检查

```bash
# 测试和 lint 必须全过（CI 也会跑，但本地先验省一轮往返）
uv run pytest
uv run ruff check src tests

# 构建并核对产物
rm -rf dist && uv build
tar -tzf dist/easymd_cli-*.tar.gz   # 确认没混入本地杂物
```

sdist 内容由 `pyproject.toml` 里 `[tool.hatch.build.targets.sdist]` 的
`include` 白名单控制。新增需要打包的文件/目录时记得更新白名单；
本地临时文件（曾混入过 4.5MB 的测试图片）默认不会进包。

若改了 `requires-python` 或依赖版本，需在对应的最低版本 Python 上实际跑一遍测试：

```bash
uv venv /tmp/floor --python 3.10
# 安装并运行 tests/smoke_test.py，全过才能改声明
```

### 3. 发布（首选：打 tag 自动发版）

```bash
git add -A && git commit   # 提交信息说明版本与变更原因，不加 Co-Authored-By
git push origin main
git tag v<版本号> && git push origin v<版本号>
```

推送 `v*` tag 后 `.github/workflows/release.yml` 自动构建并通过
**Trusted Publishing（OIDC）** 上传 PyPI，全程无 token。

首次启用需要一次性配置（PyPI 网页端）：
PyPI → 项目 easymd-cli → Publishing → Add a new publisher，填：

- Owner: `decajoin`　Repository: `easymd`
- Workflow name: `release.yml`　Environment name: `pypi`

同时在 GitHub 仓库 Settings → Environments 创建名为 `pypi` 的 environment。

备用：本地手动发版（Trusted Publishing 不可用时）：

```bash
uv publish --token pypi-xxxx
```

token 安全要求：

- 用 **scope 限定为 easymd-cli 项目**的 token，不要用全账号 token
- token 不进 shell 历史（fish 用 `read -s -x UV_PUBLISH_TOKEN` 输入后直接 `uv publish`）
- token 一旦出现在任何日志/对话/提交里，立即去 PyPI 撤销重发

### 4. 发布后验证

索引同步有约 1 分钟延迟；uv 还有本地索引缓存，验证时要加 `--refresh`：

```bash
# 元数据正确（version / requires_python）
curl -s https://pypi.org/pypi/easymd-cli/<版本号>/json | python3 -c \
  "import json,sys; i=json.load(sys.stdin)['info']; print(i['version'], i['requires_python'])"

# 干净环境真实安装
uv venv /tmp/vtest --python 3.10
VIRTUAL_ENV=/tmp/vtest uv pip install --refresh easymd-cli==<版本号>
/tmp/vtest/bin/easymd --version
rm -rf /tmp/vtest
```

## 用户安装方式（写文档/答疑用）

- 推荐：`pipx install easymd-cli` 或 `uv tool install easymd-cli`
- 新版 Debian/Ubuntu 直接 `pip install` 会报 `externally-managed-environment`
  （PEP 668），属系统策略，引导用户用 pipx；不要建议 `--break-system-packages`
- pipx 首次安装会提示 `~/.local/bin` 不在 PATH，跑 `pipx ensurepath` 即可
- 系统 Python < 3.10 的机器：`pipx install --python <3.10+解释器路径> easymd-cli`
  或 `uv tool install --python 3.10 easymd-cli`（uv 会自动下载解释器）

## 已知约束

- `requires-python >= 3.10`：textual 实际只需 3.9，代码也在 3.9 实测通过，
  但 3.9 已 EOL（2025-10），刻意不支持；除非有强需求不要再降
- 本仓库根目录的 `.venv` 是手工修补过 `activate.fish` 的开发环境，
  **不要在仓库目录运行 `uv sync`**（会重建 `.venv` 覆盖补丁）

## 待办

- [ ] 首次走 tag 发版前，完成上面第 3 节的 PyPI publisher 与 GitHub
      environment 一次性配置（网页端操作，只有仓库 owner 能做）
