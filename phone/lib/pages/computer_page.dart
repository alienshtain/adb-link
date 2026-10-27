import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../icons.dart';
import '../strings.dart';
import 'command_edit_page.dart';

String _size(num bytes) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  double v = bytes.toDouble();
  var i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return '${v.toStringAsFixed(i == 0 ? 0 : 1)} ${units[i]}';
}

String _uptime(int s) {
  final d = s ~/ 86400, h = (s % 86400) ~/ 3600, m = (s % 3600) ~/ 60;
  return d > 0 ? '${d}d ${h}h' : '${h}h ${m}m';
}

class ComputerPage extends StatefulWidget {
  final Api api;
  const ComputerPage({super.key, required this.api});

  @override
  State<ComputerPage> createState() => _ComputerPageState();
}

class _ComputerPageState extends State<ComputerPage> {
  Map<String, dynamic>? info;
  List<dynamic> commands = [];
  String? error;
  Timer? timer;

  @override
  void initState() {
    super.initState();
    _load();
    timer = Timer.periodic(const Duration(seconds: 10), (_) => _refreshInfo());
  }

  @override
  void dispose() {
    timer?.cancel();
    super.dispose();
  }

  Future<void> _refreshInfo() async {
    try {
      final i = await widget.api.info();
      if (mounted) setState(() => info = i);
    } catch (_) {}
  }

  Future<void> _load() async {
    try {
      final i = await widget.api.info();
      final c = await widget.api.commands();
      if (!mounted) return;
      setState(() {
        info = i;
        commands = c;
        error = null;
      });
    } catch (e) {
      if (mounted) setState(() => error = tr('Cannot reach the computer'));
    }
  }

  Future<void> _reloadCommands() async {
    try {
      final c = await widget.api.commands();
      if (mounted) setState(() => commands = c);
    } catch (e) {
      _toast('$e');
    }
  }

