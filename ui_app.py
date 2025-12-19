import time
from typing import Optional

from constants import APP_NAME
from deps import sys, tk, Image, ImageTk, cv2
from detector import FaceDetectionWorker
from snapshot import save_snapshot
from tray import get_tray_manager
from work_app import switch_to_work_app


class CameraPreviewApp:
    """
    带摄像头预览的小窗口：
      - 窗口在屏幕上可自由拖动、缩放（默认 100x100，黑色背景）
      - 实时显示摄像头画面（镜像）和可选调试框
      - 通过独立的人脸检测线程读取 is_face_present 状态：
        - 从“无人”→“有人”时：显示提示文字 + 抓拍 + 切换到工作应用 + 托盘气泡
    """

    def __init__(self, config: dict):
        if tk is None:
            raise RuntimeError("当前环境不支持 tkinter。")
        if Image is None or ImageTk is None:
            raise RuntimeError(
                "当前环境未安装 Pillow。请先运行 pip install -r requirements.txt"
            )

        self.config = config
        ui_cfg = config.get("ui", {})

        # 提示文字内容与显示时长
        self.message_text = ui_cfg.get("message", "有人在看屏幕，请注意隐私。")
        self.display_ms = int(ui_cfg.get("display_milliseconds", 3000))

        # 冷却时间：避免频繁切换应用
        self.cooldown_seconds = float(config.get("alert_cooldown_seconds", 15))
        self._last_action_time = 0.0
        self._prev_is_face_present = False

        TrayManager = get_tray_manager()
        self.enable_tray = (
            bool(ui_cfg.get("enable_system_tray", True))
            and TrayManager is not None
        )
        self.minimize_to_tray = bool(ui_cfg.get("minimize_to_tray", True))
        self.start_minimized = bool(ui_cfg.get("start_minimized", False))
        tray_seconds = int(ui_cfg.get("tray_notification_seconds", 8))
        self.tray_notification_seconds = max(5, min(tray_seconds, 10))
        self.tray: Optional[TrayManager] = None  # type: ignore[assignment]
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
            self.tray = TrayManager(
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

        if frame_bgr is not None and cv2 is not None:
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            h, w = frame_rgb.shape[:2]

            label_width = max(self.video_label.winfo_width(), 1)
            label_height = max(self.video_label.winfo_height(), 1)

            scale = min(label_width / w, label_height / h)
            new_w = max(int(w * scale), 1)
            new_h = max(int(h * scale), 1)

            frame_resized = cv2.resize(frame_rgb, (new_w, new_h))

            from PIL import Image as PILImage  # type: ignore

            canvas = PILImage.new("RGB", (label_width, label_height), (0, 0, 0))
            x_offset = (label_width - new_w) // 2
            y_offset = (label_height - new_h) // 2
            canvas.paste(PILImage.fromarray(frame_resized), (x_offset, y_offset))

            self._photo = ImageTk.PhotoImage(image=canvas)
            self.video_label.config(image=self._photo)

        now = time.time()
        if is_face_present and not self._prev_is_face_present:
            if now - self._last_action_time >= self.cooldown_seconds:
                self._last_action_time = now
                self._handle_alert(frame_bgr)

        self._prev_is_face_present = is_face_present
        self._update_message_visibility()

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

