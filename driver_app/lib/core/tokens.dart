import 'package:sqflite/sqflite.dart';

import 'db.dart';
import 'errors.dart';

typedef Refresher = Future<Map<String, dynamic>> Function(String refreshToken);

/// The device tokens. Refresh tokens rotate and the server treats a reused one as theft (the whole family is
/// revoked and the driver is logged out), so two engines must never refresh with the same token: the refresh
/// runs under the database lock and re-reads the tokens first, in case the other engine refreshed meanwhile.
class TokenStore {
  TokenStore(this.db, {DateTime Function()? clock}) : _now = clock ?? DateTime.now;

  final AppDb db;
  final DateTime Function() _now;

  static const _keys = ['access_token', 'access_expires_at', 'refresh_token', 'device_id'];
  static const _margin = Duration(seconds: 60);

  Future<bool> hasSession() async => await db.get('refresh_token') != null;

  Future<void> save(Map<String, dynamic> t, {DatabaseExecutor? tx}) async {
    final expires = _now().add(Duration(seconds: (t['expires_in'] as num).toInt()));
    await db.put('access_token', t['access_token'] as String, tx: tx);
    await db.put('access_expires_at', expires.toUtc().toIso8601String(), tx: tx);
    await db.put('refresh_token', t['refresh_token'] as String, tx: tx);
    await db.put('device_id', t['device_id'] as String?, tx: tx);
  }

  Future<void> clear({DatabaseExecutor? tx}) async {
    for (final k in _keys) {
      await db.put(k, null, tx: tx);
    }
  }

  Future<String?> _valid(DatabaseExecutor? tx, {String? notThis}) async {
    final access = await db.get('access_token', tx: tx);
    final exp = await db.get('access_expires_at', tx: tx);
    if (access == null || exp == null || access == notThis) return null;
    return DateTime.parse(exp).isAfter(_now().add(_margin)) ? access : null;
  }

  /// A valid access token, refreshed if needed. [stale]: the token the server just refused, so it is refreshed
  /// even if it looks valid. Returns null when there is no session. Throws [SessionEnded] when the server refuses
  /// the refresh token, [ApiError] (network) when the refresh could not be done now.
  Future<String?> access(Refresher refresh, {String? stale}) async {
    final fast = await _valid(null, notThis: stale);
    if (fast != null) return fast;
    var ended = false;
    final token = await db.exclusive((tx) async {
      final refreshToken = await db.get('refresh_token', tx: tx);
      if (refreshToken == null) return null;
      final again = await _valid(tx, notThis: stale); // the other engine may have refreshed while we waited
      if (again != null) return again;
      try {
        final t = await refresh(refreshToken);
        await save(t, tx: tx);
        return t['access_token'] as String;
      } on ApiError catch (e) {
        if (e.status != 401) rethrow;
        await clear(tx: tx); // committed: throwing here would roll the clear back
        ended = true;
        return null;
      }
    });
    if (ended) throw SessionEnded();
    return token;
  }
}
