package com.huocatdesk

import java.io.ByteArrayOutputStream
import java.math.BigInteger
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * HuoCatDesk 加密层（纯 Kotlin，移植自桌面端已用 RFC 官方向量验证过的 crypto.py）。
 * 不依赖系统 ChaCha20/X25519，任意 Android 版本均可运行，且与桌面端逐字节互通。
 *
 *  - X25519: RFC 7748 §5 Montgomery ladder（屏蔽接收 u 最高位 + 输出最高位）
 *  - ChaCha20: RFC 8439 §2.3/§2.4
 *  - Poly1305: RFC 8439 §2.5（r 截断、s 不截断、每块 +2^(8*len)）
 *  - AEAD ChaCha20-Poly1305: RFC 8439 §2.8（一次性密钥 32 字节，密文也 pad16）
 *  - HKDF-SHA256: RFC 5869
 */
object Crypto {

    // ---- X25519 常量 ----
    private val P = BigInteger.valueOf(2).pow(255).subtract(BigInteger.valueOf(19))
    private val A24 = BigInteger.valueOf(121665)
    private val TOP_MASK = BigInteger.valueOf(2).pow(255).subtract(BigInteger.ONE)

    // ---- Poly1305 常量 ----
    private val POLY_P = BigInteger.valueOf(2).pow(130).subtract(BigInteger.valueOf(5))
    private val POLY_RCLAMP = BigInteger("0ffffffc0ffffffc0ffffffc0fffffff", 16)
    private val MOD128 = BigInteger.valueOf(2).pow(128)

    // ====================================================================
    // X25519
    // ====================================================================
    fun x25519(privateKey: ByteArray, peerU: ByteArray): ByteArray {
        require(privateKey.size == 32 && peerU.size == 32) { "X25519 输入必须 32 字节" }
        val k = privateKey.copyOf()
        k[0] = (k[0].toInt() and 248).toByte()
        k[31] = (k[31].toInt() and 127).toByte()
        k[31] = (k[31].toInt() or 64).toByte()
        val scalar = leInt(k)

        val u = peerU.copyOf()
        u[31] = (u[31].toInt() and 127).toByte()  // RFC 7748 §5：屏蔽接收 u 最高位
        val x1 = leInt(u).mod(P)

        var x2 = BigInteger.ONE; var z2 = BigInteger.ZERO
        var x3 = x1; var z3 = BigInteger.ONE
        var swap = 0
        for (t in 254 downTo 0) {
            val kt = scalar.shiftRight(t).and(BigInteger.ONE).toInt()
            swap = swap xor kt
            if (swap == 1) {
                var tmp = x2; x2 = x3; x3 = tmp
                tmp = z2; z2 = z3; z3 = tmp
            }
            swap = kt
            val a = x2.add(z2).mod(P)
            val aa = a.modPow(BigInteger.valueOf(2), P)
            val b = x2.subtract(z2).mod(P)
            val bb = b.modPow(BigInteger.valueOf(2), P)
            val e = aa.subtract(bb).mod(P)
            val c = x3.add(z3).mod(P)
            val d = x3.subtract(z3).mod(P)
            val da = d.multiply(a).mod(P)
            val cb = c.multiply(b).mod(P)
            x3 = da.add(cb).modPow(BigInteger.valueOf(2), P)
            z3 = x1.multiply(da.subtract(cb).modPow(BigInteger.valueOf(2), P)).mod(P)
            x2 = aa.multiply(bb).mod(P)
            z2 = e.multiply(aa.add(A24.multiply(e)).mod(P)).mod(P)
        }
        if (swap == 1) {
            var tmp = x2; x2 = x3; x3 = tmp
            tmp = z2; z2 = z3; z3 = tmp
        }
        val out = x2.multiply(z2.modPow(P.subtract(BigInteger.valueOf(2)), P)).mod(P).and(TOP_MASK)
        return out.toLEBytes(32)
    }

