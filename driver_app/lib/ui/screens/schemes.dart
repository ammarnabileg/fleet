import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show DateFormat, NumberFormat;

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../../l10n/app_localizations.dart';
import '../theme.dart';
import '../widgets/common.dart';

String _money(String? amount) =>
    '\u2066${NumberFormat('#,##0.000', 'en').format(double.tryParse(amount ?? '') ?? 0)}\u2069';
String _int(num n) => '\u2066${n.toInt()}\u2069';
String _month(DateTime m) => '\u2066${DateFormat('MM-yyyy', 'en').format(m)}\u2069';

/// His pay scheme this month with its terms. He picks a scheme himself only the first time; after that he asks the
/// office to change it, and once approved his platform's schemes show here for him to pick one, from next month.
class SchemesScreen extends StatefulWidget {
  const SchemesScreen({super.key, required this.state});

  final AppState state;

  @override
  State<SchemesScreen> createState() => _SchemesScreenState();
}

class _SchemesScreenState extends State<SchemesScreen> {
  bool _loading = true;
  String? _kind; // the kind of scheme he looks at while picking

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      await widget.state.loadSchemes();
    } on ApiError {
      // offline: the last view stays
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _askChange() async {
    final l = context.l;
    final note = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(l.schemeChange),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l.schemeChangeBody, style: const TextStyle(height: 1.6)),
            const SizedBox(height: 10),
            TextField(
              key: const Key('scheme-note'),
              controller: note,
              maxLength: 300,
              decoration: InputDecoration(labelText: l.schemeNoteHint),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c, false),
            child: Text(MaterialLocalizations.of(c).cancelButtonLabel),
          ),
          FilledButton(
            key: const Key('scheme-send'),
            onPressed: () => Navigator.pop(c, true),
            child: Text(l.schemeSend),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await widget.state.requestScheme(null, note: note.text.trim().isEmpty ? null : note.text.trim());
      if (!mounted) return;
      setState(() {});
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l.schemeSent)));
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  Future<void> _pick(PayScheme s, DateTime from) async {
    final l = context.l;
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(s.label(widget.state.lang)),
        content: Text(
          l.schemePickConfirm(s.label(widget.state.lang), _month(from)),
          style: const TextStyle(height: 1.6),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c, false),
            child: Text(MaterialLocalizations.of(c).cancelButtonLabel),
          ),
          FilledButton(
            key: const Key('scheme-pick-ok'),
            onPressed: () => Navigator.pop(c, true),
            child: Text(l.schemePick),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await widget.state.chooseScheme(s.id);
      if (!mounted) return;
      setState(() {});
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l.schemePicked)));
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  Future<void> _cancel(SchemeRequest r) async {
    try {
      await widget.state.cancelSchemeRequest(r.id);
      if (mounted) setState(() {});
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final lang = widget.state.lang;
    final v = widget.state.schemes;
    final req = v?.request;
    final current = v?.current;
    final picking = v?.canChoose ?? false;
    final now = DateTime.now();
    // the first time from this month; after the office's leave from the month it approved
    final from = current == null
        ? DateTime(now.year, now.month)
        : (req != null && req.leave && req.status == 'approved'
              ? req.effectiveMonth
              : DateTime(now.year, now.month + 1));
    final all = [
      if (picking)
        for (final s in v?.offered ?? const <PayScheme>[])
          if (s.id != (v?.nextMonth ?? current)?.id) s,
    ];
    final kinds = SchemeKindPicker.of(all);
    final kind = kinds.contains(_kind)
        ? _kind
        : (kinds.contains(current?.payKind) ? current!.payKind : kinds.firstOrNull);
    final shown = kinds.length > 1
        ? [
            for (final s in all)
              if (s.payKind == kind) s,
          ]
        : all;
    // what he last asked, when it still matters (a picked leave shows as his next month's scheme)
    final String? said = req == null || picking
        ? null
        : req.leave
        ? switch (req.status) {
            'pending' => l.schemeChangePending,
            'rejected' => l.schemeChangeRejected(req.adminNote ?? ''),
            _ => null,
          }
        : switch (req.status) {
            'approved' => l.schemeApproved(req.requestedLabel(lang), _month(req.effectiveMonth)),
            'rejected' => l.schemeRejected(req.requestedLabel(lang), req.adminNote ?? ''),
            _ => l.schemePending(req.requestedLabel(lang), _month(req.effectiveMonth)),
          };
    return Scaffold(
      appBar: AppBar(title: Text(l.paySchemes)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            if (v == null && _loading) const Center(child: CircularProgressIndicator()),
            if (v == null && !_loading) Text(l.networkError, style: const TextStyle(color: AppColors.muted)),
            if (said != null) ...[
              Banner2(
                key: const Key('scheme-request'),
                text: said,
                tone: switch (req!.status) {
                  'approved' => BannerTone.success,
                  'rejected' => BannerTone.danger,
                  _ => BannerTone.warn,
                },
              ),
              if (req.pending)
                Align(
                  alignment: AlignmentDirectional.centerEnd,
                  child: TextButton(
                    key: const Key('scheme-cancel'),
                    onPressed: () => _cancel(req),
                    child: Text(l.schemeCancel),
                  ),
                ),
              const SizedBox(height: 8),
            ],
            if (v != null && current != null) ...[
              SectionTitle(l.schemeNow),
              SchemeCard(scheme: current, lang: lang, key: const Key('scheme-current')),
              if (v.nextMonth != null) ...[
                const SizedBox(height: 6),
                Text(l.schemeNextMonth(v.nextMonth!.label(lang)), style: const TextStyle(fontWeight: FontWeight.w600)),
              ],
              if (!picking && !(req?.pending ?? false) && v.offered.isNotEmpty) ...[
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    key: const Key('scheme-change'),
                    onPressed: _askChange,
                    icon: const Icon(Icons.swap_horiz),
                    label: Text(l.schemeChange),
                  ),
                ),
              ],
            ],
            if (v != null && current == null && !picking)
              Text(l.schemeNone, style: const TextStyle(color: AppColors.muted)),
            if (v != null && picking) ...[
              const SizedBox(height: 8),
              Banner2(
                key: const Key('scheme-picking'),
                text: current == null ? l.schemePickFirst : l.schemePickAllowed(_month(from)),
                tone: current == null ? BannerTone.warn : BannerTone.success,
              ),
              const SizedBox(height: 8),
              if (kinds.length > 1)
                SchemeKindPicker(kinds: kinds, value: kind, onChanged: (k) => setState(() => _kind = k)),
              for (final s in shown)
                SchemeCard(
                  scheme: s,
                  lang: lang,
                  action: FilledButton(
                    key: Key('scheme-pick-${s.code}'),
                    onPressed: () => _pick(s, from),
                    child: Text(l.schemePick),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

/// The driver's first choice among his platform's schemes: how he is paid (per order, a fixed salary, by batch); the
/// schemes of that kind follow. Shown when the platform offers more than one kind.
class SchemeKindPicker extends StatelessWidget {
  const SchemeKindPicker({super.key, required this.kinds, required this.value, required this.onChanged});

  final List<String> kinds;
  final String? value;
  final ValueChanged<String> onChanged;

  static List<String> of(Iterable<PayScheme> schemes) => [
    for (final k in const ['per_order', 'fixed_salary', 'batch'])
      if (schemes.any((s) => s.payKind == k)) k,
  ];

  static String label(AppLocalizations l, String kind) => switch (kind) {
    'fixed_salary' => l.schemeKind_fixed_salary,
    'batch' => l.schemeKind_batch,
    _ => l.schemeKind_per_order,
  };

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(l.schemeKindPick, style: const TextStyle(color: AppColors.muted)),
        const SizedBox(height: 6),
        Wrap(
          spacing: 8,
          children: [
            for (final k in kinds)
              ChoiceChip(
                key: Key('scheme-kind-$k'),
                label: Text(label(l, k)),
                selected: value == k,
                onSelected: (_) => onChanged(k),
              ),
          ],
        ),
        const SizedBox(height: 8),
      ],
    );
  }
}

/// A scheme's terms in plain lines: what an order pays, tiers, marks, target, and who pays the expenses.
class SchemeCard extends StatelessWidget {
  const SchemeCard({super.key, required this.scheme, required this.lang, this.action, this.selected, this.onTap});

  final PayScheme scheme;
  final String lang;
  final Widget? action;
  final bool? selected; // a choice in the registration
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final s = scheme;
    final about = s.about(lang);
    return Card(
      shape: selected == true
          ? RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
              side: const BorderSide(color: AppColors.primary, width: 2),
            )
          : null,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  if (selected != null) ...[
                    Icon(
                      selected! ? Icons.radio_button_checked : Icons.radio_button_unchecked,
                      color: selected! ? AppColors.primary : AppColors.muted,
                      size: 20,
                    ),
                    const SizedBox(width: 8),
                  ],
                  Expanded(
                    child: Text(s.label(lang), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                  ),
                ],
              ),
              if (about != null && about.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(about, style: const TextStyle(color: AppColors.muted)),
              ],
              const SizedBox(height: 6),
              for (final line in terms(l, s, lang)) Padding(padding: const EdgeInsets.only(top: 3), child: Text(line)),
              if (action != null) ...[const SizedBox(height: 8), action!],
            ],
          ),
        ),
      ),
    );
  }

  static List<String> terms(AppLocalizations l, PayScheme s, String lang) {
    if (s.blocks != null) return blockTerms(l, s.blocks!, lang);
    if (s.calculator == 'platform_rates') return [l.schemePlatformRates];
    final out = <String>[];
    if (s.calculator == 'per_order') out.add(l.schemePerOrder(_money(s.perOrder)));
    if (s.calculator == 'batch') {
      out.add(l.schemeBatchRates);
      for (final b in s.stepsOf('batch_rate')) {
        out.add('• ${l.schemeBatchRow(_int(b.threshold), _money(b.amount))}');
      }
    }
    if (s.calculator == 'tiered_target') {
      out.add(l.schemePerOrder(_money(s.perOrder)));
      final reduce = s.stepsOf('marks_reduce').firstOrNull;
      out.add(
        reduce == null
            ? l.schemeReducedStar(_money(s.reducedRate))
            : l.schemeReduced(_money(s.reducedRate), _int(reduce.threshold)),
      );
      if (!s.bonusWhenReduced && s.stepsOf('tier_bonus').isNotEmpty) out.add(l.schemeReducedLoses);
      final tiers = s.stepsOf('tier_bonus');
      if (tiers.isNotEmpty) {
        out.add(l.schemeTiers);
        for (final t in tiers) {
          out.add('• ${l.schemeTierRow(_int(t.threshold), _money(t.amount))}');
        }
      }
      final marks = s.stepsOf('marks_deduction');
      if (marks.isNotEmpty) {
        out.add(l.schemeMarks);
        for (final m in marks) {
          out.add('• ${l.schemeMarkRow(_int(m.threshold), _money(m.amount))}');
        }
      }
    }
    out.add(l.schemeTarget(_int(s.targetOrders), _int(s.requiredValidDays)));
    out.add(s.missingOrderRate == null ? l.schemeNoMissing : l.schemeMissing(_money(s.missingOrderRate)));
    out.add(
      s.companyCovers.isEmpty
          ? l.schemeCoversNone
          : l.schemeCovers(
              [
                for (final c in s.companyCovers)
                  switch (c) {
                    'maintenance' => l.expense_maintenance,
                    'housing' => l.expense_housing,
                    'gas' => l.expense_gas,
                    'sim' || 'phone' => l.expense_sim,
                    _ => c,
                  },
              ].join(lang == 'ar' ? '، ' : ', '),
            ),
    );
    return out;
  }

  /// A scheme written as rule blocks, in the driver's words: what he earns, the target, the bonuses, the red marks
  /// and the star day, the platform's amounts, and who pays the expenses.
  static List<String> blockTerms(AppLocalizations l, List<Map<String, dynamic>> blocks, String lang) {
    final out = <String>[];
    Map<String, dynamic> p(Map<String, dynamic> b) => Map<String, dynamic>.from(b['params'] as Map? ?? const {});
    List<Map<String, dynamic>> cond(Map<String, dynamic> b) => [
      for (final c in b['condition'] as List? ?? const []) Map<String, dynamic>.from(c as Map),
    ];
    List<Map<String, dynamic>> rows(Object? v) => [
      for (final r in v as List? ?? const []) Map<String, dynamic>.from(r as Map),
    ];
    final company = <String>[], driver = <String>[];
    String expense(String kind) => switch (kind) {
      'maintenance' => l.expense_maintenance,
      'housing' => l.expense_housing,
      'gas' => l.expense_gas,
      'phone' || 'sim' => l.expense_sim,
      _ => kind,
    };
    for (final b in blocks) {
      final x = p(b), c = cond(b), type = b['type'] as String? ?? '';
      // a price that applies only when the month went wrong (a star day missed, too many marks)
      final starDay = c.any((y) => y['fact'] == 'month_invalid' && y['op'] == 'is_true');
      final manyMarks = c.where((y) => y['fact'] == 'marks' && y['op'] == 'gt').firstOrNull;
      if ((type == 'per_order' || type == 'price_change') && (starDay || manyMarks != null)) {
        out.add(
          starDay
              ? l.schemeReducedStarDay(_money('${x['rate']}'))
              : l.schemeReducedMarks(_int(manyMarks!['value'] as num), _money('${x['rate']}')),
        );
        continue;
      }
      switch (type) {
        case 'fixed_salary':
          out.add(x['mode'] == 'contract' ? l.schemeContractSalary : l.schemeFixedSalary(_money('${x['amount']}')));
        case 'per_order':
          if ((x['source'] ?? 'orders') == 'orders') out.add(l.schemePerOrder(_money('${x['rate']}')));
        case 'batch_rate':
          out.add(l.schemeBatchRates);
          for (final r in rows(x['rates'])) {
            out.add('• ${l.schemeBatchRow(_int(r['batch'] as num), _money('${r['rate']}'))}');
          }
        case 'tiered_rate':
          out.add(l.schemeTierRates);
          for (final r in rows(x['tiers'])) {
            out.add('• ${l.schemeTierRateRow(_int(r['from'] as num), _money('${r['rate']}'))}');
          }
        case 'target_overage':
          out.add(l.schemeOverTarget(_int(x['threshold'] as num), _money('${x['rate']}')));
          if (x['below_rate'] != null) out.add(l.schemeUnderTarget(_money('${x['below_rate']}')));
        case 'missing_orders':
          out.add(l.schemeMissing(_money('${x['rate']}')));
        case 'tier_bonus':
          out.add(l.schemeTiers);
          for (final r in rows(x['tiers'])) {
            out.add('• ${l.schemeTierRow(_int(r['from'] as num), _money('${r['amount']}'))}');
          }
        case 'monthly_bonus':
          out.add(l.schemeMonthlyBonus(_money('${x['amount']}')));
        case 'attendance_marks':
          if (x['mode'] == 'per_mark') {
            out.add(l.schemeMarkEach(_money('${x['amount']}')));
          } else {
            final table = rows(x['table']);
            out.add(l.schemeMarksTable);
            if (table.isNotEmpty && (table.first['from'] as num) > 1) {
              out.add('• ${l.schemeMarksFree(_int((table.first['from'] as num) - 1))}');
            }
            for (final r in table) {
              out.add('• ${l.schemeMarksRow(_int(r['from'] as num), _money('${r['amount']}'))}');
            }
          }
        case 'required_days':
          out.add(l.schemeRequiredDays(_int(x['days'] as num)));
        case 'platform_amounts':
          out.add(l.schemePlatformAmounts);
        case 'expense':
          (x['responsibility'] == 'company' ? company : driver).add(expense('${x['kind']}'));
      }
    }
    final sep = lang == 'ar' ? '، ' : ', ';
    if (company.isNotEmpty) out.add(l.schemeCovers(company.join(sep)));
    if (driver.isNotEmpty) out.add(l.schemeDriverPays(driver.join(sep)));
    if (company.isEmpty && driver.isEmpty) out.add(l.schemeCoversNone);
    return out;
  }
}
