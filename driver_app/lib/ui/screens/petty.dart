import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart' show DateFormat;

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../../l10n/app_localizations.dart';
import '../photos.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'home.dart';

final _amount = RegExp(r'^\d{1,9}(\.\d{1,3})?$');

String _dmy(String ymd) {
  final d = DateTime.tryParse(ymd);
  return '\u2066${d == null ? ymd : DateFormat('dd-MM-yyyy', 'en').format(d)}\u2069';
}

/// His petty cash custody (the office funds it from a branch treasury): the balance big, what he can still spend,
/// «spend from the custody» (the amount, the expense type, the invoice's camera photo, its date, a note), and its
/// movements: funded, given back, and his spending with its status (waiting, approved, rejected with the reason).
/// Spending goes through the outbox: offline it is queued, and shown as such until it is sent.
class PettyScreen extends StatefulWidget {
  const PettyScreen({super.key, required this.state});

  final AppState state;

  @override
  State<PettyScreen> createState() => _PettyScreenState();
}

class _PettyScreenState extends State<PettyScreen> {
  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      await widget.state.loadPetty();
    } on ApiError {
      // offline: the last answer stays
    }
    await widget.state.reloadLocal();
    if (mounted) setState(() {});
  }

  Future<void> _spend() async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => PettySpendScreen(state: widget.state)));
    if (mounted) setState(() {});
  }

  Future<void> _cancel(PettyExpense e) async {
    final l = context.l;
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        content: Text(l.pettyCancelQ(money(e.amount, l.kwd))),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: Text(l.cancel)),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: Text(l.pettyCancel)),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await widget.state.cancelPetty(e.id);
    } catch (err) {
      if (mounted) showError(context, widget.state, err);
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final s = widget.state;
    final p = s.petty;
    final queued = s.queued.where((i) => i.kind == 'petty').toList();
    return Scaffold(
      appBar: AppBar(title: Text(l.pettyTitle)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
          children: [
            if (p == null)
              const Padding(
                padding: EdgeInsets.all(40),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (!p.hasCustody)
              DCard(
                key: const Key('petty-none'),
                child: Banner2(
                  text: l.pettyNone,
                  tone: BannerTone.neutral,
                  icon: Icons.account_balance_wallet_outlined,
                ),
              )
            else ...[
              DCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(l.pettyBalance, style: const TextStyle(fontSize: 12.5, color: AppColors.muted)),
                    const SizedBox(height: 2),
                    Text(
                      '\u2066${p.balance}\u2069 ${l.kwd}',
                      key: const Key('petty-balance'),
                      style: const TextStyle(fontSize: 34, fontWeight: FontWeight.w700, height: 1.3),
                    ),
                    if ((double.tryParse(p.pending) ?? 0) > 0)
                      Text(
                        l.pettyPendingPart('\u2066${p.pending}\u2069', '\u2066${p.available}\u2069'),
                        key: const Key('petty-pending'),
                        style: const TextStyle(fontSize: 12.5, color: AppColors.muted),
                      ),
                    const SizedBox(height: 14),
                    BusyButton(
                      key: const Key('petty-spend'),
                      label: l.pettySpend,
                      icon: Icons.receipt_long_outlined,
                      onPressed: _spend,
                    ),
                  ],
                ),
              ),
              SectionTitle(l.pettyMine),
              if (queued.isEmpty && p.expenses.isEmpty && p.movements.isEmpty)
                DCard(
                  child: Text(l.pettyEmpty, style: const TextStyle(color: AppColors.muted)),
                )
              else
                DCard.list(
                  child: Column(
                    children: [
                      for (final q in queued)
                        DRow(
                          key: Key('petty-queued-${q.id}'),
                          leading: const IconTile(Icons.cloud_off_outlined),
                          title: money('${q.payload['amount']}', l.kwd),
                          subtitle: _dmy('${q.payload['invoice_date']}'),
                          trailing: Pill(l.pettyQueued, tone: BannerTone.warn),
                        ),
                      for (final e in p.expenses) _ExpenseRow(expense: e, lang: s.lang, onCancel: () => _cancel(e)),
                      for (final m in p.movements) _MoveRow(move: m),
                    ],
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ExpenseRow extends StatelessWidget {
  const _ExpenseRow({required this.expense, required this.lang, required this.onCancel});

  final PettyExpense expense;
  final String lang;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final e = expense;
    final (label, tone) = switch (e.status) {
      'approved' => (l.pettyApproved, BannerTone.success),
      'rejected' => (l.pettyRejected, BannerTone.danger),
      'cancelled' => (l.pettyCancelled, BannerTone.neutral),
      _ => (l.pettyPending, BannerTone.warn),
    };
    return InkWell(
      onLongPress: e.status == 'pending' ? onCancel : null,
      child: DRow(
        key: Key('petty-expense-${e.id}'),
        leading: const IconTile(Icons.receipt_long_outlined),
        title: '− ${money(e.amount, l.kwd)}',
        subtitle: [
          _dmy(e.invoiceDate),
          if (e.category != null) e.category!.label(lang),
          ?e.vendor,
          if (e.status == 'rejected' && e.decisionNote != null) l.pettyReason(e.decisionNote!),
        ].join(' · '),
        trailing: e.status == 'pending'
            ? Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Pill(label, tone: tone),
                  IconButton(
                    key: Key('petty-cancel-${e.id}'),
                    tooltip: l.pettyCancel,
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: onCancel,
                  ),
                ],
              )
            : Pill(label, tone: tone),
      ),
    );
  }
}

class _MoveRow extends StatelessWidget {
  const _MoveRow({required this.move});

  final PettyMovement move;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final m = move;
    final into = !m.amount.startsWith('-');
    final title = switch (m.kind) {
      'petty_fund' => l.pettyFunded,
      'petty_return' => l.pettyReturned,
      'disbursement' => l.pettyOfficeExpense,
      _ => l.pettyCorrection,
    };
    final amount = into ? m.amount : m.amount.substring(1);
    return DRow(
      key: Key('petty-move-${m.id}'),
      leading: IconTile(into ? Icons.south_west : Icons.north_east),
      title: title,
      subtitle: [_dmy(m.date), ?m.note].join(' · '),
      trailing: Text(
        '${into ? '+' : '−'} ${money(amount, l.kwd)}',
        style: TextStyle(fontWeight: FontWeight.w600, color: into ? AppColors.success : AppColors.text),
      ),
    );
  }
}

/// «Spend from the custody»: the amount (3 decimals, never more than he can still spend), the expense type, the
/// invoice's camera photo (required), its date (today by default), the vendor and a note.
class PettySpendScreen extends StatefulWidget {
  const PettySpendScreen({super.key, required this.state});

  final AppState state;

  @override
  State<PettySpendScreen> createState() => _PettySpendScreenState();
}

class _PettySpendScreenState extends State<PettySpendScreen> {
  final _form = GlobalKey<FormState>();
  final _amountField = TextEditingController();
  final _vendor = TextEditingController();
  final _note = TextEditingController();
  TakenPhoto? invoice;
  bool _invoiceMissing = false;
  int? category;
  DateTime date = DateTime.now();

  @override
  void dispose() {
    _amountField.dispose();
    _vendor.dispose();
    _note.dispose();
    super.dispose();
  }

  Future<void> _takeInvoice() async {
    final p = await Photos.camera(context);
    if (p != null) {
      setState(() {
        invoice = p;
        _invoiceMissing = false;
      });
    }
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final d = await showDatePicker(
      context: context,
      initialDate: date,
      firstDate: now.subtract(const Duration(days: 30)),
      lastDate: now,
    );
    if (d != null) setState(() => date = d);
  }

  String? _checkAmount(AppLocalizations l, String? v) {
    final text = latinDigits((v ?? '').trim());
    if (!_amount.hasMatch(text) || double.parse(text) <= 0) return l.pettyAmountInvalid;
    final p = widget.state.petty;
    final queued = widget.state.queued
        .where((i) => i.kind == 'petty')
        .fold<double>(0, (t, i) => t + (double.tryParse('${i.payload['amount']}') ?? 0));
    final available = (double.tryParse(p?.available ?? '') ?? 0) - queued;
    if (p != null && double.parse(text) > available + 1e-9) {
      return l.pettyAmountMax('\u2066${(available < 0 ? 0 : available).toStringAsFixed(3)}\u2069');
    }
    return null;
  }

  Future<void> _send() async {
    final ok = _form.currentState!.validate();
    setState(() => _invoiceMissing = invoice == null);
    if (!ok || _invoiceMissing) return;
    final vendor = _vendor.text.trim();
    final note = _note.text.trim();
    try {
      final r = await widget.state.sendPetty(
        amount: double.parse(latinDigits(_amountField.text.trim())).toStringAsFixed(3),
        category: category!,
        invoiceDate: date,
        vendor: vendor.isEmpty ? null : vendor,
        note: note.isEmpty ? null : note,
        invoicePath: invoice!.path,
      );
      if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(result: r)));
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final s = widget.state;
    final categories = s.petty?.categories ?? const <PettyCategory>[];
    return Scaffold(
      appBar: AppBar(title: Text(l.pettySpend)),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
          children: [
            Text(
              l.pettyIntro('\u2066${s.petty?.available ?? '0.000'}\u2069'),
              style: const TextStyle(color: AppColors.muted, fontSize: 12.5, height: 1.6),
            ),
            const SizedBox(height: 10),
            DCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  FieldLabel(l.pettyInvoice, required: true),
                  PhotoTile(
                    key: const Key('petty-photo'),
                    label: invoice == null ? l.pettyTakeInvoice : l.mntTapToRemove,
                    hint: l.cameraOnly,
                    path: invoice?.path,
                    onTap: invoice == null ? _takeInvoice : () => setState(() => invoice = null),
                  ),
                  if (_invoiceMissing) ...[
                    const SizedBox(height: 6),
                    Text(
                      l.pettyInvoiceMissing,
                      key: const Key('petty-photo-missing'),
                      style: const TextStyle(color: AppColors.danger, fontSize: 12.5),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 12),
            DCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  FieldLabel(l.pettyAmount, required: true),
                  TextFormField(
                    key: const Key('petty-amount'),
                    controller: _amountField,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    textDirection: TextDirection.ltr,
                    inputFormatters: [const DecimalPoint(), FilteringTextInputFormatter.allow(RegExp('[0-9.٠-٩۰-۹]'))],
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                    decoration: InputDecoration(
                      suffixText: '  ${l.kwd}',
                      hintText: '0.000',
                      hintTextDirection: TextDirection.ltr,
                    ),
                    validator: (v) => _checkAmount(l, v),
                  ),
                  const SizedBox(height: 14),
                  FieldLabel(l.pettyCategory, required: true),
                  DropdownButtonFormField<int>(
                    key: const Key('petty-category'),
                    initialValue: category,
                    isExpanded: true,
                    items: [
                      for (final c in categories)
                        DropdownMenuItem(
                          value: c.id,
                          key: Key('petty-category-${c.code}'),
                          child: Text(c.label(s.lang)),
                        ),
                    ],
                    onChanged: (v) => setState(() => category = v),
                    validator: (v) => v == null ? l.pettyCategoryMissing : null,
                  ),
                  const SizedBox(height: 14),
                  FieldLabel(l.pettyDate, required: true),
                  OutlinedButton.icon(
                    key: const Key('petty-date'),
                    onPressed: _pickDate,
                    icon: const Icon(Icons.event, size: 18),
                    label: Text('\u2066${DateFormat('dd-MM-yyyy', 'en').format(date)}\u2069'),
                  ),
                  const SizedBox(height: 14),
                  FieldLabel(l.pettyVendor),
                  TextFormField(key: const Key('petty-vendor'), controller: _vendor, maxLength: 200),
                  FieldLabel(l.pettyNote),
                  TextFormField(key: const Key('petty-note'), controller: _note, maxLines: 2, maxLength: 500),
                ],
              ),
            ),
            const SizedBox(height: 20),
            BusyButton(key: const Key('petty-send'), label: l.pettySend, icon: Icons.send, onPressed: _send),
          ],
        ),
      ),
    );
  }
}
