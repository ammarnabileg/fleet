import 'dart:convert';
import 'dart:io';

import 'package:fleet_driver/core/errors.dart';
import 'package:fleet_driver/core/outbox.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

Future<String> photo() async {
  final f = File('${(await Directory.systemTemp.createTemp('photo')).path}/odo.jpg');
  await f.writeAsBytes([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3]);
  return f.path;
}

Map<String, dynamic> reading() => {
  'kind': 'start_day',
  'value_km': 45210,
  'recorded_at': '2026-10-04T06:10:00Z',
  'lat': 29.3,
  'lng': 48.0,
};

void main() {
  test('a reading goes with its photo uploaded from the camera path, then leaves the outbox', () async {
    final (db, _, api, server) = await session();
    final box = Outbox(db);
    final file = await photo();
    server.on(
      'POST',
      '/api/v1/driver/files',
      (req) => (201, {'sha256': 'a' * 64, 'size_bytes': 7, 'content_type': 'image/jpeg'}),
    );
    server.on('POST', '/api/v1/driver/odometer', (req) => (201, {'id': 'r1'}));
    final id = await box.add('odometer', reading(), {'photo_sha256': file});
    expect(await box.sendNow(id, api), SendResult.sent);
    expect(server.calls('/api/v1/driver/files').single.url.queryParameters['source'], 'camera');
    final sent = jsonDecode(server.calls('/api/v1/driver/odometer').single.body) as Map;
    expect(sent['photo_sha256'], 'a' * 64);
    expect(sent['recorded_at'], '2026-10-04T06:10:00Z', reason: 'the original time, not the sending time');
    expect(await box.items(), isEmpty);
    expect(File(file).existsSync(), isFalse);
  });

  test('offline: queued, and the photo uploaded before the cut is not uploaded again', () async {
    final (db, _, api, server) = await session();
    final box = Outbox(db);
    server.on(
      'POST',
      '/api/v1/driver/files',
      (req) => (201, {'sha256': 'b' * 64, 'size_bytes': 7, 'content_type': 'image/jpeg'}),
    );
    var online = false;
    server.on('POST', '/api/v1/driver/odometer', (req) => online ? (201, {'id': 'r1'}) : throw ApiError(0, 'network'));
    final id = await box.add('odometer', reading(), {'photo_sha256': await photo()});
    expect(await box.sendNow(id, api), SendResult.queued);
    expect((await box.items()).single.state, 'pending');
    online = true;
    expect(await box.flush(api), 1);
    expect(server.calls('/api/v1/driver/files'), hasLength(1));
    expect(await box.items(), isEmpty);
  });

  test('an answer lost on the way: the retry is refused as "already recorded" and counts as sent', () async {
    final (db, _, api, server) = await session();
    final box = Outbox(db);
    server.on('POST', '/api/v1/driver/reports', (req) => (409, {'code': 'report_exists'}));
    await box.add('report', {'business_date': '2026-10-04', 'orders_count': 20, 'cash_amount': '15.000'}, {});
    expect(await box.flush(api), 1);
    expect(await box.items(), isEmpty);
  });

  test('a final refusal on send-now is removed and shown; in the background it is kept as failed', () async {
    final (db, _, api, server) = await session();
    final box = Outbox(db);
    server.on('POST', '/api/v1/driver/reports', (req) => (422, {'code': 'invalid_business_date'}));
    final id = await box.add('report', {'business_date': '2020-01-01'}, {});
    await expectLater(
      box.sendNow(id, api),
      throwsA(isA<ApiError>().having((e) => e.code, 'code', 'invalid_business_date')),
    );
    expect(await box.items(), isEmpty);
    await box.add('report', {'business_date': '2020-01-01'}, {});
    await box.flush(api);
    final kept = (await box.items()).single;
    expect((kept.state, kept.lastError), ('failed', 'invalid_business_date'));
  });

  test('flush keeps the order: it stops at the first network problem', () async {
    final (db, _, api, server) = await session();
    final box = Outbox(db);
    final order = <String>[];
    server.on('POST', '/api/v1/driver/reports', (req) {
      final day = jsonDecode(req.body)['business_date'] as String;
      order.add(day);
      if (day == '2026-10-03') throw ApiError(0, 'network');
      return (201, {'id': day});
    });
    for (final d in ['2026-10-02', '2026-10-03', '2026-10-04']) {
      await box.add('report', {'business_date': d}, {});
    }
    expect(await box.flush(api), 1);
    expect(order, ['2026-10-02', '2026-10-03']);
    expect(await box.waiting(), 2);
  });

  test('an item being sent by the other engine is not sent twice', () async {
    final (db, _, api, server) = await session();
    final box = Outbox(db);
    server.on('POST', '/api/v1/driver/reports', (req) => (201, {'id': 'x'}));
    final id = await box.add('report', {'business_date': '2026-10-04'}, {});
    await db.raw.update(
      'outbox',
      {'state': 'sending', 'claimed_at': DateTime.now().toUtc().toIso8601String()},
      where: 'id = ?',
      whereArgs: [id],
    );
    expect(await box.flush(api), 0);
    expect(server.calls('/api/v1/driver/reports'), isEmpty);
    // a claim older than the timeout (the other engine died mid-send) is taken over
    await db.raw.update(
      'outbox',
      {'claimed_at': DateTime.now().subtract(const Duration(minutes: 5)).toUtc().toIso8601String()},
      where: 'id = ?',
      whereArgs: [id],
    );
    expect(await box.flush(api), 1);
  });

  test('older than the server would accept: marked failed instead of retried forever', () async {
    final (db, _, api, server) = await session();
    final box = Outbox(db, clock: () => DateTime.now().add(const Duration(hours: 50)));
    await Outbox(db).add('report', {'business_date': '2026-10-04'}, {});
    await box.flush(api);
    expect((await box.items()).single.lastError, 'too_old');
    expect(server.requests, isEmpty);
  });
}
