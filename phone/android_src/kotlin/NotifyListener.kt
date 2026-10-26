package com.alienshtain.adblink

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONObject

/** Sends every phone notification to the computer. Needs "notification access" in Android settings. */
class NotifyListener : NotificationListenerService() {
    private var lastKey = ""
    private var lastTime = 0L

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (sbn.packageName == packageName) return // our own (this includes the ones from the computer)
        val n = sbn.notification
        if ((n.flags and Notification.FLAG_ONGOING_EVENT) != 0) return
        if ((n.flags and Notification.FLAG_GROUP_SUMMARY) != 0) return
        val c = Link.cfg(this) ?: return
        if (!c.notif) return
        val extras = n.extras
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: ""
        val text = (extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
            ?: extras.getCharSequence(Notification.EXTRA_TEXT))?.toString() ?: ""
        if (title.isEmpty() && text.isEmpty()) return
        val key = sbn.packageName + "|" + title + "|" + text
        synchronized(this) {
            val now = System.currentTimeMillis()
            if (key == lastKey && now - lastTime < 3000) return
            lastKey = key
            lastTime = now
        }
        val label = try {
            packageManager.getApplicationLabel(packageManager.getApplicationInfo(sbn.packageName, 0)).toString()
        } catch (e: Exception) {
            sbn.packageName
        }
        Thread {
            Link.postJson(c, "/notify", JSONObject().put("app", label).put("title", title).put("text", text))
        }.start()
    }
}
