@Tags(['contract'])
library;

import 'dart:convert';
import 'dart:io';

import 'package:fleet_driver/app/state.dart';
import 'package:fleet_driver/core/db.dart';
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

      // ---- tracking: the server says track (custody open); three fixes go out and are acknowledged
      final now = DateTime.now().toUtc();
      final fixes = Stream<Fix>.fromIterable([
        for (var i = 0; i < 3; i++)
          Fix(
            at: now.subtract(Duration(seconds: 90 - 31 * i)),
            lat: 29.37 + i * 0.001,
            lng: 47.98,
            speedKmh: 35,
            heading: 90,
          ),
      ]);
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
        heartbeatEvery: const Duration(hours: 1),
        syncEvery: const Duration(hours: 1),
      );
      await tracker.start();
      expect(tracker.required, isTrue);
      await Future<void>.delayed(const Duration(milliseconds: 300));
      await tracker.sync();
      expect(await tracker.queue.size(), 0);
      await tracker.stop();
      final live = (await admin.call('GET', '/tracking/live') as List).firstWhere(
        (v) => v['vehicle']['id'] == vehicle['id'],
      );
      expect((live['position']['lat'] as num).toDouble(), closeTo(29.372, 0.0001));

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

      // ---- daily report
      final shot = await jpeg('shot');
      final day = DateTime.now().toUtc().add(const Duration(hours: 3)).toIso8601String().substring(0, 10);
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

      // ---- cash, then sign out: the phone forgets the session and the server refuses its tokens
      await state.loadCash();
      expect(state.cash!.pending, '17.250');
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

      // the payload exactly as the registration screen builds it
      Future<String> up(String name, String source) async =>
          (await state.api.upload((await jpeg(name)).path, source: source))['sha256'] as String;
      final draft = {
        'civil_id': '2900101${n.toString().padLeft(5, '0').substring(0, 5)}',
        'nationality': 'India',
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
    },
    skip: backend == null ? 'set BACKEND_URL to run against a real backend' : null,
    timeout: const Timeout(Duration(minutes: 2)),
  );
}
