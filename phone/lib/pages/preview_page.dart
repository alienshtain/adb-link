import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api.dart';
import '../strings.dart';

/// Look at the pictures of a folder on the computer before downloading them. Swipe for the next one.
class ImagePreviewPage extends StatefulWidget {
  final Api api;
  final String dir;
  final List<String> names;
  final int index;
  final Future<void> Function(String name) onDownload;
  const ImagePreviewPage({
    super.key,
    required this.api,
    required this.dir,
    required this.names,
    required this.index,
    required this.onDownload,
  });

  @override
  State<ImagePreviewPage> createState() => _ImagePreviewPageState();
}

class _ImagePreviewPageState extends State<ImagePreviewPage> {
  late final PageController controller = PageController(initialPage: widget.index);
  late int current = widget.index;

  String _join(String name) => widget.dir.endsWith('/') ? '${widget.dir}$name' : '${widget.dir}/$name';

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(widget.names[current], style: const TextStyle(fontSize: 15)),
        actions: [
          IconButton(
            icon: const Icon(Icons.download),
            tooltip: tr('Download to phone'),
            onPressed: () => widget.onDownload(widget.names[current]),
          ),
        ],
      ),
      body: PageView.builder(
        controller: controller,
        itemCount: widget.names.length,
        onPageChanged: (i) => setState(() => current = i),
        itemBuilder: (ctx, i) {
          final url = widget.api.fileUri('thumb', _join(widget.names[i]), {'w': '1800'}).toString();
          return InteractiveViewer(
            minScale: 1,
            maxScale: 5,
            child: Center(
              child: Image.network(
                url,
                headers: widget.api.authHeaders,
                fit: BoxFit.contain,
                loadingBuilder: (c, child, p) {
                  if (p == null) return child;
                  final total = p.expectedTotalBytes;
                  return Center(
                    child: CircularProgressIndicator(
                      value: total != null ? p.cumulativeBytesLoaded / total : null,
                    ),
                  );
                },
                errorBuilder: (c, err, st) => Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(tr('Cannot show this picture'), style: const TextStyle(color: Colors.white)),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

/// Read the first part of a text file from the computer.
class TextPreviewPage extends StatefulWidget {
  final Api api;
  final String path;
  final String name;
  final Future<void> Function(String name) onDownload;
  const TextPreviewPage({
    super.key,
    required this.api,
    required this.path,
    required this.name,
    required this.onDownload,
  });

  @override
  State<TextPreviewPage> createState() => _TextPreviewPageState();
}

class _TextPreviewPageState extends State<TextPreviewPage> {
  String? text;
  bool truncated = false;
  String? error;
  double fontSize = 13;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await widget.api.text(widget.path);
      if (!mounted) return;
      setState(() {
        text = '${r['text']}';
        truncated = r['truncated'] == true;
      });
    } on ApiError catch (e) {
      if (mounted) {
        setState(() => error = e.status == 415 ? tr('This is not a text file') : e.message);
      }
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    Widget body;
    if (error != null) {
      body = Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(error!)));
    } else if (text == null) {
      body = const Center(child: CircularProgressIndicator());
    } else {
      body = Column(children: [
        if (truncated)
          Container(
            width: double.infinity,
            color: scheme.secondaryContainer,
            padding: const EdgeInsets.all(8),
            child: Text(tr('Only the first part of the file is shown. Download it to read all.'),
                style: const TextStyle(fontSize: 12)),
          ),
        Expanded(
          child: Scrollbar(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(14),
              child: SelectableText(
                text!.isEmpty ? tr('Empty file') : text!,
                style: TextStyle(fontFamily: 'monospace', fontSize: fontSize),
              ),
            ),
          ),
        ),
      ]);
    }
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.name, style: const TextStyle(fontSize: 15)),
        actions: [
          IconButton(
            icon: const Icon(Icons.text_decrease),
            onPressed: () => setState(() => fontSize = (fontSize - 1).clamp(9.0, 26.0).toDouble()),
          ),
          IconButton(
            icon: const Icon(Icons.text_increase),
            onPressed: () => setState(() => fontSize = (fontSize + 1).clamp(9.0, 26.0).toDouble()),
          ),
          IconButton(
            icon: const Icon(Icons.copy),
            tooltip: tr('Copy'),
            onPressed: text == null
                ? null
                : () {
                    Clipboard.setData(ClipboardData(text: text!));
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(tr('Copied'))));
                  },
          ),
          IconButton(
            icon: const Icon(Icons.download),
            tooltip: tr('Download to phone'),
            onPressed: () => widget.onDownload(widget.name),
          ),
        ],
      ),
      body: body,
    );
  }
}
