import 'dart:convert';

import '../core/models.dart' show inLang;
import '../l10n/app_localizations.dart';
import '../status/engine.dart';
import 'tracker.dart' show NoticeInfo;

/// What the tracking service's single ongoing notification shows, after the design's six states: the work state and
/// the real tracking state as its title ("At work · location being sent"), one line of text, and a line more when
/// expanded (the shift's start, the day ended, the last confirmed send, the maintenance center); the company in its
/// header. Android draws the frame: the design's colours are its accent only. The service being alive is never proven
/// by this notification: the server's stale detection stays the truth.
class NoticeContent {
  const NoticeContent({
    required this.state,
    required this.title,
    required this.body,
    required this.big,
    required this.header,
    required this.color,
  });

  /// working_active / off_active / stale / waiting_first / off / maintenance (the design's states).
  final String state;
  final String title;
  final String body;
  final String big;
  final String header;
  final int color;

  @override
  bool operator ==(Object other) =>
      other is NoticeContent &&
      other.title == title &&
      other.body == body &&
      other.big == big &&
      other.header == header &&
      other.color == color;

  @override
  int get hashCode => Object.hash(title, body, big, header, color);
}

// accents readable on Android's light notification shade (the design's are for a dark one: #67e7b4, #8dc8ff, ...)
const green = 0xFF15803D;
const blue = 0xFF1D4ED8;
const amber = 0xFFB45309;
const grey = 0xFF6B7280;
const purple = 0xFF7C3AED;

String hm(DateTime t) {
  final l = t.toLocal();
  return '\u2066${l.hour.toString().padLeft(2, '0')}:${l.minute.toString().padLeft(2, '0')}\u2069';
}

/// The notification's data from the live status the service keeps (null fields: not known).
NoticeInfo noticeInfo(LiveStatus s) => NoticeInfo(
  shiftStartedAt: s.shiftStartedAt,
  dayEnded: s.dayEnded,
  ordersToday: s.ordersToday,
  inMaintenance: s.vehicle == 'maintenance',
  center: s.center,
  stage: s.stage,
);

/// [tracking]: active / stale / off. [lastFixAt]: the last fix this phone got (null: none since tracking started);
/// [lastSentAt]: the last upload the server confirmed.
NoticeContent workNoticeContent(
  AppLocalizations l, {
  required String lang,
  required Map<String, dynamic>? company,
  required bool working,
  required String tracking,
  DateTime? lastFixAt,
  DateTime? lastSentAt,
  NoticeInfo? info,
}) {
  final header = (inLang(company, lang) ?? l.appTitle) as String;
  final work = working ? l.noticeAtWork : l.noticeOffDuty;
  final offMeta = info?.dayEnded == true
      ? (info?.ordersToday == null ? l.noticeDayEndedNoCount : l.noticeDayEnded('\u2066${info!.ordersToday}\u2069'))
      : l.noticeDayNotStarted;
  final sent = lastSentAt == null ? l.noticeNoneConfirmed : l.noticeLastConfirmed(hm(lastSentAt));
  NoticeContent make(String state, String title, String body, String? meta, int color) => NoticeContent(
    state: state,
    title: title,
    body: body,
    big: meta == null || meta.isEmpty ? body : '$body\n$meta',
    header: header,
    color: color,
  );
  if (tracking == 'off' && info?.inMaintenance == true) {
    final where = StatusEngine.fill('{center} · {stage}', {'center': info?.center, 'stage': info?.stage});
    return make('maintenance', '${l.noticeInMaintenance} · ${l.trackingOff}', l.noticeBigOff, where, purple);
  }
  switch (tracking) {
    case 'active':
      final body = lastSentAt != null
          ? l.noticeBigActive(hm(lastSentAt))
          : lastFixAt == null
          ? l.noticeLocating
          : l.noticeNoneConfirmed;
      final start = info?.shiftStartedAt;
      final meta = working ? (start == null ? null : l.noticeShiftFrom(hm(start))) : offMeta;
      return make(
        working ? 'working_active' : 'off_active',
        '$work · ${l.trackingActive}',
        body,
        meta,
        working ? green : blue,
      );
    case 'stale':
      if (lastFixAt == null) {
        return make('waiting_first', '$work · ${l.noticeAwaitingFirst}', l.noticeBigStaleNever, sent, amber);
      }
      return make('stale', '$work · ${l.trackingStale}', l.noticeBigStale(hm(lastFixAt)), sent, amber);
    default:
      return make('off', '$work · ${l.trackingOff}', l.noticeBigOff, working ? null : offMeta, grey);
  }
}

/// The alerts that pop up as heads-up notifications (on their own high-importance channel): a contact request and a
/// location problem. Each alert id once only; none when the driver refused notifications (Android 13): he sees them
/// in the app.
const headsUpCodes = {'contact_request', 'location_problem'};

