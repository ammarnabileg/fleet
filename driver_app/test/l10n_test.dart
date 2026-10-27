import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:fleet_driver/app/state.dart';
import 'package:fleet_driver/core/api.dart';
import 'package:fleet_driver/core/db.dart';
import 'package:fleet_driver/core/icu.dart';
import 'package:fleet_driver/core/tokens.dart';
import 'package:fleet_driver/core/translations.dart';
import 'package:fleet_driver/l10n/app_localizations.dart';
import 'package:fleet_driver/l10n/reference_en.dart';
import 'package:fleet_driver/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'support.dart';

const languages = ['ar', 'en', 'fr', 'sw', 'hi', 'fil'];

Map<String, String> arb(String lang) {
  final j = jsonDecode(File('lib/l10n/app_$lang.arb').readAsStringSync()) as Map<String, dynamic>;
  return {
    for (final e in j.entries)
      if (!e.key.startsWith('@')) e.key: e.value as String,
  };
}

/// A published bundle document as the server writes it, and its sha256.
(List<int>, String) bundle(
  String lang,
  int version,
  Map<String, String> strings, {
  int schema = 1,
  int minAppBuild = 1,
  String? docLang,
}) {
  final bytes = utf8.encode(
    jsonEncode({
      'schema': schema,
      'min_app_build': minAppBuild,
      'lang': docLang ?? lang,
      'version': version,
      'dir': lang == 'ar' ? 'rtl' : 'ltr',
      'strings': strings,
    }),
  );
  return (bytes, BundleStore.sha256Of(bytes));
}

Future<Directory> tempDir() => Directory.systemTemp.createTemp('fleet_l10n');

/// The manifest and bundles a server publishes; [requests] counts what the app asked.
class Published {
  final bundles = <String, Map<int, (List<int>, String)>>{};
  final requests = <String>[];
  var extra = <Map<String, Object?>>[];
  String etag = 'W/"1"';

  void publish(String lang, int version, Map<String, String> strings) {
    (bundles[lang] ??= {})[version] = bundle(lang, version, strings);
    etag = 'W/"${DateTime.now().microsecondsSinceEpoch}"';
  }

  Map<String, Object?> manifest() => {
    'schema': 1,
    'min_app_build': 1,
    'languages': [
      for (final code in languages)
        {
          'code': code,
          'name_native': code,
          'name_en': code,
          'dir': code == 'ar' ? 'rtl' : 'ltr',
          'version': bundles[code]?.keys.fold<int>(0, (a, b) => a > b ? a : b) ?? 0,
          'sha256': bundles[code] == null
              ? null
              : bundles[code]![bundles[code]!.keys.reduce((a, b) => a > b ? a : b)]!.$2,
        },
      ...extra,
    ],
  };

  http.Client client() => MockClient((req) async {
    requests.add(req.url.path);
    if (req.url.path == '/api/v1/driver/translations/manifest') {
      if (req.headers['If-None-Match'] == etag) return http.Response('', 304, headers: {'etag': etag});
      return http.Response(jsonEncode(manifest()), 200, headers: {'etag': etag, 'content-type': 'application/json'});
    }
    final m = RegExp(r'^/api/v1/driver/translations/bundle/(\w+)/(\d+)$').firstMatch(req.url.path);
    if (m != null) {
      final b = bundles[m[1]]?[int.parse(m[2]!)];
      if (b != null) return http.Response.bytes(b.$1, 200);
    }
    return http.Response(jsonEncode({'code': 'not_found'}), 404);
  });
}

Future<(AppDb, Api)> offlineApi(http.Client client) async {
  final db = await testDb();
  return (db, Api(baseUrl: 'http://fleet.test', tokens: TokenStore(db), client: client));
}

AppState appState(AppDb db, Api api, Directory dir, {bool withDir = true}) => AppState(
  db: db,
  api: api,
  pollEvery: null,
  stringsDir: () async => withDir ? dir : null,
  platform: PhoneHooks(
    permissionsOk: () async => true,
    startTracking: () async {},
    stopTracking: () async {},
    deviceMeta: () async => {'platform': 'android', 'model': 'Test phone', 'app_version': '0.1.0'},
  ),
);

