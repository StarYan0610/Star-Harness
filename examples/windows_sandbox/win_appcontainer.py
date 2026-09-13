"""Windows AppContainer 的小型 ctypes 适配层，仅使用 Python 标准库。

阅读顺序：run_isolated() -> SecurityCapabilities -> CreateProcessW。
结构体较多，是因为 Win32 API 要求精确的内存布局，不是 Agent 业务逻辑。
"""
import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager
import subprocess


kernel = C.WinDLL("kernel32", use_last_error=True)
advapi = C.WinDLL("advapi32", use_last_error=True)
userenv = C.WinDLL("userenv", use_last_error=True)
SIZE_T = C.c_size_t


class StartupInfo(C.Structure):
    _fields_ = [
        ("cb", W.DWORD), ("lpReserved", W.LPWSTR), ("lpDesktop", W.LPWSTR),
        ("lpTitle", W.LPWSTR), ("dwX", W.DWORD), ("dwY", W.DWORD),
        ("dwXSize", W.DWORD), ("dwYSize", W.DWORD),
        ("dwXCountChars", W.DWORD), ("dwYCountChars", W.DWORD),
        ("dwFillAttribute", W.DWORD), ("dwFlags", W.DWORD),
        ("wShowWindow", W.WORD), ("cbReserved2", W.WORD),
        ("lpReserved2", C.c_void_p), ("hStdInput", W.HANDLE),
        ("hStdOutput", W.HANDLE), ("hStdError", W.HANDLE),
    ]


class StartupInfoEx(C.Structure):
    _fields_ = [("StartupInfo", StartupInfo), ("lpAttributeList", C.c_void_p)]


class ProcessInformation(C.Structure):
    _fields_ = [("hProcess", W.HANDLE), ("hThread", W.HANDLE),
                ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD)]


class SecurityCapabilities(C.Structure):
    _fields_ = [("AppContainerSid", C.c_void_p), ("Capabilities", C.c_void_p),
                ("CapabilityCount", W.DWORD), ("Reserved", W.DWORD)]


class BasicJobLimits(C.Structure):
    _fields_ = [("PerProcessUserTimeLimit", C.c_longlong),
                ("PerJobUserTimeLimit", C.c_longlong), ("LimitFlags", W.DWORD),
                ("MinimumWorkingSetSize", SIZE_T), ("MaximumWorkingSetSize", SIZE_T),
                ("ActiveProcessLimit", W.DWORD), ("Affinity", SIZE_T),
                ("PriorityClass", W.DWORD), ("SchedulingClass", W.DWORD)]


class IoCounters(C.Structure):
    _fields_ = [(name, C.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class ExtendedJobLimits(C.Structure):
    _fields_ = [("BasicLimitInformation", BasicJobLimits), ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", SIZE_T), ("JobMemoryLimit", SIZE_T),
                ("PeakProcessMemoryUsed", SIZE_T), ("PeakJobMemoryUsed", SIZE_T)]


def bind(dll, name, args, result):
    fn = getattr(dll, name)
    fn.argtypes, fn.restype = args, result
    return fn


create_profile = bind(userenv, "CreateAppContainerProfile",
    [W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, C.c_void_p, W.DWORD, C.POINTER(C.c_void_p)], C.c_long)
delete_profile = bind(userenv, "DeleteAppContainerProfile", [W.LPCWSTR], C.c_long)
free_sid = bind(advapi, "FreeSid", [C.c_void_p], C.c_void_p)
sid_to_string = bind(advapi, "ConvertSidToStringSidW",
    [C.c_void_p, C.POINTER(W.LPWSTR)], W.BOOL)
local_free = bind(kernel, "LocalFree", [C.c_void_p], C.c_void_p)
initialize_attributes = bind(kernel, "InitializeProcThreadAttributeList",
    [C.c_void_p, W.DWORD, W.DWORD, C.POINTER(SIZE_T)], W.BOOL)
update_attribute = bind(kernel, "UpdateProcThreadAttribute",
    [C.c_void_p, W.DWORD, SIZE_T, C.c_void_p, SIZE_T, C.c_void_p, C.c_void_p], W.BOOL)
delete_attributes = bind(kernel, "DeleteProcThreadAttributeList", [C.c_void_p], None)
create_process = bind(kernel, "CreateProcessW",
    [W.LPCWSTR, W.LPWSTR, C.c_void_p, C.c_void_p, W.BOOL, W.DWORD,
     C.c_void_p, W.LPCWSTR, C.POINTER(StartupInfoEx), C.POINTER(ProcessInformation)], W.BOOL)
close_handle = bind(kernel, "CloseHandle", [W.HANDLE], W.BOOL)
wait = bind(kernel, "WaitForSingleObject", [W.HANDLE, W.DWORD], W.DWORD)
get_exit_code = bind(kernel, "GetExitCodeProcess", [W.HANDLE, C.POINTER(W.DWORD)], W.BOOL)
open_token = bind(advapi, "OpenProcessToken", [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)], W.BOOL)
get_token_info = bind(advapi, "GetTokenInformation",
    [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)], W.BOOL)
