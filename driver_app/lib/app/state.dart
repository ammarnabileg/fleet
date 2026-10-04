import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import '../core/api.dart';
import '../core/catalog.dart';
import '../core/config.dart';
import '../core/db.dart';
import '../core/device.dart';
import '../core/errors.dart';
import '../core/models.dart';
import '../core/outbox.dart';
import '../core/tokens.dart';

enum Phase { booting, signedOut, permissions, onboarding, waiting, ready, blocked }

/// What needs the phone (camera, gallery, permissions, the background service). Replaced by fakes in tests.
class PhoneHooks {
  PhoneHooks({
    required this.permissionsOk,
    required this.startTracking,
    required this.stopTracking,
    required this.deviceMeta,
  });

  final Future<bool> Function() permissionsOk;
  final Future<void> Function() startTracking;
  final Future<void> Function() stopTracking;
  final Future<Map<String, String?>> Function() deviceMeta;
}

/// The app's single source of truth for the screens.
class AppState extends ChangeNotifier {
  AppState({
    required this.db,
    required this.platform,
    Api? api,
    String? baseUrl,
    this.pollEvery = const Duration(seconds: 15),
  }) : tokens = TokenStore(db),
       outbox = Outbox(db),
       catalog = Catalog(db) {
    this.api = api ?? Api(baseUrl: baseUrl ?? AppConfig.apiUrl, tokens: tokens);
    this.api.onSessionEnded = _sessionEnded;
  }

  final AppDb db;
  final PhoneHooks platform;

  /// How often the screens re-read what the tracking service stored (null: never, in tests).
  final Duration? pollEvery;
  final TokenStore tokens;
  final Outbox outbox;
  final Catalog catalog;
  late final Api api;

  Phase phase = Phase.booting;
  String lang = 'ar';
  Today? today;
  Cash? cash;
  Onboarding? onboarding;
  List<Report> reports = [];
  List<MaintenanceRequest> maintenance = [];
  List<Accident> accidents = [];
  List<Fine> fines = [];
  List<OutboxItem> queued = [];
  Map<String, dynamic> tracking = {};
  Object? lastError;
  bool busy = false;
  Timer? _poll;

  /// [deviceLang]: the phone's language at first launch; afterwards the driver's choice is kept.
  Future<void> boot({String deviceLang = 'ar'}) async {
    lang = await db.get('lang') ?? (deviceLang == 'ar' ? 'ar' : 'en');
    api.lang = lang;
    unawaited(catalog.load(api, lang));
    if (!await tokens.hasSession()) {
      _set(Phase.signedOut);
      return;
    }
    await refresh();
    _startPolling();
  }

  void _startPolling() {
    if (pollEvery != null) _poll ??= Timer.periodic(pollEvery!, (_) => _readLocal());
  }

  Future<void> setLang(String value) async {
    lang = value;
    api.lang = value;
    await db.put('lang', value);
    await catalog.load(api, value);
    notifyListeners();
  }

  // ---------------------------------------------------------------- sign in

  Future<void> requestCode(String phone) async {
    await api.post('/driver/auth/otp', body: {'phone': phone, 'device_uid': await DeviceIdentity.uid(db)}, auth: false);
  }

  Future<void> verifyCode(String phone, String code) async {
    final t = await api.post(
      '/driver/auth/verify',
      body: {'phone': phone, 'device_uid': await DeviceIdentity.uid(db), 'code': code, ...await platform.deviceMeta()},
      auth: false,
    );
    await _signedIn(t as Map<String, dynamic>);
  }

  /// The activation link the supervisor sent: binds this phone with no code. The token is after "#" (https link)
  /// or in "?t=" (the btfleet:// link from the fallback page).
  static String? activationToken(Uri uri) {
    final isActivation = uri.path.endsWith('/activate') || (uri.scheme == 'btfleet' && uri.host == 'activate');
    if (!isActivation) return null;
    final fromFragment = Uri.splitQueryString(uri.fragment)['t'];
    final token = fromFragment ?? uri.queryParameters['t'];
    return token != null && token.length >= 20 ? token : null;
  }

