from __future__ import annotations

import ctypes
from collections.abc import Iterable

import win32gui

from app.capture.models import PixelRect, WindowInfo


DEFAULT_TITLE_KEYWORDS = (
    "master duel",
    "yu-gi-oh! master duel",
    "游戏王：大师决斗",
    "遊戯王 マスターデュエル",
)


def enable_dpi_awareness() -> None:
    """Avoid Windows DPI virtualization when resolving client coordinates."""

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def title_matches(title: str, keywords: Iterable[str] = DEFAULT_TITLE_KEYWORDS) -> bool:
    normalized = title.casefold().strip()
    if not normalized:
        return False

    compact = "".join(character for character in normalized if character.isalnum())
    return any(
        keyword.casefold() in normalized
        or "".join(character for character in keyword.casefold() if character.isalnum()) in compact
        for keyword in keywords
    )


def get_client_rect(handle: int) -> PixelRect:
    left, top, right, bottom = win32gui.GetClientRect(handle)
    screen_left, screen_top = win32gui.ClientToScreen(handle, (left, top))
    screen_right, screen_bottom = win32gui.ClientToScreen(handle, (right, bottom))
    rect = PixelRect(
        left=screen_left,
        top=screen_top,
        width=screen_right - screen_left,
        height=screen_bottom - screen_top,
    )
    rect.validate()
    return rect


def list_visible_windows(*, only_master_duel: bool = True) -> list[WindowInfo]:
    enable_dpi_awareness()
    windows: list[WindowInfo] = []

    def collect(handle: int, _extra: object) -> None:
        if not win32gui.IsWindowVisible(handle) or win32gui.IsIconic(handle):
            return

        title = win32gui.GetWindowText(handle).strip()
        if not title:
            return
        if only_master_duel and not title_matches(title):
            return

        try:
            client_rect = get_client_rect(handle)
        except (ValueError, win32gui.error):
            return

        if client_rect.width < 640 or client_rect.height < 360:
            return

        windows.append(WindowInfo(handle=handle, title=title, client_rect=client_rect))

    win32gui.EnumWindows(collect, None)
    return sorted(windows, key=lambda item: item.title.casefold())

