package com.alienshtain.adblink

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale

data class Cfg(val host: String, val port: Int, val token: String, val clip: Boolean, val notif: Boolean)

object Link {
    /** Reads the connection the Flutter side saved (key "link" in Flutter's shared preferences). */
    fun cfg(ctx: Context): Cfg? {
        val prefs = ctx.getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
        val raw = prefs.getString("flutter.link", null) ?: return null
        return try {
            val j = JSONObject(raw)
            Cfg(
                j.getString("host"), j.getInt("port"), j.getString("token"),
                j.optBoolean("syncClipboard", true), j.optBoolean("syncNotifications", true)
            )
        } catch (e: Exception) {
            null
        }
    }

    fun open(c: Cfg, method: String, path: String, readTimeoutMs: Int = 15000): HttpURLConnection {
        val host = if (c.host.contains(':')) "[${c.host}]" else c.host
        val conn = URL("http://$host:${c.port}$path").openConnection() as HttpURLConnection
        conn.requestMethod = method
        conn.connectTimeout = 8000
        conn.readTimeout = readTimeoutMs
        conn.setRequestProperty("Authorization", "Bearer ${c.token}")
        return conn
    }

    /** Returns the HTTP status, or -1 when the computer cannot be reached. */
    fun postJson(c: Cfg, path: String, body: JSONObject): Int {
        val conn = open(c, "POST", path, 20000)
        return try {
            val bytes = body.toString().toByteArray(Charsets.UTF_8)
            conn.doOutput = true
            conn.setFixedLengthStreamingMode(bytes.size)
            conn.outputStream.use { it.write(bytes) }
            val code = conn.responseCode
            if (code < 400) conn.inputStream.use { it.readBytes() }
            code
        } catch (e: Exception) {
            -1
        } finally {
            conn.disconnect()
        }
    }

    /** GET returning the body text, or null on any failure. */
    fun getText(c: Cfg, path: String, readTimeoutMs: Int): String? {
        val conn = open(c, "GET", path, readTimeoutMs)
        return try {
            if (conn.responseCode != 200) null else conn.inputStream.use { String(it.readBytes(), Charsets.UTF_8) }
        } finally {
            conn.disconnect()
        }
    }

    fun t(en: String, ar: String): String = if (Locale.getDefault().language == "ar") ar else en
}
