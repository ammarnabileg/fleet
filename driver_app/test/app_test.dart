import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:fleet_driver/app/state.dart';
import 'package:fleet_driver/core/api.dart';
import 'package:fleet_driver/core/models.dart' show kuwaitDay;
import 'package:fleet_driver/core/tokens.dart';
import 'package:fleet_driver/main.dart';
import 'package:fleet_driver/ui/screens/fuel.dart';
import 'package:fleet_driver/ui/photos.dart';
import 'package:fleet_driver/ui/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/intl.dart' show DateFormat;

import 'support.dart';

/// The whole app against a scripted server: what the driver taps, what reaches the API.
Future<void> loadFonts() async {
  final plex = FontLoader('IBMPlexSansArabic');
  for (final w in ['Regular', 'Medium', 'SemiBold', 'Bold']) {
    plex.addFont(rootBundle.load('assets/fonts/IBMPlexSansArabic-$w.ttf'));
  }
  await plex.load();
  final sdk = Platform.environment['FLUTTER_ROOT'] ?? '/opt/flutter-sdk/flutter';
  final icons = File('$sdk/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf');
  if (icons.existsSync()) {
    await (FontLoader('MaterialIcons')..addFont(Future.value(ByteData.view(icons.readAsBytesSync().buffer)))).load();
  }
}

Future<String> testImage() async {
  final dir = await Directory.systemTemp.createTemp('img');
  final f = File('${dir.path}/odo.jpg');
  await f.writeAsBytes(
    base64Decode(
      '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP////////////////////////////////////////////////////////////////////////////////////8AAAA//////////////////9k=',
    ),
  );
  return f.path;
}

const nationalities = [
  {'value': 'الهند', 'ar': 'الهند', 'en': 'India'},
  {'value': 'مصر', 'ar': 'مصر', 'en': 'Egypt'},
  {'value': 'باكستان', 'ar': 'باكستان', 'en': 'Pakistan'},
];

var trackingStarts = 0; // how often the app asked the tracking service to start or report

class World {
  World(this.state, this.server);
  final AppState state;
  final FakeServer server;
}

Future<World> world({
  bool signedIn = true,
  Map<String, dynamic>? onboarding,
  Future<void> Function()? startTracking,
  Map<String, dynamic>? today,
  List<Map<String, dynamic>>? maintenance,
  List<Map<String, dynamic>>? accidents,
  List<Map<String, dynamic>>? fines,
  Map<String, dynamic>? fuel,
  Future<String?> Function(
    Map<String, dynamic> config, {
    required void Function(String token) onRefresh,
    required void Function() onMessage,
  })?
  pushToken,
}) async {
  final db = await testDb();
  final server = FakeServer();
  final tokens = TokenStore(db);
  if (signedIn) await tokens.save(tokensJson('1'));
  final api = Api(baseUrl: 'http://fleet.test', tokens: tokens, client: server.client);
  final state = AppState(
    db: db,
    api: api,
    pollEvery: null,
    platform: PhoneHooks(
      permissionsOk: () async => true,
      startTracking: startTracking ?? () async => trackingStarts++,
      stopTracking: () async {},
      deviceMeta: () async => {'platform': 'android', 'model': 'Test phone', 'app_version': '0.1.0'},
      pushToken: pushToken,
    ),
  );
  server.on(
    'GET',
    '/api/v1/i18n/catalog/ar',
    (r) => (
      200,
      {
        'lang': 'ar',
        'direction': 'rtl',
        'revision': 1,
        'messages': {
          'errors': {
            'reading_exists': 'سُجّلت قراءة نهاية اليوم من قبل',
            'otp_invalid': 'الرمز غير صحيح',
            'vehicle_plate_not_found': 'رقم اللوحة ده مش متسجل عندنا. راجع الرقم ودخّله صح.',
          },
        },
      },
    ),
  );
  server.on(
    'GET',
    '/api/v1/driver/onboarding',
    (r) => (
      200,
      onboarding ??
          {
            'required': false,
            'status': 'approved',
            'data': {},
            'review_note': null,
            'required_documents': [],
            'vehicle_photos': [],
            'document_types': [],
          },
    ),
  );
  server.on(
    'GET',
    '/api/v1/driver/today',
    (r) => (
      200,
      today ??
          {
            'custody': {
              'id': 'c1',
              'plate_number': '18/23456',
              'started_at': '2026-10-02T05:00:00Z',
              'last_odometer_km': 45100,
            },
            'start_day_done': false,
          },
    ),
  );
  server.on(
    'GET',
    '/api/v1/driver/cash',
    (r) => (
      200,
      {
        'posted': '42.500',
        'pending': '15.250',
        'total': '57.750',
        'alert_limit': '80.000',
        'receipts': [
          {
            'id': 'r1',
            'receipt_no': 12,
            'branch_id': 1,
            'amount': '20.000',
            'created_at': '2026-10-03T14:00:00Z',
            'driver_confirmed_at': null,
          },
        ],
      },
    ),
  );
  server.on(
    'GET',
    '/api/v1/driver/reports',
    (r) => (
      200,
      [
        {
          'id': 'p1',
          'driver': null,
          'company_id': 1,
          'vehicle_plate': '18/23456',
          'business_date': '2026-10-03',
          'orders_count': 24,
          'cash_amount': '18.500',
          'approved_cash': '18.500',
          'has_screenshot': true,
          'notes': null,
          'status': 'approved',
          'submitted_at': '2026-10-03T20:00:00Z',
          'reviewed_at': null,
          'review_note': null,
        },
      ],
    ),
  );
  server.on('GET', '/api/v1/driver/maintenance', (r) => (200, maintenance ?? []));
  server.on(
    'GET',
    '/api/v1/driver/maintenance/form',
    (r) => (
      200,
      {
        'direct_to_center': true,
        'centers': [
          {'id': 'k1', 'name': 'مركز النور', 'specialty': 'ميكانيكا', 'phone': '+965 2222 1100', 'address': 'الشويخ'},
        ],
      },
    ),
  );
  server.on('GET', '/api/v1/driver/accidents', (r) => (200, accidents ?? []));
  server.on('GET', '/api/v1/driver/fines', (r) => (200, fines ?? []));
  // no fuel route by default: an older server, the app offers no fuel
  if (fuel != null) server.on('GET', '/api/v1/driver/fuel', (r) => (200, fuel));
  return World(state, server);
}

Map<String, dynamic> scheme(
  String code,
  String name,
  String calculator, {
  String? perOrder,
  String? reducedRate,
  String? missingOrderRate,
  List<String> covers = const [],
  List<(String, String, String?)> steps = const [],
}) => {
  'id': 'id-$code',
  'code': code,
  'name': {'ar': name, 'en': code},
  'description': null,
  'calculator': calculator,
  'per_order': perOrder,
  'target_orders': 420,
  'required_valid_days': 28,
  'missing_order_rate': missingOrderRate,
  'reduced_rate': reducedRate,
  'bonus_when_reduced': false,
  'marks_when_reduced': false,
  'floor_at_zero': true,
  'company_covers': covers,
  'steps': [
    for (final (kind, threshold, amount) in steps) {'kind': kind, 'threshold': threshold, 'amount': amount},
  ],
};

final fixedScheme = scheme(
  'fixed_350',
  'سعر ثابت 0.350',
  'per_order',
  perOrder: '0.350',
  covers: ['maintenance', 'housing', 'gas', 'sim'],
);
final batchScheme = scheme(
  'batch',
  'نظام الباتش',
  'batch',
  steps: [('batch_rate', '2.000', '0.675'), ('batch_rate', '1.000', '0.700')],
);
final keetaScheme = scheme(
  'keeta_base',
  'كيتا الأساسي',
  'tiered_target',
  perOrder: '0.350',
  reducedRate: '0.200',
  missingOrderRate: '0.350',
  covers: ['maintenance'],
  steps: [
    ('tier_bonus', '450.000', '50.000'),
    ('tier_bonus', '540.000', '90.000'),
    ('marks_deduction', '3.000', '10.000'),
    ('marks_deduction', '4.000', '30.000'),
    ('marks_reduce', '5.000', null),
  ],
);

/// Brings a widget of the open screen into view: scrolls its list until the widget is built (a long form builds
/// its end only when near), then onto the screen.
Future<void> reveal(WidgetTester tester, Finder f) async {
  // the field typed in last keeps the focus and scrolls itself back on screen: the keyboard closes first
  FocusManager.instance.primaryFocus?.unfocus();
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 100)); // and its last scroll to the caret ends
  }
  if (f.evaluate().isEmpty) await tester.scrollUntilVisible(f, 200, scrollable: find.byType(Scrollable).first);
  await tester.ensureVisible(f);
  await tester.pump();
}

Future<void> pumpApp(WidgetTester tester, World w) async {
  tester.view.physicalSize = const Size(1080, 2280);
  tester.view.devicePixelRatio = 2.75;
  await tester.pumpWidget(DriverApp(state: w.state));
  await tester.runAsync(() => w.state.boot());
  await settle(tester);
}

/// Lets real I/O (files, the database, the fake server) progress between frames until no spinner is left.
Future<void> idle(WidgetTester tester) async {
  for (var i = 0; i < 100; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 15)));
    await tester.pump(const Duration(milliseconds: 50));
    if (find.byType(CircularProgressIndicator).evaluate().isEmpty) break;
  }
  await settle(tester);
}

Future<void> settle(WidgetTester tester) => tester.pumpAndSettle(
  const Duration(milliseconds: 100),
  EnginePhase.sendSemanticsUpdate,
  const Duration(seconds: 5),
);

Future<void> shot(WidgetTester tester, String name) async {
  if (Platform.environment['SCREENSHOTS'] != '1') return;
  await expectLater(find.byType(MaterialApp), matchesGoldenFile('screenshots/$name.png'));
}