  void _toast(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  String _result(Map<String, dynamic> r, String name) {
    final out = '${r['output'] ?? ''}'.trim();
    if (r['ok'] == true) {
      if (out.isEmpty) return '$name: ${tr('Done')}';
      return '$name: ${out.length > 150 ? out.substring(0, 150) : out}';
    }
    final msg = '${r['error'] ?? r['output'] ?? ''}'.trim();
    return '$name: ${msg.isEmpty ? '${tr('Failed')} (${r['code']})' : msg}';
  }

  Future<void> _tap(Map<String, dynamic> c) async {
    final values = <String, String>{};
    final fields = (c['fields'] as List).cast<String>();
    if (c['confirm'] == true) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text('${c['name']}?'),
          content: Text(tr('Are you sure?')),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(tr('Cancel'))),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(tr('Run'))),
          ],
        ),
      );
      if (ok != true) return;
    }
    if (fields.isNotEmpty) {
      final controllers = {for (final f in fields) f: TextEditingController()};
      final labels = (c['labels'] as Map).cast<String, dynamic>();
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text('${c['name']}'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final f in fields)
                TextField(
                  controller: controllers[f],
                  decoration: InputDecoration(labelText: '${labels[f] ?? f}'),
                ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(tr('Cancel'))),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(tr('Run'))),
          ],
        ),
      );
      if (ok != true) return;
      for (final f in fields) {
        values[f] = controllers[f]!.text.trim();
      }
    }
    try {
      final r = await widget.api.run('${c['id']}', values);
      _toast(_result(r, '${c['name']}'));
    } catch (e) {
      _toast('$e');
    }
  }

  Future<void> _edit(Map<String, dynamic>? c) async {
    final changed = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => CommandEditPage(api: widget.api, command: c)),
    );
    if (changed == true) _reloadCommands();
  }

  Future<void> _order() async {
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => _OrderPage(api: widget.api, commands: List<dynamic>.of(commands))),
    );
    _reloadCommands();
  }

  Future<void> _delete(Map<String, dynamic> c) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('${tr('Delete')} ${c['name']}?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(tr('Cancel'))),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(tr('Delete'))),
        ],
      ),
    );
    if (ok != true) return;
    try {
      final list = await widget.api.deleteCommand('${c['id']}');
      if (mounted) setState(() => commands = list);
    } catch (e) {
      _toast('$e');
    }
  }

  Future<void> _reset() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(tr('Restore the default commands?')),
        content: Text(tr('Your own commands will be removed.')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(tr('Cancel'))),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(tr('Restore'))),
        ],
      ),
    );
    if (ok != true) return;
    try {
      final list = await widget.api.resetCommands();
      if (mounted) setState(() => commands = list);
    } catch (e) {
      _toast('$e');
    }
  }

  void _menu(Map<String, dynamic> c) {
    showModalBottomSheet<void>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          ListTile(
            leading: RoundIcon(icon: '${c['icon'] ?? ''}', color: '${c['color'] ?? ''}', size: 40),
            title: Text('${c['name']}'),
            subtitle: Text('${c['cmd'] ?? ''}', maxLines: 2, overflow: TextOverflow.ellipsis),
          ),
          ListTile(
            leading: const Icon(Icons.edit),
            title: Text(tr('Edit')),
            onTap: () {
              Navigator.pop(ctx);
              _edit(c);
            },
          ),
          ListTile(
            leading: const Icon(Icons.delete),
            title: Text(tr('Delete')),
            onTap: () {
              Navigator.pop(ctx);
              _delete(c);
            },
          ),
        ]),
      ),
    );
  }

  Widget _bar(String label, num used, num total) {
    final f = total > 0 ? (used / total).clamp(0.0, 1.0).toDouble() : 0.0;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('$label  ${_size(used)} / ${_size(total)}'),
        const SizedBox(height: 4),
        LinearProgressIndicator(value: f),
      ]),
    );
  }

  Widget _cell(Map<String, dynamic> c) {
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: () => _tap(c),
      onLongPress: () => _menu(c),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          RoundIcon(icon: '${c['icon'] ?? ''}', color: '${c['color'] ?? ''}', size: 54),
          const SizedBox(height: 6),
          Text(
            '${c['name']}',
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 12),
          ),
        ]),
      ),
    );
  }

  Widget _addCell() {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: () => _edit(null),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Container(
            width: 54,
            height: 54,
            decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: scheme.outline, width: 1.5)),
            child: const Icon(Icons.add),
          ),
          const SizedBox(height: 6),
          Text(tr('Add'), style: const TextStyle(fontSize: 12)),
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (info == null) {
      return Center(
        child: error == null
            ? const CircularProgressIndicator()
            : Column(mainAxisSize: MainAxisSize.min, children: [
                Text(error!),
                const SizedBox(height: 8),
                FilledButton(onPressed: _load, child: Text(tr('Retry'))),
              ]),
      );
    }
    final i = info!;
    final bat = i['battery'] as Map<String, dynamic>?;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  const Icon(Icons.laptop, size: 36),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${i['name']}', style: Theme.of(context).textTheme.titleLarge),
                      Text('${i['os']}'),
                    ]),
                  ),
                  if (bat != null) Text('${bat['percent']}%  ${bat['state']}'),
                ]),
                const SizedBox(height: 12),
                Text('${tr('Uptime')}: ${_uptime((i['uptime'] as num).toInt())}'),
                _bar(tr('Memory'), i['mem_used'] as num, i['mem_total'] as num),
                _bar(tr('Storage'), i['disk_used'] as num, i['disk_total'] as num),
              ]),
            ),
          ),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(child: Text(tr('Commands'), style: Theme.of(context).textTheme.titleMedium)),
            IconButton(icon: const Icon(Icons.swap_vert), tooltip: tr('Sort commands'), onPressed: _order),
            IconButton(icon: const Icon(Icons.add), tooltip: tr('Add'), onPressed: () => _edit(null)),
            PopupMenuButton<String>(
              onSelected: (v) {
                if (v == 'reset') _reset();
              },
              itemBuilder: (ctx) => [
                PopupMenuItem<String>(value: 'reset', child: Text(tr('Restore the default commands?'))),
              ],
            ),
          ]),
          Text(tr('Tap to run. Press and hold to edit or delete.'), style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 8),
          GridView.count(
            crossAxisCount: 4,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            mainAxisSpacing: 6,
            crossAxisSpacing: 6,
            childAspectRatio: 0.72,
            children: [
              for (final c in commands.cast<Map<String, dynamic>>()) _cell(c),
              _addCell(),
            ],
          ),
        ],
      ),
    );
  }
}

/// Drag the handle to change the order of the commands. The new order is saved on the computer at once.
class _OrderPage extends StatefulWidget {
  final Api api;
  final List<dynamic> commands;
  const _OrderPage({required this.api, required this.commands});

  @override
  State<_OrderPage> createState() => _OrderPageState();
}

class _OrderPageState extends State<_OrderPage> {
  late List<dynamic> list = widget.commands;

  Future<void> _moved(int oldIndex, int newIndex) async {
    if (newIndex > oldIndex) newIndex -= 1;
    setState(() {
      final item = list.removeAt(oldIndex);
      list.insert(newIndex, item);
    });
    try {
      await widget.api.orderCommands([for (final c in list) '${(c as Map)['id']}']);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(tr('Sort commands'))),
      body: ReorderableListView.builder(
        buildDefaultDragHandles: false,
        itemCount: list.length,
        onReorder: _moved,
        itemBuilder: (ctx, i) {
          final c = list[i] as Map<String, dynamic>;
          return ListTile(
            key: ValueKey('${c['id']}'),
            leading: RoundIcon(icon: '${c['icon'] ?? ''}', color: '${c['color'] ?? ''}', size: 40),
            title: Text('${c['name']}'),
            trailing: ReorderableDragStartListener(index: i, child: const Icon(Icons.drag_handle)),
          );
        },
      ),
    );
  }
}
