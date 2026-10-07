import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart' show NumberFormat;

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../../l10n/app_localizations.dart';
import '../photos.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'home.dart';

String fuelType(AppLocalizations l, String type) => switch (type) {
  'premium_91' => l.fuelType_premium_91,
  'super_95' => l.fuelType_super_95,
  'ultra_98' => l.fuelType_ultra_98,
  'diesel' => l.fuelType_diesel,
  _ => type,
};

(String, BannerTone) fuelStatus(AppLocalizations l, String status) => switch (status) {
  'approved' => (l.fuelStatus_approved, BannerTone.success),
  'rejected' => (l.fuelStatus_rejected, BannerTone.danger),
  _ => (l.fuelStatus_pending, BannerTone.warn),
};

String _n(String value, String pattern) =>
    '\u2066${NumberFormat(pattern, 'en').format(double.tryParse(value) ?? 0)}\u2069';

/// A fill for the vehicle the driver holds (FR-FUL-01): the litres, the amount and the fuel from the invoice, the
/// odometer, and the camera photos of the invoice and the odometer. The office's checks (the tank, the model's fuels,
/// the official price, the odometer) approve it at once or hold it for the accountant; his fills show their review.
class FuelScreen extends StatefulWidget {
  const FuelScreen({super.key, required this.state});

  final AppState state;

  @override
  State<FuelScreen> createState() => _FuelScreenState();
}

