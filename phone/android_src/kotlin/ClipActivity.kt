package com.alienshtain.adblink

import android.app.Activity
import android.content.ClipboardManager
import android.widget.Toast
import org.json.JSONObject

/**
 * Invisible screen that reads the clipboard (Android only allows that for the app in front)
 * and sends it to the computer. Opened from the quick-settings tile or the notification button.
 */
class ClipActivity : Activity() {
    private var handled = false

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (!hasFocus || handled) return
        handled = true
        val cm = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
        val clip = cm.primaryClip
        val text = if (clip != null && clip.itemCount > 0) clip.getItemAt(0).coerceToText(this).toString() else ""
        val c = Link.cfg(this)
        if (c == null || text.isEmpty()) {
            Toast.makeText(this, Link.t("Nothing to send", "لا يوجد شيء للإرسال"), Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        Thread {
            val code = Link.postJson(c, "/clipboard", JSONObject().put("text", text))
            runOnUiThread {
                val msg = if (code == 200) Link.t("Sent to the computer", "أُرسل إلى الحاسوب")
                else Link.t("Could not reach the computer", "تعذر الوصول إلى الحاسوب")
                Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
                finish()
            }
        }.start()
    }
}
