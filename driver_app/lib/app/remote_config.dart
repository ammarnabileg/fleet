import 'dart:async';

import 'package:firebase_remote_config/firebase_remote_config.dart';

import '../core/remote_version.dart';
import 'push.dart';

/// Firebase Remote Config on the phone, once Firebase is started with the server's values (push.dart): fetched and
/// activated in the background, at most once an hour (Firebase's own cache), and read by the updater. Firebase not
/// started, nothing fetched yet or the parameter missing: null, and the updater asks the server instead.
class FirebaseRemoteVersion implements RemoteVersionSource {
  static const keys = [
    'driver_latest_version_code',
    'driver_latest_version_name',
    'driver_force_update',
    'driver_download_url',
  ];

  static bool _configured = false;

  /// Right after Firebase starts: fetch and activate in the background, so the next check has the values.
  static Future<void> prefetch() async {
    try {
      await _fetch();
    } catch (_) {
      // offline or Remote Config not set up: the updater falls back to the server
    }
  }

  static Future<void> _fetch() async {
    final rc = FirebaseRemoteConfig.instance;
    if (!_configured) {
      await rc.setConfigSettings(
        RemoteConfigSettings(fetchTimeout: const Duration(seconds: 10), minimumFetchInterval: const Duration(hours: 1)),
      );
      _configured = true;
    }
    await rc.fetchAndActivate().timeout(const Duration(seconds: 12));
  }

  @override
  Future<RemoteVersion?> read() async {
    if (!FirebasePush.ready) return null;
    await prefetch(); // within the hour: Firebase answers from its cache without a request
    try {
      final rc = FirebaseRemoteConfig.instance;
      final code = rc.getValue(keys.first);
      if (code.source != ValueSource.valueRemote) return null; // never fetched: no value from the dashboard
      return RemoteVersion.fromValues({for (final k in keys) k: rc.getString(k)});
    } catch (_) {
      return null;
    }
  }
}
