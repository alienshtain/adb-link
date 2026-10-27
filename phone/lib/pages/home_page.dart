import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api.dart';
import '../strings.dart';
import 'computer_page.dart';
import 'files_page.dart';
import 'remote_page.dart';
import 'settings_page.dart';
import 'terminal_page.dart';

class HomePage extends StatefulWidget {
  final Config cfg;
  final VoidCallback onDisconnect;
  const HomePage({super.key, required this.cfg, required this.onDisconnect});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> with WidgetsBindingObserver {
  int tab = 0;
  late final Api api = Api(widget.cfg);
  String? lastSentClipboard;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  /// Android lets the app read the clipboard only while it is in front: send it when the app opens.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) async {
    if (state != AppLifecycleState.resumed || !widget.cfg.syncClipboard) return;
    await Future.delayed(const Duration(milliseconds: 400));
    try {
      final data = await Clipboard.getData(Clipboard.kTextPlain);
      final text = data?.text;
      if (text != null && text.isNotEmpty && text != lastSentClipboard) {
        lastSentClipboard = text;
        await api.sendClipboard(text);
      }
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final pages = <Widget>[
      ComputerPage(api: api),
      FilesPage(api: api),
      RemotePage(api: api, active: tab == 2),
      TerminalPage(api: api),
      SettingsPage(cfg: widget.cfg, api: api, onDisconnect: widget.onDisconnect),
    ];
    return Scaffold(
      body: SafeArea(child: IndexedStack(index: tab, children: pages)),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: [
          NavigationDestination(icon: const Icon(Icons.computer_rounded), label: tr('Computer')),
          NavigationDestination(icon: const Icon(Icons.folder_rounded), label: tr('Files')),
          NavigationDestination(icon: const Icon(Icons.mouse_rounded), label: tr('Remote')),
          NavigationDestination(icon: const Icon(Icons.terminal_rounded), label: tr('Terminal')),
          NavigationDestination(icon: const Icon(Icons.settings_rounded), label: tr('Settings')),
        ],
      ),
    );
  }
}
