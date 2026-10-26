import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api.dart';
import '../strings.dart';
import 'command_edit_page.dart';

class _Entry {
  final String cmd;
  final String cwd;
  String output = '';
  int? code;
  bool timedOut = false;
  bool done = false;
  _Entry(this.cmd, this.cwd);
}

/// Run any command on the computer and read its output. Not for programs that wait for keys (nano, top).
class TerminalPage extends StatefulWidget {
  final Api api;
  const TerminalPage({super.key, required this.api});

  @override
  State<TerminalPage> createState() => _TerminalPageState();
}

class _TerminalPageState extends State<TerminalPage> {
  final input = TextEditingController();
  final scroll = ScrollController();
  final entries = <_Entry>[];
  List<String> history = [];
  String cwd = '';
  String home = '';
  bool busy = false;

  @override
  void initState() {
    super.initState();
    _loadHistory();
    _loadHome();
  }

  @override
  void dispose() {
    input.dispose();
    scroll.dispose();
    super.dispose();
  }

  Future<void> _loadHome() async {
    try {
      final i = await widget.api.info();
      if (!mounted) return;
      setState(() {
        home = '${i['home'] ?? ''}';
        if (cwd.isEmpty) cwd = home;
      });
    } catch (_) {}
  }

  Future<void> _loadHistory() async {
    try {
      final p = await SharedPreferences.getInstance();
      final raw = p.getString('term_history');
      if (raw != null && mounted) {
        setState(() => history = (jsonDecode(raw) as List).cast<String>());
      }
    } catch (_) {}
  }

  Future<void> _remember(String cmd) async {
    history.remove(cmd);
    history.insert(0, cmd);
    if (history.length > 40) history = history.sublist(0, 40);
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString('term_history', jsonEncode(history));
    } catch (_) {}
  }

  String _short(String path) {
    if (home.isNotEmpty && path.startsWith(home)) return '~${path.substring(home.length)}';
    return path;
  }

  void _scrollDown() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (scroll.hasClients) {
        scroll.animateTo(scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _run([String? preset]) async {
    final cmd = (preset ?? input.text).trim();
    if (cmd.isEmpty || busy) return;
    input.clear();
    final e = _Entry(cmd, cwd);
    setState(() {
      entries.add(e);
      busy = true;
    });
    _scrollDown();
    _remember(cmd);
    try {
      final r = await widget.api.shell(cmd, cwd);
      var out = '${r['output'] ?? r['error'] ?? ''}';
      if (out.length > 30000) out = out.substring(out.length - 30000);
      e.output = out;
      e.code = (r['code'] as num?)?.toInt();
      e.timedOut = r['timed_out'] == true;
      final nc = r['cwd'];
      if (nc is String && nc.isNotEmpty) cwd = nc;
    } catch (err) {
      e.output = '$err';
      e.code = -1;
    }
    e.done = true;
    if (mounted) setState(() => busy = false);
    _scrollDown();
  }

  void _toast(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _saveAsCommand(String cmd) async {
    final saved = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => CommandEditPage(api: widget.api, presetCmd: cmd)),
    );
    if (saved == true) _toast(tr('Saved in Commands'));
  }

  void _pickHistory() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => SafeArea(
        child: history.isEmpty
            ? Padding(padding: const EdgeInsets.all(24), child: Text(tr('No history yet')))
            : ListView(
                shrinkWrap: true,
                children: [
                  for (final h in history)
                    ListTile(
                      dense: true,
                      title: Text(h, style: const TextStyle(fontFamily: 'monospace', fontSize: 13)),
                      onTap: () {
                        Navigator.pop(ctx);
                        input.text = h;
                        input.selection = TextSelection.collapsed(offset: h.length);
                      },
                    ),
                ],
              ),
      ),
    );
  }

  Widget _entry(_Entry e) {
    final scheme = Theme.of(context).colorScheme;
    const mono = TextStyle(fontFamily: 'monospace', fontSize: 13);
    final failed = e.done && e.code != 0;
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: SelectableText(
              '${_short(e.cwd)} \$ ${e.cmd}',
              style: mono.copyWith(color: scheme.primary, fontWeight: FontWeight.bold),
              textDirection: TextDirection.ltr,
            ),
          ),
          PopupMenuButton<String>(
            icon: const Icon(Icons.more_vert, size: 20),
            onSelected: (v) {
              if (v == 'again') _run(e.cmd);
              if (v == 'copy') {
                Clipboard.setData(ClipboardData(text: e.output));
                _toast(tr('Copied'));
              }
              if (v == 'save') _saveAsCommand(e.cmd);
            },
            itemBuilder: (ctx) => [
              PopupMenuItem(value: 'again', child: Text(tr('Run again'))),
              PopupMenuItem(value: 'copy', child: Text(tr('Copy output'))),
              PopupMenuItem(value: 'save', child: Text(tr('Save as command'))),
            ],
          ),
        ]),
        if (!e.done)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 6),
            child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
          )
        else if (e.output.isNotEmpty)
          SelectableText(e.output, style: mono, textDirection: TextDirection.ltr),
        if (e.timedOut)
          Text(tr('Stopped: it took too long (60 s).'), style: TextStyle(color: scheme.error)),
        if (failed && !e.timedOut)
          Text('${tr('Exit code')}: ${e.code}', style: TextStyle(color: scheme.error, fontSize: 12)),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(children: [
      Container(
        color: scheme.surfaceContainerHighest,
        padding: const EdgeInsets.fromLTRB(16, 4, 4, 4),
        child: Row(children: [
          Icon(Icons.terminal, size: 18, color: scheme.primary),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              cwd.isEmpty ? tr('Terminal') : _short(cwd),
              style: const TextStyle(fontFamily: 'monospace', fontSize: 13),
              overflow: TextOverflow.ellipsis,
              textDirection: TextDirection.ltr,
            ),
          ),
          IconButton(icon: const Icon(Icons.history), tooltip: tr('History'), onPressed: _pickHistory),
          IconButton(
            icon: const Icon(Icons.delete_sweep),
            tooltip: tr('Clear'),
            onPressed: () => setState(entries.clear),
          ),
        ]),
      ),
      Expanded(
        child: entries.isEmpty
            ? Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    tr('Type a command to run it on the computer. For example: ls, df -h, ip a, git pull.'),
                    textAlign: TextAlign.center,
                  ),
                ),
              )
            : ListView(
                controller: scroll,
                padding: const EdgeInsets.all(16),
                children: [for (final e in entries) _entry(e)],
              ),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
        child: Row(children: [
          Expanded(
            child: TextField(
              controller: input,
              autocorrect: false,
              enableSuggestions: false,
              textInputAction: TextInputAction.send,
              onSubmitted: (_) => _run(),
              style: const TextStyle(fontFamily: 'monospace'),
              textDirection: TextDirection.ltr,
              decoration: InputDecoration(
                hintText: tr('Command'),
                border: const OutlineInputBorder(),
                isDense: true,
              ),
            ),
          ),
          const SizedBox(width: 8),
          IconButton.filled(
            onPressed: busy ? null : () => _run(),
            icon: busy
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.send),
          ),
        ]),
      ),
    ]);
  }
}
