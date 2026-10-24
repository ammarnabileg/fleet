import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'app_test.dart' show idle, loadFonts, pumpApp, reveal, settle, world;

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
    await pumpApp(tester, w);
    expect(find.text('أنت شغال مع أنهي شركة؟'), findsOneWidget);
    expect(find.byKey(const Key('company-keeta')), findsOneWidget);
    expect(find.byKey(const Key('company-talabat')), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byKey(const Key('company-send'))).onPressed, isNull); // nothing picked

    await tester.tap(find.byKey(const Key('company-keeta')));
    await settle(tester);
    await tester.enterText(find.byKey(const Key('company-note')), 'من أول الشهر');
    await tester.tap(find.byKey(const Key('company-send')));
    await idle(tester);
    final sent = jsonDecode(w.server.calls('/api/v1/driver/platform-request', method: 'POST').single.body) as Map;
    expect(sent, {'platform_id': 1, 'note': 'من أول الشهر'});
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
