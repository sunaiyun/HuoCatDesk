package com.huocatdesk

import android.content.ContentResolver
import android.net.Uri
import java.security.MessageDigest

/** 文件分块发送（与桌面端 filexfer.py 一致）：FILE_META -> FILE_DATA* -> FILE_END(SHA256)。 */
object FileXfer {
    private const val CHUNK = 60000

    fun send(channel: Channel, resolver: ContentResolver, uri: Uri, name: String, size: Long) {
        val fileId = 1
        val nameB = name.toByteArray(Charsets.UTF_8)
        // FILE_META: id(1) + name_len(2,BE) + name + size(8,BE)
        val meta = ByteArray(3 + nameB.size + 8)
        meta[0] = fileId.toByte()
        meta[1] = ((nameB.size ushr 8) and 0xff).toByte()
        meta[2] = (nameB.size and 0xff).toByte()
        System.arraycopy(nameB, 0, meta, 3, nameB.size)
        for (i in 0 until 8) meta[3 + nameB.size + i] = ((size ushr (8 * (7 - i))) and 0xff).toByte()
        channel.send(Protocol.FILE_META, meta)

        val sha = MessageDigest.getInstance("SHA-256")
        resolver.openInputStream(uri)?.use { input ->
            val buf = ByteArray(CHUNK)
            var off = 0L
            while (true) {
                val n = input.read(buf)
                if (n <= 0) break
                val data = if (n == buf.size) buf else buf.copyOf(n)
                sha.update(data)
                // FILE_DATA: id(1) + offset(8,BE) + data
                val frame = ByteArray(9 + data.size)
                frame[0] = fileId.toByte()
                for (i in 0 until 8) frame[1 + i] = ((off ushr (8 * (7 - i))) and 0xff).toByte()
                System.arraycopy(data, 0, frame, 9, data.size)
                channel.send(Protocol.FILE_DATA, frame)
                off += n
            }
        }
        // FILE_END: id(1) + sha256(32)
        channel.send(Protocol.FILE_END, byteArrayOf(fileId.toByte()) + sha.digest())
    }
}
