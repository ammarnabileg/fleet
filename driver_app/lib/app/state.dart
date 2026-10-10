import 'dart:async';
import 'dart:convert';
import 'dart:io';

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
    this.pushToken,
  });

  final Future<bool> Function() permissionsOk;
  final Future<void> Function() startTracking;
  final Future<void> Function() stopTracking;
  final Future<Map<String, String?>> Function() deviceMeta;

  /// The phone's push token for the server's Firebase values (null: refused, or no push on this build).
  final Future<String?> Function(
    Map<String, dynamic> config, {
    required void Function(String token) onRefresh,
    required void Function() onMessage,
  })?
  pushToken;
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
  PlatformStatus? statements;
  List<Payslip> payslips = [];
  List<Objection> objections = [];
  DriverSchemes? schemes;
  Fuel? fuel; // null until loaded, or when the server has no fuel for him: the app offers none
  Notices? notices;
  List<OutboxItem> queued = [];
  Map<String, dynamic> tracking = {};
  Object? lastError;
  bool busy = false;
  Timer? _poll;

  /// What this company's office set for the app (GET /driver/app-config), kept from the last answer so the right
  /// screens show offline: how drivers sign in (the phone and a WhatsApp code, or false: the civil ID and a password
  /// only), the screens it hides (the server refuses them too), and its splash screen.
  bool phoneCodes = true;
  Set<String> hiddenScreens = {};
  ({String image, String color, int seconds})? splash;

  /// The splash image kept on the phone, and whether it is showing (only when the app opens).
  Uint8List? splashImage;
  bool splashing = false;

  bool shows(String screen) => !hiddenScreens.contains(screen);

  /// What the daily report asks, from the driver's platform: orders and cash for one, orders and whether the
  /// platform counted the day for another. Kept for offline; until the server answers, orders and cash.
  ({List<String> fields, bool screenshot, bool endReading}) reportForm = (
    fields: const ['orders', 'cash'],
    screenshot: true,
    endReading: false,
  );

  /// The maintenance request form: the centers he may take the car to. Kept for offline.
  ({bool direct, List<MaintenanceCenter> centers}) maintenanceForm = (direct: false, centers: const []);

  Profile? profile;
  MyVehicle? myVehicle;
  List<DriverDocument> documents = [];

  /// Today's report waits for the end-of-day odometer: the day was started on a vehicle still held and not closed.
  bool get endReadingDue => reportForm.endReading && today?.custody != null && dayStarted && !dayEnded;

  /// Starts and ends of day still in the queue (no signal yet), oldest first: the screens count them already, so
  /// the driver can end the session he started offline, or report it, without waiting for the network.
  List<String> get _queuedDay => [
    for (final i in queued)
      if (i.kind == 'odometer' && i.state != 'failed' && _isToday(i.payload['recorded_at'] as String?))
        i.payload['kind'] as String,
  ];

  bool _isToday(String? at) => at != null && kuwaitDay(DateTime.parse(at)) == kuwaitDay(DateTime.now());

  /// The day as the driver left it, the queue included.
  bool get dayStarted => _queuedDay.isNotEmpty || (today?.startDayDone ?? false);
  bool get dayEnded => _queuedDay.isNotEmpty ? _queuedDay.last == 'end_day' : (today?.endDayDone ?? false);

  /// The start of day still in the queue (no signal yet), the latest: its time and reading.
  ({DateTime at, int? km})? get queuedStart {
    for (final i in queued.reversed) {
      if (i.kind == 'odometer' && i.state != 'failed' && i.payload['kind'] == 'start_day') {
        final at = i.payload['recorded_at'] as String?;
        if (_isToday(at)) return (at: DateTime.parse(at!), km: (i.payload['value_km'] as num?)?.toInt());
      }
    }
    return null;
  }

  /// This session's report of today, once sent (not refused): the home screen and the daily work say so.
  Report? get todaysReport {
    final day = kuwaitDay(DateTime.now());
    for (final r in reports) {
      if (r.businessDate == day && r.status != 'rejected' && r.session >= sessionsToday) return r;
    }
    return null;
  }

  /// A report of [day] for [session] (or later) still in the outbox, not refused: as far as the driver is concerned it
  /// is sent, and it must not be sent twice. One without a session (an older server) is the day's.
  OutboxItem? queuedReport(String day, int session) {
    for (final i in queued) {
      if (i.kind == 'report' && i.state != 'failed' && i.payload['business_date'] == day) {
        final s = (i.payload['session'] as num?)?.toInt();
        if (s == null || s >= session) return i;
      }
    }
    return null;
  }

  /// This session's report of today still waiting for the network.
  OutboxItem? get todaysQueuedReport => queuedReport(kuwaitDay(DateTime.now()), sessionsToday);

  /// Today's work sessions as known, the starts still queued included.
  int get sessionsToday => (today?.sessions ?? 0) + _queuedDay.where((k) => k == 'start_day').length;

  /// [deviceLang]: the phone's language at first launch; afterwards the driver's choice is kept.
  Future<void> boot({String deviceLang = 'ar'}) async {
    lang = await db.get('lang') ?? (deviceLang == 'ar' ? 'ar' : 'en');
    api.lang = lang;
    try {
      final m = await DeviceIdentity.meta();
      api.userAgent = 'FleetDriver/${m['app_version']} (${m['model'] ?? m['platform']})';
    } catch (_) {
      // the plain name will do
    }
    _applyConfig(await db.get('app_config'));
    _applyReportForm(await db.get('report_form'));
    _applyMaintenanceForm(await db.get('maintenance_form'));
    _applyFuel(await db.get('fuel'));
    await _showSplash();
    unawaited(catalog.load(api, lang));
    if (!await tokens.hasSession()) {
      _set(Phase.signedOut);
      unawaited(loadAppConfig());
      return;
    }
    await refresh();
    _startPolling();
  }

  void _startPolling() {
    if (pollEvery != null) _poll ??= Timer.periodic(pollEvery!, (_) => pollLocal());
  }

  Future<void> setLang(String value) async {
    lang = value;
    api.lang = value;
    await db.put('lang', value);
    await catalog.load(api, value);
    notifyListeners();
    unawaited(registerPush()); // pushes are written in the app's language
    // the tracking notification too: the service reads the language again and redraws it
    if (phase == Phase.ready) unawaited(platform.startTracking().catchError((Object _) {}));
  }

  // ---------------------------------------------------------------- sign in

  Future<void> loadAppConfig() async {
    try {
      final raw = jsonEncode(await api.get('/driver/app-config', auth: false));
      await db.put('app_config', raw);
      final changed = _applyConfig(raw);
      await _keepSplash();
      if (changed) notifyListeners();
    } catch (_) {
      // offline or an older server: the last known answer stays
    }
  }

  /// Firebase's public values for this app, once the office switched push on (GET /driver/app-config).
  Map<String, dynamic>? pushConfig;

  bool _applyConfig(String? raw) {
    if (raw == null) return false;
    final c = jsonDecode(raw) as Map<String, dynamic>;
    pushConfig = c['push'] as Map<String, dynamic>?;
    final codes = c['phone_codes'] != false;
    final hidden = {for (final s in c['hidden_screens'] as List? ?? const []) s as String};
    final s = c['splash'] as Map<String, dynamic>?;
    final next = s == null
        ? null
        : (image: s['image'] as String, color: s['color'] as String, seconds: (s['seconds'] as num).toInt());
    final changed = codes != phoneCodes || !setEquals(hidden, hiddenScreens) || next != splash;
    phoneCodes = codes;
    hiddenScreens = hidden;
    splash = next;
    return changed;
  }

  /// The splash image is kept on the phone: it shows when the app opens, before the network answers (so from the
  /// launch after it was set).
  Future<void> _keepSplash() async {
    final s = splash;
    if (s == null) {
      await db.put('splash_sha', null);
      await db.put('splash_image', null);
      return;
    }
    if (await db.get('splash_sha') == s.image) return;
    final bytes = await api.bytes('/driver/splash/${s.image}');
    await db.put('splash_image', base64Encode(bytes));
    await db.put('splash_sha', s.image);
  }

  Future<void> _showSplash() async {
    final s = splash;
    final kept = await db.get('splash_image');
    if (s == null || kept == null || await db.get('splash_sha') != s.image) return;
    splashImage = base64Decode(kept);
    splashing = true;
    Timer(Duration(seconds: s.seconds), () {
      splashing = false;
      notifyListeners();
    });
  }

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

  /// His civil ID and the initial password the office gave him (once), or without phone codes his own password.
  /// next: "phone" (register his phone by code), "password" (choose his own), or "done" (his own password: signed in).
  Future<({String next, String? token, Map<String, dynamic> name})> claimStart(String civilId, String password) async {
    final r = await api.post(
      '/driver/auth/claim',
      body: {
        'civil_id': civilId,
        'password': password,
        'device_uid': await DeviceIdentity.uid(db),
        ...await platform.deviceMeta(),
      },
      auth: false,
    ) as Map<String, dynamic>;
    final next = r['next'] as String? ?? 'phone';
    if (next == 'done') await _signedIn(Map<String, dynamic>.from(r['tokens'] as Map));
    return (next: next, token: r['claim_token'] as String?, name: Map<String, dynamic>.from(r['name'] as Map));
  }

  /// Without phone codes: the password he signs in with from now on; this phone is bound and the self-registration
  /// follows.
  Future<void> claimPassword(String token, String password) async {
    final t = await api.post(
      '/driver/auth/claim/password',
      body: {
        'claim_token': token,
        'device_uid': await DeviceIdentity.uid(db),
        'password': password,
        ...await platform.deviceMeta(),
      },
      auth: false,
    );
    await _signedIn(t as Map<String, dynamic>);
  }

  /// His phone: a WhatsApp code goes to it. Returns the masked number it went to.
  Future<String> claimPhone(String token, String phone) async {
    final r = await api.post(
      '/driver/auth/claim/phone',
      body: {'claim_token': token, 'device_uid': await DeviceIdentity.uid(db), 'phone': phone},
      auth: false,
    ) as Map<String, dynamic>;
    return r['sent_to'] as String;
  }

  /// The code: the phone becomes his, this phone is bound, and the self-registration follows.
  Future<void> claimVerify(String token, String code) async {
    final t = await api.post(
      '/driver/auth/claim/verify',
      body: {
        'claim_token': token,
        'device_uid': await DeviceIdentity.uid(db),
        'code': code,
        ...await platform.deviceMeta(),
      },
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
    await db.put('push_token', null); // the server forgot it: the next sign-in sends it again
    _reset();
    _set(Phase.signedOut);
    unawaited(loadAppConfig());
  }

  void _sessionEnded() {
    unawaited(platform.stopTracking());
    _reset();
    _set(Phase.signedOut);
    unawaited(loadAppConfig());
  }

  void _reset() {
    today = null;
    cash = null;
    profile = null;
    myVehicle = null;
    _carNoticesSeen = null;
    documents = [];
    onboarding = null;
    reports = [];
    maintenance = [];
    accidents = [];
    fines = [];
    statements = null;
    payslips = [];
    objections = [];
    schemes = null;
    fuel = null;
    unawaited(db.put('fuel', null)); // whether he may claim fuel was his, not the next driver's
    notices = null;
  }

  // ---------------------------------------------------------------- data

  /// Decides where the driver is (registration, waiting, permissions, ready) and loads the home data.
  Future<void> refresh() async {
    try {
      await loadAppConfig();
      onboarding = Onboarding.fromJson(await api.get('/driver/onboarding') as Map<String, dynamic>);
      if (onboarding!.mustFill) return _set(Phase.onboarding);
      if (onboarding!.waiting) return _set(Phase.waiting);
      if (!await platform.permissionsOk()) return _set(Phase.permissions);
      // the home screen does not wait for the tracking service to come up, nor fails with it
      unawaited(platform.startTracking().catchError((Object _) {}));
      await Future.wait([
        loadToday(),
        if (shows('cash')) loadCash(),
        if (shows('daily_report')) loadReports(),
        if (shows('maintenance')) _quietly(loadMaintenance),
        if (shows('accidents')) _quietly(loadAccidents),
        if (shows('fuel')) _quietly(loadFuel),
        _quietly(loadNotices),
        _quietly(loadProfile),
      ]);
      await _readLocal();
      _set(Phase.ready);
      unawaited(registerPush());
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

  Future<void> loadToday() async {
    final before = today?.custody?.id;
    today = Today.fromJson(await api.get('/driver/today') as Map<String, dynamic>);
    final changed = today!.custody?.id != before;
    // another car, or none: "my car" is read again whole and replaces what was shown; no car: the one he registered
    // (waiting for the office, or refused) shows on the home card
    if (changed || today!.custody == null) await _reloadVehicle(stale: changed);
  }

  int _vehicleReads = 0;

  /// Reads "my car": what was shown stays until the answer replaces it. A read that fails once his car changed leaves
  /// it unknown (null): the screens then show the error, never the car before nor the button to register one.
  Future<void> _reloadVehicle({required bool stale}) async {
    _vehicleReads++;
    try {
      await loadVehicle();
    } on ApiError {
      if (stale) myVehicle = null;
    }
  }

  /// The notices that say his custody changed: handed a car, taken out of one, swapped, his registered car
  /// approved, his car returned to the office.
  static const carNotices = {
    'vehicle_handed_over',
    'vehicle_returned',
    'vehicle_taken',
    'vehicle_swapped',
    'vehicle_claim_approved',
    'vehicle_claim_rejected',
    'vehicle_claim_superseded',
  };
  Set<String>? _carNoticesSeen;

  /// His custody changed: everything shown about "my car" (the car, its readings, today's day, the screens that
  /// use the current car) is read again and replaces what was there; tracking reports at once.
  Future<void> carChanged() async {
    final reads = _vehicleReads;
    try {
      await loadToday();
    } on ApiError {
      // the day as it was; "my car" below says whether the network is there
    }
    if (_vehicleReads == reads) await _reloadVehicle(stale: true);
    await Future.wait([
      if (shows('maintenance')) _quietly(loadMaintenance),
      if (shows('fines')) _quietly(loadFines),
      if (shows('fuel')) _quietly(loadFuel),
    ]);
    unawaited(platform.startTracking().catchError((Object _) {}));
    notifyListeners();
  }

  /// Back to the app: his car and day as they are now, and what he was told meanwhile.
  Future<void> resumed() async {
    if (phase != Phase.ready) return;
    await _quietly(loadToday);
    await _quietly(loadNotices);
    notifyListeners();
  }

  Future<void> loadProfile() async => profile = Profile(await api.get('/driver/profile') as Map<String, dynamic>);

  Future<void> loadVehicle() async =>
      myVehicle = MyVehicle.fromJson(await api.get('/driver/vehicle') as Map<String, dynamic>);

  Future<void> loadDocuments() async => documents = [
    for (final d in await api.get('/driver/documents') as List) DriverDocument(d as Map<String, dynamic>),
  ];

  /// Another vehicle, named by its plate, with his reason; the supervisor decides (FR-ASG-04). Needs the network.
  /// A plate the server does not know is refused (`vehicle_plate_not_found`) so he types it again.
  Future<void> requestVehicleChange(String plate, String reason) async {
    myVehicle = MyVehicle.fromJson(
      await api.post('/driver/vehicle-change-requests', body: {'requested_plate': plate, 'reason': reason})
          as Map<String, dynamic>,
    );
    notifyListeners();
  }

  /// No car: he registers the one he takes, by its plate, with the odometer from the app's camera at the photo's
  /// time and condition photos. It waits for the office's approval. Through the outbox (a resend is recognised by its
  /// client_ref); a plate the server refuses comes back at once so he types it again.
  Future<SendResult> sendClaim({
    required String plate,
    required int km,
    required String photoPath,
    required DateTime takenAt,
    List<String> photoPaths = const [],
  }) async {
    // the outbox removes its files when the server refuses: it sends copies, so after a plate refused he corrects the
    // plate and sends again with the same photos
    final originals = [photoPath, ...photoPaths];
    final copies = [for (final f in originals) (await File(f).copy('$f.${const Uuid().v4()}.jpg')).path];
    final id = await outbox.add(
      'vehicle_claim',
      {
        'client_ref': const Uuid().v4(),
        'plate': plate,
        'odometer_km': km,
        'recorded_at': takenAt.toUtc().toIso8601String(),
      },
      {'photo_sha256': copies.first, for (var i = 1; i < copies.length; i++) 'photos.${i - 1}': copies[i]},
    );
    final r = await _sendNow(id, after: loadVehicle);
    for (final f in originals) {
      try {
        await File(f).delete();
      } on FileSystemException {
        // already gone
      }
    }
    return r;
  }

  /// A renewed document, from the phone's files, with its new expiry; the office checks it before it counts.
  Future<SendResult> sendRenewal({
    required String typeCode,
    required String expiry,
    String? number,
    required String filePath,
  }) async {
    final id = await outbox.add(
      'renewal',
      {'type_code': typeCode, 'expiry_date': expiry, 'number': number},
      {'file_sha256': filePath},
    );
    return _sendNow(id, after: loadDocuments);
  }

  Future<void> loadCash() async => cash = Cash.fromJson(await api.get('/driver/cash') as Map<String, dynamic>);

  Future<void> loadReports() async {
    reports = [for (final r in await api.get('/driver/reports') as List) Report.fromJson(r as Map<String, dynamic>)];
    try {
      final raw = jsonEncode(await api.get('/driver/reports/form'));
      await db.put('report_form', raw);
      _applyReportForm(raw);
    } on ApiError {
      // an older server: the last known form stays
    }
  }

  void _applyReportForm(String? raw) {
    if (raw == null) return;
    final f = jsonDecode(raw) as Map<String, dynamic>;
    reportForm = (
      fields: [for (final x in f['fields'] as List) x as String],
      screenshot: f['screenshot'] != false,
      endReading: f['end_reading'] == true,
    );
  }

  Future<void> loadMaintenance() async {
    maintenance = [
      for (final r in await api.get('/driver/maintenance') as List)
        MaintenanceRequest.fromJson(r as Map<String, dynamic>),
    ];
    try {
      final raw = jsonEncode(await api.get('/driver/maintenance/form'));
      await db.put('maintenance_form', raw);
      _applyMaintenanceForm(raw);
    } on ApiError {
      // an older server: the last form kept
    }
  }

  void _applyMaintenanceForm(String? raw) {
    if (raw == null) return;
    final f = jsonDecode(raw) as Map<String, dynamic>;
    maintenanceForm = (
      direct: f['direct_to_center'] == true,
      centers: [for (final c in f['centers'] as List? ?? []) MaintenanceCenter.fromJson(c as Map<String, dynamic>)],
    );
  }

  /// Whether he may claim fuel and his last claims. A refusal (an older server, the screen hidden) means none is
  /// offered; a network failure keeps what was loaded.
  Future<void> loadFuel() async {
    try {
      final raw = await api.get('/driver/fuel') as Map<String, dynamic>;
      fuel = Fuel.fromJson(raw);
      await db.put('fuel', jsonEncode(raw)); // a receipt is photographed at a station with no signal, after a restart
    } on ApiError catch (e) {
      if (e.isTransient) rethrow;
      fuel = null;
      await db.put('fuel', null);
    }
  }

  void _applyFuel(String? raw) {
    if (raw == null || fuel != null) return;
    try {
      fuel = Fuel.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      // an older shape: the next load replaces it
    }
  }

  Future<void> loadAccidents() async => accidents = [
    for (final a in await api.get('/driver/accidents') as List) Accident.fromJson(a as Map<String, dynamic>),
  ];

  /// Gives the server this phone's push token (again when it or the language changes), once push is on.
  Future<void> registerPush({bool force = false}) async {
    final config = pushConfig, hook = platform.pushToken;
    if (config == null || hook == null || !await tokens.hasSession()) return;
    try {
      final token = await hook(
        config,
        onRefresh: (t) => unawaited(_sendPushToken(t)),
        onMessage: () => unawaited(_quietly(loadNotices)),
      );
      if (token == null) return;
      if (!force && await db.get('push_token') == '$token|$lang') return;
      await _sendPushToken(token);
    } catch (_) {
      // Firebase unreachable or the server older: notices still show in the app
    }
  }

  Future<void> _sendPushToken(String token) async {
    await api.post('/driver/push-token', body: {'token': token, 'lang': lang});
    await db.put('push_token', '$token|$lang');
  }

  Future<void> loadNotices() async {
    notices = Notices.fromJson(await api.get('/driver/notifications') as Map<String, dynamic>);
    final car = {
      for (final n in notices!.items)
        if (carNotices.contains(n.kind)) n.id,
    };
    final seen = _carNoticesSeen;
    _carNoticesSeen = {...?seen, ...car};
    notifyListeners();
    // a custody change told since the last look (the first look is the app's start, which reads everything)
    if (seen != null && car.difference(seen).isNotEmpty) await carChanged();
  }

  /// Everything shown is now read: the badge goes, the list keeps them.
  Future<void> readNotices() async {
    if ((notices?.unread ?? 0) == 0) return;
    await api.post('/driver/notifications/read');
    await loadNotices();
  }

  Future<void> loadFines() async =>
      fines = [for (final f in await api.get('/driver/fines') as List) Fine.fromJson(f as Map<String, dynamic>)];

  Future<void> loadStatements() async =>
      statements = PlatformStatus.fromJson(await api.get('/driver/statements') as Map<String, dynamic>);

  Future<void> loadPayslips() async => payslips = [
    for (final p in await api.get('/driver/payslips') as List) Payslip.fromJson(p as Map<String, dynamic>),
  ];

  Future<void> loadObjections() async => objections = [
    for (final o in await api.get('/driver/objections') as List) Objection.fromJson(o as Map<String, dynamic>),
  ];

  /// An objection to a payslip: all of it ([itemCode] none) or one line, the reason, a photo if he has one. Through the
  /// outbox, so a lost answer is retried without a second objection.
  Future<SendResult> sendObjection({
    required String runId,
    String? itemCode,
    required String reason,
    String? attachmentPath,
  }) async {
    final id = await outbox.add(
      'objection',
      {'run_id': runId, 'client_ref': const Uuid().v4(), 'item_code': itemCode, 'reason': reason},
      {'attachment_sha256': ?attachmentPath},
    );
    return _sendNow(id, after: loadObjections);
  }

  Future<void> loadSchemes() async =>
      schemes = DriverSchemes.fromJson(await api.get('/driver/schemes') as Map<String, dynamic>);

  /// Asks the office to move him to another scheme of his platform, from next month.
  Future<void> requestScheme(String schemeId, {String? note}) async {
    schemes = DriverSchemes.fromJson(
      await api.post('/driver/scheme-requests', body: {'scheme_id': schemeId, 'note': ?note}) as Map<String, dynamic>,
    );
    notifyListeners();
  }

  Future<void> cancelSchemeRequest(String id) async {
    schemes = DriverSchemes.fromJson(await api.delete('/driver/scheme-requests/$id') as Map<String, dynamic>);
    notifyListeners();
  }

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
  /// [onlyIfChanged] (the periodic look): the screens are rebuilt only when the tracking state or the outbox moved.
  Future<void> _readLocal({bool onlyIfChanged = false}) async {
    final raw = await db.get('tracking_state');
    final items = await outbox.items();
    final state = raw == null ? <String, dynamic>{} : Map<String, dynamic>.from(jsonDecode(raw) as Map);
    // updated_at moves with every point and no screen shows it
    final seen = Map<String, dynamic>.from(state)..remove('updated_at');
    final mark =
        '${jsonEncode(seen)}|${[for (final i in items) '${i.id}:${i.state}:${i.attempts}:${i.lastError}'].join(',')}';
    if (onlyIfChanged && mark == _localMark) return;
    _localMark = mark;
    tracking = state;
    final gone = [
      for (final i in queued)
        if (i.kind.isNotEmpty && !items.any((x) => x.id == i.id)) i.kind,
    ];
    queued = items;
    notifyListeners();
    // something the home screen shows was delivered meanwhile (a reading, a pickup): its state from the server
    if (gone.any((k) => k != 'report') && today != null) unawaited(_quietly(loadToday).then((_) => notifyListeners()));
    // a report delivered in the background: the daily work shows it sent, with its status
    if (gone.contains('report') && shows('daily_report')) {
      unawaited(_quietly(loadReports).then((_) => notifyListeners()));
    }
  }

  String? _localMark;

  /// The periodic look at what the tracking service and the outbox wrote (they run apart from the screens).
  @visibleForTesting
  Future<void> pollLocal() => _readLocal(onlyIfChanged: true);

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
    // the day started or ended: the tracking service reports at once, so its notification says so within seconds
    return _sendNow(
      id,
      after: () async {
        await loadToday();
        if (kind == 'start_day' || kind == 'end_day') unawaited(platform.startTracking().catchError((Object _) {}));
      },
    );
  }

  /// [queueOnly]: something it depends on (the end-of-day reading) is still waiting, so it waits behind it and goes
  /// in order with the next send, never before it.
  Future<SendResult> sendReport({
    required String businessDate,
    int? orders,
    String? cash,
    bool? validDay,
    String? screenshotPath,
    String? notes,
    bool queueOnly = false,
    int? session,
  }) async {
    final id = await outbox.add(
      'report',
      {
        'business_date': businessDate,
        'orders_count': ?orders,
        'cash_amount': ?cash,
        'valid_day': ?validDay,
        'notes': notes,
        // the session it is written for, fixed now: a retry or a late delivery stays in it (an older server: none)
        if (session != null && session > 0 && (today?.canStartAgain ?? false)) 'session': session,
      },
      {'screenshot_sha256': ?screenshotPath},
    );
    if (queueOnly) {
      await _readLocal();
      return SendResult.queued;
    }
    return _sendNow(
      id,
      after: () async {
        await loadReports();
        await loadCash();
      },
    );
  }

  /// The driver's correction of a report: directly until it is approved (FR-DWR-06), after that as a request with
  /// his reason, decided by the office (BR-06). Only a new screenshot is uploaded; the rest goes as it stands.
  Future<SendResult> changeReport(
    Report report, {
    int? orders,
    String? cash,
    bool? validDay,
    String? screenshotPath,
    String? notes,
    String? reason,
  }) async {
    final id = await outbox.add(
      report.editable ? 'report_edit' : 'report_change',
      {
        'report_id': report.id,
        'orders_count': ?orders,
        'cash_amount': ?cash,
        'valid_day': ?validDay,
        'notes': notes,
        'reason': ?reason,
      },
      {'screenshot_sha256': ?screenshotPath},
    );
    return _sendNow(id, after: loadReports);
  }

  /// A maintenance request for the vehicle the driver holds. The id is made here, once: a retry after a lost
  /// answer is recognised by the server ("request_exists") instead of creating a second request.
  /// [centerId]: the center he takes the car to, when requests go straight to the center.
  Future<SendResult> sendMaintenance({
    required String kind,
    required String description,
    int? km,
    required List<String> photoPaths,
    String? centerId,
  }) async {
    final id = await outbox.add(
      'maintenance',
      {
        'client_ref': const Uuid().v4(),
        'kind': kind,
        'description': description,
        'odometer_km': km,
        'center_id': ?centerId,
      },
      {for (var i = 0; i < photoPaths.length; i++) 'photos.$i': photoPaths[i]},
    );
    return _sendNow(id, after: loadMaintenance);
  }

  /// He collected the car from the center: the odometer from the camera, at the photo's time. The car is his
  /// again, so his day can start.
  Future<SendResult> sendPickup({
    required String requestId,
    required int km,
    required String photoPath,
    required DateTime takenAt,
  }) async {
    final id = await outbox.add(
      'maintenance_pickup',
      {'request_id': requestId, 'odometer_km': km, 'picked_up_at': takenAt.toUtc().toIso8601String()},
      {'odometer_photo': photoPath},
    );
    return _sendNow(
      id,
      after: () async {
        await Future.wait([loadMaintenance(), loadToday()]);
        unawaited(platform.startTracking().catchError((Object _) {}));
      },
    );
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

  /// Fuel he paid from his cash: the amount (3 decimals), the receipt's camera photo and its time, the odometer if
  /// he gives it. Through the outbox: sent now, or queued until the network is back.
  Future<SendResult> sendFuel({
    required DateTime paidAt,
    required String amount,
    int? odometerKm,
    String? notes,
    required String receiptPath,
  }) async {
    final id = await outbox.add(
      'fuel',
      {
        'client_ref': const Uuid().v4(),
        'paid_at': paidAt.toUtc().toIso8601String(),
        'amount': amount,
        'odometer_km': ?odometerKm,
        'notes': ?notes,
      },
      {'receipt_sha256': receiptPath},
    );
    return _sendNow(id, after: loadFuel);
  }

  /// The month's statement: screenshots of the platform's monthly summary and the figures read on them.
  Future<SendResult> sendStatement({
    required String month,
    int? validDays,
    int? orders,
    String? hours,
    required List<String> screenshotPaths,
  }) async {
    final id = await outbox.add(
      'statement',
      {'month': month, 'valid_days': validDays, 'orders': orders, 'hours': hours},
      {for (var i = 0; i < screenshotPaths.length; i++) 'screenshots.$i': screenshotPaths[i]},
    );
    return _sendNow(id, after: loadStatements);
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
