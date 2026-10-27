package com.alienshtain.adblink

import android.Manifest
import android.app.Activity
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

class MainActivity : FlutterActivity() {
    companion object {
        private const val REQ_FILES = 4711
        private const val REQ_TREE = 4712
    }

    private var channel: MethodChannel? = null
    private var pending: MethodChannel.Result? = null

    /** Runs an upload on a worker thread; progress goes to Dart, the final answer to [result]. */
    private fun runUpload(result: MethodChannel.Result, to: String?, items: () -> List<Uploader.Item>) {
        Thread {
            val res: Map<String, Any> = try {
                Uploader.run(this, items(), to) { p ->
                    Handler(Looper.getMainLooper()).post { channel?.invokeMethod("uploadProgress", p) }
                }
            } catch (e: Exception) {
                mapOf("ok" to 0, "failed" to 1, "errors" to listOf(e.message ?: "upload failed"))
            }
            runOnUiThread { result.success(res) }
        }.start()
    }

    private fun openPicker(result: MethodChannel.Result, intent: Intent, code: Int) {
        if (pending != null) {
            result.error("busy", "Another picker is open", null)
            return
        }
        pending = result
        try {
            startActivityForResult(intent, code)
        } catch (e: Exception) {
            pending = null
            result.error("pick", e.message, null)
        }
    }

    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == REQ_FILES || requestCode == REQ_TREE) {
            val r = pending
            pending = null
            if (r == null) return
            if (resultCode != Activity.RESULT_OK || data == null) {
                r.success(if (requestCode == REQ_TREE) null else ArrayList<String>())
            } else if (requestCode == REQ_TREE) {
                r.success(data.data?.toString())
            } else {
                val list = ArrayList<String>()
                val clip = data.clipData
                if (clip != null) {
                    for (i in 0 until clip.itemCount) list.add(clip.getItemAt(i).uri.toString())
                } else {
                    data.data?.let { list.add(it.toString()) }
                }
                r.success(list)
            }
            return
        }
        super.onActivityResult(requestCode, resultCode, data)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val ch = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "adblink/native")
        channel = ch
        ch.setMethodCallHandler { call, result ->
            when (call.method) {
                "serviceRunning" -> result.success(LinkService.running)
                "startService" -> {
                    getSharedPreferences("adblink", Context.MODE_PRIVATE).edit().putBoolean("autostart", true).apply()
                    val i = Intent(this, LinkService::class.java)
                    try {
                        if (Build.VERSION.SDK_INT >= 26) startForegroundService(i) else startService(i)
                        result.success(null)
                    } catch (e: Exception) {
                        result.error("start", e.message, null)
                    }
                }
                "stopService" -> {
                    getSharedPreferences("adblink", Context.MODE_PRIVATE).edit().putBoolean("autostart", false).apply()
                    stopService(Intent(this, LinkService::class.java))
                    result.success(null)
                }
                "notificationAccess" -> {
                    val flat = Settings.Secure.getString(contentResolver, "enabled_notification_listeners") ?: ""
                    result.success(flat.contains(packageName))
                }
                "openNotificationAccess" -> {
                    startActivity(Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS"))
                    result.success(null)
                }
                "requestNotifications" -> {
                    if (Build.VERSION.SDK_INT >= 33) {
                        requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 11)
                    }
                    result.success(null)
                }
                "ignoreBattery" -> {
                    try {
                        startActivity(
                            Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                                .setData(Uri.parse("package:$packageName"))
                        )
                    } catch (e: Exception) {
                        startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                    }
                    result.success(null)
                }
                "pickFiles" -> {
                    val i = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "*/*"
                        putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                    }
                    openPicker(result, i, REQ_FILES)
                }
                "pickFolder" -> openPicker(result, Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), REQ_TREE)
                "uploadUris" -> {
                    val uris = (call.argument<List<String>>("uris") ?: emptyList()).map { Uri.parse(it) }
                    runUpload(result, call.argument<String>("to")) { Uploader.itemsFromUris(this, uris) }
                }
                "uploadTree" -> {
                    val tree = Uri.parse(call.argument<String>("uri") ?: "")
                    runUpload(result, call.argument<String>("to")) { Uploader.scanTree(this, tree) }
                }
                "saveToDownloads" -> {
                    val path = call.argument<String>("path")
                    val name = call.argument<String>("name")
                    val sub = (call.argument<String>("sub") ?: "").split('/')
                        .filter { it.isNotEmpty() && it != "." && it != ".." }.joinToString("/")
                    val rootRaw = (call.argument<String>("root") ?: "Documents/ADB Link").split('/')
                        .filter { it.isNotEmpty() && it != "." && it != ".." }
                    val root = (if (rootRaw.isNotEmpty() && (rootRaw[0] == "Documents" || rootRaw[0] == "Download"))
                        rootRaw else listOf("Documents") + rootRaw).joinToString("/")
                    val rel = if (sub.isEmpty()) root else "$root/$sub"
                    if (path == null || name == null || Build.VERSION.SDK_INT < 29) {
                        result.success(false)
                    } else {
                        Thread {
                            val ok = try {
                                val values = ContentValues().apply {
                                    put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                                    put(MediaStore.MediaColumns.RELATIVE_PATH, rel)
                                }
                                // Downloads has its own table; Documents (and everything else) lives in Files
                                val table = if (rel.startsWith("Download"))
                                    MediaStore.Downloads.EXTERNAL_CONTENT_URI
                                else MediaStore.Files.getContentUri("external")
                                val uri = contentResolver.insert(table, values)
                                if (uri == null) false else {
                                    contentResolver.openOutputStream(uri)?.use { out ->
                                        File(path).inputStream().use { it.copyTo(out, 64 * 1024) }
                                    }
                                    true
                                }
                            } catch (e: Exception) {
                                false
                            }
                            runOnUiThread { result.success(ok) }
                        }.start()
                    }
                }
                else -> result.notImplemented()
            }
        }
    }
}
