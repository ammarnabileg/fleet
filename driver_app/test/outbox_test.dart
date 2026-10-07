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

  test('an accident: its photos from the camera, its police report from the phone files', () async {
    final (db, _, api, server) = await session();
    final box = Outbox(db);
    var n = 0;
    server.on('POST', '/api/v1/driver/files', (req) {
      n++;
      return (201, {'sha256': '$n' * 64, 'size_bytes': 7, 'content_type': 'image/jpeg'});
    });
    server.on('POST', '/api/v1/driver/accidents', (req) => (201, {'id': 'a1'}));
    final id = await box.add(
      'accident',
      {'client_ref': 'x1', 'description': 'صدمة'},
      {'photos.0': await photo(), 'police_report': await photo()},
    );
    expect(await box.sendNow(id, api), SendResult.sent);
    final sources = {for (final c in server.calls('/api/v1/driver/files')) c.url.queryParameters['source']};
    expect(sources, {'camera', 'upload'});
    final sent = jsonDecode(server.calls('/api/v1/driver/accidents').single.body) as Map;
    expect(sent['photos'], ['1' * 64]);
    expect(sent['police_report'], '2' * 64);
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

  test('a maintenance request sends its photos as one list, in order; a retry resumes and is recognised', () async {
    final (db, _, api, server) = await session();
    final box = Outbox(db);
    var n = 0, failSecond = true;
    server.on('POST', '/api/v1/driver/files', (req) {
      n++;
      if (n == 2 && failSecond) {
        failSecond = false;
        throw ApiError(0, 'network');
      }
      return (201, {'sha256': '$n' * 64, 'size_bytes': 7, 'content_type': 'image/jpeg'});
    });
    var posts = 0;
    server.on('POST', '/api/v1/driver/maintenance', (req) {
      posts++;
      return posts == 1 ? throw ApiError(0, 'network') : (409, {'code': 'request_exists'});
    });
    final payload = {'client_ref': 'ref-1', 'kind': 'tyres', 'description': 'Flat tyre', 'odometer_km': null};
    final id = await box.add('maintenance', payload, {'photos.0': await photo(), 'photos.1': await photo()});
    expect(await box.sendNow(id, api), SendResult.queued); // the second photo failed
    expect(await box.flush(api), 0); // both uploaded now, the request itself lost on the way
    expect(await box.flush(api), 1, reason: 'the server already has it: request_exists counts as sent');
    expect(server.calls('/api/v1/driver/files'), hasLength(3), reason: 'the first photo was not uploaded twice');
    final bodies = [for (final r in server.calls('/api/v1/driver/maintenance')) jsonDecode(r.body) as Map];
    expect(bodies.last['photos'], ['1' * 64, '3' * 64]);
    expect(bodies.last['client_ref'], 'ref-1', reason: 'the same id on every try');
    expect(bodies.last.keys.where((k) => k.toString().contains('.')), isEmpty);
    expect(await box.items(), isEmpty);
  });

  test('a police report goes to its accident; one attached by the office meanwhile counts as done', () async {
    final (db, _, api, server) = await session();
    final box = Outbox(db);
    server.on(
      'POST',
      '/api/v1/driver/files',
      (req) => (201, {'sha256': 'a' * 64, 'size_bytes': 7, 'content_type': 'image/jpeg'}),
    );
    server.on('POST', '/api/v1/driver/accidents/acc-7/police-report', (req) => (409, {'code': 'police_report_exists'}));
    final id = await box.add(
      'police_report',
      {'accident_id': 'acc-7', 'number': 'PR-1'},
      {'file_sha256': await photo()},
    );
    expect(await box.sendNow(id, api), SendResult.sent);
    final body = jsonDecode(server.calls('/api/v1/driver/accidents/acc-7/police-report').single.body) as Map;
    expect(body, {'number': 'PR-1', 'file_sha256': 'a' * 64}, reason: 'the accident id is in the path, not the body');
    expect(await box.items(), isEmpty);
  });

  test('an accident report: photos as one list, the police report as its own field, a retry recognised', () async {
    final (db, _, api, server) = await session();
    final box = Outbox(db);
    var n = 0;
    server.on(
      'POST',
      '/api/v1/driver/files',
      (req) => (201, {'sha256': '${++n}' * 64, 'size_bytes': 7, 'content_type': 'image/jpeg'}),
    );
    var posts = 0;
    server.on('POST', '/api/v1/driver/accidents', (req) {
      posts++;
      return posts == 1 ? throw ApiError(0, 'network') : (409, {'code': 'accident_exists'});
    });
    final id = await box.add(
      'accident',
      {
        'client_ref': 'ref-9',
        'occurred_at': '2026-10-04T06:00:00.000Z',
        'description': 'Rear-ended',
        'injuries': false,
      },
      {'photos.0': await photo(), 'photos.1': await photo(), 'photos.2': await photo(), 'police_report': await photo()},
    );
    expect(await box.sendNow(id, api), SendResult.queued);
    expect(await box.flush(api), 1);
    final body = jsonDecode(server.calls('/api/v1/driver/accidents').last.body) as Map;
    expect(body['photos'], ['1' * 64, '2' * 64, '3' * 64]);
    expect(body['police_report'], '4' * 64);
    expect(body['occurred_at'], '2026-10-04T06:00:00.000Z', reason: 'the time of the accident, not of the sending');
    expect(server.calls('/api/v1/driver/files'), hasLength(4));
  });
}
