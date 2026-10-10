import 'dart:io';

import 'package:device_info_plus/device_info_plus.dart';
import 'package:uuid/uuid.dart';

import 'config.dart';
import 'db.dart';

/// What the server records about this phone. The id is random and local: a reinstall is a new device, which the
/// server binds again (activation link or code) and reports to the supervisor.
class DeviceIdentity {
  static Future<String> uid(AppDb db) async {
    final existing = await db.get('device_uid');
    if (existing != null) return existing;
    final id = const Uuid().v4();
    await db.put('device_uid', id);
    return id;
  }

  static Future<Map<String, String?>> meta() async {
    String? model;
    try {
      if (Platform.isAndroid) {
        final a = await DeviceInfoPlugin().androidInfo;
        model = '${a.manufacturer} ${a.model} (Android ${a.version.release})';
      }
    } catch (_) {
      model = null;
    }
    return {'platform': Platform.operatingSystem, 'model': _cut(model), 'app_version': AppConfig.appVersion};
  }

  static String? _cut(String? s) => s == null || s.length <= 60 ? s : s.substring(0, 60);
}
