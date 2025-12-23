# -*- coding: utf-8 -*-
"""
Windows DPI 感知设置 - 解决高分辨率屏幕模糊问题
"""

import sys
import os


def enable_dpi_awareness():
    """
    启用 Windows DPI 感知，解决高分辨率屏幕上 tkinter 界面模糊的问题。
    应在创建任何 Tk 窗口之前调用。
    """
    if not sys.platform.startswith("win"):
        return

    try:
        # Windows 10 1703+ 推荐使用 Per-Monitor DPI Awareness V2
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE_V2
    except Exception:
        try:
            # Windows 8.1+ 回退方案
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
        except Exception:
            try:
                # Windows Vista+ 最后回退
                from ctypes import windll
                windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def enable_dark_title_bar(window):
    """
    启用 Windows 10/11 暗色标题栏。
    
    Args:
        window: Tk 窗口对象
    """
    if not sys.platform.startswith("win"):
        return

    try:
        from ctypes import windll, c_int, byref, sizeof
        
        # 获取窗口句柄
        hwnd = windll.user32.GetParent(window.winfo_id())
        
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 10 1809+)
        # 对于较新的 Windows 11，使用值 20
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        
        # 尝试设置暗色模式
        value = c_int(1)
        result = windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            byref(value),
            sizeof(value)
        )
        
        # 如果失败，尝试使用旧版本的属性值 (19)
        if result != 0:
            DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
                byref(value),
                sizeof(value)
            )
    except Exception:
        pass  # 在不支持的系统上静默失败


def get_dpi_scale(root) -> float:
    """
    获取当前显示器的 DPI 缩放比例。

    Args:
        root: Tk 根窗口

    Returns:
        DPI 缩放比例 (1.0 = 100%, 1.5 = 150%, 2.0 = 200% 等)
    """
    try:
        # 获取屏幕 DPI
        dpi = root.winfo_fpixels('1i')
        return dpi / 96.0  # 96 是标准 DPI
    except Exception:
        return 1.0


def scaled_size(base_width: int, base_height: int, root) -> tuple:
    """
    根据 DPI 缩放计算窗口尺寸。
    基础尺寸是针对 100% DPI (96dpi) 设计的。

    Args:
        base_width: 基础宽度 (100% DPI)
        base_height: 基础高度 (100% DPI)
        root: Tk 根窗口

    Returns:
        (scaled_width, scaled_height)
    """
    scale = get_dpi_scale(root)
    # 让 tkinter 按 DPI 自动缩放 UI 元素，我们只需调整窗口大小
    return int(base_width * scale), int(base_height * scale)


def extract_app_name(exe_path: str) -> str:
    """
    从 exe 路径中提取应用名称。
    
    例如:
      - "C:/Program Files/Typora/Typora.exe" -> "Typora"
      - "C:/app/developer/apps/IntelliJ IDEA 2025.1/bin/idea64.exe" -> "IntelliJ IDEA 2025.1"
    
    Args:
        exe_path: exe 文件路径
    
    Returns:
        提取的应用名称
    """
    if not exe_path:
        return ""
    
    # 获取文件名（不含扩展名）
    basename = os.path.basename(exe_path)
    name_without_ext = os.path.splitext(basename)[0]
    
    # 常见的可执行文件名映射
    exe_name_map = {
        "idea64": "IntelliJ IDEA",
        "idea": "IntelliJ IDEA",
        "code": "VSCode",
        "chrome": "Chrome",
        "msedge": "Edge",
        "firefox": "Firefox",
        "wps": "WPS Office",
        "et": "WPS 表格",
        "wpp": "WPS 演示",
        "winword": "Word",
        "excel": "Excel",
        "powerpnt": "PowerPoint",
        "notepad": "记事本",
        "notepad++": "Notepad++",
        "typora": "Typora",
        "sublime_text": "Sublime Text",
    }
    
    # 尝试从映射中获取
    lower_name = name_without_ext.lower()
    if lower_name in exe_name_map:
        return exe_name_map[lower_name]
    
    # 如果 exe 名称太简短或太技术化，尝试从父文件夹获取
    if len(name_without_ext) <= 3 or name_without_ext.endswith("64") or lower_name in ["bin", "app"]:
        # 尝试从路径中提取更友好的名称
        path_parts = exe_path.replace("\\", "/").split("/")
        for i in range(len(path_parts) - 2, -1, -1):
            part = path_parts[i]
            # 跳过常见的无意义目录名
            if part.lower() not in ["bin", "app", "application", "program files", "program files (x86)", "appdata", "local", "programs"]:
                if len(part) > 3:
                    return part
    
    # 美化名称：首字母大写
    return name_without_ext.replace("_", " ").replace("-", " ").title()

