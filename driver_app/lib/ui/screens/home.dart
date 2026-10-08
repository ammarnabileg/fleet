import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show DateFormat, NumberFormat;

import '../../app/state.dart';
import '../../core/config.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../../core/outbox.dart';
import '../../l10n/app_localizations.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'accident.dart';
import 'fines.dart';
import 'fuel.dart';
import 'maintenance.dart';
import 'me.dart';
import 'notifications.dart';
import 'odometer.dart';
import 'report.dart';
import 'schemes.dart';
import 'statement.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.state});

  final AppState state;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

/// The five tabs of the design: home, the daily work, cash, maintenance, the account. A tab the office hides is
/// left out; the open one is remembered by name, so it stays open when another appears or goes.
class _HomeScreenState extends State<HomeScreen> {
  String tab = 'home';

  void _go(String name) => setState(() => tab = name);

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final s = widget.state;
    final name = s.profile?.name;
    final first = name == null ? null : '${name[s.lang] ?? name['ar'] ?? ''}'.trim().split(RegExp(r'\s+')).first;
    final tabs = [
      (
        'home',
        HomeTab(state: s, onTab: _go),
        first == null || first.isEmpty ? l.appTitle : l.greeting(first),
        NavigationDestination(
          icon: const Icon(Icons.home_outlined),
          selectedIcon: const Icon(Icons.home_rounded),
          label: l.tabHome,
        ),
      ),
      if (s.shows('daily_report'))
        (
          'work',
          WorkTab(state: s),
          l.reportTitle,
          NavigationDestination(
            icon: const Icon(Icons.assignment_outlined),
            selectedIcon: const Icon(Icons.assignment),
            label: l.tabWork,
          ),
        ),
      if (s.shows('cash'))
        (
          'cash',
          CashTab(state: s),
          l.cashTitle,
          NavigationDestination(
            icon: const Icon(Icons.account_balance_wallet_outlined),
            selectedIcon: const Icon(Icons.account_balance_wallet),
            label: l.tabCash,
          ),
        ),
      if (s.shows('maintenance'))
        (
          'maintenance',
          MaintenanceTab(state: s),
          l.maintenance,
          NavigationDestination(
            icon: const Icon(Icons.build_outlined),
            selectedIcon: const Icon(Icons.build),
            label: l.maintenance,
          ),
        ),
      (
        'account',
        AccountTab(state: s),
        l.tabAccount,
        NavigationDestination(
          icon: const Icon(Icons.person_outline),
          selectedIcon: const Icon(Icons.person),
          label: l.tabAccount,
        ),
      ),
    ];
    var index = tabs.indexWhere((t) => t.$1 == tab);
    if (index < 0) {
      // the office hid the open tab: home, and it stays home when that tab comes back
      index = 0;
      tab = 'home';
    }
    final unread = s.notices?.unread ?? 0;
    return Scaffold(
      appBar: AppBar(
        title: Text(tabs[index].$3),
        actions: [
          if (tabs[index].$1 != 'account')
            Padding(
              padding: const EdgeInsetsDirectional.only(end: 16),
              child: _Bell(
                unread: unread,
                tooltip: l.noticesTitle,
                onTap: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => NotificationsScreen(state: s))),
              ),
            ),
        ],
      ),
      body: tabs[index].$2,
      bottomNavigationBar: DecoratedBox(
        decoration: const BoxDecoration(
          border: Border(top: BorderSide(color: AppColors.border)),
        ),
        child: NavigationBar(
          selectedIndex: index,
          onDestinationSelected: (i) => _go(tabs[i].$1),
          destinations: [for (final t in tabs) t.$4],
        ),
      ),
    );
  }
}

/// The bell: a white circle, the unread count on a red badge.
class _Bell extends StatelessWidget {
  const _Bell({required this.unread, required this.onTap, required this.tooltip});

  final int unread;
  final VoidCallback onTap;
  final String tooltip;

  @override
  Widget build(BuildContext context) => Tooltip(
    message: tooltip,
    child: InkWell(
      key: const Key('notifications'),
      customBorder: const CircleBorder(),
      onTap: onTap,
      child: Container(
        width: 38,
        height: 38,
        decoration: const BoxDecoration(
          color: AppColors.surface,
          shape: BoxShape.circle,
          boxShadow: AppColors.shadowXs,
        ),
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            const Center(child: Icon(Icons.notifications_none_rounded, size: 21, color: AppColors.text2)),
            if (unread > 0)
              Positioned(
                top: -3,
                right: -3,
                child: Container(
                  constraints: const BoxConstraints(minWidth: 18, minHeight: 18),
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  decoration: BoxDecoration(
                    color: AppColors.dangerFill,
                    borderRadius: BorderRadius.circular(9),
                    border: Border.all(color: Colors.white, width: 2),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    '$unread',
                    style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w700, height: 1.2),
                  ),
                ),
              ),
          ],
        ),
      ),
    ),
  );
}

