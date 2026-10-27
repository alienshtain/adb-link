import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../strings.dart';

/// Touchpad, keyboard, shortcuts and media keys for the computer.
class RemotePage extends StatefulWidget {
  final Api api;
  final bool active;
  const RemotePage({super.key, required this.api, required this.active});

  @override
  State<RemotePage> createState() => _RemotePageState();
}

class _RemotePageState extends State<RemotePage> {
  /// What is wrong with remote input, shown in red until it works (never hidden).
  String? inputProblem;
  double pendingX = 0, pendingY = 0, pendingScroll = 0;
  double speed = 2.2;
  bool dragging = false;
  final Set<String> mods = {};
  Timer? sender;
  final text = TextEditingController();

  static const List<String> keys = [
    'esc', 'tab', 'backspace', 'enter', 'space', 'up', 'down', 'left', 'right',
    'home', 'end', 'pageup', 'pagedown', 'delete', 'insert', 'f5', 'f11',
  ];

  // label -> key combination understood by the computer
  static const List<List<String>> shortcuts = [
    ['Copy', 'ctrl+c'], ['Paste', 'ctrl+v'], ['Cut', 'ctrl+x'], ['Undo', 'ctrl+z'],
    ['Select all', 'ctrl+a'], ['Save', 'ctrl+s'], ['Find', 'ctrl+f'], ['New tab', 'ctrl+t'],
    ['Close tab', 'ctrl+w'], ['Switch app', 'alt+tab'], ['Desktop', 'super'], ['Lock', 'super+l'],
    ['Close window', 'alt+f4'], ['Screenshot', 'print'],
  ];

  static const List<List<String>> media = [
    ['Play / pause', 'playpause'], ['Previous', 'prev'], ['Next', 'next'],
    ['Volume +', 'volumeup'], ['Volume -', 'volumedown'], ['Mute', 'mute'],
  ];

  @override
  void initState() {
    super.initState();
    sender = Timer.periodic(const Duration(milliseconds: 40), (_) => _flush());
    _checkCaps();
  }

