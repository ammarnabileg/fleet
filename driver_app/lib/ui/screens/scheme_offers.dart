import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show NumberFormat;

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../../l10n/app_localizations.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'schemes.dart';

String _money(Object? v) {
  final n = v is num ? v.toDouble() : double.tryParse('$v') ?? 0;
  return '\u2066${NumberFormat(n == n.roundToDouble() && n >= 10 ? '#,##0' : '#,##0.000', 'en').format(n)}\u2069';
}

/// What a scheme card shows at a glance: its price, its target with the price of an order over or short of it, its
/// bonus tiers and who pays which expense. The full terms stay under «Terms and details».
class OfferFacts {
  OfferFacts._();

  String? price; // the headline: the salary, or the price of an order (a range for batches)
  String priceUnit = 'order'; // month | order | batch
  int? target;
  String? over; // + per order above the target
  String? under; // − per order short of it
  final bonus = <(int, String)>[]; // (orders, amount), lowest first
  final covers = <String>[]; // maintenance | housing | gas | sim: paid by the company
  final yours = <String>[]; // paid by the driver

  factory OfferFacts.of(PayScheme s) {
    final f = OfferFacts._();
    final blocks = s.blocks;
    if (blocks == null) {
      // a scheme from the earlier calculators
      f.price = s.perOrder;
      f.target = s.targetOrders > 0 ? s.targetOrders : null;
      f.under = s.missingOrderRate;
      for (final t in s.stepsOf('tier_bonus')) {
        f.bonus.add((t.threshold.toInt(), t.amount ?? '0'));
      }
      f.covers.addAll(s.companyCovers);
      return f;
    }
    Map<String, dynamic> p(Map<String, dynamic> b) => Map<String, dynamic>.from(b['params'] as Map? ?? const {});
    bool conditional(Map<String, dynamic> b) => (b['condition'] as List? ?? const []).isNotEmpty;
    for (final b in blocks) {
      final x = p(b);
      switch (b['type']) {
        case 'fixed_salary':
          if (x['mode'] != 'contract') {
            f.price = '${x['amount']}';
            f.priceUnit = 'month';
          }
        case 'per_order' when !conditional(b):
          f.price ??= '${x['rate']}';
        case 'batch_rate':
          final rates = [
            for (final r in x['rates'] as List? ?? const []) double.tryParse('${(r as Map)['rate']}') ?? 0,
          ];
          if (rates.isNotEmpty) {
            rates.sort();
            f.price = '${rates.first}–${rates.last}';
            f.priceUnit = 'batch';
          }
        case 'target_overage':
          f.target = (x['threshold'] as num?)?.toInt();
          f.over = x['rate']?.toString();
          if (x['below_rate'] != null) f.under = '${x['below_rate']}';
        case 'missing_orders':
          f.target ??= (x['target'] as num?)?.toInt();
          f.under = x['rate']?.toString();
        case 'tier_bonus':
          for (final t in x['tiers'] as List? ?? const []) {
            final m = Map<String, dynamic>.from(t as Map);
            f.bonus.add(((m['from'] as num).toInt(), '${m['amount']}'));
          }
        case 'expense':
          final kind = x['kind'] == 'phone' ? 'sim' : '${x['kind']}';
          (x['responsibility'] == 'company' ? f.covers : f.yours).add(kind);
      }
    }
    f.bonus.sort((a, b) => a.$1.compareTo(b.$1));
    return f;
  }
}

/// After he picks his company: its schemes as cards, he picks one, and both go to the office in one request.
class SchemeOffersScreen extends StatefulWidget {
  const SchemeOffersScreen({super.key, required this.state, required this.company});

  final AppState state;
  final Company company;

  @override
  State<SchemeOffersScreen> createState() => _SchemeOffersScreenState();
}