    // ====================================================================
    // ChaCha20
    // ====================================================================
    private fun rotl(x: Int, n: Int): Int = (x shl n) or (x ushr (32 - n))
    private fun quarter(s: IntArray, a: Int, b: Int, c: Int, d: Int) {
        s[a] = s[a] + s[b]
        s[d] = rotl(s[d] xor s[a], 16)
        s[c] = s[c] + s[d]
        s[b] = rotl(s[b] xor s[c], 12)
        s[a] = s[a] + s[b]
        s[d] = rotl(s[d] xor s[a], 8)
        s[c] = s[c] + s[d]
        s[b] = rotl(s[b] xor s[c], 7)
    }
    private fun le32(b: ByteArray, i: Int): Int =
        ((b[i].toInt() and 0xff)) or
        ((b[i + 1].toInt() and 0xff) shl 8) or
        ((b[i + 2].toInt() and 0xff) shl 16) or
        ((b[i + 3].toInt() and 0xff) shl 24)
    private fun put32(v: Int, out: ByteArray, i: Int) {
        out[i] = (v and 0xff).toByte()
        out[i + 1] = ((v ushr 8) and 0xff).toByte()
        out[i + 2] = ((v ushr 16) and 0xff).toByte()
        out[i + 3] = ((v ushr 24) and 0xff).toByte()
    }

    fun chacha20Block(key: ByteArray, counter: Int, nonce: ByteArray): ByteArray {
        require(key.size == 32 && nonce.size == 12)
        val s = IntArray(16)
        s[0] = 0x61707865; s[1] = 0x3320646e; s[2] = 0x79622d32; s[3] = 0x6b206574
        for (i in 0..3) s[4 + i] = le32(key, i * 4)
        for (i in 0..3) s[8 + i] = le32(key, 16 + i * 4)
        s[12] = counter
        for (i in 0..2) s[13 + i] = le32(nonce, i * 4)
        val x = s.copyOf()
        for (round in 0 until 10) {
            quarter(x, 0, 4, 8, 12); quarter(x, 1, 5, 9, 13)
            quarter(x, 2, 6, 10, 14); quarter(x, 3, 7, 11, 15)
            quarter(x, 0, 5, 10, 15); quarter(x, 1, 6, 11, 12)
            quarter(x, 2, 7, 8, 13); quarter(x, 3, 4, 9, 14)
        }
        val out = ByteArray(64)
        for (i in 0 until 16) put32(x[i] + s[i], out, i * 4)
        return out
    }

    fun chacha20(key: ByteArray, counter: Int, nonce: ByteArray, data: ByteArray): ByteArray {
        val out = ByteArray(data.size)
        var off = 0
        var cnt = counter
        while (off < data.size) {
            val block = chacha20Block(key, cnt, nonce)
            val n = minOf(64, data.size - off)
            for (i in 0 until n) out[off + i] = (data[off + i].toInt() xor block[i].toInt()).toByte()
            off += n
            cnt++
        }
        return out
    }

    // ====================================================================
    // Poly1305
    // ====================================================================
    fun poly1305(oneTimeKey: ByteArray, msg: ByteArray): ByteArray {
        val key = if (oneTimeKey.size == 16) oneTimeKey + ByteArray(16) else oneTimeKey
        require(key.size == 32) { "Poly1305 密钥 16 或 32 字节" }
        val r = leInt(key.copyOfRange(0, 16)).and(POLY_RCLAMP)
        val s = leInt(key.copyOfRange(16, 32))
        var acc = BigInteger.ZERO
        var i = 0
        while (i < msg.size) {
            val end = minOf(i + 16, msg.size)
            val chunk = msg.copyOfRange(i, end)
            val n = leInt(chunk).add(BigInteger.valueOf(2).pow(8 * (end - i)))
            acc = acc.add(n).mod(POLY_P).multiply(r).mod(POLY_P)
            i += 16
        }
        val tag = acc.add(s).mod(MOD128)
        return tag.toLEBytes(16)
    }

