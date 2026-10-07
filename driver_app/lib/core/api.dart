import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'errors.dart';
import 'tokens.dart';

/// The driver API (`/api/v1/driver/...`). Every call carries the device's access token; an expired or refused
/// token is refreshed once and the call repeated. [onSessionEnded] tells the app to go back to sign-in.
class Api {
  Api({required this.baseUrl, required this.tokens, http.Client? client, this.lang = 'ar', this.onSessionEnded})
    : _http = client ?? http.Client();

  final String baseUrl;
  final TokenStore tokens;
  final http.Client _http;
  String lang;
  void Function()? onSessionEnded;

  static const timeout = Duration(seconds: 30);

  Uri uri(String path, [Map<String, String>? query]) {
    final u = Uri.parse('$baseUrl/api/v1$path');
    return query == null || query.isEmpty ? u : u.replace(queryParameters: query);
  }

  Future<dynamic> get(String path, {Map<String, String>? query, bool auth = true}) =>
      _send('GET', path, query: query, auth: auth);

  Future<dynamic> post(String path, {Object? body, Map<String, String>? query, bool auth = true}) =>
      _send('POST', path, body: body ?? const {}, query: query, auth: auth);

  Future<dynamic> put(String path, {Object? body}) => _send('PUT', path, body: body ?? const {}, auth: true);

  Future<dynamic> patch(String path, {Object? body}) => _send('PATCH', path, body: body ?? const {}, auth: true);

  Future<dynamic> delete(String path) => _send('DELETE', path, auth: true);

  /// A public file's bytes, with no session (the splash image, shown before sign-in).
  Future<Uint8List> bytes(String path) async {
    final http.Response res;
    try {
      res = await _http.get(uri(path), headers: {'Accept-Language': lang}).timeout(timeout);
    } on SocketException {
      throw ApiError(0, 'network');
    } on TimeoutException {
      throw ApiError(0, 'network');
    } on http.ClientException {
      throw ApiError(0, 'network');
    }
    if (res.statusCode != 200) throw ApiError(res.statusCode, 'http_${res.statusCode}');
    return res.bodyBytes;
  }

  /// Uploads a file to /driver/files. [source] "camera" for photos taken in the app, "upload" for picked files.
  Future<Map<String, dynamic>> upload(String filePath, {String source = 'camera'}) async {
    final res = await _withAuth(true, (headers) async {
      final req = http.MultipartRequest('POST', uri('/driver/files', {'source': source}))
        ..headers.addAll(headers)
        ..files.add(await http.MultipartFile.fromPath('file', filePath));
      return http.Response.fromStream(await _http.send(req).timeout(timeout * 2));
    });
    return res as Map<String, dynamic>;
  }

  Future<dynamic> _send(String method, String path, {Object? body, Map<String, String>? query, required bool auth}) {
    return _withAuth(auth, (headers) {
      final req = http.Request(method, uri(path, query))..headers.addAll(headers);
      if (body != null) {
        req.headers['Content-Type'] = 'application/json';
        req.body = jsonEncode(body);
      }
      return _http.send(req).then(http.Response.fromStream).timeout(timeout);
    });
  }

  Future<dynamic> _withAuth(bool auth, Future<http.Response> Function(Map<String, String> headers) call) async {
    String? stale;
    for (var attempt = 0; attempt < 2; attempt++) {
      final headers = {'Accept': 'application/json', 'Accept-Language': lang};
      if (auth) {
        final token = await _token(stale);
        headers['Authorization'] = 'Bearer $token';
        stale = token;
      }
      final http.Response res;
      try {
        res = await call(headers);
      } on SocketException {
        throw ApiError(0, 'network');
      } on TimeoutException {
        throw ApiError(0, 'network');
      } on http.ClientException {
        throw ApiError(0, 'network');
      } on HandshakeException {
        throw ApiError(0, 'network');
      }
      if (res.statusCode == 401 && auth && attempt == 0) continue; // refresh once and repeat
      if (res.statusCode == 401 && auth) {
        await tokens.clear();
        onSessionEnded?.call();
        throw SessionEnded();
      }
      return _decode(res);
    }
    throw StateError('unreachable');
  }

  Future<String> _token(String? stale) async {
    try {
      final token = await tokens.access(_refresh, stale: stale);
      if (token == null) throw SessionEnded();
      return token;
    } on SessionEnded {
      onSessionEnded?.call();
      rethrow;
    }
  }

  Future<Map<String, dynamic>> _refresh(String refreshToken) async {
    final r = await _send('POST', '/driver/auth/refresh', body: {'refresh_token': refreshToken}, auth: false);
    return r as Map<String, dynamic>;
  }

  static dynamic _decode(http.Response res) {
    final text = utf8.decode(res.bodyBytes);
    dynamic data;
    if (text.isNotEmpty) {
      try {
        data = jsonDecode(text);
      } on FormatException {
        data = null;
      }
    }
    if (res.statusCode >= 200 && res.statusCode < 300) return data;
    final body = data is Map<String, dynamic> ? data : <String, dynamic>{};
    final params = body['params'] is Map<String, dynamic>
        ? body['params'] as Map<String, dynamic>
        : <String, dynamic>{};
    throw ApiError(res.statusCode, (body['code'] as String?) ?? 'http_${res.statusCode}', params: params, body: body);
  }
}
