import 'dart:async';
import 'dart:io';
import 'dart:ui';

import 'package:flutter/widgets.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:geolocator/geolocator.dart';
import 'package:path_provider/path_provider.dart';

import '../core/api.dart';
import '../core/config.dart';
import '../core/db.dart';
import '../core/error_log.dart';
import '../core/tokens.dart';
import '../core/translations.dart';
import '../l10n/app_localizations.dart';
import '../status/engine.dart';
import 'alerts.dart';
import 'fix_mapper.dart';
import 'health.dart';
import 'notice.dart';
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

/// The ongoing notification of the tracking service, always the same one (its id and channel), updated in place
/// when what it says changes: the company as its title, whether the driver is at work and the real tracking state;
/// expanded, the time of the last location. At work with tracking active the card is painted green (Android colours a
/// foreground service's notification). One action: open the app. The important alerts go on their own channel.
class WorkNotice {
  WorkNotice([FlutterLocalNotificationsPlugin? plugin]) : _plugin = plugin ?? FlutterLocalNotificationsPlugin();

  final FlutterLocalNotificationsPlugin _plugin;
  static const channel = 'FOREGROUND_DEFAULT'; // created by flutter_background_service before its first post
  static const alertsChannel = 'driver_alerts';

  bool _ready = false;

  /// The published strings kept on the phone (the app downloads them), read again now and then: this service runs
  /// in its own engine.
  final _bundles = BundleStore(
    () => getApplicationSupportDirectory().then<Directory?>((d) => d, onError: (Object _) => null),
    appBuild: AppConfig.appBuild,
  );
  final _read = <String, (DateTime, RemoteStrings)>{};

  Future<AppLocalizations> _strings(String lang) async {
    final kept = _read[lang];
    if (kept == null || DateTime.now().difference(kept.$1) > const Duration(minutes: 10)) {
      RemoteStrings remote;
      try {
        final b = await _bundles.read(lang);
        remote = b == null ? RemoteStrings.empty : RemoteStrings(lang, b.version, b.strings);
      } catch (_) {
        remote = RemoteStrings.empty;
      }
      _read[lang] = (DateTime.now(), remote);
    }
    return appStrings(Locale(lang), _read[lang]!.$2);
  }

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

  AndroidFlutterLocalNotificationsPlugin? get _android =>
      _plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();

  /// Android 13 and later: the driver may refuse notifications; then the alerts stay in the app.
  Future<bool> allowed() async {
    if (!_ready) return false;
    try {
      return await _android?.areNotificationsEnabled() ?? false;
    } catch (_) {
      return false;
    }
  }

  Future<void> show({required String lang, required WorkState state}) async {
    if (!_ready) return;
    final l = await _strings(lang);
    final c = workNoticeContent(
      l,
      lang: lang,
      company: state.company,
      working: state.working,
      tracking: state.tracking,
      lastFixAt: state.lastFixAt,
    );
    try {
      await _plugin.show(
        id: TrackingService.notificationId,
        title: c.title,
        body: c.body,
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
            color: Color(c.color),
            colorized: c.colorized,
            styleInformation: BigTextStyleInformation(c.big),
            actions: [AndroidNotificationAction('open', l.openApp, showsUserInterface: true)],
          ),
        ),
      );
    } catch (_) {}
  }

  /// A heads-up for an important alert (a contact request, a location problem), on the high-importance channel.
  Future<void> headsUp({required String lang, required StatusAlert alert}) async {
    if (!_ready) return;
    final l = await _strings(lang);
    try {
      await _android?.createNotificationChannel(
        AndroidNotificationChannel(alertsChannel, l.alertsChannel, importance: Importance.high),
      );
      await _plugin.show(
        id: headsUpId(alert.id),
        title: alert.title ?? l.appTitle,
        body: alert.subtitle,
        notificationDetails: NotificationDetails(
          android: AndroidNotificationDetails(
            alertsChannel,
            l.alertsChannel,
            importance: Importance.high,
            priority: Priority.high,
            category: AndroidNotificationCategory.message,
            icon: 'ic_bg_service_small',
            styleInformation: BigTextStyleInformation(
              [alert.subtitle, alert.data['message']].whereType<String>().where((x) => x.isNotEmpty).join('\n'),
            ),
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
  // whatever escapes (a plugin's error, a timer) goes to the phone's local error log, never stops the service quietly
  AppDb? db;
  FlutterError.onError = (d) => unawaited(_log(db, 'service.flutter', d.exception, d.stack));
  await runZonedGuarded(() async {
    db = await AppDb.open();
    await _run(service, db!);
  }, (e, st) => unawaited(_log(db, 'service.zone', e, st)));
}

Future<void> _log(AppDb? db, String where, Object e, StackTrace? st) async {
  if (db != null) await ErrorLog(db).record(where, e, st);
}

Future<void> _run(ServiceInstance service, AppDb db) async {
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
    notifyState: (state) => notice.show(lang: api.lang, state: state),
    // the live status and its important alerts: shown, never a reason to start tracking
    checkAlerts: () => AlertWatcher(
      api: api,
      db: db,
      allowed: notice.allowed,
      post: (alert) => notice.headsUp(lang: api.lang, alert: alert),
    ).check(),
    onSessionEnded: () => service.stopSelf(),
  );
  service.on('stop').listen((_) async {
    await tracker.stop();
    await service.stopSelf();
  });
  service.on('refresh').listen((_) async {
    try {
      api.lang = await db.get('lang') ?? api.lang;
    } catch (e, st) {
      await tracker.errors.record('service.refresh', e, st);
    }
    await tracker.heartbeat();
    await tracker.sync();
  });
  await tracker.start();
}
