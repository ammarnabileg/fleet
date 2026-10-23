import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:fleet_driver/app/state.dart';
import 'package:fleet_driver/core/api.dart';
import 'package:fleet_driver/core/error_log.dart';
import 'package:fleet_driver/core/errors.dart';
import 'package:fleet_driver/core/outbox.dart';
import 'package:fleet_driver/tracking/positions.dart';
import 'package:fleet_driver/tracking/tracker.dart';
import 'package:fleet_driver/core/db.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'support.dart';

/// The architecture review's findings (R1-R3 and the sign-out leak), reproduced first and now asserting the fix.
Future<String> photo() async {
  final f = File('${(await Directory.systemTemp.createTemp('photo')).path}/odo.jpg');
  await f.writeAsBytes([1, 2, 3]);
  return f.path;
}

Tracker tracker(Api api, dynamic db, {FixStream? fixes}) => Tracker(
  db: db,
  api: api,
  fixes: fixes ?? (i) => const Stream<Fix>.empty(),
  health: ({required bool trackingRunning, required int queueSize, String? lastUploadAt}) async => {},
  heartbeatEvery: const Duration(hours: 1),
  syncEvery: const Duration(hours: 1),
);

AppState appState(dynamic db, Api api) => AppState(
  db: db,
  api: api,
  pollEvery: null,
  platform: PhoneHooks(
    permissionsOk: () async => true,
    startTracking: () async {},
    stopTracking: () async {},
    deviceMeta: () async => {'platform': 'android', 'model': 'Test phone', 'app_version': '0.1.0'},
  ),
);