class _SchemeOffersScreenState extends State<SchemeOffersScreen> {
  List<PayScheme>? _schemes;
  Object? _error;
  String? _picked;
  String? _kind;
  bool _busy = false;
  final _note = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final all = await widget.state.companySchemes(widget.company.id);
      if (mounted) {
        setState(() {
          _schemes = all;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  Future<void> _send() async {
    setState(() => _busy = true);
    try {
      final note = _note.text.trim();
      await widget.state.chooseCompany(widget.company.id, schemeId: _picked, note: note.isEmpty ? null : note);
      if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
    } on ApiError catch (e) {
      if (mounted) showError(context, widget.state, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final lang = widget.state.lang;
    final all = _schemes;
    final kinds = all == null ? const <String>[] : SchemeKindPicker.of(all);
    final kind = kinds.contains(_kind) ? _kind : kinds.firstOrNull;
    final shown = all == null
        ? const <PayScheme>[]
        : kinds.length > 1
        ? [
            for (final s in all)
              if (s.payKind == kind) s,
          ]
        : all;
    final ready = all != null && (all.isEmpty || _picked != null);
    return Scaffold(
      appBar: AppBar(title: Text(widget.company.nameIn(lang))),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          children: [
            Text(
              l.offerTitle,
              key: const Key('offers-title'),
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 6),
            Text(
              l.offerSub,
              textAlign: TextAlign.center,
              style: const TextStyle(color: AppColors.muted, height: 1.5),
            ),
            const SizedBox(height: 16),
            if (all == null && _error == null) const Center(child: CircularProgressIndicator()),
            if (_error != null) Banner2(text: l.networkError, tone: BannerTone.danger),
            if (all != null && all.isEmpty)
              Banner2(key: const Key('offers-none'), text: l.offerNone, tone: BannerTone.warn),
            if (kinds.length > 1) ...[
              SchemeKindPicker(kinds: kinds, value: kind, onChanged: (k) => setState(() => _kind = k)),
              const SizedBox(height: 4),
            ],
            for (final s in shown)
              Padding(
                padding: const EdgeInsets.only(bottom: 14),
                child: SchemeOfferCard(
                  key: Key('offer-${s.code}'),
                  scheme: s,
                  company: widget.company.nameIn(lang),
                  lang: lang,
                  selected: _picked == s.id,
                  onPick: _busy ? null : () => setState(() => _picked = s.id),
                ),
              ),
            if (all != null) ...[
              TextField(
                key: const Key('company-note'),
                controller: _note,
                maxLength: 500,
                decoration: InputDecoration(labelText: l.companyNote),
              ),
              const SizedBox(height: 8),
              FilledButton(
                key: const Key('company-send'),
                onPressed: ready && !_busy ? _send : null,
                child: _busy
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                    : Text(ready ? l.companySend : l.offerPickOne),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// One scheme as the driver compares them: kind and name, the headline price, the target with what an order over
/// or short of it is worth, the bonus tiers, who pays which expense, the full terms folded, and the pick button.
class SchemeOfferCard extends StatelessWidget {
  const SchemeOfferCard({
    super.key,
    required this.scheme,
    required this.company,
    required this.lang,
    required this.selected,
    this.onPick,
  });

  final PayScheme scheme;
  final String company;
  final String lang;
  final bool selected;
  final VoidCallback? onPick;

  static const _green = AppColors.successFill;
  static const _icons = {
    'maintenance': Icons.build_outlined,
    'housing': Icons.home_outlined,
    'gas': Icons.local_gas_station_outlined,
    'sim': Icons.sim_card_outlined,
  };

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final s = scheme;
    final f = OfferFacts.of(s);
    final about = s.about(lang);
    final kindName = switch (s.payKind) {
      'fixed_salary' => l.schemeKind_fixed_salary,
      'batch' => l.schemeKind_batch,
      _ => l.schemeKind_per_order,
    };
    final unit = switch (f.priceUnit) {
      'month' => l.offerPerMonth,
      'batch' => l.offerByBatch,
      _ => l.offerPerOrder,
    };
    Widget stat(String value, String label, {Color? color}) => Expanded(
      child: Column(
        children: [
          Text(
            value,
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: color ?? AppColors.text),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 12, color: AppColors.muted),
          ),
        ],
      ),
    );
    final stats = [
      if (f.target != null) stat('\u2066${f.target}\u2069', l.offerTarget),
      if (f.over != null) stat('+${_money(f.over)} ${l.offerKwd}', l.offerOver, color: _green),
      if (f.under != null) stat('−${_money(f.under)} ${l.offerKwd}', l.offerUnder, color: AppColors.danger),
    ];
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        boxShadow: const [BoxShadow(color: Color(0x0F0B1F3A), blurRadius: 12, offset: Offset(0, 4))],
      ),
      child: Material(
        color: AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: BorderSide(color: selected ? _green : AppColors.border, width: selected ? 2 : 1),
        ),
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(color: AppColors.successSoft, borderRadius: BorderRadius.circular(10)),
                    child: const Icon(Icons.work_outline, color: _green, size: 20),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(s.label(lang), style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w800)),
                      ],
                    ),
                  ),
                  if (selected) const Icon(Icons.check_circle, color: _green, size: 30, key: Key('offer-check')),
                ],
              ),
              const SizedBox(height: 8),
              Align(alignment: AlignmentDirectional.centerStart, child: _Chip(kindName)),
              if (f.price != null) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  decoration: BoxDecoration(
                    color: selected ? AppColors.successSoft : AppColors.sunken,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Column(
                    children: [
                      Text.rich(
                        TextSpan(
                          children: [
                            TextSpan(
                              text: f.price!.contains('–')
                                  ? f.price!.split('–').map(_money).join(' – ')
                                  : _money(f.price),
                              style: const TextStyle(fontSize: 34, fontWeight: FontWeight.w900),
                            ),
                            TextSpan(
                              text: '  ${l.offerKwd}',
                              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                            ),
                          ],
                        ),
                        key: const Key('offer-price'),
                      ),
                      Text(unit, style: const TextStyle(color: AppColors.muted)),
                    ],
                  ),
                ),
              ],
              if (stats.isNotEmpty) ...[
                const SizedBox(height: 10),
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  decoration: BoxDecoration(color: AppColors.sunken, borderRadius: BorderRadius.circular(14)),
                  child: Row(children: stats),
                ),
              ],
              if (f.bonus.isNotEmpty) ...[
                const SizedBox(height: 14),
                Text(l.offerBonus, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                const SizedBox(height: 6),
                Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: AppColors.border),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Column(
                    children: [
                      for (final (i, (orders, amount)) in f.bonus.indexed)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                          decoration: BoxDecoration(
                            border: i == 0 ? null : const Border(top: BorderSide(color: AppColors.border)),
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: Text(
                                  l.offerOrders('\u2066$orders\u2069'),
                                  style: const TextStyle(fontWeight: FontWeight.w700),
                                ),
                              ),
                              Text(
                                '${_money(amount)} ${l.offerKwd}',
                                style: const TextStyle(color: _green, fontWeight: FontWeight.w800),
                              ),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 4),
                Text(l.offerBonusTop, style: const TextStyle(fontSize: 12, color: AppColors.muted)),
              ],
              if (f.covers.isNotEmpty) ...[
                const SizedBox(height: 14),
                Text(l.offerCovers, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 15)),
                const SizedBox(height: 8),
                Row(
                  children: [
                    for (final c in f.covers)
                      Expanded(
                        child: Column(
                          children: [
                            CircleAvatar(
                              radius: 20,
                              backgroundColor: AppColors.successSoft,
                              child: Icon(_icons[c] ?? Icons.check, color: _green, size: 20),
                            ),
                            const SizedBox(height: 4),
                            Text(_expense(l, c), style: const TextStyle(fontSize: 12)),
                          ],
                        ),
                      ),
                  ],
                ),
              ],
              if (f.yours.isNotEmpty) ...[
                const SizedBox(height: 10),
                Text(
                  '${l.offerYouPay}: ${f.yours.map((c) => _expense(l, c)).join('، ')}',
                  style: const TextStyle(fontSize: 13, color: AppColors.text3),
                ),
              ],
              const SizedBox(height: 6),
              Theme(
                data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  key: Key('offer-terms-${s.code}'),
                  tilePadding: EdgeInsets.zero,
                  childrenPadding: const EdgeInsetsDirectional.only(bottom: 8),
                  expandedCrossAxisAlignment: CrossAxisAlignment.start,
                  title: Text(l.offerTerms, style: const TextStyle(fontWeight: FontWeight.w700)),
                  children: [
                    if (about != null && about.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: Text(about, style: const TextStyle(color: AppColors.text3, height: 1.6)),
                      ),
                    for (final line in SchemeCard.terms(l, s, lang))
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(line, style: const TextStyle(height: 1.5)),
                      ),
                  ],
                ),
              ),
              selected
                  ? FilledButton.icon(
                      key: Key('offer-picked-${s.code}'),
                      onPressed: onPick,
                      style: FilledButton.styleFrom(backgroundColor: AppColors.successSoft, foregroundColor: _green),
                      icon: const Icon(Icons.check_circle),
                      label: Text(l.offerSelected),
                    )
                  : FilledButton(
                      key: Key('offer-pick-${s.code}'),
                      onPressed: onPick,
                      style: FilledButton.styleFrom(backgroundColor: _green),
                      child: Text(l.offerSelect),
                    ),
            ],
          ),
        ),
      ),
    );
  }

  static String _expense(AppLocalizations l, String kind) => switch (kind) {
    'maintenance' => l.expense_maintenance,
    'housing' => l.expense_housing,
    'gas' => l.expense_gas,
    'sim' => l.expense_sim,
    _ => kind,
  };
}

class _Chip extends StatelessWidget {
  const _Chip(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
    decoration: BoxDecoration(color: AppColors.successSoft, borderRadius: BorderRadius.circular(20)),
    child: Text(
      text,
      style: const TextStyle(fontSize: 12, color: AppColors.success, fontWeight: FontWeight.w600),
    ),
  );
}
