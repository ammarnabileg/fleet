import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:fleet_driver/app/state.dart';
import 'package:fleet_driver/core/api.dart';
import 'package:fleet_driver/core/db.dart';
import 'package:fleet_driver/core/tokens.dart';
import 'package:fleet_driver/core/updater.dart';
import 'package:fleet_driver/l10n/app_localizations.dart';
import 'package:fleet_driver/main.dart';
import 'package:fleet_driver/ui/screens/update.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'support.dart';

/// The in-app update: the check, the optional banner, the required screen (the queue still goes), the download
/// checked byte for byte, the "install unknown apps" permission, the throttle.

final apk = List<int>.generate(5000, (i) => i % 251);
String get apkSha => sha256.convert(apk).toString();

Map<String, dynamic> latest({int code = 9, bool required = false, String? sha, int? size}) => {
  'latest': {
    'version_code': code,
    'version_name': '0.$code.0',
    'size': size ?? apk.length,
    'sha256': sha ?? apkSha,
    'notes': 'Faster sign-in',
    'url': '/api/v1/driver/app-update/$code.apk',
  },
  'required': required,
};

/// The APK route, honouring Range like the server does from its disk.
MockClient apkServer(FakeServer server, {List<int>? body, List<String>? ranges}) {
  final bytes = body ?? apk;
  return MockClient((req) async {
    if (req.url.path.endsWith('.apk')) {
      final range = req.headers['Range'];
      ranges?.add(range ?? '');
      if (range != null) {
        final from = int.parse(RegExp(r'bytes=(\d+)-').firstMatch(range)!.group(1)!);
        return http.Response.bytes(bytes.sublist(from), 206);
      }
      return http.Response.bytes(bytes, 200);
    }
    return server.client.send(req).then(http.Response.fromStream);
  });
}

class Phone {
  Phone({this.allowed = true, this.wifi = true});
  bool allowed;
  bool wifi;
  final installed = <String>[];
  var settingsOpened = 0;
  late Directory dir;

  UpdateHooks hooks() => UpdateHooks(
    dir: () async => dir,
    canInstall: () async => allowed,
    openInstallSettings: () async => settingsOpened++,
    install: (path) async {
      installed.add(path);
      return true;
    },
    unmetered: () async => wifi,
  );
}

Future<(AppDb, Api, FakeServer, Phone)> setUpPhone({bool signedIn = false, Phone? phone}) async {
  final db = await testDb();
  final server = FakeServer();
  final tokens = TokenStore(db);
  if (signedIn) await tokens.save(tokensJson('1'));
  final api = Api(baseUrl: 'http://fleet.test', tokens: tokens, client: server.client);
  final p = phone ?? Phone();
  p.dir = await Directory.systemTemp.createTemp('updates');
  return (db, api, server, p);
}

Updater updater(
  AppDb db,
  Api api,
  Phone phone, {
  http.Client? client,
  DateTime Function()? now,
  Future<void> Function()? beforeBlock,
}) => Updater(
  db: db,
  api: api,
  hooks: phone.hooks(),
  currentBuild: 5,
  client: client,
  now: now,
  beforeBlock: beforeBlock,
);