String when(BuildContext context, DateTime t) =>
    '\u2066${DateFormat('dd-MM-yyyy HH:mm', 'en').format(t.toLocal())}\u2069';

/// How long ago, shortly ("منذ 5 د").
String ago(BuildContext context, DateTime t) {
  final l = context.l;
  final d = DateTime.now().difference(t);
  if (d.inMinutes < 1) return l.agoNow;
  if (d.inHours < 1) return l.agoMinutes('\u2066${d.inMinutes}\u2069');
  if (d.inDays < 1) return l.agoHours('\u2066${d.inHours}\u2069');
  return l.agoDays('\u2066${d.inDays}\u2069');
}

String km(int n) => '\u2066${NumberFormat('#,###', 'en').format(n)}\u2069';

Future<void> _push(BuildContext context, Widget screen) =>
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));

class HomeTab extends StatelessWidget {
  const HomeTab({super.key, required this.state, required this.onTab});

  final AppState state;
  final void Function(String tab) onTab;

  Future<void> _refresh() async {
    try {
      await state.loadAppConfig();
      await Future.wait([
        state.loadToday(),
        if (state.shows('cash')) state.loadCash(),
        if (state.shows('daily_report')) state.loadReports(),
        if (state.shows('maintenance')) state.loadMaintenance(),
        if (state.shows('accidents')) state.loadAccidents(),
        if (state.shows('fuel')) state.loadFuel(),
        state.loadNotices(),
      ]);
      await state.loadProfile();
    } on ApiError {
      // offline: the last data stays on screen
    }
    await state.reloadLocal();
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final custody = state.today?.custody;
    final cash = state.cash;
    final report = state.todaysReport;
    final unconfirmed = cash?.receipts.where((r) => r.confirmedAt == null).length ?? 0;
    final actions = [
      if (state.shows('daily_report'))
        QuickAction(
          key: const Key('daily-report'),
          icon: Icons.assignment_outlined,
          title: l.dailyReport,
          subtitle: report != null
              ? l.workReportSent
              : state.todaysQueuedReport != null
              ? l.workReportQueued
              : state.reportForm.fields.contains('cash')
              ? l.qaReportSub
              : l.qaReportSubDays,
          onTap: () => _push(context, ReportScreen(state: state)),
        ),
      if (state.shows('cash'))
        QuickAction(
          key: const Key('qa-cash'),
          icon: Icons.account_balance_wallet_outlined,
          title: l.qaBalance,
          subtitle: cash == null ? null : money(cash.total, l.kwd),
          onTap: () => onTab('cash'),
        ),
      if (state.shows('maintenance'))
        QuickAction(
          key: const Key('maintenance'),
          icon: Icons.build_outlined,
          title: l.kind_maintenance,
          subtitle: l.qaMaintenanceSub,
          onTap: () => _push(context, MaintenanceScreen(state: state)),
        ),
      if (state.shows('accidents'))
        QuickAction(
          key: const Key('accident'),
          icon: Icons.warning_amber_rounded,
          title: l.accident,
          subtitle: l.qaAccidentSub,
          danger: true,
          onTap: () => _push(context, AccidentScreen(state: state)),
        ),
      // only when his pay scheme puts fuel on the company (no fuel card, a car with him)
      if (state.shows('fuel') && state.fuel?.allowed == true)
        QuickAction(
          key: const Key('fuel'),
          icon: Icons.local_gas_station,
          title: l.fuel,
          subtitle: l.qaFuelSub,
          onTap: () => _push(context, FuelScreen(state: state)),
        ),
      if (state.shows('cash') && cash != null && cash.receipts.isNotEmpty)
        QuickAction(
          key: const Key('qa-receipts'),
          icon: Icons.receipt_outlined,
          title: l.qaReceipts,
          subtitle: unconfirmed > 0 ? l.qaReceiptsWaiting('\u2066$unconfirmed\u2069') : l.qaReceiptsDone,
          onTap: () => onTab('cash'),
        ),
      if (state.shows('fines'))
        QuickAction(
          key: const Key('fines'),
          icon: Icons.receipt_long_outlined,
          title: l.fines,
          subtitle: l.qaFinesSub,
          onTap: () => _push(context, FinesScreen(state: state)),
        ),
      if (state.shows('statement'))
        QuickAction(
          key: const Key('statement'),
          icon: Icons.fact_check_outlined,
          title: l.monthlyStatement,
          subtitle: l.qaStatementSub,
          onTap: () => _push(context, StatementScreen(state: state)),
        ),
      if (state.shows('payslips'))
        QuickAction(
          key: const Key('payslips'),
          icon: Icons.payments_outlined,
          title: l.payslips,
          subtitle: l.qaPayslipsSub,
          onTap: () => _push(context, PayslipsScreen(state: state)),
        ),
      if (state.shows('schemes'))
        QuickAction(
          key: const Key('schemes'),
          icon: Icons.price_change_outlined,
          title: l.paySchemes,
          subtitle: l.qaSchemesSub,
          onTap: () => _push(context, SchemesScreen(state: state)),
        ),
    ];
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
        children: [
          for (final r in state.maintenance.where((r) => r.isReady && state.shows('maintenance'))) ...[
            ReadyBanner(request: r, state: state),
            const SizedBox(height: 12),
          ],
          for (final a in state.accidents.where((a) => a.awaitsPoliceReport && state.shows('accidents'))) ...[
            InkWell(
              key: Key('police-banner-${a.number}'),
              onTap: () => _push(context, AccidentScreen(state: state)),
              child: Banner2(
                text: l.accAwaitingPolice('${a.number}'),
                tone: BannerTone.warn,
                icon: Icons.description_outlined,
              ),
            ),
            const SizedBox(height: 12),
          ],
          _VehicleCard(state: state),
          if (custody != null) ...[const SizedBox(height: 12), _DayCard(state: state)],
          if (state.queued.isNotEmpty) ...[
            SectionTitle(l.outboxTitle),
            DCard.list(
              child: Column(
                children: [
                  for (final (i, item) in state.queued.indexed)
                    _QueuedTile(state: state, item: item, last: i == state.queued.length - 1),
                ],
              ),
            ),
          ],
          if (actions.isNotEmpty) ...[
            SectionTitle(l.quickActions),
            GridView(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              padding: EdgeInsets.zero,
              // as tall as the tile's text needs at the phone's font size
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                mainAxisSpacing: 10,
                crossAxisSpacing: 10,
                mainAxisExtent: 70 + MediaQuery.textScalerOf(context).scale(13.5 + 11) * 1.5,
              ),
              children: actions,
            ),
          ],
        ],
      ),
    );
  }
}

