@Tags(['contract'])
library;

import 'dart:convert';
import 'dart:io';

import 'package:fleet_driver/app/state.dart';
import 'package:fleet_driver/core/db.dart';
import 'package:fleet_driver/core/errors.dart';
import 'package:fleet_driver/core/outbox.dart';
import 'package:fleet_driver/tracking/tracker.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'support.dart';

/// The app against a real backend (not a fake): BACKEND_URL=http://127.0.0.1:8000 ADMIN_PASSWORD=... flutter test
/// --tags contract. Creates its own driver, vehicle and custody through the admin API, then uses the app's code.
final backend = Platform.environment['BACKEND_URL'];

class Admin {
  Admin(this.base);
  final String base;
  final _http = http.Client();
  String? cookie;
  String? csrf;

  Future<dynamic> call(String method, String path, [Object? body]) async {
    final req = http.Request(method, Uri.parse('$base/api/v1$path'))
      ..headers['Content-Type'] = 'application/json'
      ..headers['Accept-Language'] = 'en';
    if (cookie != null) req.headers['Cookie'] = cookie!;
    if (csrf != null) req.headers['X-CSRF-Token'] = csrf!;
    if (body != null) req.body = jsonEncode(body);
    final res = await http.Response.fromStream(await _http.send(req));
    final set = res.headers['set-cookie'];
    if (set != null) cookie = set.split(';').first;
    if (res.statusCode >= 400) throw StateError('$method $path -> ${res.statusCode} ${res.body}');
    return res.body.isEmpty ? null : jsonDecode(utf8.decode(res.bodyBytes));
  }

  Future<String> upload(File f) async {
    final req = http.MultipartRequest('POST', Uri.parse('$base/api/v1/files'))
      ..headers['Cookie'] = cookie!
      ..headers['X-CSRF-Token'] = csrf!
      ..files.add(await http.MultipartFile.fromPath('file', f.path));
    final res = await http.Response.fromStream(await _http.send(req));
    return jsonDecode(res.body)['sha256'] as String;
  }
}

Future<File> jpeg(String name) async {
  // a real JPEG, made unique so the server never sees a reused photo
  final f = File('${(await Directory.systemTemp.createTemp('c')).path}/$name.jpg');
  final base = base64Decode(
    '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP////////////////////////////////////////////////////////////////////////////////////8AAAA//////////////////9k=',
  );
  final unique = utf8.encode(DateTime.now().microsecondsSinceEpoch.toString());
  await f.writeAsBytes([...base.sublist(0, 2), 0xff, 0xfe, 0, unique.length + 2, ...unique, ...base.sublist(2)]);
  return f;
}

Future<int> companyId(Admin admin) async {
  final existing = (await admin.call('GET', '/companies/options')) as List;
  if (existing.isNotEmpty) return existing.first['id'] as int;
  final c = await admin.call('POST', '/companies', {
    'name': {'ar': 'شركة الاختبار', 'en': 'Test Company'},
  });
  return c['id'] as int;
}

Future<Admin> signedInAdmin() async {
  final admin = Admin(backend!);
  final login = await admin.call('POST', '/auth/login', {
    'username': 'admin',
    'password': Platform.environment['ADMIN_PASSWORD'] ?? 'correct-horse-battery',
  });
  admin.csrf = login['csrf_token'] as String;
  return admin;
}

AppState appAgainstBackend(AppDb db) => AppState(
  db: db,
  baseUrl: backend,
  pollEvery: null,
  platform: PhoneHooks(
    permissionsOk: () async => true,
    startTracking: () async {},
    stopTracking: () async {},
    deviceMeta: () async => {'platform': 'android', 'model': 'Contract test', 'app_version': '0.1.0'},
  ),
);

