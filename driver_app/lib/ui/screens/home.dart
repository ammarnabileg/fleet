import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../app/state.dart';
import '../../core/config.dart';
import '../../core/errors.dart';
import '../../core/outbox.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'accident.dart';
import 'fines.dart';
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

class _HomeScreenState extends State<HomeScreen> {
  int tab = 0;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final s = widget.state;
    final tabs = [
      (
        HomeTab(state: s),
        l.appTitle,
        NavigationDestination(
          icon: const Icon(Icons.home_outlined),
          selectedIcon: const Icon(Icons.home),
          label: l.tabHome,
        ),
      ),
      if (s.shows('cash'))
        (
          CashTab(state: s),
          l.cashTitle,
          NavigationDestination(
            icon: const Icon(Icons.account_balance_wallet_outlined),
            selectedIcon: const Icon(Icons.account_balance_wallet),
            label: l.tabCash,
          ),
        ),
      (
        AccountTab(state: s),
        l.tabAccount,
        NavigationDestination(
          icon: const Icon(Icons.person_outline),
          selectedIcon: const Icon(Icons.person),
          label: l.tabAccount,
        ),
      ),
    ];
    if (tab >= tabs.length) tab = 0; // the office hid a tab while it was open
    final unread = s.notices?.unread ?? 0;
    return Scaffold(
      appBar: AppBar(
        title: Text(tabs[tab].$2),
        actions: [
          IconButton(
            key: const Key('notifications'),
            tooltip: l.noticesTitle,
            icon: Badge(
              isLabelVisible: unread > 0,
              label: Text('$unread'),
              child: const Icon(Icons.notifications_outlined),
            ),
            onPressed: () =>
                Navigator.of(context).push(MaterialPageRoute(builder: (_) => NotificationsScreen(state: s))),
          ),
        ],
      ),
      body: tabs[tab].$1,
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (i) => setState(() => tab = i),
        destinations: [for (final t in tabs) t.$3],
      ),
    );
  }
}

String when(BuildContext context, DateTime t) =>
    '\u2066${DateFormat('dd-MM-yyyy HH:mm', 'en').format(t.toLocal())}\u2069';

class HomeTab extends StatelessWidget {
  const HomeTab({super.key, required this.state});

  final AppState state;

