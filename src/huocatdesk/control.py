"""键鼠事件执行。Windows 用 SendInput（ctypes，无第三方依赖），其它平台占位。

坐标约定：x/y 为归一化值 0..1（控制端按屏幕宽高归一化后发送）。
buttons 位掩码：bit0=左, bit1=右, bit2=中。wheel 正=上滚，负=下滚。
"""
from __future__ import annotations

import sys

_is_win = sys.platform == "win32"

if _is_win:
    import ctypes
    from ctypes import wintypes

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_ABSOLUTE = 0x8000
    KEYEVENTF_KEYUP = 0x0002
    WHEEL_DELTA = 120

    ULONG_PTR = ctypes.POINTER(wintypes.ULONG)

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class _INPUT(ctypes.Structure):
        class _in(ctypes.Union):
            _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]
        _anonymous_ = ["_in"]
        _fields_ = [("type", wintypes.DWORD), ("_in", _in)]

    _user32 = ctypes.windll.user32
    _user32.SetProcessDPIAware()
    _prev_buttons = 0

    def _send(*inputs: "_INPUT") -> None:
        n = len(inputs)
        arr = (_INPUT * n)(*inputs)
        _user32.SendInput(n, ctypes.byref(arr), ctypes.sizeof(_INPUT))

    def move(x: float, y: float) -> None:
        """移动到归一化绝对坐标。"""
        ax = int(max(0.0, min(1.0, x)) * 65535)
        ay = int(max(0.0, min(1.0, y)) * 65535)
        mi = _MOUSEINPUT(dx=ax, dy=ay, mouseData=0,
                         dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, time=0,
                         dwExtraInfo=None)
        inp = _INPUT(type=INPUT_MOUSE)
        inp.mi = mi
        _send(inp)

    def _button_flag(button: int, down: bool) -> int:
        if button == 0:  # 左
            return MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
        if button == 1:  # 右
            return MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP
        return MOUSEEVENTF_MIDDLEDOWN if down else MOUSEEVENTF_MIDDLEUP

    def mouse(x: float, y: float, buttons: int, wheel: int = 0) -> None:
        """执行鼠标事件：移动 + 按键状态变化 + 滚轮。"""
        global _prev_buttons
        ax = int(max(0.0, min(1.0, x)) * 65535)
        ay = int(max(0.0, min(1.0, y)) * 65535)
        flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
        if wheel:
            flags |= MOUSEEVENTF_WHEEL
        mi = _MOUSEINPUT(dx=ax, dy=ay, mouseData=wheel * WHEEL_DELTA,
                         dwFlags=flags, time=0, dwExtraInfo=None)
        _send(_INPUT(type=INPUT_MOUSE, mi=mi))
        # 按键状态变化：与上次比较，发 down/up
        changed = buttons ^ _prev_buttons
        extra = []
        for b in range(3):
            if changed & (1 << b):
                extra.append(_INPUT(type=INPUT_MOUSE, mi=_MOUSEINPUT(
                    dx=0, dy=0, mouseData=0,
                    dwFlags=_button_flag(b, bool(buttons & (1 << b))),
                    time=0, dwExtraInfo=None)))
        if extra:
            _send(*extra)
        _prev_buttons = buttons

    def key(vk_code: int, down: bool) -> None:
        """按下/松开一个虚拟键码（Windows VK_*）。"""
        ki = _KEYBDINPUT(wVk=vk_code, wScan=0,
                         dwFlags=0 if down else KEYEVENTF_KEYUP, time=0,
                         dwExtraInfo=None)
        _send(_INPUT(type=INPUT_KEYBOARD, ki=ki))

else:  # 非 Windows：占位，便于跨平台启动调试
    _prev_buttons = 0

    def move(x: float, y: float) -> None:  # noqa: D401
        pass

    def mouse(x: float, y: float, buttons: int, wheel: int = 0) -> None:
        global _prev_buttons
        _prev_buttons = buttons

    def key(vk_code: int, down: bool) -> None:
        pass
