package com.huocatdesk

import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetSocketAddress

/** 邀请码编解码 + UDP 打洞握手 + 加密通道（与桌面端 p2p.py 一致，逐字节互通）。 */
object P2p {
    val BASE_POINT_U = byteArrayOf(0x09).plus(ByteArray(31))  // curve25519 基点 u

    data class KeyPair(val priv: ByteArray, val public: ByteArray)

    fun newKeyPair(): KeyPair {
        val priv = Crypto.randomBytes(32)
        return KeyPair(priv, Crypto.x25519(priv, BASE_POINT_U))
    }

    // ---- base32 (RFC 4648，无填充) ----
    private val B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    private fun b32encode(data: ByteArray): String {
        val sb = StringBuilder()
        var buf = 0; var bits = 0
        for (b in data) {
            buf = (buf shl 8) or (b.toInt() and 0xff); bits += 8
            while (bits >= 5) { bits -= 5; sb.append(B32[(buf ushr bits) and 0x1f]) }
        }
        if (bits > 0) sb.append(B32[(buf shl (5 - bits)) and 0x1f])
        return sb.toString()
    }
    private fun b32decode(s: String): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        var buf = 0; var bits = 0
        for (c in s) {
            val v = B32.indexOf(c); if (v < 0) continue
            buf = (buf shl 5) or v; bits += 5
            if (bits >= 8) { bits -= 8; out.write((buf ushr bits) and 0xff) }
        }
        return out.toByteArray()
    }
    private fun crc16(data: ByteArray): Int {
        var crc = 0xFFFF
        for (b in data) {
            crc = crc xor (b.toInt() and 0xff)
            for (i in 0 until 8) crc = if ((crc and 1) != 0) (crc ushr 1) xor 0xA001 else crc ushr 1
        }
        return crc and 0xFFFF
    }

    private fun ipToBytes(ip: String): ByteArray {
        val p = ip.split(".")
        return ByteArray(4) { p[it].trim().toInt().toByte() }
    }

    fun makeInvite(pubkey: ByteArray, publicEp: Pair<String, Int>): String {
        val port = publicEp.second
        val ts = (System.currentTimeMillis() / 1000).toInt()
        val raw = pubkey + ipToBytes(publicEp.first) +
                  byteArrayOf(((port ushr 8) and 0xff).toByte(), (port and 0xff).toByte()) +
                  byteArrayOf(((ts ushr 24) and 0xff).toByte(), ((ts ushr 16) and 0xff).toByte(),
                              ((ts ushr 8) and 0xff).toByte(), (ts and 0xff).toByte())
        val crc = crc16(raw)
        val blob = byteArrayOf(((crc ushr 8) and 0xff).toByte(), (crc and 0xff).toByte()) + raw
        return b32encode(blob).chunked(4).joinToString("-")
    }

    fun parseInvite(code: String): Pair<ByteArray, Pair<String, Int>> {
        val b32 = code.replace("-", "").replace(" ", "").uppercase()
        val blob = b32decode(b32)
        require(blob.size >= 4) { "邀请码过短" }
        val crc = ((blob[0].toInt() and 0xff) shl 8) or (blob[1].toInt() and 0xff)
        val raw = blob.copyOfRange(2, blob.size)
        require(crc16(raw) == crc) { "邀请码校验失败" }
        require(raw.size >= 42) { "邀请码内容过短" }
        val pubkey = raw.copyOfRange(0, 32)
        val ip = (raw[32].toInt() and 0xff).toString() + "." + (raw[33].toInt() and 0xff) + "." +
                 (raw[34].toInt() and 0xff) + "." + (raw[35].toInt() and 0xff)
        val port = ((raw[36].toInt() and 0xff) shl 8) or (raw[37].toInt() and 0xff)
        return pubkey to (ip to port)
    }

    private fun byteArrayOf(vararg b: Byte): ByteArray = b
}

class Channel(val kp: P2p.KeyPair, localPort: Int = 0) {
    val sock: DatagramSocket = DatagramSocket(localPort)
    var publicEp: Pair<String, Int>? = null
    var peerPubkey: ByteArray? = null
    var peerEp: InetSocketAddress? = null
    private var aeadKey: ByteArray? = null
    @Volatile var connected = false
    @Volatile private var stop = false
    private val handlers = mutableMapOf<Int, MutableList<(ByteArray, InetSocketAddress) -> Unit>>()

