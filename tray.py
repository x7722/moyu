import threading
from typing import Optional, Callable

from deps import sys, win32con, win32gui


class SystemTrayManager:
    """
    Windows 托盘图标管理器。
    在非 Windows 或未安装 pywin32 的环境下，可以安全导入但不会生效。
    """

    WM_TRAYICON = (win32con.WM_USER + 20) if win32con is not None else 1028
    MENU_SHOW = 1024
    MENU_EXIT = 1025

    def __init__(self, app_name: str, on_restore: Callable, on_exit: Callable):
        self.app_name = app_name
        self.on_restore = on_restore
        self.on_exit = on_exit
        self._hwnd = None
        self._hicon = None
        self._thread: Optional[threading.Thread] = None

    # ---------- lifecycle ----------

    def start(self) -> None:
        if (
            self._thread
            or win32gui is None
            or win32con is None
            or not sys.platform.startswith("win")
        ):
            return

        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._hwnd and win32gui is not None and win32con is not None:
            try:
                win32gui.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    # ---------- public api ----------

    def show_notification(self, title: str, message: str, duration_seconds: int = 8):
        """Show a balloon notification from the tray icon (Windows only)."""
        if (
            not self._hwnd
            or not self._hicon
            or win32gui is None
            or win32con is None
        ):
            return

        duration_ms = max(5000, min(duration_seconds * 1000, 10000))
        nid = (
            self._hwnd,
            0,
            win32gui.NIF_INFO,
            self.WM_TRAYICON,
            self._hicon,
            self.app_name,
            message,
            duration_ms,
            title,
            win32gui.NIIF_INFO,
        )
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid)
        except Exception:
            pass

    # ---------- internals ----------

    def _message_loop(self):
        h_instance = win32gui.GetModuleHandle(None)
        wndclass = win32gui.WNDCLASS()
        wndclass.hInstance = h_instance
        wndclass.lpszClassName = f"{self.app_name}_TrayWindow"
        wndclass.lpfnWndProc = self._wnd_proc
        try:
            atom = win32gui.RegisterClass(wndclass)
        except Exception:
            atom = wndclass.lpszClassName

        try:
            self._hwnd = win32gui.CreateWindow(
                atom, self.app_name, 0, 0, 0, 0, 0, 0, 0, h_instance, None
            )
        except Exception:
            return
        self._hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

        nid = (
            self._hwnd,
            0,
            win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP,
            self.WM_TRAYICON,
            self._hicon,
            self.app_name,
        )
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
        except Exception:
            try:
                win32gui.DestroyWindow(self._hwnd)
            except Exception:
                pass
            self._hwnd = None
            return
        win32gui.PumpMessages()
        self._remove_icon()

    def _remove_icon(self):
        if self._hwnd:
            try:
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self._hwnd, 0))
            except Exception:
                pass

    def _show_menu(self):
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, self.MENU_SHOW, "打开")
        win32gui.AppendMenu(menu, win32con.MF_STRING, self.MENU_EXIT, "退出")

        pos = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self._hwnd)
        win32gui.TrackPopupMenu(
            menu,
            win32con.TPM_LEFTALIGN,
            pos[0],
            pos[1],
            0,
            self._hwnd,
            None,
        )
        win32gui.PostMessage(self._hwnd, win32con.WM_NULL, 0, 0)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == self.WM_TRAYICON:
            if lparam == win32con.WM_LBUTTONDBLCLK:
                if self.on_restore:
                    self.on_restore()
            elif lparam == win32con.WM_RBUTTONUP:
                self._show_menu()
            return 1
        if msg == win32con.WM_COMMAND:
            cmd_id = wparam & 0xFFFF
            if cmd_id == self.MENU_SHOW and self.on_restore:
                self.on_restore()
            elif cmd_id == self.MENU_EXIT and self.on_exit:
                self.on_exit()
            return 1
        if msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 1
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)


class DummyTrayManager:
    """
    macOS / 其他平台上的占位托盘管理器，接口兼容但不做任何事。
    用于保持调用方逻辑简单。
    """

    def __init__(self, *_args, **_kwargs):
        pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def show_notification(self, *_args, **_kwargs) -> None:
        pass


def get_tray_manager():
    """Return a platform-appropriate tray manager class."""
    if sys.platform.startswith("win") and win32gui is not None and win32con is not None:
        return SystemTrayManager
    return DummyTrayManager

