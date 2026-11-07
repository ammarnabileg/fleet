import 'dart:convert';

import 'db.dart';
import 'errors.dart';

/// A small log of unexpected failures, kept on the phone only (no outside service). It records where it happened,
/// the kind of error and the app's own frames of the stack: never the error's message, which may carry a driver's
/// data (a name, a plate, a token in a URL). The newest [keep] entries stay.
class ErrorLog {
  ErrorLog(this.db, {DateTime Function()? clock}) : _now = clock ?? DateTime.now;

  final AppDb db;
  final DateTime Function() _now;

  static const key = 'error_log';
  static const keep = 50;

  /// Never throws: a log that cannot be written must not become a second failure.
  Future<void> record(String where, Object error, [StackTrace? stack]) async {
    try {
      final entry = {
        'at': _now().toUtc().toIso8601String(),
        'where': where,
        'type': describe(error),
        if (stack != null) 'stack': frames(stack),
      };
      await db.raw.transaction((tx) async {
        final old = await db.get(key, tx: tx);
        final list = old == null ? <dynamic>[] : jsonDecode(old) as List<dynamic>;
        list.add(entry);
        final kept = list.length > keep ? list.sublist(list.length - keep) : list;
        await db.put(key, jsonEncode(kept), tx: tx);
      });
    } catch (_) {
      // the database itself is failing: nothing more can be done here
    }
  }

  Future<List<Map<String, dynamic>>> entries() async {
    final raw = await db.get(key);
    if (raw == null) return [];
    return [for (final e in jsonDecode(raw) as List<dynamic>) Map<String, dynamic>.from(e as Map)];
  }

  /// The kind of error, with the server's stable code for an API error (a code, never free text).
  static String describe(Object error) => switch (error) {
    ApiError(:final status, :final code) => 'ApiError($status, $code)',
    _ => error.runtimeType.toString(),
  };

  /// The app's own frames (file and line), at most eight: enough to find the place, nothing of the data.
  static List<String> frames(StackTrace stack) => [
    for (final line in stack.toString().split('\n'))
      if (line.contains('package:fleet_driver/'))
        line.substring(line.indexOf('package:fleet_driver/')).replaceAll(')', '').trim(),
  ].take(8).toList();
}