  Future<void> _refresh() async {
    try {
      await state.loadAppConfig();
      await Future.wait([
        state.loadToday(),
        if (state.shows('cash')) state.loadCash(),
        if (state.shows('daily_report')) state.loadReports(),
        if (state.shows('maintenance')) state.loadMaintenance(),
        if (state.shows('accidents')) state.loadAccidents(),
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
    final today = state.today;
    final custody = today?.custody;
    final tracking = state.tracking;
    final on = tracking['running'] == true;
    final waiting = (tracking['queue'] as num?)?.toInt() ?? 0;
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          for (final r in state.maintenance.where((r) => r.isReady && state.shows('maintenance'))) ...[
            ReadyBanner(request: r, state: state),
            const SizedBox(height: 12),
          ],
          for (final a in state.accidents.where((a) => a.awaitsPoliceReport && state.shows('accidents'))) ...[
            InkWell(
              key: Key('police-banner-${a.number}'),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => AccidentScreen(state: state))),
              child: Banner2(
                text: l.accAwaitingPolice('${a.number}'),
                tone: BannerTone.warn,
                icon: Icons.description_outlined,
              ),
            ),
            const SizedBox(height: 12),
          ],
          Card(
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              key: const Key('my-car'),
              onTap: custody == null
                  ? null
                  : () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => MyCarScreen(state: state))),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: custody == null
                    ? Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.directions_car_outlined, size: 32, color: AppColors.muted),
                          const SizedBox(height: 8),
                          Text(l.noCustody, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                          const SizedBox(height: 4),
                          Text(l.noCustodyHint, style: const TextStyle(color: AppColors.muted, height: 1.6)),
                        ],
                      )
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                decoration: BoxDecoration(
                                  color: AppColors.text,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text(
                                  '\u2066${custody.plate}\u2069',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 20,
                                    fontWeight: FontWeight.w700,
                                    letterSpacing: 1,
                                  ),
                                ),
                              ),
                              const Spacer(),
                              Pill(on ? l.trackingOn : l.trackingOff, tone: on ? BannerTone.success : BannerTone.warn),
                            ],
                          ),
                          const SizedBox(height: 10),
                          Text(
                            l.custodySince(when(context, custody.startedAt)),
                            style: const TextStyle(color: AppColors.muted),
                          ),
                          if (custody.lastKm != null)
                            Text(
                              l.lastKm('\u2066${NumberFormat('#,###', 'en').format(custody.lastKm)}\u2069'),
                              style: const TextStyle(color: AppColors.muted),
                            ),
                          if (waiting > 0) ...[
                            const SizedBox(height: 6),
                            Text(l.trackingWaiting('$waiting'), style: const TextStyle(color: AppColors.warning)),
                          ],
                        ],
                      ),
              ),
            ),
          ),
          const SizedBox(height: 14),
          if (custody != null) ...[
            state.dayStarted
                ? Banner2(text: l.startDayDone, tone: BannerTone.success, icon: Icons.check_circle_outline)
                : FilledButton.icon(
                    key: const Key('start-day'),
                    icon: const Icon(Icons.speed),
                    label: Text(l.startDay),
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => OdometerScreen(state: state, kind: 'start_day'),
                      ),
                    ),
                  ),
            const SizedBox(height: 10),
          ],
          if (state.shows('daily_report'))
            OutlinedButton.icon(
              key: const Key('daily-report'),
              icon: const Icon(Icons.assignment_outlined),
              label: Text(l.dailyReport),
              onPressed: () =>
                  Navigator.of(context).push(MaterialPageRoute(builder: (_) => ReportScreen(state: state))),
            ),
          if (custody != null && state.dayStarted) ...[
            const SizedBox(height: 10),
            if (state.dayEnded) ...[
              Banner2(text: l.endDayDone, tone: BannerTone.success, icon: Icons.nightlight_outlined),
              // working once more the same day: a new session, its orders add to the day's (an older server: no)
              if (today!.canStartAgain) ...[
                const SizedBox(height: 10),
                FilledButton.icon(
                  key: const Key('start-again'),
                  icon: const Icon(Icons.replay),
                  label: Text(l.startAgain),
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => OdometerScreen(state: state, kind: 'start_day'),
                    ),
                  ),
                ),
              ],
            ] else
              OutlinedButton.icon(
                key: const Key('end-day'),
                icon: const Icon(Icons.nightlight_outlined),
                label: Text(l.endDay),
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => OdometerScreen(state: state, kind: 'end_day'),
                  ),
                ),
              ),
          ],
          for (final (screen, button) in [
            (
              'maintenance',
              OutlinedButton.icon(
                key: const Key('maintenance'),
                icon: const Icon(Icons.car_repair),
                label: Text(l.maintenance),
                onPressed: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => MaintenanceScreen(state: state))),
              ),
            ),
            (
              'accidents',
              OutlinedButton.icon(
                key: const Key('accident'),
                style: OutlinedButton.styleFrom(foregroundColor: AppColors.danger),
                icon: const Icon(Icons.car_crash_outlined),
                label: Text(l.accident),
                onPressed: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => AccidentScreen(state: state))),
              ),
            ),
            (
              'fines',
              OutlinedButton.icon(
                key: const Key('fines'),
                icon: const Icon(Icons.receipt_long_outlined),
                label: Text(l.fines),
                onPressed: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => FinesScreen(state: state))),
              ),
            ),
            (
              'statement',
              OutlinedButton.icon(
                key: const Key('statement'),
                icon: const Icon(Icons.fact_check_outlined),
                label: Text(l.monthlyStatement),
                onPressed: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => StatementScreen(state: state))),
              ),
            ),
            (
              'payslips',
              OutlinedButton.icon(
                key: const Key('payslips'),
                icon: const Icon(Icons.payments_outlined),
                label: Text(l.payslips),
                onPressed: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => PayslipsScreen(state: state))),
              ),
            ),
            (
              'schemes',
              OutlinedButton.icon(
                key: const Key('schemes'),
                icon: const Icon(Icons.price_change_outlined),
                label: Text(l.paySchemes),
                onPressed: () =>
                    Navigator.of(context).push(MaterialPageRoute(builder: (_) => SchemesScreen(state: state))),
              ),
            ),
          ])
            if (state.shows(screen)) ...[const SizedBox(height: 10), button],
          if (state.queued.isNotEmpty) ...[
            SectionTitle(l.outboxTitle),
            for (final item in state.queued) _QueuedTile(state: state, item: item),
          ],
        ],
      ),
    );
  }
}