void main() {
  group('R1: the outbox never blocks behind one item, never drops one', () {
    test('an item answering 500 waits with a growing, jittered delay; the items after it still go', () async {
      final (db, _, api, server) = await session();
      var now = DateTime.now();
      final box = Outbox(db, clock: () => now, random: math.Random(1));
      server.on('POST', '/api/v1/driver/files', (req) => (201, {'sha256': 'a' * 64}));
      server.on('POST', '/api/v1/driver/maintenance', (req) => (500, {'code': 'boom'}));
      server.on('POST', '/api/v1/driver/fuel', (req) => (201, {'id': 'f'}));
      await box.add('maintenance', {'client_ref': 'm', 'kind': 'x', 'description': 'd'}, {});
      await box.add(
        'fuel',
        {'client_ref': 'f', 'amount': '1.000', 'paid_at': '2026-10-04T06:00:00Z'},
        {'receipt_sha256': await photo()},
      );
      for (var i = 0; i < 5; i++) {
        await box.flush(api);
      }
      expect(server.calls('/api/v1/driver/fuel'), hasLength(1), reason: 'not held back by the failing one');
      expect(server.calls('/api/v1/driver/maintenance'), hasLength(1), reason: 'waits before its next try');
      final first = (await box.items()).single;
      expect((first.state, first.attempts), ('pending', 1));
      final wait = first.nextAt!.difference(now);
      expect(wait >= Outbox.backoffBase && wait <= Outbox.backoffBase * 1.5, isTrue, reason: '$wait');

      // each failure waits longer, never over the cap (plus its jitter)
      var last = wait;
      for (var i = 2; i < Outbox.maxServerFailures; i++) {
        now = (await box.items()).single.nextAt!.add(const Duration(seconds: 1));
        await box.flush(api);
        final item = (await box.items()).single;
        final next = item.nextAt!.difference(now);
        expect(item.attempts, i);
        expect(next <= Outbox.backoffCap * 1.5, isTrue);
        if (last < Outbox.backoffCap) expect(next > last * 0.7, isTrue);
        last = next;
      }
      // too many: parked for the driver, kept with its last error, no longer retried by itself
      now = (await box.items()).single.nextAt!.add(const Duration(seconds: 1));
      await box.flush(api);
      final parked = (await box.items()).single;
      expect((parked.state, parked.lastError, parked.needsAttention), ('parked', 'boom', true));
      expect(await box.waiting(), 0);
      final calls = server.calls('/api/v1/driver/maintenance').length;
      now = now.add(const Duration(hours: 5));
      await box.flush(api);
      expect(server.calls('/api/v1/driver/maintenance'), hasLength(calls));
      // the driver retries it: sent
      server.on('POST', '/api/v1/driver/maintenance', (req) => (201, {'id': 'm'}));
      expect(await box.retry(parked.id, api), SendResult.sent);
      expect(await box.items(), isEmpty);
    });

    test('a refusal (4xx) is final at once and does not hold back the rest', () async {
      final (db, _, api, server) = await session();
      final box = Outbox(db);
      server.on('POST', '/api/v1/driver/maintenance', (req) => (422, {'code': 'invalid_kind'}));
      server.on('POST', '/api/v1/driver/accidents', (req) => (201, {'id': 'a'}));
      await box.add('maintenance', {'client_ref': 'm', 'kind': 'x', 'description': 'd'}, {});
      await box.add('accident', {'client_ref': 'a'}, {});
      expect(await box.flush(api), 1);
      final left = (await box.items()).single;
      expect((left.state, left.lastError), ('failed', 'invalid_kind'));
    });

    test('a day keeps its order: a report waits behind its failing reading, other kinds do not', () async {
      final (db, _, api, server) = await session();
      final box = Outbox(db);
      server.on('POST', '/api/v1/driver/odometer', (req) => (503, {'code': 'busy'}));
      server.on('POST', '/api/v1/driver/reports', (req) => (201, {'id': 'r'}));
      server.on('POST', '/api/v1/driver/accidents', (req) => (201, {'id': 'a'}));
      await box.add('odometer', {'kind': 'end_day'}, {});
      await box.add('report', {'business_date': '2026-10-04'}, {});
      await box.add('accident', {'client_ref': 'a'}, {});
      await box.flush(api);
      expect(server.calls('/api/v1/driver/reports'), isEmpty);
      expect(server.calls('/api/v1/driver/accidents'), hasLength(1));
    });

    test('no network ends the round without counting against the item', () async {
      final (db, _, api, server) = await session();
      final box = Outbox(db);
      server.on('POST', '/api/v1/driver/maintenance', (req) => throw const SocketException('offline'));
      await box.add('maintenance', {'client_ref': 'm', 'kind': 'x', 'description': 'd'}, {});
      for (var i = 0; i < 20; i++) {
        await box.flush(api);
      }
      final item = (await box.items()).single;
      expect((item.state, item.attempts, item.nextAt), ('pending', 0, null));
    });

    test('47 hours old: parked as needing attention, never dropped; the driver may still send it', () async {
      final (db, _, api, server) = await session();
      final box = Outbox(db, clock: () => DateTime.now().add(const Duration(hours: 50)));
      await Outbox(db).add('report', {'business_date': '2026-10-04'}, {});
      await box.flush(api);
      final item = (await box.items()).single;
      expect((item.state, item.lastError, item.needsAttention), ('parked', 'too_old', true));
      expect(server.requests, isEmpty);
      server.on('POST', '/api/v1/driver/reports', (req) => (422, {'code': 'invalid_business_date'}));
      await expectLater(box.retry(item.id, api), throwsA(isA<ApiError>()));
      expect((await box.items()).single.state, 'failed', reason: "the server's answer, shown to him");
    });
  });

  test('R2: restarted offline during a custody, the tracker restores the decision and starts GPS', () async {
    final (db, _, api, server) = await session();
    server.on(
      'POST',
      '/api/v1/driver/status',
      (req) =>
          (200, {'tracking_required': true, 'interval_moving_s': 20, 'interval_stationary_s': 600, 'on_duty': true}),
    );
    final asked = <Duration>[];
    Stream<Fix> fixes(Duration i) {
      asked.add(i);
      return const Stream<Fix>.empty();
    }

    final t1 = tracker(api, db, fixes: fixes);
    await t1.start();
    await t1.stop();
    expect(asked, [const Duration(seconds: 20)]);
    server.routes.clear();
    server.on('POST', '/api/v1/driver/status', (req) => throw const SocketException('offline'));
    final t2 = tracker(api, db, fixes: fixes);
    await t2.start();
    expect(asked, [const Duration(seconds: 20), const Duration(seconds: 20)], reason: 'GPS on, last interval');
    expect(t2.required, isTrue);
    await t2.stop();
  });

  test('R3: a malformed heartbeat answer keeps the last decision and is logged, never thrown', () async {
    final (db, _, api, server) = await session();
    server.on('POST', '/api/v1/driver/status', (req) => (200, {'tracking_required': null}));
    final t = tracker(api, db);
    t.required = true;
    await t.heartbeat();
    expect(t.required, isTrue);
    final log = await ErrorLog(db).entries();
    expect(log.single['where'], 'tracker.heartbeat');
    expect(log.single['type'], 'FormatException');
    // the positions answer is malformed too: sync logs it, the points stay queued
    server.on('POST', '/api/v1/driver/positions', (req) => (200, {'stored_seqs': 'x'}));
    await PositionQueue(db).add(recordedAt: DateTime.now(), lat: 29.3, lng: 47.9);
    await t.sync();
    expect(await PositionQueue(db).size(), 1);
    expect((await ErrorLog(db).entries()).last['where'], 'tracker.sync');
    await t.stop();
  });

  test('the error log keeps no message (no driver data) and only the newest entries', () async {
    final db = await testDb();
    final log = ErrorLog(db);
    for (var i = 0; i < ErrorLog.keep + 5; i++) {
      await log.record('x$i', FormatException('plate 12345 of Ahmad'), StackTrace.current);
    }
    final all = await log.entries();
    expect(all, hasLength(ErrorLog.keep));
    expect(all.first['where'], 'x5');
    expect(jsonEncode(all), isNot(contains('Ahmad')));
  });

  group('P0-1: a signed-out driver leaves nothing for the next one', () {
    Future<void> leftovers(dynamic db) async {
      final box = Outbox(db);
      await box.add('maintenance', {'client_ref': 'm', 'kind': 'x', 'description': 'd'}, {'photos.0': await photo()});
      await PositionQueue(db).add(recordedAt: DateTime.now(), lat: 29.3, lng: 47.9);
      await db.put('tracking_state', jsonEncode({'required': true}));
      await db.put('fuel', '{}');
    }

    Future<void> expectClean(dynamic db) async {
      expect(await Outbox(db).items(), isEmpty);
      expect(await PositionQueue(db).size(), 0);
      expect(await db.get('tracking_state'), isNull);
      expect(await db.get('fuel'), isNull);
    }

    test('sign-out offline: queue, positions and his cached data are forgotten', () async {
      final (db, _, api, server) = await session();
      server.on('POST', '/api/v1/driver/files', (req) => throw const SocketException('offline'));
      server.on('POST', '/api/v1/driver/auth/logout', (req) => throw const SocketException('offline'));
      await leftovers(db);
      final files = (await Outbox(db).items()).single.files.values.toList();
      await db.put('lang', 'en');
      await appState(db, api).signOut();
      await expectClean(db);
      expect(File(files.single).existsSync(), isFalse, reason: 'his photos too');
      expect(await db.get('lang'), 'en', reason: "the phone's own settings stay");
    });

    test('session ended by the server: forgotten as well', () async {
      final (db, _, api, server) = await session();
      await leftovers(db);
      final s = appState(db, api);
      server.on('GET', '/api/v1/driver/onboarding', (req) => (401, {'code': 'device_revoked'}));
      server.on('POST', '/api/v1/driver/auth/refresh', (req) => (401, {'code': 'device_revoked'}));
      await s.refresh();
      for (var i = 0; i < 20 && (await Outbox(db).items()).isNotEmpty; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }
      expect(s.phase, Phase.signedOut);
      await expectClean(db);
    });

    test('a new sign-in starts clean even if something was left behind', () async {
      final (db, _, api, server) = await session();
      await leftovers(db);
      server.on('POST', '/api/v1/driver/auth/activate', (req) => (200, tokensJson('2')));
      final s = appState(db, api);
      await s.tokens.clear();
      await s.activate('t' * 43);
      expect(await Outbox(db).items(), isEmpty);
      expect(await PositionQueue(db).size(), 0);
    });

    test('the tracking service told the session ended forgets it too', () async {
      final (db, _, api, server) = await session();
      await leftovers(db);
      server.on('POST', '/api/v1/driver/status', (req) => (401, {'code': 'device_revoked'}));
      server.on('POST', '/api/v1/driver/auth/refresh', (req) => (401, {'code': 'device_revoked'}));
      var ended = false;
      final t = Tracker(
        db: db,
        api: api,
        fixes: (i) => const Stream<Fix>.empty(),
        health: ({required bool trackingRunning, required int queueSize, String? lastUploadAt}) async => {},
        onSessionEnded: () => ended = true,
      );
      await t.heartbeat();
      expect(ended, isTrue);
      await expectClean(db);
    });
  });

  test('a phone on the first database version keeps its queue and gains the retry time', () async {
    sqfliteFfiInit();
    final path = '${(await Directory.systemTemp.createTemp('v1')).path}/fleet.db';
    final old = await databaseFactoryFfiNoIsolate.openDatabase(
      path,
      options: OpenDatabaseOptions(
        version: 1,
        onCreate: (db, v) async {
          await db.execute('CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
          await db.execute(
            "CREATE TABLE outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, payload TEXT NOT NULL, "
            "files TEXT NOT NULL, created_at TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', claimed_at TEXT, "
            'attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT)',
          );
          await db.insert('outbox', {
            'kind': 'report',
            'payload': '{}',
            'files': '{}',
            'created_at': '2026-10-04T06:00:00Z',
          });
        },
      ),
    );
    await old.close();
    final db = await AppDb.open(factory: databaseFactoryFfiNoIsolate, path: path);
    final item = (await Outbox(db).items()).single;
    expect((item.kind, item.nextAt), ('report', null));
  });
}
