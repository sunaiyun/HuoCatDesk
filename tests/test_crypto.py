"""crypto 模块的已知答案测试（Known-Answer Test）。

所有向量都取自 RFC 官方文档：
  - X25519: RFC 7748 §5.2（两个独立向量 + 迭代向量）与 §6.1（DH 场景）
  - ChaCha20 块函数: RFC 8439 §2.3.2
  - Poly1305: RFC 8439 附录 A.3（向量 1-11，含约简边界用例）
  - Poly1305 一次性密钥生成: RFC 8439 附录 A.4
  - ChaCha20-Poly1305 AEAD: RFC 8439 §2.8.2 与附录 A.5
  - HKDF-SHA256: RFC 5869 附录 A.1 / A.2 / A.3（SHA-256 测试用例）

测试同时覆盖两种后端：纯 Python 参考实现（始终可用）与 cryptography 后端
（装了就用）。因此无论用户机器上装没装 cryptography，加密层都有被验证过。

可直接运行（不依赖 pytest）：
    python tests/test_crypto.py
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import huocatdesk.crypto as crypto  # noqa: E402


def _h(hexstr: str) -> bytes:
    return bytes.fromhex(hexstr.replace(" ", ""))


# ---------------------------------------------------------------------------
# X25519（RFC 7748 §5.2）
# ---------------------------------------------------------------------------
_X25519_VECTORS = [
    (
        "a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4",
        "e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c",
        "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552",
    ),
    (
        "4b66e9d4d1b4673c5ad22691957d6af5c11b6421e0ea01d42ca4169e7918ba0d",
        "e5210f12786811d3f4b7959d0538ae2c31dbe7106fc03c3efc4cd549c715a493",
        "95cbde9476e8907d7aade45cb4b873f88b595a68799fa152e6f8f7647aac7957",
    ),
]

# RFC 7748 §5.2 的迭代向量：k0 = u0 = 基点，迭代一次后 k 的值
_X25519_ITER_START = "09" + "00" * 31
_X25519_ITER_1 = "422c8e7a6227d7bca1350b3e2bb7279f7897b87bb6854b783c60e80311ae3079"

# RFC 7748 §6.1 DH 测试向量
_DH_A = "77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a"
_DH_B = "5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb"
_DH_A_PUB = "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"
_DH_B_PUB = "de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f"
_DH_SECRET = "4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742"


def test_x25519_kat_ref():
    """纯 Python 参考实现对 RFC 7748 §5.2 两个向量。"""
    for k_hex, u_hex, out_hex in _X25519_VECTORS:
        out = crypto._x25519_ref(_h(k_hex), _h(u_hex))
        assert out == _h(out_hex), f"X25519 向量不匹配：输入 {k_hex[:8]}.../{u_hex[:8]}..."


def test_x25519_kat_api():
    """公共 API 必须给出同样结果（无论走哪个后端）。"""
    for k_hex, u_hex, out_hex in _X25519_VECTORS:
        assert crypto.x25519(_h(k_hex), _h(u_hex)) == _h(out_hex)


def test_x25519_iteration():
    """RFC 7748 §5.2 迭代向量（k := X25519(k, u); u := 旧 k）。"""
    k, u = _h(_X25519_ITER_START), _h(_X25519_ITER_START)
    k = crypto._x25519_ref(k, u)
    assert k == _h(_X25519_ITER_1)


def test_x25519_dh_rfc7748_6_1():
    """RFC 7748 §6.1：公钥与共享密钥全部对上。"""
    assert crypto._x25519_ref(_h(_DH_A), crypto.BASE_POINT_U) == _h(_DH_A_PUB)
    assert crypto._x25519_ref(_h(_DH_B), crypto.BASE_POINT_U) == _h(_DH_B_PUB)
    assert crypto._x25519_ref(_h(_DH_A), _h(_DH_B_PUB)) == _h(_DH_SECRET)
    assert crypto._x25519_ref(_h(_DH_B), _h(_DH_A_PUB)) == _h(_DH_SECRET)


def test_x25519_accepts_noncanonical_u():
    """RFC 7748 §5：非规范 u 必须先按模约简再计算。"""
    p = 2**255 - 19
    u_noncanonical = (p + 1).to_bytes(32, "little")  # 约简后等于 1
    k = _h("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
    assert crypto._x25519_ref(k, u_noncanonical) == crypto._x25519_ref(
        k, (1).to_bytes(32, "little")
    )


# ---------------------------------------------------------------------------
# ChaCha20 块函数（RFC 8439 §2.3.2）
# ---------------------------------------------------------------------------
_CHACHA_KEY = bytes(range(32))
_CHACHA_NONCE = _h("000000090000004a00000000")
_CHACHA_BLOCK = _h(
    "10f1e7e4d13b5915500fdd1fa32071c4"
    "c7d1f4c733c068030422aa9ac3d46c4e"
    "d2826446079faa0914c2d705d98b02a2"
    "b5129cd1de164eb9cbd083e8a2503c4e"
)


def test_chacha20_block_kat():
    assert crypto._chacha20_block(_CHACHA_KEY, 1, _CHACHA_NONCE) == _CHACHA_BLOCK


def test_chacha20_encrypt_xor_roundtrip():
    data = "HuoCatDesk 加密层的往返测试文本".encode() * 7
    ct = crypto._chacha20(_CHACHA_KEY, 1, _CHACHA_NONCE, data)
    assert ct != data
    assert crypto._chacha20(_CHACHA_KEY, 1, _CHACHA_NONCE, ct) == data
    assert crypto._chacha20(_CHACHA_KEY, 2, _CHACHA_NONCE, data) != ct


def test_chacha20_zero_key_zero_nonce():
    """RFC 8439 附录 A.4 向量 1：零密钥零 nonce 的一次性密钥（块前 32 字节）。"""
    otk = crypto._chacha20_block(b"\x00" * 32, 0, b"\x00" * 12)[:32]
    assert otk == _h("76b8e0ada0f13d90405d6ae55386bd28bdd219b8a08ded1aa836efcc8b770dc7")


# ---------------------------------------------------------------------------
# Poly1305（RFC 8439 附录 A.3）
# ---------------------------------------------------------------------------
_POLY1305_MSG = (
    b"Any submission to the IETF intended by the Contributor for publication as "
    b"all or part of an IETF Internet-Draft or RFC and any statement made within "
    b"the context of an IETF activity is considered an \"IETF Contribution\". "
    b"Such statements include oral statements in IETF sessions, as well as "
    b"written and electronic communications made at any time or place, which are "
    b"addressed to"
)
_POLY1305_MSG2 = (
    b"'Twas brillig, and the slithy toves\n"
    b"Did gyre and gimble in the wabe:\n"
    b"All mimsy were the borogoves,\n"
    b"And the mome raths outgrabe."
)

_POLY_R36E5 = _h("36e5f6b5c5e06070f0efca96227a863e")  # A.3 TV2/TV3 共用的 128 位分量

_POLY1305_VECTORS = [
    # RFC 8439 A.3 TV1：全零密钥 / 全零文本 -> 全零标签
    (b"\x00" * 32, b"\x00" * 64, b"\x00" * 16),
    # A.3 TV2：r=0 -> 标签只取决于 s
    (b"\x00" * 16 + _POLY_R36E5, _POLY1305_MSG, _POLY_R36E5),
    # A.3 TV3：s=0
    (_POLY_R36E5 + b"\x00" * 16, _POLY1305_MSG,
     _h("f3477e7cd95417af89a6b8794c310cf0")),
    # A.3 TV4：完整 32 字节密钥 + 127 字节文本
    (_h("1c9240a5eb55d38af333888604f6b5f0473917c1402b80099dca5cbc207075c0"),
     _POLY1305_MSG2, _h("4541669a7eaaee61e708dc7cbcc5eb62")),
]
# A.3 TV5-T11（约简/进位边界用例）：由 .tmp/gen_edge_vectors.py 从 RFC 原文生成，避免手抄长 hex 出错
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _poly1305_edge import VECTORS as _POLY1305_EDGE_VECTORS  # noqa: E402


def test_poly1305_kats():
    assert len(_POLY1305_MSG) == 375 and len(_POLY1305_MSG2) == 127
    for key, msg, tag in _POLY1305_VECTORS + _POLY1305_EDGE_VECTORS:
        got = crypto._poly1305(key, msg)
        assert got == tag, f"Poly1305 向量不匹配：key={key.hex()[:16]}... msg={len(msg)}B"
        assert len(got) == 16


def test_poly1305_empty_message_and_16byte_key():
    assert len(crypto._poly1305(_h("36e5f6b5c5e06070f0efca96227a863e"), b"")) == 16
    assert crypto._poly1305(b"\x00" * 16, b"") == crypto._poly1305(b"\x00" * 32, b"")


# ---------------------------------------------------------------------------
# ChaCha20-Poly1305 AEAD（RFC 8439 附录 A.5）
# ---------------------------------------------------------------------------
_AEAD_KEY = _h("1c9240a5eb55d38af333888604f6b5f0473917c1402b80099dca5cbc207075c0")
_AEAD_NONCE = _h("000000000102030405060708")
_AEAD_AAD = _h("f33388860000000000004e91")
_AEAD_CT = _h(
    "64a0861575861af460f062c79be643bd"
    "5e805cfd345cf389f108670ac76c8cb2"
    "4c6cfc18755d43eea09ee94e382d26b0"
    "bdb7b73c321b0100d4f03b7f355894cf"
    "332f830e710b97ce98c8a84abd0b9481"
    "14ad176e008d33bd60f982b1ff37c855"
    "9797a06ef4f0ef61c186324e2b350638"
    "3606907b6a7c02b0f9f6157b53c867e4"
    "b9166c767b804d46a59b5216cde7a4e9"
    "9040c5a40433225ee282a1b0a06c523e"
    "af4534d7f83fa1155b0047718cbc546a"
    "0d072b04b3564eea1b422273f548271a"
    "0bb2316053fa76991955ebd63159434e"
    "cebb4e466dae5a1073a6727627097a10"
    "49e617d91d361094fa68f0ff77987130"
    "305beaba2eda04df997b714d6c6f2c29"
    "a6ad5cb4022b02709b"
)
_AEAD_TAG = _h("ee ad 9d 67 89 0c bb 22 39 23 36 fe a1 85 1f 38")
_AEAD_PT = (
    "Internet-Drafts are draft documents valid for a maximum of six months "
    "and may be updated, replaced, or obsoleted by other documents at any "
    "time. It is inappropriate to use Internet-Drafts as reference "
    "material or to cite them other than as /\u201cwork in progress./\u201d"
).encode("utf-8")


def test_aead_rfc8439_a5():
    """按 RFC 8439 附录 A.5 加密应精确复现官方密文与标签。"""
    assert len(_AEAD_CT) == len(_AEAD_PT) == 265
    ref = crypto._AeadRef(_AEAD_KEY)
    blob = ref._seal_with_nonce(_AEAD_NONCE, _AEAD_PT, _AEAD_AAD)
    assert blob == _AEAD_NONCE + _AEAD_CT + _AEAD_TAG
    assert ref.open(_AEAD_NONCE + _AEAD_CT + _AEAD_TAG, _AEAD_AAD) == _AEAD_PT


def test_aead_public_api_matches():
    """公共 API（无论后端）能解开 RFC 官方密文。"""
    aead = crypto.Aead(_AEAD_KEY)
    assert aead.open(_AEAD_NONCE + _AEAD_CT + _AEAD_TAG, _AEAD_AAD) == _AEAD_PT
    fixed = crypto.seal_fixed_nonce(aead, _AEAD_NONCE, _AEAD_PT, _AEAD_AAD)
    assert aead.open(fixed, _AEAD_AAD) == _AEAD_PT


def test_aead_seal_open_roundtrip():
    aead = crypto.Aead(_AEAD_KEY)
    for msg, aad in [(b"", b""), (b"x", b"HuoCatDesk"), (("帧数据" * 10000).encode(), b"aad")]:
        assert aead.open(aead.seal(msg, aad), aad) == msg


def test_aead_tamper_detection():
    aead = crypto.Aead(_AEAD_KEY)
    blob = bytearray(aead.seal(b"hello world", b"aad"))
    blob[5] ^= 0x01  # 改一个字节
    for fn in (
        lambda: aead.open(bytes(blob), b"aad"),
        lambda: aead.open(aead.seal(b"hello world", b"aad"), b"other"),
        lambda: aead.open(blob[2:], b"aad"),
    ):
        try:
            fn()
        except crypto.InvalidTag:
            continue
        raise AssertionError("篡改数据竟然通过了 AEAD 校验")


def test_aead_short_input():
    aead = crypto.Aead(_AEAD_KEY)
    for bad in (b"", b"123", b"123456789012", b"1234567890123456"):
        try:
            aead.open(bad)
        except crypto.InvalidTag:
            continue
        raise AssertionError(f"过短输入未报错：len={len(bad)}")


# ---------------------------------------------------------------------------
# HKDF-SHA256（RFC 5869 附录 A.1 / A.2 / A.3，均为 SHA-256）
# ---------------------------------------------------------------------------
def test_hkdf_rfc5869_tc1():
    """RFC 5869 A.1 测试用例 1：基本 SHA-256 用例。"""
    okm = crypto.hkdf_sha256(
        b"\x0b" * 22,
        salt=bytes.fromhex("000102030405060708090a0b0c"),
        info=bytes.fromhex("f0f1f2f3f4f5f6f7f8f9"),
        length=42,
    )
    assert okm == _h("3cb25f25faacd57a90434f64d0362f2a"
                     "2d2d0a90cf1a5a4c5db02d56ecc4c5bf"
                     "34007208d5b887185865")


def test_hkdf_rfc5869_tc2():
    """RFC 5869 A.2 测试用例 2：长输入长输出（80/80/80 字节，L=82）。"""
    okm = crypto.hkdf_sha256(
        bytes(range(0x00, 0x50)),          # 80 字节 IKM
        salt=bytes(range(0x60, 0xB0)),     # 80 字节 salt
        info=bytes(range(0xB0, 0x100)),    # 80 字节 info
        length=82,
    )
    assert okm == _h("b11e398dc80327a1c8e7f78c596a49344f012eda2d4efad8a050cc4c19afa97c"
                     "59045a99cac7827271cb41c65e590e09da3275600c2f09b8367793a9aca3db71"
                     "cc30c58179ec3e87c14c01d5c1f3434f1d87")


def test_hkdf_rfc5869_tc3():
    """RFC 5869 A.3 测试用例 3：空 salt/info（salt 默认为 32 个 0）。"""
    okm = crypto.hkdf_sha256(b"\x0b" * 22, salt=b"", info=b"", length=42)
    assert okm == _h("8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d"
                     "9d201395faa4b61a96c8")


def test_derive_key_deterministic():
    ikm = b"huocatdesk shared secret material"
    assert crypto.derive_key(ikm, b"ctrl") == crypto.derive_key(ikm, b"ctrl")
    assert crypto.derive_key(ikm, b"ctrl") != crypto.derive_key(ikm, b"frame")
    assert crypto.derive_key(ikm, b"ctrl") != crypto.derive_key(ikm + b"x", b"ctrl")


def test_keypair_agreement():
    """双方各自生成密钥对，交叉计算应得到同一会话密钥。"""
    a, b = crypto.new_keypair(), crypto.new_keypair()
    ka = crypto.derive_key(crypto.x25519(a.private, b.public), b"HuoCatDesk")
    kb = crypto.derive_key(crypto.x25519(b.private, a.public), b"HuoCatDesk")
    assert ka == kb
    c = crypto.new_keypair()
    assert crypto.derive_key(crypto.x25519(a.private, c.public), b"HuoCatDesk") != ka


def test_hmac_sha256_matches_stdlib():
    import hmac as _hmac

    key, data = b"key-key-key-key-key-", b"some data to mac"
    assert crypto.hmac_sha256(key, data) == _hmac.new(key, data, hashlib.sha256).digest()


# ---------------------------------------------------------------------------
def _run_all() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"  ok    {name}")
    total = len(tests)
    print(f"\n加密后端: {crypto.BACKEND}"
          + (f"（{crypto.BACKEND_REASON}）" if crypto.BACKEND_REASON else ""))
    print(f"结果: {total - failed}/{total} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
