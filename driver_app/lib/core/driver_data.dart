import 'dart:convert';
import 'dart:io';

import 'db.dart';

/// What the phone kept for the driver signed in: his unsent actions (with their photos), his recorded positions, and
/// what was read for him. Forgotten when his session ends, so the next driver on this phone never sends or sees it.
/// The phone's own settings stay (language, the office's app config, the device id, the server's texts).
const driverKeys = [
  'tracking_state',
  'last_upload_at',
  'fuel',
  'report_form',
  'maintenance_form',
  'push_token',
  'live_status', // his states and alerts (the templates are the office's, kept)
  'headsup_posted',
];

Future<void> forgetDriver(AppDb db) async {
  final files = <String>[];
  await db.exclusive((tx) async {
    for (final r in await tx.query('outbox', columns: ['files'])) {
      files.addAll(Map<String, String>.from(jsonDecode(r['files'] as String) as Map).values);
    }
    await tx.delete('outbox');
    // the sequence numbers go on (never reused, the server keeps them unique per phone): only the rows go
    await tx.delete('positions');
    for (final k in driverKeys) {
      await db.put(k, null, tx: tx);
    }
  });
  for (final f in files) {
    try {
      await File(f).delete();
    } on FileSystemException {
      // already gone
    }
  }
}
