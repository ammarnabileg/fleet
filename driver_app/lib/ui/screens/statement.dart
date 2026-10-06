import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../../l10n/app_localizations.dart';
import '../photos.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'home.dart';

const _maxShots = 6;

String _month(String iso) => '\u2066${iso.substring(0, 7)}\u2069';

(String, BannerTone) statementStatus(AppLocalizations l, String status) => switch (status) {
  'approved' => (l.statementStatus_approved, BannerTone.success),
  'rejected' => (l.statementStatus_rejected, BannerTone.danger),
  _ => (l.statementStatus_submitted, BannerTone.warn),
};

/// The month as the platform counted it: screenshots of the platform app's monthly summary (from the gallery) and the
/// figures the driver reads on them (valid days, orders, hours: what his platform asks for). The office compares
/// them with the screenshots before the payroll; what it approves is what the salary uses.
class StatementScreen extends StatefulWidget {
  const StatementScreen({super.key, required this.state});

  final AppState state;

  @override
  State<StatementScreen> createState() => _StatementScreenState();
}

class _StatementScreenState extends State<StatementScreen> {
  final _form = GlobalKey<FormState>();
  final _fields = {
    for (final f in ['valid_days', 'orders', 'hours']) f: TextEditingController(),
  };
  final _shots = <TakenPhoto>[];
  String? month;
  bool loaded = false;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      await widget.state.loadStatements();
    } on ApiError {
      // offline: the last state stays
    }
    if (!mounted) return;
    final s = widget.state.statements;
    setState(() {
      loaded = true;
      month = s != null && s.months.isNotEmpty ? (s.months.contains(month) ? month : s.months.last) : null;
    });
  }

  String _label(AppLocalizations l, String field) => switch (field) {
    'valid_days' => l.validDays,
    'orders' => l.ordersTotal,
    _ => l.hoursTotal,
  };

  Future<void> _send() async {
    final l = context.l;
    if (!_form.currentState!.validate()) return;
    if (_shots.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l.statementShotRequired)));
      return;
    }
    try {
      int? number(String f) => _fields[f]!.text.trim().isEmpty ? null : int.parse(_fields[f]!.text.trim());
      final r = await widget.state.sendStatement(
        month: month!,
        validDays: number('valid_days'),
        orders: number('orders'),
        hours: _fields['hours']!.text.trim().isEmpty ? null : _fields['hours']!.text.trim(),
        screenshotPaths: [for (final s in _shots) s.path],
      );
      if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(result: r)));
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final s = widget.state.statements;
    final sent = s?.statements ?? const <PlatformStatement>[];
    final already = {for (final x in sent.where((x) => x.status != 'rejected')) x.month};
    final open = (s?.months ?? const <String>[]).where((m) => !already.contains(m)).toList();
    if (month != null && !open.contains(month)) month = open.isEmpty ? null : open.last;
    return Scaffold(
      appBar: AppBar(title: Text(l.statementTitle)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              if (!loaded)
                const Center(child: CircularProgressIndicator())
              else if (s == null || s.platform == null)
                Banner2(text: l.statementNoPlatform, tone: BannerTone.warn)
              else ...[
                Text(
                  l.statementIntro(s.platformName(widget.state.lang)),
                  style: const TextStyle(color: AppColors.muted, height: 1.6),
                ),
                const SizedBox(height: 16),
                if (open.isEmpty)
                  Banner2(text: l.statementNoMonth, tone: BannerTone.success, icon: Icons.check_circle_outline)
                else ...[
                  Text(l.statementMonth, style: const TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 8),
                  SegmentedButton<String>(
                    key: const Key('statement-month'),
                    segments: [for (final m in open) ButtonSegment(value: m, label: Text(_month(m)))],
                    selected: {month!},
                    onSelectionChanged: (v) => setState(() => month = v.first),
                  ),
                  const SizedBox(height: 16),
                  for (final f in s.driverFields) ...[
                    TextFormField(
                      key: Key('statement-$f'),
                      controller: _fields[f],
                      keyboardType: f == 'hours'
                          ? const TextInputType.numberWithOptions(decimal: true)
                          : TextInputType.number,
                      textDirection: TextDirection.ltr,
                      inputFormatters: [
                        f == 'hours'
                            ? FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))
                            : FilteringTextInputFormatter.digitsOnly,
                        LengthLimitingTextInputFormatter(f == 'orders' ? 5 : 6),
                      ],
                      decoration: InputDecoration(labelText: _label(l, f)),
                      validator: (v) {
                        final t = (v ?? '').trim();
                        if (t.isEmpty) return l.required;
                        if (f == 'valid_days' && (int.tryParse(t) ?? 99) > 31) return l.required;
                        if (f == 'hours' && double.tryParse(t) == null) return l.required;
                        return null;
                      },
                    ),
                    const SizedBox(height: 12),
                  ],
                  Text(l.statementShots, style: const TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (var i = 0; i < _shots.length; i++)
                        SizedBox(
                          width: 104,
                          child: PhotoTile(
                            label: '${i + 1}',
                            path: _shots[i].path,
                            onTap: () => setState(() => _shots.removeAt(i)),
                          ),
                        ),
                      if (_shots.length < _maxShots)
                        SizedBox(
                          width: 104,
                          child: PhotoTile(
                            key: const Key('statement-shot'),
                            label: l.addShot,
                            path: null,
                            onTap: () async {
                              final p = await Photos.gallery();
                              if (p != null) setState(() => _shots.add(p));
                            },
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 22),
                  BusyButton(key: const Key('send-statement'), label: l.send, icon: Icons.send, onPressed: _send),
                ],
                if (sent.isNotEmpty) ...[
                  SectionTitle(l.statementHistory),
                  for (final x in sent) StatementTile(statement: x),
                ],
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class StatementTile extends StatelessWidget {
  const StatementTile({super.key, required this.statement});

  final PlatformStatement statement;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final x = statement;
    final (label, tone) = statementStatus(l, x.status);
    final declared = x.declared['valid_days'];
    return Card(
      child: ListTile(
        title: Text(_month(x.month)),
        subtitle: Text(
          [
            if (declared != null) l.statementSentDays('$declared'),
            if (x.status == 'approved' && x.validDays != null) l.statementApprovedDays('${x.validDays}'),
            if (x.reviewNote != null) x.reviewNote!,
          ].join('\n'),
        ),
        isThreeLine: x.reviewNote != null,
        trailing: Pill(label, tone: tone),
      ),
    );
  }
}

/// The driver's approved payslips, each in the rows of his platform's salary sheet.
class PayslipsScreen extends StatefulWidget {
  const PayslipsScreen({super.key, required this.state});

  final AppState state;

  @override
  State<PayslipsScreen> createState() => _PayslipsScreenState();
}

class _PayslipsScreenState extends State<PayslipsScreen> {
  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      await widget.state.loadPayslips();
    } on ApiError {
      // offline: the last list stays
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final slips = widget.state.payslips;
    return Scaffold(
      appBar: AppBar(title: Text(l.payslipsTitle)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            if (slips.isEmpty) Text(l.payslipsNone, style: const TextStyle(color: AppColors.muted)),
            for (final p in slips) PayslipCard(payslip: p),
          ],
        ),
      ),
    );
  }
}

