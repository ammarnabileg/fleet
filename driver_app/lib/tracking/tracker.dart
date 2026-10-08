import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

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

  /// The ongoing notification: the driver's company and whether he is at work (shown only when either changes).
  final void Function(Map<String, dynamic>? company, bool working)? notify;
  final void Function()? onSessionEnded;
  final DateTime Function() _now;
  final Duration heartbeatEvery;
  final Duration syncEvery;
  final PositionQueue queue;
  final Outbox outbox;

  bool required = false;
  bool onDuty = false; // day started and not ended (the server's rule, as on the live map)
  Map<String, dynamic>? company; // the driver's company name, by language
  Duration moving = const Duration(seconds: 30);
  Duration stationary = const Duration(seconds: 300);
  Duration? _interval;
  bool _parked = false;
  StreamSubscription<Fix>? _sub;
  DateTime? _lastKept;
  DateTime? _stillSince;
  Fix? _prev; // the last fix received, kept or not, to work out a speed the phone did not measure
  DateTime? lastFixAt;
  String? _shown; // what the notification shows now
  Timer? _beat;
  Timer? _sync;
  bool _stopped = false;
  bool _syncing = false;

  static const stillSpeedKmh = 3.0;
  static const movingSpeedKmh = 8.0;
  static const stillFor = Duration(minutes: 2);

  Future<void> start() async {
    // what the last run knew, so an offline restart still shows the right notification
    final saved = await db.get('tracking_state');
    if (saved != null) {
      final m = jsonDecode(saved) as Map<String, dynamic>;
      onDuty = m['on_duty'] as bool? ?? false;
      company = (m['company'] as Map?)?.cast<String, dynamic>();
    }
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
      onDuty = r['on_duty'] as bool? ?? false; // an older server: not at work
      company = (r['company'] as Map?)?.cast<String, dynamic>() ?? company;
    } on ApiError {
      // offline: keep the last known decision (a custody does not end because the network did)
    } on SessionEnded {
      await _ended();
      return;
    }
    await _apply();
  }

  Duration get _wanted => _parked ? stationary : moving;

  Future<void> _apply() async {
    if (!required) {
      await _sub?.cancel();
      _sub = null;
      _interval = null;
      _parked = false;
      _stillSince = null;
    } else if (_interval != _wanted) {
      _listen(_wanted); // started, or the office changed the intervals: applied at once
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
    final speed = f.speedKmh ?? _derivedSpeed(_prev, f);
    _prev = f;
    // the platform may deliver faster than asked: keep one point per interval
    if (_lastKept != null && f.at.difference(_lastKept!) < (_interval ?? moving) * 0.8) return;
    _lastKept = f.at;
    await queue.add(
      recordedAt: f.at,
      lat: f.lat,
      lng: f.lng,
      accuracyM: f.accuracyM,
      speedKmh: speed,
      heading: f.heading,
      isMock: f.isMock, // sent as it is: the server rejects it and alerts the supervisors
    );
    _adapt(f, speed);
    unawaited(sync()); // each point goes at once (the live map moves with it); offline it waits in the queue
  }

  /// Parked for a while: ask for fewer fixes (battery); moving again: back to the moving interval. An unknown speed
  /// (first fix, no measurement) neither parks nor wakes.
  void _adapt(Fix f, double? speed) {
    if (speed == null) return;
    if (speed < stillSpeedKmh) {
      _stillSince ??= f.at;
      if (!_parked && f.at.difference(_stillSince!) >= stillFor) _parked = true;
    } else {
      _stillSince = null;
      if (speed >= movingSpeedKmh) _parked = false;
    }
    if (_interval != _wanted) _listen(_wanted);
  }

  /// The speed between two fixes when the phone measured none (km/h), or null when it cannot be told: too close in
  /// time or too far apart, approximate positions (over 100 m), or an impossible jump. Within the positions' own
  /// accuracy it is a stop, not wifi jitter.
  static double? _derivedSpeed(Fix? a, Fix b) {
    if (a == null) return null;
    final secs = b.at.difference(a.at).inMilliseconds / 1000;
    if (secs < 3 || secs > 600) return null;
    if ((a.accuracyM ?? 0) > 100 || (b.accuracyM ?? 0) > 100) return null;
    final metres = _metres(a.lat, a.lng, b.lat, b.lng);
    if (metres < math.max(20, math.max(a.accuracyM ?? 0, b.accuracyM ?? 0))) return 0;
    final kmh = metres / secs * 3.6;
    return kmh > 250 ? null : kmh;
  }

  static double _metres(double lat1, double lng1, double lat2, double lng2) {
    const r = 6371000.0;
    double rad(double d) => d * math.pi / 180;
    final dLat = rad(lat2 - lat1), dLng = rad(lng2 - lng1);
    final h =
        math.pow(math.sin(dLat / 2), 2) + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.pow(math.sin(dLng / 2), 2);
    return 2 * r * math.asin(math.sqrt(h));
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
        'on_duty': onDuty,
        'company': company,
      }),
    );
    final shown = jsonEncode([company, onDuty]);
    if (shown != _shown) {
      _shown = shown;
      notify?.call(company, onDuty);
    }
  }
}
