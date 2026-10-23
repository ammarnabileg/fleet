import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'api.dart';
import 'config.dart';
import 'db.dart';
import 'errors.dart';

/// What the driver did while the phone may be offline (an odometer reading, a daily report): stored with its
/// photo and original time, then sent in order. The server accepts readings up to 48 hours late with their real
/// time, so a lost connection never loses a reading.
class OutboxItem {
  OutboxItem(
    this.id,
    this.kind,
    this.payload,
    this.files,
    this.createdAt,
    this.state,
    this.attempts,
    this.lastError, [
    this.nextAt,
  ]);

  factory OutboxItem.fromRow(Map<String, Object?> r) => OutboxItem(
    r['id'] as int,
    r['kind'] as String,
    Map<String, dynamic>.from(jsonDecode(r['payload'] as String) as Map),
    Map<String, String>.from(jsonDecode(r['files'] as String) as Map),
    DateTime.parse(r['created_at'] as String),
    r['state'] as String,
    r['attempts'] as int,
    r['last_error'] as String?,
    r['next_at'] == null ? null : DateTime.parse(r['next_at'] as String),
  );

  final int id;
  final String kind; // odometer | report | report_edit | report_change | maintenance | accident | police_report | statement | fuel | objection | contact_ack | leave | leave_cancel
  final Map<String, dynamic> payload;
  final Map<String, String> files; // payload field -> local file still to upload
  final DateTime createdAt;

  /// pending | sending | failed (the server's final refusal) | parked (needs the driver: too old, or the server kept
  /// failing on it). Neither failed nor parked holds back the items after it.
  final String state;
  final int attempts;
  final String? lastError;

  /// Not tried again before this time (the wait grows after each server failure).
  final DateTime? nextAt;

  bool get needsAttention => state == 'parked';
}

enum SendResult { sent, queued }

class Outbox {
  Outbox(this.db, {DateTime Function()? clock, math.Random? random})
    : _now = clock ?? DateTime.now,
      _random = random ?? math.Random();

  final AppDb db;
  final DateTime Function() _now;
  final math.Random _random;

  /// After a server failure (5xx, 429, 408) an item waits before its next try: 30 s, doubling up to 30 minutes,
  /// each with up to half of it at random so phones do not retry in step. After [maxServerFailures] it is parked
  /// for the driver instead of retried forever. No network is not counted: it ends the round, nothing is tried.
  static const backoffBase = Duration(seconds: 30);
  static const backoffCap = Duration(minutes: 30);
  static const maxServerFailures = 10;

  /// Kinds whose order matters to the server: a day's readings and its report (a new start of day never overtakes
  /// the end before it, nor a report the reading it follows). Every other kind stands alone.
  static String _group(String kind) =>
      const {'odometer', 'report', 'report_edit', 'report_change'}.contains(kind) ? 'day' : kind;

  Duration backoff(int failures) {
    final n = math.max(0, math.min(failures - 1, 16));
    final base = backoffBase * math.pow(2, n).toInt();
    final capped = base > backoffCap ? backoffCap : base;
    return capped + capped * (_random.nextDouble() * 0.5);
  }

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
    // he collected the car from the center (a retry finds it collected already)
    'maintenance_pickup': ('/driver/maintenance/{request_id}/picked-up', 'camera', {'already_picked_up'}, 'POST'),
    // a renewed document for the office to check (a retry finds it already waiting)
    'renewal': ('/driver/documents/renewals', 'upload', {'renewal_exists'}, 'POST'),
    'accident': ('/driver/accidents', 'camera', {'accident_exists'}, 'POST'),
    // the office may have attached a report meanwhile: the accident has one, nothing more to send
    'police_report': ('/driver/accidents/{accident_id}/police-report', 'upload', {'police_report_exists'}, 'POST'),
    // the month's screenshots from the platform's app (from the gallery)
    'statement': ('/driver/statements', 'upload', {'statement_exists'}, 'POST'),
    // fuel he paid from his cash, with the receipt's camera photo (a resend is recognised by its client_ref)
    'fuel': ('/driver/fuel', 'camera', {'fuel_exists'}, 'POST'),
    // no car: the one he takes, registered for the office to approve (a resend is recognised by its client_ref)
    'vehicle_claim': ('/driver/vehicle-claims', 'camera', {'vehicle_claim_exists'}, 'POST'),
    // an objection to a payslip, with a photo from the camera or the gallery if any (a resend: its client_ref)
    'objection': ('/driver/payslips/{run_id}/objections', 'upload', {'objection_exists'}, 'POST'),
    // an absence request, with a certificate from the camera or the gallery if any (a resend: its client_ref)
    'leave': ('/driver/leaves', 'upload', {'leave_exists'}, 'POST'),
    // he withdraws a request still waiting (a resend finds it withdrawn)
    'leave_cancel': ('/driver/leaves/{leave_id}/cancel', 'upload', <String>{}, 'POST'),
    // «Done» on the office's contact request: the server answers the same to a resend (its client_ref)
    'contact_ack': ('/driver/contact-requests/{request_id}/ack', 'upload', <String>{}, 'POST'),
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
      (await db.raw.rawQuery("SELECT count(*) AS n FROM outbox WHERE state NOT IN ('failed', 'parked')")).first['n']
          as int;

  Future<void> discard(int id) async {
    final rows = await db.raw.query('outbox', where: 'id = ?', whereArgs: [id]);
    if (rows.isNotEmpty) await _deleteFiles(OutboxItem.fromRow(rows.first));
    await db.raw.delete('outbox', where: 'id = ?', whereArgs: [id]);
  }