  Future<void> activate(String token) async {
    final t = await api.post(
      '/driver/auth/activate',
      body: {'token': token, 'device_uid': await DeviceIdentity.uid(db), ...await platform.deviceMeta()},
      auth: false,
    );
    await _signedIn(t as Map<String, dynamic>);
  }

  Future<void> _signedIn(Map<String, dynamic> t) async {
    await tokens.save(t);
    await refresh();
    _startPolling();
  }

  Future<void> signOut() async {
    try {
      await api.post('/driver/auth/logout');
    } catch (_) {
      // the phone forgets the session anyway
    }
    await platform.stopTracking();
    await tokens.clear();
    _reset();
    _set(Phase.signedOut);
  }

  void _sessionEnded() {
    unawaited(platform.stopTracking());
    _reset();
    _set(Phase.signedOut);
  }

  void _reset() {
    today = null;
    cash = null;
    onboarding = null;
    reports = [];
    maintenance = [];
    accidents = [];
    fines = [];
  }

  // ---------------------------------------------------------------- data

  /// Decides where the driver is (registration, waiting, permissions, ready) and loads the home data.
  Future<void> refresh() async {
    try {
      onboarding = Onboarding.fromJson(await api.get('/driver/onboarding') as Map<String, dynamic>);
      if (onboarding!.mustFill) return _set(Phase.onboarding);
      if (onboarding!.waiting) return _set(Phase.waiting);
      if (!await platform.permissionsOk()) return _set(Phase.permissions);
      await platform.startTracking();
      await Future.wait([loadToday(), loadCash(), loadReports(), _quietly(loadMaintenance), _quietly(loadAccidents)]);
      await _readLocal();
      _set(Phase.ready);
    } on SessionEnded {
      // already sent to sign-in
    } on ApiError catch (e) {
      if (e.code == 'driver_access_disabled') return _set(Phase.blocked);
      lastError = e;
      await _readLocal();
      // offline: show what we have; the first launch with no data stays on its current phase
      if (phase == Phase.booting) _set(onboarding == null ? Phase.ready : phase);
      notifyListeners();
    }
  }

  Future<void> permissionsGranted() => refresh();

  Future<void> loadToday() async => today = Today.fromJson(await api.get('/driver/today') as Map<String, dynamic>);

  Future<void> loadCash() async => cash = Cash.fromJson(await api.get('/driver/cash') as Map<String, dynamic>);

  Future<void> loadReports() async =>
      reports = [for (final r in await api.get('/driver/reports') as List) Report.fromJson(r as Map<String, dynamic>)];

  Future<void> loadMaintenance() async => maintenance = [
    for (final r in await api.get('/driver/maintenance') as List)
      MaintenanceRequest.fromJson(r as Map<String, dynamic>),
  ];

  Future<void> loadAccidents() async => accidents = [
    for (final a in await api.get('/driver/accidents') as List) Accident.fromJson(a as Map<String, dynamic>),
  ];

  Future<void> loadFines() async =>
      fines = [for (final f in await api.get('/driver/fines') as List) Fine.fromJson(f as Map<String, dynamic>)];

  /// Something the home screen can live without (the maintenance list): a failure does not hold the rest.
  Future<void> _quietly(Future<void> Function() load) async {
    try {
      await load();
    } on ApiError {
      // shown next time
    }
  }

  Future<void> confirmReceipt(String id) async {
    await api.post('/driver/cash/receipts/$id/confirm');
    await loadCash();
    notifyListeners();
  }

  /// The tracking service's state and the outbox, as stored by either engine.
  Future<void> _readLocal() async {
    final raw = await db.get('tracking_state');
    tracking = raw == null ? {} : Map<String, dynamic>.from(jsonDecode(raw) as Map);
    queued = await outbox.items();
    notifyListeners();
  }