/// The car he holds, on the design's blue card: its plate, make and model, and whether his position is sent.
class _VehicleCard extends StatelessWidget {
  const _VehicleCard({required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final custody = state.today?.custody;
    if (custody == null) {
      return DCard(
        key: const Key('my-car'),
        child: Row(
          children: [
            const IconTile(
              Icons.directions_car_outlined,
              bg: AppColors.surface3,
              fg: AppColors.text3,
              size: 44,
              iconSize: 22,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l.noCustody, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700)),
                  Text(l.noCustodyHint, style: const TextStyle(fontSize: 12.5, color: AppColors.muted, height: 1.6)),
                ],
              ),
            ),
          ],
        ),
      );
    }
    final t = state.tracking;
    final on = t['running'] == true;
    final last = t['last_upload_at'] as String?;
    final waiting = (t['queue'] as num?)?.toInt() ?? 0;
    final status = [
      on ? l.trackingOn : l.trackingOff,
      if (on && last != null) l.lastSentAgo(ago(context, DateTime.parse(last))),
      if (waiting > 0) l.trackingWaiting('$waiting'),
    ].join(' · ');
    return GestureDetector(
      key: const Key('my-car'),
      onTap: () => _push(context, MyCarScreen(state: state)),
      child: Container(
        decoration: BoxDecoration(
          gradient: AppColors.vehicleGradient,
          borderRadius: BorderRadius.circular(20),
          boxShadow: const [BoxShadow(color: Color(0x330A5AD8), blurRadius: 18, offset: Offset(0, 6))],
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(
          children: [
            Positioned(
              left: -50,
              top: -70,
              child: Container(
                width: 180,
                height: 180,
                decoration: const BoxDecoration(color: Color(0x17FFFFFF), shape: BoxShape.circle),
              ),
            ),
            const Positioned(
              left: 14,
              bottom: 40,
              child: Icon(Icons.directions_car_filled_outlined, size: 64, color: Color(0x38FFFFFF)),
            ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l.yourCar, style: const TextStyle(color: Color(0xC7FFFFFF), fontSize: 12)),
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      Text(
                        '\u2066${custody.plate}\u2069',
                        style: const TextStyle(color: Colors.white, fontSize: 21, fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(width: 10),
                      if (custody.model?.isNotEmpty ?? false)
                        Flexible(
                          child: Text(
                            custody.model!,
                            textDirection: TextDirection.ltr,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(color: Color(0xE6FFFFFF), fontSize: 13),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                    decoration: BoxDecoration(color: const Color(0x24FFFFFF), borderRadius: BorderRadius.circular(12)),
                    child: Row(
                      children: [
                        Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                            color: on ? const Color(0xFF6CFF9B) : const Color(0xFFFFC46B),
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                color: (on ? const Color(0xFF6CFF9B) : const Color(0xFFFFC46B)).withValues(alpha: .5),
                                blurRadius: 6,
                                spreadRadius: 2,
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(status, style: const TextStyle(color: Colors.white, fontSize: 12)),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The day, as one card: not started (start it), started (when, at what reading; end it), ended (start again).
class _DayCard extends StatelessWidget {
  const _DayCard({required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final today = state.today!;
    Widget head(IconData icon, Color bg, Color fg, String title, String? sub) => Row(
      children: [
        IconTile(icon, bg: bg, fg: fg, size: 44, iconSize: 22),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700)),
              if (sub != null) Text(sub, style: const TextStyle(fontSize: 12.5, color: AppColors.muted, height: 1.6)),
            ],
          ),
        ),
      ],
    );
    Widget reading(String kind) => OdometerScreen(state: state, kind: kind);
    if (!state.dayStarted) {
      return DCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            head(
              Icons.wb_twilight_rounded,
              AppColors.primarySoft,
              AppColors.primaryStrong,
              l.dayNotStarted,
              l.dayNotStartedHint,
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              key: const Key('start-day'),
              icon: const Icon(Icons.play_arrow_rounded),
              label: Text(l.startDay),
              onPressed: () => _push(context, reading('start_day')),
            ),
          ],
        ),
      );
    }
    final queued = state.queuedStart;
    final at = queued?.at ?? today.dayStartedAt;
    final startKm = queued?.km ?? today.dayStartKm;
    if (!state.dayEnded) {
      return DCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            head(
              Icons.timer_outlined,
              AppColors.successSoft,
              AppColors.success,
              at == null
                  ? l.startDayDone
                  : l.dayStartedAt('\u2066${DateFormat('HH:mm', 'en').format(at.toLocal())}\u2069'),
              startKm == null ? null : l.dayStartKm(km(startKm)),
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              key: const Key('end-day'),
              icon: const Icon(Icons.nightlight_outlined),
              label: Text(l.endDay),
              onPressed: () => _push(context, reading('end_day')),
            ),
          ],
        ),
      );
    }
    return DCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          head(
            Icons.nights_stay_outlined,
            AppColors.neutralSoft,
            AppColors.neutral,
            l.endDayDone,
            today.canStartAgain ? l.dayEndedHint : null,
          ),
          // working once more the same day: a new session, its orders add to the day's (an older server: no)
          if (today.canStartAgain) ...[
            const SizedBox(height: 12),
            FilledButton.icon(
              key: const Key('start-again'),
              icon: const Icon(Icons.replay_rounded),
              label: Text(l.startAgain),
              onPressed: () => _push(context, reading('start_day')),
            ),
          ],
        ],
      ),
    );
  }
}

