import sys

try:
    import tkinter as tk  # type: ignore
except ImportError:
    tk = None  # type: ignore

try:
    from PIL import Image, ImageTk  # type: ignore
except ImportError:
    Image = None  # type: ignore
    ImageTk = None  # type: ignore

try:
    import cv2  # type: ignore
except ImportError:
    cv2 = None  # type: ignore

try:
    import mediapipe as mp  # type: ignore
except ImportError:
    mp = None  # type: ignore

try:
    import win32con  # type: ignore
    import win32gui  # type: ignore
except ImportError:
    win32con = None  # type: ignore
    win32gui = None  # type: ignore

__all__ = [
    "sys",
    "tk",
    "Image",
    "ImageTk",
    "cv2",
    "mp",
    "win32con",
    "win32gui",
]

