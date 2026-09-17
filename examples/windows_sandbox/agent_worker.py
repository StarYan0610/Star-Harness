"""被隔离的演示 Agent：只依赖内置模块，方便放入很小的 Python 运行环境。

固定动作是为了观察沙箱效果，不调用模型。真正的 Agent 可以在相同的隔离
进程里根据模型输出决定动作；安全边界由 Windows 决定，与决策来自哪里无关。
"""
import os
import sys


def main():
    workspace, outside, report_path, role = sys.argv[1:]
    # 标准输出不是安全边界。把观察结果写进有写权限的 workspace。
    with open(report_path, "w", encoding="utf-8") as report:
        def record(message):
            report.write(message + "\n")
            report.flush()

        def attempt(name, action):
            try:
                action()
            except OSError as exc:
                record(f"{name}: DENIED errno={exc.errno} {type(exc).__name__}: {exc.strerror}")
            else:
                record(f"{name}: ALLOWED")

        def write_file(path):
            with open(path, "w", encoding="utf-8") as file:
                file.write(f"written by {role}\n")

        def read_private_file():
            with open(os.path.join(outside, "private.txt"), encoding="utf-8") as file:
                file.read()

        record(f"role={role}")
        attempt("WRITE_INSIDE", lambda: write_file(os.path.join(workspace, "inside.txt")))
        attempt("READ_OUTSIDE", read_private_file)
        attempt("WRITE_OUTSIDE", lambda: write_file(os.path.join(outside, "private.txt")))

        # 再启动一个全新的 Python 进程，使用其自己的 open() 尝试写入。
        # 子进程也受限制，说明不是当前 Python 进程里的函数包装在起作用。
        def child_write(path):
            # Windows CRT 的 spawnv 需要调用者给含空格的 argv 加引号。
            return os.spawnv(os.P_WAIT, sys.executable, [
                f'"{sys.executable}"', "-I", "-S", f'"{__file__}"',
                "--child", f'"{path}"',
            ])

        # 先在允许目录写入，证明子进程确实启动成功。
        child_inside = os.path.join(workspace, f"child_{role}.txt")
        code = child_write(child_inside)
        record(f"CHILD_INSIDE_EXIT_CODE={code}")
        child_path = os.path.join(outside, f"child_{role}.txt")
        code = child_write(child_path)
        record(f"CHILD_OUTSIDE_EXIT_CODE={code}")
        record("WORKER_FINISHED")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--child"]:
        try:
            with open(sys.argv[2], "w", encoding="utf-8") as file:
                file.write("child-write\n")
        except OSError:
            sys.exit(13)
    else:
        main()
