import '../core/api.dart';
import '../core/db.dart';

/// Points recorded by the phone, kept until the server acknowledged them. The server answers every batch with the
/// sequence numbers it stored and the ones it rejected (with a reason): both are done and leave the queue, so a
/// point is never lost and never sent twice, however often a batch is resent.
class PositionQueue {
  PositionQueue(this.db, {DateTime Function()? clock}) : _now = clock ?? DateTime.now;

  final AppDb db;
  final DateTime Function() _now;

  static const batchSize = 500; // the server's maximum per batch
  static const maxKept = 50000; // about two weeks of driving offline; the server refuses older points anyway

  Future<int> add({
    required DateTime recordedAt,
    required double lat,
    required double lng,
    double? accuracyM,
    double? speedKmh,
    int? heading,
    bool isMock = false,
  }) async {
    final seq = await db.raw.insert('positions', {
      'recorded_at': recordedAt.toUtc().toIso8601String(),
      'lat': lat,
      'lng': lng,
      'accuracy_m': accuracyM,
      'speed_kmh': speedKmh,
      'heading': heading,
      'is_mock': isMock ? 1 : 0,
    });
    if (seq % 1000 == 0) await _trim();
    return seq;
  }

  Future<int> size() async => (await db.raw.rawQuery('SELECT count(*) AS n FROM positions')).first['n'] as int;

  Future<void> _trim() => db.raw.rawDelete(
    'DELETE FROM positions WHERE seq NOT IN (SELECT seq FROM positions ORDER BY seq DESC LIMIT ?)',
    [maxKept],
  );

  /// Sends everything queued; returns how many points were acknowledged. Network errors propagate (the points
  /// stay queued for the next attempt).
  Future<int> upload(Api api) async {
    var done = 0;
    while (true) {
      final rows = await db.raw.query('positions', orderBy: 'seq', limit: batchSize);
      if (rows.isEmpty) break;
      final points = [
        for (final r in rows)
          {
            'seq': r['seq'],
            'recorded_at': r['recorded_at'],
            'lat': r['lat'],
            'lng': r['lng'],
            'accuracy_m': r['accuracy_m'],
            'speed_kmh': r['speed_kmh'],
            'heading': r['heading'],
            'is_mock': r['is_mock'] == 1,
          },
      ];
      final res = await api.post(
        '/driver/positions',
        body: {'sent_at': _now().toUtc().toIso8601String(), 'points': points},
      ) as Map<String, dynamic>;
      final acked = <int>{
        for (final s in res['stored_seqs'] as List) (s as num).toInt(),
        for (final r in res['rejected'] as List) ((r as Map)['seq'] as num).toInt(),
      };
      if (acked.isEmpty) break; // nothing acknowledged: never loop forever on the same batch
      await db.raw.delete(
        'positions',
        where: 'seq IN (${List.filled(acked.length, '?').join(',')})',
        whereArgs: acked.toList(),
      );
      done += acked.length;
      await db.put('last_upload_at', _now().toUtc().toIso8601String());
      if (rows.length < batchSize) break;
    }
    return done;
  }
}
