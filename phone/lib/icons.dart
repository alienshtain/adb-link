import 'package:flutter/material.dart';

import 'style.dart';

/// Icons a command can use. The computer stores only the key (for example "lock").
const Map<String, IconData> commandIcons = {
  'lock': Icons.lock_rounded,
  'bedtime': Icons.bedtime_rounded,
  'power_settings_new': Icons.power_settings_new_rounded,
  'restart_alt': Icons.restart_alt_rounded,
  'volume_up': Icons.volume_up_rounded,
  'volume_down': Icons.volume_down_rounded,
  'volume_off': Icons.volume_off_rounded,
  'play_arrow': Icons.play_arrow_rounded,
  'pause': Icons.pause_rounded,
  'skip_next': Icons.skip_next_rounded,
  'skip_previous': Icons.skip_previous_rounded,
  'screenshot_monitor': Icons.screenshot_monitor_rounded,
  'terminal': Icons.terminal_rounded,
  'link': Icons.link_rounded,
  'language': Icons.language_rounded,
  'public': Icons.public_rounded,
  'folder': Icons.folder_rounded,
  'music_note': Icons.music_note_rounded,
  'headphones': Icons.headphones_rounded,
  'speaker': Icons.speaker_rounded,
  'mic': Icons.mic_rounded,
  'photo_camera': Icons.photo_camera_rounded,
  'movie': Icons.movie_rounded,
  'tv': Icons.tv_rounded,
  'cast': Icons.cast_rounded,
  'sports_esports': Icons.sports_esports_rounded,
  'wifi': Icons.wifi_rounded,
  'bluetooth': Icons.bluetooth_rounded,
  'brightness_high': Icons.brightness_high_rounded,
  'brightness_low': Icons.brightness_low_rounded,
  'light_mode': Icons.light_mode_rounded,
  'dark_mode': Icons.dark_mode_rounded,
  'lightbulb': Icons.lightbulb_rounded,
  'home': Icons.home_rounded,
  'star': Icons.star_rounded,
  'favorite': Icons.favorite_rounded,
  'notifications': Icons.notifications_rounded,
  'alarm': Icons.alarm_rounded,
  'timer': Icons.timer_rounded,
  'settings': Icons.settings_rounded,
  'build': Icons.build_rounded,
  'code': Icons.code_rounded,
  'bug_report': Icons.bug_report_rounded,
  'bolt': Icons.bolt_rounded,
  'rocket_launch': Icons.rocket_launch_rounded,
  'power': Icons.power_rounded,
  'laptop': Icons.laptop_rounded,
  'mouse': Icons.mouse_rounded,
  'keyboard': Icons.keyboard_rounded,
  'memory': Icons.memory_rounded,
  'storage': Icons.storage_rounded,
  'cloud': Icons.cloud_rounded,
  'download': Icons.download_rounded,
  'upload': Icons.upload_rounded,
  'refresh': Icons.refresh_rounded,
  'delete': Icons.delete_rounded,
  'print': Icons.print_rounded,
  'mail': Icons.mail_rounded,
  'chat': Icons.chat_rounded,
  'search': Icons.search_rounded,
  'security': Icons.security_rounded,
  'flag': Icons.flag_rounded,
  'videocam': Icons.videocam_rounded,
  'image': Icons.image_rounded,
  'description': Icons.description_rounded,
  'apps': Icons.apps_rounded,
  'dashboard': Icons.dashboard_rounded,
  'sync': Icons.sync_rounded,
  'usb': Icons.usb_rounded,
  'phone_android': Icons.phone_android_rounded,
  'location_on': Icons.location_on_rounded,
  'coffee': Icons.coffee_rounded,
  'mic_off': Icons.mic_off_rounded,
  'wifi_off': Icons.wifi_off_rounded,
  'volume_mute': Icons.volume_mute_rounded,
  'cloud_download': Icons.cloud_download_rounded,
  'cleaning_services': Icons.cleaning_services_rounded,
  'ac_unit': Icons.ac_unit_rounded,
};

const List<String> commandColors = [
  '#3584E4',
  '#0091FF',
  '#12A594',
  '#30A46C',
  '#F5A524',
  '#F76B15',
  '#E5484D',
  '#D6409F',
  '#8E4EC6',
  '#5E5CE6',
  '#687076',
  '#1F2937',
];

Color colorFromHex(String hex, Color fallback) {
  final m = RegExp(r'^#([0-9a-fA-F]{6})$').firstMatch(hex);
  if (m == null) return fallback;
  return Color(int.parse('FF${m.group(1)}', radix: 16));
}

/// A round, filled icon in the app's one accent colour (Settings > Icon colour), white glyph inside.
/// [color] is accepted only so old code compiles: every command icon uses the same colour now.
class RoundIcon extends StatelessWidget {
  final String icon;
  final String color;
  final double size;
  const RoundIcon({super.key, required this.icon, this.color = '', this.size = 56});

  @override
  Widget build(BuildContext context) {
    final data = commandIcons[icon];
    return ListenableBuilder(
      listenable: AppStyle.I,
      builder: (context, _) => Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: AppStyle.I.color, shape: BoxShape.circle),
        child: data != null
            ? Icon(data, color: Colors.white, size: size * 0.5)
            : Text(icon.isEmpty ? '⚙' : icon, style: TextStyle(fontSize: size * 0.45)),
      ),
    );
  }
}