List<StatusAlert> headsUpToPost(
  List<StatusAlert> alerts, {
  required Set<String> posted,
  required bool allowed,
  required DateTime now,
}) {
  if (!allowed) return const [];
  return [
    for (final a in alerts)
      if (headsUpCodes.contains(a.code) && !posted.contains(a.id) && !a.expired(now)) a,
  ];
}

/// A stable small notification id per alert id (the foreground notification keeps its own, outside this range).
int headsUpId(String alertId) {
  var h = 0;
  for (final c in alertId.codeUnits) {
    h = (h * 31 + c) & 0x7FFFFFFF; // String.hashCode differs between runs: this one does not
  }
  return 5000 + (h & 0x7FF);
}

/// A notification button: [opensApp] ones bring the app up (a call needs it, so do the settings); the others run in
/// the background.
class NoticeAction {
  const NoticeAction(this.id, this.label, {required this.opensApp});

  final String id;
  final String label;
  final bool opensApp;
}

class HeadsUpContent {
  const HeadsUpContent({
    required this.title,
    required this.body,
    required this.big,
    required this.color,
    required this.actions,
    required this.payload,
  });

  final String title;
  final String body;
  final String big;
  final int color;
  final List<NoticeAction> actions;
  final String payload;
}

/// The heads-up of an important alert, after the design: a contact request (blue, «Call» when the supervisor has a
/// phone, «Done»), a location problem (amber, «Open location settings»).
HeadsUpContent headsUpContent(AppLocalizations l, StatusAlert alert) {
  final phone = alert.data['phone'], request = alert.data['request_id'];
  final payload = jsonEncode({
    'alert': alert.id,
    'code': alert.code,
    if (request is String) 'request_id': request,
    if (phone is String && phone.isNotEmpty) 'phone': phone,
  });
  if (alert.code == 'contact_request') {
    final body = alert.title ?? '';
    final message = alert.data['message'];
    return HeadsUpContent(
      title: l.headsUpContact,
      body: body,
      big: [body, if (message is String && message.isNotEmpty) '«$message»'].join('\n'),
      color: blue,
      actions: [
        if (phone is String && phone.isNotEmpty) NoticeAction('call', l.statusCall, opensApp: true),
        if (request is String) NoticeAction('ack', l.statusDone, opensApp: false),
      ],
      payload: payload,
    );
  }
  if (alert.code == 'location_problem') {
    final last = alert.values['last_update'];
    final body = last == null || last.isEmpty ? l.headsUpLocationBodyNever : l.headsUpLocationBody('\u2066$last\u2069');
    return HeadsUpContent(
      title: alert.title ?? l.trackingStale,
      body: body,
      big: body,
      color: amber,
      actions: [NoticeAction('location_settings', l.actionOpenLocationSettings, opensApp: true)],
      payload: payload,
    );
  }
  final body = alert.subtitle ?? '';
  return HeadsUpContent(
    title: alert.title ?? l.appTitle,
    body: body,
    big: body,
    color: grey,
    actions: const [],
    payload: payload,
  );
}

/// What a tap on a notification asks for: [kind] is open (the app, at [target]), call, ack or location_settings.
class NoticeTap {
  const NoticeTap(this.kind, {this.requestId, this.phone, this.target = 'inbox'});

  final String kind;
  final String? requestId;
  final String? phone;

  /// Where a plain tap opens the app: the inbox (its «current» section), or the screen named (maintenance, accident).
  final String target;
}

const openTargets = {'inbox', 'maintenance', 'accident', 'cash', 'documents', 'leave'};

/// Reads a tap from the plugin's response: an unknown button or a damaged payload only opens the app.
NoticeTap noticeTap(String? actionId, String? payload) {
  Map<String, dynamic> p;
  try {
    final j = jsonDecode(payload ?? '{}');
    p = j is Map<String, dynamic> ? j : const {};
  } on FormatException {
    p = const {};
  }
  final request = p['request_id'] is String ? p['request_id'] as String : null;
  final phone = p['phone'] is String ? p['phone'] as String : null;
  return switch (actionId) {
    'call' when phone != null => NoticeTap('call', phone: phone),
    'ack' when request != null => NoticeTap('ack', requestId: request),
    'location_settings' => const NoticeTap('location_settings'),
    _ => NoticeTap('open', target: openTargets.contains(p['open']) ? p['open'] as String : 'inbox'),
  };
}

/// Does what a tap asked for, in the app: a call (the dialer, the driver presses call), the phone's location
/// settings, «Done» (when it reached the app rather than the background). A plain tap opens the app where it says.
Future<void> runNoticeTap(
  NoticeTap tap, {
  required Future<bool> Function(String phone)? dial,
  required Future<void> Function()? openLocationSettings,
  required Future<void> Function(String requestId) acknowledge,
  void Function(String target)? open,
}) async {
  switch (tap.kind) {
    case 'open':
      open?.call(tap.target);
    case 'call':
      await dial?.call(tap.phone!);
    case 'location_settings':
      await openLocationSettings?.call();
    case 'ack':
      await acknowledge(tap.requestId!);
  }
}
