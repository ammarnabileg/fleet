import 'dart:async';
import 'dart:convert';

import '../core/api.dart';
import '../core/config.dart';
import '../core/db.dart';
import '../core/errors.dart';
import '../core/outbox.dart';
import 'positions.dart';

/// One location fix, whatever produced it (the GPS plugin on the phone, a fake in tests).
class Fix {
  Fix({
    required this.at,
    required this.lat,
    required this.lng,
    this.accuracyM,
    this.speedKmh,
    this.heading,
    this.isMock = false,
  });

  final DateTime at;
  final double lat;
  final double lng;
  final double? accuracyM;
  final double? speedKmh;
  final int? heading;
  final bool isMock;
}

typedef FixStream = Stream<Fix> Function(Duration interval);
typedef HealthProbe = Future<Map<String, dynamic>> Function({
  required bool trackingRunning,
  required int queueSize,
  String? lastUploadAt,
});

/// The background work: a heartbeat tells the server the phone's health and tells the phone whether to track
/// (only during a custody) and how often; fixes go to the queue; the queue and the outbox are sent regularly.
/// No plugin code here, so the whole behaviour runs in tests.
class Tracker {
  Tracker({
    required this.db,
    required this.api,
    required this.fixes,
    required this.health,
    this.notify,
    this.onSessionEnded,
    DateTime Function()? clock,
    this.heartbeatEvery = const Duration(minutes: 5),
    this.syncEvery = const Duration(minutes: 1),
  }) : _now = clock ?? DateTime.now,
       queue = PositionQueue(db, clock: clock),
       outbox = Outbox(db, clock: clock);

  final AppDb db;
  final Api api;
  final FixStream fixes;
  final HealthProbe health;
  final void Function(String title, String text)? notify;
  final void Function()? onSessionEnded;
  final DateTime Function() _now;
  final Duration heartbeatEvery;
  final Duration syncEvery;
  final PositionQueue queue;
  final Outbox outbox;

  bool required = false;
  Duration moving = const Duration(seconds: 30);
  Duration stationary = const Duration(seconds: 300);
  Duration? _interval;
  StreamSubscription<Fix>? _sub;
  DateTime? _lastKept;
  DateTime? _stillSince;
  DateTime? lastFixAt;
  Timer? _beat;
  Timer? _sync;
  bool _stopped = false;
  bool _syncing = false;

  static const stillSpeedKmh = 3.0;
  static const movingSpeedKmh = 8.0;
  static const stillFor = Duration(minutes: 2);

  Future<void> start() async {
    await heartbeat();
    await sync();
    _beat = Timer.periodic(heartbeatEvery, (_) => heartbeat());
    _sync = Timer.periodic(syncEvery, (_) => sync());
  }

  Future<void> stop() async {
    _stopped = true;
    _beat?.cancel();
    _sync?.cancel();
    await _sub?.cancel();
    _sub = null;
    _interval = null;
  }

  /// Reports health; the answer switches tracking on or off and sets the intervals (from the server settings).
  Future<void> heartbeat() async {
    if (_stopped) return;
    try {
      final state = await health(
        trackingRunning: _sub != null,
        queueSize: await queue.size(),
        lastUploadAt: await db.get('last_upload_at'),
      );
      final r = await api.post('/driver/status', body: state) as Map<String, dynamic>;
      required = r['tracking_required'] as bool;
      moving = Duration(seconds: (r['interval_moving_s'] as num).toInt());
      stationary = Duration(seconds: (r['interval_stationary_s'] as num).toInt());
    } on ApiError {
      // offline: keep the last known decision (a custody does not end because the network did)
    } on SessionEnded {
      await _ended();
      return;
    }
    await _apply();
  }

  Future<void> _apply() async {
    if (!required) {
      await _sub?.cancel();
      _sub = null;
      _interval = null;
    } else if (_interval == null) {
      _listen(moving);
    }
    await _publish();
  }

  void _listen(Duration interval) {
    _sub?.cancel();
    _interval = interval;
    _sub = fixes(interval).listen(_onFix, onError: (Object _) {});
  }

  Future<void> _onFix(Fix f) async {
    if (!required || _stopped) return;
    lastFixAt = f.at;
    // the platform may deliver faster than asked: keep one point per interval
    if (_lastKept != null && f.at.difference(_lastKept!) < (_interval ?? moving) * 0.8) return;
    _lastKept = f.at;
    await queue.add(
      recordedAt: f.at,
      lat: f.lat,
      lng: f.lng,
      accuracyM: f.accuracyM,
      speedKmh: f.speedKmh,
      heading: f.heading,
      isMock: f.isMock, // sent as it is: the server rejects it and alerts the supervisors
    );
    _adapt(f);
    if (await queue.size() >= 30) unawaited(sync());
  }

  /// Parked for a while: ask for fewer fixes (battery); moving again: back to the moving interval.
  void _adapt(Fix f) {
    final speed = f.speedKmh ?? 0;
    if (speed < stillSpeedKmh) {
      _stillSince ??= f.at;
      if (_interval == moving && f.at.difference(_stillSince!) >= stillFor) _listen(stationary);
    } else {
      _stillSince = null;
      if (speed >= movingSpeedKmh && _interval == stationary) _listen(moving);
    }
  }

  /// Sends the outbox (readings, reports) then the queued points. Network errors simply wait for next time.
  Future<void> sync() async {
    if (_stopped || _syncing) return;
    _syncing = true;
    try {
      await outbox.flush(api);
      await queue.upload(api);
    } on ApiError {
      // offline or server trouble: everything stays queued
    } on SessionEnded {
      await _ended();
    } finally {
      _syncing = false;
    }
    await _publish();
  }

  Future<void> _ended() async {
    await stop();
    onSessionEnded?.call();
  }

  /// The state the UI shows (it runs in the other engine, so it reads it from the database).
  Future<void> _publish() async {
    final size = await queue.size();
    final last = await db.get('last_upload_at');
    await db.put(
      'tracking_state',
      jsonEncode({
        'required': required,
        'running': _sub != null,
        'interval_s': _interval?.inSeconds,
        'last_fix_at': lastFixAt?.toUtc().toIso8601String(),
        'last_upload_at': last,
        'queue': size,
        'updated_at': _now().toUtc().toIso8601String(),
        'app_version': AppConfig.appVersion,
      }),
    );
    notify?.call(
      required ? 'التتبع يعمل · Tracking on' : 'متصل · Connected',
      size > 0 ? 'بانتظار الإرسال: $size · Waiting: $size' : 'كل المواقع أُرسلت · All sent',
    );
  }
}
