package com.alienshtain.adblink

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        val wanted = context.getSharedPreferences("adblink", Context.MODE_PRIVATE).getBoolean("autostart", false)
        if (!wanted || Link.cfg(context) == null) return
        val i = Intent(context, LinkService::class.java)
        try {
            if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(i) else context.startService(i)
        } catch (e: Exception) {
            // the system may refuse to start it right after boot; the app can start it by hand
        }
    }
}
