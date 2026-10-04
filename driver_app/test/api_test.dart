import 'dart:convert';

import 'package:fleet_driver/core/errors.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

void main() {
  test('a refused access token is refreshed once and the call repeated with the new one', () async {
    final (_, _, api, server) = await session();
    var first = true;
    server.on('GET', '/api/v1/driver/today', (req) {
      if (first) {
        first = false;
        return (401, {'code': 'device_not_authenticated'});
      }
      return (200, {'custody': null, 'start_day_done': false});
    });
    server.on('POST', '/api/v1/driver/auth/refresh', (req) => (200, tokensJson('2')));
    expect(await api.get('/driver/today'), {'custody': null, 'start_day_done': false});
    final auths = [for (final r in server.calls('/api/v1/driver/today')) r.headers['Authorization']];
    expect(auths, ['Bearer access-1', 'Bearer access-2']);
    expect(jsonDecode(server.calls('/api/v1/driver/auth/refresh').single.body), {'refresh_token': 'refresh-1'});
  });

  test('a phone the server no longer knows ends the session and tells the app', () async {
    final (_, tokens, api, server) = await session();
    var ended = 0;
    api.onSessionEnded = () => ended++;
    server.on('GET', '/api/v1/driver/today', (req) => (401, {'code': 'device_not_authenticated'}));
    server.on('POST', '/api/v1/driver/auth/refresh', (req) => (401, {'code': 'device_not_authenticated'}));
    await expectLater(api.get('/driver/today'), throwsA(isA<SessionEnded>()));
    expect(ended, greaterThan(0));
    expect(await tokens.hasSession(), isFalse);
  });

  test('problem+json becomes a code with its params; the UI language goes with every call', () async {
    final (_, _, api, server) = await session();
    api.lang = 'en';
    server.on(
      'POST',
      '/api/v1/driver/reports',
      (req) => (
        422,
        {
          'code': 'field_required',
          'params': {'field': 'orders_count'},
        },
      ),
    );
    try {
      await api.post('/driver/reports', body: {'business_date': '2026-10-04'});
      fail('expected an error');
    } on ApiError catch (e) {
      expect((e.status, e.code), (422, 'field_required'));
      expect(e.params, {'field': 'orders_count'});
      expect(e.isTransient, isFalse);
    }
    expect(server.requests.last.headers['Accept-Language'], 'en');
  });

  test('server trouble is transient, a refusal is final', () {
    expect(ApiError(0, 'network').isTransient, isTrue);
    expect(ApiError(503, 'http_503').isTransient, isTrue);
    expect(ApiError(409, 'reading_exists').isTransient, isFalse);
  });
}
