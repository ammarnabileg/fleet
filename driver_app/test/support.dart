import 'dart:convert';
import 'dart:io';

import 'package:fleet_driver/core/api.dart';
import 'package:fleet_driver/core/db.dart';
import 'package:fleet_driver/core/tokens.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

/// A fresh database file per test, as on the phone (WAL, busy timeout), through FFI.
Future<AppDb> testDb([String? path]) async {
  sqfliteFfiInit();
  final dir = await Directory.systemTemp.createTemp('fleet_test');
  return AppDb.open(factory: databaseFactoryFfiNoIsolate, path: path ?? '${dir.path}/fleet.db');
}

/// A scripted backend: each route answers with a status and a JSON body; every request is recorded.
class FakeServer {
  final requests = <http.Request>[];
  final routes = <String, (int, Object?) Function(http.Request)>{};

  void on(String method, String path, (int, Object?) Function(http.Request) answer) => routes['$method $path'] = answer;

  late final client = MockClient((req) async {
    requests.add(req);
    final route = routes['${req.method} ${req.url.path}'];
    if (route == null) return http.Response(jsonEncode({'code': 'not_found'}), 404);
    final (status, body) = route(req);
    return http.Response(body == null ? '' : jsonEncode(body), status, headers: {'content-type': 'application/json'});
  });

  List<http.Request> calls(String path, {String? method}) => [
    for (final r in requests)
      if (r.url.path == path && (method == null || r.method == method)) r,
  ];
}

Map<String, dynamic> tokensJson(String n, {int expiresIn = 900}) => {
  'access_token': 'access-$n',
  'refresh_token': 'refresh-$n',
  'token_type': 'bearer',
  'expires_in': expiresIn,
  'device_id': 'dev-1',
};

Future<(AppDb, TokenStore, Api, FakeServer)> session({int expiresIn = 900}) async {
  final db = await testDb();
  final tokens = TokenStore(db);
  await tokens.save(tokensJson('1', expiresIn: expiresIn));
  final server = FakeServer();
  final api = Api(baseUrl: 'http://fleet.test', tokens: tokens, client: server.client);
  return (db, tokens, api, server);
}
