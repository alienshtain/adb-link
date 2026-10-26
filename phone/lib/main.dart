import 'package:flutter/material.dart';

import 'api.dart';
import 'pages/home_page.dart';
import 'pages/pair_page.dart';
import 'strings.dart';
import 'style.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppStyle.load();
  final cfg = await Config.load();
  runApp(LinkApp(initial: cfg));
}

class LinkApp extends StatefulWidget {
  final Config? initial;
  const LinkApp({super.key, this.initial});

  @override
  State<LinkApp> createState() => _LinkAppState();
}

class _LinkAppState extends State<LinkApp> {
  Config? cfg;
  final navKey = GlobalKey<NavigatorState>();

  @override
  void initState() {
    super.initState();
    cfg = widget.initial;
  }

  void _paired(Config c) => setState(() => cfg = c);

  void _lost() async {
    await Config.clear();
    setState(() => cfg = null);
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: AppStyle.I,
      builder: (context, _) {
        final seed = AppStyle.I.color;
        return MaterialApp(
          title: 'ADB Link',
          debugShowCheckedModeBanner: false,
          theme: ThemeData(colorSchemeSeed: seed, useMaterial3: true),
          darkTheme: ThemeData(colorSchemeSeed: seed, useMaterial3: true, brightness: Brightness.dark),
          builder: (context, child) => Directionality(
            textDirection: isArabic ? TextDirection.rtl : TextDirection.ltr,
            child: child ?? const SizedBox.shrink(),
          ),
          home: cfg == null
              ? PairPage(onPaired: _paired)
              : HomePage(cfg: cfg!, onDisconnect: _lost),
        );
      },
    );
  }
}
