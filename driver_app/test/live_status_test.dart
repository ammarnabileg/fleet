import 'dart:convert';

import 'package:fleet_driver/core/outbox.dart';
import 'package:fleet_driver/l10n/app_localizations.dart';
import 'package:fleet_driver/status/engine.dart';
import 'package:fleet_driver/tracking/alerts.dart';
import 'package:fleet_driver/tracking/notice.dart';
import 'package:fleet_driver/tracking/system_notices.dart';
import 'package:fleet_driver/tracking/tracker.dart';
import 'package:fleet_driver/ui/screens/notifications.dart';
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
      expect(view.top!.subtitle, '', reason: 'its only variable without a value: left out, as on the server');
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

    test('the settlement card shows no undefined date: a part whose variables are all empty is left out', () {
      final view = compose(
        status(
          body(
            alerts: [
              alert('custody_settlement', 60, values: {'amount': '125.500'}),
            ],
          ),
        ),
        null,
        now: now,
        lang: 'ar',
      );
      expect(view.top!.title, 'معك 125.500 د.ك للتسوية');
      expect(view.top!.subtitle, 'سلّم المبلغ للمكتب');
      expect('${view.top!.title}${view.top!.subtitle}', isNot(contains('—')));
      expect(StatusEngine.fill('التسوية قبل {due}', {'due': null}), '');
      expect(StatusEngine.fill('معك {amount}\nالتسوية قبل {due}', {'amount': '5'}), 'معك 5');
      expect(StatusEngine.fill('{center} · {stage}', {'stage': 'Quote'}), 'Quote');
      expect(StatusEngine.fill('{amount} قبل {due}', {'amount': '5'}), '5 قبل —');
    });

    test('off duty before the day is not off duty after ending it', () {
      Map<String, dynamic> off({bool? ended, int? orders}) => {
        ...body(shift: 'off_duty'),
        'shift': {'state': 'off_duty', 'day_ended': ?ended, 'orders_today': ?orders},
      };
      final before = compose(status(off()), null, now: now, lang: 'ar').shift;
      expect([before.code, before.subtitle], ['shift_off', 'لم يبدأ يوم العمل']);
      final after = compose(status(off(ended: true, orders: 18)), null, now: now, lang: 'ar').shift;
      expect(
        [after.code, after.kind, after.title, after.subtitle],
        ['shift_ended', 'shift_off', 'خارج الدوام', 'أنهيت يومك · 18 طلب'],
      );
      expect(compose(status(off(ended: true)), null, now: now, lang: 'en').shift.subtitle, 'Day ended');
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

    final at = DateTime(2026, 10, 23, 10, 42); // local times: the notification shows the phone's clock
    String t(String hhmm) => '\u2066$hhmm\u2069';

    NoticeContent content(
      AppLocalizations l, {
      bool working = true,
      String tracking = 'active',
      DateTime? fix,
      DateTime? sent,
      NoticeInfo? info,
    }) => workNoticeContent(
      l,
      lang: l.localeName,
      company: company,
      working: working,
      tracking: tracking,
      lastFixAt: fix,
      lastSentAt: sent,
      info: info,
    );

    test('1. at work, location sent: the last send, the shift start; green; the company in the header', () {
      final c = content(
        ar,
        fix: at,
        sent: at,
        info: NoticeInfo(shiftStartedAt: DateTime(2026, 10, 23, 7, 15)),
      );
      expect(c.state, 'working_active');
      expect(c.title, 'في العمل · الموقع يُرسل');
      expect(c.body, 'آخر موقع أُرسل ${t('10:42')}');
      expect(c.big, 'آخر موقع أُرسل ${t('10:42')}\nالوردية من ${t('07:15')}');
      expect(c.header, 'شركة المثال');
      expect(c.color, green);
      expect(content(en, fix: at, sent: at).header, 'Example Co');
      expect(
        content(en, fix: at, sent: at).big,
        content(en, fix: at, sent: at).body,
        reason: 'no start known',
      );
    });

    test('2. off duty, location still sent (the car with him): before the day vs after ending it; blue', () {
      final before = content(ar, working: false, fix: at, sent: at);
      expect(before.state, 'off_active');
      expect(before.title, 'خارج الدوام · الموقع يُرسل');
      expect(before.big, endsWith('لم يبدأ يوم العمل'));
      expect(before.color, blue);
      final ended = content(
        ar,
        working: false,
        fix: at,
        sent: at,
        info: const NoticeInfo(dayEnded: true, ordersToday: 18),
      );
      expect(ended.big, endsWith('أنهيت يومك · ${t('18')} طلب'));
      final noCount = content(ar, working: false, fix: at, sent: at, info: const NoticeInfo(dayEnded: true));
      expect(noCount.big, endsWith('\nأنهيت يومك'));
    });

    test('3. location not coming through: since when, the last confirmed send; amber', () {
      final c = content(ar, tracking: 'stale', fix: at, sent: at.subtract(const Duration(minutes: 1)));
      expect(c.state, 'stale');
      expect(c.title, 'في العمل · الموقع لا يصل');
      expect(c.body, 'لم يصل موقع منذ ${t('10:42')}. افتح التطبيق وتحقق من إعدادات الموقع');
      expect(c.big, endsWith('آخر إرسال مؤكد ${t('10:41')}'));
      expect(c.color, amber);
      expect(content(en, working: false, tracking: 'stale', fix: at).title, 'Off duty · ${en.trackingStale}');
    });

    test('4. no location sent yet after the grace: waiting for the first; amber', () {
      final c = content(ar, tracking: 'stale');
      expect(c.state, 'waiting_first');
      expect(c.title, 'في العمل · بانتظار أول موقع');
      expect(c.body, ar.noticeBigStaleNever);
      expect(c.big, endsWith('لم يتم تأكيد أي إرسال'));
      expect(c.color, amber);
      // within the grace: not a problem yet
      expect(content(ar).body, ar.noticeLocating);
      expect(content(ar).color, green);
    });

    test('5. off duty, no car: tracking stopped; grey', () {
      final c = content(ar, working: false, tracking: 'off');
      expect(c.state, 'off');
      expect(c.title, 'خارج الدوام · التتبع متوقف');
      expect(c.body, 'لا يُتتبَّع موقعك الآن');
      expect(c.big, endsWith('لم يبدأ يوم العمل'));
      expect(c.color, grey);
    });

    test('6. the car at a center: tracking stopped, the center and stage when known; purple', () {
      final c = content(
        ar,
        working: false,
        tracking: 'off',
        info: const NoticeInfo(inMaintenance: true, center: 'المركز', stage: 'الفحص'),
      );
      expect(c.state, 'maintenance');
      expect(c.title, 'السيارة في الصيانة · التتبع متوقف');
      expect(c.big, '${ar.noticeBigOff}\nالمركز · الفحص');
      expect(c.color, purple);
      final unknown = content(ar, working: false, tracking: 'off', info: const NoticeInfo(inMaintenance: true));
      expect(unknown.big, ar.noticeBigOff, reason: 'no "— · —"');
      final some = content(
        ar,
        working: false,
        tracking: 'off',
        info: const NoticeInfo(inMaintenance: true, stage: 'x'),
      );
      expect(some.big, endsWith('\nx'));
    });

    test('the live status gives the notification its shift and car', () {
      final s = status({
        ...body(shift: 'off_duty', vehicle: 'maintenance', tracking: 'off'),
        'shift': {'state': 'off_duty', 'day_ended': true, 'orders_today': 18},
      });
      final info = noticeInfo(s);
      expect(
        [info.dayEnded, info.ordersToday, info.inMaintenance, info.center, info.stage],
        [true, 18, true, 'Center', 'Quote'],
      );
      final old = noticeInfo(status(body(shift: 'off_duty')));
      expect([old.dayEnded, old.ordersToday], [false, null], reason: 'an older server: as before the day');
    });

    test('heads-up: the design\'s title, text, accent and working buttons', () {
      final contact = headsUpContent(
        ar,
        StatusAlert.fromJson(
          alert(
            'contact_request',
            90,
            id: 'contact:1',
            data: {'request_id': 'r1', 'phone': '+96550000000', 'message': 'كلمني'},
          ),
        )!,
      );
      expect(contact.title, 'طلب تواصل');
      expect(contact.body, 'server title contact_request');
      expect(contact.big, 'server title contact_request\n«كلمني»');
      expect(contact.color, blue);
      expect(
        [for (final a in contact.actions) (a.id, a.label, a.opensApp)],
        [('call', ar.statusCall, true), ('ack', ar.statusDone, false)],
      );
      expect(noticeTap('ack', contact.payload).requestId, 'r1');
      expect(noticeTap('call', contact.payload).phone, '+96550000000');
      expect(noticeTap(null, contact.payload).kind, 'open');
      final noPhone = headsUpContent(
        ar,
        StatusAlert.fromJson(alert('contact_request', 90, data: {'request_id': 'r1'}))!,
      );
      expect([for (final a in noPhone.actions) a.id], ['ack']);
      final location = headsUpContent(
        en,
        StatusAlert.fromJson(alert('location_problem', 80, values: {'last_update': '10:42'}))!,
      );
      expect(location.title, 'server title location_problem');
      expect(location.body, en.headsUpLocationBody(t('10:42')));
      expect(location.color, amber);
      expect([for (final a in location.actions) (a.id, a.opensApp)], [('location_settings', true)]);
      expect(noticeTap('location_settings', location.payload).kind, 'location_settings');
      expect(
        headsUpContent(en, StatusAlert.fromJson(alert('location_problem', 80))!).body,
        en.headsUpLocationBodyNever,
      );
      expect(noticeTap('ack', 'not json').kind, 'open', reason: 'a damaged payload only opens the app');
    });

    test('a tap does what its button says; «Done» goes through the outbox', () async {
      final done = <String>[];
      Future<void> run(NoticeTap tap) => runNoticeTap(
        tap,
        dial: (p) async {
          done.add('dial $p');
          return true;
        },
        openLocationSettings: () async => done.add('settings'),
        acknowledge: (r) async => done.add('ack $r'),
      );
      await run(const NoticeTap('call', phone: '1'));
      await run(const NoticeTap('location_settings'));
      await run(const NoticeTap('ack', requestId: 'r1'));
      await run(const NoticeTap('open'));
      expect(done, ['dial 1', 'settings', 'ack r1']);
      final db = await testDb();
      await queueContactAck(Outbox(db), 'r1');
      final rows = await db.raw.query('outbox');
      expect(rows.single['kind'], 'contact_ack');
      expect(jsonDecode(rows.single['payload'] as String)['request_id'], 'r1');
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

    test('the watcher posts each alert once, updates it in place, cancels it when over; refused: none', () async {
      final (db, _, api, server) = await session();
      var alerts = [alert('contact_request', 90, id: 'contact:1'), alert('location_problem', 80)];
      server.on('GET', '/api/v1/driver/live-status', (_) => (200, body(alerts: alerts)));
      final poster = FakePoster()..allowed_ = false;
      final w = AlertWatcher(api: api, db: db, poster: poster, strings: () async => ar, clock: () => now);
      await w.check();
      expect(poster.posted, isEmpty, reason: 'notifications refused: in the inbox only');
      poster.allowed_ = true;
      await w.check();
      await w.check();
      expect([for (final n in poster.posted) n.key], ['contact:1', 'location_problem']);
      expect([for (final n in poster.posted) n.channel], [alertsChannel, alertsChannel]);
      alerts = [alert('location_problem', 80), alert('custody_settlement', 60)];
      await w.check();
      expect(poster.cancelled, [headsUpId('contact:1')], reason: 'resolved: gone from the shade');
      expect(poster.posted.last.key, 'custody_settlement');
      expect(poster.posted.last.channel, messagesChannel, reason: 'quietly: not over the screen');
      expect(noticeTap(null, poster.posted.last.payload).target, 'inbox');
      // its text changes: the same notification, updated in place
      alerts = [
        alert('location_problem', 80, values: {'last_update': '08:55'}),
        alert('custody_settlement', 60),
      ];
      await w.check();
      expect(poster.posted.last.key, 'location_problem');
      expect(poster.posted.last.id, headsUpId('location_problem'));
      final count = poster.posted.length;
      await w.check();
      expect(poster.posted, hasLength(count), reason: 'nothing changed: nothing posted');
      alerts = [];
      await w.check();
      expect(poster.cancelled, containsAll([headsUpId('location_problem'), headsUpId('custody_settlement')]));
      expect(server.calls('/api/v1/driver/live-status').last.url.queryParameters, isEmpty);
    });

    test('every current alert kind is a system notification; the car\'s state too, once', () {
      final view = compose(
        status(
          body(
            vehicle: 'breakdown',
            alerts: [
              alert('vehicle_maintenance', 70),
              alert('document_missing', 40, values: {'document': 'رخصة'}),
              alert('custody_settlement', 60),
            ],
          ),
        ),
        null,
        now: now,
        lang: 'ar',
      );
      final cards = currentCards(view);
      expect(
        [for (final c in cards) c.code],
        ['vehicle_maintenance', 'custody_settlement', 'document_missing', 'vehicle_breakdown'],
      );
      final notices = [for (final c in cards) cardNotice(ar, c)];
      expect({for (final n in notices) n.channel}, {messagesChannel});
      expect({for (final n in notices) n.id}, hasLength(4));
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
        checkAlerts: () => AlertWatcher(
          api: api,
          db: db,
          poster: FakePoster(onPost: (n) => posted.add(n.key)),
          strings: () async => ar,
        ).check(),
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
              body: ListView(
                children: [
                  LiveStatusPanel(view: view),
                  // the inbox's «current» cards, drawn by the same widget there
                  for (final c in currentCards(view)) StatusCardView(card: c, onAction: (a, _) => on?.call(a)),
                ],
              ),
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

    testWidgets('home\'s panel: the shift card only, never an alert nor the car\'s state', (tester) async {
      final view = compose(
        status(body(vehicle: 'maintenance', alerts: [alert('custody_settlement', 60), alert('contact_request', 90)])),
        null,
        now: now,
        lang: 'ar',
      );
      await tester.pumpWidget(
        MaterialApp(
          locale: const Locale('ar'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: LiveStatusPanel(view: view)),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('status-shift')), findsOneWidget);
      expect(find.byType(StatusCardView), findsNothing);
      expect(find.byKey(const Key('status-card-custody_settlement')), findsNothing);
      expect(find.byKey(const Key('status-card-vehicle_maintenance')), findsNothing);
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

  group('inbox', () {
    test('every message kind of the catalog falls in one of the design\'s groups', () {
      const groups = {
        'cash': [
          'receipt_issued',
          'receipt_reversed',
          'report_corrected',
          'report_returned',
          'report_change_approved',
          'report_change_rejected',
          'report_rejected',
          'report_missing',
          'fuel_approved',
          'fuel_rejected',
        ],
        'car': [
          'vehicle_change_approved',
          'vehicle_change_done',
          'vehicle_change_rejected',
          'vehicle_change_closed',
          'vehicle_handed_over',
          'vehicle_returned',
          'vehicle_taken',
          'vehicle_swapped',
          'vehicle_claim_approved',
          'vehicle_claim_rejected',
          'vehicle_claim_superseded',
        ],
        'maintenance': [
          'maintenance_approved',
          'maintenance_rejected',
          'maintenance_ready',
          'accident_no_liability',
          'accident_charged',
          'fine_charged',
          'deduction_added',
        ],
        'documents': [
          'document_renewal_approved',
          'document_renewal_rejected',
          'document_expiring',
          'document_expired',
          'payslip_ready',
          'scheme_request_approved',
          'scheme_request_rejected',
          'objection_updated',
        ],
        'alerts': ['something_new'],
      };
      for (final e in groups.entries) {
        for (final kind in e.value) {
          expect(noticeCategory(kind), e.key, reason: kind);
        }
      }
      final accents = {for (final g in groups.keys) categoryStyle(g).$1};
      expect(accents, hasLength(5), reason: 'each group its own accent');
      final ar = lookupAppLocalizations(const Locale('ar'));
      expect(
        [for (final g in groups.keys) categoryLabel(ar, g)],
        ['الكاش والتقارير', 'السيارة والعهدة', 'الصيانة والخصومات', 'المستندات والراتب', 'التنبيهات'],
      );
      expect(noticeIcon('vehicle_swapped'), categoryStyle('car').$2, reason: 'no icon of its own: the group\'s');
    });

    testWidgets('the card enters with motion only when the phone allows it', (tester) async {
      Future<void> pump(bool still) => tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: MediaQueryData(disableAnimations: still),
            child: const Scaffold(
              body: AccentCard(accent: Color(0xFF1D4ED8), icon: Icons.info_outline, title: 't', subtitle: 's'),
            ),
          ),
        ),
      );
      await pump(true);
      expect(find.byType(TweenAnimationBuilder<double>), findsNothing);
      await pump(false);
      expect(find.byType(TweenAnimationBuilder<double>), findsOneWidget);
      await tester.pumpAndSettle();
      expect(find.text('s'), findsOneWidget);
    });
  });
}

final ar = lookupAppLocalizations(const Locale('ar'));