create_job = bind(kernel, "CreateJobObjectW", [C.c_void_p, W.LPCWSTR], W.HANDLE)
set_job_info = bind(kernel, "SetInformationJobObject",
    [W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL)
assign_job = bind(kernel, "AssignProcessToJobObject", [W.HANDLE, W.HANDLE], W.BOOL)
resume_thread = bind(kernel, "ResumeThread", [W.HANDLE], W.DWORD)
terminate_process = bind(kernel, "TerminateProcess", [W.HANDLE, W.UINT], W.BOOL)


def check(ok):
    if not ok:
        raise C.WinError(C.get_last_error())


@contextmanager
def appcontainer_profile(name):
    """创建唯一身份；结束时移除身份配置，不修改现有用户或系统目录的权限。"""
    sid = C.c_void_p()
    hr = create_profile(name, "Python sandbox demo", "Temporary teaching demo", None, 0, C.byref(sid))
    if hr < 0:
        raise OSError(f"CreateAppContainerProfile failed: HRESULT 0x{hr & 0xffffffff:08x}")
    try:
        value = W.LPWSTR()
        check(sid_to_string(sid, C.byref(value)))
        try:
            sid_text = value.value
        finally:
            local_free(C.cast(value, C.c_void_p))
        yield sid, sid_text
    finally:
        free_sid(sid)
        hr = delete_profile(name)
        if hr < 0:
            raise OSError(f"DeleteAppContainerProfile failed: HRESULT 0x{hr & 0xffffffff:08x}; name={name}")


def run_isolated(argv, cwd, sid, environment, timeout_seconds=20):
    """真正的隔离发生在这里；失败就报错，绝不改为普通进程继续运行。"""
    # 0 个 capability：没有授予 internetClient 等网络能力。
    capabilities = SecurityCapabilities(sid, None, 0, 0)
    size = SIZE_T()
    initialize_attributes(None, 1, 0, C.byref(size))
    if C.get_last_error() != 122:  # 首次调用只查询缓冲区大小。
        raise C.WinError(C.get_last_error())
    buffer = C.create_string_buffer(size.value)
    check(initialize_attributes(buffer, 1, 0, C.byref(size)))
    job = None
    process = ProcessInformation()
    try:
        # PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009。
        check(update_attribute(buffer, 0, 0x00020009, C.byref(capabilities),
                               C.sizeof(capabilities), None, None))
        startup = StartupInfoEx()
        startup.StartupInfo.cb = C.sizeof(startup)
        startup.lpAttributeList = C.cast(buffer, C.c_void_p)

        # Job Object 负责超时后的整棵进程树清理；文件隔离由 AppContainer 负责。
        job = create_job(None, None)
        check(job)
        limits = ExtendedJobLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        check(set_job_info(job, 9, C.byref(limits), C.sizeof(limits)))

        # 不继承宿主环境里的 API Key，也不继承打开的文件句柄。
        env_text = "\0".join(f"{k}={v}" for k, v in sorted(environment.items())) + "\0\0"
        env_buffer = C.create_unicode_buffer(env_text)
        command = C.create_unicode_buffer(subprocess.list2cmdline([str(a) for a in argv]))
        flags = 0x00080000 | 0x00000400 | 0x08000000 | 0x4
        # EXTENDED_STARTUPINFO_PRESENT | UNICODE_ENVIRONMENT | NO_WINDOW | SUSPENDED
        check(create_process(str(argv[0]), command, None, None, False, flags,
                             env_buffer, str(cwd), C.byref(startup), C.byref(process)))
        check(assign_job(job, process.hProcess))

        # 在执行任何 Python 代码前，检查 Windows 给进程的真实 token。
        token = W.HANDLE()
        check(open_token(process.hProcess, 0x0008, C.byref(token)))  # TOKEN_QUERY
        try:
            is_container, returned = W.DWORD(), W.DWORD()
            check(get_token_info(token, 29, C.byref(is_container), C.sizeof(is_container), C.byref(returned)))
            if is_container.value != 1:
                raise RuntimeError("Child is not an AppContainer; refusing to run")
        finally:
            close_handle(token)
        if resume_thread(process.hThread) == 0xffffffff:
            raise C.WinError(C.get_last_error())
        result = wait(process.hProcess, timeout_seconds * 1000)
        if result == 258:
            raise TimeoutError("Sandbox worker timed out; its process tree will be terminated")
        if result != 0:
            raise C.WinError(C.get_last_error())
        code = W.DWORD()
        check(get_exit_code(process.hProcess, C.byref(code)))
        return code.value
    finally:
        # 也覆盖创建成功、但 token 检查或 Job 绑定失败的情况。
        if process.hProcess:
            terminate_process(process.hProcess, 1)
        if job:
            close_handle(job)
        if process.hThread:
            close_handle(process.hThread)
        if process.hProcess:
            wait(process.hProcess, 5000)
            close_handle(process.hProcess)
        delete_attributes(buffer)
