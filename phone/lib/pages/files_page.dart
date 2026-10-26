import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import '../api.dart';
import '../native.dart';
import '../strings.dart';
import 'preview_page.dart';

const _imageExt = {'jpg', 'jpeg', 'png', 'webp', 'bmp', 'gif'};
const _textExt = {
  'txt', 'md', 'log', 'json', 'yaml', 'yml', 'xml', 'csv', 'tsv', 'ini', 'conf', 'cfg', 'sh', 'bash',
  'py', 'js', 'ts', 'dart', 'html', 'htm', 'css', 'java', 'kt', 'c', 'cpp', 'h', 'hpp', 'rs', 'go',
  'toml', 'sql', 'srt', 'tex', 'php', 'rb', 'service', 'desktop', 'env', 'gitignore', 'rst', 'lua',
};

String _ext(String name) {
  final i = name.lastIndexOf('.');
  return i <= 0 ? '' : name.substring(i + 1).toLowerCase();
}

bool _isImage(String name) => _imageExt.contains(_ext(name));

/// Files without an extension (README, Makefile, .bashrc) are tried as text too.
bool _isText(String name) {
  final e = _ext(name);
  return e.isEmpty || _textExt.contains(e);
}

String _size(num b) {
  if (b < 1024) return '${b.toInt()} B';
  if (b < 1024 * 1024) return '${(b / 1024).toStringAsFixed(0)} KB';
  if (b < 1024 * 1024 * 1024) return '${(b / 1024 / 1024).toStringAsFixed(1)} MB';
  return '${(b / 1024 / 1024 / 1024).toStringAsFixed(2)} GB';
}

String _date(num seconds) {
  final d = DateTime.fromMillisecondsSinceEpoch(seconds.toInt() * 1000);
  String two(int n) => n.toString().padLeft(2, '0');
  return '${d.year}-${two(d.month)}-${two(d.day)}  ${two(d.hour)}:${two(d.minute)}';
}

class FilesPage extends StatefulWidget {
  final Api api;
  const FilesPage({super.key, required this.api});

  @override
  State<FilesPage> createState() => _FilesPageState();
}

class _FilesPageState extends State<FilesPage> {
  String path = '';
  String home = '';
  List<dynamic> items = [];
  String? error;
  bool loading = true;
  bool hidden = false;
  bool busy = false;
  double? progress;
  String? progressText;
  bool uploadHere = false;

  @override
  void initState() {
    super.initState();
    _open('');
  }

