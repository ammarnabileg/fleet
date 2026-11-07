import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:fleet_driver/core/db.dart';
import 'package:fleet_driver/core/errors.dart';
import 'package:fleet_driver/core/tokens.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'support.dart';

/// One engine (the app or the tracking service): its own database connection, asks for an access token.
Future<String?> _engine((String, String) args) async {
  final (path, url) = args;
  sqfliteFfiInit();
  final db = await AppDb.open(factory: databaseFactoryFfiNoIsolate, path: path);
  final store = TokenStore(db);
  final token = await store.access((refresh) async {
    final r = await http.post(Uri.parse(url), body: jsonEncode({'refresh_token': refresh}));
    return jsonDecode(r.body) as Map<String, dynamic>;
  });
  await db.close();
  return token;
}

void main() {
  test('two engines needing a token at the same time refresh once, with the same token, and agree', () async {
    final dir = await Directory.systemTemp.createTemp('fleet_lock');
    final path = '${dir.path}/fleet.db';
    final db = await testDb(path);
    await TokenStore(db).save(tokensJson('1', expiresIn: 30)); // inside the refresh margin: both must refresh
    await db.close();

    var refreshes = 0;
    final seen = <String>[];
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((req) async {
      final body = jsonDecode(await utf8.decoder.bind(req).join()) as Map;
      seen.add(body['refresh_token'] as String);
      refreshes++;
      await Future<void>.delayed(const Duration(milliseconds: 300)); // a slow network while holding the lock
      req.response.write(jsonEncode(tokensJson('$refreshes')));
      await req.response.close();
    });
    final url = 'http://127.0.0.1:${server.port}/refresh';
    final results = await Future.wait([
      Isolate.run(() => _engine((path, url))),
      Isolate.run(() => _engine((path, url))),
    ]);
    await server.close();
    expect(refreshes, 1, reason: 'a second refresh with the same token is taken for theft and logs the driver out');
    expect(seen, ['refresh-1']);
    expect(results, ['access-1', 'access-1']);
  });

  test('a refused refresh ends the session and the clear is committed', () async {
    final db = await testDb();
    final store = TokenStore(db);
    await store.save(tokensJson('1', expiresIn: 10));
    await expectLater(store.access((_) async => throw ApiError(401, 'token_reused')), throwsA(isA<SessionEnded>()));
    expect(await store.hasSession(), isFalse);
    expect(await db.get('access_token'), isNull);
  });

  test('no network during a refresh keeps the tokens for the next try', () async {
    final db = await testDb();
    final store = TokenStore(db);
    await store.save(tokensJson('1', expiresIn: 10));
    await expectLater(store.access((_) async => throw ApiError(0, 'network')), throwsA(isA<ApiError>()));
    expect(await db.get('refresh_token'), 'refresh-1');
  });

  test('a valid token is used without refreshing; a refused one is refreshed even if it looks valid', () async {
    final db = await testDb();
    final store = TokenStore(db);
    await store.save(tokensJson('1'));
    var calls = 0;
    Future<Map<String, dynamic>> refresh(String r) async => tokensJson('${++calls + 1}');
    expect(await store.access(refresh), 'access-1');
    expect(calls, 0);
    expect(await store.access(refresh, stale: 'access-1'), 'access-2');
    expect(calls, 1);
  });
}