void main() {
  setUpAll(loadFonts);

  testWidgets('sign in with the WhatsApp code, land on today with the vehicle in custody', (tester) async {
    final w = (await tester.runAsync(() => world(signedIn: false)))!;
    w.server.on('POST', '/api/v1/driver/auth/otp', (r) => (202, {'status': 'sent'}));
    w.server.on('POST', '/api/v1/driver/auth/verify', (r) => (200, tokensJson('9')));
    await pumpApp(tester, w);
    await shot(tester, '01-sign-in');
    await tester.enterText(find.byKey(const Key('phone')), '65001234');
    await tester.tap(find.byKey(const Key('send-code')));
    await idle(tester);
    final otp = jsonDecode(w.server.calls('/api/v1/driver/auth/otp').single.body) as Map;
    expect(otp['phone'], '+96565001234');
    expect((otp['device_uid'] as String).length, greaterThanOrEqualTo(8));
    await shot(tester, '02-code');
    await tester.enterText(find.byKey(const Key('code')), '123456');
    await tester.tap(find.byKey(const Key('verify')));
    await idle(tester);
    final verify = jsonDecode(w.server.calls('/api/v1/driver/auth/verify').single.body) as Map;
    expect((verify['code'], verify['model'], verify['device_uid']), ('123456', 'Test phone', otp['device_uid']));
    expect(find.textContaining('18/23456'), findsOneWidget);
    expect(find.byKey(const Key('start-day')), findsOneWidget);
    await shot(tester, '03-home');
  });

  testWidgets('a wrong code shows the server message, in Arabic', (tester) async {
    final w = (await tester.runAsync(() => world(signedIn: false)))!;
    w.server.on('POST', '/api/v1/driver/auth/otp', (r) => (202, {'status': 'sent'}));
    w.server.on('POST', '/api/v1/driver/auth/verify', (r) => (401, {'code': 'otp_invalid'}));
    await pumpApp(tester, w);
    await tester.enterText(find.byKey(const Key('phone')), '65001234');
    await tester.tap(find.byKey(const Key('send-code')));
    await idle(tester);
    await tester.enterText(find.byKey(const Key('code')), '000000');
    await tester.tap(find.byKey(const Key('verify')));
    await idle(tester);
    expect(find.text('الرمز غير صحيح'), findsOneWidget);
  });

  testWidgets('start of day: camera photo and reading go out with the photo time', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    final img = await tester.runAsync(testImage);
    final taken = DateTime.utc(2026, 10, 4, 5, 55);
    Photos.camera = (_) async => TakenPhoto(img!, taken, lat: 29.3, lng: 48.0);
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': 'c' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on('POST', '/api/v1/driver/odometer', (r) => (201, {'id': 'x'}));
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('start-day')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('odo-photo')));
    await idle(tester);
    await tester.enterText(find.byKey(const Key('km')), '45090');
    await tester.pump();
    expect(
      find.textContaining('أقل من آخر قراءة'),
      findsOneWidget,
      reason: 'warned before sending; the server flags it anyway',
    );
    await shot(tester, '04-start-day');
    await tester.enterText(find.byKey(const Key('km')), '45210');
    final startsBefore = trackingStarts;
    await tester.tap(find.byKey(const Key('send-reading')));
    await idle(tester);
    expect(trackingStarts, startsBefore + 1, reason: 'the service reports at once: its notification says at work');
    expect(w.server.calls('/api/v1/driver/files').single.url.queryParameters['source'], 'camera');
    final body = jsonDecode(w.server.calls('/api/v1/driver/odometer').single.body) as Map;
    expect(
      (body['kind'], body['value_km'], body['photo_sha256'], body['recorded_at']),
      ('start_day', 45210, 'c' * 64, '2026-10-04T05:55:00.000Z'),
    );
    expect(find.text('تم الإرسال'), findsOneWidget);
    await shot(tester, '05-sent');
  });

  testWidgets('no network: the reading is kept on the phone and shown as waiting', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    final img = await tester.runAsync(testImage);
    Photos.camera = (_) async => TakenPhoto(img!, DateTime.utc(2026, 10, 4, 6));
    await pumpApp(tester, w);
    w.server.routes.remove('POST /api/v1/driver/files');
    w.server.on('POST', '/api/v1/driver/files', (r) => throw const SocketException('offline'));
    await tester.tap(find.byKey(const Key('start-day')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('odo-photo')));
    await idle(tester);
    await tester.enterText(find.byKey(const Key('km')), '45210');
    await tester.tap(find.byKey(const Key('send-reading')));
    await idle(tester);
    expect(find.text('حُفظ على الهاتف'), findsOneWidget);
    await tester.tap(find.text('تم'));
    await settle(tester);
    expect(find.text('بانتظار الإرسال'), findsOneWidget);
    await shot(tester, '06-queued');
  });

  testWidgets('daily report: day, orders, cash with three decimals, the screenshot from the gallery', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    final img = await tester.runAsync(testImage);
    Photos.gallery = () async => TakenPhoto(img!, DateTime.now());
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': 'd' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on('POST', '/api/v1/driver/reports', (r) => (201, {'id': 'n'}));
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('daily-report')));
    await settle(tester);
    await tester.enterText(find.byKey(const Key('orders')), '27');
    await tester.enterText(find.byKey(const Key('cash')), '19.5');
    await tester.tap(find.byKey(const Key('screenshot')));
    await idle(tester);
    await shot(tester, '07-report');
    await reveal(tester, find.byKey(const Key('send-report')));
    await tester.tap(find.byKey(const Key('send-report')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/files').single.url.queryParameters['source'], 'upload');
    final body = jsonDecode(w.server.calls('/api/v1/driver/reports', method: 'POST').single.body) as Map;
    expect((body['orders_count'], body['cash_amount'], body['screenshot_sha256']), (27, '19.500', 'd' * 64));
    expect(RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(body['business_date'] as String), isTrue);
  });

  testWidgets('today\'s report after a started day: the end-of-day reading goes first', (tester) async {
    var ended = false;
    final w = (await tester.runAsync(
      () => world(
        today: {
          'custody': {
            'id': 'c1',
            'plate_number': '18/23456',
            'started_at': '2026-10-02T05:00:00Z',
            'last_odometer_km': 45210,
          },
          'start_day_done': true,
          'end_day_done': false,
        },
      ),
    ))!;
    final img = await tester.runAsync(testImage);
    final screenshot = await tester.runAsync(testImage); // each photo its own file: the outbox removes it once sent
    Photos.camera = (_) async => TakenPhoto(img!, DateTime.utc(2026, 10, 4, 18, 30));
    Photos.gallery = () async => TakenPhoto(screenshot!, DateTime.now());
    w.server.on(
      'GET',
      '/api/v1/driver/reports/form',
      (r) => (
        200,
        {
          'fields': ['orders', 'cash'],
          'screenshot': true,
          'end_reading': true,
        },
      ),
    );
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': (r.url.queryParameters['source'] == 'camera' ? 'c' : 'd') * 64}),
    );
    w.server.on('POST', '/api/v1/driver/odometer', (r) {
      ended = true;
      return (201, {'id': 'e'});
    });
    w.server.on(
      'GET',
      '/api/v1/driver/today',
      (r) => (
        200,
        {
          'custody': {
            'id': 'c1',
            'plate_number': '18/23456',
            'started_at': '2026-10-02T05:00:00Z',
            'last_odometer_km': 45210,
          },
          'start_day_done': true,
          'end_day_done': ended,
        },
      ),
    );
    w.server.on('POST', '/api/v1/driver/reports', (r) => (201, {'id': 'n'}));
    await pumpApp(tester, w);
    expect(find.byKey(const Key('end-day')), findsOneWidget);
    await tester.tap(find.byKey(const Key('daily-report')));
    await settle(tester);
    expect(find.byKey(const Key('end-reading')), findsOneWidget);
    // another day's report does not ask for it
    await tester.tap(find.text('أمس'));
    await settle(tester);
    expect(find.byKey(const Key('end-photo')), findsNothing);
    await tester.tap(find.text('اليوم'));
    await settle(tester);
    final list = find.byType(Scrollable).first;
    Future<void> reach(String key, {double step = 120}) async {
      await tester.scrollUntilVisible(find.byKey(Key(key)), step, scrollable: list);
      await reveal(tester, find.byKey(Key(key)));
      await tester.pumpAndSettle();
    }

    await reach('orders');
    await tester.enterText(find.byKey(const Key('orders')), '30');
    await reach('cash');
    await tester.enterText(find.byKey(const Key('cash')), '12');
    await reach('screenshot');
    await tester.tap(find.byKey(const Key('screenshot')));
    await idle(tester);
    await reach('send-report');
    await tester.tap(find.byKey(const Key('send-report')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/reports', method: 'POST'), isEmpty, reason: 'no odometer photo yet');
    await reach('end-photo', step: -120);
    await tester.tap(find.byKey(const Key('end-photo')));
    await idle(tester);
    await reach('end-km');
    await tester.enterText(find.byKey(const Key('end-km')), '45390');
    await shot(tester, '30-report-end-reading');
    await reach('send-report');
    await tester.tap(find.byKey(const Key('send-report')));
    await idle(tester);
    final sent = [
      for (final r in w.server.requests)
        if (r.method == 'POST' && r.url.path != '/api/v1/driver/files') r.url.path,
    ];
    expect(sent, ['/api/v1/driver/odometer', '/api/v1/driver/reports'], reason: 'the reading first');
    final reading = jsonDecode(w.server.calls('/api/v1/driver/odometer').single.body) as Map;
    expect(
      (reading['kind'], reading['value_km'], reading['photo_sha256'], reading['recorded_at']),
      ('end_day', 45390, 'c' * 64, '2026-10-04T18:30:00.000Z'),
    );
    final report = jsonDecode(w.server.calls('/api/v1/driver/reports', method: 'POST').single.body) as Map;
    expect((report['orders_count'], report['screenshot_sha256']), (30, 'd' * 64));
    await tester.tap(find.text('تم'));
    await settle(tester);
    expect(find.text('أنهيت اليوم'), findsOneWidget);
    expect(find.byKey(const Key('end-day')), findsNothing);
  });

  Map<String, dynamic> sentReport(String id, String day, String status, {String? note, bool pending = false}) => {
    'id': id,
    'driver': null,
    'company_id': 1,
    'vehicle_plate': '18/23456',
    'business_date': day,
    'orders_count': 24,
    'cash_amount': '18.500',
    'approved_cash': status == 'approved' ? '17.000' : null,
    'valid_day': null,
    'has_screenshot': true,
    'notes': null,
    'status': status,
    'submitted_at': '${day}T20:00:00Z',
    'reviewed_at': null,
    'review_note': note,
    'late': false,
    'deviations': <String>[],
    'change_pending': pending,
  };

  testWidgets('after ending the day he starts again: a new session, and its report adds to the day', (tester) async {
    final today = DateTime.now().toUtc().add(const Duration(hours: 3)).toIso8601String().substring(0, 10);
    var sessions = 1;
    var ended = true;
    Map<String, dynamic> day() => {
      'custody': {
        'id': 'c1',
        'plate_number': '18/23456',
        'started_at': '2026-10-02T05:00:00Z',
        'last_odometer_km': 45210,
      },
      'start_day_done': true,
      'end_day_done': ended,
      'sessions': sessions,
    };
    final w = (await tester.runAsync(() => world(today: day())))!;
    // each photo its own file: the outbox removes it once sent
    final photos = [for (var i = 0; i < 2; i++) (await tester.runAsync(testImage))!];
    final screenshot = await tester.runAsync(testImage);
    Photos.camera = (_) async => TakenPhoto(photos.removeAt(0), DateTime.now());
    Photos.gallery = () async => TakenPhoto(screenshot!, DateTime.now());
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': (r.url.queryParameters['source'] == 'camera' ? 'c' : 'd') * 64}),
    );
    w.server.on('POST', '/api/v1/driver/odometer', (r) {
      final kind = (jsonDecode(r.body) as Map)['kind'];
      if (kind == 'start_day') (sessions, ended) = (2, false);
      if (kind == 'end_day') ended = true;
      return (201, {'id': 'x'});
    });
    w.server.on('GET', '/api/v1/driver/today', (r) => (200, day()));
    w.server.on(
      'GET',
      '/api/v1/driver/reports/form',
      (r) => (
        200,
        {
          'fields': ['orders', 'cash'],
          'screenshot': true,
          'end_reading': true,
        },
      ),
    );
    w.server.on('GET', '/api/v1/driver/reports', (r) => (200, [sentReport('t1', today, 'submitted')]));
    w.server.on('POST', '/api/v1/driver/reports', (r) => (201, {'id': 'n'}));
    await pumpApp(tester, w);
    expect(find.text('أنهيت اليوم'), findsOneWidget);
    // within the session that ended, its report is edited, not sent twice (UAT-04)
    await tester.tap(find.byKey(const Key('daily-report')));
    await settle(tester);
    expect(find.byKey(const Key('report-exists')), findsOneWidget);
    await tester.state<NavigatorState>(find.byType(Navigator).first).maybePop();
    await settle(tester);

    await tester.tap(find.byKey(const Key('start-again')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('odo-photo')));
    await idle(tester);
    await tester.enterText(find.byKey(const Key('km')), '45300');
    await tester.tap(find.byKey(const Key('send-reading')));
    await idle(tester);
    expect((jsonDecode(w.server.calls('/api/v1/driver/odometer').single.body) as Map)['kind'], 'start_day');
    await tester.tap(find.text('تم'));
    await settle(tester);
    expect(find.byKey(const Key('start-again')), findsNothing);
    await tester.tap(find.byKey(const Key('end-day')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('odo-photo')));
    await idle(tester);
    await tester.enterText(find.byKey(const Key('km')), '45360');
    await tester.tap(find.byKey(const Key('send-reading')));
    await idle(tester);
    await tester.tap(find.text('تم'));
    await settle(tester);
    expect(find.byKey(const Key('start-again')), findsOneWidget);

    // the new session's report: the form, with what today already holds
    await tester.tap(find.byKey(const Key('daily-report')));
    await settle(tester);
    expect(find.byKey(const Key('report-exists')), findsNothing);
    expect(find.byKey(const Key('report-adds')), findsOneWidget);
    expect(find.textContaining('24'), findsWidgets);
    final list = find.byType(Scrollable).first;
    Future<void> reach(String key) async {
      await tester.scrollUntilVisible(find.byKey(Key(key)), 120, scrollable: list);
      await tester.pumpAndSettle();
    }

    await reach('orders');
    await tester.enterText(find.byKey(const Key('orders')), '6');
    await reach('cash');
    await tester.enterText(find.byKey(const Key('cash')), '3');
    await reach('screenshot');
    await tester.tap(find.byKey(const Key('screenshot')));
    await idle(tester);
    await reach('send-report');
    await tester.tap(find.byKey(const Key('send-report')));
    await idle(tester);
    final report = jsonDecode(w.server.calls('/api/v1/driver/reports', method: 'POST').single.body) as Map;
    expect(
      (report['business_date'], report['orders_count'], report['session']),
      (today, 6, 2),
      reason: 'the session it was written for goes with it: a retry stays in it',
    );
  });

  Map<String, dynamic> ended({int? sessions, Map<String, int>? recent}) => {
    'custody': {
      'id': 'c1',
      'plate_number': '18/23456',
      'started_at': '2026-10-02T05:00:00Z',
      'last_odometer_km': 45210,
    },
    'start_day_done': true,
    'end_day_done': true,
    'sessions': ?sessions,
    'recent': ?recent,
  };

  testWidgets('an older server that knows one session a day: no "start again" to refuse', (tester) async {
    final w = (await tester.runAsync(() => world(today: ended())))!;
    await pumpApp(tester, w);
    expect(find.text('أنهيت اليوم'), findsOneWidget);
    expect(find.byKey(const Key('start-again')), findsNothing);
  });

  testWidgets('started again with no signal: the queued start counts, so the session can be ended', (tester) async {
    final w = (await tester.runAsync(() => world(today: ended(sessions: 1))))!;
    final img = await tester.runAsync(testImage);
    Photos.camera = (_) async => TakenPhoto(img!, DateTime.now());
    await pumpApp(tester, w);
    w.server.routes.remove('POST /api/v1/driver/files');
    w.server.on('POST', '/api/v1/driver/files', (r) => throw const SocketException('offline'));
    await tester.tap(find.byKey(const Key('start-again')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('odo-photo')));
    await idle(tester);
    await tester.enterText(find.byKey(const Key('km')), '45300');
    await tester.tap(find.byKey(const Key('send-reading')));
    await idle(tester);
    await tester.tap(find.text('تم'));
    await settle(tester);
    expect(find.byKey(const Key('start-again')), findsNothing, reason: 'a second tap would only be refused');
    expect(find.byKey(const Key('end-day')), findsOneWidget);
    expect(w.state.sessionsToday, 2);
  });

  testWidgets('yesterday\'s second session: its report can still be sent, on its own', (tester) async {
    final yesterday = DateTime.now()
        .toUtc()
        .add(const Duration(hours: 3))
        .subtract(const Duration(days: 1))
        .toIso8601String()
        .substring(0, 10);
    final w = (await tester.runAsync(() => world(today: ended(sessions: 0, recent: {yesterday: 2}))))!;
    final screenshot = await tester.runAsync(testImage);
    Photos.gallery = () async => TakenPhoto(screenshot!, DateTime.now());
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': 'd' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on('GET', '/api/v1/driver/reports', (r) => (200, [sentReport('y1', yesterday, 'approved')]));
    w.server.on('POST', '/api/v1/driver/reports', (r) => (201, {'id': 'n'}));
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('daily-report')));
    await settle(tester);
    await tester.tap(find.text('أمس'));
    await settle(tester);
    expect(find.byKey(const Key('report-exists')), findsNothing);
    expect(find.byKey(const Key('report-adds')), findsOneWidget);
    final list = find.byType(Scrollable).first;
    Future<void> reach(String key) async {
      await tester.scrollUntilVisible(find.byKey(Key(key)), 120, scrollable: list);
      await tester.pumpAndSettle();
    }

    await reach('orders');
    await tester.enterText(find.byKey(const Key('orders')), '5');
    await reach('cash');
    await tester.enterText(find.byKey(const Key('cash')), '2');
    await reach('screenshot');
    await tester.tap(find.byKey(const Key('screenshot')));
    await idle(tester);
    await reach('send-report');
    await tester.tap(find.byKey(const Key('send-report')));
    await idle(tester);
    final body = jsonDecode(w.server.calls('/api/v1/driver/reports', method: 'POST').single.body) as Map;
    expect((body['business_date'], body['orders_count'], body['session']), (yesterday, 5, 2));
  });

  testWidgets('a report sent back: the office note, then corrected in place, never sent twice', (tester) async {
    final today = DateTime.now().toUtc().add(const Duration(hours: 3)).toIso8601String().substring(0, 10);
    final w = (await tester.runAsync(() => world()))!;
    w.server.on(
      'GET',
      '/api/v1/driver/reports',
      (r) => (200, [sentReport('t1', today, 'returned', note: 'اللقطة لا تظهر الكاش')]),
    );
    w.server.on('PATCH', '/api/v1/driver/reports/t1', (r) => (200, sentReport('t1', today, 'submitted')));
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('daily-report')));
    await settle(tester);
    // UAT-04: today is reported already: no second report, the way to edit it
    expect(find.byKey(const Key('report-exists')), findsOneWidget);
    expect(find.byKey(const Key('send-report')), findsNothing);
    await tester.tap(find.byKey(const Key('edit-sent')));
    await settle(tester);
    expect(find.text('تعديل التقرير'), findsWidgets);
    expect(find.textContaining('اللقطة لا تظهر الكاش'), findsOneWidget);
    expect(tester.widget<TextFormField>(find.byKey(const Key('cash'))).controller!.text, '18.500');
    await tester.enterText(find.byKey(const Key('cash')), '19.25');
    await shot(tester, '31-report-returned-edit');
    await reveal(tester, find.byKey(const Key('send-report')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('send-report')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/reports', method: 'POST'), isEmpty);
    expect(w.server.calls('/api/v1/driver/files'), isEmpty, reason: 'the screenshot stays unless replaced');
    final body = jsonDecode(w.server.calls('/api/v1/driver/reports/t1', method: 'PATCH').single.body) as Map;
    expect((body['cash_amount'], body['orders_count'], body.containsKey('report_id')), ('19.250', 24, false));
    expect(find.text('تم الإرسال'), findsOneWidget);
  });

  testWidgets('an approved report: a change is asked for with its reason, and waits for the office', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    w.server.on('GET', '/api/v1/driver/reports', (r) => (200, [sentReport('a1', '2026-10-03', 'approved')]));
    w.server.on('POST', '/api/v1/driver/reports/a1/change-request', (r) => (201, {'id': 'c1', 'status': 'pending'}));
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('daily-report')));
    await settle(tester);
    await tester.scrollUntilVisible(
      find.byKey(const Key('report-2026-10-03')),
      200,
      scrollable: find.byType(Scrollable).first,
    );
    await reveal(tester, find.byKey(const Key('report-2026-10-03')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('report-2026-10-03')));
    await settle(tester);
    expect(find.byKey(const Key('change-intro')), findsOneWidget);
    expect(
      tester.widget<TextFormField>(find.byKey(const Key('cash'))).controller!.text,
      '17.000',
      reason: 'the approved cash',
    );
    await tester.enterText(find.byKey(const Key('orders')), '26');
    await reveal(tester, find.byKey(const Key('send-report')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('send-report')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/reports/a1/change-request'), isEmpty, reason: 'the reason is required');
    await reveal(tester, find.byKey(const Key('change-reason')));
    await settle(tester);
    await tester.enterText(find.byKey(const Key('change-reason')), 'طلبان لم يظهرا في اللقطة');
    await shot(tester, '32-report-change-request');
    await reveal(tester, find.byKey(const Key('send-report')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('send-report')));
    await idle(tester);
    final body = jsonDecode(w.server.calls('/api/v1/driver/reports/a1/change-request').single.body) as Map;
    expect((body['orders_count'], body['cash_amount'], body['reason']), (26, '17.000', 'طلبان لم يظهرا في اللقطة'));
  });

  testWidgets('daily report on a platform that counts valid days: orders and the valid day, no cash', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    final img = await tester.runAsync(testImage);
    Photos.gallery = () async => TakenPhoto(img!, DateTime.now());
    w.server.on(
      'GET',
      '/api/v1/driver/reports/form',
      (r) => (
        200,
        {
          'fields': ['orders', 'valid_day'],
          'screenshot': true,
        },
      ),
    );
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': 'e' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on('POST', '/api/v1/driver/reports', (r) => (201, {'id': 'v'}));
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('daily-report')));
    await settle(tester);
    expect(find.byKey(const Key('cash')), findsNothing, reason: 'this platform does not ask for cash');
    await tester.enterText(find.byKey(const Key('orders')), '31');
    await tester.tap(find.byKey(const Key('screenshot')));
    await idle(tester);
    await reveal(tester, find.byKey(const Key('send-report')));
    await tester.tap(find.byKey(const Key('send-report')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/reports', method: 'POST'), isEmpty, reason: 'the valid day is required');
    await reveal(tester, find.text('يوم صالح'));
    await tester.tap(find.text('يوم صالح'));
    await settle(tester);
    await shot(tester, '25-report-valid-day');
    await reveal(tester, find.byKey(const Key('send-report')));
    await tester.tap(find.byKey(const Key('send-report')));
    await idle(tester);
    final body = jsonDecode(w.server.calls('/api/v1/driver/reports', method: 'POST').single.body) as Map;
    expect((body['orders_count'], body['valid_day'], body.containsKey('cash_amount')), (31, true, false));
  });

  testWidgets('cash: balance and a receipt to confirm', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    w.server.on('POST', '/api/v1/driver/cash/receipts/r1/confirm', (r) => (200, {'id': 'r1'}));
    await pumpApp(tester, w);
    await tester.tap(find.text('الكاش').last);
    await settle(tester);
    expect(find.textContaining('57.750'), findsOneWidget);
    await shot(tester, '08-cash');
    await tester.tap(find.text('أؤكد التسليم'));
    await settle(tester);
    await tester.tap(find.widgetWithText(FilledButton, 'أؤكد التسليم'));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/cash/receipts/r1/confirm'), hasLength(1));
  });

  testWidgets('cash: his movements, and a warning before the limit', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    w.server.on(
      'GET',
      '/api/v1/driver/cash',
      (r) => (
        200,
        {
          'posted': '50.000',
          'pending': '14.000',
          'total': '64.000',
          'alert_limit': '80.000',
          'near_limit': true,
          'receipts': [],
          'lines': [
            {
              'journal_id': 'j2',
              'kind': 'collection',
              'status': 'pending',
              'amount': '14.000',
              'business_date': '2026-10-04',
              'reason': null,
              'source_type': 'daily_report',
              'created_at': '2026-10-04T20:00:00Z',
            },
            {
              'journal_id': 'j1',
              'kind': 'adjustment',
              'status': 'posted',
              'amount': '-6.000',
              'business_date': '2026-10-03',
              'reason': 'فرق عد',
              'source_type': 'manual',
              'created_at': '2026-10-03T20:00:00Z',
            },
          ],
        },
      ),
    );
    await pumpApp(tester, w);
    await tester.tap(find.text('الكاش').last);
    await settle(tester);
    expect(find.byKey(const Key('cash-near-limit')), findsOneWidget);
    expect(find.textContaining('80.000'), findsWidgets);
    await tester.scrollUntilVisible(find.text('تسوية'), 200, scrollable: find.byType(Scrollable).first);
    expect(find.text('كاش تقرير يومي'), findsOneWidget);
    expect(find.textContaining('بانتظار المراجعة'), findsWidgets);
    expect(find.textContaining('فرق عد'), findsOneWidget);
    expect(find.text('\u2066+14.000\u2069'), findsOneWidget);
    expect(find.text('\u2066-6.000\u2069'), findsOneWidget);
    await shot(tester, '33-cash-movements');
  });

  testWidgets('his profile, without the full IBAN', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    w.server.on(
      'GET',
      '/api/v1/driver/profile',
      (r) => (
        200,
        {
          'name': {'ar': 'سالم العتيبي', 'en': 'Salem'},
          'employee_number': 'D-120',
          'phone': '+96550001234',
          'civil_id': '290010112345',
          'nationality': null,
          'job_title': null,
          'hire_date': null,
          'company': {'ar': 'شركة النقل', 'en': 'Transport Co'},
          'branch': null,
          'platform': {'ar': 'منصة س', 'en': 'X'},
          'platform_driver_id': 'KT-77',
          'bank_name': 'الوطني',
          'iban_last4': '0101',
          'payment_method': 'bank',
        },
      ),
    );
    await pumpApp(tester, w);
    await tester.tap(find.text('الحساب').last);
    await settle(tester);
    expect(find.byKey(const Key('profile')), findsOneWidget);
    expect(find.text('سالم العتيبي'), findsOneWidget);
    expect(find.textContaining('290010112345'), findsOneWidget);
    expect(find.textContaining('KT-77'), findsOneWidget);
    expect(find.textContaining('****0101'), findsOneWidget);
    await shot(tester, '34-profile');
  });

  testWidgets('my car: the vehicle and its last reading, then another asked for by its plate with the reason', (
    tester,
  ) async {
    final w = (await tester.runAsync(() => world()))!;
    Map<String, dynamic> car(Map<String, dynamic>? request) => {
      'vehicle': {
        'plate_number': '18/23456',
        'make': 'Kia',
        'model': 'Pegas',
        'year': 2023,
        'color': 'أبيض',
        'since': '2026-10-02T05:00:00Z',
        'last_odometer_km': 45210,
        'last_reading_at': '2026-10-04T05:55:00Z',
        'registration_expiry': '2027-03-01',
      },
      'change_request': request,
    };
    w.server.on('GET', '/api/v1/driver/vehicle', (r) => (200, car(null)));
    w.server.on('POST', '/api/v1/driver/vehicle-change-requests', (r) {
      // a plate the office does not have is refused: he types it again
      if ((jsonDecode(r.body) as Map)['requested_plate'] != '12-34567') {
        return (422, {'code': 'vehicle_plate_not_found'});
      }
      return (
        201,
        car({
          'id': 'v1',
          'status': 'pending',
          'reason': 'المكيف لا يعمل',
          'requested_plate': '12-34567',
          'note': null,
          'created_at': '2026-10-04T08:00:00Z',
          'decided_at': null,
        }),
      );
    });
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('my-car')));
    await settle(tester);
    expect(find.textContaining('Kia · Pegas · 2023'), findsOneWidget);
    expect(find.textContaining('45,210'), findsOneWidget);
    expect(find.textContaining('2027-03-01'), findsOneWidget);
    await tester.tap(find.byKey(const Key('ask-change')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('send-change')));
    await settle(tester);
    expect(
      w.server.calls('/api/v1/driver/vehicle-change-requests'),
      isEmpty,
      reason: 'the plate and reason are required',
    );
    await tester.enterText(find.byKey(const Key('change-reason')), 'المكيف لا يعمل');
    await tester.tap(find.byKey(const Key('send-change')));
    await settle(tester);
    expect(w.server.calls('/api/v1/driver/vehicle-change-requests'), isEmpty, reason: 'the plate is required');
    final plateField = tester.widget<TextField>(
      find.descendant(of: find.byKey(const Key('change-plate')), matching: find.byType(TextField)),
    );
    expect(plateField.textDirection, TextDirection.ltr);

    // a plate not found: the message under the field, the dialog stays open
    await tester.enterText(find.byKey(const Key('change-plate')), '99-1');
    await tester.tap(find.byKey(const Key('send-change')));
    await idle(tester);
    expect(find.text('رقم اللوحة ده مش متسجل عندنا. راجع الرقم ودخّله صح.'), findsOneWidget);
    expect(find.byKey(const Key('send-change')), findsOneWidget);
    expect(find.byKey(const Key('change-pending')), findsNothing);

    await tester.enterText(find.byKey(const Key('change-plate')), ' 12-34567 ');
    await tester.tap(find.byKey(const Key('send-change')));
    await idle(tester);
    final body = jsonDecode(w.server.calls('/api/v1/driver/vehicle-change-requests').last.body) as Map;
    expect(body, {'requested_plate': '12-34567', 'reason': 'المكيف لا يعمل'});
    expect(find.byKey(const Key('send-change')), findsNothing);
    expect(find.byKey(const Key('change-pending')), findsOneWidget);
    expect(find.textContaining('12-34567'), findsOneWidget);
    expect(find.byKey(const Key('ask-change')), findsNothing);
    await shot(tester, '35-my-car');
  });

  testWidgets('no car: he registers the one he takes, it waits for the office, refused then approved', (tester) async {
    final w = (await tester.runAsync(
      () => world(today: {'custody': null, 'start_day_done': false, 'end_day_done': false}),
    ))!;
    final img = await tester.runAsync(testImage);
    final taken = DateTime.utc(2026, 10, 4, 6, 10);
    Photos.camera = (_) async => TakenPhoto(img!, taken);
    Map<String, dynamic>? claim = {
      'id': 'k0',
      'status': 'rejected',
      'plate': '18-111',
      'odometer_km': 900,
      'claimed_at': '2026-10-03T06:00:00Z',
      'created_at': '2026-10-03T06:01:00Z',
      'note': 'العربية في الصيانة',
      'decided_at': '2026-10-03T07:00:00Z',
    };
    w.server.on(
      'GET',
      '/api/v1/driver/vehicle',
      (r) => (200, {'vehicle': null, 'change_request': null, 'claim': claim}),
    );
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': 'c' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on('POST', '/api/v1/driver/vehicle-claims', (r) {
      final body = jsonDecode(r.body) as Map;
      if (body['plate'] != '12-34567') return (422, {'code': 'vehicle_plate_not_found'});
      claim = {...claim!, 'id': 'k1', 'status': 'pending', 'plate': '12-34567', 'note': null, 'decided_at': null};
      return (201, {'vehicle': null, 'change_request': null, 'claim': claim});
    });
    Future<void> send() async {
      await tester.tap(find.byKey(const Key('send-claim')));
      await idle(tester);
    }

    await pumpApp(tester, w);
    tester.view.physicalSize = const Size(1080, 4400); // the whole form on screen
    await settle(tester);
    // refused before: the reason, and the button again
    expect(find.byKey(const Key('claim-rejected')), findsOneWidget);
    expect(find.textContaining('العربية في الصيانة'), findsOneWidget);
    await tester.tap(find.byKey(const Key('claim-vehicle')));
    await settle(tester);

    await send();
    expect(w.server.calls('/api/v1/driver/vehicle-claims'), isEmpty, reason: 'the plate and the reading are required');
    final plateField = tester.widget<TextField>(
      find.descendant(of: find.byKey(const Key('claim-plate')), matching: find.byType(TextField)),
    );
    expect(plateField.textDirection, TextDirection.ltr);
    await tester.enterText(find.byKey(const Key('claim-plate')), '99-1');
    await tester.enterText(find.byKey(const Key('claim-km')), '45300');
    await send();
    expect(w.server.calls('/api/v1/driver/vehicle-claims'), isEmpty, reason: 'the odometer photo is required');
    expect(find.text('الصورة مطلوبة'), findsOneWidget);
    tester.state<ScaffoldMessengerState>(find.byType(ScaffoldMessenger)).removeCurrentSnackBar();
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('claim-odo-photo')));
    await idle(tester);
    await tester.tap(find.byKey(const Key('claim-photo')));
    await idle(tester);

    // a plate the office does not have: the message under the field, the screen stays to correct it
    await send();
    expect(w.server.calls('/api/v1/driver/vehicle-claims'), hasLength(1));
    expect(find.text('رقم اللوحة ده مش متسجل عندنا. راجع الرقم ودخّله صح.'), findsOneWidget);
    expect(find.byKey(const Key('send-claim')), findsOneWidget);
    expect(await tester.runAsync(() => w.state.outbox.items()), isEmpty, reason: 'refused: nothing left to send');

    await tester.enterText(find.byKey(const Key('claim-plate')), ' 12-34567 ');
    await send();
    final calls = w.server.calls('/api/v1/driver/vehicle-claims');
    expect(calls, hasLength(2));
    final body = jsonDecode(calls.last.body) as Map;
    expect(
      (body['plate'], body['odometer_km'], body['photo_sha256'], '${body['photos']}', body['recorded_at']),
      ('12-34567', 45300, 'c' * 64, '[${'c' * 64}]', '2026-10-04T06:10:00.000Z'),
    );
    expect(body['client_ref'], isNot((jsonDecode(calls.first.body) as Map)['client_ref']));
    expect(w.server.calls('/api/v1/driver/files').every((r) => r.url.queryParameters['source'] == 'camera'), isTrue);

    // back home: waiting for the office, no button
    expect(find.byKey(const Key('send-claim')), findsNothing);
    expect(find.byKey(const Key('claim-pending')), findsOneWidget);
    expect(find.textContaining('12-34567'), findsOneWidget);
    expect(find.byKey(const Key('claim-vehicle')), findsNothing);
    await shot(tester, '36-claim-pending');

    // approved: the car is his, as any handover
    w.server.on(
      'GET',
      '/api/v1/driver/today',
      (r) => (
        200,
        {
          'custody': {
            'id': 'c9',
            'plate_number': '12-34567',
            'started_at': '2026-10-04T06:10:00Z',
            'last_odometer_km': 45300,
          },
          'start_day_done': false,
          'end_day_done': false,
        },
      ),
    );
    await tester.runAsync(w.state.refresh);
    await settle(tester);
    expect(find.byKey(const Key('claim-pending')), findsNothing);
    expect(find.byKey(const Key('start-day')), findsOneWidget);
  });

  testWidgets('no car: the register button only once the server said so; a refusal told reloads it', (tester) async {
    final w = (await tester.runAsync(
      () => world(today: {'custody': null, 'start_day_done': false, 'end_day_done': false}),
    ))!;
    final img = await tester.runAsync(testImage);
    Photos.camera = (_) async => TakenPhoto(img!, DateTime.utc(2026, 10, 4, 6, 10));
    final items = <Map<String, dynamic>>[];
    w.server.on('GET', '/api/v1/driver/notifications', (r) => (200, {'unread': items.length, 'items': items}));
    // "my car" cannot be read: nothing offered, on home or on the screen
    w.server.on('GET', '/api/v1/driver/vehicle', (r) => (503, {'code': 'unavailable'}));
    await pumpApp(tester, w);
    expect(find.byKey(const Key('claim-vehicle')), findsNothing);
    expect(find.byKey(const Key('claim-pending')), findsNothing);

    Map<String, dynamic>? claim = {
      'id': 'k1',
      'status': 'pending',
      'plate': '12-34567',
      'odometer_km': 900,
      'claimed_at': '2026-10-04T06:00:00Z',
      'created_at': '2026-10-04T06:01:00Z',
      'note': null,
      'decided_at': null,
    };
    w.server.on(
      'GET',
      '/api/v1/driver/vehicle',
      (r) => (200, {'vehicle': null, 'change_request': null, 'claim': claim}),
    );
    await tester.runAsync(w.state.resumed);
    await settle(tester);
    expect(find.byKey(const Key('claim-pending')), findsOneWidget);

    // the office refused it: the notice reloads "my car", the reason shows and the button is back
    claim = {...claim, 'status': 'rejected', 'note': 'العربية مع حد تاني', 'decided_at': '2026-10-04T07:00:00Z'};
    items.insert(0, {
      'id': 'n1',
      'kind': 'vehicle_claim_rejected',
      'message': 'المكتب رفض طلبك',
      'entity_type': null,
      'entity_id': null,
      'created_at': '2026-10-04T07:00:00Z',
      'read': false,
    });
    await tester.runAsync(w.state.loadNotices);
    await idle(tester);
    expect(find.byKey(const Key('claim-rejected')), findsOneWidget);
    expect(find.textContaining('العربية مع حد تاني'), findsOneWidget);

    // sent while another one waits (from another phone, say): told, not taken as sent
    w.server.on('POST', '/api/v1/driver/files', (r) => (201, {'sha256': 'c' * 64}));
    w.server.on('POST', '/api/v1/driver/vehicle-claims', (r) => (409, {'code': 'vehicle_claim_pending'}));
    tester.view.physicalSize = const Size(1080, 4400);
    await tester.tap(find.byKey(const Key('claim-vehicle')));
    await settle(tester);
    await tester.enterText(find.byKey(const Key('claim-plate')), '12-34567');
    await tester.enterText(find.byKey(const Key('claim-km')), '45300');
    await tester.tap(find.byKey(const Key('claim-odo-photo')));
    await idle(tester);
    await tester.tap(find.byKey(const Key('send-claim')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/vehicle-claims'), hasLength(1));
    expect(find.byKey(const Key('send-claim')), findsOneWidget, reason: 'still on the form');
    expect(find.byType(SnackBar), findsOneWidget);
    expect(await tester.runAsync(() => w.state.outbox.items()), isEmpty);
  });

  testWidgets('my car not readable: the error and a retry, never a car shown from before', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    var up = false;
    w.server.on(
      'GET',
      '/api/v1/driver/vehicle',
      (r) => up
          ? (
              200,
              {
                'vehicle': {
                  'plate_number': '18/23456',
                  'make': 'Kia',
                  'model': null,
                  'year': null,
                  'color': null,
                  'since': '2026-10-02T05:00:00Z',
                  'last_odometer_km': 45100,
                  'last_reading_at': null,
                  'registration_expiry': null,
                },
                'change_request': null,
                'claim': null,
              },
            )
          : (503, {'code': 'unavailable'}),
    );
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('my-car')));
    await idle(tester);
    expect(find.byKey(const Key('car-retry')), findsOneWidget);
    expect(find.byKey(const Key('claim-vehicle')), findsNothing);
    up = true;
    await tester.tap(find.byKey(const Key('car-retry')));
    await idle(tester);
    expect(find.byKey(const Key('car-last-km')), findsOneWidget);
  });

  testWidgets('his car swapped by the office: told, the app shows the new car and nothing of the old one', (
    tester,
  ) async {
    final w = (await tester.runAsync(() => world()))!;
    final items = <Map<String, dynamic>>[];
    w.server.on('GET', '/api/v1/driver/notifications', (r) => (200, {'unread': items.length, 'items': items}));
    Map<String, dynamic> car(String plate, String make, int km, String expiry) => {
      'vehicle': {
        'plate_number': plate,
        'make': make,
        'model': null,
        'year': null,
        'color': null,
        'since': '2026-10-02T05:00:00Z',
        'last_odometer_km': km,
        'last_reading_at': '2026-10-04T05:55:00Z',
        'registration_expiry': expiry,
      },
      'change_request': null,
      'claim': null,
    };
    var mine = car('18/23456', 'Kia', 45100, '2027-03-01');
    w.server.on('GET', '/api/v1/driver/vehicle', (r) => (200, mine));
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('my-car')));
    await settle(tester);
    expect(find.textContaining('18/23456'), findsOneWidget);
    expect(find.textContaining('Kia'), findsOneWidget);

    // the office swapped his car: the server has the new one, and a notice tells the phone (push, or the next look)
    mine = car('30/777', 'Toyota', 61200, '2028-01-15');
    w.server.on(
      'GET',
      '/api/v1/driver/today',
      (r) => (
        200,
        {
          'custody': {
            'id': 'c2',
            'plate_number': '30/777',
            'make': 'Toyota',
            'started_at': '2026-10-04T08:00:00Z',
            'last_odometer_km': 61200,
          },
          'start_day_done': false,
          'end_day_done': false,
        },
      ),
    );
    items.insert(0, {
      'id': 'n9',
      'kind': 'vehicle_swapped',
      'message': 'اتبدّلت عربيتك: سلّمت 18/23456 واستلمت 30/777',
      'entity_type': null,
      'entity_id': null,
      'created_at': '2026-10-04T08:00:00Z',
      'read': false,
    });
    final before = w.server.calls('/api/v1/driver/vehicle').length;
    await tester.runAsync(w.state.loadNotices);
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/vehicle').length, greaterThan(before), reason: 'my car read again');
    // the open "my car" screen: the new car, its reading and registration; nothing of the old one
    expect(find.textContaining('30/777'), findsOneWidget);
    expect(find.textContaining('Toyota'), findsOneWidget);
    expect(find.textContaining('61,200'), findsOneWidget);
    expect(find.textContaining('2028-01-15'), findsOneWidget);
    expect(find.textContaining('18/23456'), findsNothing);
    expect(find.textContaining('Kia'), findsNothing);
    expect(find.textContaining('45,100'), findsNothing);
    expect(w.state.today!.custody!.plate, '30/777');
    // and home: the new car on its card
    Navigator.of(tester.element(find.byKey(const Key('car-last-km')))).pop();
    await settle(tester);
    expect(find.textContaining('30/777'), findsWidgets);
    expect(find.textContaining('18/23456'), findsNothing);
    // the same notice seen again changes nothing more
    final after = w.server.calls('/api/v1/driver/vehicle').length;
    await tester.runAsync(w.state.loadNotices);
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/vehicle').length, after);
  });

  testWidgets('documents: their expiry, and a renewal from the phone checked by the office', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    final img = await tester.runAsync(testImage);
    Photos.gallery = () async => TakenPhoto(img!, DateTime.now());
    Map<String, dynamic> doc(String code, String ar, String state, {int? days, Map<String, dynamic>? renewal}) => {
      'type_code': code,
      'type_name': {'ar': ar, 'en': code},
      'number': state == 'missing' ? null : 'N-1',
      'expiry_date': state == 'missing' ? null : '2026-10-17',
      'days_left': days,
      'state': state,
      'renewable': true,
      'renewal': renewal,
    };
    var sent = false;
    w.server.on(
      'GET',
      '/api/v1/driver/documents',
      (r) => (
        200,
        [
          doc(
            'residence',
            'الإقامة',
            'expiring',
            days: 10,
            renewal: sent
                ? {
                    'id': 'rn1',
                    'type_code': 'residence',
                    'type_name': null,
                    'number': 'RES-2',
                    'expiry_date': '2027-10-01',
                    'status': 'pending',
                    'created_at': '2026-10-04T08:00:00Z',
                    'decided_at': null,
                    'note': null,
                  }
                : null,
          ),
          doc('driving_license', 'رخصة القيادة', 'missing'),
        ],
      ),
    );
    w.server.on('POST', '/api/v1/driver/files', (r) => (201, {'sha256': 'f' * 64}));
    w.server.on('POST', '/api/v1/driver/documents/renewals', (r) {
      sent = true;
      return (201, {'id': 'rn1', 'status': 'pending'});
    });
    await pumpApp(tester, w);
    await tester.tap(find.text('الحساب').last);
    await settle(tester);
    await tester.tap(find.byKey(const Key('my-documents')));
    await settle(tester);
    expect(find.text('ينتهي خلال 10 يوم'), findsOneWidget);
    expect(find.text('غير مسجل'), findsOneWidget);
    await shot(tester, '36-documents');
    await tester.tap(find.byKey(const Key('renew-residence')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('send-renewal')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/documents/renewals'), isEmpty, reason: 'the new expiry date is required');
    await tester.tap(find.byKey(const Key('renewal-expiry')));
    await settle(tester);
    final ok = MaterialLocalizations.of(tester.element(find.byType(DatePickerDialog))).okButtonLabel;
    await tester.tap(find.text(ok));
    await settle(tester);
    await tester.enterText(find.byKey(const Key('renewal-number')), 'RES-2');
    await tester.tap(find.byKey(const Key('renewal-photo')));
    await idle(tester);
    await tester.tap(find.byKey(const Key('send-renewal')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/files').single.url.queryParameters['source'], 'upload');
    final body = jsonDecode(w.server.calls('/api/v1/driver/documents/renewals').single.body) as Map;
    final inAYear = DateTime.now().add(const Duration(days: 365));
    expect((body['type_code'], body['number'], body['file_sha256']), ('residence', 'RES-2', 'f' * 64));
    expect(body['expiry_date'], inAYear.toIso8601String().substring(0, 10));
    expect(find.text('تم الإرسال'), findsOneWidget);
    await tester.tap(find.text('تم'));
    await settle(tester);
    await tester.tap(find.byKey(const Key('my-documents')));
    await idle(tester);
    expect(find.text('التجديد بانتظار مراجعة المكتب'), findsOneWidget);
    expect(find.byKey(const Key('renew-residence')), findsNothing, reason: 'one waiting renewal at a time');
  });

  testWidgets('self-registration: details, documents, vehicle photos from the camera, then review', (tester) async {
    final w = (await tester.runAsync(
      () => world(
        onboarding: {
          'required': true,
          'status': 'rejected',
          'data': {},
          'review_note': 'صورة الإقامة غير واضحة',
          'require_bank': true,
          'required_documents': ['residence'],
          'vehicle_photos': ['front', 'back'],
          'document_types': [
            {
              'code': 'residence',
              'name': {'ar': 'الإقامة', 'en': 'Residence'},
              'requires_expiry': false,
            },
          ],
          'nationalities': nationalities,
        },
      ),
    ))!;
    final img = await tester.runAsync(testImage);
    Photos.camera = (_) async => TakenPhoto(img!, DateTime.now());
    Photos.gallery = () async => TakenPhoto(img!, DateTime.now());
    var n = 0;
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': '${n++}'.padLeft(64, 'e'), 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    Map<String, dynamic>? saved;
    w.server.on('PUT', '/api/v1/driver/onboarding', (r) {
      saved = jsonDecode(r.body) as Map<String, dynamic>;
      return (
        200,
        {
          'required': true,
          'status': 'draft',
          'data': saved,
          'review_note': null,
          'require_bank': true,
          'required_documents': ['residence'],
          'vehicle_photos': ['front', 'back'],
          'document_types': [
            {
              'code': 'residence',
              'name': {'ar': 'الإقامة', 'en': 'Residence'},
              'requires_expiry': false,
            },
          ],
          'nationalities': nationalities,
        },
      );
    });
    await pumpApp(tester, w);
    expect(find.textContaining('صورة الإقامة غير واضحة'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('civil')), '٢٩٠٠١٠١١٢٣٤٥'); // Arabic digits become 0-9
    await tester.tap(find.byKey(const Key('nationality'))); // picked from the server's list, never typed
    await settle(tester);
    await tester.enterText(find.byKey(const Key('nationality-search')), 'ind');
    await settle(tester);
    expect(find.byKey(const Key('nat-Egypt')), findsNothing);
    await tester.tap(find.byKey(const Key('nat-India')));
    await settle(tester);
    // as a banking app copies it: invisible direction marks, a no-break space, dashes
    final lrm = String.fromCharCode(0x200E), nbsp = String.fromCharCode(0xA0);
    await tester.enterText(find.byKey(const Key('iban')), '${lrm}kw81${nbsp}cbku-0000 0000 0000 1234 5601 01$lrm');
    expect(tester.widget<TextField>(find.byKey(const Key('iban'))).controller!.text, 'KW81CBKU0000000000001234560101');
    await tester.enterText(find.byKey(const Key('bank')), 'بنك الكويت الوطني');
    await shot(tester, '09-onboarding-data');
    Future<void> next() async {
      await tester.tap(find.byKey(const Key('ob-next')));
      await idle(tester);
    }

    Future<void> tapTile(String label, {bool sheet = false}) async {
      await reveal(tester, find.text(label).first);
      await tester.tap(find.text(label).first);
      await idle(tester);
      if (sheet) {
        await tester.tap(find.text('من المعرض'));
        await idle(tester);
      }
      await idle(tester);
    }

    await next();
    await tapTile('الوجه', sheet: true);
    await tapTile('الظهر', sheet: true);
    await shot(tester, '10-onboarding-docs');
    await next();
    await tester.enterText(find.byKey(const Key('plate')), '18/23456');
    await tester.enterText(find.byKey(const Key('ob-km')), '45000');
    await tapTile('صورة العداد');
    await tapTile('الأمام');
    await tapTile('الخلف');
    await shot(tester, '11-onboarding-vehicle');
    await next();
    await shot(tester, '12-onboarding-review');
    expect((saved!['civil_id'], saved!['nationality']), ('290010112345', 'الهند'));
    expect((saved!['iban'], saved!['bank_name']), ('KW81CBKU0000000000001234560101', 'بنك الكويت الوطني'));
    final docs = saved!['documents'] as List;
    expect((docs.single['front_sha256'] as String).length, 64);
    final vehicle = saved!['vehicle'] as Map;
    expect(
      (vehicle['plate_number'], vehicle['odometer_km'], (vehicle['photos'] as List).length),
      ('18/23456', 45000, 2),
    );
    final sources = [for (final r in w.server.calls('/api/v1/driver/files')) r.url.queryParameters['source']];
    expect(sources, [
      'upload',
      'upload',
      'camera',
      'camera',
      'camera',
    ], reason: 'vehicle and odometer photos from the camera only');
    final submit = tester.widget<FilledButton>(
      find.descendant(of: find.byKey(const Key('ob-submit')), matching: find.byType(FilledButton)),
    );
    expect(submit.onPressed, isNotNull, reason: 'everything required is there');
  });

  testWidgets('self-registration: what the office has on file is shown locked and never sent', (tester) async {
    final ob = {
      'required': true,
      'status': 'draft',
      // an old draft with his own values: none of them is shown or sent once the office has the field
      'data': {'civil_id': '2900101123', 'nationality': 'باكستان', 'bank_name': 'بنك آخر'},
      'review_note': null,
      'require_bank': true,
      'required_documents': [],
      'vehicle_photos': [],
      'document_types': [],
      'nationalities': nationalities,
      'known': {
        'name': {'ar': 'أحمد علي', 'en': 'Ahmed Ali'},
        'employee_number': 'E-17',
        'phone': '+96550000017',
        'civil_id': '288020212345',
        'nationality': 'مصر',
        'bank_name': 'بنك الخليج',
        'iban_last4': '0101',
        'locked': ['civil_id', 'nationality', 'iban', 'bank_name'],
      },
    };
    final w = (await tester.runAsync(() => world(onboarding: ob)))!;
    Map<String, dynamic>? saved;
    w.server.on('PUT', '/api/v1/driver/onboarding', (r) {
      saved = jsonDecode(r.body) as Map<String, dynamic>;
      return (200, {...ob, 'data': saved});
    });
    await pumpApp(tester, w);
    TextField field(String key) => tester.widget<TextField>(
      find.descendant(of: find.byKey(Key(key)), matching: find.byType(TextField), matchRoot: true).first,
    );
    for (final (key, value) in [
      ('known-name', 'أحمد علي'),
      ('known-number', 'E-17'),
      ('known-phone', '+96550000017'),
      ('civil', '288020212345'),
      ('nationality', 'مصر'),
      ('iban', '•••• 0101'),
      ('bank', 'بنك الخليج'),
    ]) {
      final f = field(key);
      expect((f.enabled, f.controller!.text), (false, value), reason: key);
    }
    await shot(tester, '37-onboarding-on-file');
    await tester.tap(find.byKey(const Key('nationality')));
    await settle(tester);
    expect(find.byKey(const Key('nationality-search')), findsNothing, reason: 'locked: no list');
    await tester.tap(find.byKey(const Key('ob-next')));
    await idle(tester);
    expect(
      [
        for (final f in ['civil_id', 'nationality', 'iban', 'bank_name']) saved![f],
      ],
      [null, null, null, null],
      reason: 'the office\'s values stay on the server',
    );
    for (var i = 0; i < 2; i++) {
      await tester.tap(find.byKey(const Key('ob-next')));
      await idle(tester);
    }
    expect(find.text('أكمل: السيارة'), findsOneWidget, reason: 'nothing on file is asked again');
    expect(find.textContaining('288020212345'), findsWidgets);
  });

  testWidgets('self-registration: a wrong civil ID or IBAN is pointed at before sending; a refusal names the field', (
    tester,
  ) async {
    final ob = {
      'required': true,
      'status': 'draft',
      'data': {'nationality': 'هندي'},
      'review_note': null,
      'require_bank': true,
      'required_documents': [],
      'vehicle_photos': [],
      'document_types': [],
      'nationalities': nationalities,
    };
    final w = (await tester.runAsync(() => world(onboarding: ob)))!;
    w.server.on(
      'PUT',
      '/api/v1/driver/onboarding',
      (r) => (
        422,
        {
          'code': 'validation_error',
          'errors': [
            {
              'loc': ['body', 'bank_name'],
              'msg': 'String should have at most 60 characters',
              'type': 'string_too_long',
            },
          ],
        },
      ),
    );
    await pumpApp(tester, w);
    await tester.enterText(find.byKey(const Key('civil')), '29001011239'); // 11 digits
    await tester.enterText(find.byKey(const Key('iban')), 'KW81CBKU0000000000001234560102'); // a check digit off
    await tester.tap(find.byKey(const Key('ob-next')));
    await idle(tester);
    expect(find.text('الرقم المدني 12 رقماً'), findsOneWidget);
    expect(find.text('في الآيبان حرف أو رقم غلط (أرقام التحقق لا تطابق): انسخه من تطبيق البنك'), findsOneWidget);
    expect(w.server.calls('/api/v1/driver/onboarding', method: 'PUT'), isEmpty, reason: 'nothing sent');
    await shot(tester, '38-onboarding-field-errors');
    await tester.enterText(find.byKey(const Key('iban')), 'KW81CBKU000000000000123456010'); // one character short
    await tester.tap(find.byKey(const Key('ob-next')));
    await idle(tester);
    expect(find.text('الآيبان الكويتي 30 خانة تبدأ بـ KW، والمكتوب هنا 29'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('civil')), '290010112399');
    await tester.enterText(find.byKey(const Key('iban')), 'KW81CBKU0000000000001234560101');
    await tester.tap(find.byKey(const Key('ob-next')));
    await idle(tester);
    expect(find.text('الرقم المدني 12 رقماً'), findsNothing);
    expect(find.text('راجع هذه الخانات: اسم البنك'), findsOneWidget);
    final sent = jsonDecode(w.server.calls('/api/v1/driver/onboarding', method: 'PUT').single.body) as Map;
    expect(sent['nationality'], isNull, reason: 'typed before the list: he picks it again');
  });

  test('activation links: the token after "#" (App Link) or "?t=" (fallback page); anything else ignored', () {
    final token = 'A' * 32;
    expect(AppState.activationToken(Uri.parse('https://fleet.example.com/activate#t=$token')), token);
    expect(AppState.activationToken(Uri.parse('btfleet://activate?t=$token')), token);
    expect(AppState.activationToken(Uri.parse('https://fleet.example.com/other#t=$token')), isNull);
    expect(AppState.activationToken(Uri.parse('https://fleet.example.com/activate#t=short')), isNull);
  });

  testWidgets('the periodic look rebuilds the screens only when the tracking state or the outbox moved', (
    tester,
  ) async {
    final w = (await tester.runAsync(() => world()))!;
    await pumpApp(tester, w);
    var rebuilds = 0;
    w.state.addListener(() => rebuilds++);
    await tester.runAsync(() async {
      await w.state.pollLocal();
      await w.state.pollLocal();
    });
    expect(rebuilds, 0, reason: 'nothing changed: no rebuild every 15 s');
    await tester.runAsync(() async {
      await w.state.db.put('tracking_state', '{"required": true, "queue": 2, "updated_at": "a"}');
      await w.state.pollLocal();
    });
    expect(rebuilds, 1);
    await tester.runAsync(() async {
      await w.state.db.put('tracking_state', '{"required": true, "queue": 2, "updated_at": "b"}');
      await w.state.pollLocal();
    });
    expect(rebuilds, 1, reason: 'only the time stamp moved, which no screen shows');
  });

  testWidgets('the home screen does not wait for the tracking service to come up', (tester) async {
    final never = Completer<void>();
    final w = (await tester.runAsync(() => world(startTracking: () => never.future)))!;
    await pumpApp(tester, w);
    expect(find.byKey(const Key('start-day')), findsOneWidget);
  });

  testWidgets('maintenance: type, description and camera photos go out as one request', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    final img = await tester.runAsync(testImage);
    Photos.camera = (_) async => TakenPhoto(img!, DateTime.now());
    var n = 0;
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': '${++n}' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on(
      'POST',
      '/api/v1/driver/maintenance',
      (r) => (
        201,
        {
          'id': 'm1',
          'number': 41,
          'vehicle_plate': '18/23456',
          'kind': 'tyres',
          'description': 'Flat',
          'status': 'requested',
          'center': null,
          'created_at': '2026-10-04T07:00:00Z',
          'ready_at': null,
          'picked_up_at': null,
          'decision_note': null,
        },
      ),
    );
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('maintenance')));
    await idle(tester);
    await tester.tap(find.byKey(const Key('mnt-center')));
    await settle(tester);
    await tester.tap(find.text('مركز النور · ميكانيكا').last);
    await settle(tester);
    await tester.tap(find.byKey(const Key('mnt-kind')));
    await settle(tester);
    await tester.tap(find.text('إطارات').last);
    await settle(tester);
    await tester.enterText(find.byKey(const Key('mnt-description')), 'الإطار الخلفي الأيسر مثقوب');
    await tester.enterText(find.byKey(const Key('mnt-km')), '45230');
    await tester.tap(find.byKey(const Key('mnt-photo')));
    await idle(tester);
    await tester.tap(find.byKey(const Key('mnt-photo')));
    await idle(tester);
    await shot(tester, '13-maintenance');
    await reveal(tester, find.byKey(const Key('mnt-send')));
    await tester.tap(find.byKey(const Key('mnt-send')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/files').every((r) => r.url.queryParameters['source'] == 'camera'), isTrue);
    final body = jsonDecode(w.server.calls('/api/v1/driver/maintenance', method: 'POST').single.body) as Map;
    expect(
      (body['kind'], body['description'], body['odometer_km'], body['center_id']),
      ('tyres', 'الإطار الخلفي الأيسر مثقوب', 45230, 'k1'),
    );
    expect(body['photos'], ['1' * 64, '2' * 64]);
    expect(body['client_ref'], isA<String>());
    expect(find.text('تم الإرسال'), findsOneWidget);
  });

  testWidgets('a vehicle ready at the center is announced on the home screen with where to collect it', (tester) async {
    final w = (await tester.runAsync(
      () => world(
        maintenance: [
          {
            'id': 'm1',
            'number': 41,
            'vehicle_plate': '18/23456',
            'kind': 'mechanical',
            'description': 'Noise',
            'status': 'ready',
            'center': {'id': 'c', 'name': 'مركز النور', 'phone': '+965 2222 1100', 'address': 'الشويخ'},
            'created_at': '2026-10-03T07:00:00Z',
            'ready_at': '2026-10-04T09:00:00Z',
            'picked_up_at': null,
            'decision_note': null,
          },
        ],
      ),
    ))!;
    await pumpApp(tester, w);
    expect(find.textContaining('جاهزة للاستلام من مركز النور'), findsOneWidget);
    expect(find.textContaining('الشويخ'), findsOneWidget);
    await shot(tester, '14-maintenance-ready');
  });

  Map<String, dynamic> directForm() => {
    'direct_to_center': true,
    'centers': [
      {'id': 'k1', 'name': 'مركز النور', 'specialty': 'ميكانيكا', 'phone': '+965 2222 1100', 'address': 'الشويخ'},
      {'id': 'k2', 'name': 'مركز الفجر', 'specialty': 'كهرباء', 'phone': null, 'address': 'الري، شارع 4'},
    ],
  };

  testWidgets('no center open to pick: he is told to call the office, and nothing is sent', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    w.server.on('GET', '/api/v1/driver/maintenance/form', (r) => (200, {'direct_to_center': true, 'centers': []}));
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('maintenance')));
    await idle(tester);
    expect(find.text('مفيش مركز صيانة متاح، كلّم المكتب'), findsOneWidget);
    expect(find.byKey(const Key('mnt-send')), findsNothing);
    expect(find.byKey(const Key('mnt-center')), findsNothing);
  });

  testWidgets('straight to the center: he picks where he leaves the car and the request goes to it', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    w.server.on('GET', '/api/v1/driver/maintenance/form', (r) => (200, directForm()));
    final img = await tester.runAsync(testImage);
    Photos.camera = (_) async => TakenPhoto(img!, DateTime.now());
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': 'c' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on(
      'POST',
      '/api/v1/driver/maintenance',
      (r) => (
        201,
        {
          'id': 'm1',
          'number': 42,
          'vehicle_plate': '18/23456',
          'kind': 'electrical',
          'description': 'x',
          'status': 'referred',
          'center': {'id': 'k2', 'name': 'مركز الفجر', 'phone': null, 'address': 'الري، شارع 4'},
          'created_at': '2026-10-04T07:00:00Z',
          'ready_at': null,
          'picked_up_at': null,
          'decision_note': null,
        },
      ),
    );
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('maintenance')));
    await idle(tester);
    expect(find.textContaining('الطلب يوصل للمركز على طول'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('mnt-description')), 'البطارية لا تشحن');
    await reveal(tester, find.byKey(const Key('mnt-send')));
    await tester.tap(find.byKey(const Key('mnt-send')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/maintenance', method: 'POST'), isEmpty, reason: 'the center is required');
    await reveal(tester, find.byKey(const Key('mnt-center')));
    await tester.tap(find.byKey(const Key('mnt-center')));
    await settle(tester);
    await tester.tap(find.text('مركز الفجر · كهرباء').last);
    await settle(tester);
    expect(find.textContaining('الري، شارع 4'), findsOneWidget);
    await shot(tester, '15-maintenance-direct');
    await reveal(tester, find.byKey(const Key('mnt-send')));
    await tester.tap(find.byKey(const Key('mnt-send')));
    await idle(tester);
    final body = jsonDecode(w.server.calls('/api/v1/driver/maintenance', method: 'POST').single.body) as Map;
    expect((body['center_id'], body['description']), ('k2', 'البطارية لا تشحن'));
  });

  testWidgets('his car at the center: still his, no day starts; he collects it and works with it again', (
    tester,
  ) async {
    var collected = false;
    var ready = false;
    Map<String, dynamic> request() => {
      'id': 'm1',
      'number': 41,
      'vehicle_plate': '18/23456',
      'kind': 'mechanical',
      'description': 'Noise',
      'status': collected ? 'picked_up' : (ready ? 'ready' : 'received'),
      'center': {'id': 'k1', 'name': 'مركز النور', 'phone': '+965 2222 1100', 'address': 'الشويخ'},
      'created_at': '2026-10-03T07:00:00Z',
      'ready_at': ready ? '2026-10-04T09:00:00Z' : null,
      'picked_up_at': null,
      'decision_note': null,
      'direct': true,
      'pickup_in_app': ready && !collected,
    };
    final w = (await tester.runAsync(() => world()))!;
    w.server.on('GET', '/api/v1/driver/maintenance', (r) => (200, [request()]));
    w.server.on(
      'GET',
      '/api/v1/driver/today',
      (r) => (
        200,
        {
          'custody': {
            'id': 'c1',
            'plate_number': '18/23456',
            'started_at': '2026-10-01T10:00:00Z',
            'last_odometer_km': collected ? 45300 : 45200,
            'in_maintenance': !collected,
            'maintenance_center': collected ? null : 'مركز النور',
          },
          'start_day_done': false,
          'end_day_done': false,
        },
      ),
    );
    final img = await tester.runAsync(testImage);
    final taken = DateTime.utc(2026, 10, 4, 10, 5);
    Photos.camera = (_) async => TakenPhoto(img!, taken);
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': 'c' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on('POST', '/api/v1/driver/maintenance/m1/picked-up', (r) {
      collected = true;
      return (200, request());
    });
    await pumpApp(tester, w);
    // at the center: the car is his, but no work day starts with it
    expect(find.text('عربيتك في الصيانة عند مركز النور'), findsOneWidget);
    expect(find.byKey(const Key('start-day')), findsNothing, reason: 'no work with a car at the center');
    expect(find.byKey(const Key('mnt-picked-up-41')), findsNothing, reason: 'not ready yet');
    await shot(tester, '16-maintenance-at-center');
    // ready: he collects it with the odometer from the camera
    ready = true;
    await tester.drag(find.byKey(const Key('in-maintenance')), const Offset(0, 400)); // pulled to refresh
    await idle(tester);
    await tester.tap(find.byKey(const Key('mnt-picked-up-41')));
    await settle(tester);
    expect(find.text('استلام السيارة من المركز'), findsOneWidget);
    await tester.tap(find.byKey(const Key('odo-photo')));
    await idle(tester);
    await tester.enterText(find.byKey(const Key('km')), '45300');
    await tester.tap(find.byKey(const Key('send-reading')));
    await idle(tester);
    final body = jsonDecode(w.server.calls('/api/v1/driver/maintenance/m1/picked-up').single.body) as Map;
    expect(
      (body['odometer_km'], body['odometer_photo'], body['picked_up_at'], body.containsKey('request_id')),
      (45300, 'c' * 64, '2026-10-04T10:05:00.000Z', false),
    );
    await tester.tap(find.text('تم'));
    await settle(tester);
    expect(find.byKey(const Key('in-maintenance')), findsNothing);
    expect(find.byKey(const Key('start-day')), findsOneWidget, reason: 'he works with it again: his day can start');
  });

  Map<String, dynamic> accident({
    String stage = 'reported',
    bool police = false,
    String? liability,
    String? percent,
    Map<String, dynamic>? deduction,
  }) => {
    'id': 'a1',
    'number': 12,
    'vehicle_plate': '18/23456',
    'occurred_at': '2026-10-04T06:30:00Z',
    'description': 'صدمني من الخلف عند الإشارة',
    'stage': stage,
    'has_police_report': police,
    'liability': liability,
    'liability_percent': percent,
    'deduction': deduction,
    'created_at': '2026-10-04T06:35:00Z',
  };

  testWidgets('an accident: at least 3 camera photos, then it goes out with time and place', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    final img = await tester.runAsync(testImage);
    Photos.camera = (_) async => TakenPhoto(img!, DateTime.now(), lat: 29.37, lng: 47.97);
    var n = 0;
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': '${++n}' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on('POST', '/api/v1/driver/accidents', (r) => (201, accident()));
    await pumpApp(tester, w);
    await reveal(tester, find.byKey(const Key('accident')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('accident')));
    await idle(tester);
    expect(find.textContaining('112'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('acc-description')), 'صدمني من الخلف عند الإشارة');
    await tester.tap(find.byKey(const Key('acc-injuries')));
    await settle(tester);
    await tester.enterText(find.byKey(const Key('acc-injuries-note')), 'ألم في الرقبة');
    await tester.enterText(find.byKey(const Key('acc-other-party')), 'بيك أب أبيض 12345');
    for (var i = 0; i < 2; i++) {
      await reveal(tester, find.byKey(const Key('acc-photo')));
      await settle(tester);
      await tester.tap(find.byKey(const Key('acc-photo')));
      await idle(tester);
    }
    await tester.scrollUntilVisible(find.byKey(const Key('acc-send')), 200, scrollable: find.byType(Scrollable).first);
    await settle(tester);
    await tester.tap(find.byKey(const Key('acc-send')));
    await idle(tester);
    expect(find.byKey(const Key('acc-photos-missing')), findsOneWidget);
    expect(w.server.calls('/api/v1/driver/accidents', method: 'POST'), isEmpty);
    await reveal(tester, find.byKey(const Key('acc-photo')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('acc-photo')));
    await idle(tester);
    await shot(tester, '15-accident');
    await tester.scrollUntilVisible(find.byKey(const Key('acc-send')), 200, scrollable: find.byType(Scrollable).first);
    await settle(tester);
    await tester.tap(find.byKey(const Key('acc-send')));
    await idle(tester);
    final body = jsonDecode(w.server.calls('/api/v1/driver/accidents', method: 'POST').single.body) as Map;
    expect(body['photos'], ['1' * 64, '2' * 64, '3' * 64]);
    expect((body['lat'], body['lng'], body['injuries'], body['injuries_note']), (29.37, 47.97, true, 'ألم في الرقبة'));
    expect(body['other_party'], 'بيك أب أبيض 12345');
    expect(body.containsKey('police_report'), isFalse);
    expect(DateTime.parse(body['occurred_at'] as String).isBefore(DateTime.now()), isTrue);
    expect(find.text('تم الإرسال'), findsOneWidget);
  });

  testWidgets('waiting for the police report: a banner on the home screen, sent later from the list', (tester) async {
    final w = (await tester.runAsync(() => world(accidents: [accident()])))!;
    final img = await tester.runAsync(testImage);
    Photos.camera = (_) async => fail('the police report comes from the phone files, not the camera');
    Photos.gallery = () async => TakenPhoto(img!, DateTime.now());
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': 'c' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on('POST', '/api/v1/driver/accidents/a1/police-report', (r) => (200, accident(police: true)));
    await pumpApp(tester, w);
    expect(find.textContaining('بانتظار محضر الشرطة'), findsOneWidget);
    await tester.tap(find.byKey(const Key('police-banner-12')));
    await idle(tester);
    await tester.dragUntilVisible(
      find.byKey(const Key('acc-send-police-12')),
      find.byType(ListView).last,
      const Offset(0, -300),
    );
    await settle(tester);
    await tester.tap(find.byKey(const Key('acc-send-police-12')));
    await idle(tester);
    final call = w.server.calls('/api/v1/driver/accidents/a1/police-report').single;
    expect(jsonDecode(call.body), {'number': null, 'file_sha256': 'c' * 64});
    expect(w.server.calls('/api/v1/driver/files').single.url.queryParameters['source'], 'upload');
    expect(find.text('تم الإرسال'), findsOneWidget);
  });

  testWidgets('the outcome and the deduction in monthly installments are shown to the driver', (tester) async {
    final w = (await tester.runAsync(
      () => world(
        accidents: [
          accident(
            stage: 'outcome_recorded',
            police: true,
            liability: 'driver',
            percent: '100.00',
            deduction: {
              'total': '150.000',
              'installments': 3,
              'schedule': [
                {'month': '2026-11-01', 'amount': '50.000'},
                {'month': '2026-12-01', 'amount': '50.000'},
                {'month': '2027-01-01', 'amount': '50.000'},
              ],
            },
          ),
        ],
      ),
    ))!;
    await pumpApp(tester, w);
    expect(find.textContaining('بانتظار محضر الشرطة'), findsNothing);
    await reveal(tester, find.byKey(const Key('accident')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('accident')));
    await idle(tester);
    await tester.dragUntilVisible(
      find.byKey(const Key('acc-deduction-12')),
      find.byType(ListView).last,
      const Offset(0, -300),
    );
    await settle(tester);
    expect(find.text('المسؤولية عليك'), findsOneWidget);
    expect(find.textContaining('150.000'), findsOneWidget);
    expect(find.textContaining('\u206650.000'), findsNWidgets(3));
    expect(find.textContaining('01-2027'), findsOneWidget);
    expect(find.byKey(const Key('acc-send-police-12')), findsNothing);
    await shot(tester, '16-accident-deduction');
  });

  testWidgets('traffic fines: the company decides, a deducted one shows its installments', (tester) async {
    final w = (await tester.runAsync(
      () => world(
        fines: [
          {
            'id': 'f1',
            'number': 7,
            'vehicle_plate': '18/23456',
            'occurred_at': '2026-10-02T15:10:00Z',
            'violation': 'تجاوز السرعة',
            'location_text': 'طريق الملك فهد',
            'amount': '30.000',
            'status': 'charged',
            'deduction': {
              'total': '30.000',
              'installments': 2,
              'schedule': [
                {'month': '2026-11-01', 'amount': '15.000'},
                {'month': '2026-12-01', 'amount': '15.000'},
              ],
            },
          },
          {
            'id': 'f2',
            'number': 8,
            'vehicle_plate': '18/23456',
            'occurred_at': '2026-10-03T09:00:00Z',
            'violation': 'وقوف خاطئ',
            'location_text': null,
            'amount': '5.000',
            'status': 'company',
            'deduction': null,
          },
        ],
      ),
    ))!;
    await pumpApp(tester, w);
    await reveal(tester, find.byKey(const Key('fines')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('fines')));
    await idle(tester);
    expect(find.text('تُخصم من راتبك'), findsOneWidget);
    expect(find.text('على الشركة'), findsOneWidget);
    expect(find.byKey(const Key('fine-deduction-7')), findsOneWidget);
    expect(find.textContaining('\u206615.000'), findsNWidgets(2));
    expect(find.byKey(const Key('fine-deduction-8')), findsNothing);
    await shot(tester, '17-fines');
  });

  testWidgets('monthly statement: valid days and screenshots from the platform app go out for review', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    final img = await tester.runAsync(testImage);
    Photos.gallery = () async => TakenPhoto(img!, DateTime.now());
    Map<String, dynamic> view(List<Map<String, dynamic>> statements) => {
      'platform': {
        'id': 1,
        'code': 'by_days',
        'name': {'ar': 'المنصة أ', 'en': 'Platform A'},
      },
      'driver_fields': ['valid_days'],
      'months': ['2026-09-01', '2026-10-01'],
      'statements': statements,
    };
    final rejected = {
      'id': 's0',
      'month': '2026-09-01',
      'status': 'rejected',
      'declared': {'valid_days': 30},
      'valid_days': 30,
      'orders': null,
      'hours': null,
      'review_note': 'اللقطة لشهر آخر',
      'submitted_at': '2026-10-01T08:00:00Z',
    };
    var n = 0;
    w.server.on('GET', '/api/v1/driver/statements', (r) => (200, view([rejected])));
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': '${n++}'.padLeft(64, 'a'), 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on('POST', '/api/v1/driver/statements', (r) => (201, view([rejected])));
    await pumpApp(tester, w);
    await tester.dragUntilVisible(
      find.byKey(const Key('statement')),
      find.byType(ListView).first,
      const Offset(0, -200),
    );
    await settle(tester);
    await tester.tap(find.byKey(const Key('statement')));
    await idle(tester);
    expect(find.textContaining('المنصة أ'), findsOneWidget);
    await tester.dragUntilVisible(
      find.textContaining('اللقطة لشهر آخر'),
      find.byType(ListView).first,
      const Offset(0, -200),
    );
    await settle(tester);
    expect(find.textContaining('اللقطة لشهر آخر'), findsOneWidget);
    await tester.dragUntilVisible(
      find.byKey(const Key('send-statement')),
      find.byType(ListView).first,
      const Offset(0, 200),
    );
    await settle(tester);
    await tester.tap(find.byKey(const Key('send-statement')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/statements', method: 'POST'), isEmpty, reason: 'valid days are required');
    await tester.enterText(find.byKey(const Key('statement-valid_days')), '22');
    await tester.tap(find.byKey(const Key('send-statement')));
    await idle(tester);
    expect(find.text('أضف لقطة شاشة واحدة على الأقل'), findsOneWidget);
    for (var i = 0; i < 2; i++) {
      await tester.tap(find.byKey(const Key('statement-shot')));
      await idle(tester);
    }
    await shot(tester, '18-statement');
    await reveal(tester, find.byKey(const Key('send-statement')));
    await tester.tap(find.byKey(const Key('send-statement')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/files').map((c) => c.url.queryParameters['source']).toSet(), {'upload'});
    final body = jsonDecode(w.server.calls('/api/v1/driver/statements', method: 'POST').single.body) as Map;
    expect((body['month'], body['valid_days']), ('2026-10-01', 22));
    expect(body['screenshots'], ['0'.padLeft(64, 'a'), '1'.padLeft(64, 'a')]);
  });

  testWidgets('payslips: each month in the rows of the platform sheet, with the net', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    w.server.on(
      'GET',
      '/api/v1/driver/payslips',
      (r) => (
        200,
        [
          {
            'month': '2026-09-01',
            'status': 'paid',
            'platform': {
              'id': 1,
              'code': 'by_days',
              'name': {'ar': 'المنصة أ'},
            },
            'rows': [
              {'code': 'valid_days', 'header': 'عدد الأيام الصالحة', 'value': 22},
              {'code': 'invalid_days_deduction', 'header': 'خصم الأيام الغير صالحة', 'value': '40.000'},
              {'code': 'net', 'header': 'صافي الراتب', 'value': '130.000'},
            ],
            'gross': '320.000',
            'deductions': '190.000',
            'net': '130.000',
          },
        ],
      ),
    );
    await pumpApp(tester, w);
    await tester.dragUntilVisible(
      find.byKey(const Key('payslips')),
      find.byType(ListView).first,
      const Offset(0, -200),
    );
    await settle(tester);
    await tester.tap(find.byKey(const Key('payslips')));
    await idle(tester);
    expect(find.text('عدد الأيام الصالحة'), findsOneWidget);
    expect(find.textContaining('40.000'), findsOneWidget);
    expect(find.text('مدفوع'), findsOneWidget);
    final net = tester.widget<Text>(find.byKey(const Key('payslip-net')));
    expect(net.data, contains('130.000'));
    await shot(tester, '19-payslips');
  });

  testWidgets('payslip on a pay scheme: each item with its reason, penalties in red, what was not taken', (
    tester,
  ) async {
    final w = (await tester.runAsync(() => world()))!;
    w.server.on(
      'GET',
      '/api/v1/driver/payslips',
      (r) => (
        200,
        [
          {
            'month': '2026-09-01',
            'status': 'approved',
            'platform': null,
            'rows': [
              {'code': 'net', 'header': 'صافي الراتب', 'value': '0.000'},
            ],
            'scheme': {
              'name': {'ar': 'كيتا الأساسي', 'en': 'Keeta base'},
            },
            'breakdown': [
              {
                'code': 'orders_pay',
                'amount': '20.000',
                'why': {'orders': 100, 'rate': '0.200', 'reduced_by': 'star_day'},
              },
              {
                'code': 'missing_target',
                'amount': '-112.000',
                'why': {'target': 420, 'missing': 320, 'rate': '0.350'},
              },
              {
                'code': 'uncovered_penalty',
                'amount': '92.000',
                'why': {'uncovered': '92.000'},
              },
            ],
            'gross': '20.000',
            'deductions': '20.000',
            'net': '0.000',
          },
        ],
      ),
    );
    await pumpApp(tester, w);
    await tester.dragUntilVisible(
      find.byKey(const Key('payslips')),
      find.byType(ListView).first,
      const Offset(0, -200),
    );
    await settle(tester);
    await tester.tap(find.byKey(const Key('payslips')));
    await idle(tester);
    expect(find.text('كيف حسب نظامك الشهر: كيتا الأساسي'), findsOneWidget);
    expect(find.text('\u2066100\u2069 طلب × \u20660.200\u2069 د.ك · السعر المخفض: فوّت Star Day'), findsOneWidget);
    expect(find.text('\u2066320\u2069 طلب ناقص عن \u2066420\u2069 × \u20660.350\u2069 د.ك'), findsOneWidget);
    final penalty = tester.widget<Text>(
      find.descendant(of: find.byKey(const Key('pay-item-missing_target')), matching: find.textContaining('112.000')),
    );
    expect(penalty.style!.color, AppColors.danger);
    expect(find.text('خصومات غير محصلة (للمراجعة)'), findsOneWidget);
    expect(find.byKey(const Key('object-payslip')), findsNothing); // an older server sends no run: nothing to name
    await shot(tester, '28-payslip-scheme');
  });

  Map<String, dynamic> objectionSlip() => {
    'run_id': 'run-9',
    'month': '2026-09-01',
    'status': 'approved',
    'platform': null,
    'rows': [
      {'code': 'gross', 'header': 'إجمالي الراتب', 'value': '140.000'},
      {'code': 'net', 'header': 'صافي الراتب', 'value': '123.000'},
    ],
    'scheme': {
      'name': {'ar': 'كيتا الأساسي', 'en': 'Keeta base'},
    },
    'breakdown': [
      {
        'code': 'orders_pay',
        'amount': '140.000',
        'why': {'orders': 400, 'rate': '0.350'},
      },
      {
        'code': 'missing_target',
        'amount': '-7.000',
        'why': {'target': 420, 'missing': 20, 'rate': '0.350'},
      },
    ],
    'gross': '140.000',
    'deductions': '17.000',
    'net': '123.000',
    'uncollected': '0.000',
  };

  Future<World> openPayslips(WidgetTester tester, {List<Map<String, dynamic>> mine = const []}) async {
    final w = (await tester.runAsync(() => world()))!;
    w.server.on('GET', '/api/v1/driver/payslips', (r) => (200, [objectionSlip()]));
    w.server.on('GET', '/api/v1/driver/objections', (r) => (200, mine));
    await pumpApp(tester, w);
    await tester.dragUntilVisible(
      find.byKey(const Key('payslips')),
      find.byType(ListView).first,
      const Offset(0, -200),
    );
    await settle(tester);
    await tester.tap(find.byKey(const Key('payslips')));
    await idle(tester);
    return w;
  }

  testWidgets('objection to one payslip line: the reason, a photo from the gallery, sent with the line', (
    tester,
  ) async {
    final img = await tester.runAsync(testImage);
    Photos.gallery = () async => TakenPhoto(img!, DateTime.now());
    final w = await openPayslips(tester);
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': 'e' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on('POST', '/api/v1/driver/payslips/run-9/objections', (r) {
      final b = jsonDecode(r.body) as Map;
      return (
        201,
        {
          'id': 'ob-1',
          'run_id': 'run-9',
          'month': '2026-09-01',
          'item_code': b['item_code'],
          'item_amount': '-7.000',
          'reason': b['reason'],
          'has_attachment': true,
          'status': 'open',
          'response': null,
          'action_taken': null,
          'deduction': null,
          'created_at': '2026-10-02T08:00:00Z',
          'updated_at': '2026-10-02T08:00:00Z',
          'version': 1,
        },
      );
    });
    expect(find.byKey(const Key('object-payslip')), findsOneWidget);
    expect(find.byKey(const Key('object-gross')), findsOneWidget); // a sheet amount can be objected to as well
    await tester.tap(find.byKey(const Key('object-missing_target')));
    await settle(tester);
    expect(find.textContaining('خصم نقص التارجت'), findsWidgets);
    expect(find.text('اعتراض على كشف الراتب'), findsOneWidget);
    await tester.tap(find.byKey(const Key('send-objection')));
    await settle(tester);
    expect(find.text('اكتب السبب (3 أحرف على الأقل)'), findsOneWidget); // the reason is required
    await tester.enterText(find.byKey(const Key('objection-reason')), 'عملت 425 طلب حسب تطبيق المنصة');
    await tester.tap(find.byKey(const Key('objection-gallery')));
    await idle(tester);
    expect(find.byKey(const Key('objection-photo')), findsOneWidget);
    w.server.on(
      'GET',
      '/api/v1/driver/objections',
      (r) => (
        200,
        [
          {
            'id': 'ob-1',
            'run_id': 'run-9',
            'month': '2026-09-01',
            'item_code': 'missing_target',
            'item_amount': '-7.000',
            'reason': 'عملت 425 طلب حسب تطبيق المنصة',
            'has_attachment': true,
            'status': 'open',
            'response': null,
            'action_taken': null,
          },
        ],
      ),
    );
    await reveal(tester, find.byKey(const Key('send-objection')));
    await tester.tap(find.byKey(const Key('send-objection')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/files').single.url.queryParameters['source'], 'upload');
    final body = jsonDecode(w.server.calls('/api/v1/driver/payslips/run-9/objections', method: 'POST').single.body);
    expect(
      (body['item_code'], body['reason'], body['attachment_sha256']),
      ('missing_target', 'عملت 425 طلب حسب تطبيق المنصة', 'e' * 64),
    );
    expect(body.containsKey('run_id'), isFalse); // it names the run in the path
    expect(RegExp(r'^[0-9a-f-]{36}$').hasMatch(body['client_ref'] as String), isTrue);
    expect(find.text('أُرسل اعتراضك للمكتب، وسيصلك الرد'), findsOneWidget);
    await settle(tester);
    expect(find.byKey(const Key('objection-ob-1')), findsOneWidget); // back on the payslips, in his objections
  });

  testWidgets('objection to the whole payslip, and his objections with the status and the office answer', (
    tester,
  ) async {
    final w = await openPayslips(
      tester,
      mine: [
        {
          'id': 'ob-2',
          'run_id': 'run-9',
          'month': '2026-09-01',
          'item_code': 'orders_pay',
          'item_amount': '140.000',
          'reason': 'الطلبات ناقصة',
          'has_attachment': false,
          'status': 'rejected',
          'response': 'تقرير المنصة 400 طلب',
          'action_taken': null,
        },
      ],
    );
    w.server.on('POST', '/api/v1/driver/payslips/run-9/objections', (r) => (201, {'id': 'ob-3'}));
    await reveal(tester, find.byKey(const Key('objection-ob-2')));
    final tile = find.byKey(const Key('objection-ob-2'));
    expect(find.descendant(of: tile, matching: find.text('مرفوض')), findsOneWidget);
    expect(find.descendant(of: tile, matching: find.textContaining('رد المكتب: تقرير المنصة 400 طلب')), findsOneWidget);
    expect(find.descendant(of: tile, matching: find.textContaining('قيمة الطلبات')), findsOneWidget);
    await shot(tester, '40-objections');

    await reveal(tester, find.byKey(const Key('object-payslip')));
    await tester.tap(find.byKey(const Key('object-payslip')));
    await settle(tester);
    expect(find.text('على: الكشف كله'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('objection-reason')), 'الكشف كله غير صحيح');
    await tester.tap(find.byKey(const Key('send-objection')));
    await idle(tester);
    final body = jsonDecode(w.server.calls('/api/v1/driver/payslips/run-9/objections', method: 'POST').single.body);
    expect(body['item_code'], isNull);
    expect(body.containsKey('attachment_sha256'), isFalse);
    expect(w.server.calls('/api/v1/driver/files'), isEmpty);
  });

  testWidgets('no phone on file: civil ID and the initial password, then the phone and its WhatsApp code', (
    tester,
  ) async {
    final w = (await tester.runAsync(() => world(signedIn: false)))!;
    w.server.on('POST', '/api/v1/driver/auth/claim', (r) {
      final b = jsonDecode(r.body) as Map;
      if (b['password'] != '12345678') return (401, {'code': 'claim_invalid', 'status': 401});
      return (
        200,
        {
          'next': 'phone',
          'claim_token': 'c' * 43,
          'name': {'ar': 'الفاتح مختار', 'en': 'Alfatih'},
          'expires_in': 900,
        },
      );
    });
    w.server.on(
      'POST',
      '/api/v1/driver/auth/claim/phone',
      (r) => (200, {'sent_to': '+965••••1111', 'expires_in': 300}),
    );
    w.server.on('POST', '/api/v1/driver/auth/claim/verify', (r) => (200, tokensJson('7')));
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('civil-sign-in')));
    await settle(tester);
    await tester.enterText(find.byKey(const Key('claim-civil')), '286092015272');
    await tester.enterText(find.byKey(const Key('claim-password')), 'wrong-one');
    await tester.tap(find.byKey(const Key('claim-start')));
    await idle(tester);
    expect(find.byKey(const Key('claim-phone')), findsNothing, reason: 'a wrong password stays on the first step');
    await tester.enterText(find.byKey(const Key('claim-password')), '12345678');
    await tester.tap(find.byKey(const Key('claim-start')));
    await idle(tester);
    expect(find.textContaining('الفاتح مختار'), findsOneWidget);
    await shot(tester, '20-claim-phone');
    await tester.enterText(find.byKey(const Key('claim-phone')), '5000 1111');
    await tester.tap(find.byKey(const Key('claim-send')));
    await idle(tester);
    final phone = jsonDecode(w.server.calls('/api/v1/driver/auth/claim/phone').single.body) as Map;
    expect((phone['claim_token'], phone['phone']), ('c' * 43, '+96550001111'));
    await tester.enterText(find.byKey(const Key('claim-code')), '123456');
    await tester.tap(find.byKey(const Key('claim-verify')));
    await idle(tester);
    final verify = jsonDecode(w.server.calls('/api/v1/driver/auth/claim/verify').single.body) as Map;
    expect((verify['code'], verify['model']), ('123456', 'Test phone'));
    final start = jsonDecode(w.server.calls('/api/v1/driver/auth/claim').last.body) as Map;
    expect(verify['device_uid'], start['device_uid'], reason: 'the same phone all along');
    expect(find.textContaining('18/23456'), findsOneWidget, reason: 'signed in: today with the vehicle in custody');
  });

  testWidgets('no phone codes: the civil ID is the sign-in, the initial password, then his own, then his own alone', (
    tester,
  ) async {
    final w = (await tester.runAsync(() => world(signedIn: false)))!;
    w.server.on(
      'GET',
      '/api/v1/driver/app-config',
      (r) => (200, {'phone_codes': false, 'hidden_screens': <String>[], 'splash': null}),
    );
    final name = {'ar': 'الفاتح مختار', 'en': 'Alfatih'};
    w.server.on('POST', '/api/v1/driver/auth/claim', (r) {
      final b = jsonDecode(r.body) as Map;
      return switch (b['password']) {
        '12345678' => (200, {'next': 'password', 'claim_token': 'c' * 43, 'name': name, 'expires_in': 900}),
        'own-pass-1' => (200, {'next': 'done', 'name': name, 'tokens': tokensJson('8')}),
        _ => (401, {'code': 'claim_invalid', 'status': 401}),
      };
    });
    w.server.on('POST', '/api/v1/driver/auth/claim/password', (r) => (200, tokensJson('7')));
    await pumpApp(tester, w);
    await idle(tester);
    expect(find.byKey(const Key('phone')), findsNothing, reason: 'no sign-in by phone code for this company');
    expect(find.byKey(const Key('claim-civil')), findsOneWidget);
    expect(find.text('نسيت كلمة المرور؟ اطلب من المشرف كلمة مرور مبدئية جديدة.'), findsOneWidget);
    await shot(tester, '21-civil-sign-in');
    await tester.enterText(find.byKey(const Key('claim-civil')), '286092015272');
    await tester.enterText(find.byKey(const Key('claim-password')), '12345678');
    await tester.tap(find.byKey(const Key('claim-start')));
    await idle(tester);
    expect(find.textContaining('أهلاً الفاتح مختار. اختر كلمة مرورك'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('claim-new-password')), '286092015272');
    await tester.tap(find.byKey(const Key('claim-save-password')));
    await idle(tester);
    expect(find.text('لا تستخدم رقمك المدني كلمة مرور'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('claim-new-password')), 'own-pass-1');
    await tester.enterText(find.byKey(const Key('claim-confirm-password')), 'own-pass-2');
    await tester.tap(find.byKey(const Key('claim-save-password')));
    await idle(tester);
    expect(find.text('كلمتا المرور غير متطابقتين'), findsOneWidget);
    expect(w.server.calls('/api/v1/driver/auth/claim/password'), isEmpty);
    await shot(tester, '22-choose-password');
    await tester.enterText(find.byKey(const Key('claim-confirm-password')), 'own-pass-1');
    await tester.tap(find.byKey(const Key('claim-save-password')));
    await idle(tester);
    final chosen = jsonDecode(w.server.calls('/api/v1/driver/auth/claim/password').single.body) as Map;
    final start = jsonDecode(w.server.calls('/api/v1/driver/auth/claim').single.body) as Map;
    expect((chosen['claim_token'], chosen['password'], chosen['model']), ('c' * 43, 'own-pass-1', 'Test phone'));
    expect(chosen['device_uid'], start['device_uid']);
    expect(find.textContaining('18/23456'), findsOneWidget, reason: 'signed in');

    // signed out (another phone next month): his civil ID and his own password, nothing else
    w.server.on('POST', '/api/v1/driver/auth/logout', (r) => (204, null));
    await tester.runAsync(() => w.state.signOut());
    await idle(tester);
    await tester.enterText(find.byKey(const Key('claim-civil')), '286092015272');
    await tester.enterText(find.byKey(const Key('claim-password')), 'own-pass-1');
    await tester.tap(find.byKey(const Key('claim-start')));
    await idle(tester);
    expect(find.textContaining('18/23456'), findsOneWidget);
    expect(w.server.calls('/api/v1/driver/auth/claim/password').length, 1);
  });

  testWidgets('the office hides screens: their buttons, banners and the cash tab go', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    var hidden = <String>[];
    w.server.on(
      'GET',
      '/api/v1/driver/app-config',
      (r) => (200, {'phone_codes': true, 'hidden_screens': hidden, 'splash': null}),
    );
    await pumpApp(tester, w);
    for (final k in ['daily-report', 'maintenance', 'accident', 'fines', 'statement', 'payslips', 'schemes']) {
      expect(find.byKey(Key(k)), findsOneWidget, reason: k);
    }
    expect(find.text('الكاش'), findsWidgets);
    hidden = ['cash', 'maintenance', 'fines', 'payslips', 'schemes'];
    await tester.runAsync(() => w.state.refresh());
    await idle(tester);
    for (final k in ['maintenance', 'fines', 'payslips', 'schemes']) {
      expect(find.byKey(Key(k)), findsNothing, reason: k);
    }
    for (final k in ['daily-report', 'accident', 'statement', 'start-day']) {
      expect(find.byKey(Key(k)), findsOneWidget, reason: k);
    }
    expect(find.byIcon(Icons.account_balance_wallet_outlined), findsNothing, reason: 'no cash tab');
    final cashCalls = w.server.calls('/api/v1/driver/cash').length;
    await tester.runAsync(() => w.state.refresh());
    expect(w.server.calls('/api/v1/driver/cash').length, cashCalls, reason: 'a hidden screen is not even loaded');
    await shot(tester, '23-hidden-screens');
  });

  testWidgets('pay scheme: his terms, another scheme asked for from next month, then the request cancelled', (
    tester,
  ) async {
    final w = (await tester.runAsync(() => world()))!;
    Map<String, dynamic> view(Map<String, dynamic>? request) => {
      'current': fixedScheme,
      'next_month': null,
      'schemes': [fixedScheme, batchScheme],
      'request': request,
    };
    final pending = {
      'id': 'q1',
      'employee': null,
      'company_id': 1,
      'current': {'id': 'id-fixed_350', 'code': 'fixed_350', 'name': fixedScheme['name']},
      'requested': {'id': 'id-batch', 'code': 'batch', 'name': batchScheme['name']},
      'effective_month': '2026-11-01',
      'status': 'pending',
      'driver_note': 'عاوز الباتش',
      'admin_note': null,
      'created_at': '2026-10-06T10:00:00Z',
      'decided_at': null,
      'version': 1,
    };
    w.server.on('GET', '/api/v1/driver/schemes', (r) => (200, view(null)));
    w.server.on('POST', '/api/v1/driver/scheme-requests', (r) => (201, view(pending)));
    w.server.on('DELETE', '/api/v1/driver/scheme-requests/q1', (r) => (200, view(null)));
    await pumpApp(tester, w);
    await reveal(tester, find.byKey(const Key('schemes')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('schemes')));
    await idle(tester);
    final current = find.byKey(const Key('scheme-current'));
    expect(find.descendant(of: current, matching: find.text('سعر الطلب: \u20660.350\u2069 د.ك')), findsOneWidget);
    expect(
      find.descendant(of: current, matching: find.text('على الشركة: الصيانة، السكن، البنزين، الشريحة')),
      findsOneWidget,
    );
    expect(find.text('لا خصم على الطلبات الناقصة عن التارجت'), findsNWidgets(2));
    expect(find.text('• باتش \u20661\u2069: \u20660.700\u2069 د.ك'), findsOneWidget, reason: 'levels in order');
    expect(find.text('المصاريف عليك: الصيانة والسكن والبنزين والشريحة'), findsOneWidget);
    expect(find.byKey(const Key('scheme-ask-fixed_350')), findsNothing, reason: 'not his own scheme');
    await shot(tester, '25-schemes');
    await tester.tap(find.byKey(const Key('scheme-ask-batch')));
    await settle(tester);
    await tester.enterText(find.byKey(const Key('scheme-note')), 'عاوز الباتش');
    await tester.tap(find.byKey(const Key('scheme-send')));
    await idle(tester);
    final sent = jsonDecode(w.server.calls('/api/v1/driver/scheme-requests', method: 'POST').single.body);
    expect(sent, {'scheme_id': 'id-batch', 'note': 'عاوز الباتش'});
    expect(find.textContaining('بانتظار المكتب'), findsOneWidget);
    expect(find.byKey(const Key('scheme-ask-batch')), findsNothing, reason: 'one request at a time');
    await tester.tap(find.byKey(const Key('scheme-cancel')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/scheme-requests/q1', method: 'DELETE'), hasLength(1));
    expect(find.byKey(const Key('scheme-ask-batch')), findsOneWidget);
  });

  testWidgets('pay scheme on tiers: the reduced price, the tiers and the marks, and a refusal with its reason', (
    tester,
  ) async {
    final w = (await tester.runAsync(() => world()))!;
    w.server.on(
      'GET',
      '/api/v1/driver/schemes',
      (r) => (
        200,
        {
          'current': keetaScheme,
          'next_month': null,
          'schemes': [keetaScheme],
          'request': {
            'id': 'q2',
            'employee': null,
            'company_id': 1,
            'current': null,
            'requested': {
              'id': 'id-x',
              'code': 'x',
              'name': {'ar': 'نظام آخر', 'en': 'Other'},
            },
            'effective_month': '2026-11-01',
            'status': 'rejected',
            'driver_note': null,
            'admin_note': 'غير متاح لمنصتك',
            'created_at': '2026-10-06T10:00:00Z',
            'decided_at': '2026-10-06T12:00:00Z',
            'version': 2,
          },
        },
      ),
    );
    await pumpApp(tester, w);
    await reveal(tester, find.byKey(const Key('schemes')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('schemes')));
    await idle(tester);
    expect(
      find.text('ينخفض إلى \u20660.200\u2069 د.ك لكل طلبات الشهر لو فوّت Star Day أو وصلت علاماتك \u20665\u2069'),
      findsOneWidget,
    );
    expect(find.text('في شهر السعر المخفض لا يُصرف البونص'), findsOneWidget);
    expect(find.text('• \u2066450\u2069 طلب: \u206650.000\u2069 د.ك'), findsOneWidget);
    expect(find.text('• \u20664\u2069 علامات: \u206630.000\u2069 د.ك'), findsOneWidget);
    expect(find.text('كل طلب ناقص عن التارجت يُخصم \u20660.350\u2069 د.ك'), findsOneWidget);
    expect(find.text('رفض المكتب طلبك «نظام آخر»: غير متاح لمنصتك'), findsOneWidget);
    expect(find.byKey(const Key('scheme-cancel')), findsNothing);
    await shot(tester, '26-scheme-tiers');
  });

  testWidgets('self-registration: the driver chooses one of his platform\'s pay schemes', (tester) async {
    final ob = {
      'required': true,
      'status': 'draft',
      'data': {},
      'review_note': null,
      'required_documents': [],
      'vehicle_photos': [],
      'document_types': [],
      'schemes': [fixedScheme, batchScheme],
      'scheme_required': true,
    };
    final w = (await tester.runAsync(() => world(onboarding: ob)))!;
    Map<String, dynamic>? saved;
    w.server.on('PUT', '/api/v1/driver/onboarding', (r) {
      saved = jsonDecode(r.body) as Map<String, dynamic>;
      return (200, {...ob, 'data': saved});
    });
    await pumpApp(tester, w);
    await reveal(tester, find.byKey(const Key('ob-scheme-batch')));
    await settle(tester);
    expect(find.byIcon(Icons.radio_button_checked), findsNothing);
    await tester.tap(find.byKey(const Key('ob-scheme-batch')));
    await settle(tester);
    expect(find.byIcon(Icons.radio_button_checked), findsOneWidget);
    await shot(tester, '27-onboarding-scheme');
    await tester.tap(find.byKey(const Key('ob-next')));
    await idle(tester);
    expect(saved!['scheme_id'], 'id-batch');
  });

  testWidgets('the splash screen the office designed shows when the app opens, from the next launch', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    final png = base64Decode(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
    );
    final sha = 'a' * 64;
    w.server.on(
      'GET',
      '/api/v1/driver/app-config',
      (r) => (
        200,
        {
          'phone_codes': true,
          'hidden_screens': <String>[],
          'splash': {'image': sha, 'color': '#0A6CFF', 'seconds': 2},
        },
      ),
    );
    w.server.on('GET', '/api/v1/driver/splash/$sha', (r) => (200, png));
    await pumpApp(tester, w);
    expect(find.byKey(const Key('splash')), findsNothing, reason: 'the first launch only fetches and keeps it');
    expect(w.server.calls('/api/v1/driver/splash/$sha').length, 1);

    // the next launch: shown before anything else, then the app goes on
    final again = AppState(db: w.state.db, api: w.state.api, pollEvery: null, platform: w.state.platform);
    await tester.pumpWidget(const SizedBox()); // the app closed
    await tester.pumpWidget(DriverApp(state: again));
    await tester.runAsync(() => again.boot());
    await tester.pump();
    expect(find.byKey(const Key('splash')), findsOneWidget);
    await shot(tester, '24-splash');
    await tester.runAsync(() => Future<void>.delayed(const Duration(seconds: 2, milliseconds: 100)));
    await idle(tester);
    expect(find.byKey(const Key('splash')), findsNothing);
    expect(find.byKey(const Key('start-day')), findsOneWidget);
    expect(w.server.calls('/api/v1/driver/splash/$sha').length, 1, reason: 'kept on the phone, not fetched again');
  });

  testWidgets('notifications: a badge with the unread count, the list in the app language, read once opened', (
    tester,
  ) async {
    final w = (await tester.runAsync(() => world()))!;
    var unread = 2;
    Map<String, dynamic> notice(String id, String kind, String message, bool read) => {
      'id': id,
      'kind': kind,
      'message': message,
      'entity_type': null,
      'entity_id': null,
      'created_at': '2026-10-07T09:00:00Z',
      'read': read,
    };
    w.server.on(
      'GET',
      '/api/v1/driver/notifications',
      (r) => (
        200,
        {
          'unread': unread,
          'items': [
            notice('n2', 'maintenance_ready', 'سيارتك جاهزة للاستلام من مركز النور (طلب الصيانة رقم 12).', unread == 0),
            notice('n1', 'receipt_issued', 'استلم المكتب منك 15.000 د.ك، إيصال رقم 7.', unread == 0),
          ],
        },
      ),
    );
    w.server.on('POST', '/api/v1/driver/notifications/read', (r) {
      unread = 0;
      return (200, {'count': 2});
    });
    await pumpApp(tester, w);
    final bell = find.byKey(const Key('notifications'));
    expect(find.descendant(of: bell, matching: find.text('2')), findsOneWidget);
    await tester.tap(bell);
    await settle(tester);
    expect(find.textContaining('سيارتك جاهزة للاستلام من مركز النور'), findsOneWidget);
    expect(find.textContaining('إيصال رقم 7'), findsOneWidget);
    expect(w.server.calls('/api/v1/driver/notifications/read', method: 'POST'), hasLength(1));
    await shot(tester, '24-notifications');
    await tester.binding.handlePopRoute(); // the phone's back button
    await settle(tester);
    expect(find.descendant(of: bell, matching: find.text('2')), findsNothing); // read: the badge is gone
  });

  testWidgets('push: once the office switches it on, the phone gives its token once, again in a new language', (
    tester,
  ) async {
    void Function()? arrived;
    var asked = 0;
    final w = (await tester.runAsync(
      () => world(
        pushToken: (config, {required onRefresh, required onMessage}) async {
          expect(config['project_id'], 'fleet-test');
          asked++;
          arrived = onMessage;
          return 'fcm-token-1';
        },
      ),
    ))!;
    w.server.on(
      'GET',
      '/api/v1/driver/app-config',
      (r) => (
        200,
        {
          'phone_codes': true,
          'hidden_screens': [],
          'splash': null,
          'push': {'project_id': 'fleet-test', 'app_id': '1:1:android:a', 'api_key': 'k', 'sender_id': '1'},
        },
      ),
    );
    var unread = 0;
    w.server.on('GET', '/api/v1/driver/notifications', (r) => (200, {'unread': unread, 'items': []}));
    w.server.on('POST', '/api/v1/driver/push-token', (r) => (204, null));
    await pumpApp(tester, w);
    await idle(tester);
    final sent = w.server.calls('/api/v1/driver/push-token');
    expect(sent, hasLength(1));
    expect(jsonDecode(sent.single.body), {'token': 'fcm-token-1', 'lang': 'ar'});
    await tester.runAsync(() => w.state.refresh());
    await idle(tester);
    expect(asked, 2);
    expect(w.server.calls('/api/v1/driver/push-token'), hasLength(1), reason: 'the same token is not sent twice');
    await tester.runAsync(() => w.state.setLang('en'));
    await idle(tester);
    expect(jsonDecode(w.server.calls('/api/v1/driver/push-token').last.body)['lang'], 'en');
    // a push while the app is open: the badge follows
    unread = 1;
    arrived!();
    await idle(tester);
    expect(find.descendant(of: find.byKey(const Key('notifications')), matching: find.text('1')), findsOneWidget);
  });
  testWidgets(
    'home: the car with its make and model, the day started at its time and reading, the balance opens cash',
    (tester) async {
      const started = '2026-10-08T04:52:00Z';
      final w = (await tester.runAsync(
        () => world(
          today: {
            'custody': {
              'id': 'c1',
              'plate_number': '18/23456',
              'started_at': '2026-10-02T05:00:00Z',
              'last_odometer_km': 45198,
              'make': 'Toyota',
              'model': 'Yaris',
              'year': 2023,
            },
            'start_day_done': true,
            'sessions': 1,
            'day_started_at': started,
            'day_start_km': 45198,
          },
        ),
      ))!;
      await pumpApp(tester, w);
      expect(find.text('Toyota Yaris 2023'), findsOneWidget);
      final time = DateFormat('HH:mm', 'en').format(DateTime.parse(started).toLocal());
      expect(find.text('يومك بدأ الساعة \u2066$time\u2069'), findsOneWidget);
      expect(find.text('عداد البداية \u206645,198\u2069'), findsOneWidget);
      expect(find.byKey(const Key('end-day')), findsOneWidget);
      expect(find.byKey(const Key('start-day')), findsNothing);
      await tester.tap(find.byKey(const Key('qa-cash')));
      await settle(tester);
      expect(find.byKey(const Key('cash-total')), findsOneWidget);
      expect(find.byKey(const Key('daily-report')), findsNothing, reason: 'the cash tab, not home');
    },
  );

  testWidgets('the daily work tab: today\'s report to send and the ones before; once sent, its status', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    await pumpApp(tester, w);
    await tester.tap(find.text('العمل اليومي').last);
    await settle(tester);
    expect(find.byKey(const Key('work-report-p1')), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('work-report-p1')), matching: find.text('معتمد')), findsOneWidget);
    await tester.tap(find.byKey(const Key('work-report')));
    await settle(tester);
    expect(find.byKey(const Key('orders')), findsOneWidget, reason: 'the report form');
    await tester.tap(find.byType(BackButton));
    await settle(tester);

    w.server.on(
      'GET',
      '/api/v1/driver/reports',
      (r) => (
        200,
        [
          {
            'id': 'p2',
            'driver': null,
            'company_id': 1,
            'vehicle_plate': '18/23456',
            'business_date': kuwaitDay(DateTime.now()),
            'orders_count': 25,
            'cash_amount': '40.500',
            'approved_cash': null,
            'has_screenshot': true,
            'notes': null,
            'status': 'submitted',
            'submitted_at': DateTime.now().toUtc().toIso8601String(),
            'reviewed_at': null,
            'review_note': null,
          },
        ],
      ),
    );
    await tester.runAsync(() async {
      await w.state.loadReports();
      await w.state.reloadLocal(); // as the pull to refresh does: the screens are told
    });
    await tester.pump();
    expect(find.byKey(const Key('work-report')), findsNothing, reason: 'sent: nothing to send');
    expect(find.text('أرسلت تقرير اليوم'), findsOneWidget);
    expect(find.textContaining('40.500'), findsWidgets);
    expect(find.text('بانتظار المراجعة'), findsWidgets);
  });

  testWidgets('the maintenance tab: a new request from it, his requests with where each is', (tester) async {
    final w = (await tester.runAsync(
      () => world(
        maintenance: [
          {
            'id': 'm1',
            'number': 7,
            'vehicle_plate': '18/23456',
            'kind': 'tyres',
            'description': 'الإطار الخلفي',
            'status': 'referred',
            'created_at': '2026-10-05T08:00:00Z',
            'center': {'name': 'مركز الملا', 'phone': null, 'address': null},
            'ready_at': null,
            'decision_note': null,
          },
        ],
      ),
    ))!;
    await pumpApp(tester, w);
    await tester.tap(find.text('الصيانة').last);
    await settle(tester);
    expect(find.text('إطارات'), findsOneWidget);
    expect(find.text('أُرسل للمركز'), findsOneWidget);
    expect(find.textContaining('مركز الملا'), findsOneWidget);
    await tester.tap(find.byKey(const Key('mnt-new')));
    await settle(tester);
    expect(find.byKey(const Key('mnt-send')), findsOneWidget);
  });
  testWidgets('a report sent with no signal waits on the phone: shown as not sent yet, never offered twice', (
    tester,
  ) async {
    final w = (await tester.runAsync(() => world()))!;
    final img = await tester.runAsync(testImage);
    Photos.gallery = () async => TakenPhoto(img!, DateTime.now());
    w.server.on('POST', '/api/v1/driver/files', (r) => throw const SocketException('offline'));
    await pumpApp(tester, w);
    await tester.tap(find.byKey(const Key('daily-report')));
    await settle(tester);
    await tester.enterText(find.byKey(const Key('orders')), '27');
    await tester.enterText(find.byKey(const Key('cash')), '19.5');
    await tester.tap(find.byKey(const Key('screenshot')));
    await idle(tester);
    await reveal(tester, find.byKey(const Key('send-report')));
    await tester.tap(find.byKey(const Key('send-report')));
    await idle(tester);
    expect(find.text('حُفظ على الهاتف'), findsOneWidget);
    await tester.tap(find.text('تم'));
    await idle(tester);
    expect(
      find.descendant(of: find.byKey(const Key('daily-report')), matching: find.text('تقرير اليوم محفوظ على الهاتف')),
      findsOneWidget,
    );
    await tester.tap(find.text('العمل اليومي').last);
    await settle(tester);
    expect(find.byKey(const Key('work-report')), findsNothing, reason: 'waiting to go: not to be sent again');
    expect(find.text('لم يُرسل بعد'), findsOneWidget);
    expect(find.textContaining('27'), findsWidgets);
    await tester.tap(find.text('الرئيسية').last);
    await settle(tester);
    await tester.tap(find.byKey(const Key('daily-report')));
    await settle(tester);
    expect(find.byKey(const Key('report-queued')), findsOneWidget);
    expect(find.byKey(const Key('send-report')), findsNothing);
  });

  Map<String, dynamic> fuelView({bool allowed = true, String? reason, List<Map<String, dynamic>>? claims}) => {
    'allowed': allowed,
    'reason': reason,
    'max_amount': '50.000',
    'claims': claims ?? [],
  };

  testWidgets('fuel from the cash: the receipt from the camera, the amount with 3 decimals, the odometer optional', (
    tester,
  ) async {
    final claims = <Map<String, dynamic>>[];
    final w = (await tester.runAsync(() => world()))!;
    w.server.on('GET', '/api/v1/driver/fuel', (r) => (200, fuelView(claims: claims)));
    final img = await tester.runAsync(testImage);
    final taken = DateTime.now().subtract(const Duration(minutes: 7));
    Photos.camera = (_) async => TakenPhoto(img!, taken);
    Photos.gallery = () async => fail('the receipt comes from the camera only');
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': 'f' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on('POST', '/api/v1/driver/fuel', (r) {
      final b = jsonDecode(r.body) as Map<String, dynamic>;
      final claim = {
        'id': 'fc1',
        'paid_at': b['paid_at'],
        'amount': b['amount'],
        'approved_amount': null,
        'status': 'pending',
        'decision_note': null,
        'odometer_km': b['odometer_km'],
        'notes': null,
        'vehicle_plate': '18/23456',
        'created_at': '2026-10-08T08:00:00Z',
      };
      claims.add(claim);
      return (201, claim);
    });
    await pumpApp(tester, w);
    await reveal(tester, find.byKey(const Key('fuel')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('fuel')));
    await idle(tester);
    expect(find.byKey(const Key('fuel-off')), findsNothing);

    // no photo: not sent; above the maximum: not sent
    await tester.enterText(find.byKey(const Key('fuel-amount')), '60');
    await reveal(tester, find.byKey(const Key('fuel-send')));
    await tester.tap(find.byKey(const Key('fuel-send')));
    await idle(tester);
    expect(find.byKey(const Key('fuel-photo-missing')), findsOneWidget);
    expect(find.textContaining('أقصى مبلغ للفاتورة'), findsOneWidget);
    expect(w.server.calls('/api/v1/driver/fuel', method: 'POST'), isEmpty);

    await reveal(tester, find.byKey(const Key('fuel-amount')));
    await tester.enterText(find.byKey(const Key('fuel-amount')), '7.5');
    await reveal(tester, find.byKey(const Key('fuel-photo')));
    await tester.tap(find.byKey(const Key('fuel-photo')));
    await idle(tester);
    expect(find.byKey(const Key('fuel-photo-missing')), findsNothing);
    await shot(tester, '30-fuel');
    await reveal(tester, find.byKey(const Key('fuel-send')));
    await tester.tap(find.byKey(const Key('fuel-send')));
    await idle(tester);
    final body = jsonDecode(w.server.calls('/api/v1/driver/fuel', method: 'POST').single.body) as Map;
    expect((body['amount'], body['receipt_sha256']), ('7.500', 'f' * 64));
    expect(body.containsKey('odometer_km') || body.containsKey('notes'), isFalse, reason: 'optional, left empty');
    expect(DateTime.parse(body['paid_at'] as String).isAtSameMomentAs(taken), isTrue, reason: 'the photo\'s time');
    expect((body['client_ref'] as String).length, 36);
    expect(w.server.calls('/api/v1/driver/files').single.url.queryParameters['source'], 'camera');
    expect(find.text('تم الإرسال'), findsOneWidget);

    // back on home, opened again: the receipt waits for the accountant
    await tester.tap(find.text('تم'));
    await settle(tester);
    await reveal(tester, find.byKey(const Key('fuel')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('fuel')));
    await idle(tester);
    await reveal(tester, find.byKey(const Key('fuel-claim-fc1')));
    expect(
      find.descendant(of: find.byKey(const Key('fuel-claim-fc1')), matching: find.text('بانتظار المراجعة')),
      findsOne,
    );
  });

  testWidgets('fuel decided: approved at its amount, rejected with the reason; in the cash tab as fuel', (
    tester,
  ) async {
    final w = (await tester.runAsync(
      () => world(
        fuel: fuelView(
          claims: [
            {
              'id': 'a',
              'paid_at': '2026-10-07T06:00:00Z',
              'amount': '7.250',
              'approved_amount': '7.000',
              'status': 'approved',
              'decision_note': 'المبلغ في الفاتورة 7.000',
              'odometer_km': 45210,
              'notes': null,
              'vehicle_plate': '18/23456',
              'created_at': '2026-10-07T06:01:00Z',
            },
            {
              'id': 'b',
              'paid_at': '2026-10-06T06:00:00Z',
              'amount': '4.000',
              'approved_amount': null,
              'status': 'rejected',
              'decision_note': 'فاتورة غير واضحة',
              'odometer_km': null,
              'notes': null,
              'vehicle_plate': '18/23456',
              'created_at': '2026-10-06T06:01:00Z',
            },
          ],
        ),
      ),
    ))!;
    w.server.on(
      'GET',
      '/api/v1/driver/cash',
      (r) => (
        200,
        {
          'posted': '-7.000',
          'pending': '0.000',
          'total': '-7.000',
          'alert_limit': '80.000',
          'receipts': [],
          'lines': [
            {
              'journal_id': 'j1',
              'kind': 'fuel',
              'status': 'posted',
              'amount': '-7.000',
              'business_date': '2026-10-07',
              'reason': 'المبلغ في الفاتورة 7.000',
              'source_type': 'fuel_claim',
              'created_at': '2026-10-08T06:00:00Z',
            },
          ],
        },
      ),
    );
    await pumpApp(tester, w);
    await reveal(tester, find.byKey(const Key('fuel')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('fuel')));
    await idle(tester);
    await reveal(tester, find.byKey(const Key('fuel-claim-b')));
    expect(find.text('تم القبول (\u20667.000\u2069 د.ك)'), findsOneWidget);
    expect(find.descendant(of: find.byKey(const Key('fuel-claim-b')), matching: find.text('مرفوض')), findsOne);
    expect(find.textContaining('فاتورة غير واضحة'), findsOneWidget);
    await tester.tap(find.byType(BackButton));
    await settle(tester);
    await reveal(tester, find.byKey(const Key('qa-cash')));
    await tester.tap(find.byKey(const Key('qa-cash')));
    await settle(tester);
    expect(find.text('بنزين'), findsOneWidget);
  });

  testWidgets('fuel not offered: a fuel card, fuel on the driver, no car; an older server', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    await pumpApp(tester, w);
    expect(find.byKey(const Key('fuel')), findsNothing, reason: 'the server has no fuel route');
    expect(w.state.fuel, isNull);
    final texts = {
      'fuel_card': 'كارت بنزين',
      'not_covered': 'البنزين عليك حسب نظام الدفع',
      'no_vehicle': 'لا توجد سيارة في عهدتك',
    };
    for (final MapEntry(key: reason, value: text) in texts.entries) {
      w.server.on('GET', '/api/v1/driver/fuel', (r) => (200, fuelView(allowed: false, reason: reason)));
      await tester.runAsync(() => w.state.refresh());
      await idle(tester);
      expect(find.byKey(const Key('fuel')), findsNothing, reason: reason);
      // the screen itself (opened before his scheme changed) says why, with no form
      final nav = tester.state<NavigatorState>(find.byType(Navigator).first);
      unawaited(nav.push(MaterialPageRoute<void>(builder: (_) => FuelScreen(state: w.state))));
      await idle(tester);
      expect(find.byKey(const Key('fuel-off')), findsOneWidget, reason: reason);
      expect(find.textContaining(text), findsOneWidget, reason: reason);
      expect(find.byKey(const Key('fuel-amount')), findsNothing, reason: reason);
      expect(find.byKey(const Key('fuel-send')), findsNothing, reason: reason);
      nav.pop();
      await settle(tester);
    }
  });

  testWidgets('fuel with no signal: kept on the phone with its receipt and sent later', (tester) async {
    final w = (await tester.runAsync(() => world(fuel: fuelView())))!;
    final img = await tester.runAsync(testImage);
    Photos.camera = (_) async => TakenPhoto(img!, DateTime.now());
    w.server.on('POST', '/api/v1/driver/files', (r) => throw const SocketException('offline'));
    await pumpApp(tester, w);
    await reveal(tester, find.byKey(const Key('fuel')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('fuel')));
    await idle(tester);
    // typed on an Arabic keyboard: its digits and its decimal point (٫)
    await tester.enterText(find.byKey(const Key('fuel-amount')), '\u0663\u066B\u0662\u0665');
    await tester.enterText(find.byKey(const Key('fuel-km')), '45210');
    await reveal(tester, find.byKey(const Key('fuel-photo')));
    await tester.tap(find.byKey(const Key('fuel-photo')));
    await idle(tester);
    await reveal(tester, find.byKey(const Key('fuel-send')));
    await tester.tap(find.byKey(const Key('fuel-send')));
    await idle(tester);
    expect(find.text('حُفظ على الهاتف'), findsOneWidget);
    await tester.tap(find.text('تم'));
    await idle(tester);
    expect(find.text('فاتورة بنزين'), findsOneWidget);
    final item = w.state.queued.single;
    expect((item.kind, item.payload['amount'], item.payload['odometer_km']), ('fuel', '3.250', 45210));
    expect(item.files.keys, ['receipt_sha256']);

    // the network is back: sent with the receipt uploaded from the camera
    w.server.on(
      'POST',
      '/api/v1/driver/files',
      (r) => (201, {'sha256': 'e' * 64, 'size_bytes': 10, 'content_type': 'image/jpeg'}),
    );
    w.server.on('POST', '/api/v1/driver/fuel', (r) => (409, {'code': 'fuel_exists'})); // its first try got there
    await tester.runAsync(() => w.state.outbox.flush(w.state.api));
    await tester.runAsync(() => w.state.reloadLocal());
    await idle(tester);
    expect(w.state.queued, isEmpty, reason: 'a resend already recorded is done');
    final body = jsonDecode(w.server.calls('/api/v1/driver/fuel', method: 'POST').single.body) as Map;
    expect((body['receipt_sha256'], body['amount']), ('e' * 64, '3.250'));
  });
}