  Future<void> reloadLocal() => _readLocal();

  // ---------------------------------------------------------------- driver actions (through the outbox)

  Future<SendResult> sendReading({
    required String kind,
    required int km,
    required String photoPath,
    required DateTime takenAt,
    double? lat,
    double? lng,
  }) async {
    final id = await outbox.add(
      'odometer',
      {'kind': kind, 'value_km': km, 'recorded_at': takenAt.toUtc().toIso8601String(), 'lat': lat, 'lng': lng},
      {'photo_sha256': photoPath},
    );
    return _sendNow(id, after: loadToday);
  }

  Future<SendResult> sendReport({
    required String businessDate,
    required int orders,
    required String cash,
    String? screenshotPath,
    String? notes,
  }) async {
    final id = await outbox.add(
      'report',
      {'business_date': businessDate, 'orders_count': orders, 'cash_amount': cash, 'notes': notes},
      {'screenshot_sha256': ?screenshotPath},
    );
    return _sendNow(
      id,
      after: () async {
        await loadReports();
        await loadCash();
      },
    );
  }

  /// A maintenance request for the vehicle the driver holds. The id is made here, once: a retry after a lost
  /// answer is recognised by the server ("request_exists") instead of creating a second request.
  Future<SendResult> sendMaintenance({
    required String kind,
    required String description,
    int? km,
    required List<String> photoPaths,
  }) async {
    final id = await outbox.add(
      'maintenance',
      {'client_ref': const Uuid().v4(), 'kind': kind, 'description': description, 'odometer_km': km},
      {for (var i = 0; i < photoPaths.length; i++) 'photos.$i': photoPaths[i]},
    );
    return _sendNow(id, after: loadMaintenance);
  }

  /// An accident with the vehicle the driver held at [occurredAt] (taken when the report screen opened, so a report
  /// sent hours later keeps the real time). Photos from the app's camera; the police report may come later.
  Future<SendResult> sendAccident({
    required DateTime occurredAt,
    double? lat,
    double? lng,
    required String description,
    required bool injuries,
    String? injuriesNote,
    String? otherParty,
    required List<String> photoPaths,
    String? policeReportPath,
    String? policeReportNo,
  }) async {
    final id = await outbox.add(
      'accident',
      {
        'client_ref': const Uuid().v4(),
        'occurred_at': occurredAt.toUtc().toIso8601String(),
        'lat': lat,
        'lng': lng,
        'description': description,
        'injuries': injuries,
        'injuries_note': injuriesNote,
        'other_party': otherParty,
        'police_report_no': policeReportNo,
      },
      {for (var i = 0; i < photoPaths.length; i++) 'photos.$i': photoPaths[i], 'police_report': ?policeReportPath},
    );
    return _sendNow(id, after: loadAccidents);
  }

  /// The police report photographed once it is issued (the accident waits for it).
  Future<SendResult> sendPoliceReport({required String accidentId, required String photoPath, String? number}) async {
    final id = await outbox.add(
      'police_report',
      {'accident_id': accidentId, 'number': number},
      {'file_sha256': photoPath},
    );
    return _sendNow(id, after: loadAccidents);
  }

  Future<SendResult> _sendNow(int id, {required Future<void> Function() after}) async {
    try {
      final r = await outbox.sendNow(id, api);
      if (r == SendResult.sent) {
        try {
          await after();
        } on ApiError {
          // sent; the screen data refreshes next time
        }
      }
      return r;
    } finally {
      await _readLocal();
    }
  }

  Future<void> discard(int id) async {
    await outbox.discard(id);
    await _readLocal();
  }

  /// A readable message for any failure, in the app's language.
  String message(Object error, {required String network, required String generic}) =>
      catalog.message(error, network: network, generic: generic);

  void _set(Phase p) {
    phase = p;
    notifyListeners();
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }
}
