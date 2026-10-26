package com.alienshtain.adblink

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import org.json.JSONObject

/** Keeps a long connection to the computer: clipboard and notifications from it arrive here. */
class LinkService : Service() {
    companion object {
        @Volatile
        var running = false
        const val CH_LINK = "link"
        const val CH_PC = "pc"
    }

    private var worker: Thread? = null
    @Volatile
    private var stopped = false
    private var noteId = 100

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        if (Build.VERSION.SDK_INT >= 26) {
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(CH_LINK, Link.t("Link to computer", "الربط بالحاسوب"), NotificationManager.IMPORTANCE_LOW)
            )
            nm.createNotificationChannel(
                NotificationChannel(CH_PC, Link.t("Computer notifications", "إشعارات الحاسوب"), NotificationManager.IMPORTANCE_DEFAULT)
            )
        }
    }

    private fun builder(channel: String): Notification.Builder =
        if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, channel) else Notification.Builder(this)

    @Suppress("DEPRECATION")
    private fun ongoing(): Notification {
        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, ClipActivity::class.java), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return builder(CH_LINK)
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle(Link.t("ADB Link is connected", "ADB Link متصل"))
            .setOngoing(true)
            .addAction(android.R.drawable.ic_menu_send, Link.t("Send clipboard to PC", "إرسال الحافظة للحاسوب"), pi)
            .build()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(1, ongoing(), ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(1, ongoing())
        }
        if (worker == null) {
            stopped = false
            running = true
            worker = Thread { loop() }.also {
                it.isDaemon = true
                it.start()
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        stopped = true
        running = false
        worker?.interrupt()
        worker = null
        super.onDestroy()
    }

    private fun loop() {
        var after = -1L
        var backoff = 3000L
        while (!stopped) {
            val c = Link.cfg(this)
            if (c == null) {
                try { Thread.sleep(5000) } catch (e: InterruptedException) { return }
                continue
            }
            try {
                if (after < 0) {
                    // start from "now": ask for events after a huge number just to learn the last id
                    val first = Link.getText(c, "/events?after=999999999&wait=0", 15000)
                    after = if (first != null) JSONObject(first).getLong("last") else -1L
                    if (after < 0) throw RuntimeException("no answer")
                }
                val body = Link.getText(c, "/events?after=$after&wait=25", 40000) ?: throw RuntimeException("no answer")
                val json = JSONObject(body)
                val last = json.getLong("last")
                if (last < after) after = last // the computer app was restarted
                val events = json.getJSONArray("events")
                for (i in 0 until events.length()) {
                    val ev = events.getJSONObject(i)
                    handle(c, ev)
                    after = maxOf(after, ev.getLong("id"))
                }
                after = maxOf(after, last)
                backoff = 3000L
            } catch (e: InterruptedException) {
                return
            } catch (e: Exception) {
                try { Thread.sleep(backoff) } catch (ie: InterruptedException) { return }
                backoff = minOf(backoff * 2, 30000L)
            }
        }
    }

    private fun handle(c: Cfg, ev: JSONObject) {
        when (ev.optString("type")) {
            "clipboard" -> if (c.clip) {
                val text = ev.optString("text")
                Handler(Looper.getMainLooper()).post {
                    val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    cm.setPrimaryClip(ClipData.newPlainText("PC", text))
                }
            }
            "notification" -> if (c.notif) {
                val app = ev.optString("app")
                val title = ev.optString("title")
                val body = ev.optString("body")
                val n = builder(CH_PC)
                    .setSmallIcon(android.R.drawable.stat_notify_chat)
                    .setContentTitle(if (title.isEmpty()) app else title)
                    .setContentText(body)
                    .setSubText(app)
                    .setStyle(Notification.BigTextStyle().bigText(body))
                    .setAutoCancel(true)
                    .build()
                try {
                    getSystemService(NotificationManager::class.java).notify(noteId++, n)
                } catch (e: SecurityException) {
                    // notification permission not granted
                }
                if (noteId > 400) noteId = 100
            }
        }
    }
}
