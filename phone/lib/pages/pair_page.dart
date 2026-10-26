import 'dart:io';

import 'package:flutter/material.dart';

import '../api.dart';
import '../discovery.dart';
import '../strings.dart';

class PairPage extends StatefulWidget {
  final void Function(Config) onPaired;
  const PairPage({super.key, required this.onPaired});

  @override
  State<PairPage> createState() => _PairPageState();
}

class _PairPageState extends State<PairPage> {
  final host = TextEditingController();
  final port = TextEditingController(text: '8765');
  final code = TextEditingController();
  bool busy = false;
  bool searching = false;
  List<FoundComputer> found = [];
  bool searched = false;
  String? error;

  Future<void> _search() async {
    setState(() {
      searching = true;
      searched = false;
      found = [];
      error = null;
    });
    final res = await findComputers();
    if (!mounted) return;
    setState(() {
      found = res;
      searching = false;
      searched = true;
      if (res.length == 1) _use(res.first);
    });
  }

  void _use(FoundComputer c) {
    host.text = c.host;
    port.text = '${c.port}';
  }

  @override
  void initState() {
    super.initState();
    _search();
  }

  Future<void> _pair() async {
    final h = host.text.trim();
    final p = int.tryParse(port.text.trim()) ?? 8765;
    if (h.isEmpty || code.text.trim().length != 6) {
      setState(() => error = tr('Wrong code or the computer is not reachable'));
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final phone = Platform.localHostname.isEmpty ? 'Phone' : Platform.localHostname;
      final cfg = await Api.pair(h, p, code.text.trim(), phone);
      await cfg.save();
      if (mounted) widget.onPaired(cfg);
    } on ApiError catch (e) {
      setState(() => error = e.status == 429
          ? tr('Too many wrong codes, wait a minute')
          : tr('Wrong code or the computer is not reachable'));
    } catch (_) {
      setState(() => error = tr('Cannot reach the computer'));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(tr('Connect to your computer'))),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(tr(
              'On the computer open ADB Link, go to the "Phone app" page and read the pairing code. The computer and this phone must be on the same Wi-Fi (or both on Tailscale).')),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  const Icon(Icons.radar_rounded),
                  const SizedBox(width: 8),
                  Expanded(child: Text(tr('Find my computer'), style: Theme.of(context).textTheme.titleMedium)),
                  if (searching)
                    const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  else
                    IconButton(icon: const Icon(Icons.refresh_rounded), onPressed: _search),
                ]),
                if (searching) Text(tr('Looking on the network...')),
                if (searched && found.isEmpty)
                  Text(tr('No computer found. Is ADB Link open on it, and are both on the same network? You can type the address below.')),
                for (final c in found)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.laptop_rounded),
                    title: Text(c.name),
                    subtitle: Text('${c.host}:${c.port}${c.os.isEmpty ? '' : '  ·  ${c.os}'}'),
                    trailing: host.text == c.host ? const Icon(Icons.check_circle_rounded) : null,
                    onTap: () => setState(() => _use(c)),
                  ),
              ]),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: host,
            keyboardType: TextInputType.url,
            decoration: InputDecoration(
                labelText: tr('Computer address (IP)'), hintText: '100.x.x.x', border: const OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: port,
            keyboardType: TextInputType.number,
            decoration: InputDecoration(labelText: tr('Port'), border: const OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: code,
            keyboardType: TextInputType.number,
            maxLength: 6,
            decoration: InputDecoration(labelText: tr('Pairing code'), border: const OutlineInputBorder()),
          ),
          if (error != null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: busy ? null : _pair,
            child: busy
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : Text(tr('Pair')),
          ),
        ],
      ),
    );
  }
}
