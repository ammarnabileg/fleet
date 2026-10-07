import 'dart:convert';
import 'dart:io';

import 'api.dart';
import 'config.dart';
import 'db.dart';
import 'errors.dart';

/// What the driver did while the phone may be offline (an odometer reading, a daily report): stored with its
/// photo and original time, then sent in order. The server accepts readings up to 48 hours late with their real
/// time, so a lost connection never loses a reading.
class OutboxItem {
  OutboxItem(this.id, this.kind, this.payload, this.files, this.createdAt, this.state, this.attempts, this.lastError);

  factory OutboxItem.fromRow(Map<String, Object?> r) => OutboxItem(
    r['id'] as int,
    r['kind'] as String,
    Map<String, dynamic>.from(jsonDecode(r['payload'] as String) as Map),
    Map<String, String>.from(jsonDecode(r['files'] as String) as Map),
    DateTime.parse(r['created_at'] as String),
    r['state'] as String,
    r['attempts'] as int,
    r['last_error'] as String?,
  );

  final int id;
  final String
  kind; // odometer | report | report_edit | report_change | maintenance | accident | police_report | statement
  final Map<String, dynamic> payload;
  final Map<String, String> files; // payload field -> local file still to upload
  final DateTime createdAt;
  final String state; // pending | sending | failed
  final int attempts;
  final String? lastError;
}

enum SendResult { sent, queued }

class Outbox {
  Outbox(this.db, {DateTime Function()? clock}) : _now = clock ?? DateTime.now;

  final AppDb db;
  final DateTime Function() _now;

  /// Where each kind goes, how its files are uploaded, and which answers mean "already recorded" (the first try
  /// reached the server but its answer was lost: the retry must not count as a failure).
  static const _routes = {
    'odometer': ('/driver/odometer', 'camera', {'reading_exists'}, 'POST'),
    'report': ('/driver/reports', 'upload', {'report_exists'}, 'POST'),
    // the driver corrects his report before approval (sent again the same, it changes nothing)
    'report_edit': ('/driver/reports/{report_id}', 'upload', <String>{}, 'PATCH'),
    // after approval he asks for the change; a retry finds his request already waiting
    'report_change': ('/driver/reports/{report_id}/change-request', 'upload', {'change_request_exists'}, 'POST'),
    'maintenance': ('/driver/maintenance', 'camera', {'request_exists'}, 'POST'),
    // a renewed document for the office to check (a retry finds it already waiting)
    'renewal': ('/driver/documents/renewals', 'upload', {'renewal_exists'}, 'POST'),
    'accident': ('/driver/accidents', 'camera', {'accident_exists'}, 'POST'),
    // the office may have attached a report meanwhile: the accident has one, nothing more to send
    'police_report': ('/driver/accidents/{accident_id}/police-report', 'upload', {'police_report_exists'}, 'POST'),
    // the month's screenshots from the platform's app (from the gallery)
    'statement': ('/driver/statements', 'upload', {'statement_exists'}, 'POST'),
    // a fill: the invoice and the odometer from the camera (a retry sends the same invoice, already recorded)
    'fuel': ('/driver/fuel', 'camera', {'fuel_fill_exists'}, 'POST'),
    // his objection to a violation, with an optional screenshot (a retry finds it sent)
    'violation_objection': ('/driver/violations/{violation_id}/objection', 'upload', {'objection_exists'}, 'POST'),
  };
  static const _claimTimeout = Duration(minutes: 2);

  /// Fields that come from the phone's files even when the rest of the item is the camera's (the accident's police
  /// report, BRD FR-APP-06).
  static const _fromFiles = {'police_report'};

  Future<int> add(String kind, Map<String, dynamic> payload, Map<String, String> files) {
    assert(_routes.containsKey(kind));
    return db.raw.insert('outbox', {
      'kind': kind,
      'payload': jsonEncode(payload),
      'files': jsonEncode(files),
      'created_at': _now().toUtc().toIso8601String(),
    });
  }

  Future<List<OutboxItem>> items() async => [
    for (final r in await db.raw.query('outbox', orderBy: 'id')) OutboxItem.fromRow(r),
  ];

  Future<int> waiting() async =>
      (await db.raw.rawQuery("SELECT count(*) AS n FROM outbox WHERE state != 'failed'")).first['n'] as int;

  Future<void> discard(int id) async {
    final rows = await db.raw.query('outbox', where: 'id = ?', whereArgs: [id]);
    if (rows.isNotEmpty) await _deleteFiles(OutboxItem.fromRow(rows.first));
    await db.raw.delete('outbox', where: 'id = ?', whereArgs: [id]);
  }