class _FuelScreenState extends State<FuelScreen> {
  final _form = GlobalKey<FormState>();
  final _litres = TextEditingController();
  final _amount = TextEditingController();
  final _station = TextEditingController();
  final _km = TextEditingController();
  String? type;
  TakenPhoto? invoice;
  TakenPhoto? odometer;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      await widget.state.loadFuel();
    } on ApiError {
      // offline: the last form stays
    }
    if (mounted) setState(() {});
  }

  Future<void> _take(void Function(TakenPhoto) keep) async {
    final p = await Photos.camera(context);
    if (p != null) setState(() => keep(p));
  }

  static String? _positive(AppLocalizations l, String? v) =>
      (double.tryParse(v ?? '') ?? 0) > 0 ? null : l.fuelNumberInvalid;

  Future<void> _send() async {
    final l = context.l;
    if (!_form.currentState!.validate()) return;
    if (invoice == null || odometer == null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l.fuelPhotosRequired)));
      return;
    }
    final station = _station.text.trim();
    try {
      final r = await widget.state.sendFuel(
        filledAt: invoice!.takenAt,
        litres: _litres.text,
        amount: _amount.text,
        fuelType: type!,
        station: station.isEmpty ? null : station,
        km: int.parse(_km.text),
        invoicePath: invoice!.path,
        odometerPath: odometer!.path,
      );
      if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(result: r)));
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final data = widget.state.fuel;
    final vehicle = data?.vehicle;
    final fills = data?.fills ?? const <FuelFill>[];
    if (vehicle != null && !vehicle.fuelTypes.contains(type)) type = vehicle.fuelTypes.first;
    final km = int.tryParse(_km.text);
    final decimals = [FilteringTextInputFormatter.allow(RegExp(r'^\d{0,4}(\.\d{0,3})?'))];
    return Scaffold(
      appBar: AppBar(title: Text(l.fuelTitle)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              if (data == null)
                const Center(child: CircularProgressIndicator())
              else if (vehicle == null)
                Banner2(text: l.fuelNoVehicle, tone: BannerTone.info)
              else ...[
                Text(l.fuelNew, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                Text(l.fuelIntro, style: const TextStyle(color: AppColors.muted, height: 1.6)),
                const SizedBox(height: 10),
                Banner2(
                  key: const Key('fuel-vehicle'),
                  text: [
                    '\u2066${vehicle.plate}\u2069',
                    if (vehicle.tank != null) l.fuelTank(_n(vehicle.tank!, '#,##0.#')),
                  ].join(' · '),
                  icon: Icons.local_gas_station_outlined,
                ),
                const SizedBox(height: 16),
                DropdownButtonFormField<String>(
                  key: const Key('fuel-type'),
                  initialValue: type,
                  decoration: InputDecoration(labelText: l.fuelType),
                  items: [for (final t in vehicle.fuelTypes) DropdownMenuItem(value: t, child: Text(fuelType(l, t)))],
                  onChanged: (v) => setState(() => type = v ?? type),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: TextFormField(
                        key: const Key('fuel-litres'),
                        controller: _litres,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        textDirection: TextDirection.ltr,
                        inputFormatters: decimals,
                        decoration: InputDecoration(labelText: l.fuelLitres),
                        validator: (v) => _positive(l, v),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: TextFormField(
                        key: const Key('fuel-amount'),
                        controller: _amount,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        textDirection: TextDirection.ltr,
                        inputFormatters: decimals,
                        decoration: InputDecoration(labelText: l.fuelAmount),
                        validator: (v) => _positive(l, v),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                TextFormField(
                  key: const Key('fuel-km'),
                  controller: _km,
                  keyboardType: TextInputType.number,
                  textDirection: TextDirection.ltr,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(7)],
                  decoration: InputDecoration(labelText: l.odometerKm, suffixText: '  ${l.km}'),
                  onChanged: (_) => setState(() {}),
                  validator: (v) => int.tryParse(v ?? '') == null ? l.kmInvalid : null,
                ),
                if (km != null && vehicle.lastKm != null && km < vehicle.lastKm!) ...[
                  const SizedBox(height: 10),
                  Banner2(text: l.kmLower('\u2066${vehicle.lastKm}\u2069'), tone: BannerTone.warn),
                ],
                const SizedBox(height: 12),
                TextFormField(
                  key: const Key('fuel-station'),
                  controller: _station,
                  maxLength: 120,
                  decoration: InputDecoration(labelText: l.fuelStation),
                ),
                const SizedBox(height: 8),
                GridView.count(
                  crossAxisCount: 2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  mainAxisSpacing: 10,
                  crossAxisSpacing: 10,
                  childAspectRatio: 4 / 3,
                  children: [
                    PhotoTile(
                      key: const Key('fuel-invoice'),
                      label: l.fuelInvoicePhoto,
                      path: invoice?.path,
                      onTap: () => _take((p) => invoice = p),
                    ),
                    PhotoTile(
                      key: const Key('fuel-odometer'),
                      label: l.odometerPhoto,
                      path: odometer?.path,
                      onTap: () => _take((p) => odometer = p),
                    ),
                  ],
                ),
                const SizedBox(height: 22),
                BusyButton(key: const Key('fuel-send'), label: l.send, icon: Icons.send, onPressed: _send),
              ],
              SectionTitle(l.fuelMine),
              if (data != null && fills.isEmpty) Text(l.fuelNone, style: const TextStyle(color: AppColors.muted)),
              for (final f in fills) _FillTile(fill: f),
            ],
          ),
        ),
      ),
    );
  }
}

class _FillTile extends StatelessWidget {
  const _FillTile({required this.fill});

  final FuelFill fill;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final (label, tone) = fuelStatus(l, fill.status);
    final lines = [
      '${fuelType(l, fill.fuelType)} · ${when(context, fill.filledAt)}',
      l.fuelLine(_n(fill.litres, '#,##0.##'), _n(fill.amount, '#,##0.000')),
      if (fill.reason != null) l.fuelRejected(fill.reason!),
    ];
    return Card(
      child: ListTile(
        title: Text(l.fuelFillNo('${fill.number}')),
        subtitle: Text(lines.join('\n'), style: const TextStyle(height: 1.5)),
        isThreeLine: true,
        trailing: Pill(label, tone: tone),
      ),
    );
  }
}
