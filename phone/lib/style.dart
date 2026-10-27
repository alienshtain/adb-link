import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// One accent colour for the whole app: command icons, buttons, highlights. Change it in Settings.
class AppStyle extends ChangeNotifier {
  AppStyle._();
  static final AppStyle I = AppStyle._();

  static const String defaultAccent = '#3584E4';
  String accent = defaultAccent;

  /// Where files from the computer are saved on this phone (inside Documents or Download).
  static const String defaultSavePath = 'Documents/ADB Link';
  String savePath = defaultSavePath;

  /// Folder on the computer for files sent from this phone. Empty = the computer's own setting
  /// (Documents/ADB Link by default).
  String uploadDir = '';

  /// 'auto' (follow the phone), 'en' or 'ar'.
  String language = 'auto';

  Color get color {
    final m = RegExp(r'^#([0-9a-fA-F]{6})$').firstMatch(accent);
    return m == null ? const Color(0xFF3584E4) : Color(int.parse('FF${m.group(1)}', radix: 16));
  }

  static Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      I.accent = prefs.getString('accent') ?? defaultAccent;
      I.savePath = prefs.getString('savePath') ?? defaultSavePath;
      I.uploadDir = prefs.getString('uploadDir') ?? '';
      I.language = prefs.getString('language') ?? 'auto';
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

  Future<void> _save(String key, String value) async {
    notifyListeners();
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(key, value);
    } catch (_) {}
  }

  /// Only Documents/... or Download/... are allowed by Android for ordinary files.
  static String cleanSavePath(String raw) {
    final parts = raw.split('/').map((e) => e.trim()).where((e) => e.isNotEmpty && e != '.' && e != '..').toList();
    if (parts.isEmpty) return defaultSavePath;
    if (parts.first != 'Documents' && parts.first != 'Download') parts.insert(0, 'Documents');
    return parts.join('/');
  }

  Future<void> setSavePath(String value) async {
    savePath = cleanSavePath(value);
    await _save('savePath', savePath);
  }

  Future<void> setUploadDir(String value) async {
    uploadDir = value.trim();
    await _save('uploadDir', uploadDir);
  }

  Future<void> setLanguage(String value) async {
    language = const ['auto', 'en', 'ar'].contains(value) ? value : 'auto';
    await _save('language', language);
  }
}
