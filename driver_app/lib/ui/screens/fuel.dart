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

final _amount = RegExp(r'^\d{1,9}(\.\d{1,3})?$');

/// Why the app offers him no fuel claim.
String fuelOff(AppLocalizations l, String? reason) => switch (reason) {
  'fuel_card' => l.fuelOff_fuel_card,
  'no_vehicle' => l.fuelOff_no_vehicle,
  _ => l.fuelOff_not_covered,
};

/// Fuel the driver paid from the cash he holds: the receipt's camera photo, the amount, the odometer if he wants;
/// the accountant reviews it (and may correct the amount), and an approval takes it off his cash. Only when his pay
/// scheme puts fuel on the company: otherwise the screen says why and has no form. Below: his last receipts.
class FuelScreen extends StatefulWidget {
  const FuelScreen({super.key, required this.state});

  final AppState state;

  @override
  State<FuelScreen> createState() => _FuelScreenState();
}

class _FuelScreenState extends State<FuelScreen> {
  final _form = GlobalKey<FormState>();
  final _amountField = TextEditingController();
  final _km = TextEditingController();
  final _notes = TextEditingController();
  TakenPhoto? receipt;
  bool _receiptMissing = false;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  @override
  void dispose() {
    _amountField.dispose();
    _km.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _reload() async {
    try {
      await widget.state.loadFuel();
    } on ApiError {
      // offline: the last answer stays
    }
    if (mounted) setState(() {});
  }

  Future<void> _takeReceipt() async {
    final p = await Photos.camera(context);
    if (p != null) {
      setState(() {
        receipt = p;
        _receiptMissing = false;
      });
    }
  }

  String? _checkAmount(AppLocalizations l, String? v) {
    final text = latinDigits((v ?? '').trim());
    if (!_amount.hasMatch(text) || double.parse(text) <= 0) return l.fuelAmountInvalid;
    final max = double.tryParse(widget.state.fuel?.maxAmount ?? '');
    if (max != null && double.parse(text) > max) return l.fuelAmountMax('\u2066${widget.state.fuel!.maxAmount}\u2069');
    return null;
  }

  Future<void> _send() async {
    final ok = _form.currentState!.validate();
    setState(() => _receiptMissing = receipt == null);
    if (!ok || _receiptMissing) return;
    final km = _km.text.trim();
    final notes = _notes.text.trim();
    try {
      final r = await widget.state.sendFuel(
        paidAt: receipt!.takenAt,
        amount: double.parse(latinDigits(_amountField.text.trim())).toStringAsFixed(3),
        odometerKm: km.isEmpty ? null : int.parse(latinDigits(km)),
        notes: notes.isEmpty ? null : notes,
        receiptPath: receipt!.path,
      );
      if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(result: r)));
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final fuel = widget.state.fuel;
    final claims = fuel?.claims ?? const <FuelClaim>[];
    return Scaffold(
      appBar: AppBar(title: Text(l.fuelTitle)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
            children: [
              if (fuel != null && !fuel.allowed)
                DCard(
                  key: const Key('fuel-off'),
                  child: Banner2(
                    text: fuelOff(l, fuel.reason),
                    tone: BannerTone.neutral,
                    icon: Icons.local_gas_station,
                  ),
                )
              else if (fuel != null) ...[
                Text(l.fuelIntro, style: const TextStyle(color: AppColors.muted, fontSize: 12.5, height: 1.6)),
                const SizedBox(height: 10),
                DCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      FieldLabel(l.fuelReceipt, required: true),
                      PhotoTile(
                        key: const Key('fuel-photo'),
                        label: receipt == null ? l.fuelTakeReceipt : l.mntTapToRemove,
                        hint: l.cameraOnly,
                        path: receipt?.path,
                        onTap: receipt == null ? _takeReceipt : () => setState(() => receipt = null),
                      ),
                      if (_receiptMissing) ...[
                        const SizedBox(height: 6),
                        Text(
                          l.fuelReceiptMissing,
                          key: const Key('fuel-photo-missing'),
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
                      FieldLabel(l.fuelAmount, required: true),
                      TextFormField(
                        key: const Key('fuel-amount'),
                        controller: _amountField,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        textDirection: TextDirection.ltr,
                        inputFormatters: [FilteringTextInputFormatter.allow(RegExp('[0-9.٠-٩۰-۹]'))],
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                        decoration: InputDecoration(
                          suffixText: '  ${l.kwd}',
                          hintText: '0.000',
                          hintTextDirection: TextDirection.ltr,
                        ),
                        validator: (v) => _checkAmount(l, v),
                      ),
                      const SizedBox(height: 14),
                      FieldLabel(l.fuelOdometer),
                      TextFormField(
                        key: const Key('fuel-km'),
                        controller: _km,
                        keyboardType: TextInputType.number,
                        textDirection: TextDirection.ltr,
                        inputFormatters: [
                          FilteringTextInputFormatter.allow(RegExp('[0-9٠-٩۰-۹]')),
                          LengthLimitingTextInputFormatter(7),
                        ],
                        decoration: InputDecoration(
                          hintText: '000000',
                          hintTextDirection: TextDirection.ltr,
                          suffixText: l.km,
                        ),
                      ),
                      const SizedBox(height: 14),
                      FieldLabel(l.fuelNotes),
                      TextFormField(key: const Key('fuel-notes'), controller: _notes, maxLines: 2, maxLength: 500),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                BusyButton(key: const Key('fuel-send'), label: l.fuelSend, icon: Icons.send, onPressed: _send),
              ],
              SectionTitle(l.fuelMine),
              if (claims.isEmpty)
                DCard(
                  child: Text(l.fuelNone, style: const TextStyle(color: AppColors.muted)),
                )
              else
                DCard.list(
                  child: Column(
                    children: [for (final (i, c) in claims.indexed) _ClaimRow(claim: c, last: i == claims.length - 1)],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ClaimRow extends StatelessWidget {
  const _ClaimRow({required this.claim, required this.last});

  final FuelClaim claim;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final c = claim;
    final (label, tone) = switch (c.status) {
      'approved' => (l.fuelApproved(money(c.approvedAmount ?? c.amount, l.kwd)), BannerTone.success),
      'rejected' => (l.fuelRejected, BannerTone.danger),
      _ => (l.fuelPending, BannerTone.warn),
    };
    return DRow(
      key: Key('fuel-claim-${c.id}'),
      divider: !last,
      leading: const IconTile(Icons.local_gas_station),
      title: money(c.amount, l.kwd),
      subtitle: [
        when(context, c.paidAt),
        if (c.plate != null) '\u2066${c.plate}\u2069',
        if (c.odometerKm != null) '\u2066${c.odometerKm}\u2069 ${l.km}',
        ?c.decisionNote,
      ].join(' · '),
      trailing: Pill(label, tone: tone),
    );
  }
}
