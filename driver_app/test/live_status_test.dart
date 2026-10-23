import 'dart:convert';

import 'package:fleet_driver/l10n/app_localizations.dart';
import 'package:fleet_driver/status/engine.dart';
import 'package:fleet_driver/tracking/alerts.dart';
import 'package:fleet_driver/tracking/notice.dart';
import 'package:fleet_driver/tracking/tracker.dart';
import 'package:fleet_driver/ui/widgets/live_status.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'support.dart';

final now = DateTime.utc(2026, 10, 23, 9);

Map<String, dynamic> alert(String code, int priority, {String? id, String? expires, Map? data, Map? values}) => {
  'id': id ?? code,
  'code': code,
  'kind':
      {'custody_settlement': 'custody', 'contact_request': 'contact', 'location_problem': 'location'}[code] ??
      'generic',
  'priority': priority,
  'expires_at': expires,
  'values': values ?? {},
  'data': data ?? {},
  'title': 'server title $code',
  'subtitle': 'server subtitle',
};

Map<String, dynamic> body({
  String shift = 'working',
  String tracking = 'active',
  String vehicle = 'available',
  List<Map<String, dynamic>> alerts = const [],
  Object? config,
}) => {
  'config_version': 3,
  'min_app_template_version': 1,
  'generated_at': now.toIso8601String(),
  'shift': {
    'state': shift,
    'started_at': shift == 'working' ? now.subtract(const Duration(hours: 2, minutes: 5)).toIso8601String() : null,
    'sessions_today': 1,
  },
  'vehicle': {'state': vehicle, 'plate_number': '12345', 'stage': 'Quote', 'center': 'Center'},
  'tracking': {'state': tracking, 'last_update': now.subtract(const Duration(minutes: 1)).toIso8601String()},
  'alerts': alerts,
  'config': config,
};

Map<String, dynamic> template(String code, {String kind = 'custody', String icon = 'wallet', List<String>? actions}) =>
    {
      'code': code,
      'kind': kind,
      'icon': icon,
      'color': '#B45309',
      'title': {'ar': 'سلّم {amount}', 'en': 'Hand in {amount}'},
      'subtitle': {'ar': 'قبل {due}', 'en': 'By {due}'},
      'priority': 60,
      'actions': actions ?? ['open_cash'],
    };

LiveStatus status(Map<String, dynamic> b, {DateTime? at}) => LiveStatus.fromJson(b, at ?? now)!;

