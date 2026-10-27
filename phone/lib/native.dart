import 'package:flutter/services.dart';

import 'style.dart';

/// Things only Android code can do (background service, notification access, saving to Downloads,
/// picking and uploading phone files and folders).
class Native {
  static const _ch = MethodChannel('adblink/native');

  /// Called while an upload runs: files, doneFiles, bytes, doneBytes, name.
  static void Function(Map<String, dynamic>)? onUploadProgress;
  static bool _handlerSet = false;

  static void _ensureHandler() {
    if (_handlerSet) return;
    _handlerSet = true;
    _ch.setMethodCallHandler((call) async {
      if (call.method == 'uploadProgress') {
        final a = call.arguments;
        if (a is Map) onUploadProgress?.call(Map<String, dynamic>.from(a));
      }
      return null;
    });
  }

  static Future<bool> serviceRunning() async => (await _ch.invokeMethod<bool>('serviceRunning')) ?? false;
  static Future<void> startService() => _ch.invokeMethod('startService');
  static Future<void> stopService() => _ch.invokeMethod('stopService');
  static Future<bool> notificationAccess() async =>
      (await _ch.invokeMethod<bool>('notificationAccess')) ?? false;
  static Future<void> openNotificationAccess() => _ch.invokeMethod('openNotificationAccess');
  static Future<void> requestNotifications() => _ch.invokeMethod('requestNotifications');
  static Future<void> ignoreBattery() => _ch.invokeMethod('ignoreBattery');

  /// Saves [path] in the folder chosen in Settings (Documents/ADB Link by default), inside [sub] when
  /// given, for example "MyFolder/images".
  static Future<bool> saveToDownloads(String path, String name, {String sub = ''}) async =>
      (await _ch.invokeMethod<bool>('saveToDownloads',
          {'path': path, 'name': name, 'sub': sub, 'root': AppStyle.I.savePath})) ?? false;

  /// Opens Android's file picker (several files). Returns content:// addresses, empty when cancelled.
  static Future<List<String>> pickFiles() async {
    _ensureHandler();
    final r = await _ch.invokeMethod<List<dynamic>>('pickFiles');
    return (r ?? <dynamic>[]).cast<String>();
  }

  /// Opens Android's folder picker. Returns a content:// address, null when cancelled.
  static Future<String?> pickFolder() async {
    _ensureHandler();
    return _ch.invokeMethod<String>('pickFolder');
  }

  /// Sends the picked files to the computer. [to] is a folder on the computer (null: the folder chosen in Settings, or Documents/ADB Link).
  /// Returns {ok, failed, errors}.
  static Future<Map<String, dynamic>> uploadUris(List<String> uris, {String? to}) async {
    _ensureHandler();
    final r = await _ch.invokeMethod<Map<dynamic, dynamic>>('uploadUris', {'uris': uris, 'to': to ?? (AppStyle.I.uploadDir.isEmpty ? null : AppStyle.I.uploadDir)});
    return Map<String, dynamic>.from(r ?? <dynamic, dynamic>{});
  }

  /// Sends a picked folder (with everything inside it) to the computer.
  static Future<Map<String, dynamic>> uploadTree(String uri, {String? to}) async {
    _ensureHandler();
    final r = await _ch.invokeMethod<Map<dynamic, dynamic>>('uploadTree', {'uri': uri, 'to': to ?? (AppStyle.I.uploadDir.isEmpty ? null : AppStyle.I.uploadDir)});
    return Map<String, dynamic>.from(r ?? <dynamic, dynamic>{});
  }
}
