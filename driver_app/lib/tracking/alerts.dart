import 'dart:convert';

import '../core/api.dart';
import '../core/db.dart';
import '../status/engine.dart';
import 'notice.dart';

/// Run by the tracking service after each heartbeat: reads the driver's live status (kept for the app's screens
/// too) and pops up the important new alerts, each once. It never touches the tracking itself.
class AlertWatcher {
  AlertWatcher({
    required this.api,
    required this.db,
    required this.allowed,
    required this.post,
    DateTime Function()? clock,
  }) : _now = clock ?? DateTime.now;

  final Api api;
  final AppDb db;

  /// Whether the driver lets the app post notifications (Android 13 and later ask him).
  final Future<bool> Function() allowed;
  final Future<void> Function(StatusAlert alert) post;
  final DateTime Function() _now;

  static const postedKey = 'headsup_posted';

  /// The live status received (null: an answer it could not read).
  Future<LiveStatus?> check() async {
    final store = LiveStatusStore(db.get, db.put);
    final version = await store.version();
    final body = await api.get('/driver/live-status', query: {if (version != null) 'config_version': '$version'});
    final now = _now();
    final status = await store.save(body, now);
    if (status == null) return null;
    final posted = <String>{};
    try {
      posted.addAll([for (final x in jsonDecode(await db.get(postedKey) ?? '[]') as List) '$x']);
    } on FormatException {
      // forgotten: at worst an alert pops up again
    }
    final todo = headsUpToPost(status.alerts, posted: posted, allowed: await allowed(), now: now);
    for (final a in todo) {
      await post(a);
    }
    // an alert that went away and comes back (the location lost again) pops up again
    final current = {for (final a in status.alerts) a.id};
    final keep = {...posted.where(current.contains), for (final a in todo) a.id};
    await db.put(postedKey, jsonEncode(keep.toList()));
    return status;
  }
}
