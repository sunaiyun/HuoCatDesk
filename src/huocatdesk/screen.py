"""屏幕采集：抓全屏 -> 缩放 -> JPEG 编码。

Windows/macOS 用 PIL.ImageGrab（Pillow 自带，跨平台 GDI/CoreGraphics 后端）；
Linux 无 ImageGrab 时回退到截一段占位图（仅用于无桌面环境调试）。
"""
from __future__ import annotations

import io

from PIL import Image, ImageGrab


def grab(quality: int = 55, max_w: int = 1600, max_h: int = 900) -> tuple[int, int, bytes]:
    """抓全屏并编码 JPEG。返回 (width, height, jpeg_bytes)。失败返回 (0, 0, b"")。"""
    try:
        img = ImageGrab.grab()
    except Exception:
        return 0, 0, b""
    w, h = img.size
    if w > max_w or h > max_h:
        img.thumbnail((max_w, max_h), Image.LANCZOS)
        w, h = img.size
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    return w, h, buf.getvalue()


def decode(jpeg: bytes):
    """解 JPEG 为 PIL.Image（控制端渲染用）。"""
    if not jpeg:
        return None
    return Image.open(io.BytesIO(jpeg))
