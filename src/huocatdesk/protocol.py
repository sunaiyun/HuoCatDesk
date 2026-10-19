"""HuoCatDesk 线协议：UDP 分帧 + 消息类型定义。

帧（明文头 + 应用 body）：
    MAGIC(4) b"P2PD" | type(1) | flags(1) | len(4, BE) | body(len)
- len 是 body 字节数；单 UDP 报文 body 上限约 65000，大块由上层分片。
- flags bit0 = body 已加密（会话后 body = nonce(12) + ciphertext + tag(16)）；
  握手帧 bit0=0 明文。
- protocol 只管分帧；body 的加密/解密由 p2p 层负责。
"""
from __future__ import annotations

import struct

MAGIC = b"P2PD"
HEADER = struct.Struct(">4sBBI")  # magic, type, flags, len
HEADER_LEN = HEADER.size  # 10

# 消息类型
HELLO = 1        # 握手：body = pubkey(32) + ts(8)（明文）
HELLO_ACK = 2    # 握手应答：body = pubkey(32) + ts(8)（明文）
SCREEN = 3       # 屏幕帧：body = seq(4) + ts(8) + w(2) + h(2) + jpeg
KEY = 4          # 键盘：body = vkcode(4) + state(1: 1=down 0=up)
MOUSE = 5        # 鼠标：body = x(2) + y(2) + buttons(1) + wheel(1)
FILE_META = 6    # 文件元信息：body = id(1) + name_len(2) + name + size(8)
FILE_DATA = 7    # 文件数据：body = id(1) + offset(8) + data
FILE_END = 8     # 文件结束：body = id(1) + sha256(32)
HEARTBEAT = 9    # 心跳：body = ts(8)
BYE = 10         # 离开：body = 空
ACK = 11         # 可靠确认：body = what_type(1) + seq(4)

FLAG_ENC = 0x01
MAX_BODY = 65000


def pack(msg_type: int, body: bytes, flags: int = 0) -> bytes:
    """组装一帧。"""
    if len(body) > MAX_BODY:
        raise ValueError(f"body 过长: {len(body)} > {MAX_BODY}")
    return HEADER.pack(MAGIC, msg_type, flags, len(body)) + body


def parse(buf: bytes) -> tuple[int, int, bytes]:
    """解析一帧，返回 (type, flags, body)。帧不完整或 magic 错抛 ValueError。"""
    if len(buf) < HEADER_LEN:
        raise ValueError("帧过短")
    magic, mtype, flags, n = HEADER.unpack_from(buf)
    if magic != MAGIC:
        raise ValueError("magic 不匹配")
    if len(buf) < HEADER_LEN + n:
        raise ValueError("帧不完整")
    return mtype, flags, buf[HEADER_LEN:HEADER_LEN + n]


TYPE_NAMES = {
    HELLO: "HELLO", HELLO_ACK: "HELLO_ACK", SCREEN: "SCREEN", KEY: "KEY",
    MOUSE: "MOUSE", FILE_META: "FILE_META", FILE_DATA: "FILE_DATA",
    FILE_END: "FILE_END", HEARTBEAT: "HEARTBEAT", BYE: "BYE", ACK: "ACK",
}
