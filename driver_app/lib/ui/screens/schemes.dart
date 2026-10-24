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

/// His pay scheme this month, the other schemes his platform offers with their terms, and a request to move to one of
/// them from next month (the office decides).
class SchemesScreen extends StatefulWidget {
  const SchemesScreen({super.key, required this.state});

  final AppState state;

  @override
  State<SchemesScreen> createState() => _SchemesScreenState();
}

class _SchemesScreenState extends State<SchemesScreen> {
  bool _loading = true;

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

  Future<void> _ask(PayScheme s) async {
    final l = context.l;
    final note = TextEditingController();
    final next = DateTime(DateTime.now().year, DateTime.now().month + 1);
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(s.label(widget.state.lang)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(l.schemeAskBody(s.label(widget.state.lang), _month(next)), style: const TextStyle(height: 1.6)),
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
      await widget.state.requestScheme(s.id, note: note.text.trim().isEmpty ? null : note.text.trim());
      if (!mounted) return;
      setState(() {});
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l.schemeSent)));
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
    final others = [
      for (final s in v?.offered ?? const <PayScheme>[])
        if (s.id != current?.id) s,
    ];
    return Scaffold(
      appBar: AppBar(title: Text(l.paySchemes)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(l.schemesIntro, style: const TextStyle(color: AppColors.muted, height: 1.6)),
            const SizedBox(height: 12),
            if (v == null && _loading) const Center(child: CircularProgressIndicator()),
            if (v == null && !_loading) Text(l.networkError, style: const TextStyle(color: AppColors.muted)),
            if (req != null) ...[
              Banner2(
                key: const Key('scheme-request'),
                text: switch (req.status) {
                  'approved' => l.schemeApproved(req.requestedLabel(lang), _month(req.effectiveMonth)),
                  'rejected' => l.schemeRejected(req.requestedLabel(lang), req.adminNote ?? ''),
                  _ => l.schemePending(req.requestedLabel(lang), _month(req.effectiveMonth)),
                },
                tone: switch (req.status) {
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
            if (v != null) ...[
              SectionTitle(l.schemeNow),
              if (current != null)
                SchemeCard(scheme: current, lang: lang, key: const Key('scheme-current'))
              else
                Text(l.schemeNone, style: const TextStyle(color: AppColors.muted)),
              if (v.nextMonth != null) ...[
                const SizedBox(height: 6),
                Text(l.schemeNextMonth(v.nextMonth!.label(lang)), style: const TextStyle(fontWeight: FontWeight.w600)),
              ],
              if (others.isNotEmpty) SectionTitle(l.schemeOthers),
              for (final s in others)
                SchemeCard(
                  scheme: s,
                  lang: lang,
                  action: req != null && req.pending
                      ? null
                      : OutlinedButton(
                          key: Key('scheme-ask-${s.code}'),
                          onPressed: () => _ask(s),
                          child: Text(l.schemeAsk),
                        ),
                ),
            ],
          ],
        ),
      ),
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
                    'sim' => l.expense_sim,
                    _ => c,
                  },
              ].join(lang == 'ar' ? '، ' : ', '),
            ),
    );
    return out;
  }
}
