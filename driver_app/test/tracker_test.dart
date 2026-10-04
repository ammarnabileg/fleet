import 'dart:async';
import 'dart:convert';

import 'package:fleet_driver/core/errors.dart';
import 'package:fleet_driver/tracking/tracker.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  late StreamController<Fix> gps;
  late List<Duration> asked;

  Future<(Tracker, FakeServer)> make({bool required = true}) async {
    final (db, _, api, server) = await session();
    gps = StreamController<Fix>.broadcast();
    asked = [];
    server.on(
      'POST',
      '/api/v1/driver/status',
      (req) => (
        200,
        {
          'server_time': '2026-10-04T09:00:00Z',
          'tracking_required': required,
          'interval_moving_s': 30,
          'interval_stationary_s': 300,
        },
      ),
    );
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
      heartbeatEvery: const Duration(hours: 1),
      syncEvery: const Duration(hours: 1),
    );
    return (t, server);
  }

  Fix fix(DateTime at, {double speed = 40, bool mock = false}) =>
      Fix(at: at, lat: 29.3, lng: 48.0, speedKmh: speed, isMock: mock);

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
    }
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(await t.queue.size(), 3, reason: 'the fix 5 s after the first is dropped');
    await t.sync();
    final sent = [for (final r in server.calls('/api/v1/driver/positions')) ...jsonDecode(r.body)['points'] as List];
    expect([for (final p in sent) p['is_mock']], [false, false, true]);
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
}
