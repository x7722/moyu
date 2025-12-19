import shlex
import subprocess
import time
from typing import Optional, List

from core.deps import sys, win32con, win32gui


def _bring_window_to_front(keywords: List[str], retries: int = 0, delay: float = 0.2) -> bool:
    """Try to bring a window matching all keywords to the foreground on Windows."""
    if win32gui is None or win32con is None:
        return False

    keywords_lower = [k.lower() for k in keywords if k]

    def _enum_handler(hwnd, result):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = (win32gui.GetWindowText(hwnd) or "").lower()
        if all(k in title for k in keywords_lower):
            result.append(hwnd)

    for attempt in range(max(retries + 1, 1)):
        handles: List[int] = []
        try:
            win32gui.EnumWindows(_enum_handler, handles)
        except Exception:
            return False

        for hwnd in handles:
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                return True
            except Exception:
                continue

        if attempt < retries:
            time.sleep(delay)

    return False


def get_os_command_key() -> Optional[str]:
    """根据当前操作系统选择配置中使用的命令字段。"""
    if sys.platform.startswith("win"):
        return "windows_command"
    if sys.platform == "darwin":
        return "macos_command"
    return None


def _mac_activate_app_from_command(cmd: str, window_keywords: List[str]) -> None:
    """
    尝试从 macOS 命令中推断应用名/进程名，并通过 AppleScript 激活到前台。
    优先从 `open -a "App Name"` 解析，其次用 window_keywords 兜底。
    """
    app_name: Optional[str] = None
    parts = shlex.split(cmd)
    if len(parts) >= 3 and parts[0] == "open" and parts[1] == "-a":
        app_name = parts[2]

    target_names: List[str] = []
    if app_name:
        target_names.append(app_name)
    target_names.extend(window_keywords or [])

    for name in target_names:
        try:
            script = f'tell application "{name}" to activate'
            subprocess.run(["osascript", "-e", script], check=False)
            return
        except Exception:
            continue

    if window_keywords:
        kw = window_keywords[0]
        try:
            script = (
                'tell application "System Events" to '
                f'set frontmost of first process whose name contains "{kw}" to true'
            )
            subprocess.run(["osascript", "-e", script], check=False)
        except Exception:
            pass


def switch_to_work_app(config: dict) -> None:
    """
    执行配置中的工作应用命令：
      - Windows：通常是 code / IDEA 的 exe 路径，同时尝试前置已打开窗口
      - macOS：通常是 open -a "xxx"，并通过 AppleScript 显式激活到前台
    """
    work_cfg = config.get("work_app", {})
    active_key = work_cfg.get("active")
    targets = work_cfg.get("targets", {})
    if not active_key or active_key not in targets:
        print("未配置有效的工作应用目标（work_app.active / work_app.targets）")
        return

    target = targets[active_key]
    cmd_key = get_os_command_key()
    if not cmd_key:
        print("当前操作系统未在配置中支持，仅支持 Windows 和 macOS。")
        return

    window_keywords = target.get("window_keywords") or []
    if not window_keywords:
        if active_key and active_key.lower() == "idea":
            window_keywords = ["intellij idea"]
        elif active_key and active_key.lower() == "vscode":
            window_keywords = ["visual studio code"]
        else:
            window_keywords = [active_key] if active_key else []

    cmd = target.get(cmd_key)
    if not cmd:
        print(f"未为当前系统配置工作应用启动命令: {cmd_key}")
        return

    if sys.platform.startswith("win") and window_keywords:
        _bring_window_to_front(window_keywords)

    try:
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = getattr(subprocess, "SW_SHOWNORMAL", 1)
            subprocess.Popen(cmd, shell=True, startupinfo=startupinfo)
        else:
            subprocess.Popen(cmd, shell=True)

        if sys.platform.startswith("win") and window_keywords:
            _bring_window_to_front(window_keywords, retries=10, delay=0.3)
        elif sys.platform == "darwin":
            _mac_activate_app_from_command(cmd, window_keywords)
    except Exception as e:
        print(f"切换到工作应用失败: {e}")

