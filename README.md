# Coding Agent

第一版本地编程编排 Agent，提供 CLI 入口，将需求或审计报告拆成串行任务，调用 Codex 执行，并记录 run、task、plan、events 和 report。

## Install

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e ".[test]"
```
