import json
import os
import sys
import threading
import time
import subprocess
from typing import Optional, List, Tuple

try:
    import tkinter as tk
except ImportError:
    tk = None

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import mediapipe as mp
except ImportError:
    mp = None

try:
    import win32con
    import win32gui
except ImportError:
    win32con = None
    win32gui = None


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


def _get_base_dir() -> str:
    """
    PyInstaller onefile 时 __file__ 指向临时解包目录，使用可执行文件所在目录作为基准。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _get_bundled_config_path() -> str:
    """
    获取内置的默认配置路径（打包时随 exe 一起包含）。
    """
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return os.path.join(bundle_dir, "config.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def _get_external_config_path() -> str:
    """
    获取用户可覆盖的外部配置路径（exe 同级）。
    """
    return os.path.join(_get_base_dir(), "config.json")


def _merge_dict(base: dict, override: dict) -> dict:
    """递归合并配置，override 中的键优先。"""
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _merge_dict(result[k], v)
        else:
            result[k] = v
    return result


BASE_DIR = _get_base_dir()
BUNDLED_CONFIG_PATH = _get_bundled_config_path()
DEFAULT_CONFIG_PATH = _get_external_config_path()
APP_NAME = "moyu"


# =========================
# 配置与通用工具函数
# =========================

def load_config(path: Optional[str] = None) -> dict:
    """
    先加载内置默认配置，再用外部配置（若存在）进行覆盖，便于用户仅填写需要改的字段。
    """
    base_path = BUNDLED_CONFIG_PATH
    if not os.path.exists(base_path):
        raise FileNotFoundError(f"内置配置文件不存在: {base_path}")
    with open(base_path, "r", encoding="utf-8") as f:
        base_cfg = json.load(f)

    external_path = path or DEFAULT_CONFIG_PATH
    if external_path and os.path.exists(external_path):
        with open(external_path, "r", encoding="utf-8") as f:
            override_cfg = json.load(f)
        return _merge_dict(base_cfg, override_cfg)

    return base_cfg


class SystemTrayManager:
    """Minimal system tray helper for Windows."""

    WM_TRAYICON = (win32con.WM_USER + 20) if win32con is not None else 1028
    MENU_SHOW = 1024
    MENU_EXIT = 1025

    def __init__(self, app_name: str, on_restore, on_exit):
        self.app_name = app_name
        self.on_restore = on_restore
        self.on_exit = on_exit
        self._hwnd = None
        self._hicon = None
        self._thread: Optional[threading.Thread] = None

    # ---------- lifecycle ----------

    def start(self):
        if (
            self._thread
            or win32gui is None
            or win32con is None
            or not sys.platform.startswith("win")
        ):
            return

        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()

    def stop(self):
        if self._hwnd:
            try:
                win32gui.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    # ---------- public api ----------

    def show_notification(self, title: str, message: str, duration_seconds: int = 8):
        """Show a balloon notification from the tray icon."""
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


def get_os_command_key() -> Optional[str]:
    """根据当前操作系统选择配置中使用的命令字段。"""
    if sys.platform.startswith("win"):
        return "windows_command"
    if sys.platform == "darwin":
        return "macos_command"
    return None


def switch_to_work_app(config: dict) -> None:
    """
    执行配置中的工作应用命令：
    - Windows：通常是 code / IDEA 的 exe 路径
    - macOS：通常是 open -a "xxx"
    """
    work_cfg = config.get("work_app", {})
    active_key = work_cfg.get("active")
    targets = work_cfg.get("targets", {})
    if not active_key or active_key not in targets:
        print("未配置有效的工作应用目标（work_app.active / work_app.targets）。")
        return

    target = targets[active_key]
    cmd_key = get_os_command_key()
    if not cmd_key:
        print("当前操作系统未在配置中支持，仅支持 Windows 和 macOS。")
        return

    # 窗口关键字用于激活已有实例或启动后强行前置
    window_keywords = target.get("window_keywords") or []
    if not window_keywords:
        if active_key and active_key.lower() == "idea":
            window_keywords = ["intellij idea"]
        elif active_key and active_key.lower() == "vscode":
            window_keywords = ["visual studio code"]
        else:
            window_keywords = [active_key] if active_key else []

    if sys.platform.startswith("win") and window_keywords:
        # 先尝试前置已在运行的窗口，避免重复启动
        _bring_window_to_front(window_keywords)

    cmd = target.get(cmd_key)
    if not cmd:
        print(f"未为当前系统配置工作应用启动命令: {cmd_key}")
        return

    try:
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = getattr(subprocess, "SW_SHOWNORMAL", 1)
            subprocess.Popen(cmd, shell=True, startupinfo=startupinfo)
        else:
            subprocess.Popen(cmd, shell=True)

        if sys.platform.startswith("win") and window_keywords:
            # 尝试多次前置窗口，减少任务栏黄闪需要手动点击的情况
            _bring_window_to_front(window_keywords, retries=10, delay=0.3)
    except Exception as e:
        print(f"切换到工作应用失败: {e}")


def get_snapshot_dir(config: dict) -> Optional[str]:
    """从配置中读取抓拍保存目录。"""
    snap_cfg = config.get("snapshot")
    if not isinstance(snap_cfg, dict):
        return None
    directory = snap_cfg.get("directory")
    if not directory:
        return None
    return directory


def save_snapshot(config: dict, frame) -> None:
    """
    将当前画面保存到配置的目录中，用于事后检查是谁在看屏幕。
    命名格式：people_YYYYMMDD_HHMMSS_mmm.jpg
    """
    if frame is None:
        return

    directory = get_snapshot_dir(config)
    enabled = bool(config.get("snapshot", {}).get("enabled", True))
    if not enabled or not directory:
        return

    try:
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        print(f"创建抓拍目录失败: {e}")
        return

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    millis = int((time.time() % 1) * 1000)
    filename = f"people_{timestamp}_{millis:03d}.jpg"
    filepath = os.path.join(directory, filename)

    try:
        cv2.imwrite(filepath, frame)
        print(f"已保存抓拍: {filepath}")
    except Exception as e:
        print(f"保存抓拍失败: {e}")


# =========================
# 高精度人脸检测线程（MediaPipe）
# =========================


class FaceDetectionWorker(threading.Thread):
    """
    使用 MediaPipe Face Detection 的高精度人脸检测线程：
    - 独立线程内完成摄像头采集 + 人脸检测，不阻塞 UI。
    - 做多帧稳定判断（去抖动），输出稳定状态 is_face_present。
    - 提供 latest_frame_bgr / latest_faces 给 UI 做显示与调试。
    """

    def __init__(self, config: dict):
        super().__init__(daemon=True)
        if cv2 is None:
            raise RuntimeError("未安装 OpenCV。请先执行: pip install opencv-python")
        if mp is None:
            raise RuntimeError("未安装 MediaPipe。请先执行: pip install mediapipe")

        self.config = config
        camera_cfg = config.get("camera", {})

        # ---------- 检测灵敏度与过滤参数 ----------
        # 置信度阈值：低于该值的检测结果会被忽略（0.6 ~ 0.8 之间较合理）
        self.conf_threshold = float(camera_cfg.get("mp_min_confidence", 0.7))

        # 多帧稳定判断参数：N 帧有人 → 状态变为有人；M 帧无人 → 状态变为无人
        self.on_frames = int(camera_cfg.get("debounce_on_frames", 5))   # N
        self.off_frames = int(camera_cfg.get("debounce_off_frames", 15))  # M

        # 基于框面积过滤过小或过大的框（占整幅画面的比例）
        self.min_area_ratio = float(camera_cfg.get("min_area_ratio", 0.01))
        self.max_area_ratio = float(camera_cfg.get("max_area_ratio", 0.6))

        # 低光环境过滤：灰度均值低于该值时忽略本帧
        self.low_light_threshold = float(camera_cfg.get("low_light_threshold", 40.0))

        # 是否在画面上叠加检测框与置信度（调试模式）
        self.debug_draw = bool(camera_cfg.get("debug_draw", False))

        # 图像增强参数
        self.camera_contrast = float(camera_cfg.get("contrast", 1.1))
        self.camera_brightness = float(camera_cfg.get("brightness", -20.0))
        self.enable_hist_eq = bool(camera_cfg.get("hist_equalization", True))

        # 摄像头分辨率（如果支持会被应用）
        self.frame_width = int(camera_cfg.get("frame_width", 0))
        self.frame_height = int(camera_cfg.get("frame_height", 0))

        # 人脸数量触发阈值（与旧逻辑保持兼容）
        self.min_faces_for_alert = int(config.get("min_faces_for_alert", 2))

        # 多帧计数器与状态
        self.face_present_frames = 0
        self.face_absent_frames = 0
        self.is_face_present = False

        # 最新一帧画面与检测结果（供 UI 读取）
        self.latest_frame_bgr = None  # type: ignore
        self.latest_faces: List[Tuple[int, int, int, int, float]] = []
        self.latest_brightness: float = 0.0

        # 线程控制
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # 初始化摄像头
        camera_index = config.get("camera_index", 0)
        self.cap = cv2.VideoCapture(camera_index)
        if self.frame_width > 0:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
        if self.frame_height > 0:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开摄像头（index={camera_index}）。")

        # 初始化 MediaPipe Face Detection
        self._mp_face_detection = mp.solutions.face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=self.conf_threshold,
        )

    # ---------- 外部读取接口 ----------

    def get_latest_frame_and_state(self):
        """
        供 UI 线程调用，获得最新一帧画面和当前稳定状态。
        返回：(frame_bgr, is_face_present)
        """
        with self._lock:
            return self.latest_frame_bgr, self.is_face_present

    # ---------- 线程控制 ----------

    def stop(self):
        """请求检测线程停止。"""
        self._stop_event.set()

    # ---------- 主检测循环 ----------

    def run(self):
        try:
            while not self._stop_event.is_set():
                ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

                # 镜像处理，让画面更符合“照镜子”的习惯
                frame = cv2.flip(frame, 1)

                # 亮度/对比度调整
                frame = cv2.convertScaleAbs(
                    frame,
                    alpha=self.camera_contrast,
                    beta=self.camera_brightness,
                )

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                mean_brightness = float(gray.mean())

                valid_detections: List[Tuple[int, int, int, int, float]] = []

                # 低光环境：直接忽略本帧检测结果
                if mean_brightness >= self.low_light_threshold:
                    if self.enable_hist_eq:
                        gray_eq = cv2.equalizeHist(gray)
                    else:
                        gray_eq = gray

                    h, w = gray_eq.shape[:2]
                    # MediaPipe 需要 RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    results = self._mp_face_detection.process(frame_rgb)

                    if results.detections:
                        for det in results.detections:
                            if not det.score:
                                continue
                            score = float(det.score[0])
                            # 1. 置信度过滤
                            if score < self.conf_threshold:
                                continue

                            # 2. 取出 bounding box（相对坐标 → 像素坐标）
                            bbox = det.location_data.relative_bounding_box
                            x_min = int(bbox.xmin * w)
                            y_min = int(bbox.ymin * h)
                            box_w = int(bbox.width * w)
                            box_h = int(bbox.height * h)

                            # 边界裁剪
                            x_min = max(min(x_min, w - 1), 0)
                            y_min = max(min(y_min, h - 1), 0)
                            box_w = max(min(box_w, w - x_min), 1)
                            box_h = max(min(box_h, h - y_min), 1)

                            # 3. 基于框面积过滤太小或太大的框
                            area_ratio = (box_w * box_h) / float(w * h)
                            if not (self.min_area_ratio <= area_ratio <= self.max_area_ratio):
                                continue

                            valid_detections.append((x_min, y_min, box_w, box_h, score))

                # ---------- 多帧稳定判断（去抖动） ----------
                if len(valid_detections) >= self.min_faces_for_alert:
                    self.face_present_frames += 1
                    self.face_absent_frames = 0
                else:
                    self.face_present_frames = 0
                    self.face_absent_frames += 1

                new_state = self.is_face_present
                # 连续 on_frames 帧有人 → 状态切换为“有人”
                if not self.is_face_present and self.face_present_frames >= self.on_frames:
                    new_state = True
                # 连续 off_frames 帧无人 → 状态切换为“无人”
                elif self.is_face_present and self.face_absent_frames >= self.off_frames:
                    new_state = False

                # ---------- 调试绘制 ----------
                draw_frame = frame.copy()
                # 识别到的人默认绿色框；当满足报警条件（is_face_present 为真）时用红色框
                box_color = (0, 0, 255) if new_state else (0, 255, 0)
                for (x, y, box_w, box_h, score) in valid_detections:
                    cv2.rectangle(draw_frame, (x, y), (x + box_w, y + box_h), box_color, 1)
                    if self.debug_draw:
                        cv2.putText(
                            draw_frame,
                            f"{score:.2f}",
                            (x, max(y - 5, 0)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.4,
                            box_color,
                            1,
                            cv2.LINE_AA,
                        )

                # ---------- 更新共享状态 ----------
                with self._lock:
                    self.latest_frame_bgr = draw_frame
                    self.latest_faces = list(valid_detections)
                    self.latest_brightness = mean_brightness
                    self.is_face_present = new_state

                time.sleep(0.01)
        finally:
            self.cap.release()
            self._mp_face_detection.close()


# =========================
# GUI 模式：带预览的小窗口
# =========================


class CameraPreviewApp:
    """
    带摄像头预览的小窗口：
    - 窗口在屏幕上可自由拖动、缩放（默认 100x100，黑色背景）。
    - 会实时显示摄像头画面（镜像）和可选调试框。
    - 通过独立的人脸检测线程读取 is_face_present 状态：
      - 从“无人”→“有人”时：显示提示文字 + 抓拍 + 切换到工作应用。
    """

    def __init__(self, config: dict):
        if tk is None:
            raise RuntimeError("当前环境不支持 tkinter。")
        if Image is None or ImageTk is None:
            raise RuntimeError("当前环境未安装 Pillow。请先运行: pip install -r requirements.txt")

        self.config = config
        ui_cfg = config.get("ui", {})

        # 提示文字内容与显示时长
        self.message_text = ui_cfg.get("message", "有人在看屏幕，注意隐私。")
        self.display_ms = int(ui_cfg.get("display_milliseconds", 3000))

        # 冷却时间：避免频繁切换应用
        self.cooldown_seconds = float(config.get("alert_cooldown_seconds", 15))
        self._last_action_time = 0.0
        self._prev_is_face_present = False

        self.enable_tray = (
            bool(ui_cfg.get("enable_system_tray", True))
            and sys.platform.startswith("win")
            and win32gui is not None
            and win32con is not None
        )
        self.minimize_to_tray = bool(ui_cfg.get("minimize_to_tray", True))
        self.start_minimized = bool(ui_cfg.get("start_minimized", False))
        tray_seconds = int(ui_cfg.get("tray_notification_seconds", 8))
        self.tray_notification_seconds = max(5, min(tray_seconds, 10))
        self.tray: Optional[SystemTrayManager] = None
        self._hidden_to_tray = False
        self._tray_hint_shown = False

        # 初始化 Tk 小窗口
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} - 预览")
        self.root.attributes("-topmost", True)
        self.root.resizable(True, True)
        self.root.geometry("100x100")
        self.root.configure(bg="#000000")

        # 视频显示区域
        self.video_label = tk.Label(self.root, bg="#000000")
        self.video_label.pack(fill="both", expand=True)

        # 左上角小号提示文字
        self.text_label = tk.Label(
            self.root,
            text="",
            bg="#000000",
            fg="#CCCCCC",
            font=("Microsoft YaHei", 8),
            anchor="w",
        )
        self.text_label.place(x=6, y=4)
        self.text_visible = False

        self._photo = None

        # 启动人脸检测线程
        self.detector = FaceDetectionWorker(config)
        self.detector.start()

        if self.enable_tray:
            self.tray = SystemTrayManager(
                APP_NAME,
                on_restore=lambda: self.root.after(0, self._restore_from_tray),
                on_exit=lambda: self.root.after(
                    0, lambda: self._on_close(force_exit=True)
                ),
            )
            try:
                self.tray.start()
            except Exception:
                self.tray = None
                self.enable_tray = False

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Unmap>", self._on_window_state_change)
        self.root.after(0, self._update_frame)
        if self.enable_tray and self.start_minimized:
            self.root.after(150, self._hide_to_tray)

    # ---------- Tk 回调 ----------

    def _on_close(self, force_exit: bool = False):
        """关闭窗口时最小化到托盘或退出程序。"""
        if self.enable_tray and self.minimize_to_tray and not force_exit:
            self._hide_to_tray()
            return
        self._shutdown()

    def _on_window_state_change(self, event):
        if (
            event.widget == self.root
            and self.enable_tray
            and self.minimize_to_tray
            and not self._hidden_to_tray
            and str(self.root.state()) == "iconic"
        ):
            self._hide_to_tray()

    def _hide_to_tray(self):
        self._hidden_to_tray = True
        self.root.withdraw()
        if self.tray and not self._tray_hint_shown:
            self.tray.show_notification(
                APP_NAME,
                "moyu 已最小化到托盘，双击图标可恢复。",
                self.tray_notification_seconds,
            )
            self._tray_hint_shown = True

    def _restore_from_tray(self):
        self._hidden_to_tray = False
        self.root.deiconify()
        try:
            self.root.state("normal")
        except Exception:
            pass
        self.root.lift()
        try:
            self.root.focus_force()
        except Exception:
            pass

    def _shutdown(self):
        try:
            if self.detector:
                self.detector.stop()
        except Exception:
            pass
        if self.tray:
            self.tray.stop()
            self.tray = None
        self.root.destroy()

    def _show_message(self):
        """在左上角显示提示文字。"""
        self.text_label.config(text=self.message_text)
        self.text_visible = True
        self._message_hide_at = time.time() + self.display_ms / 1000.0

    def _update_message_visibility(self):
        """根据时间自动隐藏提示文字。"""
        if not self.text_visible:
            return
        if time.time() >= getattr(self, "_message_hide_at", 0):
            self.text_label.config(text="")
            self.text_visible = False

    def _handle_alert(self, frame_bgr):
        """统一处理报警后的动作：提示、抓拍、切换应用、托盘提醒。"""
        self._show_message()
        save_snapshot(self.config, frame_bgr)
        switch_to_work_app(self.config)
        if self.tray:
            self.tray.show_notification(
                APP_NAME,
                self.message_text,
                self.tray_notification_seconds,
            )

    # ---------- 主 UI 循环 ----------

    def _update_frame(self):
        """从检测线程读取最新状态并更新 UI。"""
        frame_bgr, is_face_present = self.detector.get_latest_frame_and_state()

        if frame_bgr is not None:
            # 将 BGR 转为 RGB，并进行等比例缩放 + 黑边显示
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            h, w = frame_rgb.shape[:2]

            label_width = max(self.video_label.winfo_width(), 1)
            label_height = max(self.video_label.winfo_height(), 1)

            scale = min(label_width / w, label_height / h)
            new_w = max(int(w * scale), 1)
            new_h = max(int(h * scale), 1)

            frame_resized = cv2.resize(frame_rgb, (new_w, new_h))

            # 创建黑色画布，并将画面居中贴上去
            canvas = Image.new("RGB", (label_width, label_height), (0, 0, 0))
            x_offset = (label_width - new_w) // 2
            y_offset = (label_height - new_h) // 2
            canvas.paste(Image.fromarray(frame_resized), (x_offset, y_offset))

            self._photo = ImageTk.PhotoImage(image=canvas)
            self.video_label.config(image=self._photo)

        # 根据 is_face_present 做状态变化触发
        now = time.time()
        if is_face_present and not self._prev_is_face_present:
            # 只在 由“无人”->“有人” 且冷却时间已过 时触发一次
            if now - self._last_action_time >= self.cooldown_seconds:
                self._last_action_time = now
                self._handle_alert(frame_bgr)

        self._prev_is_face_present = is_face_present
        self._update_message_visibility()

        # 继续下一帧
        self.root.after(30, self._update_frame)

    def run(self):
        """进入 Tk 主循环。"""
        try:
            self.root.mainloop()
        finally:
            try:
                if self.detector:
                    self.detector.stop()
            except Exception:
                pass
            try:
                if self.tray:
                    self.tray.stop()
            except Exception:
                pass


# =========================
# 无界面模式（只检测 + 抓拍 + 切应用）
# =========================


def run_headless(config: dict) -> None:
    """在当前终端中以无界面模式运行检测。"""
    if cv2 is None:
        print("未安装 OpenCV。请先执行:\n  pip install opencv-python")
        sys.exit(1)
    if mp is None:
        print("未安装 MediaPipe。请先执行:\n  pip install mediapipe")
        sys.exit(1)

    detector = FaceDetectionWorker(config)
    detector.start()

    ui_cfg = config.get("ui", {})
    tray_seconds = int(ui_cfg.get("tray_notification_seconds", 8))
    tray_seconds = max(5, min(tray_seconds, 10))
    tray_message = ui_cfg.get("message", "检测到额外人脸，已切回工作应用。")
    tray: Optional[SystemTrayManager] = None
    if (
        sys.platform.startswith("win")
        and win32gui is not None
        and win32con is not None
    ):
        tray = SystemTrayManager(APP_NAME, on_restore=lambda: None, on_exit=lambda: None)
        try:
            tray.start()
        except Exception:
            tray = None

    cooldown_seconds = float(config.get("alert_cooldown_seconds", 15))
    last_action_time = 0.0
    prev_is_face_present = False

    print("当前环境不支持 GUI 或未启用 Tkinter，已使用无界面模式运行。")
    print(" - 触发时会抓拍一张画面并切换到工作应用。")
    print(" - 按 Ctrl + C 结束程序。")

    try:
        while True:
            time.sleep(0.1)
            frame_bgr, is_face_present = detector.get_latest_frame_and_state()
            now = time.time()

            if is_face_present and not prev_is_face_present:
                if now - last_action_time >= cooldown_seconds:
                    last_action_time = now
                    print("检测到额外人脸，正在切换到工作应用……")
                    save_snapshot(config, frame_bgr)
                    switch_to_work_app(config)
                    if tray:
                        tray.show_notification(APP_NAME, tray_message, tray_seconds)

            prev_is_face_present = is_face_present
    except KeyboardInterrupt:
        print("正在退出……")
    finally:
        detector.stop()
        detector.join(timeout=2)
        if tray:
            tray.stop()


# =========================
# 程序入口
# =========================


def main():
    if cv2 is None:
        print("未安装 OpenCV。请先执行:\n  pip install opencv-python")
        sys.exit(1)
    if mp is None:
        print("未安装 MediaPipe。请先执行:\n  pip install mediapipe")
        sys.exit(1)

    try:
        config = load_config()
    except Exception as e:
        print(f"加载配置失败: {e}")
        sys.exit(1)

    # 优先使用带预览的小窗口（需要 tkinter + Pillow）
    if tk is not None and Image is not None and ImageTk is not None:
        try:
            app = CameraPreviewApp(config)
        except Exception as e:
            print(f"启动带预览窗口失败，将退回到无界面模式。错误: {e}")
            run_headless(config)
            return

        print(f"{APP_NAME} 已启动（带摄像头预览窗口）：")
        print(" - 窗口默认大小约 100x100，黑色背景，适配暗色模式，可自由拖动、调整。")
        print(" - 使用 MediaPipe Face Detection 高精度检测人脸，带多帧稳定判断与区域过滤。")
        print(" - 检测到多人时会在窗口内显示提示文字、抓拍一张照片并切换到工作应用。")
        if app.enable_tray:
            print(" - 支持托盘运行：最小化或关闭窗口会隐藏到托盘，双击图标恢复，右键托盘图标可退出。")
            print(
                f" - 报警时会在托盘气泡提醒，约 {app.tray_notification_seconds} 秒后自动消失。"
            )
        else:
            print(" - 当前环境未启用托盘，关闭窗口即退出。")

        app.run()
    else:
        print("当前 Python 环境不完整（缺少 tkinter 或 Pillow），将以无界面模式运行。")
        run_headless(config)


if __name__ == "__main__":
    main()