  /// Sends one item now (right after the driver pressed send). A final refusal removes it and is thrown, so the
  /// driver can correct and send again; no network leaves it queued. Older items still waiting go first, in order:
  /// a new start of day never overtakes the end before it, nor a report the reading it follows.
  Future<SendResult> sendNow(int id, Api api) async {
    final older = await db.raw.rawQuery(
      "SELECT count(*) AS n FROM outbox WHERE id < ? AND state NOT IN ('failed', 'parked')",
      [id],
    );
    if ((older.first['n'] as int) > 0) {
      await flush(api);
      final rows = await db.raw.query('outbox', where: 'id = ?', whereArgs: [id]);
      if (rows.isEmpty) return SendResult.sent;
      final left = OutboxItem.fromRow(rows.first);
      if (left.state == 'failed' || left.state == 'parked') {
        await discard(id); // the server's final answer for this one: the driver sees it, as below
        throw ApiError(422, left.lastError ?? '');
      }
      return SendResult.queued; // still behind something the network holds back
    }
    final item = await _claim(id);
    if (item == null) return SendResult.queued;
    try {
      await _deliver(item, api);
      return SendResult.sent;
    } on ApiError catch (e) {
      if (e.isTransient) {
        await _retryLater(item, e);
        return SendResult.queued;
      }
      await discard(item.id);
      rethrow;
    } on SessionEnded {
      await _release(item, 'session_ended');
      rethrow;
    }
  }

  /// Sends everything waiting, oldest first. No network ends the round (nothing else would get through); an item
  /// the server keeps failing on waits its turn ([backoff]) and holds back only the items that must follow it (its
  /// [_group]), never the rest of the queue. One too old for the server is parked for the driver, never dropped.
  Future<int> flush(Api api) async {
    var sent = 0;
    final rows = await db.raw.query('outbox', where: "state NOT IN ('failed', 'parked')", orderBy: 'id');
    final held = <String>{}; // groups waiting behind an earlier item
    for (final r in rows) {
      final candidate = OutboxItem.fromRow(r);
      final group = _group(candidate.kind);
      if (held.contains(group)) continue;
      if (_now().difference(candidate.createdAt) > AppConfig.outboxMaxAge) {
        await _park(candidate.id, 'too_old');
        continue;
      }
      if (candidate.nextAt != null && _now().isBefore(candidate.nextAt!)) {
        held.add(group);
        continue;
      }
      final item = await _claim(candidate.id);
      if (item == null) {
        held.add(group); // the other engine is sending it: what follows it waits
        continue;
      }
      try {
        await _deliver(item, api);
        sent++;
      } on ApiError catch (e) {
        if (e.isNetwork) {
          await _release(item, e.code, count: false);
          break;
        }
        if (e.isTransient) {
          final parked = await _retryLater(item, e);
          if (!parked) held.add(group);
          continue;
        }
        await db.raw.update(
          'outbox',
          {'state': 'failed', 'last_error': e.code, 'claimed_at': null, 'next_at': null},
          where: 'id = ?',
          whereArgs: [item.id],
        );
      } on SessionEnded {
        await _release(item, 'session_ended', count: false);
        rethrow;
      }
    }
    return sent;
  }

  /// The driver asks to try a parked item again: one attempt now, whatever its age (the server decides). A final
  /// refusal marks it failed; no network or another server failure parks it again.
  Future<SendResult> retry(int id, Api api) async {
    final item = await _claim(id, parked: true);
    if (item == null) return SendResult.queued;
    try {
      await _deliver(item, api);
      return SendResult.sent;
    } on ApiError catch (e) {
      if (e.isTransient) {
        await _park(item.id, e.code, attempts: item.attempts + 1);
        return SendResult.queued;
      }
      await db.raw.update(
        'outbox',
        {'state': 'failed', 'last_error': e.code, 'claimed_at': null, 'next_at': null},
        where: 'id = ?',
        whereArgs: [item.id],
      );
      rethrow;
    } on SessionEnded {
      await _park(item.id, 'session_ended');
      rethrow;
    }
  }

  /// A server failure: wait longer before the next try, or park the item after too many. Returns whether parked.
  Future<bool> _retryLater(OutboxItem item, ApiError e) async {
    final failures = item.attempts + 1;
    if (!e.isNetwork && failures >= maxServerFailures) {
      await _park(item.id, e.code, attempts: failures);
      return true;
    }
    if (e.isNetwork) {
      await _release(item, e.code, count: false);
    } else {
      await _release(item, e.code, nextAt: _now().add(backoff(failures)));
    }
    return false;
  }

  Future<void> _park(int id, String error, {int? attempts}) => db.raw.update(
    'outbox',
    {'state': 'parked', 'last_error': error, 'claimed_at': null, 'next_at': null, 'attempts': ?attempts},
    where: 'id = ?',
    whereArgs: [id],
  );

  /// Takes an item for sending, unless the other engine is sending it right now.
  Future<OutboxItem?> _claim(int id, {bool parked = false}) {
    return db.exclusive((tx) async {
      final rows = await tx.query('outbox', where: 'id = ?', whereArgs: [id]);
      if (rows.isEmpty) return null;
      final item = OutboxItem.fromRow(rows.first);
      final claimed = rows.first['claimed_at'] as String?;
      if (item.state == 'failed' || (item.state == 'parked') != parked) return null;
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

  /// Back to waiting. [count]: a server failure that counts toward parking it (no network does not).
  Future<void> _release(OutboxItem item, String error, {bool count = true, DateTime? nextAt}) => db.raw.update(
    'outbox',
    {
      'state': 'pending',
      'claimed_at': null,
      'attempts': item.attempts + (count ? 1 : 0),
      'last_error': error,
      'next_at': nextAt?.toUtc().toIso8601String(),
    },
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
