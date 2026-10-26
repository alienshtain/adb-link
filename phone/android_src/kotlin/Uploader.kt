package com.alienshtain.adblink

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import android.provider.OpenableColumns
import org.json.JSONObject
import java.io.File
import java.io.InputStream
import java.net.URLEncoder

/**
 * Sends phone files and folders to the computer (POST /files?op=put).
 * It reads content:// documents picked with Android's own pickers, so no storage permission is needed
 * and big files are streamed (never loaded into memory).
 */
object Uploader {
    class Item(val uri: Uri, val name: String, val dir: String, val size: Long)

    private fun enc(s: String): String = URLEncoder.encode(s, "UTF-8")

    private fun nameAndSize(ctx: Context, u: Uri): Pair<String, Long> {
        var name = u.lastPathSegment ?: "file"
        var size = -1L
        try {
            ctx.contentResolver.query(u, null, null, null, null)?.use { cur ->
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

    fun itemsFromUris(ctx: Context, uris: List<Uri>): List<Item> = uris.map { u ->
        val (name, size) = nameAndSize(ctx, u)
        Item(u, name, "", size)
    }

    /** Every file inside the picked folder; the folder's own name is the first part of each path. */
    fun scanTree(ctx: Context, tree: Uri): List<Item> {
        val rootId = DocumentsContract.getTreeDocumentId(tree)
        val rootUri = DocumentsContract.buildDocumentUriUsingTree(tree, rootId)
        var rootName = "folder"
        ctx.contentResolver.query(
            rootUri, arrayOf(DocumentsContract.Document.COLUMN_DISPLAY_NAME), null, null, null
        )?.use { c ->
            if (c.moveToFirst()) rootName = c.getString(0) ?: "folder"
        }
        val out = ArrayList<Item>()
        walk(ctx, tree, rootId, rootName, out)
        return out
    }

    private fun walk(ctx: Context, tree: Uri, docId: String, rel: String, out: MutableList<Item>) {
        val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, docId)
        val cols = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_SIZE
        )
        val subs = ArrayList<Pair<String, String>>()
        ctx.contentResolver.query(children, cols, null, null, null)?.use { c ->
            while (c.moveToNext()) {
                val id = c.getString(0) ?: continue
                val name = c.getString(1) ?: continue
                val mime = c.getString(2) ?: ""
                if (mime == DocumentsContract.Document.MIME_TYPE_DIR) {
                    subs.add(Pair(id, name))
                } else {
                    val size = if (c.isNull(3)) -1L else c.getLong(3)
                    out.add(Item(DocumentsContract.buildDocumentUriUsingTree(tree, id), name, rel, size))
                }
            }
        }
        for ((id, name) in subs) walk(ctx, tree, id, "$rel/$name", out)
    }

    /** Uploads every item. [to] is a folder on the computer (null = its Downloads/FromPhone). */
    fun run(ctx: Context, items: List<Item>, to: String?, progress: (Map<String, Any>) -> Unit): Map<String, Any> {
        val c = Link.cfg(ctx)
            ?: return mapOf("ok" to 0, "failed" to items.size, "errors" to listOf("Not paired with a computer"))
        if (items.isEmpty()) return mapOf("ok" to 0, "failed" to 0, "errors" to emptyList<String>())
        var total = 0L
        for (item in items) if (item.size > 0) total += item.size
        var doneBytes = 0L
        var lastReport = 0L
        var ok = 0
        val errors = ArrayList<String>()

        fun report(index: Int, name: String, force: Boolean) {
            val now = System.currentTimeMillis()
            if (!force && now - lastReport < 250) return
            lastReport = now
            progress(
                mapOf(
                    "files" to items.size, "doneFiles" to index, "bytes" to total,
                    "doneBytes" to doneBytes, "name" to name
                )
            )
        }

        for ((index, item) in items.withIndex()) {
            report(index, item.name, true)
            val err = upload(ctx, c, item, to) { n ->
                doneBytes += n
                report(index, item.name, false)
            }
            if (err == null) ok++ else errors.add("${item.name}: $err")
        }
        return mapOf("ok" to ok, "failed" to errors.size, "errors" to errors.take(30))
    }

    /** Returns null when it worked, otherwise the reason. */
    private fun upload(ctx: Context, c: Cfg, item: Item, to: String?, onBytes: (Long) -> Unit): String? {
        var temp: File? = null
        try {
            var size = item.size
            var input: InputStream = ctx.contentResolver.openInputStream(item.uri) ?: return "cannot open the file"
            if (size < 0) { // the computer needs the length first: copy to a temporary file
                val f = File.createTempFile("up", ".tmp", ctx.cacheDir)
                temp = f
                input.use { i -> f.outputStream().use { o -> i.copyTo(o, 64 * 1024) } }
                size = f.length()
                input = f.inputStream()
            }
            var path = "/files?op=put&name=" + enc(item.name)
            if (item.dir.isNotEmpty()) path += "&dir=" + enc(item.dir)
            if (!to.isNullOrEmpty()) path += "&to=" + enc(to)
            val conn = Link.open(c, "POST", path, 600000)
            try {
                conn.doOutput = true
                conn.setFixedLengthStreamingMode(size)
                var writeError: Exception? = null
                try {
                    input.use { i ->
                        conn.outputStream.use { o ->
                            val buf = ByteArray(64 * 1024)
                            while (true) {
                                val n = i.read(buf)
                                if (n < 0) break
                                o.write(buf, 0, n)
                                onBytes(n.toLong())
                            }
                        }
                    }
                } catch (e: Exception) {
                    writeError = e // the computer may have refused early: its answer explains why
                }
                val code = try {
                    conn.responseCode
                } catch (e: Exception) {
                    return (writeError ?: e).message ?: "connection lost"
                }
                if (code == 200) {
                    conn.inputStream.use { it.readBytes() }
                    return null
                }
                val body = try {
                    conn.errorStream?.use { String(it.readBytes(), Charsets.UTF_8) }
                } catch (e: Exception) {
                    null
                }
                val msg = try {
                    JSONObject(body ?: "").optString("error")
                } catch (e: Exception) {
                    ""
                }
                return if (msg.isNotEmpty()) msg else "HTTP $code"
            } finally {
                conn.disconnect()
            }
        } catch (e: Exception) {
            return e.message ?: e.javaClass.simpleName
        } finally {
            temp?.delete()
        }
    }
}
