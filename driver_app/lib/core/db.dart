import 'dart:async';

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

/// One SQLite file shared by the UI and the background tracking service. They run in two Flutter engines of the
/// same process, so anything both of them change (the tokens above all) goes through [exclusive], a real database
/// lock, never through memory.
class AppDb {
  AppDb._(this.raw);

  final Database raw;
  static const fileName = 'fleet.db';

  static Future<AppDb> open({DatabaseFactory? factory, String? path}) async {
    final f = factory ?? databaseFactory;
    final location = path ?? p.join(await f.getDatabasesPath(), fileName);
    final db = await f.openDatabase(
      location,
      options: OpenDatabaseOptions(version: 1, onConfigure: _configure, onCreate: _create),
    );
    return AppDb._(db);
  }

  static Future<void> _configure(Database db) async {
    await db.rawQuery('PRAGMA journal_mode=WAL');
    await db.rawQuery('PRAGMA busy_timeout=8000');
  }

  static Future<void> _create(Database db, int version) async {
    await db.execute('CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)');
    // AUTOINCREMENT: a sequence number is never reused, even after the acknowledged points are deleted. The
    // server keeps (device, seq) unique, so a reused number would be dropped as a duplicate.
    await db.execute('''
      CREATE TABLE positions (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        recorded_at TEXT NOT NULL,
        lat REAL NOT NULL,
        lng REAL NOT NULL,
        accuracy_m REAL,
        speed_kmh REAL,
        heading INTEGER,
        is_mock INTEGER NOT NULL DEFAULT 0
      )''');
    await db.execute('''
      CREATE TABLE outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        payload TEXT NOT NULL,
        files TEXT NOT NULL,
        created_at TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending',
        claimed_at TEXT,
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT
      )''');
  }

  Future<String?> get(String key, {DatabaseExecutor? tx}) async {
    final rows = await (tx ?? raw).query('kv', columns: ['value'], where: 'key = ?', whereArgs: [key]);
    return rows.isEmpty ? null : rows.first['value'] as String;
  }

  Future<void> put(String key, String? value, {DatabaseExecutor? tx}) async {
    final ex = tx ?? raw;
    if (value == null) {
      await ex.delete('kv', where: 'key = ?', whereArgs: [key]);
    } else {
      await ex.insert('kv', {'key': key, 'value': value}, conflictAlgorithm: ConflictAlgorithm.replace);
    }
  }

  /// Runs [fn] holding the database's write lock (BEGIN EXCLUSIVE), across both engines. A lock held by the other
  /// engine longer than the busy timeout is retried, so a slow network call on one side never fails the other.
  Future<T> exclusive<T>(Future<T> Function(Transaction tx) fn, {int retries = 8}) async {
    for (var attempt = 0; ; attempt++) {
      try {
        return await raw.transaction(fn, exclusive: true);
      } on DatabaseException catch (e) {
        final locked = e.toString().contains('locked') || e.toString().contains('busy');
        if (!locked || attempt >= retries) rethrow;
        await Future<void>.delayed(Duration(milliseconds: 250 * (attempt + 1)));
      }
    }
  }

  Future<void> close() => raw.close();
}
