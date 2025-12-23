import time
import os
import sys as _sys
from typing import Optional

# Windows 任务栏图标修复：设置 AppUserModelID 让 Windows 识别这是独立应用
if _sys.platform.startswith('win'):
    try:
        import ctypes
        # 设置应用 ID，让 Windows 任务栏正确显示图标而不是 Python 图标
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('moyu.app.v1')
    except Exception:
        pass

from core.constants import APP_NAME
from core.deps import sys, tk, Image, ImageTk, cv2
from core.detector import FaceDetectionWorker
from core.paths import get_base_dir
from services.snapshot import save_snapshot
from .tray import get_tray_manager
from services.work_app import switch_to_work_app
from .settings_dialog import SettingsDialog
from .dpi_utils import enable_dpi_awareness, enable_dark_title_bar


class CameraPreviewApp:
    """
    带摄像头预览的小窗口：
      - 窗口在屏幕上可自由拖动、缩放（默认 100x100，黑色背景）
      - 实时显示摄像头画面（镜像）和可选调试框
      - 通过独立的人脸检测线程读取 is_face_present 状态：
        - 从"无人"→"有人"时：显示提示文字 + 抓拍 + 切换到工作应用 + 托盘气泡
    """

    def __init__(self, config: dict):
        if tk is None:
            raise RuntimeError("当前环境不支持 tkinter。")
        if Image is None or ImageTk is None:
            raise RuntimeError(
                "当前环境未安装 Pillow。请先运行 pip install -r requirements.txt"
            )

        # 启用高 DPI 感知
        enable_dpi_awareness()

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
        self._config_path = None  # 用户配置文件路径

        # 定义主题颜色
        self.theme_bg = "#1a1a2e"
        self.theme_card = "#16213e"
        self.theme_accent = "#4a90d9"
        self.theme_text = "#e8e8e8"

        # 初始化 Tk 小窗口
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} - 预览")
        self.root.attributes("-topmost", True)
        self.root.resizable(True, False)  # 只允许水平调整大小，禁用最大化
        self.root.geometry("300x130")  # 加宽预览窗口
        self.root.configure(bg=self.theme_bg)
        
        # 设置窗口图标（修复任务栏显示 Python 图标的问题）
        import os
        icon_path = os.path.join(get_base_dir(), "moyu.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass  # 忽略图标加载失败

        # 顶部工具栏
        toolbar = tk.Frame(self.root, bg=self.theme_card, height=24)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        # 状态指示器
        self.status_label = tk.Label(
            toolbar,
            text="● 运行中",
            font=("Microsoft YaHei", 8),
            fg="#00d4aa",
            bg=self.theme_card,
        )
        self.status_label.pack(side="left", padx=6)

        # 设置按钮
        settings_btn = tk.Button(
            toolbar,
            text="⚙",
            font=("Segoe UI Symbol", 10),
            fg=self.theme_text,
            bg=self.theme_card,
            relief="flat",
            cursor="hand2",
            command=self._open_settings,
        )
        settings_btn.pack(side="right", padx=4)

        # 视频显示区域
        self.video_label = tk.Label(self.root, bg=self.theme_bg)
        self.video_label.pack(fill="both", expand=True)

        # 左上角小号提示文字
        self.text_label = tk.Label(
            self.root,
            text="",
            bg=self.theme_bg,
            fg="#CCCCCC",
            font=("Microsoft YaHei", 8),
            anchor="w",
        )
        self.text_label.place(x=6, y=28)
        self.text_visible = False

        # 启用暗色标题栏
        enable_dark_title_bar(self.root)

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
                on_settings=lambda: self.root.after(0, self._open_settings),
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
            # self.tray.show_notification(
            #     APP_NAME,
            #     "魔芋 已最小化到托盘，双击图标可恢复。",
            #     self.tray_notification_seconds,
            # )
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

    def _open_settings(self):
        """打开设置对话框"""
        import os
        try:
            import yaml
        except ImportError:
            yaml = None

        # 隐藏预览窗口
        self.root.withdraw()

        def on_save(new_config):
            # 保存配置到用户配置文件
            config_path = self._config_path or os.path.join(get_base_dir(), "user_config.yml")
            if yaml:
                try:
                    content = "# 魔芋 用户配置文件\n# 此文件由设置对话框生成，可手动编辑\n\n"
                    content += yaml.dump(new_config, allow_unicode=True, default_flow_style=False, sort_keys=False)
                    with open(config_path, "w", encoding="utf-8") as f:
                        f.write(content)
                except Exception as e:
                    print(f"保存配置失败: {e}")
            
            # 立即应用新配置（不需要重启）
            self.config.update(new_config)
            # 更新消息显示配置
            ui_cfg = new_config.get("ui", {})
            self.message_text = ui_cfg.get("message", self.message_text)

        try:
            # 传递 self.root 作为父窗口，避免创建多个 Tk() 实例导致卡死
            dialog = SettingsDialog(self.config, on_save=on_save, parent=self.root)
            dialog.run()
        finally:
            # 恢复预览窗口
            self.root.deiconify()
            self.root.lift()

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
            # 确保窗口完全渲染后再设置暗色标题栏
            self.root.update_idletasks()
            enable_dark_title_bar(self.root)
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