class PayslipCard extends StatelessWidget {
  const PayslipCard({super.key, required this.payslip});

  final Payslip payslip;

  static final _amount = RegExp(r'^-?\d+\.\d{3}$');

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final p = payslip;
    String show(String? v) => v == null || v.isEmpty ? '—' : (_amount.hasMatch(v) ? money(v, l.kwd) : '\u2066$v\u2069');
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(_month(p.month), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                ),
                Pill(
                  p.status == 'paid' ? l.payslipStatus_paid : l.payslipStatus_approved,
                  tone: p.status == 'paid' ? BannerTone.success : BannerTone.info,
                ),
              ],
            ),
            const Divider(),
            if (p.breakdown.isNotEmpty) ...[
              Text(
                l.payslipScheme(p.scheme(Localizations.localeOf(context).languageCode) ?? ''),
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 4),
              for (final b in p.breakdown) PayItemRow(item: b),
              if (p.rows.any((r) => r.code != 'net')) const Divider(),
            ],
            for (final r in p.rows.where((r) => r.code != 'net'))
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(r.header, style: const TextStyle(color: AppColors.muted)),
                    ),
                    Text(show(r.value)),
                  ],
                ),
              ),
            const Divider(),
            Row(
              children: [
                Expanded(
                  child: Text(l.payslipNet, style: const TextStyle(fontWeight: FontWeight.w700)),
                ),
                Text(
                  money(p.net, l.kwd),
                  key: const Key('payslip-net'),
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// One item of the scheme's month on the payslip: what it is, why (orders × rate, the tier reached, …), and the amount.
class PayItemRow extends StatelessWidget {
  const PayItemRow({super.key, required this.item});

  final PayItem item;

  static String _n(Object? v) => '\u2066${v ?? ''}\u2069';

  static String why(AppLocalizations l, PayItem b) {
    final w = b.why;
    return switch (b.code) {
      'orders_pay' => [
        l.payWhyOrders(_n(w['orders']), _n(w['rate'])),
        if (w['batch_level'] != null) l.payWhyBatch(_n(w['batch_level'])),
        if (w['reduced_by'] == 'star_day') l.payWhyReducedStar,
        if (w['reduced_by'] == 'marks') l.payWhyReducedMarks,
      ].join(' · '),
      'tier_bonus' => l.payWhyTier(_n(w['orders']), _n(w['from'])),
      'missing_target' => l.payWhyMissing(_n(w['missing']), _n(w['target']), _n(w['rate'])),
      'marks_deduction' => l.payWhyMarks(_n(w['marks'])),
      'uncovered_penalty' => l.payWhyUncovered,
      _ => '',
    };
  }

  static String label(AppLocalizations l, String code) => switch (code) {
    'orders_pay' => l.payItem_orders_pay,
    'tier_bonus' => l.payItem_tier_bonus,
    'missing_target' => l.payItem_missing_target,
    'marks_deduction' => l.payItem_marks_deduction,
    'uncovered_penalty' => l.payItem_uncovered_penalty,
    _ => code,
  };

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final info = item.code == 'uncovered_penalty'; // shown, not deducted
    final negative = item.amount.startsWith('-');
    return Padding(
      key: Key('pay-item-${item.code}'),
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label(l, item.code)),
                Text(why(l, item), style: const TextStyle(color: AppColors.muted, fontSize: 13)),
              ],
            ),
          ),
          Text(
            money(item.amount, l.kwd),
            style: TextStyle(color: info ? AppColors.muted : (negative ? AppColors.danger : null)),
          ),
        ],
      ),
    );
  }
}
