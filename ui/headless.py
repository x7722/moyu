import sys
import time
from typing import Optional

from core.constants import APP_NAME
from core.deps import cv2, mp
from core.detector import FaceDetectionWorker
from services.snapshot import save_snapshot
from .tray import get_tray_manager
from services.work_app import switch_to_work_app


def run_headless(config: dict) -> None:
    """在当前终端中以无界面模式运行检测。"""
    if cv2 is None:
        print("未安装 OpenCV。请先执行\n  pip install opencv-python")
        sys.exit(1)
    if mp is None:
        print("未安装 MediaPipe。请先执行\n  pip install mediapipe")
        sys.exit(1)

    detector = FaceDetectionWorker(config)
    detector.start()

    ui_cfg = config.get("ui", {})
    tray_seconds = int(ui_cfg.get("tray_notification_seconds", 8))
    tray_seconds = max(5, min(tray_seconds, 10))
    tray_message = ui_cfg.get("message", "检测到额外人脸，已切回工作应用。")
    TrayManager = get_tray_manager()
    tray: Optional[TrayManager] = None  # type: ignore[assignment]
    if TrayManager is not None:
        tray = TrayManager(APP_NAME, on_restore=lambda: None, on_exit=lambda: None)
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
                    print("检测到额外人脸，正在切换到工作应用…")
                    save_snapshot(config, frame_bgr)
                    switch_to_work_app(config)
                    if tray:
                        tray.show_notification(APP_NAME, tray_message, tray_seconds)

            prev_is_face_present = is_face_present
    except KeyboardInterrupt:
        print("正在退出…")
    finally:
        detector.stop()
        detector.join(timeout=2)
        if tray:
            tray.stop()