void main() {
  group('the check', () {
    test('up to date: nothing offered', () async {
      final (db, api, server, phone) = await setUpPhone();
      server.on('GET', '/api/v1/driver/app-update', (r) => (200, {'latest': null, 'required': false}));
      final u = updater(db, api, phone);
      expect(await u.check(), isTrue);
      expect(u.available, isNull);
      expect(u.showBanner, isFalse);
      expect(u.blocking, isFalse);
      final req = server.calls('/api/v1/driver/app-update').single;
      expect(req.url.queryParameters['version_code'], '5');
      expect(req.headers['Authorization'], isNull, reason: 'no session needed: the sign-in screen updates too');
    });

    test('throttled: once every 6 hours unless the driver asks', () async {
      final (db, api, server, phone) = await setUpPhone();
      server.on('GET', '/api/v1/driver/app-update', (r) => (200, {'latest': null, 'required': false}));
      var clock = DateTime(2026, 10, 1, 8);
      final u = updater(db, api, phone, now: () => clock);
      await u.check();
      clock = clock.add(const Duration(hours: 2));
      await u.check();
      expect(server.calls('/api/v1/driver/app-update'), hasLength(1));
      await u.check(force: true);
      expect(server.calls('/api/v1/driver/app-update'), hasLength(2));
      clock = clock.add(const Duration(hours: 7));
      await u.check();
      expect(server.calls('/api/v1/driver/app-update'), hasLength(3));
      // the time of the last check is kept: a restart does not ask again at once
      final again = updater(db, api, phone, now: () => clock);
      await again.load();
      await again.check();
      expect(server.calls('/api/v1/driver/app-update'), hasLength(3));
    });

    test('offline: false, nothing changes', () async {
      final (db, _, _, phone) = await setUpPhone();
      final api = Api(
        baseUrl: 'http://fleet.test',
        tokens: TokenStore(db),
        client: MockClient((_) async => throw const SocketException('offline')),
      );
      final u = updater(db, api, phone);
      expect(await u.check(), isFalse);
      expect(u.available, isNull);
    });
  });

  group('download and install', () {
    test('on Wi-Fi it downloads by itself, checks the sha256, and hands the file to the installer', () async {
      final (db, api, server, phone) = await setUpPhone();
      server.on('GET', '/api/v1/driver/app-update', (r) => (200, latest()));
      final u = updater(db, api, phone, client: apkServer(server));
      await u.check();
      await pumpEventQueue();
      while (u.stage == UpdateStage.downloading) {
        await Future<void>.delayed(const Duration(milliseconds: 10));
      }
      expect(u.stage, UpdateStage.ready);
      await u.install();
      expect(phone.installed.single, endsWith('update-9.apk'));
      expect(await File(phone.installed.single).readAsBytes(), apk);
    });

    test('on mobile data nothing downloads until the driver taps', () async {
      final (db, api, server, phone) = await setUpPhone(phone: Phone(wifi: false));
      server.on('GET', '/api/v1/driver/app-update', (r) => (200, latest()));
      final ranges = <String>[];
      final u = updater(db, api, phone, client: apkServer(server, ranges: ranges));
      await u.check();
      await pumpEventQueue();
      expect(u.stage, UpdateStage.idle);
      expect(ranges, isEmpty);
      await u.install(); // the tap
      expect(ranges, hasLength(1));
      expect(phone.installed, hasLength(1));
    });

    test('a sha256 mismatch is refused and the file deleted', () async {
      final (db, api, server, phone) = await setUpPhone(phone: Phone(wifi: false));
      server.on('GET', '/api/v1/driver/app-update', (r) => (200, latest()));
      final tampered = [...apk]..[100] = 7;
      final u = updater(db, api, phone, client: apkServer(server, body: tampered));
      await u.check();
      await u.download();
      expect(u.stage, UpdateStage.failed);
      expect(u.error, 'checksum');
      expect(phone.dir.listSync(), isEmpty, reason: 'nothing left to install by mistake');
      await u.install();
      expect(phone.installed, isEmpty);
    });

    test('a cut download resumes with a Range request', () async {
      final (db, api, server, phone) = await setUpPhone(phone: Phone(wifi: false));
      server.on('GET', '/api/v1/driver/app-update', (r) => (200, latest()));
      await File('${phone.dir.path}/update-9.apk.part').writeAsBytes(apk.sublist(0, 1200));
      final ranges = <String>[];
      final u = updater(db, api, phone, client: apkServer(server, ranges: ranges));
      await u.check();
      expect(u.received, 1200);
      await u.download();
      expect(ranges, ['bytes=1200-']);
      expect(u.stage, UpdateStage.ready);
      expect(await File('${phone.dir.path}/update-9.apk').readAsBytes(), apk);
    });

    test('"install unknown apps" not allowed: the setting, then the installer on return', () async {
      final (db, api, server, phone) = await setUpPhone(phone: Phone(allowed: false, wifi: false));
      server.on('GET', '/api/v1/driver/app-update', (r) => (200, latest()));
      final u = updater(db, api, phone, client: apkServer(server));
      await u.check();
      await u.install();
      expect(u.stage, UpdateStage.needsPermission);
      expect(phone.installed, isEmpty);
      await u.openInstallSettings();
      expect(phone.settingsOpened, 1);
      await u.resumed(); // back, still not allowed
      expect(u.stage, UpdateStage.needsPermission);
      phone.allowed = true;
      await u.resumed();
      expect(phone.installed, hasLength(1));
    });

    test('old downloads are removed at start', () async {
      final (db, api, _, phone) = await setUpPhone();
      for (final name in ['update-4.apk', 'update-5.apk', 'update-3.apk.part', 'other.txt']) {
        await File('${phone.dir.path}/$name').writeAsString('x');
      }
      final u = updater(db, api, phone);
      await u.load();
      expect(phone.dir.listSync().map((e) => e.uri.pathSegments.last), ['other.txt']);
    });
  });

  group('required', () {
    test('the queue is sent before the screens block, and a required update stays required offline', () async {
      final (db, api, server, phone) = await setUpPhone(signedIn: true, phone: Phone(wifi: false));
      server.on('GET', '/api/v1/driver/app-update', (r) => (200, latest(required: true)));
      server.on('POST', '/api/v1/driver/leaves/l1/cancel', (r) => (200, {'id': 'l1', 'status': 'cancelled'}));
      final state = AppState(
        db: db,
        api: api,
        pollEvery: null,
        updateStringsAtStart: false,
        platform: PhoneHooks(
          permissionsOk: () async => true,
          startTracking: () async {},
          stopTracking: () async {},
          deviceMeta: () async => {},
          updates: phone.hooks(),
        ),
      );
      await state.outbox.add('leave_cancel', {'leave_id': 'l1'}, {});
      var blockedBeforeSend = false;
      state.updater.addListener(() {
        if (state.updater.blocking && server.calls('/api/v1/driver/leaves/l1/cancel').isEmpty) {
          blockedBeforeSend = true;
        }
      });
      await state.updater.check();
      expect(state.updater.blocking, isTrue);
      expect(server.calls('/api/v1/driver/leaves/l1/cancel'), hasLength(1));
      expect(blockedBeforeSend, isFalse);

      final later = updater(db, api, phone);
      await later.load();
      expect(later.blocking, isTrue);
    });

    test('offline at block time: nothing queued is lost', () async {
      final (db, _, _, phone) = await setUpPhone(signedIn: true);
      var online = true;
      final client = MockClient((req) async {
        if (req.url.path == '/api/v1/driver/app-update') return http.Response(jsonEncode(latest(required: true)), 200);
        if (!online || req.url.path.contains('/leaves/')) throw const SocketException('gone');
        return http.Response('{}', 200);
      });
      final api = Api(baseUrl: 'http://fleet.test', tokens: TokenStore(db), client: client);
      final state = AppState(
        db: db,
        api: api,
        pollEvery: null,
        updateStringsAtStart: false,
        platform: PhoneHooks(
          permissionsOk: () async => true,
          startTracking: () async {},
          stopTracking: () async {},
          deviceMeta: () async => {},
          updates: phone.hooks(),
        ),
      );
      await state.outbox.add('leave_cancel', {'leave_id': 'l1'}, {});
      online = false;
      await state.updater.check();
      expect(state.updater.blocking, isTrue);
      final rows = await db.raw.query('outbox');
      expect(rows, hasLength(1));
      expect(rows.single['state'], isNot('failed'));
    });
  });

  group('screens', () {
    Future<Updater> withUpdate(WidgetTester tester, AppState state, Map<String, dynamic> answer) async {
      await tester.runAsync(() => state.updater.check());
      return state.updater;
    }

    Widget app(AppState state, Widget child) => MaterialApp(
      locale: const Locale('en'),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: child),
    );

    Future<(AppState, FakeServer, Phone)> stateWith(WidgetTester tester, Map<String, dynamic> answer) async {
      final (db, api, server, phone) = (await tester.runAsync(() => setUpPhone(phone: Phone(wifi: false))))!;
      server.on('GET', '/api/v1/driver/app-update', (r) => (200, answer));
      final state = AppState(
        db: db,
        api: api,
        pollEvery: null,
        updateStringsAtStart: false,
        platform: PhoneHooks(
          permissionsOk: () async => true,
          startTracking: () async {},
          stopTracking: () async {},
          deviceMeta: () async => {},
          updates: phone.hooks(),
        ),
      );
      return (state, server, phone);
    }

    testWidgets('up to date: no banner', (tester) async {
      final (state, _, _) = await stateWith(tester, {'latest': null, 'required': false});
      await withUpdate(tester, state, {});
      await tester.pumpWidget(app(state, UpdateBanner(state: state)));
      expect(find.byKey(const Key('update-banner')), findsNothing);
    });

    testWidgets('optional: a banner with the version, the notes and size in the sheet, closed for good', (
      tester,
    ) async {
      final (state, _, _) = await stateWith(tester, latest());
      await withUpdate(tester, state, {});
      await tester.pumpWidget(app(state, UpdateBanner(state: state)));
      expect(find.byKey(const Key('update-banner')), findsOneWidget);
      expect(find.textContaining('0.9.0'), findsOneWidget);
      await tester.tap(find.byKey(const Key('update-open')));
      await tester.pumpAndSettle();
      expect(find.text('Faster sign-in'), findsOneWidget);
      expect(find.textContaining('MB'), findsOneWidget);
      expect(find.text('You are on mobile data: the download uses your data plan.'), findsOneWidget);
      Navigator.of(tester.element(find.byType(UpdatePanel))).pop();
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('update-dismiss')));
      await tester.pump();
      expect(find.byKey(const Key('update-banner')), findsNothing);
      expect(state.updater.blocking, isFalse);
    });

    testWidgets('required: the whole app shows the update screen; the tracking hooks are untouched', (tester) async {
      final (state, server, _) = await stateWith(tester, latest(required: true));
      server.on('GET', '/api/v1/driver/app-config', (r) => (200, {'phone_codes': true, 'hidden_screens': []}));
      tester.view.physicalSize = const Size(1080, 2280);
      tester.view.devicePixelRatio = 2.75;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(DriverApp(state: state));
      await tester.runAsync(() => state.boot(deviceLang: 'en'));
      await tester.runAsync(() => state.updater.check());
      expect(state.updater.blocking, isTrue, reason: '${state.updater.error}');
      await tester.pump();
      expect(find.byKey(const Key('update-required')), findsOneWidget);
      expect(find.byKey(const Key('update-go')), findsOneWidget);
      expect(find.text('لازم تحدّث التطبيق عشان تكمل'), findsOneWidget);
    });

    testWidgets('the permission message and its button', (tester) async {
      final (state, server, phone) = await stateWith(tester, latest());
      phone.allowed = false;
      final u = await withUpdate(tester, state, {});
      // the APK is served by the same scripted server
      server.on('GET', '/api/v1/driver/app-update/9.apk', (r) => (200, apk));
      await tester.runAsync(() => u.install());
      await tester.pumpWidget(app(state, UpdatePanel(state: state)));
      await tester.pump();
      expect(find.byKey(const Key('update-permission')), findsOneWidget);
      await tester.tap(find.byKey(const Key('update-settings')));
      await tester.pump();
      expect(phone.settingsOpened, 1);
    });
  });
}
