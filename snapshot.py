import os
import time
from typing import Optional

from deps import cv2


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
    if frame is None or cv2 is None:
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

