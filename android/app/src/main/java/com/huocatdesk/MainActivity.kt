package com.huocatdesk

import android.app.Activity
import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.MotionEvent
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast

/** HuoCatDesk 控制端：输入桌面端邀请码 -> 打洞直连 -> 看屏幕 -> 触控 -> 发文件。 */
class MainActivity : Activity() {
    private var channel: Channel? = null
    private var inviteEdit: EditText? = null
    private var screenView: ImageView? = null
    private var statusView: TextView? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private var buttons = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        inviteEdit = findViewById(R.id.invite)
        screenView = findViewById(R.id.screen)
        statusView = findViewById(R.id.status)
        findViewById<Button>(R.id.connect_btn).setOnClickListener { doConnect() }
        findViewById<Button>(R.id.sendfile_btn).setOnClickListener {
            val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "*/*"
            }
            try { startActivityForResult(intent, 1) }
            catch (e: android.content.ActivityNotFoundException) { toast("无可用文件选择器") }
        }
        screenView?.setOnTouchListener { _, ev -> handleTouch(ev); true }
        setStatus("把桌面端 HuoCatDesk 生成的邀请码粘贴到上方，点连接。")
    }

    private fun doConnect() {
        val code = inviteEdit?.text?.toString()?.trim() ?: ""
        if (code.isEmpty()) { toast("请输入邀请码"); return }
        val (peerPub, peerEp) = try { P2p.parseInvite(code) }
        catch (e: Exception) { toast("邀请码无效：${e.message}"); return }
        setStatus("正在打洞连接 ${peerEp.first}:${peerEp.second} ...")
        Thread {
            val kp = P2p.newKeyPair()
            val ch = Channel(kp)
            ch.on(Protocol.SCREEN) { body, _ -> onScreen(body) }
            ch.connectTo(peerPub, peerEp)
            val ok = ch.waitConnected(20000)
            mainHandler.post {
                channel = ch
                if (ok) setStatus("已连接：接收屏幕中。触控屏幕即可操作对方桌面。")
                else { setStatus("连接超时：对方未响应，可能 NAT 不支持直连。"); toast("连接失败") }
            }
        }.start()
    }

    private fun onScreen(body: ByteArray) {
        try {
            // body = seq(4) + ts(8) + w(2) + h(2) + jpeg
            val jpg = body.copyOfRange(16, body.size)
            val bmp = BitmapFactory.decodeByteArray(jpg, 0, jpg.size) ?: return
            mainHandler.post { screenView?.setImageBitmap(bmp) }
        } catch (e: Exception) {}
    }

    private fun handleTouch(ev: MotionEvent): Boolean {
        val w = (screenView?.width ?: 1).coerceAtLeast(1)
        val h = (screenView?.height ?: 1).coerceAtLeast(1)
        val x = (ev.x / w).coerceIn(0f, 1f)
        val y = (ev.y / h).coerceIn(0f, 1f)
        when (ev.actionMasked) {
            MotionEvent.ACTION_DOWN -> buttons = buttons or 1
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> buttons = buttons and 1.inv()
        }
        channel?.send(Protocol.MOUSE, mouseBody(x, y, buttons, 0))
        return true
    }

    private fun mouseBody(x: Float, y: Float, buttons: Int, wheel: Int): ByteArray {
        val xi = (x * 65535).toInt()
        val yi = (y * 65535).toInt()
        return byteArrayOf(
            ((xi ushr 8) and 0xff).toByte(), (xi and 0xff).toByte(),
            ((yi ushr 8) and 0xff).toByte(), (yi and 0xff).toByte(),
            buttons.toByte(), wheel.toByte())
    }

    override fun onActivityResult(req: Int, res: Int, data: Intent?) {
        super.onActivityResult(req, res, data)
        if (req == 1 && res == RESULT_OK && data?.data != null) {
            val uri = data.data!!
            val ch = channel ?: run { toast("未连接"); return }
            Thread {
                val name = try {
                    contentResolver.query(uri, null, null, null, null)?.use {
                        it.moveToFirst()
                        val idx = it.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
                        if (idx >= 0) it.getString(idx) else null
                    }
                } catch (e: Exception) { null } ?: "file"
                val size = try {
                    contentResolver.query(uri, null, null, null, null)?.use {
                        it.moveToFirst()
                        val idx = it.getColumnIndex(android.provider.OpenableColumns.SIZE)
                        if (idx >= 0) it.getLong(idx) else -1L
                    }
                } catch (e: Exception) { null } ?: -1L
                FileXfer.send(ch, contentResolver, uri, name, size)
                mainHandler.post { setStatus("文件已发送：$name") }
            }.start()
            setStatus("发送中：…")
        }
    }

    private fun setStatus(s: String) { mainHandler.post { statusView?.text = s } }
    private fun toast(s: String) { runOnUiThread { Toast.makeText(this, s, Toast.LENGTH_SHORT).show() } }

    override fun onDestroy() {
        super.onDestroy()
        channel?.close()
    }
}

private fun byteArrayOf(vararg b: Byte): ByteArray = b