  Future<void> _open(String target) async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final r = await widget.api.list(target, hidden: hidden);
      if (!mounted) return;
      setState(() {
        path = r['path'] as String;
        home = r['home'] as String;
        items = r['items'] as List<dynamic>;
        loading = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          error = '$e';
          loading = false;
        });
      }
    }
  }

  void _up() {
    if (path.isEmpty || path == '/') return;
    final i = path.lastIndexOf('/');
    _open(i <= 0 ? '/' : path.substring(0, i));
  }

  String _join(String name) => path.endsWith('/') ? '$path$name' : '$path/$name';

  void _toast(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  void _start(String text) {
    setState(() {
      busy = true;
      progress = null;
      progressText = text;
    });
  }

  void _stop() {
    if (!mounted) return;
    setState(() {
      busy = false;
      progress = null;
      progressText = null;
    });
  }

  // ---------------------------------------------------------------- download

  Future<void> _download(String name) async {
    if (busy) return;
    _start(name);
    try {
      final tmp = await getTemporaryDirectory();
      final file = File('${tmp.path}/dl_single');
      await widget.api.download(_join(name), file, (p) {
        if (mounted) setState(() => progress = p);
      });
      final ok = await Native.saveToDownloads(file.path, name);
      await file.delete().catchError((_) => file);
      _toast(ok ? tr('Saved in Downloads/FromPC') : tr('Failed'));
    } catch (e) {
      _toast('$e');
    } finally {
      _stop();
    }
  }

  /// Downloads every file of a folder into Downloads/FromPC/<folder name>/...
  Future<void> _downloadFolder(String name) async {
    if (busy) return;
    _start(tr('Reading the folder...'));
    try {
      final t = await widget.api.tree(_join(name));
      final files = (t['files'] as List).cast<Map<String, dynamic>>();
      if (files.isEmpty) {
        _toast(tr('Empty folder'));
        return;
      }
      final total = files.fold<num>(0, (a, f) => a + (f['size'] as num));
      final tmp = await getTemporaryDirectory();
      var done = 0;
      var failed = 0;
      num doneBytes = 0;
      for (var i = 0; i < files.length; i++) {
        final f = files[i];
        final rel = f['rel'] as String;
        final slash = rel.lastIndexOf('/');
        final dir = slash < 0 ? '' : rel.substring(0, slash);
        final base = slash < 0 ? rel : rel.substring(slash + 1);
        final local = File('${tmp.path}/dl_$i');
        if (mounted) setState(() => progressText = '${i + 1}/${files.length}  $base');
        try {
          await widget.api.download('${_join(name)}/$rel', local, (p) {
            if (!mounted) return;
            final soFar = doneBytes + (f['size'] as num) * p;
            setState(() => progress = total > 0 ? (soFar / total).clamp(0.0, 1.0).toDouble() : null);
          });
          final ok = await Native.saveToDownloads(local.path, base, sub: dir.isEmpty ? name : '$name/$dir');
          if (ok) {
            done++;
          } else {
            failed++;
          }
        } catch (_) {
          failed++;
        } finally {
          try {
            if (await local.exists()) await local.delete();
          } catch (_) {}
        }
        doneBytes += f['size'] as num;
      }
      final where = 'Downloads/FromPC/$name';
      _toast(failed == 0 ? '${tr('Saved in')} $where  ($done)' : '$where:  $done OK,  $failed ${tr('Failed')}');
      if (t['truncated'] == true) _toast(tr('The folder is very big: only the first 20000 files were downloaded.'));
    } catch (e) {
      _toast('$e');
    } finally {
      _stop();
    }
  }

  // ---------------------------------------------------------------- upload

  Future<void> _uploadSheet() async {
    if (busy) return;
    await showModalBottomSheet<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSheet) => SafeArea(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            ListTile(
              leading: const Icon(Icons.upload_file),
              title: Text(tr('Upload files')),
              onTap: () {
                Navigator.pop(ctx);
                _pickAndUpload(false);
              },
            ),
            ListTile(
              leading: const Icon(Icons.drive_folder_upload),
              title: Text(tr('Upload a folder')),
              onTap: () {
                Navigator.pop(ctx);
                _pickAndUpload(true);
              },
            ),
            SwitchListTile(
              title: Text(tr('Save in the folder I am looking at')),
              subtitle: Text(uploadHere ? path : tr('Downloads/FromPhone on the computer')),
              value: uploadHere,
              onChanged: (v) {
                setSheet(() {});
                setState(() => uploadHere = v);
              },
            ),
          ]),
        ),
      ),
    );
  }

  Future<void> _pickAndUpload(bool folder) async {
    final to = uploadHere ? path : null;
    try {
      String? uri;
      var uris = <String>[];
      if (folder) {
        uri = await Native.pickFolder();
        if (uri == null) return;
      } else {
        uris = await Native.pickFiles();
        if (uris.isEmpty) return;
      }
      _start(tr('Uploading...'));
      Native.onUploadProgress = (m) {
        if (!mounted) return;
        final bytes = (m['bytes'] as num?) ?? 0;
        final doneBytes = (m['doneBytes'] as num?) ?? 0;
        final files = ((m['files'] as num?) ?? 0).toInt();
        final doneFiles = ((m['doneFiles'] as num?) ?? 0).toInt();
        final n = files == 0 ? 0 : (doneFiles + 1 > files ? files : doneFiles + 1);
        setState(() {
          progress = bytes > 0 ? (doneBytes / bytes).clamp(0.0, 1.0).toDouble() : null;
          progressText = '$n/$files  ${m['name'] ?? ''}';
        });
      };
      final r = folder ? await Native.uploadTree(uri!, to: to) : await Native.uploadUris(uris, to: to);
      _uploadDone(r, to);
    } catch (e) {
      _toast('$e');
    } finally {
      Native.onUploadProgress = null;
      _stop();
    }
  }

  void _uploadDone(Map<String, dynamic> r, String? to) {
    final ok = (r['ok'] as num?)?.toInt() ?? 0;
    final failed = (r['failed'] as num?)?.toInt() ?? 0;
    final errors = ((r['errors'] as List?) ?? const []).map((e) => '$e').toList();
    if (failed == 0 && ok > 0) {
      _toast('${tr('Uploaded')}: $ok  -  ${to ?? tr('Downloads/FromPhone on the computer')}');
    } else if (mounted) {
      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text('${tr('Uploaded')}: $ok     ${tr('Failed')}: $failed'),
          content: SingleChildScrollView(child: Text(errors.isEmpty ? tr('Nothing was sent') : errors.join('\n'))),
          actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('OK'))],
        ),
      );
    }
    if (to != null && ok > 0) _open(path);
  }

  // ---------------------------------------------------------------- details and preview

  Widget _row(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 120, child: Text(label, style: const TextStyle(color: Colors.grey))),
          Expanded(child: Text(value)),
        ]),
      );

  Future<void> _folderSheet(String name) async {
    final full = _join(name);
    final info = widget.api.fileInfo(full);
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              const Icon(Icons.folder, color: Color(0xFFF5A524), size: 36),
              const SizedBox(width: 12),
              Expanded(child: Text(name, style: Theme.of(ctx).textTheme.titleMedium)),
            ]),
            const SizedBox(height: 8),
            _row(tr('Location'), full),
            FutureBuilder<Map<String, dynamic>>(
              future: info,
              builder: (c, s) {
                if (s.hasError) return Text('${s.error}');
                if (!s.hasData) {
                  return const Padding(padding: EdgeInsets.symmetric(vertical: 8), child: LinearProgressIndicator());
                }
                final i = s.data!;
                final more = i['truncated'] == true ? '+' : '';
                return Column(children: [
                  _row(tr('Files inside'), '${i['files']}$more'),
                  _row(tr('Folders inside'), '${i['dirs']}$more'),
                  _row(tr('Size'), '${_size(i['size'] as num)}${more.isEmpty ? '' : '+'}'),
                  _row(tr('Modified'), _date(i['mtime'] as num)),
                ]);
              },
            ),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(
                child: FilledButton.icon(
                  icon: const Icon(Icons.download),
                  label: Text(tr('Download folder')),
                  onPressed: () {
                    Navigator.pop(ctx);
                    _downloadFolder(name);
                  },
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton(
                onPressed: () {
                  Navigator.pop(ctx);
                  _open(full);
                },
                child: Text(tr('Open')),
              ),
            ]),
          ]),
        ),
      ),
    );
  }

  Future<void> _fileSheet(Map<String, dynamic> it) async {
    final name = it['name'] as String;
    await showModalBottomSheet<void>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(name, style: Theme.of(ctx).textTheme.titleMedium),
            const SizedBox(height: 8),
            _row(tr('Location'), _join(name)),
            _row(tr('Size'), _size(it['size'] as num)),
            if (it['mtime'] != null) _row(tr('Modified'), _date(it['mtime'] as num)),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(
                child: FilledButton.icon(
                  icon: const Icon(Icons.download),
                  label: Text(tr('Download to phone')),
                  onPressed: () {
                    Navigator.pop(ctx);
                    _download(name);
                  },
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton(
                onPressed: () {
                  Navigator.pop(ctx);
                  _openText(name);
                },
                child: Text(tr('Read as text')),
              ),
            ]),
          ]),
        ),
      ),
    );
  }

  void _openImage(String name) {
    final names = [
      for (final it in items.cast<Map<String, dynamic>>())
        if (it['dir'] != true && _isImage(it['name'] as String)) it['name'] as String
    ];
    final index = names.indexOf(name);
    if (index < 0) return;
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ImagePreviewPage(
          api: widget.api,
          dir: path,
          names: names,
          index: index,
          onDownload: _download,
        ),
      ),
    );
  }

  void _openText(String name) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => TextPreviewPage(api: widget.api, path: _join(name), name: name, onDownload: _download),
      ),
    );
  }

  void _tapItem(Map<String, dynamic> it) {
    final name = it['name'] as String;
    if (it['dir'] == true) {
      _open(_join(name));
    } else if (_isImage(name)) {
      _openImage(name);
    } else if (_isText(name)) {
      _openText(name);
    } else {
      _fileSheet(it);
    }
  }

  Widget _leading(Map<String, dynamic> it) {
    final name = it['name'] as String;
    if (it['dir'] == true) return const Icon(Icons.folder, color: Color(0xFFF5A524), size: 36);
    if (_isImage(name)) {
      final url = widget.api.fileUri('thumb', _join(name), {'w': '112'}).toString();
      return ClipRRect(
        borderRadius: BorderRadius.circular(8),
        child: SizedBox(
          width: 44,
          height: 44,
          child: Image.network(
            url,
            headers: widget.api.authHeaders,
            fit: BoxFit.cover,
            cacheWidth: 112,
            errorBuilder: (c, e, s) => const Icon(Icons.image_outlined),
          ),
        ),
      );
    }
    return Icon(_isText(name) ? Icons.description_outlined : Icons.insert_drive_file_outlined);
  }

  @override
  Widget build(BuildContext context) {
    final title = path.isEmpty ? tr('Files') : (home.isNotEmpty ? path.replaceFirst(home, '~') : path);
    return Scaffold(
      appBar: AppBar(
        title: Text(title, style: const TextStyle(fontSize: 14)),
        leading: IconButton(icon: const Icon(Icons.arrow_upward), onPressed: _up),
        actions: [
          IconButton(
            icon: Icon(hidden ? Icons.visibility : Icons.visibility_off),
            tooltip: tr('Hidden files'),
            onPressed: () {
              setState(() => hidden = !hidden);
              _open(path);
            },
          ),
          IconButton(icon: const Icon(Icons.refresh), onPressed: () => _open(path)),
        ],
        bottom: busy
            ? PreferredSize(
                preferredSize: const Size.fromHeight(30),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  LinearProgressIndicator(value: progress),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 3, 12, 3),
                    child: Text(progressText ?? '', style: const TextStyle(fontSize: 11), maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                  ),
                ]),
              )
            : null,
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: busy ? null : _uploadSheet,
        icon: const Icon(Icons.upload_file),
        label: Text(tr('Upload to computer')),
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : error != null
              ? Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(error!)))
              : items.isEmpty
                  ? Center(child: Text(tr('Empty folder')))
                  : ListView.builder(
                      padding: const EdgeInsets.only(bottom: 90),
                      itemCount: items.length,
                      itemBuilder: (ctx, i) {
                        final it = items[i] as Map<String, dynamic>;
                        final isDir = it['dir'] == true;
                        final name = it['name'] as String;
                        return ListTile(
                          leading: _leading(it),
                          title: Text(name),
                          subtitle: isDir ? null : Text(_size(it['size'] as num)),
                          trailing: isDir
                              ? null
                              : IconButton(
                                  icon: const Icon(Icons.download),
                                  tooltip: tr('Download to phone'),
                                  onPressed: busy ? null : () => _download(name)),
                          onTap: () => _tapItem(it),
                          onLongPress: () => isDir ? _folderSheet(name) : _fileSheet(it),
                        );
                      },
                    ),
    );
  }
}