class _QueuedTile extends StatelessWidget {
  const _QueuedTile({required this.state, required this.item});

  final AppState state;
  final OutboxItem item;

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
      _ => l.kind_report,
    };
    final reason = failed
        ? state.message(ApiError(422, item.lastError ?? ''), network: l.networkError, generic: item.lastError ?? '')
        : l.outboxQueued;
    return Card(
      child: ListTile(
        leading: Icon(
          failed ? Icons.error_outline : Icons.schedule,
          color: failed ? AppColors.danger : AppColors.warning,
        ),
        title: Text(what),
        subtitle: Text(failed ? l.outboxFailed(reason) : reason),
        trailing: failed ? TextButton(onPressed: () => state.discard(item.id), child: Text(l.outboxDiscard)) : null,
      ),
    );
  }
}

class CashTab extends StatelessWidget {
  const CashTab({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final cash = state.cash;
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
        padding: const EdgeInsets.all(16),
        children: [
          if (cash == null)
            const Padding(
              padding: EdgeInsets.all(40),
              child: Center(child: CircularProgressIndicator()),
            )
          else ...[
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(l.cashTotal, style: const TextStyle(color: AppColors.muted)),
                    const SizedBox(height: 6),
                    Text(
                      money(cash.total, l.kwd),
                      key: const Key('cash-total'),
                      style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w700),
                    ),
                    const Divider(height: 26),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${l.cashPosted}\n${money(cash.posted, l.kwd)}',
                            style: const TextStyle(height: 1.6),
                          ),
                        ),
                        Expanded(
                          child: Text(
                            '${l.cashPending}\n${money(cash.pending, l.kwd)}',
                            style: const TextStyle(height: 1.6),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            if (cash.overLimit) ...[
              const SizedBox(height: 12),
              Banner2(text: l.cashOverLimit(money(cash.alertLimit, l.kwd)), tone: BannerTone.warn),
            ] else if (cash.nearLimit) ...[
              const SizedBox(height: 12),
              Banner2(
                key: const Key('cash-near-limit'),
                text: l.cashNearLimit(money(cash.alertLimit, l.kwd)),
                tone: BannerTone.warn,
              ),
            ],
            SectionTitle(l.receipts),
            if (cash.receipts.isEmpty) Text(l.noReceipts, style: const TextStyle(color: AppColors.muted)),
            for (final r in cash.receipts)
              Card(
                child: ListTile(
                  title: Text(l.receiptNo('${r.number}')),
                  subtitle: Text('${money(r.amount, l.kwd)} · ${when(context, r.createdAt)}'),
                  trailing: r.confirmedAt != null
                      ? Pill(l.receiptConfirmed, tone: BannerTone.success)
                      : TextButton(
                          onPressed: () async {
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
                          },
                          child: Text(l.confirmReceipt),
                        ),
                ),
              ),
            SectionTitle(l.movements),
            if (cash.lines.isEmpty) Text(l.noMovements, style: const TextStyle(color: AppColors.muted)),
            for (final m in cash.lines)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: Text(switch (m.kind) {
                  'collection' => l.moveCollection,
                  'receipt' || 'deposit' => l.moveReceipt,
                  'adjustment' => l.moveAdjustment,
                  'reversal' => l.moveReversal,
                  'settlement' => l.moveSettlement,
                  'opening' => l.moveOpening,
                  _ => m.kind,
                }),
                subtitle: Text(
                  [
                    '\u2066${m.date}\u2069',
                    if (m.status == 'pending') l.cashPending,
                    if (m.status == 'rejected') l.status_rejected,
                    ?m.reason,
                  ].join(' · '),
                ),
                trailing: Text(
                  '\u2066${m.amount.startsWith('-') ? '' : '+'}${m.amount}\u2069',
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    color: m.status == 'rejected'
                        ? AppColors.muted
                        : m.amount.startsWith('-')
                        ? AppColors.success
                        : null,
                    decoration: m.status == 'rejected' ? TextDecoration.lineThrough : null,
                  ),
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
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (p != null) ...[
          SectionTitle(l.profileTitle),
          Card(
            key: const Key('profile'),
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.badge_outlined),
                  title: Text(named(p.name), style: const TextStyle(fontWeight: FontWeight.w700)),
                  subtitle: Text('${l.employeeNumber}: \u2066${p.employeeNumber}\u2069'),
                ),
                for (final (label, value) in [
                  (l.phoneLabel, p.text('phone')),
                  (l.civilId, p.text('civil_id')),
                  (l.companyLabel, named(p.named('company'))),
                  (
                    l.platformLabel,
                    p.named('platform') == null
                        ? null
                        : '${named(p.named('platform'))}${p.text('platform_driver_id') == null ? '' : ' · \u2066${p.text('platform_driver_id')}\u2069'}',
                  ),
                  (
                    l.bankLabel,
                    p.text('bank_name') == null && p.text('iban_last4') == null
                        ? null
                        : '${p.text('bank_name') ?? ''} \u2066****${p.text('iban_last4') ?? ''}\u2069',
                  ),
                ])
                  if (value != null)
                    ListTile(
                      dense: true,
                      title: Text(label),
                      trailing: Text(
                        value.startsWith('+') || RegExp(r'^\d').hasMatch(value) ? '\u2066$value\u2069' : value,
                      ),
                    ),
              ],
            ),
          ),
          const SizedBox(height: 12),
        ],
        Card(
          child: ListTile(
            key: const Key('my-documents'),
            leading: const Icon(Icons.folder_shared_outlined),
            title: Text(l.myDocuments),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => DocumentsScreen(state: state))),
          ),
        ),
        const SizedBox(height: 12),
        Card(
          child: Column(
            children: [
              ListTile(
                leading: const Icon(Icons.language),
                title: Text(l.language),
                trailing: SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'ar', label: Text('العربية')),
                    ButtonSegment(value: 'en', label: Text('English')),
                  ],
                  selected: {state.lang},
                  onSelectionChanged: (s) => state.setLang(s.first),
                ),
              ),
              ListTile(
                leading: const Icon(Icons.gps_fixed),
                title: Text(l.trackingDetails),
                subtitle: Text(
                  '${t['running'] == true ? l.trackingOn : l.trackingOff} · ${l.lastUpload(last == null ? l.never : when(context, DateTime.parse(last)))}'
                  '${((t['queue'] as num?) ?? 0) > 0 ? ' · ${l.trackingWaiting('${t['queue']}')}' : ''}',
                ),
              ),
              ListTile(leading: const Icon(Icons.info_outline), title: Text(l.appVersion(AppConfig.appVersion))),
            ],
          ),
        ),
        const SizedBox(height: 20),
        OutlinedButton.icon(
          style: OutlinedButton.styleFrom(foregroundColor: AppColors.danger),
          icon: const Icon(Icons.logout),
          label: Text(l.signOut),
          onPressed: () async {
            final ok = await showDialog<bool>(
              context: context,
              builder: (c) => AlertDialog(
                content: Text(l.signOutQ),
                actions: [
                  TextButton(onPressed: () => Navigator.pop(c, false), child: Text(l.cancel)),
                  FilledButton(onPressed: () => Navigator.pop(c, true), child: Text(l.signOut)),
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
            children: [
              Icon(
                sent ? Icons.check_circle : Icons.cloud_off_outlined,
                size: 72,
                color: sent ? AppColors.success : AppColors.warning,
              ),
              const SizedBox(height: 18),
              Text(
                sent ? l.sentTitle : l.queuedTitle,
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
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
