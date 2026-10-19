package com.huocatdesk

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

/** Kotlin 加密层对 RFC 官方向量的已知答案回归（与桌面端 crypto.py 同源）。 */
class CryptoTest {

    private fun h(s: String) = s.replace(" ", "").chunked(2).map { it.toInt(16).toByte() }.toByteArray()

    @Test fun chacha20Block_zeroKeyNonce_counter0() {
        // RFC 8439 A.4 TV1：零密钥零 nonce，块前 32 字节一次性密钥
        val block = Crypto.chacha20Block(ByteArray(32), 0, ByteArray(12))
        assertArrayEquals(
            h("76b8e0ada0f13d90405d6ae55386bd28bdd219b8a08ded1aa836efcc8b770dc7"),
            block.copyOfRange(0, 32))
    }

    @Test fun x25519_rfc7748_5_2_v1() {
        val out = Crypto.x25519(
            h("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4"),
            h("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c"))
        assertArrayEquals(
            h("c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552"), out)
    }

    @Test fun x25519_rfc7748_5_2_v2_highBitU() {
        // u 末字节 0x93 最高位为 1，验证屏蔽逻辑
        val out = Crypto.x25519(
            h("4b66e9d4d1b4673c5ad22691957d6af5c11b6421e0ea01d42ca4169e7918ba0d"),
            h("e5210f12786811d3f4b7959d0538ae2c31dbe7106fc03c3efc4cd549c715a493"))
        assertArrayEquals(
            h("95cbde9476e8907d7aade45cb4b873f88b595a68799fa152e6f8f7647aac7957"), out)
    }

    @Test fun poly1305_rfc8439_A3_TV4() {
        val msg = "'Twas brillig, and the slithy toves\nDid gyre and gimble in the wabe:\nAll mimsy were the borogoves,\nAnd the mome raths outgrabe.".toByteArray()
        val tag = Crypto.poly1305(
            h("1c9240a5eb55d38af333888604f6b5f0473917c1402b80099dca5cbc207075c0"), msg)
        assertArrayEquals(h("4541669a7eaaee61e708dc7cbcc5eb62"), tag)
    }

    @Test fun hkdf_rfc5869_TC1() {
        val okm = Crypto.hkdfSha256(
            ByteArray(22) { 0x0b },
            h("000102030405060708090a0b0c"),
            h("f0f1f2f3f4f5f6f7f8f9"), 42)
        assertArrayEquals(
            h("3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"), okm)
    }

    @Test fun aead_rfc8439_2_8_2() {
        // §2.8.2 官方示例：seal 应精确复现官方 nonce+ct+tag
        val key = h("808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9f")
        val nonce = h("070000004041424344454647")
        val aad = h("50515253c0c1c2c3c4c5c6c7")
        val pt = "Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, sunscreen would be it.".toByteArray()
        val blob = Crypto.aeadSeal(key, nonce, pt, aad)
        val expectedCt = h(
            "d31a8d34648e60db7b86afbc53ef7ec2a4aded51296e08fea9e2b5a736ee62d6" +
            "3dbea45e8ca9671282fafb69da92728b1a71de0a9e060b2905d6a5b67ecd3b36" +
            "92ddbd7f2d778b8c9803aee328091b58fab324e4fad675945585808b4831d7bc" +
            "3ff4def08e4b7a9de576d26586cec64b6116")
        val expectedTag = h("1ae10b594f09e26a7e902ecbd0600691")
        // blob = nonce(12) + ct(114) + tag(16)
        assertArrayEquals(expectedCt, blob.copyOfRange(12, 12 + expectedCt.size))
        assertArrayEquals(expectedTag, blob.copyOfRange(blob.size - 16, blob.size))
        // roundtrip
        assertArrayEquals(pt, Crypto.aeadOpen(key, blob, aad))
    }

    @Test fun invite_roundtrip() {
        val kp = P2p.newKeyPair()
        val code = P2p.makeInvite(kp.public, "203.0.113.42" to 48523)
        val (pub, ep) = P2p.parseInvite(code)
        assertArrayEquals(kp.public, pub)
        assertEquals("203.0.113.42" to 48523, ep)
    }
}
