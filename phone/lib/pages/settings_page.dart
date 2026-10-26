import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api.dart';
import '../icons.dart';
import '../native.dart';
import '../strings.dart';
import '../style.dart';

class SettingsPage extends StatefulWidget {
  final Config cfg;
  final Api api;
  final VoidCallback onDisconnect;
  const SettingsPage({super.key, required this.cfg, required this.api, required this.onDisconnect});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> with WidgetsBindingObserver {
  bool service = false;
  bool listener = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _status();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _status();
  }

  Future<void> _status() async {
    try {
      final s = await Native.serviceRunning();
      final l = await Native.notificationAccess();
      if (mounted) {
        setState(() {
          service = s;
          listener = l;
        });
      }
    } catch (_) {}
  }

  void _toast(String text) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  final hexCtl = TextEditingController();

  Future<void> _adbResult(Future<dynamic> Function() call) async {
    _toast(tr('Working...'));
    try {
      final r = await call() as Map<String, dynamic>;
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          icon: Icon(r['ok'] == true ? Icons.check_circle_rounded : Icons.error_rounded),
          title: Text(r['ok'] == true ? tr('Done') : tr('Failed')),
          content: SingleChildScrollView(
            child: Text('${r['message'] ?? ''}${'${r['hint'] ?? ''}'.isEmpty ? '' : '\n\n${r['hint']}'}'),
          ),
          actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: Text(tr('OK')))],
        ),
      );
    } catch (e) {
      _toast('$e');
    }
  }

  Future<void> _adbConnect() => _adbResult(() => widget.api.postJson('/adb/connect', {}, null, 40));

  Future<void> _adbPair() async {
    final addr = TextEditingController();
    final code = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(tr('Pair adb with a code')),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(tr('Settings > Developer options > Wireless debugging > Pair device with pairing code. Type the address with its port and the 6 digits.')),
          const SizedBox(height: 8),
          TextField(controller: addr, decoration: const InputDecoration(labelText: '192.168.1.20:37123')),
          TextField(controller: code, keyboardType: TextInputType.number, maxLength: 6,
              decoration: InputDecoration(labelText: tr('Pairing code'))),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: Text(tr('Cancel'))),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: Text(tr('Pair'))),
        ],
      ),
    );
    if (ok != true) return;
    await _adbResult(() => widget.api.postJson('/adb/pair', {'address': addr.text.trim(), 'code': code.text.trim()}, null, 40));
  }

  Future<void> _sendClipboard() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final t = data?.text ?? '';
    if (t.isEmpty) {
      _toast(tr('Clipboard is empty'));
      return;
    }
    try {
      await widget.api.sendClipboard(t);
      _toast(tr('Clipboard sent'));
    } catch (e) {
      _toast('$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final cfg = widget.cfg;
    return ListView(
      children: [
        ListTile(
          leading: const Icon(Icons.laptop),
          title: Text(cfg.name),
          subtitle: Text('${cfg.host}:${cfg.port}'),
        ),
        const Divider(),
        ListTile(
          leading: const Icon(Icons.palette_rounded),
          title: Text(tr('Icon colour')),
          subtitle: Text(tr('One colour for all command icons and the whole app')),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: ListenableBuilder(
            listenable: AppStyle.I,
            builder: (context, _) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final c in commandColors)
                  GestureDetector(
                    onTap: () => AppStyle.I.setAccent(c),
                    child: Container(
                      width: 38,
                      height: 38,
                      decoration: BoxDecoration(
                        color: colorFromHex(c, Colors.blue),
                        shape: BoxShape.circle,
                        border: Border.all(
                            color: AppStyle.I.accent == c.toUpperCase() ? Theme.of(context).colorScheme.onSurface : Colors.transparent,
                            width: 3),
                      ),
                      child: AppStyle.I.accent == c.toUpperCase() ? const Icon(Icons.check_rounded, color: Colors.white) : null,
                    ),
                  ),
              ]),
              const SizedBox(height: 8),
              Row(children: [
                Expanded(
                  child: TextField(
                    controller: hexCtl,
                    maxLength: 7,
                    decoration: InputDecoration(labelText: tr('Other colour, for example #FF8800'), counterText: ''),
                    onSubmitted: (v) => AppStyle.I.setAccent(v.trim()),
                  ),
                ),
                IconButton(icon: const Icon(Icons.check_rounded), onPressed: () => AppStyle.I.setAccent(hexCtl.text.trim())),
              ]),
            ]),
          ),
        ),
        const Divider(),
        ListTile(
          leading: const Icon(Icons.usb_rounded),
          title: Text(tr('Let the computer connect to this phone with adb')),
          subtitle: Text(tr('The computer runs "adb connect" for this phone. Network mode must be on.')),
          onTap: _adbConnect,
        ),
        ListTile(
          leading: const Icon(Icons.password_rounded),
          title: Text(tr('Pair adb with a code')),
          subtitle: Text(tr('Android 11+ Wireless debugging, no cable')),
          onTap: _adbPair,
        ),
        const Divider(),
        SwitchListTile(
          title: Text(tr('Share the clipboard')),
          value: cfg.syncClipboard,
          onChanged: (v) async {
            setState(() => cfg.syncClipboard = v);
            await cfg.save();
          },
        ),
        SwitchListTile(
          title: Text(tr('Share notifications')),
          value: cfg.syncNotifications,
          onChanged: (v) async {
            setState(() => cfg.syncNotifications = v);
            await cfg.save();
          },
        ),
        const Divider(),
        ListTile(
          leading: Icon(service ? Icons.sync : Icons.sync_disabled),
          title: Text(tr('Background link')),
          subtitle: Text(service ? tr('Running') : tr('Stopped')),
          trailing: FilledButton(
            onPressed: () async {
              if (service) {
                await Native.stopService();
              } else {
                await Native.requestNotifications();
                await Native.startService();
              }
              await Future.delayed(const Duration(milliseconds: 500));
              _status();
            },
            child: Text(service ? tr('Stop') : tr('Start')),
          ),
        ),
        ListTile(
          leading: Icon(listener ? Icons.check_circle : Icons.notifications_active),
          title: Text(tr('Allow reading phone notifications')),
          onTap: Native.openNotificationAccess,
        ),
        ListTile(
          leading: const Icon(Icons.notifications),
          title: Text(tr('Allow notifications')),
          onTap: Native.requestNotifications,
        ),
        ListTile(
          leading: const Icon(Icons.battery_saver),
          title: Text(tr('Do not restrict battery')),
          onTap: Native.ignoreBattery,
        ),
        ListTile(
          leading: const Icon(Icons.content_paste_go),
          title: Text(tr('Send phone clipboard to computer now')),
          onTap: _sendClipboard,
        ),
        Padding(
          padding: const EdgeInsets.all(16),
          child: Text(
            tr('Android only lets an app read the clipboard while it is open. Use the quick-settings tile "Send clipboard to PC" '
                'or the button in the notification for copies you make in other apps. Copies made on the computer arrive by themselves.'),
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
        const Divider(),
        ListTile(
          leading: Icon(Icons.link_off, color: Theme.of(context).colorScheme.error),
          title: Text(tr('Disconnect')),
          onTap: () async {
            await Native.stopService();
            widget.onDisconnect();
          },
        ),
      ],
    );
  }
}
