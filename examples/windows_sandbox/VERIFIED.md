# 本机验证记录

2026-10-18，Windows 11（系统版本 10.0.26200），CPython 3.11.9，普通用户权限。

执行 `py -3.11 examples/windows_sandbox/sandbox_demo.py`，程序退出码为 0。

实际观察：

```text
[1] Normal process (cwd alone is NOT isolation)
role=ordinary
WRITE_INSIDE: ALLOWED
READ_OUTSIDE: ALLOWED
WRITE_OUTSIDE: ALLOWED
CHILD_INSIDE_EXIT_CODE=0
CHILD_OUTSIDE_EXIT_CODE=0
WORKER_FINISHED

[2] AppContainer process (OS-enforced boundary)
role=sandbox
WRITE_INSIDE: ALLOWED
READ_OUTSIDE: DENIED errno=13 PermissionError: Permission denied
WRITE_OUTSIDE: DENIED errno=13 PermissionError: Permission denied
CHILD_INSIDE_EXIT_CODE=0
CHILD_OUTSIDE_EXIT_CODE=13
WORKER_FINISHED

PASS: inside write succeeded; outside read/write and child write were blocked.
Temporary AppContainer profile removed. Experiment files kept for inspection.
```

父进程同时核对：`outside/private.txt` 原始内容未变、越界子进程文件未创建、
允许目录中的子进程文件确实存在。创建子进程时检查了其 Windows token 的
`TokenIsAppContainer`，不是只根据命令参数推断是否启用了沙箱。

该记录只覆盖 README 所列的文件操作，不构成完整的安全审计或沙箱逃逸测试。