class _QueuedTile extends StatelessWidget {
  const _QueuedTile({required this.state, required this.item, required this.last});

  final AppState state;
  final OutboxItem item;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final failed = item.state == 'failed';
    final what = switch (item.kind) {
      'odometer' => l.kind_odometer,
      'maintenance' => l.kind_maintenance,
      'maintenance_pickup' => l.kind_pickup,
      'accident' => l.kind_accident,
      'police_report' => l.kind_police_report,
      'fuel' => l.kind_fuel,
      _ => l.kind_report,
    };
    final reason = failed
        ? state.message(ApiError(422, item.lastError ?? ''), network: l.networkError, generic: item.lastError ?? '')
        : l.outboxQueued;
    return DRow(
      divider: !last,
      leading: IconTile(
        failed ? Icons.error_outline : Icons.schedule,
        bg: failed ? AppColors.dangerSoft : AppColors.warningSoft,
        fg: failed ? AppColors.danger : AppColors.warning,
      ),
      title: what,
      subtitle: failed ? l.outboxFailed(reason) : reason,
      trailing: failed ? TextButton(onPressed: () => state.discard(item.id), child: Text(l.outboxDiscard)) : null,
    );
  }
}

/// A report in a line, with what the platform's form asks: orders, the valid day, the cash (as approved, once it is).
String reportSummary(AppLocalizations l, AppState state, Report? r, {int? orders, String? cash, bool? validDay}) {
  final asks = state.reportForm.fields;
  final n = r?.orders ?? orders;
  final valid = r?.validDay ?? validDay;
  final amount = r == null ? cash : (r.status == 'approved' ? r.approvedCash ?? r.cash : r.cash);
  return [
    if (asks.contains('orders') || n != null) l.ordersN('\u2066${n ?? '—'}\u2069'),
    if (valid != null) valid ? l.validDayYes : l.validDayNo,
    if (asks.contains('cash') && amount != null) money(amount, l.kwd),
  ].join(' · ');
}