void main() {
  test(
    'activation link, heartbeat, positions, start of day with photo, daily report, cash, sign out',
    () async {
      final admin = await signedInAdmin();
      final n = DateTime.now().millisecondsSinceEpoch % 10000000;
      final company = await companyId(admin);
      final driver = await admin.call('POST', '/employees', {
        'employee_number': 'C$n',
        'name': {'ar': 'سائق العقد', 'en': 'Contract Driver'},
        'company_id': company,
        'is_driver': true,
        'phone': '+9659${n.toString().padLeft(7, '0')}',
      });
      await admin.call('PUT', '/employees/${driver['id']}/app-access', {'app_access': 'active'});
      final vehicle = await admin.call('POST', '/vehicles', {
        'plate_number': '77/$n',
        'company_id': company,
        'last_odometer_km': 30000,
      });
      await admin.call('POST', '/custodies', {
        'vehicle_id': vehicle['id'],
        'driver_id': driver['id'],
        'odometer_km': 30000,
        'photo_sha256': await admin.upload(await jpeg('handover')),
        'started_at': DateTime.now().toUtc().subtract(const Duration(hours: 2)).toIso8601String(),
      });
      final link = await admin.call('POST', '/employees/${driver['id']}/activation-link', {
        'channel': 'manual',
        'onboarding': false,
      });

      // ---- the app
      final db = await testDb();
      final state = appAgainstBackend(db);
      final token = AppState.activationToken(Uri.parse(link['url'] as String))!;
      await state.activate(token);
      expect(state.phase, Phase.ready);
      expect(state.today!.custody!.plate, '77/$n');
      expect(state.today!.startDayDone, isFalse);

      // ---- tracking: the server says track (custody open); three fixes go out and are acknowledged. The phone
      // measured the speed of the first only: the others' is worked out from the distance (111 m in 31 s, 13 km/h)
      final now = DateTime.now().toUtc();
      final fixes = Stream<Fix>.fromIterable([
        for (var i = 0; i < 3; i++)
          Fix(
            at: now.subtract(Duration(seconds: 90 - 31 * i)),
            lat: 29.37 + i * 0.001,
            lng: 47.98,
            accuracyM: 8,
            speedKmh: i == 0 ? 35 : null,
            heading: 90,
          ),
      ]);
      final shown = <(Map<String, dynamic>?, bool)>[];
      final tracker = Tracker(
        db: db,
        api: state.api,
        fixes: (_) => fixes,
        health: ({required bool trackingRunning, required int queueSize, String? lastUploadAt}) async => {
          'location_permission': 'always',
          'gps_enabled': true,
          'tracking_service_running': trackingRunning,
          'queue_size': queueSize,
          'app_version': '0.1.0',
        },
        notify: (company, working) => shown.add((company, working)),
        heartbeatEvery: const Duration(hours: 1),
        syncEvery: const Duration(hours: 1),
      );
      await tracker.start();
      expect(tracker.required, isTrue);
      expect(shown.single.$2, isFalse, reason: 'custody, day not started: not at work');
      expect(shown.single.$1, isNotNull, reason: 'his company, for the notification title');
      await Future<void>.delayed(const Duration(milliseconds: 300));
      await tracker.sync();
      expect(await tracker.queue.size(), 0);
      final live = (await admin.call('GET', '/tracking/live') as List).firstWhere(
        (v) => v['vehicle']['id'] == vehicle['id'],
      );
      expect((live['position']['lat'] as num).toDouble(), closeTo(29.372, 0.0001));
      expect((live['position']['speed_kmh'] as num).toDouble(), closeTo(12.9, 0.5), reason: 'worked out, never 0');

      // ---- start of day: camera photo + reading, through the outbox
      final photo = await jpeg('odo');
      final taken = DateTime.now().toUtc().subtract(const Duration(minutes: 5));
      expect(
        await state.sendReading(
          kind: 'start_day',
          km: 30120,
          photoPath: photo.path,
          takenAt: taken,
          lat: 29.37,
          lng: 47.98,
        ),
        SendResult.sent,
      );
      expect(state.today!.startDayDone, isTrue);
      await tracker.heartbeat();
      expect(shown.last.$2, isTrue, reason: 'day started: at work');
      await tracker.stop();
      final readings = await admin.call('GET', '/odometer/readings?vehicle_id=${vehicle['id']}') as List;
      final start = readings.firstWhere((r) => r['kind'] == 'start_day');
      expect((start['value_km'], start['source']), (30120, 'device'));
      expect(
        DateTime.parse(start['recorded_at'] as String).difference(taken).inSeconds.abs(),
        lessThan(2),
        reason: 'the photo time, not the sending time',
      );

      // a retry of the same reading (an answer lost on the way) is "already recorded", not a failure
      final again = await jpeg('odo2');
      expect(
        await state.sendReading(kind: 'start_day', km: 30120, photoPath: again.path, takenAt: taken),
        SendResult.sent,
      );

      // ---- daily report: after a started day, the server waits for the end-of-day reading
      final day = DateTime.now().toUtc().add(const Duration(hours: 3)).toIso8601String().substring(0, 10);
      expect(state.endReadingDue, isTrue);
      await expectLater(
        state.sendReport(businessDate: day, orders: 21, cash: '17.250', screenshotPath: (await jpeg('early')).path),
        throwsA(isA<ApiError>().having((e) => e.code, 'code', 'end_reading_required')),
      );
      expect(
        await state.sendReading(
          kind: 'end_day',
          km: 30210,
          photoPath: (await jpeg('odo-end')).path,
          takenAt: DateTime.now().toUtc(),
        ),
        SendResult.sent,
      );
      expect((state.today!.endDayDone, state.endReadingDue), (true, false));
      final shot = await jpeg('shot');
      expect(
        await state.sendReport(businessDate: day, orders: 21, cash: '17.250', screenshotPath: shot.path),
        SendResult.sent,
      );
      final reports = await admin.call('GET', '/daily-reports?driver_id=${driver['id']}') as List;
      expect(
        (reports.single['orders_count'], reports.single['cash_amount'], reports.single['has_screenshot']),
        (21, '17.250', true),
      );
      expect(state.reports.single.status, 'submitted');
      // corrected before review (FR-DWR-06): the same report takes the new figures
      expect(await state.changeReport(state.reports.single, orders: 22, cash: '17.500'), SendResult.sent);
      final corrected = state.reports.single;
      expect((corrected.orders, corrected.cash, corrected.status), (22, '17.500', 'submitted'));

      // ---- he works again the same day: a new session, its own end reading and report, adding to the day
      expect(
        await state.sendReading(
          kind: 'start_day',
          km: 30215,
          photoPath: (await jpeg('odo-again')).path,
          takenAt: DateTime.now().toUtc(),
        ),
        SendResult.sent,
      );
      expect((state.today!.startDayDone, state.today!.endDayDone, state.today!.sessions), (true, false, 2));
      expect(
        await state.sendReading(
          kind: 'end_day',
          km: 30260,
          photoPath: (await jpeg('odo-end2')).path,
          takenAt: DateTime.now().toUtc(),
        ),
        SendResult.sent,
      );
      expect(state.today!.endDayDone, isTrue);
      expect(
        await state.sendReport(businessDate: day, orders: 4, cash: '2.500', screenshotPath: (await jpeg('shot2')).path),
        SendResult.sent,
      );
      final both = await admin.call('GET', '/daily-reports?driver_id=${driver['id']}') as List;
      expect([for (final r in both) (r['session'], r['orders_count'])]..sort((a, b) => a.$1 - b.$1), [(1, 22), (2, 4)]);

      // ---- his profile, his car and a change asked for, his cash movements, a renewed document (FR-APP-01..05)
      await state.loadProfile();
      expect(state.profile!.employeeNumber, 'C$n');
      expect(state.profile!.named('company'), isNotNull);
      await state.loadVehicle();
      expect((state.myVehicle!.vehicle!['plate_number'], state.myVehicle!.request), ('77/$n', null));
      await state.requestVehicleChange('المكيف لا يعمل');
      expect(state.myVehicle!.requestPending, isTrue);
      await state.loadCash();
      expect(state.cash!.lines.first.kind, 'collection');
      expect(state.cash!.lines.first.status, 'pending');
      await admin.call('POST', '/documents', {
        'owner_type': 'employee',
        'owner_id': driver['id'],
        'type_code': 'residence',
        // in 10 days by Kuwait's calendar, as the server counts (UTC+3: from 21:00 UTC it is already tomorrow there)
        'expiry_date': DateTime.now()
            .toUtc()
            .add(const Duration(days: 10, hours: 3))
            .toIso8601String()
            .substring(0, 10),
        'file_sha256': await admin.upload(await jpeg('residence')),
      });
      await state.loadDocuments();
      final residence = state.documents.firstWhere((d) => d.typeCode == 'residence');
      expect((residence.state, residence.daysLeft, residence.renewable), ('expiring', 10, true));
      expect(
        await state.sendRenewal(
          typeCode: 'residence',
          expiry: DateTime.now().add(const Duration(days: 400)).toIso8601String().substring(0, 10),
          number: 'R-$n',
          filePath: (await jpeg('renewal')).path,
        ),
        SendResult.sent,
      );
      expect(state.documents.firstWhere((d) => d.typeCode == 'residence').renewalPending, isTrue);

      // ---- maintenance: a request for the vehicle held, with two camera photos; the office sees it with them
      final p1 = await jpeg('mnt1');
      final p2 = await jpeg('mnt2');
      expect(
        await state.sendMaintenance(
          kind: 'tyres',
          description: 'Flat rear tyre',
          km: 30150,
          photoPaths: [p1.path, p2.path],
        ),
        SendResult.sent,
      );
      expect(state.maintenance.single.status, 'requested');
      final office = await admin.call('GET', '/maintenance/requests?vehicle_id=${vehicle['id']}') as List;
      expect(
        (office.single['kind'], office.single['source'], office.single['driver']['id']),
        ('tyres', 'driver', driver['id']),
      );
      final request = await admin.call('GET', '/maintenance/requests/${office.single['id']}');
      expect((request['photos'] as List).length, 2);

      // ---- accident: three camera photos now, the police report later; a center estimates, the office decides the
      // driver is liable: 150.000 in 3 installments, which the driver sees in the app
      final shots = [
        for (final s in ['acc1', 'acc2', 'acc3']) (await jpeg(s)).path,
      ];
      expect(
        await state.sendAccident(
          occurredAt: DateTime.now(),
          lat: 29.37,
          lng: 47.97,
          description: 'Rear-ended at a traffic light',
          injuries: false,
          photoPaths: shots,
        ),
        SendResult.sent,
      );
      final mine = state.accidents.single;
      expect((mine.stage, mine.awaitsPoliceReport), ('reported', true));
      final police = await jpeg('police');
      expect(
        await state.sendPoliceReport(accidentId: mine.id, photoPath: police.path, number: 'PR-$n'),
        SendResult.sent,
      );
      expect(state.accidents.single.hasPoliceReport, isTrue);
      final acc = await admin.call('GET', '/accidents/${mine.id}');
      expect(
        (acc['driver']['id'], acc['source'], (acc['photos'] as List).length, acc['police_report_no'], acc['lat']),
        (driver['id'], 'driver', 3, 'PR-$n', 29.37),
      );
      final center = await admin.call('POST', '/maintenance/centers', {'name': 'Contract Garage $n'});
      await admin.call('POST', '/maintenance/centers/${center['id']}/users', {
        'username': 'cg$n',
        'full_name': 'Contract Garage',
        'password': 'correct-horse-battery-$n',
      });
      await admin.call('POST', '/accidents/${mine.id}/refer', {'center_id': center['id']});
      final portal = Admin(backend!);
      final portalLogin = await portal.call('POST', '/auth/login', {
        'username': 'cg$n',
        'password': 'correct-horse-battery-$n',
      });
      portal.csrf = portalLogin['csrf_token'] as String;
      await portal.call('POST', '/portal/accidents/${mine.id}/estimate', {
        'total': '150.000',
        'items': [
          {'kind': 'part', 'description': 'Rear bumper', 'unit_price': '150.000'},
        ],
      });
      await admin.call('POST', '/accidents/${mine.id}/estimate/approve');
      await admin.call('POST', '/accidents/${mine.id}/outcome', {'liability': 'driver', 'installments': 3});
      await state.loadAccidents();
      final charged = state.accidents.single;
      expect((charged.liability, charged.deduction!.total, charged.deduction!.installments), ('driver', '150.000', 3));
      expect([for (final s in charged.deduction!.schedule) s.amount], ['50.000', '50.000', '50.000']);
      expect(charged.awaitsPoliceReport, isFalse);

      // ---- a traffic fine on the vehicle while the driver held it: charged in 2 installments, seen in the app
      final ticket = await admin.call('POST', '/fines', {
        'vehicle_id': vehicle['id'],
        'occurred_at': DateTime.now().toUtc().subtract(const Duration(seconds: 5)).toIso8601String(),
        'violation': 'Speeding',
        'amount': '30.000',
        'reference_no': 'C-$n',
      });
      expect(ticket['driver']['id'], driver['id'], reason: 'the driver is found from the custody log');
      await admin.call('POST', '/fines/${ticket['id']}/charge', {'installments': 2});
      await state.loadFines();
      expect((state.fines.single.status, state.fines.single.deduction!.total), ('charged', '30.000'));
      expect([for (final s in state.fines.single.deduction!.schedule) s.amount], ['15.000', '15.000']);

      // ---- what he was told: the fine charged to him, then read
      await state.loadNotices();
      expect(state.notices!.items.first.kind, 'fine_charged');
      expect(state.notices!.items.first.message, contains('30.000'));
      expect(state.notices!.unread, greaterThan(0));
      await state.readNotices();
      expect(state.notices!.unread, 0);

      // ---- cash, then sign out: the phone forgets the session and the server refuses its tokens
      await state.loadCash();
      expect(state.cash!.pending, '20.000'); // the corrected report's cash, not doubled, and the second session's
      final oldRefresh = (await db.get('refresh_token'))!;
      await state.signOut();
      expect(state.phase, Phase.signedOut);
      expect(await state.tokens.hasSession(), isFalse);
      final refused = await http.post(
        Uri.parse('$backend/api/v1/driver/auth/refresh'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh_token': oldRefresh}),
      );
      expect(refused.statusCode, 401, reason: 'signed out: the old tokens are dead on the server too');
    },
    skip: backend == null ? 'set BACKEND_URL to run against a real backend' : null,
    timeout: const Timeout(Duration(minutes: 2)),
  );

  test(
    'self-registration: link with registration, draft with document and vehicle photos, sent for review',
    () async {
      final admin = await signedInAdmin();
      final n = DateTime.now().millisecondsSinceEpoch % 10000000;
      final company = await companyId(admin);
      final driver = await admin.call('POST', '/employees', {
        'employee_number': 'R$n',
        'name': {'ar': 'سائق جديد', 'en': 'New Driver'},
        'company_id': company,
        'is_driver': true,
        'phone': '+9656${n.toString().padLeft(7, '0')}',
        'iban': 'KW81CBKU0000000000001234560101', // the office has his bank already
        'bank_name': 'NBK',
      });
      await admin.call('PUT', '/employees/${driver['id']}/app-access', {'app_access': 'active'});
      final vehicle = await admin.call('POST', '/vehicles', {
        'plate_number': '88/$n',
        'company_id': company,
        'last_odometer_km': 50000,
      });
      final link = await admin.call('POST', '/employees/${driver['id']}/activation-link', {
        'channel': 'manual',
        'onboarding': true,
      });
      expect(link['onboarding'], isTrue);

      final db = await testDb();
      final state = appAgainstBackend(db);
      await state.activate(AppState.activationToken(Uri.parse(link['url'] as String))!);
      expect(state.phase, Phase.onboarding);
      final ob = state.onboarding!;
      // what the office has comes back locked (the IBAN by its last four digits), the nationality list with it
      expect(
        (ob.known.label('ar'), ob.known.employeeNumber, ob.known.ibanLast4, ob.known.bankName),
        ('سائق جديد', 'R$n', '0101', 'NBK'),
      );
      expect(ob.known.locked, ['iban', 'bank_name']);
      final india = ob.nationalities.firstWhere((x) => x.en == 'India');

      // the payload exactly as the registration screen builds it
      Future<String> up(String name, String source) async =>
          (await state.api.upload((await jpeg(name)).path, source: source))['sha256'] as String;
      final draft = {
        'civil_id': '2900101${n.toString().padLeft(5, '0').substring(0, 5)}',
        'nationality': india.value,
        'iban': null, // locked: the screen sends nothing for them
        'bank_name': null,
        'documents': [
          for (final code in ob.requiredDocuments)
            {
              'type_code': code,
              'number': 'N-$code',
              'expiry_date': '2028-01-31',
              'front_sha256': await up('$code-f', 'upload'),
              'back_sha256': await up('$code-b', 'upload'),
            },
        ],
        'no_vehicle': false,
        'vehicle': {
          'plate_number': '88/$n',
          'odometer_km': 50200,
          'odometer_photo': await up('odo', 'camera'),
          'photos': [
            for (final p in ob.vehiclePhotos) {'position': p, 'sha256': await up(p, 'camera')},
          ],
        },
      };
      await state.api.put('/driver/onboarding', body: draft);
      await state.api.post('/driver/onboarding/submit');
      await state.refresh();
      expect(state.phase, Phase.waiting);
      final queue = await admin.call('GET', '/onboarding?status=submitted&limit=200') as List;
      final mine = queue.firstWhere((s) => s['employee']['id'] == driver['id']);
      expect(mine['plate_number'], '88/$n');
      final detail = await admin.call('GET', '/onboarding/${mine['id']}');
      expect((detail['vehicle']['found'], detail['vehicle']['id']), (true, vehicle['id']));
      expect(detail['data']['nationality'], india.value);
    },
    skip: backend == null ? 'set BACKEND_URL to run against a real backend' : null,
    timeout: const Timeout(Duration(minutes: 2)),
  );

  test(
    'pay schemes: the office puts him on one, he reads the terms and asks for another, the office approves',
    () async {
      final admin = await signedInAdmin();
      final n = DateTime.now().millisecondsSinceEpoch % 10000000;
      final platform = await admin.call('POST', '/payroll/platforms', {
        'code': 's$n',
        'name': {'ar': 'منصة الأنظمة', 'en': 'Schemes platform'},
      });
      final fixed = await admin.call('POST', '/payroll/schemes', {
        'platform_id': platform['id'],
        'code': 'fixed',
        'name': {'ar': 'سعر ثابت', 'en': 'Fixed'},
        'calculator': 'per_order',
        'per_order': '0.350',
        'company_covers': ['maintenance', 'sim'],
      });
      final tiers = await admin.call('POST', '/payroll/schemes', {
        'platform_id': platform['id'],
        'code': 'tiers',
        'name': {'ar': 'الشرائح', 'en': 'Tiers'},
        'calculator': 'tiered_target',
        'per_order': '0.350',
        'reduced_rate': '0.200',
        'missing_order_rate': '0.350',
        'steps': [
          {'kind': 'tier_bonus', 'threshold': 450, 'amount': '50.000'},
          {'kind': 'marks_deduction', 'threshold': 3, 'amount': '10.000'},
          {'kind': 'marks_reduce', 'threshold': 5},
        ],
      });
      // a company of its own, so the month's payroll is this test's alone
      final own = await admin.call('POST', '/companies', {
        'name': {'ar': 'شركة الأنظمة $n', 'en': 'Schemes Company $n'},
      });
      final driver = await admin.call('POST', '/employees', {
        'employee_number': 'S$n',
        'name': {'ar': 'سائق الأنظمة', 'en': 'Schemes Driver'},
        'company_id': own['id'],
        'iban': 'KW81CBKU0000000000001234560101',
        'is_driver': true,
        'phone': '+9656${n.toString().padLeft(7, '0')}',
        'platform_id': platform['id'],
      });
      final month = DateTime.now().toIso8601String().substring(0, 7);
      await admin.call('POST', '/payroll/schemes/${fixed['id']}/assign', {
        'employee_ids': [driver['id']],
        'month': '$month-01',
      });
      await admin.call('PUT', '/employees/${driver['id']}/app-access', {'app_access': 'active'});
      final link = await admin.call('POST', '/employees/${driver['id']}/activation-link', {
        'channel': 'manual',
        'onboarding': false,
      });
      final db = await testDb();
      final state = appAgainstBackend(db);
      await state.activate(AppState.activationToken(Uri.parse(link['url'] as String))!);

      // ---- the app reads the server's own JSON: amounts, thresholds, who pays what
      await state.loadSchemes();
      final v = state.schemes!;
      expect((v.current!.code, v.current!.perOrder), ('fixed', '0.350'));
      expect(v.current!.companyCovers, ['maintenance', 'sim']);
      final offered = v.offered.firstWhere((s) => s.code == 'tiers');
      expect([for (final s in offered.stepsOf('tier_bonus')) (s.threshold, s.amount)], [(450, '50.000')]);
      expect(offered.stepsOf('marks_reduce').single.amount, isNull);
      expect(offered.reducedRate, '0.200');

      // ---- he asks for the tiers from next month; the office approves; the app shows the change
      await state.requestScheme(tiers['id'] as String, note: 'من الشهر الجاي');
      expect((state.schemes!.request!.status, state.schemes!.request!.requestedLabel('ar')), ('pending', 'الشرائح'));
      final pending = (await admin.call('GET', '/payroll/scheme-requests?status=pending&limit=500') as List).firstWhere(
        (r) => r['employee']['id'] == driver['id'],
      );
      await admin.call('POST', '/payroll/scheme-requests/${pending['id']}/approve', {'version': pending['version']});
      await state.loadSchemes();
      expect(state.schemes!.request!.status, 'approved');
      expect(state.schemes!.nextMonth!.code, 'tiers');
      expect(state.schemes!.current!.code, 'fixed', reason: 'this month stays as it was');

      // ---- the month on the fixed price, approved: the payslip explains it in the app
      await admin.call('POST', '/payroll/statements', {
        'employee_id': driver['id'],
        'month': '$month-01',
        'orders': 300,
      });
      final settings = await admin.call('GET', '/settings');
      await admin.call('PUT', '/settings/payroll', {
        'version': settings['payroll']['version'],
        'value': {'max_deduction_percent': '50.00', 'deduction_cap_base': 'gross'},
      });
      final run = await admin.call('POST', '/payroll/runs', {'company_id': own['id'], 'month': '$month-01'});
      await admin.call('POST', '/payroll/runs/${run['id']}/approve');
      await state.loadPayslips();
      final slip = state.payslips.single;
      expect(slip.scheme('ar'), 'سعر ثابت');
      expect([for (final b in slip.breakdown) (b.code, b.amount)], [('orders_pay', '105.000')]); // 300 x 0.350
      expect(slip.breakdown.single.why, {'orders': 300, 'rate': '0.350'});
      expect(slip.net, '105.000');
    },
    skip: backend == null ? 'set BACKEND_URL to run against a real backend' : null,
    timeout: const Timeout(Duration(minutes: 2)),
  );

  test(
    'monthly statement from the app, reviewed, then the payroll and the payslip in the platform order',
    () async {
      final admin = await signedInAdmin();
      final n = DateTime.now().millisecondsSinceEpoch % 10000000;
      final platform = await admin.call('POST', '/payroll/platforms', {
        'code': 'c$n',
        'name': {'ar': 'منصة العقد', 'en': 'Contract platform'},
        'driver_fields': ['valid_days'],
        'invalid_days': 'daily_wage',
        'columns': [
          {'code': 'platform_driver_id', 'header': 'driver id'},
          {'code': 'valid_days', 'header': 'عدد الأيام الصالحة'},
          {'code': 'invalid_days_deduction', 'header': 'خصم الأيام الغير صالحة'},
          {'code': 'net', 'header': 'صافي الراتب'},
        ],
      });
      // a company of its own, so the month's payroll is this test's alone
      final own = await admin.call('POST', '/companies', {
        'name': {'ar': 'شركة $n', 'en': 'Company $n'},
      });
      final driver = await admin.call('POST', '/employees', {
        'employee_number': 'P$n',
        'name': {'ar': 'سائق الرواتب', 'en': 'Payroll Driver'},
        'company_id': own['id'],
        'is_driver': true,
        'phone': '+9655${n.toString().padLeft(7, '0')}',
        'basic_salary': '300.000',
        'iban': 'KW81CBKU0000000000001234560101',
        'payment_method': 'bank',
        'platform_id': platform['id'],
        'platform_driver_id': 'K-$n',
      });
      await admin.call('PUT', '/employees/${driver['id']}/app-access', {'app_access': 'active'});
      final link = await admin.call('POST', '/employees/${driver['id']}/activation-link', {
        'channel': 'manual',
        'onboarding': false,
      });
      final db = await testDb();
      final state = appAgainstBackend(db);
      await state.activate(AppState.activationToken(Uri.parse(link['url'] as String))!);

      // ---- the app: what the platform asks for, then the month with two screenshots from the gallery
      await state.loadStatements();
      expect(state.statements!.driverFields, ['valid_days']);
      expect(state.statements!.platformName('ar'), 'منصة العقد');
      final month = state.statements!.months.last;
      final r = await state.sendStatement(
        month: month,
        validDays: 22,
        screenshotPaths: [(await jpeg('s1')).path, (await jpeg('s2')).path],
      );
      expect(r, SendResult.sent);
      expect(state.statements!.statements.single.status, 'submitted');
      expect(state.statements!.statements.single.declared['valid_days'], 22);

      // ---- the office reviews it against the screenshots, then the payroll of that company and month
      final sent = (await admin.call('GET', '/payroll/statements?status=submitted&limit=500') as List).firstWhere(
        (s) => s['employee']['id'] == driver['id'],
      );
      expect((sent['screenshots'] as List).length, 2);
      await admin.call('POST', '/payroll/statements/${sent['id']}/approve', {'working_days': 25, 'valid_days': 22});
      final settings = await admin.call('GET', '/settings');
      await admin.call('PUT', '/settings/payroll', {
        'version': settings['payroll']['version'],
        'value': {'max_deduction_percent': '50.00', 'deduction_cap_base': 'gross'},
      });
      final run = await admin.call('POST', '/payroll/runs', {'company_id': own['id'], 'month': month});
      await admin.call('POST', '/payroll/runs/${run['id']}/approve');

      // ---- the payslip in the app: 300 less 3 days x 10 = 270, in the platform's rows without the driver id
      await state.loadPayslips();
      final slip = state.payslips.single;
      expect((slip.month, slip.status, slip.net), (month, 'approved', '270.000'));
      expect(
        [for (final row in slip.rows) row.header],
        ['عدد الأيام الصالحة', 'خصم الأيام الغير صالحة', 'صافي الراتب'],
      );
      expect([for (final row in slip.rows) row.value], ['22', '30.000', '270.000']);
    },
    skip: backend == null ? 'set BACKEND_URL to run against a real backend' : null,
    timeout: const Timeout(Duration(minutes: 2)),
  );

  test(
    'maintenance straight to the center: picked by the driver, repaired, invoiced, collected, his again',
    () async {
      final admin = await signedInAdmin();
      Future<void> direct(bool on) async {
        final settings = await admin.call('GET', '/settings') as Map;
        final current = settings['maintenance'] as Map;
        await admin.call('PUT', '/settings/maintenance', {
          'version': current['version'],
          'value': {...current['value'] as Map, 'direct_to_center': on},
        });
      }

      await direct(true);
      addTearDown(() => direct(false));
      final n = DateTime.now().millisecondsSinceEpoch % 10000000;
      final company = await companyId(admin);
      final driver = await admin.call('POST', '/employees', {
        'employee_number': 'M$n',
        'name': {'ar': 'سائق الصيانة', 'en': 'Maintenance Driver'},
        'company_id': company,
        'is_driver': true,
        'phone': '+9656${n.toString().padLeft(7, '0')}',
      });
      await admin.call('PUT', '/employees/${driver['id']}/app-access', {'app_access': 'active'});
      final vehicle = await admin.call('POST', '/vehicles', {
        'plate_number': '66/$n',
        'company_id': company,
        'last_odometer_km': 40000,
      });
      await admin.call('POST', '/custodies', {
        'vehicle_id': vehicle['id'],
        'driver_id': driver['id'],
        'odometer_km': 40000,
        'photo_sha256': await admin.upload(await jpeg('handover')),
        'started_at': DateTime.now().toUtc().subtract(const Duration(hours: 2)).toIso8601String(),
      });
      final center = await admin.call('POST', '/maintenance/centers', {
        'name': 'Direct Garage $n',
        'address': 'Shuwaikh, block 1',
      });
      await admin.call('POST', '/maintenance/centers/${center['id']}/users', {
        'username': 'dg$n',
        'full_name': 'Direct Garage',
        'password': 'correct-horse-battery-$n',
      });
      final link = await admin.call('POST', '/employees/${driver['id']}/activation-link', {
        'channel': 'manual',
        'onboarding': false,
      });
      final db = await testDb();
      final state = appAgainstBackend(db);
      await state.activate(AppState.activationToken(Uri.parse(link['url'] as String))!);

      // ---- the driver picks the center: the request is there at once, no office step
      await state.loadMaintenance();
      expect(state.maintenanceForm.direct, isTrue);
      final picked = state.maintenanceForm.centers.firstWhere((c) => c.name == 'Direct Garage $n');
      expect(picked.address, 'Shuwaikh, block 1');
      expect(
        await state.sendMaintenance(
          kind: 'electrical',
          description: 'Battery does not charge',
          photoPaths: [(await jpeg('mnt')).path],
          centerId: picked.id,
        ),
        SendResult.sent,
      );
      final mine = state.maintenance.single;
      expect((mine.status, mine.centerName), ('referred', 'Direct Garage $n'));

      // ---- the center: reception, done, the invoice, then the driver is called
      final portal = Admin(backend!);
      final login = await portal.call('POST', '/auth/login', {
        'username': 'dg$n',
        'password': 'correct-horse-battery-$n',
      });
      portal.csrf = login['csrf_token'] as String;
      await portal.call('POST', '/portal/requests/${mine.id}/receive', {
        'odometer_km': 40050,
        'odometer_photo': await portal.upload(await jpeg('in')),
      });
      await portal.call('POST', '/portal/requests/${mine.id}/complete', {
        'repair_details': 'Battery replaced',
        'final_odometer_km': 40052,
        'final_odometer_photo': await portal.upload(await jpeg('out')),
      });
      final day = DateTime.now().toUtc().add(const Duration(hours: 3)).toIso8601String().substring(0, 10);
      await portal.call('POST', '/portal/invoices', {
        'request_id': mine.id,
        'number': 'D-$n',
        'invoice_date': day,
        'total': '35.000',
        'file_sha256': await portal.upload(await jpeg('invoice')),
        'items': [
          {'kind': 'part', 'description': 'Battery', 'unit_price': '35.000'},
        ],
      });
      await portal.call('POST', '/portal/requests/${mine.id}/ready', {});
      await state.loadMaintenance();
      await state.loadToday();
      expect((state.maintenance.single.isReady, state.today!.custody), (true, null));

      // ---- he collects it: the car is his again, his day can start
      expect(
        await state.sendPickup(
          requestId: mine.id,
          km: 40060,
          photoPath: (await jpeg('pickup')).path,
          takenAt: DateTime.now().toUtc(),
        ),
        SendResult.sent,
      );
      expect(state.maintenance.single.status, 'picked_up');
      expect((state.today!.custody!.plate, state.today!.custody!.lastKm), ('66/$n', 40060));
      // a retry from the queue is "already collected", not a failure
      expect(
        await state.sendPickup(
          requestId: mine.id,
          km: 40060,
          photoPath: (await jpeg('pickup2')).path,
          takenAt: DateTime.now().toUtc(),
        ),
        SendResult.sent,
      );
    },
    skip: backend == null ? 'set BACKEND_URL to run against a real backend' : null,
    timeout: const Timeout(Duration(minutes: 2)),
  );

  test(
    'civil ID and the initial password from the office, the phone, the code step',
    () async {
      final admin = await signedInAdmin();
      final n = DateTime.now().millisecondsSinceEpoch % 10000000;
      final company = await companyId(admin);
      final civil = '29$n'.padRight(12, '1').substring(0, 12);
      final driver = await admin.call('POST', '/employees', {
        'employee_number': 'Q$n',
        'name': {'ar': 'سائق بلا هاتف', 'en': 'No Phone Driver'},
        'company_id': company,
        'is_driver': true,
        'civil_id': civil,
      });
      final set = await admin.call('POST', '/driver-claims', {
        'employee_ids': [driver['id']],
        'password': '12345678',
        'days': 7,
      });
      expect(set['set'], 1);

      final db = await testDb();
      final state = appAgainstBackend(db);
      final claim = await state.claimStart(civil, '12345678');
      expect((claim.next, claim.name['ar']), ('phone', 'سائق بلا هاتف'));
      final sentTo = await state.claimPhone(claim.token!, '+9654${n.toString().padLeft(7, '0')}');
      expect(sentTo, endsWith(n.toString().padLeft(7, '0').substring(3)));
      Object? refused;
      try {
        await state.claimVerify(claim.token!, '000000');
      } catch (e) {
        refused = e;
      }
      expect('$refused', contains('otp_invalid'), reason: 'the code from WhatsApp is what proves the phone');
    },
    skip: backend == null ? 'set BACKEND_URL to run against a real backend' : null,
    timeout: const Timeout(Duration(minutes: 2)),
  );

  test(
    'without phone codes: the initial password, his own password, then his own password on another phone',
    () async {
      final admin = await signedInAdmin();
      Future<void> phoneCodes(bool on) async {
        final settings = await admin.call('GET', '/settings') as Map;
        await admin.call('PUT', '/settings/driver_sign_in', {
          'version': (settings['driver_sign_in'] as Map)['version'],
          'value': {'phone_codes': on},
        });
      }

      await phoneCodes(false);
      addTearDown(() => phoneCodes(true));
      final n = DateTime.now().millisecondsSinceEpoch % 10000000;
      final civil = '28$n'.padRight(12, '2').substring(0, 12);
      final driver = await admin.call('POST', '/employees', {
        'employee_number': 'P$n',
        'name': {'ar': 'سائق بشريحة متغيرة', 'en': 'Rotating SIM Driver'},
        'company_id': await companyId(admin),
        'is_driver': true,
        'civil_id': civil,
      });
      await admin.call('POST', '/driver-claims', {
        'employee_ids': [driver['id']],
        'password': '12345678',
        'days': 7,
      });

      final first = appAgainstBackend(await testDb());
      await first.loadAppConfig();
      expect(first.phoneCodes, isFalse, reason: 'the sign-in screen shows the civil ID and a password only');
      final claim = await first.claimStart(civil, '12345678');
      expect(claim.next, 'password');
      await first.claimPassword(claim.token!, 'own-pass-$n');
      expect(first.phase, Phase.onboarding, reason: 'signed in, the self-registration next');

      final second = appAgainstBackend(await testDb());
      final again = await second.claimStart(civil, 'own-pass-$n');
      expect((again.next, again.token), ('done', null));
      expect(second.phase, Phase.onboarding);
      final devices = await admin.call('GET', '/employees/${driver['id']}/devices') as List;
      expect(devices.where((d) => d['revoked_at'] == null).length, 1, reason: 'one phone at a time');
    },
    skip: backend == null ? 'set BACKEND_URL to run against a real backend' : null,
    timeout: const Timeout(Duration(minutes: 2)),
  );

  test(
    'the office hides a screen: the app drops its button and the server refuses it',
    () async {
      final admin = await signedInAdmin();
      Future<void> hide(List<String> screens) async {
        final settings = await admin.call('GET', '/settings') as Map;
        await admin.call('PUT', '/settings/driver_app', {
          'version': (settings['driver_app'] as Map)['version'],
          'value': {'hidden_screens': screens},
        });
      }

      final driver = await admin.call('POST', '/employees', {
        'employee_number': 'H${DateTime.now().millisecondsSinceEpoch % 10000000}',
        'name': {'ar': 'سائق الشاشات', 'en': 'Screens Driver'},
        'company_id': await companyId(admin),
        'is_driver': true,
        'phone': '+9656${(DateTime.now().millisecondsSinceEpoch % 10000000).toString().padLeft(7, '0')}',
      });
      await admin.call('PUT', '/employees/${driver['id']}/app-access', {'app_access': 'active'});
      final link = await admin.call('POST', '/employees/${driver['id']}/activation-link', {
        'channel': 'manual',
        'onboarding': false,
      });
      final state = appAgainstBackend(await testDb());
      await state.activate((link['url'] as String).split('#t=')[1]);
      expect(await state.api.get('/driver/maintenance'), isA<List>());

      await hide(['maintenance']);
      addTearDown(() => hide([]));
      await state.loadAppConfig();
      expect((state.shows('maintenance'), state.shows('fines')), (false, true));
      Object? refused;
      try {
        await state.api.get('/driver/maintenance');
      } catch (e) {
        refused = e;
      }
      expect('$refused', contains('screen_off'), reason: 'hidden is refused by the server, not only by the app');
    },
    skip: backend == null ? 'set BACKEND_URL to run against a real backend' : null,
    timeout: const Timeout(Duration(minutes: 2)),
  );
}
