import 'dart:async';
import 'dart:ui';

import 'package:flutter/widgets.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:geolocator/geolocator.dart';

import '../core/api.dart';
import '../core/config.dart';
import '../core/db.dart';
import '../core/tokens.dart';
import 'health.dart';
import 'tracker.dart';

/// The Android foreground service (type "location") that keeps tracking when the app is closed. It runs in its
/// own Flutter engine; it shares only the database with the app.
class TrackingService {
  static const notificationId = 4210;

  /// [startOnBoot] only with "allow all the time": Android 14 refuses to start a location service from the
  /// background without it, and a refused start at boot would crash the app.
  static Future<void> configure({required bool startOnBoot}) {
    return FlutterBackgroundService().configure(
      androidConfiguration: AndroidConfiguration(
        onStart: trackingMain,
        autoStart: false,
        autoStartOnBoot: startOnBoot,
        isForegroundMode: true,
        initialNotificationTitle: 'تطبيق السائق · Driver app',
        initialNotificationContent: 'جاري الاتصال… · Connecting…',
        foregroundServiceNotificationId: notificationId,
        foregroundServiceTypes: [AndroidForegroundType.location],
      ),
      iosConfiguration: IosConfiguration(autoStart: false),
    );
  }

  /// Starts the service, or asks the running one to report and send now.
  static Future<void> start() async {
    final s = FlutterBackgroundService();
    if (await s.isRunning()) {
      s.invoke('refresh');
    } else {
      await s.startService();
    }
  }

  static void stop() => FlutterBackgroundService().invoke('stop');

  static Future<bool> running() => FlutterBackgroundService().isRunning();
}

Stream<Fix> _gps(Duration interval) {
  final settings = AndroidSettings(accuracy: LocationAccuracy.high, distanceFilter: 0, intervalDuration: interval);
  return Geolocator.getPositionStream(locationSettings: settings).map(
    (p) => Fix(
      at: p.timestamp,
      lat: p.latitude,
      lng: p.longitude,
      accuracyM: p.accuracy,
      speedKmh: p.speed >= 0 ? p.speed * 3.6 : null,
      heading: p.heading >= 0 ? p.heading.round() % 360 : null,
      isMock: p.isMocked,
    ),
  );
}

@pragma('vm:entry-point')
Future<void> trackingMain(ServiceInstance service) async {
  WidgetsFlutterBinding.ensureInitialized();
  DartPluginRegistrant.ensureInitialized();
  final db = await AppDb.open();
  final api = Api(baseUrl: AppConfig.apiUrl, tokens: TokenStore(db), lang: await db.get('lang') ?? 'ar');
  late final Tracker tracker;
  tracker = Tracker(
    db: db,
    api: api,
    fixes: _gps,
    health: ({required bool trackingRunning, required int queueSize, String? lastUploadAt}) => PhoneHealth.snapshot(
      trackingRunning: trackingRunning,
      queueSize: queueSize,
      lastUploadAt: lastUploadAt,
      appVersion: AppConfig.appVersion,
    ),
    notify: (title, text) {
      if (service is AndroidServiceInstance) service.setForegroundNotificationInfo(title: title, content: text);
    },
    onSessionEnded: () => service.stopSelf(),
  );
  service.on('stop').listen((_) async {
    await tracker.stop();
    await service.stopSelf();
  });
  service.on('refresh').listen((_) async {
    api.lang = await db.get('lang') ?? api.lang;
    await tracker.heartbeat();
    await tracker.sync();
  });
  await tracker.start();
}