  /// Sends one item now (right after the driver pressed send). A final refusal removes it and is thrown, so the
  /// driver can correct and send again; no network leaves it queued.
  Future<SendResult> sendNow(int id, Api api) async {
    final item = await _claim(id);
    if (item == null) return SendResult.queued;
    try {
      await _deliver(item, api);
      return SendResult.sent;
    } on ApiError catch (e) {
      if (e.isTransient) {
        await _release(item, e.code);
        return SendResult.queued;
      }
      await discard(item.id);
      rethrow;
    } on SessionEnded {
      await _release(item, 'session_ended');
      rethrow;
    }
  }

  /// Sends everything waiting, oldest first; stops at the first network problem to keep the order.
  Future<int> flush(Api api) async {
    var sent = 0;
    final rows = await db.raw.query('outbox', where: "state != 'failed'", orderBy: 'id');
    for (final r in rows) {
      final candidate = OutboxItem.fromRow(r);
      if (_now().difference(candidate.createdAt) > AppConfig.outboxMaxAge) {
        await db.raw.update(
          'outbox',
          {'state': 'failed', 'last_error': 'too_old'},
          where: 'id = ?',
          whereArgs: [candidate.id],
        );
        continue;
      }
      final item = await _claim(candidate.id);
      if (item == null) continue;
      try {
        await _deliver(item, api);
        sent++;
      } on ApiError catch (e) {
        if (e.isTransient) {
          await _release(item, e.code);
          break;
        }
        await db.raw.update(
          'outbox',
          {'state': 'failed', 'last_error': e.code, 'claimed_at': null},
          where: 'id = ?',
          whereArgs: [item.id],
        );
      } on SessionEnded {
        await _release(item, 'session_ended');
        rethrow;
      }
    }
    return sent;
  }

  /// Takes an item for sending, unless the other engine is sending it right now.
  Future<OutboxItem?> _claim(int id) {
    return db.exclusive((tx) async {
      final rows = await tx.query('outbox', where: 'id = ?', whereArgs: [id]);
      if (rows.isEmpty) return null;
      final item = OutboxItem.fromRow(rows.first);
      final claimed = rows.first['claimed_at'] as String?;
      if (item.state == 'failed') return null;
      if (item.state == 'sending' && claimed != null && _now().difference(DateTime.parse(claimed)) < _claimTimeout) {
        return null;
      }
      await tx.update(
        'outbox',
        {'state': 'sending', 'claimed_at': _now().toUtc().toIso8601String()},
        where: 'id = ?',
        whereArgs: [id],
      );
      return item;
    });
  }

  Future<void> _release(OutboxItem item, String error) => db.raw.update(
    'outbox',
    {'state': 'pending', 'claimed_at': null, 'attempts': item.attempts + 1, 'last_error': error},
    where: 'id = ?',
    whereArgs: [item.id],
  );

  Future<void> _deliver(OutboxItem item, Api api) async {
    final (path, source, alreadyDone, method) = _routes[item.kind]!;
    final payload = Map<String, dynamic>.from(item.payload);
    final files = Map<String, String>.from(item.files);
    // upload what is not uploaded yet, remembering each sha256 at once so a retry never uploads twice
    for (final field in files.keys.toList()) {
      final f = await api.upload(files[field]!, source: _fromFiles.contains(field) ? 'upload' : source);
      payload[field] = f['sha256'];
      files.remove(field);
      await db.raw.update(
        'outbox',
        {'payload': jsonEncode(payload), 'files': jsonEncode(files)},
        where: 'id = ?',
        whereArgs: [item.id],
      );
    }
    final body = _lists(payload);
    final url = path.replaceAllMapped(RegExp(r'\{(\w+)\}'), (m) => '${body.remove(m.group(1))}');
    try {
      await (method == 'PATCH' ? api.patch(url, body: body) : api.post(url, body: body));
    } on ApiError catch (e) {
      if (!alreadyDone.contains(e.code)) rethrow;
    }
    await _deleteFiles(item);
    await db.raw.delete('outbox', where: 'id = ?', whereArgs: [item.id]);
  }

  /// Several files for one field are stored as "photos.0", "photos.1" (each uploaded and remembered on its own, so
  /// a retry resumes where it stopped) and sent as one list "photos", in their order.
  static Map<String, dynamic> _lists(Map<String, dynamic> payload) {
    final out = <String, dynamic>{};
    final lists = <String, Map<int, dynamic>>{};
    for (final e in payload.entries) {
      final m = RegExp(r'^(\w+)\.(\d+)$').firstMatch(e.key);
      if (m == null) {
        out[e.key] = e.value;
      } else {
        (lists[m.group(1)!] ??= {})[int.parse(m.group(2)!)] = e.value;
      }
    }
    for (final e in lists.entries) {
      out[e.key] = [for (final i in e.value.keys.toList()..sort()) e.value[i]];
    }
    return out;
  }

  Future<void> _deleteFiles(OutboxItem item) async {
    for (final path in item.files.values) {
      try {
        await File(path).delete();
      } on FileSystemException {
        // already gone
      }
    }
  }
}
