import 'dart:async';
import 'dart:ui';

import 'package:flutter/widgets.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:geolocator/geolocator.dart';

import '../core/api.dart';
import '../core/config.dart';
import '../core/db.dart';
import '../core/tokens.dart';
import '../l10n/app_localizations.dart';
import 'fix_mapper.dart';
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
        initialNotificationTitle: 'تطبيق السائق',
        initialNotificationContent: '…', // replaced within seconds by the company and the work status (WorkNotice)
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
  return Geolocator.getPositionStream(locationSettings: settings).map(fixFromPosition);
}

/// The ongoing notification of the tracking service: the driver's company as its title, and under it whether he is
/// at work. At work the card is painted green (Android colours a foreground service's notification); not at work it
/// stays plain with the status in grey. Posted on the service's own id and channel, so it stays its notification.
class WorkNotice {
  WorkNotice([FlutterLocalNotificationsPlugin? plugin]) : _plugin = plugin ?? FlutterLocalNotificationsPlugin();

  final FlutterLocalNotificationsPlugin _plugin;
  static const channel = 'FOREGROUND_DEFAULT'; // created by flutter_background_service before its first post
  static const green = Color(0xFF15803D);
  static const grey = Color(0xFF6B7280);

  bool _ready = false;

  /// A notice that cannot be set up (say its icon went missing from a build) leaves the service's own notification
  /// in place; it never stops the tracking.
  Future<void> init() async {
    try {
      await _plugin.initialize(
        settings: const InitializationSettings(android: AndroidInitializationSettings('ic_bg_service_small')),
      );
      _ready = true;
    } catch (_) {}
  }

  Future<void> show({required String lang, required Map<String, dynamic>? company, required bool working}) async {
    if (!_ready) return;
    final l = lookupAppLocalizations(Locale(lang == 'en' ? 'en' : 'ar'));
    final title = (company?[lang] ?? company?['ar'] ?? l.appTitle) as String;
    final status = '● ${working ? l.driverWorking : l.driverNotWorking}';
    try {
      await _plugin.show(
        id: TrackingService.notificationId,
        title: title,
        body: working ? '<b>$status</b>' : '<font color="#6B7280"><b>$status</b></font>',
        notificationDetails: NotificationDetails(
          android: AndroidNotificationDetails(
            channel,
            'Background Service',
            ongoing: true,
            autoCancel: false,
            onlyAlertOnce: true,
            showWhen: false,
            playSound: false,
            enableVibration: false,
            importance: Importance.low,
            priority: Priority.low,
            category: AndroidNotificationCategory.service,
            icon: 'ic_bg_service_small',
            color: working ? green : grey,
            colorized: working,
            styleInformation: const DefaultStyleInformation(true, true),
          ),
        ),
      );
    } catch (_) {}
  }
}

@pragma('vm:entry-point')
Future<void> trackingMain(ServiceInstance service) async {
  WidgetsFlutterBinding.ensureInitialized();
  DartPluginRegistrant.ensureInitialized();
  final db = await AppDb.open();
  final api = Api(baseUrl: AppConfig.apiUrl, tokens: TokenStore(db), lang: await db.get('lang') ?? 'ar');
  final notice = WorkNotice();
  await notice.init();
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
    notify: (company, working) => notice.show(lang: api.lang, company: company, working: working),
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
