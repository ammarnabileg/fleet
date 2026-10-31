import '../core/api.dart';
import '../core/db.dart';
import '../l10n/app_localizations.dart';
import '../status/engine.dart';
import 'system_notices.dart';

/// Run by the tracking service after each heartbeat: reads the driver's live status (kept for the app's screens
/// too) and keeps its system notifications in step (system_notices.dart): each current alert posted once, updated in
/// place when its text changes, cancelled once it is over. It never touches the tracking itself.
class AlertWatcher {
  AlertWatcher({
    required this.api,
    required this.db,
    required this.poster,
    required this.strings,
    DateTime Function()? clock,
  }) : _now = clock ?? DateTime.now;

  final Api api;
  final AppDb db;
  final NoticePoster poster;
  final Future<AppLocalizations> Function() strings;
  final DateTime Function() _now;

  /// The live status received (null: an answer it could not read).
  Future<LiveStatus?> check() async {
    final store = LiveStatusStore(db.get, db.put);
    final version = await store.version();
    final body = await api.get('/driver/live-status', query: {if (version != null) 'config_version': '$version'});
    final now = _now();
    final status = await store.save(body, now);
    if (status == null) return null;
    await syncAlertNotices(
      db: db,
      poster: poster,
      l: await strings(),
      view: compose(status, await store.config(), now: now, lang: api.lang),
    );
    return status;
  }
}

/// The live status's notifications, as the app and the tracking service both keep them (one record of what is
/// posted, so they never post the same twice).
Future<void> syncAlertNotices({
  required AppDb db,
  required NoticePoster poster,
  required AppLocalizations l,
  required StatusView? view,
}) => NoticeSync(
  get: db.get,
  put: db.put,
  poster: poster,
  scope: 'alerts',
).sync([for (final c in currentCards(view)) cardNotice(l, c)]);
