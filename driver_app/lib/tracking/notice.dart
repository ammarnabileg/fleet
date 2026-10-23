import '../core/models.dart' show inLang;
import '../l10n/app_localizations.dart';
import '../status/engine.dart';

/// What the tracking service's single ongoing notification shows: the company as its title, whether the driver is at
/// work and the real tracking state (from the fixes the service actually got, not a promise), with the longer text
/// when expanded. The service being alive is never proven by this notification: the server's stale detection stays
/// the truth.
class NoticeContent {
  const NoticeContent({
    required this.title,
    required this.body,
    required this.big,
    required this.color,
    required this.colorized,
  });

  final String title;
  final String body;
  final String big;
  final int color;
  final bool colorized;

  @override
  bool operator ==(Object other) =>
      other is NoticeContent && other.title == title && other.body == body && other.big == big;

  @override
  int get hashCode => Object.hash(title, body, big);
}

const green = 0xFF15803D;
const amber = 0xFFB45309;
const grey = 0xFF6B7280;

String hm(DateTime t) {
  final l = t.toLocal();
  return '\u2066${l.hour.toString().padLeft(2, '0')}:${l.minute.toString().padLeft(2, '0')}\u2069';
}

/// [tracking]: active / stale / off.
NoticeContent workNoticeContent(
  AppLocalizations l, {
  required String lang,
  required Map<String, dynamic>? company,
  required bool working,
  required String tracking,
  DateTime? lastFixAt,
}) {
  final title = (inLang(company, lang) ?? l.appTitle) as String;
  final status = working ? l.driverWorking : l.driverNotWorking;
  final (trackText, big) = switch (tracking) {
    'active' => (l.trackingActive, lastFixAt == null ? l.trackingActive : l.noticeBigActive(hm(lastFixAt))),
    'stale' => (l.trackingStale, lastFixAt == null ? l.noticeBigStaleNever : l.noticeBigStale(hm(lastFixAt))),
    _ => (l.trackingOff, l.noticeBigOff),
  };
  return NoticeContent(
    title: title,
    body: '● $status · $trackText',
    big: '● $status · $trackText\n$big',
    color: working ? (tracking == 'stale' ? amber : green) : grey,
    colorized: working && tracking == 'active',
  );
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
