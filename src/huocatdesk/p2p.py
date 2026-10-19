"""HuoCatDesk 连接层：邀请码编码 + UDP 打洞握手 + 加密通道。

纯 P2P（无中转）：双方各自 STUN 得到公网映射地址，把 (公钥 + 公网地址) 编码成
邀请码带外交换（电话/聊天软件）。输入对方邀请码后双向 UDP 打洞，X25519 协商会话
密钥，之后所有帧用 ChaCha20-Poly1305 加密（复用已验证的 crypto.py）。

约定：被控端（host）先生成邀请码并等待；控制端（join）输入邀请码主动打洞。
"""
from __future__ import annotations

import base64
import select
import socket
import struct
import threading
import time

from . import crypto
from . import protocol as P
from . import stun


# ----------------------------------------------------------------------------
# 邀请码：CRC16 + base32，可读、可校验、可口述
# ----------------------------------------------------------------------------
def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return crc & 0xFFFF


def make_invite(pubkey: bytes, public_ep: tuple[str, int]) -> str:
    """把 (公钥 + 公网地址 + 时间戳) 编码成可读邀请码。"""
    ip = socket.inet_aton(public_ep[0])
    port = struct.pack(">H", public_ep[1])
    ts = struct.pack(">I", int(time.time()) & 0xFFFFFFFF)
    raw = pubkey + ip + port + ts  # 32+4+2+4 = 42
    blob = struct.pack(">H", _crc16(raw)) + raw  # 2+42 = 44
    b32 = base64.b32encode(blob).decode("ascii").rstrip("=")
    return "-".join(b32[i:i + 4] for i in range(0, len(b32), 4))


def parse_invite(code: str) -> tuple[bytes, tuple[str, int]]:
    """解析邀请码，返回 (peer_pubkey, (ip, port))。校验失败抛 ValueError。"""
    b32 = code.strip().replace("-", "").replace(" ", "").upper()
    pad = "=" * ((8 - len(b32) % 8) % 8)
    try:
        blob = base64.b32decode(b32 + pad)
    except Exception as e:
        raise ValueError(f"邀请码格式错误: {e}") from e
    if len(blob) < 4:
        raise ValueError("邀请码过短")
    crc = struct.unpack_from(">H", blob, 0)[0]
    raw = blob[2:]
    if _crc16(raw) != crc:
        raise ValueError("邀请码校验失败：输入有误或码已损坏")
    if len(raw) < 42:
        raise ValueError("邀请码内容过短")
    pubkey = raw[:32]
    ip = socket.inet_ntoa(raw[32:36])
    port = struct.unpack_from(">H", raw, 36)[0]
    return pubkey, (ip, port)