    fun discover(): Pair<String, Int>? {
        val ep = Stun.discover(sock)
        if (ep != null) publicEp = ep
        return ep
    }

    fun on(type: Int, fn: (ByteArray, InetSocketAddress) -> Unit) {
        synchronized(handlers) { handlers.getOrPut(type) { mutableListOf() }.add(fn) }
    }

    fun send(type: Int, body: ByteArray) {
        val ep = peerEp ?: return
        val frame = if (aeadKey != null) {
            val nonce = Crypto.randomBytes(12)
            val enc = Crypto.aeadSeal(aeadKey!!, nonce, body, byteArrayOf(type.toByte()))
            Protocol.pack(type, enc, Protocol.FLAG_ENC)
        } else Protocol.pack(type, body, 0)
        try { sock.send(DatagramPacket(frame, frame.size, ep)) } catch (e: Exception) {}
    }

    fun connectTo(peerPub: ByteArray, peerEp: Pair<String, Int>) {
        peerPubkey = peerPub
        this.peerEp = InetSocketAddress(peerEp.first, peerEp.second)
        start()
    }

    fun listen() = start()

    private fun start() {
        Thread { punchLoop() }.start()
        Thread { recvLoop() }.start()
    }

    private fun punchLoop() {
        val body = kp.public + le64ms()
        while (!stop && !connected) {
            val ep = peerEp
            if (ep != null) {
                val f = Protocol.pack(Protocol.HELLO, body, 0)
                try { sock.send(DatagramPacket(f, f.size, ep)) } catch (e: Exception) {}
            }
            try { Thread.sleep(100) } catch (e: Exception) {}
        }
    }

    private fun recvLoop() {
        val buf = ByteArray(65535)
        while (!stop) {
            val pkt = DatagramPacket(buf, buf.size)
            try {
                sock.soTimeout = 500
                sock.receive(pkt)
            } catch (e: Exception) { continue }
            handlePacket(pkt)
        }
    }

    private fun handlePacket(pkt: DatagramPacket) {
        val parsed = Protocol.parse(pkt.data, pkt.length) ?: return
        val (type, flags, body) = parsed
        val from = InetSocketAddress(pkt.address, pkt.port)
        if (type == Protocol.HELLO && !connected) {
            peerEp = from
            peerPubkey = body.copyOfRange(0, 32)
            deriveSession()
            val ack = kp.public + le64ms()
            try { sock.send(DatagramPacket(Protocol.pack(Protocol.HELLO_ACK, ack, 0), 40, from)) } catch (e: Exception) {}
            return
        }
        if (type == Protocol.HELLO_ACK && !connected) {
            peerEp = from
            peerPubkey = body.copyOfRange(0, 32)
            deriveSession()
            return
        }
        if (!connected) return
        var payload = body
        if ((flags and Protocol.FLAG_ENC) != 0) {
            val key = aeadKey ?: return
            try { payload = Crypto.aeadOpen(key, body, byteArrayOf(type.toByte())) }
            catch (e: Crypto.InvalidTagException) { return }
        }
        synchronized(handlers) { handlers[type]?.forEach { runCatching { it(payload, from) } } }
    }

    private fun deriveSession() {
        val shared = Crypto.x25519(kp.priv, peerPubkey!!)
        aeadKey = Crypto.deriveKey(shared, "huocatdesk-session-v1".toByteArray())
        connected = true
    }

    fun waitConnected(timeoutMs: Long): Boolean {
        val end = System.currentTimeMillis() + timeoutMs
        while (!connected && System.currentTimeMillis() < end) try { Thread.sleep(50) } catch (e: Exception) {}
        return connected
    }

    fun close() {
        stop = true
        if (aeadKey != null) send(Protocol.BYE, ByteArray(0))
        try { sock.close() } catch (e: Exception) {}
    }

    private fun le64ms(): ByteArray {
        val v = System.currentTimeMillis()
        return ByteArray(8) { ((v ushr (8 * it)) and 0xff).toByte() }
    }
}

private fun byteArrayOf(vararg b: Byte): ByteArray = b
