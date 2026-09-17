"""运行：py -3.11 examples/windows_sandbox/sandbox_demo.py

不需要 pip、Docker、管理员权限或 API Key。仅支持 Windows + CPython 3.11+。
实验文件都在新建的临时目录里，原项目文件不会成为 Agent 的写入目标。
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile


def acl(path, *options):
    """只对本次创建的实验目录设置 ACL；不修改 Python 安装目录或系统目录。"""
    result = subprocess.run(["icacls.exe", str(path), *options], capture_output=True)
    if result.returncode:
        raise RuntimeError(f"icacls failed for {path}: {result.stdout!r} {result.stderr!r}")


def prepare_runtime(destination):
    """复制一个极小的 Python 环境，避免给 Agent 开放整套宿主 Python 安装目录。

    worker 只用内置的 sys、冻结的 os 和文件操作；encodings 用于解释器启动。
    若换成真实 Agent，需要另外准备它的依赖，不能直接假定这个最小环境够用。
    """
    base = Path(sys.base_prefix)
    dll_name = f"python{sys.version_info.major}{sys.version_info.minor}"
    shutil.copy2(base / "python.exe", destination / "python.exe")
    for pattern in (f"{dll_name}.dll", "python3.dll", "vcruntime*.dll"):
        for source in base.glob(pattern):
            shutil.copy2(source, destination / source.name)
    with zipfile.ZipFile(destination / f"{dll_name}.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for source in (base / "Lib" / "encodings").rglob("*.py"):
            archive.write(source, source.relative_to(base / "Lib").as_posix())
    # _pth 固定模块搜索路径；不导入 site，不加载用户 site-packages。
    (destination / f"{dll_name}._pth").write_text(f"{dll_name}.zip\n.\n", encoding="ascii")
    shutil.copy2(Path(__file__).with_name("agent_worker.py"), destination / "agent_worker.py")
    return destination / "python.exe"


def main():
    if os.name != "nt" or sys.implementation.name != "cpython" or sys.version_info < (3, 11):
        raise SystemExit("Use Windows and CPython 3.11 or newer: py -3.11 sandbox_demo.py")
    from win_appcontainer import appcontainer_profile, run_isolated

    root = Path(tempfile.mkdtemp(prefix="python-agent-sandbox-"))
    runtime, workspace, outside = (root / name for name in ("runtime", "workspace", "outside"))
    for directory in (runtime, workspace, outside):
        directory.mkdir()
    python = prepare_runtime(runtime)
    private = outside / "private.txt"
    original = "private canary: demo data only\n"
    private.write_text(original, encoding="utf-8")
    print(f"Experiment directory: {root}", flush=True)

    # 先对照：同一个 worker，只设置 cwd，仍能修改 outside。这里仅用假数据。
    ordinary_report = workspace / "ordinary.log"
    argv = [python, "-I", "-S", runtime / "agent_worker.py", workspace, outside]
    ordinary = subprocess.run([str(a) for a in [*argv, ordinary_report, "ordinary"]],
                              cwd=workspace, timeout=20, capture_output=True)
    if ordinary.returncode:
        raise RuntimeError(f"Control worker failed: {ordinary.stderr!r}")
    ordinary_text = ordinary_report.read_text(encoding="utf-8")
    if "WRITE_OUTSIDE: ALLOWED" not in ordinary_text or not (outside / "child_ordinary.txt").exists():
        raise RuntimeError("Control experiment did not behave as expected")
    print("\n[1] Normal process (cwd alone is NOT isolation)\n" + ordinary_text, flush=True)
    private.write_text(original, encoding="utf-8")

    name = "PythonAgentDemo." + uuid.uuid4().hex
    with appcontainer_profile(name) as (sid, sid_text):
        # SID 就是这次沙箱的身份。读运行环境，读写 workspace，不给 outside 授权。
        acl(root, "/grant", f"*{sid_text}:(RX)")
        acl(runtime, "/grant", f"*{sid_text}:(OI)(CI)(RX)")
        acl(workspace, "/grant", f"*{sid_text}:(OI)(CI)(M)")
        acl(workspace, "/setintegritylevel", "(OI)(CI)L")
        sandbox_report = workspace / "sandbox.log"
        environment = {"SystemRoot": os.environ["SystemRoot"],
                       "WINDIR": os.environ["SystemRoot"],
                       "PATH": str(Path(os.environ["SystemRoot"]) / "System32"),
                       "TEMP": str(workspace), "TMP": str(workspace),
                       "COMSPEC": str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe")}
        # Windows 创建 AppContainer 时要用 LOCALAPPDATA 定位身份配置。
        # 传递这些路径字符串并不会授予相应目录的文件访问权。
        for key in ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "SYSTEMDRIVE"):
            if key in os.environ:
                environment[key] = os.environ[key]
        code = run_isolated([*argv, sandbox_report, "sandbox"], workspace, sid, environment)
        if code or not sandbox_report.exists():
            raise RuntimeError(f"Sandbox worker failed; exit code=0x{code:08x}. Directory: {root}")
        sandbox_text = sandbox_report.read_text(encoding="utf-8")
        print("[2] AppContainer process (OS-enforced boundary)\n" + sandbox_text, flush=True)

        # 以父进程观察到的磁盘状态为准，不只相信 worker 自己报告的成功/失败。
        expected = ["WRITE_INSIDE: ALLOWED", "READ_OUTSIDE: DENIED errno=13",
                    "WRITE_OUTSIDE: DENIED errno=13", "CHILD_INSIDE_EXIT_CODE=0",
                    "CHILD_OUTSIDE_EXIT_CODE=13", "WORKER_FINISHED"]
        if not all(item in sandbox_text for item in expected):
            raise RuntimeError("Sandbox observations differed from expectations")
        if private.read_text(encoding="utf-8") != original or (outside / "child_sandbox.txt").exists():
            raise RuntimeError("Outside canary changed: isolation test FAILED")
        if not (workspace / "child_sandbox.txt").exists():
            raise RuntimeError("Child process did not write inside the workspace")
        print("PASS: inside write succeeded; outside read/write and child write were blocked.")
    print("Temporary AppContainer profile removed. Experiment files kept for inspection.")
    print(f"Logs: {workspace}")


if __name__ == "__main__":
    main()
