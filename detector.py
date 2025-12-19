import threading
import time
from typing import List, Tuple

from deps import cv2, mp


class FaceDetectionWorker(threading.Thread):
    """
    使用 MediaPipe Face Detection 的高精度人脸检测线程：
    - 独立线程内完成摄像头采集 + 人脸检测，不阻塞 UI
    - 做多帧稳定判断（去抖动），输出稳定状态 is_face_present
    - 提供 latest_frame_bgr / latest_faces 供 UI 做显示与调试
    """

    def __init__(self, config: dict):
        super().__init__(daemon=True)
        if cv2 is None:
            raise RuntimeError("未安装 OpenCV。请先执行 pip install opencv-python")
        if mp is None:
            raise RuntimeError("未安装 MediaPipe。请先执行 pip install mediapipe")

        self.config = config
        camera_cfg = config.get("camera", {})

        # ---------- 检测灵敏度与过滤参数 ----------
        self.conf_threshold = float(camera_cfg.get("mp_min_confidence", 0.7))
        self.on_frames = int(camera_cfg.get("debounce_on_frames", 5))
        self.off_frames = int(camera_cfg.get("debounce_off_frames", 15))
        self.min_area_ratio = float(camera_cfg.get("min_area_ratio", 0.01))
        self.max_area_ratio = float(camera_cfg.get("max_area_ratio", 0.6))
        self.low_light_threshold = float(camera_cfg.get("low_light_threshold", 40.0))
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
            raise RuntimeError(f"无法打开摄像头（index={camera_index}）")

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
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    results = self._mp_face_detection.process(frame_rgb)

                    if results.detections:
                        for det in results.detections:
                            if not det.score:
                                continue
                            score = float(det.score[0])
                            if score < self.conf_threshold:
                                continue

                            bbox = det.location_data.relative_bounding_box
                            x_min = int(bbox.xmin * w)
                            y_min = int(bbox.ymin * h)
                            box_w = int(bbox.width * w)
                            box_h = int(bbox.height * h)

                            x_min = max(min(x_min, w - 1), 0)
                            y_min = max(min(y_min, h - 1), 0)
                            box_w = max(min(box_w, w - x_min), 1)
                            box_h = max(min(box_h, h - y_min), 1)

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
                if not self.is_face_present and self.face_present_frames >= self.on_frames:
                    new_state = True
                elif self.is_face_present and self.face_absent_frames >= self.off_frames:
                    new_state = False

                # ---------- 调试绘制 ----------
                draw_frame = frame.copy()
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

