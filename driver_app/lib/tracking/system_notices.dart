import 'dart:convert';
import 'dart:ui' show Color;

import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../core/models.dart' show Accident, MaintenanceRequest;
import '../l10n/app_localizations.dart';
import '../status/engine.dart';
import 'notice.dart';

/// The driver's current situations (the live status's alerts, the car's state, a car ready at the center, an
/// accident waiting for its police report) live outside the home screen: as system notifications and in the inbox's
/// «current» section. This file says which notifications stand for them, and keeps the phone's shade in step: each
/// posted once, updated in place when its text changes, cancelled when it is over. Refused notifications (Android 13
/// and later): nothing is posted, the inbox shows them all the same.

/// The two channels: important alerts pop over the screen; the others arrive quietly in the shade.
const alertsChannel = 'driver_alerts';
const messagesChannel = 'driver_messages';

/// The current cards: every alert (most important first), then the car's card when no alert already says it.
List<StatusCard> currentCards(StatusView? view) {
  if (view == null) return const [];
  final codes = {for (final a in view.alerts) a.code};
  return [...view.alerts, if (view.vehicle != null && !codes.contains(view.vehicle!.code)) view.vehicle!];
}

class SystemNotice {
  const SystemNotice({
    required this.key,
    required this.channel,
    required this.title,
    required this.body,
    required this.big,
    required this.color,
    required this.payload,
    this.actions = const [],
  });

  /// Stable per situation (the alert id, «mnt-ready:ID», «accident:ID»).
  final String key;
  final String channel;
  final String title;
  final String body;
  final String big;
  final int color;
  final String payload;
  final List<NoticeAction> actions;

  int get id => headsUpId(key);

  /// What, when changed, updates the notification in place.
  String get signature => jsonEncode([channel, title, body, big, color, for (final a in actions) a.label]);
}

/// The notification of a current card: a contact request or a location problem as the heads-up it always was (with
/// its buttons); the others quietly on the messages channel, a tap opening the inbox.
SystemNotice cardNotice(AppLocalizations l, StatusCard card) {
  final alert = card.alert;
  if (alert != null && headsUpCodes.contains(alert.code)) {
    final c = headsUpContent(l, alert);
    return SystemNotice(
      key: card.key,
      channel: alertsChannel,
      title: c.title,
      body: c.body,
      big: c.big,
      color: c.color,
      payload: c.payload,
      actions: c.actions,
    );
  }
  return SystemNotice(
    key: card.key,
    channel: messagesChannel,
    title: card.title.isEmpty ? l.appTitle : card.title,
    body: card.subtitle,
    big: card.subtitle,
    color: card.color,
    payload: jsonEncode({'open': 'inbox', 'alert': card.key}),
  );
}

SystemNotice readyNotice(AppLocalizations l, MaintenanceRequest r) {
  final body = l.mntReadyBanner('\u2066${r.plate}\u2069', r.centerName ?? '');
  return SystemNotice(
    key: 'mnt-ready:${r.id}',
    channel: messagesChannel,
    title: l.maintenance,
    body: body,
    big: body,
    color: green,
    payload: jsonEncode({'open': 'maintenance'}),
  );
}

SystemNotice policeNotice(AppLocalizations l, Accident a) {
  final body = l.accAwaitingPolice('${a.number}');
  return SystemNotice(
    key: 'accident:${a.id}',
    channel: messagesChannel,
    title: l.accident,
    body: body,
    big: body,
    color: amber,
    payload: jsonEncode({'open': 'accident'}),
  );
}

/// Posts and cancels the phone's notifications (the plugin on the phone, a fake in the tests).
abstract class NoticePoster {
  Future<bool> allowed();
  Future<void> post(SystemNotice n);
  Future<void> cancel(int id);
}

/// Keeps one group of notifications ([scope]: «alerts» from the live status, written by the app and the tracking
/// service alike; «banners», by the app) in step with what is current. What was posted is kept in the phone's
/// database, so a restart neither posts again nor forgets what to cancel.
class NoticeSync {
  NoticeSync({required this.get, required this.put, required this.poster, required this.scope});

  final Future<String?> Function(String key) get;
  final Future<void> Function(String key, String? value) put;
  final NoticePoster poster;
  final String scope;

  String get _key => 'sysnotices_$scope';

  Future<Map<String, String>> posted() async {
    try {
      final j = jsonDecode(await get(_key) ?? '{}');
      if (j is Map) return {for (final e in j.entries) '${e.key}': '${e.value}'};
    } on FormatException {
      // forgotten: at worst one is posted again
    }
    return {};
  }

  Future<void> sync(List<SystemNotice> current) async {
    final before = await posted();
    if (!await poster.allowed()) {
      // refused: nothing on the phone; the inbox shows them. Allowed again later, they are posted then.
      if (before.isNotEmpty) await put(_key, '{}');
      return;
    }
    final now = <String, String>{};
    for (final n in current) {
      now[n.key] = n.signature;
      if (before[n.key] != n.signature) {
        try {
          await poster.post(n);
        } catch (_) {
          now.remove(n.key); // tried again next time
        }
      }
    }
    for (final key in before.keys) {
      if (!now.containsKey(key)) {
        try {
          await poster.cancel(headsUpId(key));
        } catch (_) {}
      }
    }
    await put(_key, jsonEncode(now));
  }
}

/// The plugin's side: both channels created before the first post, the heads-up channel high (over the screen, its
/// updates silent), the messages channel at the default importance (in the shade, with a sound, never over the
/// screen).
class PluginPoster implements NoticePoster {
  PluginPoster(this.plugin, {required this.strings, this.header});

  final FlutterLocalNotificationsPlugin plugin;
  final Future<AppLocalizations> Function() strings;
  final String? Function()? header;

  AndroidFlutterLocalNotificationsPlugin? get _android =>
      plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();

  static Future<void> createChannels(FlutterLocalNotificationsPlugin plugin, AppLocalizations l) async {
    final android = plugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
    await android?.createNotificationChannel(
      AndroidNotificationChannel(alertsChannel, l.alertsChannel, importance: Importance.high),
    );
    await android?.createNotificationChannel(
      AndroidNotificationChannel(messagesChannel, l.messagesChannel, importance: Importance.defaultImportance),
    );
  }

  @override
  Future<bool> allowed() async {
    try {
      return await _android?.areNotificationsEnabled() ?? false;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> post(SystemNotice n) async {
    final l = await strings();
    await createChannels(plugin, l);
    final high = n.channel == alertsChannel;
    await plugin.show(
      id: n.id,
      title: n.title,
      body: n.body,
      payload: n.payload,
      notificationDetails: NotificationDetails(
        android: AndroidNotificationDetails(
          n.channel,
          high ? l.alertsChannel : l.messagesChannel,
          importance: high ? Importance.high : Importance.defaultImportance,
          priority: high ? Priority.high : Priority.defaultPriority,
          onlyAlertOnce: true, // an update in place does not ring again
          category: high ? AndroidNotificationCategory.message : AndroidNotificationCategory.status,
          icon: 'ic_bg_service_small',
          color: Color(n.color),
          subText: header?.call() ?? l.appTitle,
          styleInformation: BigTextStyleInformation(n.big, contentTitle: n.title),
          actions: [
            for (final a in n.actions) AndroidNotificationAction(a.id, a.label, showsUserInterface: a.opensApp),
          ],
        ),
      ),
    );
  }

  @override
  Future<void> cancel(int id) => plugin.cancel(id: id);
}
