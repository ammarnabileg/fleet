import 'dart:async';
import 'dart:convert';

import 'package:fleet_driver/core/errors.dart';
import 'package:fleet_driver/tracking/tracker.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  late StreamController<Fix> gps;
  late List<Duration> asked;
  late List<(Map<String, dynamic>?, bool)> shown;
  late Map<String, dynamic> status; // what the server answers to the heartbeat; a test may change it

  Future<(Tracker, FakeServer)> make({bool required = true}) async {
    final (db, _, api, server) = await session();
    gps = StreamController<Fix>.broadcast();
    asked = [];
    shown = [];
    status = {
      'server_time': '2026-10-04T09:00:00Z',
      'tracking_required': required,
      'interval_moving_s': 30,
      'interval_stationary_s': 300,
      'on_duty': false,
      'company': {'ar': 'شركة المثال', 'en': 'Example Co'},
    };
    server.on('POST', '/api/v1/driver/status', (req) => (200, status));
    server.on('POST', '/api/v1/driver/positions', (req) {
      final pts = jsonDecode(req.body)['points'] as List;
      return (
        200,
        {
          'stored_seqs': [for (final p in pts) p['seq']],
          'rejected': [],
          'server_time': '2026-10-04T09:00:00Z',
        },
      );
    });
    final t = Tracker(
      db: db,
      api: api,
      fixes: (interval) {
        asked.add(interval);
        return gps.stream;
      },
      health: ({required bool trackingRunning, required int queueSize, String? lastUploadAt}) async => {
        'tracking_service_running': trackingRunning,
        'queue_size': queueSize,
        'location_permission': 'always',
        'gps_enabled': true,
      },
      notify: (company, working) => shown.add((company, working)),
      heartbeatEvery: const Duration(hours: 1),
      syncEvery: const Duration(hours: 1),
    );
    return (t, server);
  }

  Fix fix(DateTime at, {double? speed = 40, bool mock = false, double lat = 29.3, double accuracy = 10}) =>
      Fix(at: at, lat: lat, lng: 48.0, accuracyM: accuracy, speedKmh: speed, isMock: mock);
  List sentPoints(FakeServer server) => [
    for (final r in server.calls('/api/v1/driver/positions')) ...jsonDecode(r.body)['points'] as List,
  ];
  Future<void> settle() => Future<void>.delayed(const Duration(milliseconds: 60));

  test('tracks only when the server says there is a custody, at the server interval', () async {
    final (t, server) = await make(required: false);
    await t.start();
    expect(asked, isEmpty);
    final (t2, _) = await make(required: true);
    await t2.start();
    expect(asked, [const Duration(seconds: 30)]);
    expect(jsonDecode(server.calls('/api/v1/driver/status').single.body)['location_permission'], 'always');
    await t.stop();
    await t2.stop();
  });

  test('one point per interval, sent and acknowledged; a fake location is sent for the server to reject', () async {
    final (t, server) = await make();
    await t.start();
    final t0 = DateTime.utc(2026, 10, 4, 9);
    for (final s in [0, 5, 31, 62]) {
      gps.add(fix(t0.add(Duration(seconds: s)), mock: s == 62));
      await settle();
    }
    // each kept point goes at once, without waiting for the sync timer; the fix 5 s after the first is dropped
    expect([for (final p in sentPoints(server)) p['is_mock']], [false, false, true]);
    expect(await t.queue.size(), 0);
    await t.stop();
  });

  test('parked for two minutes: fewer fixes; moving again: back to the moving interval', () async {
    final (t, _) = await make();
    await t.start();
    final t0 = DateTime.utc(2026, 10, 4, 9);
    for (var s = 0; s <= 150; s += 30) {
      gps.add(fix(t0.add(Duration(seconds: s)), speed: 0));
    }
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(asked.last, const Duration(seconds: 300));
    gps.add(fix(t0.add(const Duration(seconds: 500)), speed: 35));
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(asked.last, const Duration(seconds: 30));
    await t.stop();
  });

  test('offline: the last decision holds and the points wait', () async {
    final (t, server) = await make();
    await t.start();
    server.on('POST', '/api/v1/driver/status', (req) => throw ApiError(0, 'network'));
    server.on('POST', '/api/v1/driver/positions', (req) => throw ApiError(0, 'network'));
    await t.heartbeat();
    expect(t.required, isTrue, reason: 'a custody does not end because the network did');
    gps.add(fix(DateTime.utc(2026, 10, 4, 10)));
    await Future<void>.delayed(const Duration(milliseconds: 50));
    await t.sync();
    expect(await t.queue.size(), 1);
    final state = jsonDecode((await t.db.get('tracking_state'))!) as Map;
    expect((state['required'], state['queue']), (true, 1));
    await t.stop();
  });

  test('a phone that measures no speed: worked out from the distance, never a fake 0 while moving', () async {
    final (t, server) = await make();
    await t.start();
    final t0 = DateTime.utc(2026, 10, 4, 9);
    // 0.0027 degrees of latitude is about 300 m: 300 m in 30 s is 36 km/h
    for (var i = 0; i < 4; i++) {
      gps.add(fix(t0.add(Duration(seconds: 30 * i)), speed: null, lat: 29.3 + 0.0027 * i));
      await settle();
    }
    final speeds = [for (final p in sentPoints(server)) p['speed_kmh'] as num?];
    expect(speeds.first, isNull, reason: 'the first fix has nothing to compare with');
    for (final v in speeds.skip(1)) {
      expect(v, closeTo(36, 1));
    }
    expect(asked, [const Duration(seconds: 30)], reason: 'moving: it never parked');
    await t.stop();
  });

  test('positions within their accuracy are a stop, and an approximate position or a jump gives no speed', () async {
    final (t, server) = await make();
    await t.start();
    final t0 = DateTime.utc(2026, 10, 4, 9);
    gps.add(fix(t0, speed: null));
    await settle();
    gps.add(fix(t0.add(const Duration(seconds: 30)), speed: null, lat: 29.3 + 0.00005)); // 5 m: wifi jitter
    await settle();
    gps.add(fix(t0.add(const Duration(seconds: 60)), speed: null, lat: 29.31, accuracy: 500)); // approximate
    await settle();
    gps.add(fix(t0.add(const Duration(seconds: 90)), speed: null, lat: 30.3)); // 110 km in 30 s
    await settle();
    expect([for (final p in sentPoints(server)) p['speed_kmh']], [null, 0, null, null]);
    await t.stop();
  });

  test(
    'parked with a long interval: a clear move away wakes it, though the gap is too long to work out a speed',
    () async {
      final (t, _) = await make();
      status = {...status, 'interval_stationary_s': 900};
      await t.start();
      final t0 = DateTime.utc(2026, 10, 4, 9);
      for (var s = 0; s <= 150; s += 30) {
        gps.add(fix(t0.add(Duration(seconds: s)), speed: 0));
        await settle();
      }
      expect(asked.last, const Duration(seconds: 900));
      // fifteen minutes later, 3 km away, the phone measured no speed
      gps.add(fix(t0.add(const Duration(seconds: 1050)), speed: null, lat: 29.327));
      await settle();
      expect(asked.last, const Duration(seconds: 30));
      await t.stop();
    },
  );

  test('a fix of unknown speed breaks the still streak: parking needs two minutes known still', () async {
    final (t, _) = await make();
    await t.start();
    final t0 = DateTime.utc(2026, 10, 4, 9);
    gps.add(fix(t0, speed: 0));
    await settle();
    gps.add(fix(t0.add(const Duration(seconds: 30)), speed: null, accuracy: 500)); // no speed, approximate
    await settle();
    gps.add(fix(t0.add(const Duration(seconds: 150)), speed: 0)); // 150 s after the first, 0 s after the break
    await settle();
    expect(asked, [const Duration(seconds: 30)], reason: 'not parked: the streak restarted');
    await t.stop();
  });

  test('a few metres in a few seconds is not a stop: no speed rather than a fake 0', () async {
    final (t, server) = await make();
    status = {...status, 'interval_moving_s': 5};
    await t.start();
    final t0 = DateTime.utc(2026, 10, 4, 9);
    gps.add(fix(t0, speed: null));
    await settle();
    gps.add(fix(t0.add(const Duration(seconds: 5)), speed: null, lat: 29.3 + 0.0001)); // 11 m in 5 s: 8 km/h crawl
    await settle();
    expect([for (final p in sentPoints(server)) p['speed_kmh']], [null, null]);
    await t.stop();
  });

  test('the driver changes the language: the notification is shown again in it', () async {
    final (t, _) = await make();
    await t.start();
    expect(shown, hasLength(1));
    t.api.lang = 'en';
    await t.heartbeat();
    expect(shown, hasLength(2));
    await t.stop();
  });

  test('a change in the settings reaches the running tracker at the next heartbeat', () async {
    final (t, _) = await make();
    await t.start();
    expect(asked, [const Duration(seconds: 30)]);
    status = {...status, 'interval_moving_s': 10};
    await t.heartbeat();
    expect(asked.last, const Duration(seconds: 10));
    final t0 = DateTime.utc(2026, 10, 4, 9);
    for (var s = 0; s <= 150; s += 10) {
      gps.add(fix(t0.add(Duration(seconds: s)), speed: 0));
      await settle();
    }
    expect(asked.last, const Duration(seconds: 300), reason: 'parked');
    status = {...status, 'interval_stationary_s': 120};
    await t.heartbeat();
    expect(asked.last, const Duration(seconds: 120), reason: 'still parked, at the new parked interval');
    gps.add(fix(t0.add(const Duration(seconds: 400)), speed: 35));
    await settle();
    expect(asked.last, const Duration(seconds: 10), reason: 'moving again, at the new moving interval');
    await t.stop();
  });

  test('equal intervals do not restart the GPS on every fix', () async {
    final (t, _) = await make();
    status = {...status, 'interval_stationary_s': 30};
    await t.start();
    final t0 = DateTime.utc(2026, 10, 4, 9);
    for (var s = 0; s <= 300; s += 30) {
      gps.add(fix(t0.add(Duration(seconds: s)), speed: 0));
      await settle();
    }
    expect(asked, [const Duration(seconds: 30)]);
    await t.stop();
  });

  test('the notification shows the company and whether the driver is at work, only when that changes', () async {
    final (t, _) = await make();
    await t.start();
    expect(shown.single.$2, isFalse);
    expect(shown.single.$1, {'ar': 'شركة المثال', 'en': 'Example Co'});
    await t.sync();
    await t.heartbeat();
    expect(shown, hasLength(1), reason: 'nothing changed: not posted again every minute');
    status = {...status, 'on_duty': true};
    await t.heartbeat();
    expect(shown.last.$2, isTrue);
    final state = jsonDecode((await t.db.get('tracking_state'))!) as Map;
    expect((state['on_duty'], (state['company'] as Map)['en']), (true, 'Example Co'));
    await t.stop();
  });

  test('an older server without the work status: not at work, nothing breaks', () async {
    final (t, _) = await make();
    status = {...status}
      ..remove('on_duty')
      ..remove('company');
    await t.start();
    expect(shown, [(null, false)]);
    await t.stop();
  });
}
