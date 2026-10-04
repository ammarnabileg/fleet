import 'dart:convert';

import 'package:fleet_driver/core/errors.dart';
import 'package:fleet_driver/tracking/positions.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  test('acknowledged points (stored or rejected) leave the queue; sequence numbers are never reused', () async {
    final (db, _, api, server) = await session();
    final q = PositionQueue(db);
    final t = DateTime.utc(2026, 10, 4, 9);
    for (var i = 0; i < 3; i++) {
      await q.add(recordedAt: t.add(Duration(seconds: 30 * i)), lat: 29.3, lng: 48.0, speedKmh: 40);
    }
    server.on('POST', '/api/v1/driver/positions', (req) {
      final seqs = [for (final p in jsonDecode(req.body)['points'] as List) p['seq']];
      return (
        200,
        {
          'stored_seqs': seqs.sublist(0, 2),
          'rejected': [
            {'seq': seqs[2], 'reason': 'no_custody'},
          ],
          'server_time': t.toIso8601String(),
        },
      );
    });
    expect(await q.upload(api), 3);
    expect(await q.size(), 0);
    final next = await q.add(recordedAt: t, lat: 29.3, lng: 48.0);
    expect(next, 4, reason: 'the server keeps (device, seq) unique: a reused number would be dropped as a duplicate');
    expect(await db.get('last_upload_at'), isNotNull);
  });

  test('no network keeps every point for the next try', () async {
    final (db, _, api, server) = await session();
    final q = PositionQueue(db);
    await q.add(recordedAt: DateTime.utc(2026), lat: 1, lng: 1, isMock: true);
    server.on('POST', '/api/v1/driver/positions', (req) => throw ApiError(0, 'network'));
    await expectLater(q.upload(api), throwsA(isA<ApiError>()));
    expect(await q.size(), 1);
  });

  test('a big backlog goes in batches of the server maximum', () async {
    final (db, _, api, server) = await session();
    final q = PositionQueue(db);
    final t = DateTime.utc(2026, 10, 4);
    await db.raw.transaction((tx) async {
      for (var i = 0; i < 1200; i++) {
        await tx.insert('positions', {'recorded_at': t.toIso8601String(), 'lat': 1.0, 'lng': 1.0, 'is_mock': 0});
      }
    });
    final sizes = <int>[];
    server.on('POST', '/api/v1/driver/positions', (req) {
      final pts = jsonDecode(req.body)['points'] as List;
      sizes.add(pts.length);
      return (
        200,
        {
          'stored_seqs': [for (final p in pts) p['seq']],
          'rejected': [],
          'server_time': t.toIso8601String(),
        },
      );
    });
    expect(await q.upload(api), 1200);
    expect(sizes, [500, 500, 200]);
  });
}