    // ====================================================================
    // AEAD ChaCha20-Poly1305
    // ====================================================================
    private fun pad16(x: ByteArray): ByteArray = x + ByteArray((16 - x.size % 16) % 16)
    private fun le64(n: Int): ByteArray {
        val v = n.toLong() and 0xffffffffL
        return ByteArray(8).also { for (i in 0 until 8) it[i] = ((v ushr (8 * i)) and 0xff).toByte() }
    }

    private fun macInput(aad: ByteArray, ct: ByteArray): ByteArray {
        val out = ByteArrayOutputStream()
        out.write(pad16(aad))
        out.write(pad16(ct))
        out.write(le64(aad.size))
        out.write(le64(ct.size))
        return out.toByteArray()
    }

    /** 返回 nonce(12) + ciphertext + tag(16) 的 blob。aad 可空。 */
    fun aeadSeal(key: ByteArray, nonce: ByteArray, plaintext: ByteArray, aad: ByteArray): ByteArray {
        require(key.size == 32 && nonce.size == 12)
        val ct = chacha20(key, 1, nonce, plaintext)
        val otk = chacha20Block(key, 0, nonce).copyOfRange(0, 32)
        val tag = poly1305(otk, macInput(aad, ct))
        return nonce + ct + tag
    }

    fun aeadOpen(key: ByteArray, blob: ByteArray, aad: ByteArray): ByteArray {
        require(key.size == 32 && blob.size >= 12 + 16)
        val nonce = blob.copyOfRange(0, 12)
        val ct = blob.copyOfRange(12, blob.size - 16)
        val tag = blob.copyOfRange(blob.size - 16, blob.size)
        val otk = chacha20Block(key, 0, nonce).copyOfRange(0, 32)
        val expect = poly1305(otk, macInput(aad, ct))
        if (!expect.contentEquals(tag)) throw InvalidTagException("AEAD 认证失败")
        return chacha20(key, 1, nonce, ct)
    }

    class InvalidTagException(msg: String) : Exception(msg)

    // ====================================================================
    // HKDF-SHA256 (RFC 5869)
    // ====================================================================
    fun hmacSha256(key: ByteArray, data: ByteArray): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return mac.doFinal(data)
    }

    fun hkdfSha256(ikm: ByteArray, salt: ByteArray = ByteArray(0), info: ByteArray = ByteArray(0), length: Int): ByteArray {
        val s = if (salt.isEmpty()) ByteArray(32) else salt
        val prk = hmacSha256(s, ikm)
        val out = ByteArrayOutputStream()
        var t = ByteArray(0)
        var i = 1
        while (out.size() < length) {
            val input = ByteArrayOutputStream().apply { write(t); write(info); write(byteArrayOf(i.toByte())) }
            t = hmacSha256(prk, input.toByteArray())
            out.write(t)
            i++
            require(i <= 255) { "HKDF 长度超限" }
        }
        return out.toByteArray().copyOfRange(0, length)
    }

    fun deriveKey(ikm: ByteArray, info: ByteArray): ByteArray = hkdfSha256(ikm, ByteArray(0), info, 32)

    // ---- 小工具 ----
    private fun leInt(b: ByteArray): BigInteger = BigInteger(1, b.reversedArray())

    private fun BigInteger.toLEBytes(n: Int): ByteArray {
        val be = this.toByteArray()
        val trimmed = if (be.isNotEmpty() && be[0] == 0.toByte() && be.size > n) be.copyOfRange(1, be.size) else be
        val out = ByteArray(n)
        for (i in trimmed.indices) out[i] = trimmed[trimmed.size - 1 - i]
        return out
    }

    private fun ByteArray.reversedArray(): ByteArray = ByteArray(size).also { for (i in indices) it[i] = this[size - 1 - i] }

    // ---- 随机 ----
    fun randomBytes(n: Int): ByteArray = ByteArray(n).also { java.security.SecureRandom().nextBytes(it) }
}

fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it.toInt() and 0xff) }
fun hex(s: String): ByteArray = s.replace(" ", "").chunked(2).map { it.toInt(16).toByte() }.toByteArray()
