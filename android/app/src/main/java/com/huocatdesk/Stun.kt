package com.huocatdesk

import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.util.concurrent.ThreadLocalRandom

/** STUN 客户端（RFC 5389 子集）：获取 NAT 公网映射地址。与桌面端 stun.py 一致。 */
object Stun {
    private const val MAGIC_COOKIE = 0x2112A442
    private const val BINDING_REQUEST = 0x0001
    private const val BINDING_SUCCESS = 0x0100
    private const val ATTR_XOR_MAPPED = 0x0020

    private val SERVERS = arrayOf(
        "stun.l.google.com" to 19302,
        "stun1.l.google.com" to 19302,
        "stun2.l.google.com" to 19302,
        "stun.miwifi.com" to 3478,
        "stun.qq.com" to 3478,
    )

    private fun bindingRequest(tid: ByteArray): ByteArray {
        val out = ByteArray(20)
        out[0] = 0x00; out[1] = 0x01                      // type = Binding Request
        out[2] = 0x00; out[3] = 0x00                      // length = 0
        out[4] = 0x21; out[5] = 0x12; out[6] = 0xA4.toByte(); out[7] = 0x42 // magic cookie
        System.arraycopy(tid, 0, out, 8, 12)
        return out
    }

    fun query(sock: DatagramSocket, server: Pair<String, Int>, timeoutMs: Int = 3000): Pair<String, Int>? {
        val tid = ByteArray(12).also { ThreadLocalRandom.current().nextBytes(it) }
        val req = bindingRequest(tid)
        val addr = InetAddress.getByName(server.first)
        try {
            sock.send(DatagramPacket(req, req.size, addr, server.second))
        } catch (e: Exception) { return null }
        val buf = ByteArray(2048)
        val resp = DatagramPacket(buf, buf.size)
        sock.soTimeout = timeoutMs
        try { sock.receive(resp) } catch (e: Exception) { return null }
        if (resp.length < 20) return null
        val b = resp.data
        val type = ((b[0].toInt() and 0xff) shl 8) or (b[1].toInt() and 0xff)
        val cookie = ((b[4].toInt() and 0xff) shl 24) or ((b[5].toInt() and 0xff) shl 16) or
                     ((b[6].toInt() and 0xff) shl 8) or (b[7].toInt() and 0xff)
        if (type != BINDING_SUCCESS || cookie != MAGIC_COOKIE) return null
        val respTid = b.copyOfRange(8, 20)
        if (!respTid.contentEquals(tid)) return null
        val msgLen = ((b[2].toInt() and 0xff) shl 8) or (b[3].toInt() and 0xff)
        var off = 20
        val end = minOf(20 + msgLen, resp.length)
        while (off + 4 <= end) {
            val atype = ((b[off].toInt() and 0xff) shl 8) or (b[off + 1].toInt() and 0xff)
            val alen = ((b[off + 2].toInt() and 0xff) shl 8) or (b[off + 3].toInt() and 0xff)
            if (atype == ATTR_XOR_MAPPED && alen >= 8) {
                val family = b[off + 4 + 1].toInt() and 0xff
                if (family == 0x01) {  // IPv4
                    val xport = ((b[off + 6].toInt() and 0xff) shl 8) or (b[off + 7].toInt() and 0xff)
                    val port = xport xor (MAGIC_COOKIE ushr 16)
                    val ipBytes = ByteArray(4) { b[off + 8 + it] }
                    val key = ByteArray(4).also { MAGIC_COOKIE.toBytesBE(it) }
                    val ip = ByteArray(4)
                    for (i in 0..3) ip[i] = (ipBytes[i].toInt() xor (key[i].toInt()) and 0xff).toByte()
                    val ipStr = (ip[0].toInt() and 0xff).toString() + "." +
                                (ip[1].toInt() and 0xff) + "." +
                                (ip[2].toInt() and 0xff) + "." +
                                (ip[3].toInt() and 0xff)
                    return ipStr to port
                }
            }
            off += 4 + alen
            off += (4 - (alen % 4)) % 4
        }
        return null
    }

    fun discover(sock: DatagramSocket, timeoutMs: Int = 4000): Pair<String, Int>? {
        for (srv in SERVERS) {
            try { query(sock, srv, timeoutMs)?.let { return it } } catch (e: Exception) {}
        }
        return null
    }

    private fun Int.toBytesBE(out: ByteArray) {
        out[0] = ((this ushr 24) and 0xff).toByte()
        out[1] = ((this ushr 16) and 0xff).toByte()
        out[2] = ((this ushr 8) and 0xff).toByte()
        out[3] = (this and 0xff).toByte()
    }
}