  Future<void> _checkCaps() async {
    try {
      final info = await widget.api.info();
      final caps = info['capabilities'] as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        if (caps['input'] == null) {
          final hint = '${caps['inputHint'] ?? ''}';
          inputProblem = hint.isNotEmpty
              ? hint
              : tr('Remote input needs ydotool (Wayland) or xdotool (X11) on the computer.');
        } else {
          inputProblem = null;
        }
      });
    } catch (_) {}
  }

  @override
  void didUpdateWidget(RemotePage old) {
    super.didUpdateWidget(old);
    if (widget.active && !old.active) _checkCaps();
  }

  @override
  void dispose() {
    sender?.cancel();
    if (dragging) widget.api.input({'kind': 'up', 'button': 'left'}).catchError((_) {});
    text.dispose();
    super.dispose();
  }

  void _fail(Object e) {
    final msg = e is ApiError ? e.message : tr('Cannot reach the computer');
    if (mounted && msg != inputProblem) setState(() => inputProblem = msg);
  }

  Future<void> _send(Map<String, dynamic> body) async {
    try {
      await widget.api.input(body);
      if (inputProblem != null && mounted) setState(() => inputProblem = null);
    } catch (e) {
      _fail(e);
    }
  }

  void _flush() {
    if (pendingX.abs() >= 1 || pendingY.abs() >= 1) {
      final dx = pendingX.round(), dy = pendingY.round();
      pendingX = 0;
      pendingY = 0;
      _send({'kind': 'move', 'dx': dx, 'dy': dy});
    }
    if (pendingScroll.abs() >= 8) {
      final dy = (pendingScroll / 8).round().clamp(-5, 5);
      pendingScroll = 0;
      _send({'kind': 'scroll', 'dy': dy});
    }
  }

  void _click(String button, [int count = 1]) => _send({'kind': 'click', 'button': button, 'count': count});

  String _combo(String key) => [...mods.where((m) => m != 'super'), if (mods.contains('super')) 'super', key].join('+');

  void _key(String key) {
    _send({'kind': 'key', 'key': _combo(key)});
    if (mods.isNotEmpty) setState(mods.clear); // modifiers apply to one key, like a phone keyboard
  }

  void _shortcut(String combo) => _send({'kind': 'key', 'key': combo});

  Future<void> _sendText() async {
    final t = text.text;
    if (t.isEmpty) return;
    text.clear();
    await _send({'kind': 'text', 'text': t});
  }

  void _toggleDrag() {
    setState(() => dragging = !dragging);
    _send({'kind': dragging ? 'down' : 'up', 'button': 'left'});
  }

  Widget _problem(ColorScheme scheme) {
    final msg = inputProblem!;
    final needsSetup = msg.contains('setup-input');
    return Card(
      color: scheme.errorContainer,
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(Icons.error_rounded, color: scheme.onErrorContainer),
            const SizedBox(width: 8),
            Expanded(child: Text(tr('Mouse and keyboard are not working yet'),
                style: TextStyle(fontWeight: FontWeight.bold, color: scheme.onErrorContainer))),
          ]),
          const SizedBox(height: 6),
          SelectableText(msg, style: TextStyle(color: scheme.onErrorContainer)),
          if (needsSetup)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                tr('On the computer: open ADB Link > Phone app > "Allow" next to mouse and keyboard, or run "adblink setup-input" once.'),
                style: TextStyle(color: scheme.onErrorContainer),
              ),
            ),
          Align(
            alignment: AlignmentDirectional.centerEnd,
            child: TextButton(onPressed: _checkCaps, child: Text(tr('Retry'))),
          ),
        ]),
      ),
    );
  }

  Widget _chipRow(String title, List<List<String>> items, void Function(String) onTap) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(padding: const EdgeInsets.only(top: 12, bottom: 6), child: Text(tr(title), style: Theme.of(context).textTheme.titleSmall)),
      Wrap(spacing: 6, runSpacing: 6, children: [
        for (final s in items) ActionChip(label: Text(tr(s[0])), onPressed: () => onTap(s[1])),
      ]),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        if (inputProblem != null) _problem(scheme),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(child: Text(tr('Touchpad'), style: Theme.of(context).textTheme.titleMedium)),
          FilterChip(
            label: Text(tr('Drag')),
            avatar: const Icon(Icons.pan_tool_alt_rounded, size: 18),
            selected: dragging,
            onSelected: (_) => _toggleDrag(),
          ),
        ]),
        const SizedBox(height: 6),
        Row(children: [
          Expanded(
            child: GestureDetector(
              onPanUpdate: (d) {
                pendingX += d.delta.dx * speed;
                pendingY += d.delta.dy * speed;
              },
              onTap: () => _click('left'),
              onDoubleTap: () => _click('left', 2),
              onLongPress: () => _click('right'),
              child: Container(
                height: 220,
                decoration: BoxDecoration(
                  color: dragging ? scheme.primaryContainer : scheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(24),
                ),
                child: Center(
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Icon(Icons.touch_app_rounded, size: 44, color: scheme.onSurfaceVariant),
                    const SizedBox(height: 6),
                    Text(tr('Tap = click, double tap = double click, hold = right click'),
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant)),
                  ]),
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onVerticalDragUpdate: (d) => pendingScroll += d.delta.dy,
            child: Container(
              width: 52,
              height: 220,
              decoration: BoxDecoration(color: scheme.secondaryContainer, borderRadius: BorderRadius.circular(24)),
              child: const Icon(Icons.unfold_more_rounded),
            ),
          ),
        ]),
        Row(children: [
          Text(tr('Speed')),
          Expanded(child: Slider(value: speed, min: 1, max: 5, onChanged: (v) => setState(() => speed = v))),
        ]),
        Row(children: [
          Expanded(child: OutlinedButton(onPressed: () => _click('left'), child: Text(tr('Left click')))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton(onPressed: () => _click('middle'), child: Text(tr('Middle')))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton(onPressed: () => _click('right'), child: Text(tr('Right click')))),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: TextField(
              controller: text,
              decoration: InputDecoration(hintText: tr('Type here and press send'), border: const OutlineInputBorder()),
              onSubmitted: (_) => _sendText(),
            ),
          ),
          const SizedBox(width: 8),
          FilledButton(onPressed: _sendText, child: Text(tr('Send'))),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 6, children: [
          for (final m in const ['ctrl', 'alt', 'shift', 'super'])
            FilterChip(
              label: Text(m),
              selected: mods.contains(m),
              onSelected: (on) => setState(() => on ? mods.add(m) : mods.remove(m)),
            ),
        ]),
        const SizedBox(height: 6),
        Wrap(spacing: 6, runSpacing: 6, children: [
          for (final k in keys) ActionChip(label: Text(k), onPressed: () => _key(k)),
        ]),
        _chipRow('Shortcuts', shortcuts, _shortcut),
        _chipRow('Media', media, _shortcut),
      ],
    );
  }
}