Future<void> launch(WidgetTester tester, AppState state, {String deviceLang = 'ar'}) async {
  tester.view.physicalSize = const Size(1080, 2280);
  tester.view.devicePixelRatio = 2.75;
  await tester.pumpWidget(DriverApp(state: state));
  await tester.runAsync(() => state.boot(deviceLang: deviceLang));
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

void main() {
  group('built-in strings', () {
    test('the six arb files have the same keys and valid messages', () {
      final en = arb('en');
      expect(en.length, englishMessages.length);
      for (final lang in languages) {
        final strings = arb(lang);
        expect(strings.keys.toSet(), en.keys.toSet(), reason: lang);
        for (final e in strings.entries) {
          expect(IcuMessage.check(e.value, en[e.key]), isNull, reason: '$lang ${e.key}');
        }
      }
      expect(AppLocalizations.supportedLocales.map((l) => l.languageCode).toSet(), languages.toSet());
    });

    test('ICU messages: placeholders, plurals and select, and what is refused', () {
      expect(IcuMessage.check('Bonjour, {name}', 'Hello, {name}'), isNull);
      expect(IcuMessage.check('Bonjour, {nom}', 'Hello, {name}'), 'missing:{name}');
      expect(IcuMessage.check('Bonjour {name', 'Hello {name}'), startsWith('invalid:'));
      expect(IcuMessage.check('{n, plural, one{x}}', '{n}'), startsWith('invalid:missing_other'));
      final m = IcuMessage.parse(
        '{n, plural, =0{aucune} one{# commande} other{# commandes}} · {g, select, a{A} other{O}}',
      );
      expect(m.format({'n': 0, 'g': 'a'}, 'fr'), 'aucune · A');
      expect(m.format({'n': 1, 'g': 'z'}, 'fr'), '1 commande · O');
      expect(m.format({'n': 5, 'g': 'z'}, 'fr'), '5 commandes · O');
      expect(IcuMessage.parse('{n, plural, one{# ऑर्डर} other{# ऑर्डर}}').format({'n': '3'}, 'hi'), '3 ऑर्डर');
    });

    test('Material and Cupertino strings for every language, English where Flutter has none', () async {
      for (final lang in [...languages, 'ur', 'xx']) {
        final material = await const FallbackDelegate(GlobalMaterialLocalizations.delegate).load(Locale(lang));
        expect(material.okButtonLabel, isNotEmpty, reason: lang);
        final cupertino = await const FallbackDelegate(GlobalCupertinoLocalizations.delegate).load(Locale(lang));
        expect(cupertino.copyButtonLabel, isNotEmpty, reason: lang);
        expect(appStrings(Locale(lang), RemoteStrings.empty).save, isNotEmpty);
      }
      expect(appStrings(const Locale('xx'), RemoteStrings.empty).save, 'Save'); // not shipped: English
    });
  });

  group('bundles on the phone', () {
    test('a valid bundle is installed; a broken string falls back alone', () async {
      final store = BundleStore(tempDir, appBuild: 1);
      final (bytes, sha) = bundle('fr', 1, {'save': 'Garder', 'greeting': 'Bonjour {nom', 'unknownKey': 'x'});
      expect(await store.install('fr', bytes, version: 1, sha256: sha), isTrue);
      final b = (await store.read('fr'))!;
      expect(b.version, 1);
      expect(b.strings, {'save': 'Garder'});
      expect(b.rejected, containsAll(['greeting', 'unknownKey']));
      final l = appStrings(const Locale('fr'), RemoteStrings('fr', 1, b.strings));
      expect(l.save, 'Garder');
      expect(l.greeting('Ali'), 'Bonjour, Ali'); // the built-in French, not the broken text
      expect(l.cancel, 'Annuler');
    });

    test('corrupt, incompatible or mislabeled downloads are refused and the kept bundle stays', () async {
      final store = BundleStore(tempDir, appBuild: 1);
      final (ok, okSha) = bundle('sw', 1, {'save': 'Weka'});
      await store.install('sw', ok, version: 1, sha256: okSha);
      final (v2, v2Sha) = bundle('sw', 2, {'save': 'Hifadhi sasa'});
      final cut = v2.sublist(0, v2.length ~/ 2); // an interrupted download
      expect(await store.install('sw', cut, version: 2, sha256: v2Sha), isFalse);
      expect(await store.install('sw', v2, version: 2, sha256: okSha), isFalse); // wrong checksum
      final (newer, newerSha) = bundle('sw', 2, {'save': 'x'}, minAppBuild: 99); // needs a newer app
      expect(await store.install('sw', newer, version: 2, sha256: newerSha), isFalse);
      final (shape, shapeSha) = bundle('sw', 2, {'save': 'x'}, schema: 2); // a newer document shape
      expect(await store.install('sw', shape, version: 2, sha256: shapeSha), isFalse);
      final (other, otherSha) = bundle('sw', 2, {'save': 'x'}, docLang: 'hi');
      expect(await store.install('sw', other, version: 2, sha256: otherSha), isFalse);
      expect(
        await store.install(
          'sw',
          utf8.encode('{not json'),
          version: 2,
          sha256: BundleStore.sha256Of(utf8.encode('{not json')),
        ),
        isFalse,
      );
      expect((await store.read('sw'))!.strings['save'], 'Weka');
    });

    test('two updates arriving in reverse order: the older never replaces the newer', () async {
      final store = BundleStore(tempDir, appBuild: 1);
      final (v3, s3) = bundle('hi', 3, {'save': 'तीन'});
      final (v2, s2) = bundle('hi', 2, {'save': 'दो'});
      final results = await Future.wait([
        store.install('hi', v3, version: 3, sha256: s3),
        store.install('hi', v2, version: 2, sha256: s2),
      ]);
      expect(results, [isTrue, isFalse]);
      expect((await store.read('hi'))!.version, 3);
    });

    test('a damaged file gives way to the previous bundle; a stray temp file is ignored', () async {
      final dir = await tempDir();
      final store = BundleStore(() async => dir, appBuild: 1);
      final (v1, s1) = bundle('fil', 1, {'save': 'Isa'});
      final (v2, s2) = bundle('fil', 2, {'save': 'Dalawa'});
      await store.install('fil', v1, version: 1, sha256: s1);
      await store.install('fil', v2, version: 2, sha256: s2);
      File('${dir.path}/l10n/fil.3.tmp').writeAsStringSync('{"half');
      expect((await store.read('fil'))!.version, 2);
      File('${dir.path}/l10n/fil.json').writeAsStringSync('{broken');
      expect((await store.read('fil'))!.strings['save'], 'Isa');
    });

    test('no storage at all: the built-in strings', () async {
      final store = BundleStore(() async => null, appBuild: 1);
      expect(await store.read('fr'), isNull);
    });
  });

  group('background updates', () {
    test('only a newer bundle is downloaded; it becomes active at a safe point; checks are throttled', () async {
      final server = Published()..publish('fr', 1, {'save': 'Sauver'});
      final (db, api) = await offlineApi(server.client());
      final t = Translations(db, BundleStore(tempDir, appBuild: 1));
      await t.use('fr');
      expect(t.active.version, 0);
      await t.check(api, 'fr');
      expect(server.requests, ['/api/v1/driver/translations/manifest', '/api/v1/driver/translations/bundle/fr/1']);
      expect(t.active.version, 0, reason: 'not in the middle of a screen');
      expect(t.hasPending, isTrue);
      expect(await t.activatePending(), isTrue);
      expect(t.active.text('save'), 'Sauver');
      await t.check(api, 'fr'); // within 15 minutes: nothing asked
      expect(server.requests, hasLength(2));
      await t.check(api, 'fr', force: true); // unchanged: 304, nothing downloaded
      expect(server.requests.last, '/api/v1/driver/translations/manifest');
      expect(server.requests, hasLength(3));
      server.publish('fr', 2, {'save': 'Sauvegarde'});
      await t.check(api, 'fr', force: true);
      expect(server.requests.last, '/api/v1/driver/translations/bundle/fr/2');
      await t.use('fr'); // the next launch
      expect(t.active.version, 2);
      expect(t.languages.map((l) => l.code), languages);
    });

    test('offline, a slow network or a server error never breaks anything nor removes the kept bundle', () async {
      final dir = await tempDir();
      final store = BundleStore(() async => dir, appBuild: 1);
      final (b, sha) = bundle('fr', 1, {'save': 'Sauver'});
      await store.install('fr', b, version: 1, sha256: sha);
      for (final client in [
        MockClient((_) async => throw const SocketException('airplane mode')),
        MockClient((_) async => throw TimeoutException('slow')),
        MockClient((_) async => http.Response('oops', 500)),
        MockClient((_) async => http.Response('{"languages": "nonsense"}', 200)),
      ]) {
        final (db, api) = await offlineApi(client);
        final t = Translations(db, store);
        await t.use('fr');
        await t.check(api, 'fr', force: true);
        expect(t.active.text('save'), 'Sauver');
      }
    });
  });

  group('the app', () {
    testWidgets('first launch in airplane mode, nothing kept: the language asked first, in the phone\'s language', (
      tester,
    ) async {
      final (db, api) = (await tester.runAsync(
        () => offlineApi(MockClient((_) async => throw const SocketException('airplane mode'))),
      ))!;
      final dir = (await tester.runAsync(tempDir))!;
      final state = appState(db, api, dir);
      await launch(tester, state, deviceLang: 'fr');
      expect(find.textContaining("Choisissez la langue de l'application"), findsOneWidget); // asked before anything
      expect(
        find.descendant(of: find.byKey(const Key('first-lang-fr')), matching: find.byIcon(Icons.check_circle_rounded)),
        findsOneWidget,
      ); // the phone's language, ticked
      await tester.tap(find.byKey(const Key('first-lang-fr')));
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
      await tester.pumpAndSettle();
      expect(find.text('Envoyer le code'), findsOneWidget);
      expect(await tester.runAsync(() => db.get('lang')), 'fr'); // kept: the next launch goes to the sign-in
      expect(tester.takeException(), isNull);
    });

    testWidgets('the first screen shows while no request has answered', (tester) async {
      var asked = 0;
      final never = MockClient((_) {
        asked++;
        return Completer<http.Response>().future; // a network that never answers
      });
      final (db, api) = (await tester.runAsync(() => offlineApi(never)))!;
      final dir = (await tester.runAsync(tempDir))!;
      await launch(tester, appState(db, api, dir), deviceLang: 'sw');
      expect(find.textContaining('Chagua lugha ya programu'), findsOneWidget); // the language screen, offline
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 200)));
      expect(asked, greaterThan(0), reason: 'the update check started, and nobody waited for it');
    });

    testWidgets('a kept bundle is used at start; a broken string in it falls back alone', (tester) async {
      final (db, api) = (await tester.runAsync(
        () => offlineApi(MockClient((_) async => throw const SocketException('offline'))),
      ))!;
      final dir = (await tester.runAsync(tempDir))!;
      final (b, sha) = bundle('fr', 4, {'sendCode': 'Recevoir le code', 'signInHint': 'Votre numéro {oops'});
      await tester.runAsync(() => BundleStore(() async => dir, appBuild: 1).install('fr', b, version: 4, sha256: sha));
      await tester.runAsync(() => db.put('lang', 'fr'));
      await launch(tester, appState(db, api, dir));
      expect(find.text('Recevoir le code'), findsOneWidget);
      expect(find.textContaining('Saisissez votre numéro'), findsOneWidget); // the built-in French
      expect(find.textContaining('{oops'), findsNothing);
    });

    testWidgets('the picker lists the server\'s languages; a change applies at once, offline', (tester) async {
      final server = Published()
        ..extra = [
          {'code': 'ur', 'name_native': 'اردو', 'name_en': 'Urdu', 'dir': 'rtl', 'version': 0, 'sha256': null},
        ];
      final (db, api) = (await tester.runAsync(() => offlineApi(server.client())))!;
      final dir = (await tester.runAsync(tempDir))!;
      final state = appState(db, api, dir);
      await tester.runAsync(() => db.put('lang', 'en')); // chosen at the first launch
      await launch(tester, state, deviceLang: 'en');
      await tester.runAsync(() => state.translations.check(api, 'en', force: true));
      await tester.pump();
      await tester.tap(find.byKey(const Key('language-picker')));
      await tester.pumpAndSettle();
      for (final code in [...languages, 'ur']) {
        expect(find.byKey(Key('lang-$code')), findsOneWidget, reason: code);
      }
      expect(find.text('اردو'), findsOneWidget);
      await tester.tap(find.byKey(const Key('lang-hi')));
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 200)));
      await tester.pumpAndSettle();
      expect(state.lang, 'hi');
      expect(find.text('कोड भेजें'), findsOneWidget);
      expect(Directionality.of(tester.element(find.text('कोड भेजें'))), TextDirection.ltr);
    });

    testWidgets('Swahili and Filipino run with no crash; Devanagari renders; right to left for Arabic only', (
      tester,
    ) async {
      final cases = {
        'sw': 'Tuma msimbo',
        'fil': 'Ipadala ang code',
        'hi': 'कोड भेजें',
        'ar': 'إرسال الرمز',
        'fr': 'Envoyer le code',
      };
      for (final e in cases.entries) {
        final (db, api) = (await tester.runAsync(
          () => offlineApi(MockClient((_) async => throw const SocketException('offline'))),
        ))!;
        final dir = (await tester.runAsync(tempDir))!;
        await tester.runAsync(() => db.put('lang', e.key));
        await launch(tester, appState(db, api, dir));
        final f = find.text(e.value);
        expect(f, findsOneWidget, reason: e.key);
        expect(tester.takeException(), isNull, reason: e.key);
        expect(tester.getSize(f).width, greaterThan(0), reason: e.key);
        expect(Directionality.of(tester.element(f)), e.key == 'ar' ? TextDirection.rtl : TextDirection.ltr);
        // the date picker's own strings exist in every language
        final context = tester.element(f);
        expect(MaterialLocalizations.of(context).okButtonLabel, isNotEmpty);
        await tester.pumpWidget(const SizedBox());
      }
    });
  });
}
