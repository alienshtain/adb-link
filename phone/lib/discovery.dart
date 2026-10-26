import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

/// A computer running ADB Link that answered the search.
class FoundComputer {
  final String host;
  final int port;
  final String name;
  final String os;
  FoundComputer(this.host, this.port, this.name, this.os);
}

/// Finds computers running ADB Link on the networks this phone is on (Wi-Fi, hotspot, USB or Bluetooth tethering).
/// 1) shouts "ADBLINK?" on UDP port 8766 and listens for answers,
/// 2) in case broadcasts are blocked, asks every address of the local /24 networks on port 8765.
Future<List<FoundComputer>> findComputers({void Function(String)? progress}) async {
  final found = <String, FoundComputer>{};
  final locals = <InternetAddress>[];
  try {
    for (final nic in await NetworkInterface.list(type: InternetAddressType.IPv4)) {
      for (final a in nic.addresses) {
        if (!a.isLoopback) locals.add(a);
      }
    }
  } catch (_) {}

  // ---- 1) UDP broadcast
  progress?.call('broadcast');
  RawDatagramSocket? sock;
  try {
    sock = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
    sock.broadcastEnabled = true;
    final s = sock;
    final sub = s.listen((ev) {
      if (ev != RawSocketEvent.read) return;
      final d = s.receive();
      if (d == null) return;
      try {
        final j = jsonDecode(utf8.decode(d.data)) as Map<String, dynamic>;
        if (j['app'] == 'adblink') {
          found[d.address.address] = FoundComputer(
              d.address.address, (j['port'] as num?)?.toInt() ?? 8765, '${j['name'] ?? d.address.address}', '${j['os'] ?? ''}');
        }
      } catch (_) {}
    });
    final msg = utf8.encode('ADBLINK?');
    final targets = <String>{'255.255.255.255'};
    for (final a in locals) {
      final p = a.address.split('.');
      if (p.length == 4) targets.add('${p[0]}.${p[1]}.${p[2]}.255');
    }
    for (var round = 0; round < 3; round++) {
      for (final t in targets) {
        try {
          s.send(msg, InternetAddress(t), 8766);
        } catch (_) {}
      }
      await Future.delayed(const Duration(milliseconds: 500));
    }
    await sub.cancel();
  } catch (_) {
  } finally {
    sock?.close();
  }
  if (found.isNotEmpty) return found.values.toList();

  // ---- 2) ask the neighbours one by one (64 at a time)
  progress?.call('scan');
  final candidates = <String>[];
  for (final a in locals) {
    final p = a.address.split('.');
    if (p.length != 4) continue;
    for (var i = 1; i < 255; i++) {
      final ip = '${p[0]}.${p[1]}.${p[2]}.$i';
      if (ip != a.address && !candidates.contains(ip)) candidates.add(ip);
    }
  }
  Future<void> probe(String ip) async {
    try {
      final res = await http.get(Uri.http('$ip:8765', '/ping')).timeout(const Duration(milliseconds: 600));
      if (res.statusCode == 200) {
        final j = jsonDecode(res.body) as Map<String, dynamic>;
        if (j['app'] == 'adblink') found[ip] = FoundComputer(ip, 8765, ip, '');
      }
    } catch (_) {}
  }

  for (var i = 0; i < candidates.length; i += 64) {
    await Future.wait(candidates.skip(i).take(64).map(probe));
  }
  return found.values.toList();
}
