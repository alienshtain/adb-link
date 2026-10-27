import 'package:flutter/material.dart';

import '../api.dart';
import '../icons.dart';
import '../strings.dart';

final RegExp _fieldPattern = RegExp(r'(?<!\$)\{([A-Za-z_][A-Za-z0-9_]*)\}');

List<String> _fieldsOf(String cmd) {
  final clean = cmd.replaceAll('{{', '').replaceAll('}}', '');
  final out = <String>[];
  for (final m in _fieldPattern.allMatches(clean)) {
    final name = m.group(1)!;
    if (!out.contains(name)) out.add(name);
  }
  return out;
}

/// Add a new command or edit an existing one: name, what to run, round icon, colour.
class CommandEditPage extends StatefulWidget {
  final Api api;
  final Map<String, dynamic>? command;
  final String? presetCmd;
  const CommandEditPage({super.key, required this.api, this.command, this.presetCmd});

  @override
  State<CommandEditPage> createState() => _CommandEditPageState();
}

class _CommandEditPageState extends State<CommandEditPage> {
  final nameCtl = TextEditingController();
  final cmdCtl = TextEditingController();
  final emojiCtl = TextEditingController();
  String icon = 'bolt';
  String color = commandColors.first;
  bool confirm = false;
  bool busy = false;
  String? error;

  @override
  void initState() {
    super.initState();
    final c = widget.command;
    if (c != null) {
      nameCtl.text = '${c['name'] ?? ''}';
      cmdCtl.text = '${c['cmd'] ?? ''}';
      icon = '${c['icon'] ?? ''}'.isEmpty ? 'bolt' : '${c['icon']}';
      final col = '${c['color'] ?? ''}';
      if (col.isNotEmpty) color = col;
      confirm = c['confirm'] == true;
      if (!commandIcons.containsKey(icon)) emojiCtl.text = icon;
    } else if (widget.presetCmd != null) {
      cmdCtl.text = widget.presetCmd!;
    }
    cmdCtl.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    nameCtl.dispose();
    cmdCtl.dispose();
    emojiCtl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final n = nameCtl.text.trim();
    final c = cmdCtl.text.trim();
    if (n.isEmpty || c.isEmpty) {
      setState(() => error = tr('Name and command are required'));
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final body = <String, dynamic>{'name': n, 'cmd': c, 'icon': icon, 'color': color, 'confirm': confirm};
      final id = widget.command?['id'];
      if (id != null) body['id'] = id;
      final labels = widget.command?['labels'];
      if (labels is Map) body['labels'] = labels;
      await widget.api.saveCommand(body);
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) {
        setState(() {
          busy = false;
          error = '$e';
        });
      }
    }
  }

  Future<void> _delete() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('${tr('Delete')} ${nameCtl.text}?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(tr('Cancel'))),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(tr('Delete'))),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await widget.api.deleteCommand('${widget.command!['id']}');
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    }
  }

  Widget _choice({required bool selected, required Widget child, required VoidCallback onTap}) {
    final scheme = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(3),
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: selected ? scheme.primary : Colors.transparent, width: 2.5),
        ),
        child: child,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final fields = _fieldsOf(cmdCtl.text);
    final existing = widget.command != null;
    return Scaffold(
      appBar: AppBar(
        title: Text(existing ? tr('Edit command') : tr('New command')),
        actions: [if (existing) IconButton(icon: const Icon(Icons.delete), onPressed: _delete)],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Center(child: RoundIcon(icon: icon, size: 76)),
          const SizedBox(height: 16),
          TextField(
            controller: nameCtl,
            decoration: InputDecoration(labelText: tr('Name'), border: const OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: cmdCtl,
            minLines: 2,
            maxLines: 6,
            autocorrect: false,
            enableSuggestions: false,
            style: const TextStyle(fontFamily: 'monospace'),
            decoration: InputDecoration(
              labelText: tr('Command to run on the computer'),
              hintText: 'xdg-open {url}',
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            tr('Write {name} where the app should ask you for a value before running.'),
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (fields.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Wrap(spacing: 6, children: [
                Text('${tr('It will ask for')}:'),
                for (final f in fields) Chip(label: Text(f), visualDensity: VisualDensity.compact),
              ]),
            ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(tr('Ask "Are you sure?" before running')),
            value: confirm,
            onChanged: (v) => setState(() => confirm = v),
          ),
          const SizedBox(height: 8),
          Text(tr('Icon'), style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Wrap(spacing: 4, runSpacing: 4, children: [
            for (final e in commandIcons.entries)
              _choice(
                selected: icon == e.key,
                onTap: () => setState(() {
                  icon = e.key;
                  emojiCtl.clear();
                }),
                child: RoundIcon(icon: e.key, size: 42),
              ),
          ]),
          const SizedBox(height: 8),
          TextField(
            controller: emojiCtl,
            maxLength: 8,
            decoration: InputDecoration(labelText: tr('Or type an emoji'), border: const OutlineInputBorder()),
            onChanged: (v) {
              final t = v.trim();
              if (t.isNotEmpty) setState(() => icon = t);
            },
          ),
          const SizedBox(height: 8),
          Text(tr('All icons use one colour. Change it in Settings > Icon colour.'),
              style: Theme.of(context).textTheme.bodySmall),
          if (error != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: busy ? null : _save,
            child: busy
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : Text(tr('Save')),
          ),
        ],
      ),
    );
  }
}