/// The daily work: today's report (sent, or the way to send it) and the reports before.
class WorkTab extends StatelessWidget {
  const WorkTab({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final report = state.todaysReport;
    final waiting = report == null ? state.todaysQueuedReport : null;
    final due = report == null && waiting == null;
    final today = state.today;
    final at = state.queuedStart?.at ?? today?.dayStartedAt;
    return RefreshIndicator(
      onRefresh: () async {
        try {
          await Future.wait([state.loadReports(), state.loadToday()]);
        } on ApiError {
          // offline: the last list stays
        }
        await state.reloadLocal();
      },
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
        children: [
          Text(
            [
              '\u2066${DateFormat('dd-MM-yyyy', 'en').format(DateTime.now())}\u2069',
              if (state.dayStarted && !state.dayEnded && at != null)
                l.dayStartedAt('\u2066${DateFormat('HH:mm', 'en').format(at.toLocal())}\u2069'),
            ].join(' · '),
            style: const TextStyle(fontSize: 12.5, color: AppColors.muted),
          ),
          const SizedBox(height: 10),
          DCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    IconTile(
                      due ? Icons.assignment_outlined : Icons.hourglass_bottom_rounded,
                      bg: due ? AppColors.primarySoft : AppColors.warningSoft,
                      fg: due ? AppColors.primaryStrong : AppColors.warning,
                      size: 44,
                      iconSize: 22,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            report != null
                                ? l.workReportSent
                                : waiting != null
                                ? l.workReportQueued
                                : l.workReportDue,
                            style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700),
                          ),
                          Text(
                            report != null
                                ? reportSummary(l, state, report)
                                : waiting != null
                                ? reportSummary(
                                    l,
                                    state,
                                    null,
                                    orders: (waiting.payload['orders_count'] as num?)?.toInt(),
                                    cash: waiting.payload['cash_amount'] as String?,
                                    validDay: waiting.payload['valid_day'] as bool?,
                                  )
                                : state.reportForm.fields.contains('cash')
                                ? l.workReportDueHint
                                : l.workReportDueHintDays,
                            style: const TextStyle(fontSize: 12.5, color: AppColors.muted, height: 1.6),
                          ),
                        ],
                      ),
                    ),
                    if (report != null) _statusPill(l, report),
                    if (report == null && waiting != null) Pill(l.notSentYet, tone: BannerTone.warn),
                  ],
                ),
                if (due) ...[
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    key: const Key('work-report'),
                    icon: const Icon(Icons.send_rounded, size: 19),
                    label: Text(l.sendDailyReport),
                    onPressed: () => _push(context, ReportScreen(state: state)),
                  ),
                ],
              ],
            ),
          ),
          if (state.reports.isNotEmpty) ...[
            SectionTitle(l.recentReports),
            DCard.list(
              child: Column(
                children: [
                  for (final (i, r) in state.reports.take(10).indexed)
                    DRow(
                      key: Key('work-report-${r.id}'),
                      divider: i < state.reports.take(10).length - 1,
                      leading: const IconTile(Icons.assignment_outlined, bg: AppColors.surface3, fg: AppColors.text3),
                      title: [
                        '\u2066${r.businessDate}\u2069',
                        if (r.session > 1) l.reportSession('${r.session}'),
                      ].join(' · '),
                      subtitle: [
                        reportSummary(l, state, r),
                        if (r.changePending) l.changePending else ?r.reviewNote,
                      ].join('\n'),
                      trailing: _statusPill(l, r),
                      onTap: r.status == 'rejected' || r.changePending
                          ? null
                          : () => _push(context, ReportScreen(state: state, report: r)),
                    ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  static Widget _statusPill(AppLocalizations l, Report r) => switch (r.status) {
    'approved' => Pill(l.status_approved, tone: BannerTone.success),
    'returned' => Pill(l.status_returned, tone: BannerTone.danger),
    'rejected' => Pill(l.status_rejected, tone: BannerTone.danger),
    _ => Pill(l.status_submitted, tone: BannerTone.warn),
  };
}

/// Maintenance: a new request, the cars ready to collect, his requests and where each is.
class MaintenanceTab extends StatelessWidget {
  const MaintenanceTab({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final requests = state.maintenance;
    return RefreshIndicator(
      onRefresh: () async {
        try {
          await state.loadMaintenance();
        } on ApiError {
          // offline: the last list stays
        }
        await state.reloadLocal();
      },
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
        children: [
          FilledButton.icon(
            key: const Key('mnt-new'),
            icon: const Icon(Icons.add_rounded),
            label: Text(l.mntNew),
            onPressed: () => _push(context, MaintenanceScreen(state: state)),
          ),
          for (final r in requests.where((r) => r.isReady)) ...[
            const SizedBox(height: 12),
            ReadyBanner(request: r, state: state),
          ],
          SectionTitle(l.myRequests),
          if (requests.isEmpty)
            DCard(
              child: Text(l.mntNone, style: const TextStyle(color: AppColors.muted)),
            )
          else
            DCard.list(
              child: Column(
                children: [
                  for (final (i, r) in requests.indexed) RequestRow(request: r, divider: i < requests.length - 1),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class CashTab extends StatelessWidget {
  const CashTab({super.key, required this.state});

  final AppState state;

  Future<void> _confirm(BuildContext context, Receipt r) async {
    final l = context.l;
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        content: Text(l.confirmReceiptQ('\u2066${r.amount}\u2069')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: Text(l.cancel)),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: Text(l.confirmReceipt)),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await state.confirmReceipt(r.id);
    } catch (e) {
      if (context.mounted) showError(context, state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final cash = state.cash;
    final total = double.tryParse(cash?.total ?? '') ?? 0;
    final limit = double.tryParse(cash?.alertLimit ?? '') ?? 0;
    final pending = double.tryParse(cash?.pending ?? '') ?? 0;
    return RefreshIndicator(
      onRefresh: () async {
        try {
          await state.loadCash();
        } on ApiError {
          // offline
        }
        await state.reloadLocal();
      },
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 20),
        children: [
          if (cash == null)
            const Padding(
              padding: EdgeInsets.all(40),
              child: Center(child: CircularProgressIndicator()),
            )
          else ...[
            DCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(l.cashBalanceTitle, style: const TextStyle(fontSize: 12.5, color: AppColors.muted)),
                  const SizedBox(height: 2),
                  Text(
                    '\u2066${cash.total}\u2069',
                    key: const Key('cash-total'),
                    style: const TextStyle(fontSize: 34, fontWeight: FontWeight.w700, height: 1.3),
                  ),
                  if (pending != 0)
                    Text(
                      // "of which" only when it is a part of the balance; otherwise the figure on its own
                      pending > 0 && pending <= total
                          ? l.cashPendingPart('\u2066${cash.pending}\u2069')
                          : '${l.cashPending}: \u2066${cash.pending}\u2069',
                      style: const TextStyle(fontSize: 12.5, color: AppColors.muted),
                    ),
                  if (limit > 0) ...[
                    const SizedBox(height: 12),
                    Meter(
                      total / limit,
                      tone: cash.overLimit
                          ? BannerTone.danger
                          : cash.nearLimit
                          ? BannerTone.warn
                          : BannerTone.info,
                    ),
                    const SizedBox(height: 6),
                    if (!cash.overLimit && !cash.nearLimit)
                      Text(
                        l.cashLimit('\u2066${cash.alertLimit}\u2069'),
                        style: const TextStyle(fontSize: 12.5, color: AppColors.muted),
                      ),
                  ],
                ],
              ),
            ),
            if (cash.overLimit) ...[
              const SizedBox(height: 12),
              Banner2(text: l.cashOverLimit(money(cash.alertLimit, l.kwd)), tone: BannerTone.danger),
            ] else if (cash.nearLimit) ...[
              const SizedBox(height: 12),
              Banner2(
                key: const Key('cash-near-limit'),
                text: l.cashNearLimit(money(cash.alertLimit, l.kwd)),
                tone: BannerTone.warn,
              ),
            ],
            SectionTitle(l.receipts),
            if (cash.receipts.isEmpty)
              DCard(
                child: Text(l.noReceipts, style: const TextStyle(color: AppColors.muted)),
              )
            else
              DCard.list(
                child: Column(
                  children: [
                    for (final (i, r) in cash.receipts.indexed)
                      DRow(
                        divider: i < cash.receipts.length - 1,
                        leading: IconTile(
                          Icons.receipt_outlined,
                          bg: r.confirmedAt == null ? AppColors.warningSoft : AppColors.surface3,
                          fg: r.confirmedAt == null ? AppColors.warning : AppColors.text3,
                        ),
                        title: l.receiptNo('${r.number}'),
                        subtitle: '${money(r.amount, l.kwd)} · ${when(context, r.createdAt)}',
                        trailing: r.confirmedAt != null
                            ? Pill(l.receiptConfirmed, tone: BannerTone.success)
                            : TextButton(onPressed: () => _confirm(context, r), child: Text(l.confirmReceipt)),
                      ),
                  ],
                ),
              ),
            SectionTitle(l.movements),
            if (cash.lines.isEmpty)
              DCard(
                child: Text(l.noMovements, style: const TextStyle(color: AppColors.muted)),
              )
            else
              DCard.list(
                child: Column(
                  children: [
                    for (final (i, m) in cash.lines.indexed)
                      DRow(
                        divider: i < cash.lines.length - 1,
                        title: switch (m.kind) {
                          'collection' => l.moveCollection,
                          'receipt' || 'deposit' => l.moveReceipt,
                          'adjustment' => l.moveAdjustment,
                          'reversal' => l.moveReversal,
                          'settlement' => l.moveSettlement,
                          'opening' => l.moveOpening,
                          'fuel' => l.moveFuel,
                          _ => m.kind,
                        },
                        subtitle: [
                          '\u2066${m.date}\u2069',
                          if (m.status == 'pending') l.cashPending,
                          if (m.status == 'rejected') l.status_rejected,
                          ?m.reason,
                        ].join(' · '),
                        trailing: Text(
                          '\u2066${m.amount.startsWith('-') ? '' : '+'}${m.amount}\u2069',
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                            color: m.status == 'rejected'
                                ? AppColors.muted
                                : m.amount.startsWith('-')
                                ? AppColors.success
                                : AppColors.text,
                            decoration: m.status == 'rejected' ? TextDecoration.lineThrough : null,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class AccountTab extends StatelessWidget {
  const AccountTab({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final t = state.tracking;
    final last = t['last_upload_at'] as String?;
    final p = state.profile;
    String named(Map<String, dynamic>? n) => n == null ? '—' : '${n[state.lang] ?? n['ar'] ?? '—'}';
    final details = p == null
        ? const <(IconData, String, String)>[]
        : [
            for (final (icon, label, value) in [
              (Icons.phone_iphone_rounded, l.phoneLabel, p.text('phone')),
              (Icons.badge_outlined, l.civilId, p.text('civil_id')),
              (
                Icons.delivery_dining_outlined,
                l.platformLabel,
                p.named('platform') == null
                    ? null
                    : '${named(p.named('platform'))}${p.text('platform_driver_id') == null ? '' : ' · \u2066${p.text('platform_driver_id')}\u2069'}',
              ),
              (
                Icons.account_balance_outlined,
                l.bankLabel,
                p.text('bank_name') == null && p.text('iban_last4') == null
                    ? null
                    : '${p.text('bank_name') ?? ''} \u2066****${p.text('iban_last4') ?? ''}\u2069',
              ),
            ])
              if (value != null)
                (icon, label, value.startsWith('+') || RegExp(r'^\d').hasMatch(value) ? '\u2066$value\u2069' : value),
          ];
    final company = p?.named('company');
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
      children: [
        if (p != null) ...[
          DCard(
            key: const Key('profile'),
            child: Row(
              children: [
                Avatar(named(p.name), size: 52),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(named(p.name), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                      const SizedBox(height: 2),
                      Text(
                        company == null
                            ? '${l.employeeNumber}: \u2066${p.employeeNumber}\u2069'
                            : l.employeeAt('\u2066${p.employeeNumber}\u2069', named(company)),
                        style: const TextStyle(fontSize: 12.5, color: AppColors.muted),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (details.isNotEmpty) ...[
            SectionTitle(l.profileTitle),
            DCard.list(
              child: Column(
                children: [
                  for (final (i, (icon, label, value)) in details.indexed)
                    DRow(
                      divider: i < details.length - 1,
                      leading: Icon(icon, size: 19, color: AppColors.text3),
                      title: label,
                      trailing: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 210),
                        child: Text(
                          value,
                          textAlign: TextAlign.end,
                          style: const TextStyle(fontSize: 13, color: AppColors.text2),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 12),
        ],
        DCard.list(
          child: Column(
            children: [
              DRow(
                key: const Key('my-documents'),
                leading: const Icon(Icons.folder_shared_outlined, size: 19, color: AppColors.text3),
                title: l.myDocuments,
                chevron: true,
                onTap: () => _push(context, DocumentsScreen(state: state)),
              ),
              DRow(
                leading: const Icon(Icons.gps_fixed_rounded, size: 19, color: AppColors.text3),
                title: l.trackingDetails,
                subtitle:
                    '${t['running'] == true ? l.trackingOn : l.trackingOff} · ${l.lastUpload(last == null ? l.never : when(context, DateTime.parse(last)))}'
                    '${((t['queue'] as num?) ?? 0) > 0 ? ' · ${l.trackingWaiting('${t['queue']}')}' : ''}',
                trailing: Pill(
                  t['running'] == true ? l.trackingOn : l.trackingOff,
                  tone: t['running'] == true ? BannerTone.success : BannerTone.warn,
                ),
              ),
              DRow(
                leading: const Icon(Icons.translate_rounded, size: 19, color: AppColors.text3),
                title: l.language,
                trailing: SegmentedButton<String>(
                  showSelectedIcon: false,
                  segments: const [
                    ButtonSegment(value: 'ar', label: Text('العربية')),
                    ButtonSegment(value: 'en', label: Text('English')),
                  ],
                  selected: {state.lang},
                  onSelectionChanged: (s) => state.setLang(s.first),
                ),
              ),
              DRow(
                divider: false,
                leading: const Icon(Icons.smartphone_rounded, size: 19, color: AppColors.text3),
                title: l.thisPhone,
                subtitle: l.appVersion(AppConfig.appVersion),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: AppColors.dangerSoft,
            foregroundColor: AppColors.danger,
            elevation: 0,
            minimumSize: const Size.fromHeight(48),
          ),
          icon: const Icon(Icons.logout_rounded, size: 18),
          label: Text(l.signOut),
          onPressed: () async {
            final ok = await showDialog<bool>(
              context: context,
              builder: (c) => AlertDialog(
                icon: const IconTile(Icons.logout_rounded, bg: AppColors.dangerSoft, fg: AppColors.danger),
                content: Text(l.signOutQ),
                actions: [
                  TextButton(onPressed: () => Navigator.pop(c, false), child: Text(l.cancel)),
                  FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.dangerFill,
                      minimumSize: const Size(0, 44),
                    ),
                    onPressed: () => Navigator.pop(c, true),
                    child: Text(l.signOut),
                  ),
                ],
              ),
            );
            if (ok == true) await state.signOut();
          },
        ),
      ],
    );
  }
}

/// After sending: sent, or kept on the phone until the network is back.
class ResultScreen extends StatelessWidget {
  const ResultScreen({super.key, required this.result});

  final SendResult result;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final sent = result == SendResult.sent;
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Container(
                  width: 84,
                  height: 84,
                  decoration: BoxDecoration(
                    color: sent ? AppColors.successSoft : AppColors.warningSoft,
                    shape: BoxShape.circle,
                  ),
                  child: Icon(
                    sent ? Icons.check_rounded : Icons.cloud_off_outlined,
                    size: 42,
                    color: sent ? AppColors.success : AppColors.warning,
                  ),
                ),
              ),
              const SizedBox(height: 18),
              Text(
                sent ? l.sentTitle : l.queuedTitle,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 8),
              Text(
                sent ? l.sentText : l.queuedText,
                textAlign: TextAlign.center,
                style: const TextStyle(color: AppColors.muted, height: 1.7),
              ),
              const SizedBox(height: 28),
              FilledButton(onPressed: () => Navigator.of(context).popUntil((r) => r.isFirst), child: Text(l.done)),
            ],
          ),
        ),
      ),
    );
  }
}
