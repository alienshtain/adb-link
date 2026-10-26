import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// One accent colour for the whole app: command icons, buttons, highlights. Change it in Settings.
class AppStyle extends ChangeNotifier {
  AppStyle._();
  static final AppStyle I = AppStyle._();

  static const String defaultAccent = '#3584E4';
  String accent = defaultAccent;

  Color get color {
    final m = RegExp(r'^#([0-9a-fA-F]{6})$').firstMatch(accent);
    return m == null ? const Color(0xFF3584E4) : Color(int.parse('FF${m.group(1)}', radix: 16));
  }

  static Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      I.accent = prefs.getString('accent') ?? defaultAccent;
    } catch (_) {}
  }

  Future<void> setAccent(String hex) async {
    if (!RegExp(r'^#[0-9a-fA-F]{6}$').hasMatch(hex)) return;
    accent = hex.toUpperCase();
    notifyListeners();
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('accent', accent);
    } catch (_) {}
  }
}
