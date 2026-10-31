import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'app_test.dart' show idle, loadFonts, pumpApp, reveal, settle, shot, world;

/// The first run of a driver with no company: «which company do you work with?», sent to the office as a request;
/// while it waits the home screen says so (and he may change his choice); a rejection brings the screen back with its
/// reason; once approved, nothing more is asked.
Map<String, dynamic> company(int id, String code, String ar) => {
  'id': id,
  'code': code,
  'name': {'ar': ar, 'en': code},
  'is_core': true,
};

final keeta = company(1, 'keeta', 'كيتا');
final talabat = company(2, 'talabat', 'طلبات');

Map<String, dynamic> view({Map<String, dynamic>? platform, Map<String, dynamic>? request, required bool ask}) => {
  'platform': platform,
  'platforms': [keeta, talabat],
  'request': request,
  'ask': ask,
};

Map<String, dynamic> request(String status, Map<String, dynamic> platform, {String? note}) => {
  'id': 'req-1',
  'status': status,
  'platform': platform,
  'admin_note': note,
  'driver_note': null,
  'version': 1,
};

/// A company's schemes as the server sends them, from the real templates (keeta_fixed_200 and keeta_fixed_165).
Map<String, dynamic> offer(List<dynamic> templates, String code) {
  final t = templates.cast<Map<String, dynamic>>().firstWhere((x) => x['code'] == code);
  return {
    'id': 'id-$code',
    'code': code,
    'name': t['name'],
    'description': t['description'],
    'calculator': 'rules',
    'pay_kind': 'fixed_salary',
    'per_order': null,
    'target_orders': 0,
    'required_valid_days': 0,
    'missing_order_rate': null,
    'reduced_rate': null,
    'company_covers': <String>[],
    'steps': <Object>[],
    'blocks': t['blocks'],
  };
}

void main() {
  setUpAll(loadFonts);

  testWidgets('first run: he picks his company, the office is asked, the home screen says it waits', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    var current = view(ask: true);
    w.server.on('GET', '/api/v1/driver/platform-request', (r) => (200, current));
    w.server.on('POST', '/api/v1/driver/platform-request', (r) {
      current = view(request: request('pending', keeta), ask: false);
      return (201, current);
    });
    w.server.on('POST', '/api/v1/driver/platform-request/req-1/cancel', (r) {
      current = view(ask: true);
      return (200, current);
    });
    final templates = (await tester.runAsync(
      () async =>
          jsonDecode(await File('../backend/app/modules/payroll/rules/templates.json').readAsString()) as List<dynamic>,
    ))!;
    w.server.on(
      'GET',
      '/api/v1/driver/platform-request/1/schemes',
      (r) => (200, [offer(templates, 'keeta_fixed_200'), offer(templates, 'keeta_fixed_165')]),
    );
    await pumpApp(tester, w);
    expect(find.text('أنت شغال مع أنهي شركة؟'), findsOneWidget);
    expect(find.byKey(const Key('company-keeta')), findsOneWidget);
    expect(find.byKey(const Key('company-talabat')), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byKey(const Key('company-next'))).onPressed, isNull); // nothing picked

    await tester.tap(find.byKey(const Key('company-keeta')));
    await settle(tester);
    await tester.tap(find.byKey(const Key('company-next')));
    await idle(tester);
    // the company's schemes as cards: the salary, the target with an order over or short of it, the bonus tiers
    expect(find.text('اختر النظام المناسب لك'), findsOneWidget);
    final card = find.byKey(const Key('offer-keeta_fixed_200'));
    expect(find.descendant(of: card, matching: find.textContaining('\u2066200\u2069')), findsWidgets);
    expect(find.descendant(of: card, matching: find.text('\u2066420\u2069')), findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('+\u20660.476\u2069 د.ك')), findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('−\u20660.476\u2069 د.ك')), findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('\u2066100\u2069 د.ك')), findsOneWidget); // 610 orders
    expect(find.descendant(of: card, matching: find.text('السكن')), findsOneWidget); // on the company
    expect(find.byKey(const Key('offer-keeta_fixed_165'), skipOffstage: false), findsOneWidget);
    await shot(tester, '40-scheme-offers');
    await reveal(tester, find.byKey(const Key('company-send')));
    expect(tester.widget<FilledButton>(find.byKey(const Key('company-send'))).onPressed, isNull); // no scheme yet
    await tester.scrollUntilVisible(
      find.byKey(const Key('offer-pick-keeta_fixed_200')),
      -300,
      scrollable: find.byType(Scrollable).first,
    );

    await tester.tap(find.byKey(const Key('offer-pick-keeta_fixed_200')));
    await settle(tester);
    expect(find.byKey(const Key('offer-check')), findsOneWidget);
    expect(find.byKey(const Key('offer-picked-keeta_fixed_200')), findsOneWidget);
    await reveal(tester, find.byKey(const Key('company-note')));
    await tester.enterText(find.byKey(const Key('company-note')), 'من أول الشهر');
    await reveal(tester, find.byKey(const Key('company-send')));
    await tester.tap(find.byKey(const Key('company-send')));
    await idle(tester);
    final sent = jsonDecode(w.server.calls('/api/v1/driver/platform-request', method: 'POST').single.body) as Map;
    expect(sent, {'platform_id': 1, 'scheme_id': 'id-keeta_fixed_200', 'note': 'من أول الشهر'});
    expect(find.byKey(const Key('company-title')), findsNothing); // the home screen meanwhile
    expect(find.text('طلبك للعمل مع كيتا بانتظار موافقة المكتب'), findsOneWidget);
    expect(w.state.company!.pending, isTrue);

    await reveal(tester, find.byKey(const Key('company-change')));
    await tester.tap(find.byKey(const Key('company-change')));
    await idle(tester);
    expect(w.server.calls('/api/v1/driver/platform-request/req-1/cancel'), hasLength(1));
    expect(find.text('أنت شغال مع أنهي شركة؟'), findsOneWidget); // back to the choice
  });

  testWidgets('rejected: the screen comes back with the office\'s reason', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    w.server.on(
      'GET',
      '/api/v1/driver/platform-request',
      (r) => (200, view(request: request('rejected', talabat, note: 'أنت على كيتا حسب الكشف'), ask: true)),
    );
    await pumpApp(tester, w);
    expect(find.byKey(const Key('company-rejected')), findsOneWidget);
    expect(find.textContaining('أنت على كيتا حسب الكشف'), findsOneWidget);
    expect(find.textContaining('(طلبات)'), findsOneWidget);
  });

  testWidgets('approved: no company screen, no waiting banner', (tester) async {
    final w = (await tester.runAsync(() => world()))!;
    w.server.on(
      'GET',
      '/api/v1/driver/platform-request',
      (r) => (200, view(platform: keeta, request: request('approved', keeta), ask: false)),
    );
    await pumpApp(tester, w);
    expect(find.byKey(const Key('company-title')), findsNothing);
    expect(find.byKey(const Key('company-pending')), findsNothing);
    expect(find.byKey(const Key('start-day')), findsOneWidget);
  });

  testWidgets('an older server without company requests: straight to the home screen', (tester) async {
    final w = (await tester.runAsync(() => world()))!; // no route: 404
    await pumpApp(tester, w);
    expect(find.byKey(const Key('company-title')), findsNothing);
    expect(w.state.company, isNull);
    expect(find.byKey(const Key('start-day')), findsOneWidget);
  });
}
