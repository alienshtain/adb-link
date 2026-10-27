import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Saved connection. The same JSON is read by the Android background service (key "flutter.link").
class Config {
  String host;
  int port;
  String token;
  String name;
  bool syncClipboard;
  bool syncNotifications;

  Config({
    required this.host,
    required this.port,
    required this.token,
    this.name = 'Computer',
    this.syncClipboard = true,
    this.syncNotifications = true,
  });

  Map<String, dynamic> toJson() => {
        'host': host,
        'port': port,
        'token': token,
        'name': name,
        'syncClipboard': syncClipboard,
        'syncNotifications': syncNotifications,
      };

  factory Config.fromJson(Map<String, dynamic> j) => Config(
        host: j['host'] as String,
        port: (j['port'] as num).toInt(),
        token: j['token'] as String,
        name: (j['name'] as String?) ?? 'Computer',
        syncClipboard: (j['syncClipboard'] as bool?) ?? true,
        syncNotifications: (j['syncNotifications'] as bool?) ?? true,
      );

  static Future<Config?> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString('link');
    if (raw == null) return null;
    try {
      return Config.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  Future<void> save() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('link', jsonEncode(toJson()));
  }

  static Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('link');
  }
}

class ApiError implements Exception {
  final String message;
  final int? status;
  ApiError(this.message, [this.status]);
  @override
  String toString() => message;
}

class Api {
  final Config cfg;
  Api(this.cfg);

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri(scheme: 'http', host: cfg.host, port: cfg.port, path: path, queryParameters: query);

  Map<String, String> get _auth => {'Authorization': 'Bearer ${cfg.token}'};

  static Future<Config> pair(String host, int port, String code, String phoneName) async {
    final uri = Uri(scheme: 'http', host: host, port: port, path: '/pair');
    final res = await http
        .post(uri, body: jsonEncode({'code': code, 'name': phoneName}))
        .timeout(const Duration(seconds: 10));
    if (res.statusCode != 200) throw ApiError('pair', res.statusCode);
    final j = jsonDecode(res.body) as Map<String, dynamic>;
    return Config(host: host, port: port, token: j['token'] as String, name: (j['name'] as String?) ?? host);
  }

  dynamic _decode(http.Response res) {
    if (res.statusCode == 401) throw ApiError('not paired', 401);
    final body = res.body.isEmpty ? null : jsonDecode(utf8.decode(res.bodyBytes));
    if (res.statusCode >= 400) {
      final msg = body is Map && body['error'] != null ? '${body['error']}' : 'HTTP ${res.statusCode}';
      throw ApiError(msg, res.statusCode);
    }
    return body;
  }

  Future<dynamic> getJson(String path, [Map<String, String>? query, int timeout = 15]) async {
    final res = await http.get(_uri(path, query), headers: _auth).timeout(Duration(seconds: timeout));
    return _decode(res);
  }

  Future<dynamic> postJson(String path, Map<String, dynamic> body,
      [Map<String, String>? query, int timeout = 40]) async {
    final res = await http
        .post(_uri(path, query), headers: _auth, body: jsonEncode(body))
        .timeout(Duration(seconds: timeout));
    return _decode(res);
  }

  /// For widgets that show pictures straight from the computer (Image.network).
  Map<String, String> get authHeaders => _auth;

  Uri fileUri(String op, String path, [Map<String, String>? extra]) =>
      _uri('/files', {'op': op, 'path': path, ...?extra});

  Future<Map<String, dynamic>> info() async => (await getJson('/info')) as Map<String, dynamic>;

  Future<List<dynamic>> commands() async => (await getJson('/commands')) as List<dynamic>;

  Future<Map<String, dynamic>> run(String id, Map<String, String> values) async =>
      (await postJson('/run', {'id': id, 'values': values})) as Map<String, dynamic>;

  // ---- commands you can add, edit, delete and sort from the phone
  Future<List<dynamic>> saveCommand(Map<String, dynamic> command) async =>
      (await postJson('/commands', {'op': 'save', 'command': command})) as List<dynamic>;

  Future<List<dynamic>> deleteCommand(String id) async =>
      (await postJson('/commands', {'op': 'delete', 'id': id})) as List<dynamic>;

  Future<List<dynamic>> orderCommands(List<String> ids) async =>
      (await postJson('/commands', {'op': 'order', 'ids': ids})) as List<dynamic>;

  Future<List<dynamic>> resetCommands() async =>
      (await postJson('/commands', {'op': 'reset'})) as List<dynamic>;

  /// Runs any command on the computer (the Terminal page). Returns output, code and the new folder.
  Future<Map<String, dynamic>> shell(String cmd, String cwd, {int timeout = 60}) async =>
      (await postJson('/shell', {'cmd': cmd, 'cwd': cwd, 'timeout': timeout}, null, timeout + 15))
          as Map<String, dynamic>;

  // ---- files
  Future<Map<String, dynamic>> list(String path, {bool hidden = false}) async =>
      (await getJson('/files', {'op': 'list', 'path': path, if (hidden) 'hidden': '1'}))
          as Map<String, dynamic>;

  /// Size, item count and date of a file or folder.
  Future<Map<String, dynamic>> fileInfo(String path) async =>
      (await getJson('/files', {'op': 'info', 'path': path}, 30)) as Map<String, dynamic>;

  /// Every file inside a folder (for downloading the whole folder).
  Future<Map<String, dynamic>> tree(String path) async =>
      (await getJson('/files', {'op': 'tree', 'path': path}, 60)) as Map<String, dynamic>;

  /// The first part of a text file.
  Future<Map<String, dynamic>> text(String path) async =>
      (await getJson('/files', {'op': 'text', 'path': path, 'max': '200000'}, 30))
          as Map<String, dynamic>;

  Future<void> sendClipboard(String text) => postJson('/clipboard', {'text': text});

  Future<void> input(Map<String, dynamic> body) => postJson('/input', body);

  Future<void> download(String remotePath, File dest, void Function(double) progress) async {
    final client = http.Client();
    try {
      final req = http.Request('GET', _uri('/files', {'op': 'get', 'path': remotePath}));
      req.headers.addAll(_auth);
      final res = await client.send(req);
      if (res.statusCode != 200) throw ApiError('HTTP ${res.statusCode}', res.statusCode);
      final total = res.contentLength ?? 0;
      var got = 0;
      final sink = dest.openWrite();
      await for (final chunk in res.stream) {
        sink.add(chunk);
        got += chunk.length;
        if (total > 0) progress(got / total);
      }
      await sink.close();
    } finally {
      client.close();
    }
  }
}