void main() {
  group('engine', () {
    test('an unknown kind, icon or action: the generic card, the default icon, the action hidden', () {
      final config = StatusConfig.fromJson({
        'version': 3,
        'min_app_template_version': 1,
        'templates': [
          template('custody_settlement', kind: 'hologram', icon: 'skull', actions: ['open_cash', 'format_phone']),
        ],
      })!;
      final view = compose(
        status(
          body(
            alerts: [
              alert('custody_settlement', 60, values: {'amount': '12.500'}),
            ],
          ),
        ),
        config,
        now: now,
        lang: 'ar',
      );
      expect(view.top!.kind, 'generic');
      expect(view.top!.icon, 'info');
      expect(view.top!.actions, ['open_cash']);
      expect(view.top!.title, 'سلّم 12.500');
      expect(view.top!.subtitle, 'قبل —', reason: 'a variable without a value shows a dash, as on the server');
    });

    test('a state this app does not know shows the server text on the generic card', () {
      final view = compose(
        status(body(alerts: [alert('fuel_low', 70)])),
        null,
        now: now,
        lang: 'en',
      );
      expect(view.top!.kind, 'generic');
      expect(view.top!.title, 'server title fuel_low');
      expect(view.top!.actions, isEmpty);
    });

    test('a config made for a newer app is ignored: the built-in templates apply', () {
      expect(StatusConfig.fromJson({'version': 9, 'min_app_template_version': 2, 'templates': []}), isNull);
      final view = compose(
        status(body(alerts: [alert('contact_request', 90)])),
        null,
        now: now,
        lang: 'en',
      );
      expect(view.top!.kind, 'contact');
      expect(view.top!.actions, ['call_supervisor', 'acknowledge']);
    });

    test('the most important alert on top, then back to the base state; custody never hides tracking', () {
      final two = status(
        body(tracking: 'stale', alerts: [alert('custody_settlement', 60), alert('contact_request', 90)]),
      );
      var view = compose(two, null, now: now, lang: 'ar');
      expect(view.top!.code, 'contact_request');
      expect(view.more, 1);
      view = compose(
        status(body(tracking: 'stale', alerts: [alert('custody_settlement', 60)])),
        null,
        now: now,
        lang: 'ar',
      );
      expect(view.top!.code, 'custody_settlement');
      expect(view.tracking, 'stale', reason: 'the shift card still says the location is not coming through');
      view = compose(status(body()), null, now: now, lang: 'ar');
      expect(view.top, isNull);
      expect(view.shift.kind, 'shift_working');
      expect(view.shift.subtitle, 'منذ 2:05');
    });

    test('an expired alert is hidden', () {
      final view = compose(
        status(
          body(
            alerts: [
              alert('contact_request', 90, expires: now.subtract(const Duration(minutes: 1)).toIso8601String()),
              alert('custody_settlement', 60),
            ],
          ),
        ),
        null,
        now: now,
        lang: 'ar',
      );
      expect(view.top!.code, 'custody_settlement');
      expect(view.more, 0);
    });

    test('the car at a center or broken down has its own card', () {
      expect(
        compose(
          status(body(vehicle: 'maintenance')),
          null,
          now: now,
          lang: 'en',
        ).vehicle!.subtitle,
        'Center · Quote',
      );
      expect(
        compose(
          status(body(vehicle: 'breakdown')),
          null,
          now: now,
          lang: 'en',
        ).vehicle!.icon,
        'breakdown',
      );
      expect(compose(status(body()), null, now: now, lang: 'en').vehicle, isNull);
    });

    test('offline or an old answer: tracking is never shown as live', () {
      final s = status(body(), at: now.subtract(const Duration(minutes: 10)));
      final view = compose(s, null, now: now, lang: 'ar');
      expect(view.offline, isTrue);
      expect(view.tracking, 'unknown');
      expect(compose(status(body()), null, now: now, lang: 'ar', online: false).tracking, 'unknown');
    });
  });

  group('cache', () {
    test('the last valid config stays with its version; an unreadable one does not replace it', () async {
      final db = await testDb();
      final store = LiveStatusStore(db.get, db.put);
      await store.save(
        body(
          config: {
            'version': 3,
            'min_app_template_version': 1,
            'templates': [template('custody_settlement')],
          },
        ),
        now,
      );
      expect(await store.version(), 3);
      await store.save(body(config: {'version': 4, 'min_app_template_version': 7, 'templates': []}), now);
      expect(await store.version(), 3);
      await store.save(body(config: null), now);
      expect((await store.config())!.templates.keys, ['custody_settlement']);
      expect((await store.last())!.shift, 'working');
    });
  });

  group('notification', () {
    final ar = lookupAppLocalizations(const Locale('ar'));
    final en = lookupAppLocalizations(const Locale('en'));
    const company = {'ar': 'شركة المثال', 'en': 'Example Co'};

    test('the text follows the real tracking state', () {
      final active = workNoticeContent(
        en,
        lang: 'en',
        company: company,
        working: true,
        tracking: 'active',
        lastFixAt: now,
      );
      expect(active.title, 'Example Co');
      expect(active.body, '● ${en.driverWorking} · ${en.trackingActive}');
      expect(active.colorized, isTrue);
      final stale = workNoticeContent(en, lang: 'en', company: company, working: true, tracking: 'stale');
      expect(stale.body, contains(en.trackingStale));
      expect(stale.big, contains(en.noticeBigStaleNever));
      expect(stale.colorized, isFalse);
      final off = workNoticeContent(ar, lang: 'ar', company: company, working: false, tracking: 'off');
      expect(off.title, 'شركة المثال');
      expect(off.body, '● ${ar.driverNotWorking} · ${ar.trackingOff}');
      expect(off.big, contains(ar.noticeBigOff));
    });

    test('heads-up: only contact and location alerts, once each; none when notifications are refused', () {
      final alerts = [
        StatusAlert.fromJson(alert('contact_request', 90, id: 'contact:1'))!,
        StatusAlert.fromJson(alert('location_problem', 80))!,
        StatusAlert.fromJson(alert('custody_settlement', 60))!,
      ];
      expect(headsUpToPost(alerts, posted: {}, allowed: false, now: now), isEmpty);
      expect(
        [for (final a in headsUpToPost(alerts, posted: {}, allowed: true, now: now)) a.id],
        ['contact:1', 'location_problem'],
      );
      expect(headsUpToPost(alerts, posted: {'contact:1', 'location_problem'}, allowed: true, now: now), isEmpty);
      expect(headsUpId('contact:1'), headsUpId('contact:1'));
    });

    test('the watcher posts each alert once, again when it comes back; refused: in the app only', () async {
      final (db, _, api, server) = await session();
      var alerts = [alert('contact_request', 90, id: 'contact:1'), alert('location_problem', 80)];
      server.on('GET', '/api/v1/driver/live-status', (_) => (200, body(alerts: alerts)));
      final posted = <String>[];
      var allowed = false;
      final w = AlertWatcher(
        api: api,
        db: db,
        allowed: () async => allowed,
        post: (a) async => posted.add(a.id),
        clock: () => now,
      );
      await w.check();
      expect(posted, isEmpty, reason: 'notifications refused: the card in the app only');
      allowed = true;
      await w.check();
      await w.check();
      expect(posted, ['contact:1', 'location_problem']);
      alerts = [];
      await w.check();
      alerts = [alert('location_problem', 80)];
      await w.check();
      expect(posted, ['contact:1', 'location_problem', 'location_problem']);
      expect(server.calls('/api/v1/driver/live-status').last.url.queryParameters, isEmpty);
    });

    test('an office alert never starts the tracking', () async {
      final (db, _, api, server) = await session();
      server.on(
        'POST',
        '/api/v1/driver/status',
        (_) => (200, {'tracking_required': false, 'interval_moving_s': 30, 'interval_stationary_s': 300}),
      );
      server.on(
        'GET',
        '/api/v1/driver/live-status',
        (_) => (
          200,
          body(
            shift: 'off_duty',
            tracking: 'off',
            alerts: [alert('contact_request', 90, id: 'c')],
          ),
        ),
      );
      final asked = <Duration>[];
      final posted = <String>[];
      final states = <WorkState>[];
      final t = Tracker(
        db: db,
        api: api,
        fixes: (i) {
          asked.add(i);
          return const Stream.empty();
        },
        health: ({required bool trackingRunning, required int queueSize, String? lastUploadAt}) async => {},
        notifyState: states.add,
        checkAlerts: () =>
            AlertWatcher(api: api, db: db, allowed: () async => true, post: (a) async => posted.add(a.id)).check(),
        heartbeatEvery: const Duration(hours: 1),
        syncEvery: const Duration(hours: 1),
      );
      await t.start();
      await Future<void>.delayed(const Duration(milliseconds: 80));
      expect(posted, ['c']);
      expect(asked, isEmpty);
      expect(t.required, isFalse);
      expect(states.last.tracking, 'off');
      await t.stop();
    });
  });

  group('widget', () {
    Future<void> pump(WidgetTester tester, StatusView view, {bool still = false, void Function(String)? on}) {
      return tester.pumpWidget(
        MaterialApp(
          locale: const Locale('ar'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: MediaQuery(
            data: MediaQueryData(disableAnimations: still),
            child: Scaffold(
              body: LiveStatusPanel(view: view, onAction: (a, _) => on?.call(a)),
            ),
          ),
        ),
      );
    }

    testWidgets('offline with the cached config: a clear banner, tracking not shown as live', (tester) async {
      final s = status(body(), at: DateTime.now().subtract(const Duration(minutes: 30)));
      await pump(tester, compose(s, null, now: DateTime.now(), lang: 'ar', online: false));
      expect(find.byKey(const Key('status-offline')), findsOneWidget);
      expect(find.byKey(const Key('status-tracking-active')), findsNothing);
      expect(find.byKey(const Key('status-tracking-unknown')), findsOneWidget);
    });

    testWidgets('contact card: the message, «Call» only with a phone, «Done»', (tester) async {
      final tapped = <String>[];
      final withPhone = status(
        body(
          alerts: [
            alert('contact_request', 90, data: {'request_id': 'r1', 'message': 'Call me', 'phone': '+96550000000'}),
          ],
        ),
      );
      await pump(
        tester,
        compose(withPhone, null, now: now, lang: 'ar'),
        on: tapped.add,
      );
      expect(find.byKey(const Key('status-contact-message')), findsOneWidget);
      await tester.tap(find.byKey(const Key('status-action-call_supervisor')));
      await tester.tap(find.byKey(const Key('status-action-acknowledge')));
      expect(tapped, ['call_supervisor', 'acknowledge']);
      final noPhone = status(
        body(
          alerts: [
            alert('contact_request', 90, data: {'request_id': 'r1', 'message': 'x'}),
          ],
        ),
      );
      await pump(tester, compose(noPhone, null, now: now, lang: 'ar'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('status-action-call_supervisor')), findsNothing);
      expect(find.byKey(const Key('status-action-acknowledge')), findsOneWidget);
    });

    testWidgets('the alert switches smoothly, at once when animations are off', (tester) async {
      final a = compose(
        status(body(alerts: [alert('custody_settlement', 60)])),
        null,
        now: now,
        lang: 'ar',
      );
      final b = compose(status(body()), null, now: now, lang: 'ar');
      final card = find.byKey(const Key('status-card-custody_settlement'));
      await pump(tester, a);
      await pump(tester, b);
      await tester.pump(const Duration(milliseconds: 50));
      expect(card, findsOneWidget, reason: 'fading out');
      await tester.pumpAndSettle();
      expect(card, findsNothing);
      await pump(tester, a, still: true);
      await tester.pump();
      await pump(tester, b, still: true);
      await tester.pump();
      expect(card, findsNothing, reason: 'animations off: replaced at once');
      expect(find.byKey(const Key('status-shift')), findsOneWidget);
    });

    testWidgets('working: the green dot and the duration; off duty: calm, with the day summary', (tester) async {
      await pump(tester, compose(status(body()), null, now: now, lang: 'ar'));
      expect(find.byKey(const Key('status-working-dot')), findsOneWidget);
      expect(find.text('منذ 2:05'), findsOneWidget);
      await pump(
        tester,
        compose(
          status(body(shift: 'off_duty', tracking: 'off')),
          null,
          now: now,
          lang: 'ar',
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('status-working-dot')), findsNothing);
      expect(find.byKey(const Key('status-tracking-off')), findsOneWidget);
    });
  });

  test('json round trip of an answer keeps the alerts', () {
    final s = status(jsonDecode(jsonEncode(body(alerts: [alert('location_problem', 80)]))) as Map<String, dynamic>);
    expect(s.alerts.single.kind, 'location');
  });
}
