package com.alienshtain.adblink

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.OpenableColumns
import android.widget.Toast
import org.json.JSONObject
import java.io.File
import java.net.URLEncoder

/** "Send to PC" in the Android share sheet: text goes to the computer's clipboard, files to Downloads/FromPhone. */
class ShareActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val c = Link.cfg(this)
        if (c == null) {
            Toast.makeText(this, Link.t("Open ADB Link and pair first", "افتح ADB Link واقترن أولاً"), Toast.LENGTH_LONG).show()
            finish()
            return
        }
        Toast.makeText(this, Link.t("Sending to the computer...", "جارٍ الإرسال إلى الحاسوب..."), Toast.LENGTH_SHORT).show()
        val received = intent
        Thread { work(c, received) }.start()
    }

    @Suppress("DEPRECATION")
    private fun streamOf(i: Intent): List<Uri> {
        val list = ArrayList<Uri>()
        if (i.action == Intent.ACTION_SEND) {
            val u: Uri? = if (Build.VERSION.SDK_INT >= 33) i.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
            else i.getParcelableExtra(Intent.EXTRA_STREAM)
            if (u != null) list.add(u)
        } else if (i.action == Intent.ACTION_SEND_MULTIPLE) {
            val l: ArrayList<Uri>? = if (Build.VERSION.SDK_INT >= 33) i.getParcelableArrayListExtra(Intent.EXTRA_STREAM, Uri::class.java)
            else i.getParcelableArrayListExtra(Intent.EXTRA_STREAM)
            if (l != null) list.addAll(l)
        }
        return list
    }

    private fun nameAndSize(u: Uri): Pair<String, Long> {
        var name = u.lastPathSegment ?: "file"
        var size = -1L
        try {
            contentResolver.query(u, null, null, null, null)?.use { cur ->
                if (cur.moveToFirst()) {
                    val ni = cur.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    val si = cur.getColumnIndex(OpenableColumns.SIZE)
                    if (ni >= 0 && !cur.isNull(ni)) name = cur.getString(ni)
                    if (si >= 0 && !cur.isNull(si)) size = cur.getLong(si)
                }
            }
        } catch (e: Exception) {
        }
        return Pair(name, size)
    }

    private fun upload(c: Cfg, u: Uri): Boolean {
        var (name, size) = nameAndSize(u)
        var temp: File? = null
        try {
            var source = contentResolver.openInputStream(u) ?: return false
            if (size < 0) { // the computer needs the length first, so copy to a temporary file
                val file = File.createTempFile("share", ".tmp", cacheDir)
                temp = file
                source.use { inp -> file.outputStream().use { inp.copyTo(it, 64 * 1024) } }
                size = file.length()
                source = file.inputStream()
            }
            val conn = Link.open(c, "POST", "/files?op=put&name=" + URLEncoder.encode(name, "UTF-8"), 600000)
            try {
                conn.doOutput = true
                conn.setFixedLengthStreamingMode(size)
                source.use { inp -> conn.outputStream.use { out -> inp.copyTo(out, 64 * 1024) } }
                val code = conn.responseCode
                if (code < 400) conn.inputStream.use { it.readBytes() }
                return code == 200
            } finally {
                conn.disconnect()
            }
        } catch (e: Exception) {
            return false
        } finally {
            temp?.delete()
        }
    }

    private fun work(c: Cfg, i: Intent) {
        var ok = 0
        var bad = 0
        val files = streamOf(i)
        if (files.isEmpty()) {
            val text = i.getStringExtra(Intent.EXTRA_TEXT)
            if (!text.isNullOrEmpty()) {
                if (Link.postJson(c, "/clipboard", JSONObject().put("text", text)) == 200) ok++ else bad++
            }
        }
        for (u in files) if (upload(c, u)) ok++ else bad++
        runOnUiThread {
            val msg = if (bad == 0 && ok > 0) Link.t("Sent to the computer", "أُرسل إلى الحاسوب")
            else Link.t("Could not send ($bad failed)", "تعذر الإرسال ($bad فشل)")
            Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
            finish()
        }
    }
}
