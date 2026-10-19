# Windows 上的 Python Agent 沙箱实验

这是可运行的 **AppContainer 文件访问隔离**示例。Python 调用 Windows API 创建
受限进程，Windows 根据进程的 AppContainer 身份和文件 ACL 做权限检查。
不需要管理员、Docker、pip 包或模型 API Key。

## 运行

在本项目根目录的 PowerShell 中执行：

```powershell
py -3.11 examples/windows_sandbox/sandbox_demo.py
```

本机已验证的解释器为 CPython 3.11.9。也可以在 IDE 中运行 `sandbox_demo.py`，
解释器选择已安装的普通 CPython 3.11+。`python` 命令如果指向 Microsoft Store
占位程序，请使用上面的 `py -3.11`。

每次运行都会在 Windows 临时目录创建一个新的 `python-agent-sandbox-*` 文件夹。
Agent 只尝试读写里面的演示文件；不会拿真实个人文件做实验。

## 你会看到什么

程序先运行一个**普通进程**，再运行**相同代码的 AppContainer 进程**。

| 操作 | 普通进程，仅设置 cwd | AppContainer 进程 |
| --- | --- | --- |
| 写入 workspace/inside.txt | ALLOWED | ALLOWED |
| 读取 outside/private.txt | ALLOWED | DENIED，PermissionError |
| 覆盖 outside/private.txt | ALLOWED | DENIED，PermissionError |
| 启动 Python 子进程，写 workspace/child_*.txt | 成功 | 成功 |
| 启动 Python 子进程，写 outside/child_*.txt | 成功 | 失败，文件不存在 |

末尾应出现：

```text
PASS: inside write succeeded; outside read/write and child write were blocked.
Temporary AppContainer profile removed. Experiment files kept for inspection.
```

控制进程会恢复 `outside/private.txt` 的原始演示内容，然后再开始沙箱实验。
检查结果不仅依赖 worker 日志，还由父进程检查文件实际内容和子进程生成文件。
运行后可以打开打印出来的目录，查看 `workspace/ordinary.log`、
`workspace/sandbox.log` 和两侧的演示文件。实验目录被保留，方便观察；不自动删除。

## 按这个顺序读代码

1. `agent_worker.py`：固定的“决策 → 动作 → 观察”。它调用真正的 `open()`，
   还用 `os.spawnv()` 启动新的 Python 子进程。没有改写 open，也没有自行判断路径是否越界。
2. `sandbox_demo.py`：准备假数据、对照实验、授予目录权限，再检查结果。
3. `win_appcontainer.py`：底层 Windows API。结构体比较多，可以先只看
   `appcontainer_profile()` 和 `run_isolated()`。

“Agent”使用固定动作，便于每次复现实验，不会自主规划或调用 LLM。
将决策替换为模型输出，不改变这里演示的权限检查机制。

## 隔离的关键代码

```python
# AppContainer 的唯一身份 SID：不是新建 Windows 登录用户。
with appcontainer_profile(name) as (sid, sid_text):
    # 仅给予这次创建的 runtime 读/执行权限，给予 workspace 修改权限。
    acl(runtime, "/grant", f"*{sid_text}:(OI)(CI)(RX)")
    acl(workspace, "/grant", f"*{sid_text}:(OI)(CI)(M)")
    # outside 没有获得这个 SID 的权限。
    run_isolated(argv, workspace, sid, environment)
```

`CreateProcessW` 通过 `STARTUPINFOEX` 携带 `SECURITY_CAPABILITIES`，让 Windows
创建 AppContainer 进程。代码会在恢复其执行之前查询 `TokenIsAppContainer`，
确认 Windows 实际应用了隔离；任何设置失败都会终止，不会降级为普通进程。

`cwd` 只设置起始目录，对照实验展示了它无法阻止绝对路径访问。
Job Object 负责在超时或异常退出时终止子进程树，它和文件隔离是两种不同机制。

## 范围与限制

- 本 demo 验证的是文件读写和子进程继承限制，不是生产级任意代码执行服务。
- AppContainer 仍可读取系统允许应用包访问的部分系统资源，也有自己的私有存储；
  它不意味着整台电脑只剩一个 workspace 可见。
- 这里没有授予网络 capability，但没有做网络连通性实验，不能据此推断所有
  外部服务、IPC、设备访问或侧信道都已验证。
- 子进程使用环境变量白名单，不继承 API Key；Windows 创建 AppContainer 必需的
  `LOCALAPPDATA` 等路径变量仍传入。变量中的路径字符串不构成文件授权。
- 为避免开放宿主 Python 目录，程序复制了一个只够运行演示 worker 的最小环境。
  它只包含解释器、DLL 和 encodings；真实 Agent 的 SDK、网络模块等依赖不在其中。
- ACL 只修改本次创建的实验目录。AppContainer profile 在结束时移除；保留目录里
  的 ACL 仍可能显示该次临时 SID，它不会成为可复用的登录用户。
- 若公司安全策略禁止 AppContainer、拦截临时目录里的程序，demo 会报错。
  不要为了通过实验关闭安全软件，也不会自动去掉隔离重试。

要接入本项目，Executor 和 Reviewer 的命令都需要经由受限运行器启动。
只把 Codex 子进程隔离，不能保护随后由宿主 Python 直接运行的验收命令。

## 官方资料

- [微软：启动 AppContainer](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer)
- [微软：AppContainer 隔离机制](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)
- [微软：进程属性 API](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)
