# Coding Agent

第一版本地编程编排 Agent，提供 CLI 入口，将需求或审计报告拆成串行任务，调用 Codex 执行，并记录 run、task、plan、events 和 report。

## Install

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e ".[test]"
```

## Executors

支持两种执行器，通过 `--executor codex|claude` 或 `DEFAULT_EXECUTOR` 选择：

- `codex`：调用 Codex CLI（`codex exec --sandbox workspace-write`），在沙箱内允许工作区写入。
- `claude`：调用 Claude Code CLI 无头模式（`claude -p`）。默认 `CLAUDE_PERMISSION_MODE=acceptEdits`——只自动接受文件编辑，命令执行仍受权限门禁（验证由 Reviewer 的命令验收承担）。需要执行器自己跑命令时可设为 `bypassPermissions`，这等价于 `--dangerously-skip-permissions`，会跳过所有权限确认，请自行评估风险。两种执行器都受 `EXECUTOR_TIMEOUT_SECONDS` 超时保护。
