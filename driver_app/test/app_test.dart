import 'dart:convert';
import 'dart:io';

import 'package:fleet_driver/app/state.dart';
import 'package:fleet_driver/core/api.dart';
import 'package:fleet_driver/core/tokens.dart';
import 'package:fleet_driver/main.dart';
import 'package:fleet_driver/ui/photos.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

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

class World {
  World(this.state, this.server);
  final AppState state;
  final FakeServer server;
}

Future<World> world({
  bool signedIn = true,
  Map<String, dynamic>? onboarding,
  Map<String, dynamic>? today,
  List<Map<String, dynamic>>? maintenance,
  List<Map<String, dynamic>>? accidents,
  List<Map<String, dynamic>>? fines,
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
      startTracking: () async {},
      stopTracking: () async {},
      deviceMeta: () async => {'platform': 'android', 'model': 'Test phone', 'app_version': '0.1.0'},
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
          'errors': {'reading_exists': 'سُجّلت قراءة نهاية اليوم من قبل', 'otp_invalid': 'الرمز غير صحيح'},
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
  server.on('GET', '/api/v1/driver/accidents', (r) => (200, accidents ?? []));
  server.on('GET', '/api/v1/driver/fines', (r) => (200, fines ?? []));
  return World(state, server);
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
    await tester.tap(find.byKey(const Key('send-reading')));
    await idle(tester);
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
    await tester.ensureVisible(find.byKey(const Key('send-report')));
    await tester.tap(find.byKey(const Key('send-report')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/files').single.url.queryParameters['source'], 'upload');
    final body = jsonDecode(w.server.calls('/api/v1/driver/reports', method: 'POST').single.body) as Map;
    expect((body['orders_count'], body['cash_amount'], body['screenshot_sha256']), (27, '19.500', 'd' * 64));
    expect(RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(body['business_date'] as String), isTrue);
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
        },
      );
    });
    await pumpApp(tester, w);
    expect(find.textContaining('صورة الإقامة غير واضحة'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('civil')), '290010112345');
    await tester.enterText(find.byKey(const Key('nationality')), 'India');
    await tester.enterText(find.byKey(const Key('iban')), 'kw81 cbku 0000 0000 0000 1234 5601 01');
    await tester.enterText(find.byKey(const Key('bank')), 'بنك الكويت الوطني');
    await shot(tester, '09-onboarding-data');
    Future<void> next() async {
      await tester.tap(find.byKey(const Key('ob-next')));
      await idle(tester);
    }

    Future<void> tapTile(String label, {bool sheet = false}) async {
      await tester.ensureVisible(find.text(label).first);
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
    expect(saved!['civil_id'], '290010112345');
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

  test('activation links: the token after "#" (App Link) or "?t=" (fallback page); anything else ignored', () {
    final token = 'A' * 32;
    expect(AppState.activationToken(Uri.parse('https://fleet.example.com/activate#t=$token')), token);
    expect(AppState.activationToken(Uri.parse('btfleet://activate?t=$token')), token);
    expect(AppState.activationToken(Uri.parse('https://fleet.example.com/other#t=$token')), isNull);
    expect(AppState.activationToken(Uri.parse('https://fleet.example.com/activate#t=short')), isNull);
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
    await tester.ensureVisible(find.byKey(const Key('mnt-send')));
    await tester.tap(find.byKey(const Key('mnt-send')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/files').every((r) => r.url.queryParameters['source'] == 'camera'), isTrue);
    final body = jsonDecode(w.server.calls('/api/v1/driver/maintenance', method: 'POST').single.body) as Map;
    expect((body['kind'], body['description'], body['odometer_km']), ('tyres', 'الإطار الخلفي الأيسر مثقوب', 45230));
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
    await tester.ensureVisible(find.byKey(const Key('accident')));
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
      await tester.ensureVisible(find.byKey(const Key('acc-photo')));
      await settle(tester);
      await tester.tap(find.byKey(const Key('acc-photo')));
      await idle(tester);
    }
    await tester.ensureVisible(find.byKey(const Key('acc-send')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('acc-send')));
    await idle(tester);
    expect(find.byKey(const Key('acc-photos-missing')), findsOneWidget);
    expect(w.server.calls('/api/v1/driver/accidents', method: 'POST'), isEmpty);
    await tester.ensureVisible(find.byKey(const Key('acc-photo')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('acc-photo')));
    await idle(tester);
    await shot(tester, '15-accident');
    await tester.ensureVisible(find.byKey(const Key('acc-send')));
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
    Photos.camera = (_) async => TakenPhoto(img!, DateTime.now());
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
    await tester.ensureVisible(find.byKey(const Key('accident')));
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
    await tester.ensureVisible(find.byKey(const Key('fines')));
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
    await tester.tap(find.byKey(const Key('statement')));
    await idle(tester);
    expect(find.textContaining('المنصة أ'), findsOneWidget);
    await tester.dragUntilVisible(
      find.textContaining('اللقطة لشهر آخر'),
      find.byType(ListView).first,
      const Offset(0, -200),
    );
    expect(find.textContaining('اللقطة لشهر آخر'), findsOneWidget);
    await tester.dragUntilVisible(
      find.byKey(const Key('send-statement')),
      find.byType(ListView).first,
      const Offset(0, 200),
    );
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
    await tester.ensureVisible(find.byKey(const Key('send-statement')));
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
    await tester.tap(find.byKey(const Key('payslips')));
    await idle(tester);
    expect(find.text('عدد الأيام الصالحة'), findsOneWidget);
    expect(find.textContaining('40.000'), findsOneWidget);
    expect(find.text('مدفوع'), findsOneWidget);
    final net = tester.widget<Text>(find.byKey(const Key('payslip-net')));
    expect(net.data, contains('130.000'));
    await shot(tester, '19-payslips');
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
    w.server.on('GET', '/api/v1/driver/auth/methods', (r) => (200, {'phone_codes': false}));
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
}
