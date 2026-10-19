package com.huocatdesk

/** p2pdesk/HuoCatDesk 线协议：UDP 分帧 + 消息类型（与桌面端 protocol.py 完全一致）。 */
object Protocol {
    val MAGIC = byteArrayOf(0x50, 0x32, 0x50, 0x44)  // "P2PD"
    const val HEADER_LEN = 10
    const val FLAG_ENC = 1
    const val MAX_BODY = 65000

    const val HELLO = 1      // 握手：pubkey(32)+ts(8) 明文
    const val HELLO_ACK = 2 // 握手应答
    const val SCREEN = 3     // seq(4)+ts(8)+w(2)+h(2)+jpeg
    const val KEY = 4        // vkcode(4)+state(1)
    const val MOUSE = 5      // x(2)+y(2)+buttons(1)+wheel(1,signed)
    const val FILE_META = 6
    const val FILE_DATA = 7
    const val FILE_END = 8
    const val HEARTBEAT = 9
    const val BYE = 10
    const val ACK = 11

    fun pack(type: Int, body: ByteArray, flags: Int = 0): ByteArray {
        require(body.size <= MAX_BODY)
        val out = ByteArray(HEADER_LEN + body.size)
        System.arraycopy(MAGIC, 0, out, 0, 4)
        out[4] = type.toByte(); out[5] = flags.toByte()
        val n = body.size
        out[6] = ((n ushr 24) and 0xff).toByte()
        out[7] = ((n ushr 16) and 0xff).toByte()
        out[8] = ((n ushr 8) and 0xff).toByte()
        out[9] = (n and 0xff).toByte()
        System.arraycopy(body, 0, out, HEADER_LEN, body.size)
        return out
    }

    /** 解析一帧，返回 (type, flags, body)；不完整或 magic 错返回 null。 */
    fun parse(buf: ByteArray, len: Int): Triple<Int, Int, ByteArray>? {
        if (len < HEADER_LEN) return null
        if (buf[0] != MAGIC[0] || buf[1] != MAGIC[1] || buf[2] != MAGIC[2] || buf[3] != MAGIC[3]) return null
        val type = buf[4].toInt() and 0xff
        val flags = buf[5].toInt() and 0xff
        val n = ((buf[6].toInt() and 0xff) shl 24) or
                ((buf[7].toInt() and 0xff) shl 16) or
                ((buf[8].toInt() and 0xff) shl 8) or
                (buf[9].toInt() and 0xff)
        if (len < HEADER_LEN + n) return null
        return Triple(type, flags, buf.copyOfRange(HEADER_LEN, HEADER_LEN + n))
    }
}