# ----------------------------------------------------------------------------
# 加密 P2P 通道
# ----------------------------------------------------------------------------
class Channel:
    """一条加密 P2P 通道：UDP 打洞 + 会话密钥 + 加密收发。"""

    def __init__(self, keypair, local_port: int = 0):
        self.kp = keypair
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", local_port))
        self.local_ep = self.sock.getsockname()
        self.public_ep: tuple[str, int] | None = None
        self.peer_pubkey: bytes | None = None
        self.peer_ep: tuple[str, int] | None = None
        self._aead: crypto.Aead | None = None
        self._connected = threading.Event()
        self._stop = threading.Event()
        self._handlers: dict[int, list] = {}
        self._stun_server = None
        self._threads: list[threading.Thread] = []

    # ---- STUN 公网映射 ----
    def discover(self, timeout: float = 4.0) -> tuple[str, int] | None:
        ep, srv = stun.discover(self.sock, timeout)
        if ep:
            self.public_ep = ep
            self._stun_server = srv
        return ep

    # ---- 消息处理器注册 ----
    def on(self, msg_type: int, fn) -> None:
        self._handlers.setdefault(msg_type, []).append(fn)

    # ---- 发送 ----
    def send(self, msg_type: int, body: bytes) -> None:
        if self.peer_ep is None:
            raise RuntimeError("未设置对端地址")
        if self._aead is not None:
            enc = self._aead.seal(body, aad=bytes([msg_type]))
            frame = P.pack(msg_type, enc, P.FLAG_ENC)
        else:
            frame = P.pack(msg_type, body, 0)
        try:
            self.sock.sendto(frame, self.peer_ep)
        except OSError:
            pass

    def send_reliable(self, msg_type: int, body: bytes, retries: int = 5) -> None:
        """尽力重发（用于控制/文件等需要送达的小消息）。"""
        for _ in range(retries):
            if self._stop.is_set():
                return
            self.send(msg_type, body)
            self._stop.wait(0.05)

    # ---- 连接 ----
    def connect_to(self, peer_pubkey: bytes, peer_ep: tuple[str, int]) -> None:
        self.peer_pubkey = peer_pubkey
        self.peer_ep = peer_ep
        self._start_threads()

    def listen(self) -> None:
        """被控端：只启动收发线程，等对端打洞过来。"""
        self._start_threads()

    def _start_threads(self) -> None:
        if not self._threads:
            self._threads = [
                threading.Thread(target=self._punch_loop, daemon=True),
                threading.Thread(target=self._recv_loop, daemon=True),
                threading.Thread(target=self._keepalive_loop, daemon=True),
            ]
            for t in self._threads:
                t.start()

    def _punch_loop(self) -> None:
        """反复发 HELLO 直到连接建立。被控端也发（双向打洞）。"""
        ts = struct.pack(">Q", int(time.time() * 1000))
        body = self.kp.public + ts
        while not self._stop.is_set() and not self._connected.is_set():
            try:
                frame = P.pack(P.HELLO, body, 0)
                if self.peer_ep:
                    self.sock.sendto(frame, self.peer_ep)
            except OSError:
                pass
            self._stop.wait(0.1)

    def _keepalive_loop(self) -> None:
        while not self._stop.is_set() and self._stun_server:
            stun.keepalive(self.sock, self._stun_server)
            self._stop.wait(25.0)

    def _recv_loop(self) -> None:
        while not self._stop.is_set():
            try:
                r, _, _ = select.select([self.sock], [], [], 0.5)
            except (OSError, ValueError):
                break
            if not r:
                continue
            try:
                data, addr = self.sock.recvfrom(65535)
            except OSError:
                continue
            self._handle_packet(data, addr)

    def _handle_packet(self, data: bytes, addr) -> None:
        try:
            mtype, flags, body = P.parse(data)
        except ValueError:
            return
        if mtype == P.HELLO and not self._connected.is_set():
            self.peer_ep = addr  # 记录实际来源（应对 NAT 重绑定）
            self.peer_pubkey = body[:32]
            self._derive_session()
            ts = struct.pack(">Q", int(time.time() * 1000))
            try:
                self.sock.sendto(P.pack(P.HELLO_ACK, self.kp.public + ts, 0), addr)
            except OSError:
                pass
            return
        if mtype == P.HELLO_ACK and not self._connected.is_set():
            self.peer_ep = addr
            self.peer_pubkey = body[:32]
            self._derive_session()
            return
        if not self._connected.is_set():
            return
        if flags & P.FLAG_ENC:
            if self._aead is None:
                return
            try:
                body = self._aead.open(body, aad=bytes([mtype]))
            except crypto.InvalidTag:
                return
        for fn in self._handlers.get(mtype, []):
            try:
                fn(body, addr)
            except Exception:
                pass

    def _derive_session(self) -> None:
        shared = crypto.x25519(self.kp.private, self.peer_pubkey)
        sk = crypto.derive_key(shared, b"huocatdesk-session-v1")
        self._aead = crypto.Aead(sk)
        self._connected.set()

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def wait_connected(self, timeout: float | None = None) -> bool:
        return self._connected.wait(timeout)

    def close(self) -> None:
        self._stop.set()
        try:
            if self._aead is not None:
                self.send(P.BYE, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
