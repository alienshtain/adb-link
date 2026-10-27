package com.alienshtain.adblink

import android.content.BroadcastReceiver
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.util.Base64

/**
 * Lets the computer type any text (Arabic included) into the phone: it puts the text on the
 * clipboard and the computer then presses "paste".
 *   adb shell am broadcast -f 32 -n com.alienshtain.adblink/.TypeReceiver -a org.adblink.TYPE --es b64 <base64>
 */
class TypeReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val b64 = intent.getStringExtra("b64") ?: return
        val text = try {
            String(Base64.decode(b64, Base64.DEFAULT), Charsets.UTF_8)
        } catch (e: IllegalArgumentException) {
            return
        }
        val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText("adblink", text))
        resultCode = 1
        resultData = "ok"
    }
}
