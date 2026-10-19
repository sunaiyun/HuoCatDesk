"""HuoCatDesk 加密层：后端无关的对称/非对称接口 + 纯 Python 参考实现。

对外接口
    new_keypair()          -> KeyPair(public, private)   各 32 字节（X25519）
    x25519(priv, peer_pub) -> bytes(32)                  DH 共享值
    derive_key(ikm, info)  -> bytes(32)                  HKDF-SHA256 (RFC 5869)
    Aead(key)              -> .seal(pt, aad) / .open(blob, aad)   ChaCha20-Poly1305
    hmac_sha256(key, data) -> bytes(32)
    InvalidTag             AEAD 认证失败异常

后端选择
    装了 PyPI 的 ``cryptography`` 包就用它（快，且经过审计）；否则自动回退到本模块
    内的纯 Python 参考实现（X25519 按 RFC 7748 §5，ChaCha20 / Poly1305 / AEAD 按
    RFC 8439 §2.3/2.5/2.8，HKDF 按 RFC 5869）。两套实现都被
    ``tests/test_crypto.py`` 用 RFC 官方测试向量做已知答案校验，因此回退实现不是
    "未经验证的代码"。``BACKEND`` 变量记录当前实际使用的后端。
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import os
import struct
from dataclasses import dataclass

__all__ = [
    "KeyPair",
    "new_keypair",
    "x25519",
    "derive_key",
    "Aead",
    "seal_fixed_nonce",
    "InvalidTag",
    "hmac_sha256",
    "hkdf_sha256",
    "BASE_POINT_U",
    "BACKEND",
]

# 线上格式统一约定：nonce(12) || ciphertext || tag(16)
NONCE_LEN = 12
TAG_LEN = 16
KEY_LEN = 32


class InvalidTag(ValueError):
    """AEAD 认证标签校验失败：数据被篡改，或双方密钥不一致。"""


# ----------------------------------------------------------------------------
# 可选依赖：优先使用 cryptography
# ----------------------------------------------------------------------------
try:  # pragma: no cover - 取决于运行环境
    from cryptography.hazmat.primitives.asymmetric import x25519 as _x509_mod
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305 as _ChaCha20Poly1305

    _HAS_LIB = True
    BACKEND = "cryptography"
    BACKEND_REASON = ""
except Exception as _exc:  # pragma: no cover
    _x509_mod = None  # type: ignore[assignment]
    _ChaCha20Poly1305 = None  # type: ignore[assignment]
    _HAS_LIB = False
    BACKEND = "pure-python"
    BACKEND_REASON = f"{type(_exc).__name__}: {_exc}"


# ----------------------------------------------------------------------------
# 纯 Python 参考实现：X25519 (RFC 7748 §5)
# ----------------------------------------------------------------------------
_P = 2**255 - 19
_A24 = 121665  # (A - 2) / 4, A = 486662
BASE_POINT_U = b"\x09" + b"\x00" * 31  # curve25519 基点的 u 坐标
_TOP_BIT_MASK = (1 << 255) - 1  # X25519 输出前的 top-bit masking，必须恰好是 255 位
_M32 = 0xFFFFFFFF


def _x25519_ref(private_key: bytes, peer_public_u: bytes) -> bytes:
    """X25519，逐句翻译自 RFC 7748 §5 的 Montgomery ladder 伪代码。"""
    if len(private_key) != 32 or len(peer_public_u) != 32:
        raise ValueError("X25519 的输入必须都是 32 字节")

    scalar = bytearray(private_key)
    scalar[0] &= 248   # 清最低 3 位
    scalar[31] &= 127  # 清最高位
    scalar[31] |= 64   # 置次高位
    k = int.from_bytes(scalar, "little")

    p = _P
    peer_u = bytearray(peer_public_u)
    peer_u[31] &= 127  # RFC 7748 §5：接收方必须屏蔽对端 u 坐标的最高位
    x1 = int.from_bytes(peer_u, "little") % p  # 接受非规范值并按模约简
    x2, z2 = 1, 0
    x3, z3 = x1, 1
    swap = 0
    for t in range(254, -1, -1):
        kt = (k >> t) & 1
        swap ^= kt
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = kt
        a = (x2 + z2) % p
        aa = pow(a, 2, p)
        b = (x2 - z2) % p
        bb = pow(b, 2, p)
        e = (aa - bb) % p
        c = (x3 + z3) % p
        d = (x3 - z3) % p
        da = d * a % p
        cb = c * b % p
        x3 = pow((da + cb) % p, 2, p)
        z3 = x1 * pow((da - cb) % p, 2, p) % p
        x2 = aa * bb % p
        z2 = e * ((aa + _A24 * e) % p) % p
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
    out = (x2 * pow(z2, p - 2, p)) % p & _TOP_BIT_MASK
    return out.to_bytes(32, "little")


# ----------------------------------------------------------------------------
# 纯 Python 参考实现：ChaCha20 (RFC 8439 §2.3 / §2.4)
# ----------------------------------------------------------------------------
_CHACHA_CONSTS = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)


def _rotl(value: int, bits: int) -> int:
    return ((value << bits) | (value >> (32 - bits))) & _M32


def _quarter(s: list[int], a: int, b: int, c: int, d: int) -> None:
    s[a] = (s[a] + s[b]) & _M32
    s[d] = _rotl(s[d] ^ s[a], 16)
    s[c] = (s[c] + s[d]) & _M32
    s[b] = _rotl(s[b] ^ s[c], 12)
    s[a] = (s[a] + s[b]) & _M32
    s[d] = _rotl(s[d] ^ s[a], 8)
    s[c] = (s[c] + s[d]) & _M32
    s[b] = _rotl(s[b] ^ s[c], 7)


def _chacha20_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    """ChaCha20 块函数，输出 64 字节。"""
    if len(key) != 32 or len(nonce) != 12:
        raise ValueError("ChaCha20 需要 32 字节密钥与 12 字节 nonce")
    k = struct.unpack("<8I", key)
    n = struct.unpack("<3I", nonce)
    state = list(_CHACHA_CONSTS) + list(k) + [counter & _M32] + list(n)
    initial = list(state)
    for _ in range(10):  # 20 轮 = 10 次（列 + 对角线）
        _quarter(state, 0, 4, 8, 12)
        _quarter(state, 1, 5, 9, 13)
        _quarter(state, 2, 6, 10, 14)
        _quarter(state, 3, 7, 11, 15)
        _quarter(state, 0, 5, 10, 15)
        _quarter(state, 1, 6, 11, 12)
        _quarter(state, 2, 7, 8, 13)
        _quarter(state, 3, 4, 9, 14)
    out = bytearray()
    for i in range(16):
        out += ((state[i] + initial[i]) & _M32).to_bytes(4, "little")
    return bytes(out)


def _xor_bytes(a: bytes, b: bytes) -> bytes:
    """用大整数异或，避免逐字节 Python 循环（对 100KB 级帧体有数量级差异）。"""
    if not a:
        return b""
    return (int.from_bytes(a, "little") ^ int.from_bytes(b, "little")).to_bytes(len(a), "little")


def _chacha20(key: bytes, counter: int, nonce: bytes, data: bytes) -> bytes:
    """ChaCha20 流加密（加密/解密同码），RFC 8439 §2.4。"""
    if not data:
        return b""
    blocks = (len(data) + 63) // 64
    ks = bytearray()
    c = counter & _M32
    for _ in range(blocks):
        ks += _chacha20_block(key, c, nonce)
        c = (c + 1) & _M32
    return _xor_bytes(data, bytes(ks[: len(data)]))


# ----------------------------------------------------------------------------
# 纯 Python 参考实现：Poly1305 (RFC 8439 §2.5) 与 AEAD (RFC 8439 §2.8)
# ----------------------------------------------------------------------------
_POLY_P = 2**130 - 5
# RFC 8439 §2.5.1：clamp(r): r &= 0x0ffffffc0ffffffc0ffffffc0fffffff
_POLY_R_CLAMP = 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF


def _pad16(data: bytes) -> bytes:
    return data + b"\x00" * ((-len(data)) % 16)


def _poly1305(one_time_key: bytes, msg: bytes) -> bytes:
    """Poly1305 认证码。一次性密钥可用完整 32 字节，也可用 16 字节（右半补 0）。"""
    if len(one_time_key) == 16:
        one_time_key = one_time_key + b"\x00" * 16
    if len(one_time_key) != 32:
        raise ValueError("Poly1305 一次性密钥必须是 16 或 32 字节")
    r = int.from_bytes(one_time_key[:16], "little") & _POLY_R_CLAMP
    s = int.from_bytes(one_time_key[16:], "little")  # s 不做 clamp（RFC 8439 §2.5.1）
    acc = 0
    for i in range(0, len(msg), 16):
        chunk = msg[i:i + 16]
        # 每个块都当作 17 字节处理（块后接 0x01），即 n = LE(chunk) + 256**len(chunk)
        acc = ((acc + int.from_bytes(chunk, "little") + (1 << (8 * len(chunk)))) % _POLY_P
               * r) % _POLY_P
    return ((acc + s) % 2**128).to_bytes(16, "little")


class _AeadRef:
    """ChaCha20-Poly1305 AEAD，RFC 8439 §2.8。"""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("ChaCha20-Poly1305 密钥必须是 32 字节")
        self._key = key

    def seal(self, plaintext: bytes, aad: bytes = b"") -> bytes:
        nonce = os.urandom(NONCE_LEN)
        return self._seal_with_nonce(nonce, plaintext, aad)

    def _seal_with_nonce(self, nonce: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
        ct = _chacha20(self._key, 1, nonce, plaintext)
        # RFC 8439 §2.4/§2.8：一次性密钥是 256 位（块前 32 字节：r 128 位 + s 128 位，全部使用）
        otk = _chacha20_block(self._key, 0, nonce)[:32]
        mac_input = self._mac_input(aad, ct)
        return nonce + ct + _poly1305(otk, mac_input)

    @staticmethod
    def _mac_input(aad: bytes, ct: bytes) -> bytes:
        """RFC 8439 §2.8.1：AAD 和密文都要各自 pad16，末尾再接两个 8 字节长度。"""
        return _pad16(aad) + _pad16(ct) + len(aad).to_bytes(8, "little") + len(ct).to_bytes(8, "little")

    def open(self, blob: bytes, aad: bytes = b"") -> bytes:
        if len(blob) < NONCE_LEN + TAG_LEN:
            raise InvalidTag("数据长度不足，无法解密")
        nonce, ct, tag = blob[:NONCE_LEN], blob[NONCE_LEN:-TAG_LEN], blob[-TAG_LEN:]
        otk = _chacha20_block(self._key, 0, nonce)[:32]
        if not _hmac.compare_digest(_poly1305(otk, self._mac_input(aad, ct)), tag):
            raise InvalidTag("AEAD 认证失败：数据被篡改或密钥不匹配")
        return _chacha20(self._key, 1, nonce, ct)


# ----------------------------------------------------------------------------
# HKDF-SHA256 (RFC 5869)
# ----------------------------------------------------------------------------
def hkdf_sha256(ikm: bytes, salt: bytes = b"", info: bytes = b"", length: int = 32) -> bytes:
    if length <= 0:
        raise ValueError("length 必须为正")
    prk = _hmac.new(salt, ikm, hashlib.sha256).digest()
    okm = b""
    t = b""
    counter = 1
    while len(okm) < length:
        t = _hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
        okm += t
        counter += 1
    return okm[:length]


# ----------------------------------------------------------------------------
# 后端无关的对外接口
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class KeyPair:
    """X25519 密钥对，两个字段都是 32 字节原始字节。"""

    public: bytes
    private: bytes

    def to_public_bytes(self) -> bytes:
        return self.public


def new_keypair() -> KeyPair:
    if _HAS_LIB:  # pragma: no cover - 取决于运行环境
        priv = _x509_mod.X25519PrivateKey.generate()
        enc, fmt = _x509_mod.x25519.RawEncoding, _x509_mod.x25519.NoEncryption
        return KeyPair(priv.public_key().public_bytes(enc, fmt), priv.private_bytes(enc, fmt))
    secret = os.urandom(32)
    return KeyPair(_x25519_ref(secret, BASE_POINT_U), secret)


def x25519(private_key: bytes, peer_public_u: bytes) -> bytes:
    """X25519 标量乘，返回 32 字节共享值。"""
    if _HAS_LIB:  # pragma: no cover - 取决于运行环境
        enc, fmt = _x509_mod.x25519.RawEncoding, _x509_mod.x25519.NoEncryption
        priv = _x509_mod.X25519PrivateKey.from_private_bytes(private_key)
        pub = _x509_mod.X25519PublicKey.from_public_bytes(peer_public_u)
        return priv.exchange(pub)
    return _x25519_ref(private_key, peer_public_u)


def derive_key(ikm: bytes, info: bytes = b"") -> bytes:
    """HKDF-SHA256，固定输出 32 字节会话密钥。"""
    return hkdf_sha256(ikm, salt=b"", info=info, length=KEY_LEN)


class Aead:
    """后端无关的 ChaCha20-Poly1305：线上格式 ``nonce(12) || ct || tag(16)``。"""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("AEAD 密钥必须是 32 字节")
        self._impl: _AeadRef | _ChaCha20Poly1305 = (  # type: ignore[assignment]
            _ChaCha20Poly1305(key) if _HAS_LIB else _AeadRef(key)  # type: ignore[arg-type]
        )

    def seal(self, plaintext: bytes, aad: bytes = b"") -> bytes:
        nonce = os.urandom(NONCE_LEN)
        if _HAS_LIB:
            return nonce + self._impl.encrypt(nonce, plaintext, aad)  # type: ignore[union-attr]
        return self._impl.seal(plaintext, aad)  # type: ignore[union-attr]

    def open(self, blob: bytes, aad: bytes = b"") -> bytes:
        if len(blob) < NONCE_LEN + TAG_LEN:
            raise InvalidTag("数据长度不足，无法解密")
        nonce, payload = blob[:NONCE_LEN], blob[NONCE_LEN:]
        if _HAS_LIB:
            try:
                return self._impl.decrypt(nonce, payload, aad)  # type: ignore[union-attr]
            except Exception as exc:
                raise InvalidTag("AEAD 认证失败：数据被篡改或密钥不匹配") from exc
        return self._impl.open(blob, aad)  # type: ignore[union-attr]


def seal_fixed_nonce(aead: Aead, nonce: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """用指定的 nonce 封装，仅用于复现 RFC 官方测试向量。"""
    if len(nonce) != NONCE_LEN:
        raise ValueError("nonce 必须是 12 字节")
    if _HAS_LIB:
        return nonce + aead._impl.encrypt(nonce, plaintext, aad)  # type: ignore[union-attr]
    return aead._impl._seal_with_nonce(nonce, plaintext, aad)  # type: ignore[attr-defined]


def hmac_sha256(key: bytes, data: bytes) -> bytes:
    return _hmac.new(key, data, hashlib.sha256).digest()
