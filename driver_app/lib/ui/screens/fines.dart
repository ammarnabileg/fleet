import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show DateFormat, NumberFormat;

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../../l10n/app_localizations.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'home.dart';

(String, BannerTone) fineStatus(AppLocalizations l, String status) => switch (status) {
  'charged' => (l.fineStatus_charged, BannerTone.danger),
  'company' => (l.fineStatus_company, BannerTone.success),
  _ => (l.fineStatus_open, BannerTone.warn),
};

String _money(String amount) => '\u2066${NumberFormat('#,##0.000', 'en').format(double.tryParse(amount) ?? 0)}\u2069';

/// The traffic fines on the vehicles the driver held at the time (from the custody log), whether the company bears
/// them or they are deducted from the salary, and the monthly installments.
class FinesScreen extends StatefulWidget {
  const FinesScreen({super.key, required this.state});

  final AppState state;

  @override
  State<FinesScreen> createState() => _FinesScreenState();
}

class _FinesScreenState extends State<FinesScreen> {
  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      await widget.state.loadFines();
    } on ApiError {
      // offline: the last list stays
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final fines = widget.state.fines;
    return Scaffold(
      appBar: AppBar(title: Text(l.finesTitle)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(l.finesIntro, style: const TextStyle(color: AppColors.muted, height: 1.6)),
            const SizedBox(height: 12),
            if (fines.isEmpty) Text(l.finesNone, style: const TextStyle(color: AppColors.muted)),
            for (final f in fines) FineTile(fine: f),
          ],
        ),
      ),
    );
  }
}

class FineTile extends StatelessWidget {
  const FineTile({super.key, required this.fine});

  final Fine fine;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final f = fine;
    final (label, tone) = fineStatus(l, f.status);
    final d = f.deduction;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${f.violation} · ${_money(f.amount)} ${l.kwd}',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                Pill(label, tone: tone),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              ['\u2066${f.plate}\u2069', when(context, f.occurredAt), ?f.location].join(' · '),
              style: const TextStyle(color: AppColors.muted),
            ),
            if (d != null) ...[
              const SizedBox(height: 6),
              Text(l.accDeduction(_money(d.total), '${d.installments}'), key: Key('fine-deduction-${f.number}')),
              for (final s in d.schedule)
                Text(
                  l.accInstallment(DateFormat('MM-yyyy', 'en').format(s.month), _money(s.amount)),
                  style: const TextStyle(color: AppColors.muted),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
