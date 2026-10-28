# Coding Agent

第一版本地编程编排 Agent，提供 CLI 入口，将需求或审计报告拆成串行任务，调用 Codex 执行，并记录 run、task、plan、events 和 report。

## Install

需要 Python 3.11 或更高版本。以下命令均在本项目根目录执行。

### macOS / Linux

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e ".[test]"
```

## LLM Planner

任务拆分支持两种 planner：

- `simple`：本地规则拆分，适合无 API key 的开发和测试。
- `openai`：通过 OpenAI-compatible 协议客户端调用 LLM，可接入 DeepSeek 或 OpenAI。

创建 `.env`：

```bash
cp .env.example .env
```

通过 OpenAI-compatible 协议接入 DeepSeek：

```env
DEFAULT_PLANNER=openai
LLM_PROVIDER=openai
OPENAI_API_KEY=你的 DeepSeek API Key
OPENAI_MODEL=deepseek-v4-flash
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_TIMEOUT_SECONDS=60
PLANNER_TEMPERATURE=0.1
```

如果要退回本地规则拆分：

```env
DEFAULT_PLANNER=simple
```

`LLM_PROVIDER=openai` 表示使用 OpenAI 协议客户端；真实模型服务由 `OPENAI_BASE_URL` 和 `OPENAI_MODEL` 决定。`.env.example` 默认指向 DeepSeek；若没有可用的 `OPENAI_API_KEY`，运行时会自动降级到 `simple`，不会把密钥值打印到终端或产物中。

## Reviewers And Safety

默认审查器是 `command`：Task 配置 `verification_commands` 时，会在目标项目目录按顺序执行；没有配置时才使用基础检查。可通过 `DEFAULT_REVIEWER=basic` 仅使用基础检查，或通过 `DEFAULT_REVIEWER=command` 恢复命令验收。

验证命令和执行器直接使用当前用户的本地权限。命令当前为 shell 兼容执行模式，因此只能接受受信任的需求、Planner 输出和项目内容；请先查看 Git 工作区状态。工具不会自动 push。

执行器和验证命令都有超时保护：单次执行器调用超过 `EXECUTOR_TIMEOUT_SECONDS`（默认 3600 秒）、单条验证命令超过 `VERIFICATION_TIMEOUT_SECONDS`（默认 300 秒）时，会终止整个进程组并把该次尝试记为失败，避免挂起的子进程阻塞 Run 或在后台泄漏。

`update`（以及已有 Git 仓库上的 `create`）会记录分支、dirty 状态、diff 摘要和可能影响的文件。默认 dirty 只提示；可用 `REQUIRE_CLEAN_GIT_WORKTREE=true` 或 `--require-clean-git-worktree` 将其作为失败条件。`COMMIT_ON_SUCCESS=true` 或 `--commit-on-success` 仅会在可提交的 Git 工作区创建一次本地 commit，且永不自动 push。若运行前工作区已 dirty，工具会跳过自动提交，避免把用户已有改动一起暂存；非 Git 目录也只会记录跳过，不会因此失败。

`.coding-agent/memory.md` 存在时会以只读项目上下文传给 Planner 和 Executor；同一 Run 的后续 Task 还会收到之前已通过 Task 的标题、摘要和修改范围。终端摘要、`events.jsonl`、`report.md` 与重试回注会系统性脱敏常见密钥形式。

## Executors

支持两种执行器，通过 `--executor codex|claude` 或 `DEFAULT_EXECUTOR` 选择：

- `codex`：调用 Codex CLI（`codex exec --sandbox workspace-write`），在沙箱内允许工作区写入。
- `claude`：调用 Claude Code CLI 无头模式（`claude -p`）。默认 `CLAUDE_PERMISSION_MODE=acceptEdits`——只自动接受文件编辑，命令执行仍受权限门禁（验证由 Reviewer 的命令验收承担）。需要执行器自己跑命令时可设为 `bypassPermissions`，这等价于 `--dangerously-skip-permissions`，会跳过所有权限确认，请自行评估风险。两种执行器都受 `EXECUTOR_TIMEOUT_SECONDS` 超时保护。

## Commands

新写项目：

```bash
coding-agent create --path /abs/new-project --requirement "搭建项目骨架" --executor codex
```

更新项目：

```bash
coding-agent update --path /abs/project --update-mode requirement --requirement "增加邮箱校验"
```

审计报告优化：

```bash
coding-agent update --path /abs/project --update-mode audit-report --audit-report /abs/audit.md --requirement "优先修复高风险问题"
```

查看状态：

```bash
coding-agent status --path /abs/project --run-id <uuid>
```

查看报告：

```bash
coding-agent report --path /abs/project --run-id <uuid>
```

第一版会直接在 `--path` 目录中创建或修改代码，不使用隔离目录。核心主表为 `runs` 和 `tasks`，状态流转由 `WorkflowStateMachine` 控制。
