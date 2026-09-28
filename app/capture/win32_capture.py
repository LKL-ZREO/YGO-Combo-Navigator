from __future__ import annotations

import ctypes

import numpy as np
import win32gui
import win32ui

from app.capture.models import PixelRect, WindowInfo


PW_CLIENTONLY = 0x00000001
PW_RENDERFULLCONTENT = 0x00000002


class Win32WindowCapture:
    """Capture a Windows client area even when another window overlaps it."""

    def capture_window(self, window: WindowInfo) -> np.ndarray:
        left, top, right, bottom = win32gui.GetClientRect(window.handle)
        rect = PixelRect(left=left, top=top, width=right - left, height=bottom - top)
        rect.validate()

        source_handle = win32gui.GetDC(window.handle)
        if not source_handle:
            raise RuntimeError("无法获取 Master Duel 窗口设备上下文")

        source_dc = None
        memory_dc = None
        bitmap = None
        try:
            source_dc = win32ui.CreateDCFromHandle(source_handle)
            memory_dc = source_dc.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(source_dc, rect.width, rect.height)
            memory_dc.SelectObject(bitmap)

            flags = PW_CLIENTONLY | PW_RENDERFULLCONTENT
            rendered = ctypes.windll.user32.PrintWindow(
                window.handle,
                memory_dc.GetSafeHdc(),
                flags,
            )
            if not rendered:
                raise RuntimeError("Windows 无法读取 Master Duel 窗口画面")

            bgra = np.frombuffer(bitmap.GetBitmapBits(True), dtype=np.uint8).reshape(
                rect.height,
                rect.width,
                4,
            )
            frame = np.ascontiguousarray(bgra[:, :, :3])
            if not np.any(frame):
                raise RuntimeError("Master Duel 窗口返回了空白画面")
            return frame
        finally:
            if bitmap is not None:
                win32gui.DeleteObject(bitmap.GetHandle())
            if memory_dc is not None:
                memory_dc.DeleteDC()
            if source_dc is not None:
                source_dc.DeleteDC()
            win32gui.ReleaseDC(window.handle, source_handle)
