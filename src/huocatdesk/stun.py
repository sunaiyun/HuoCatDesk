"""STUN 客户端（RFC 5389 子集）：获取 NAT 公网映射地址 + 打洞保活。

只实现 Binding Request 与 XOR-MAPPED-ADDRESS 解析，足以支撑纯 P2P 的 UDP 打洞。
公共 STUN 服务器列表内置，失败自动轮换。
"""
from __future__ import annotations

import ipaddress
import os
import socket
import struct
import time

MAGIC_COOKIE = 0x2112A442
BINDING_REQUEST = 0x0001
BINDING_SUCCESS = 0x0100
ATTR_XOR_MAPPED = 0x0020
ATTR_MAPPED = 0x0001

# 公共 STUN，按可用性排序
STUN_SERVERS = [
    ("stun.l.google.com", 19302),
    ("stun1.l.google.com", 19302),
    ("stun2.l.google.com", 19302),
    ("stun.miwifi.com", 3478),
    ("stun.qq.com", 3478),
    ("stun.cdnbye.com", 3478),
]


def _binding_request() -> tuple[bytes, bytes]:
    """构造 Binding Request，返回 (报文, transaction_id)。"""
    tid = os.urandom(12)
    # type(2)=0001, len(2)=0, magic(4), tid(12) -> 20 字节，无属性
    return struct.pack(">HHI", BINDING_REQUEST, 0, MAGIC_COOKIE) + tid, tid


def _parse_xor_mapped(attr_value: bytes, tid: bytes):
    """解析 XOR-MAPPED-ADDRESS，返回 (ip_str, port) 或 None。"""
    if len(attr_value) < 8:
        return None
    family = attr_value[1]
    if family != 0x01:  # 只处理 IPv4
        return None
    xport = struct.unpack_from(">H", attr_value, 2)[0]
    port = xport ^ (MAGIC_COOKIE >> 16)
    ip_bytes = attr_value[4:8]
    key = struct.pack(">I", MAGIC_COOKIE) + tid
    ip = bytes(b ^ key[i] for i, b in enumerate(ip_bytes))
    try:
        return str(ipaddress.IPv4Address(ip)), port
    except (ValueError, ipaddress.AddressValueError):
        return None


def query(sock: socket.socket, server: tuple, timeout: float = 3.0):
    """向 server 发 Binding Request，返回 (ip, port) 或 None。"""
    req, tid = _binding_request()
    try:
        sock.sendto(req, server)
    except OSError:
        return None
    sock.settimeout(timeout)
    try:
        data, _ = sock.recvfrom(2048)
    except socket.timeout:
        return None
    except OSError:
        return None
    if len(data) < 20:
        return None
    msg_type, msg_len, cookie = struct.unpack_from(">HHI", data, 0)
    if cookie != MAGIC_COOKIE or msg_type != BINDING_SUCCESS:
        return None
    resp_tid = data[8:20]
    if resp_tid != tid:
        return None
    off = 20
    end = min(20 + msg_len, len(data))
    result = None
    while off + 4 <= end:
        atype, alen = struct.unpack_from(">HH", data, off)
        aval = data[off + 4: off + 4 + alen]
        if atype == ATTR_XOR_MAPPED:
            r = _parse_xor_mapped(aval, resp_tid)
            if r:
                result = r
        elif atype == ATTR_MAPPED and len(aval) >= 8 and aval[1] == 0x01:
            # 非异或映射（个别服务器），port/ip 明文
            port = struct.unpack_from(">H", aval, 2)[0]
            ip = str(ipaddress.IPv4Address(bytes(aval[4:8])))
            result = (ip, port)
        off += 4 + alen
        off += (4 - (alen % 4)) % 4  # 4 字节对齐填充
    return result


def discover(sock: socket.socket, timeout: float = 3.0):
    """轮询公共 STUN，返回第一个成功的 ((ip, port), server)。全失败返回 (None, None)。"""
    for srv in STUN_SERVERS:
        try:
            r = query(sock, srv, timeout)
        except Exception:
            r = None
        if r:
            return r, srv
    return None, None


def keepalive(sock: socket.socket, server: tuple, interval: float = 25.0):
    """定期发空 Binding Request 维持 NAT 映射（NAT 端口保活）。"""
    req, _ = _binding_request()
    try:
        sock.sendto(req, server)
    except OSError:
        pass
