"""会话编排。

被控端 HostSession：STUN + 生成邀请码 + 等待连接 + 抓屏推送 + 执行键鼠 + 收文件。
控制端 JoinSession：输入邀请码 + 打洞连接 + 渲染屏 + 转发键鼠 + 发文件。

两端的业务回调由调用方（gui / cli）注入。
"""
from __future__ import annotations

import struct
import threading
import time

from . import crypto, control, protocol as P, screen
from .filexfer import Receiver, Sender
from .p2p import Channel, make_invite, parse_invite


class HostSession:
    """被控端会话。"""

    def __init__(self, on_invite=None, on_status=None, on_connected=None,
                 on_file=None, on_file_progress=None):
        self.kp = crypto.new_keypair()
        self.ch = Channel(self.kp)
        self._on_invite = on_invite
        self._on_status = on_status
        self._on_connected = on_connected
        self._stop = threading.Event()
        self._receiver = Receiver(".", done=on_file, progress=on_file_progress)

    def start(self, timeout: float = 8.0) -> None:
        if self._on_status:
            self._on_status("正在探测公网地址...")
        ep = self.ch.discover(timeout)
        if not ep:
            raise RuntimeError("STUN 探测失败：无法获取公网地址，请检查网络")
        invite = make_invite(self.kp.public, ep)
        if self._on_invite:
            self._on_invite(invite)
        self.ch.on(P.KEY, self._on_key)
        self.ch.on(P.MOUSE, self._on_mouse)
        self._receiver.install(self.ch)
        self.ch.on(P.BYE, lambda b, a: self._stop.set())
        self.ch.listen()
        if self._on_status:
            self._on_status("等待对方连接...")
        threading.Thread(target=self._wait, daemon=True).start()

    def _wait(self) -> None:
        self.ch.wait_connected()
        if self._on_connected:
            self._on_connected()
        self._stream_loop()

    def _stream_loop(self) -> None:
        seq = 0
        fps = 0.05  # ~20fps
        while not self._stop.is_set() and self.ch.connected:
            seq = (seq + 1) & 0xFFFFFFFF
            w, h, jpg = screen.grab()
            if not jpg:
                time.sleep(0.05)
                continue
            body = (struct.pack(">I", seq) + struct.pack(">Q", int(time.time() * 1000))
                    + struct.pack(">HH", w, h) + jpg)
            self.ch.send(P.SCREEN, body)
            time.sleep(fps)

    def _on_key(self, body: bytes, addr) -> None:
        code, = struct.unpack_from(">I", body, 0)
        state = body[4]
        control.key(code, bool(state))

    def _on_mouse(self, body: bytes, addr) -> None:
        x, y, buttons, wheel = struct.unpack_from(">HHBb", body, 0)
        control.mouse(x / 65535.0, y / 65535.0, buttons, wheel)

    def send_file(self, path: str) -> None:
        Sender(self.ch, path).run()

    def stop(self) -> None:
        self._stop.set()
        self.ch.close()


class JoinSession:
    """控制端会话。"""

    def __init__(self, on_frame=None, on_status=None, on_connected=None,
                 on_file=None, on_file_progress=None):
        self.kp = crypto.new_keypair()
        self.ch = Channel(self.kp)
        self._on_frame = on_frame
        self._on_status = on_status
        self._on_connected = on_connected
        self._receiver = Receiver(".", done=on_file, progress=on_file_progress)

    def connect(self, invite_code: str, timeout: float = 20.0) -> bool:
        if self._on_status:
            self._on_status("解析邀请码...")
        peer_pub, peer_ep = parse_invite(invite_code)
        if self._on_status:
            self._on_status(f"打洞连接 {peer_ep[0]}:{peer_ep[1]} ...")
        self.ch.on(P.SCREEN, self._on_screen)
        self._receiver.install(self.ch)
        self.ch.connect_to(peer_pub, peer_ep)
        ok = self.ch.wait_connected(timeout)
        if not ok:
            raise RuntimeError(f"连接超时（{timeout}s）：对方未响应，可能 NAT 类型不支持直连")
        if self._on_connected:
            self._on_connected()
        return True

    def _on_screen(self, body: bytes, addr) -> None:
        # body = seq(4) + ts(8) + w(2) + h(2) + jpeg
        w, h = struct.unpack_from(">HH", body, 12)
        jpg = body[16:]
        if self._on_frame:
            try:
                self._on_frame(w, h, jpg)
            except Exception:
                pass

    def send_key(self, vk_code: int, down: bool) -> None:
        self.ch.send(P.KEY, struct.pack(">IB", vk_code, 1 if down else 0))

    def send_mouse(self, x_norm: float, y_norm: float, buttons: int, wheel: int = 0) -> None:
        x = int(max(0.0, min(1.0, x_norm)) * 65535)
        y = int(max(0.0, min(1.0, y_norm)) * 65535)
        self.ch.send(P.MOUSE, struct.pack(">HHBb", x, y, buttons, wheel))

    def send_file(self, path: str) -> None:
        Sender(self.ch, path).run()

    def stop(self) -> None:
        self.ch.close()
