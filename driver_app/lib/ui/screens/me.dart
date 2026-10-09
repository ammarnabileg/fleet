import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show DateFormat, NumberFormat;

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../photos.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'home.dart';

String _km(Object? km) => km == null ? '—' : '\u2066${NumberFormat('#,###', 'en').format(km)}\u2069';

String _date(Object? iso) => iso == null ? '—' : '\u2066${(iso as String).substring(0, 10)}\u2069';

/// "My car" (BRD FR-APP-02): the vehicle held, its last reading and registration, and a change of vehicle asked for
/// with the reason (FR-ASG-04).
class MyCarScreen extends StatefulWidget {
  const MyCarScreen({super.key, required this.state});

  final AppState state;

  @override
  State<MyCarScreen> createState() => _MyCarScreenState();
}

class _MyCarScreenState extends State<MyCarScreen> {
  bool loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      await widget.state.loadVehicle();
    } on ApiError catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
    if (mounted) setState(() => loading = false);
  }

  Future<void> _ask() async {
    final sent = await showDialog<bool>(
      context: context,
      builder: (c) => _ChangeDialog(state: widget.state),
    );
    if (sent == true && mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final mine = widget.state.myVehicle;
    final v = mine?.vehicle;
    final request = mine?.request;
    return Scaffold(
      appBar: AppBar(title: Text(l.myCar)),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : v == null
          ? Padding(
              padding: const EdgeInsets.all(24),
              child: Banner2(text: l.noCustody, icon: Icons.directions_car_outlined),
            )
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: Column(
                    children: [
                      ListTile(
                        leading: const Icon(Icons.directions_car),
                        title: Text(
                          '\u2066${v['plate_number']}\u2069',
                          style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
                        ),
                        subtitle: Text(
                          [v['make'], v['model'], v['year'], v['color']].where((x) => x != null).join(' · '),
                        ),
                      ),
                      ListTile(
                        dense: true,
                        title: Text(l.carSince),
                        trailing: Text(when(context, DateTime.parse(v['since'] as String))),
                      ),
                      ListTile(
                        key: const Key('car-last-km'),
                        dense: true,
                        title: Text(l.lastReading),
                        trailing: Text('${_km(v['last_odometer_km'])} ${l.km}'),
                        subtitle: v['last_reading_at'] == null
                            ? null
                            : Text(when(context, DateTime.parse(v['last_reading_at'] as String))),
                      ),
                      ListTile(
                        dense: true,
                        title: Text(l.registrationExpiry),
                        trailing: Text(_date(v['registration_expiry'])),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                if (request != null && request['status'] == 'pending')
                  Banner2(
                    key: const Key('change-pending'),
                    text: '${request['requested_plate'] ?? ''}'.isEmpty
                        ? l.vehicleChangePending
                        : l.vehicleChangePendingFor('\u2066${request['requested_plate']}\u2069'),
                    tone: BannerTone.warn,
                    icon: Icons.hourglass_top,
                  )
                else ...[
                  if (request != null && request['status'] == 'rejected') ...[
                    Banner2(text: l.vehicleChangeRejected('${request['note'] ?? ''}'), tone: BannerTone.danger),
                    const SizedBox(height: 10),
                  ],
                  OutlinedButton.icon(
                    key: const Key('ask-change'),
                    icon: const Icon(Icons.swap_horiz),
                    label: Text(l.requestVehicleChange),
                    onPressed: _ask,
                  ),
                ],
              ],
            ),
    );
  }
}

/// The change of vehicle: the other car's plate and the reason. The request is sent from here, so a plate the
/// server does not know shows its message under the field and the dialog stays open for him to correct it.
class _ChangeDialog extends StatefulWidget {
  const _ChangeDialog({required this.state});

  final AppState state;

  @override
  State<_ChangeDialog> createState() => _ChangeDialogState();
}

class _ChangeDialogState extends State<_ChangeDialog> {
  final plate = TextEditingController();
  final reason = TextEditingController();
  final form = GlobalKey<FormState>();
  String? plateError;
  bool sending = false;

  static const _plateCodes = {'vehicle_plate_not_found', 'vehicle_change_same_vehicle'};

  @override
  void dispose() {
    plate.dispose();
    reason.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    setState(() => plateError = null);
    if (!form.currentState!.validate()) return;
    setState(() => sending = true);
    try {
      await widget.state.requestVehicleChange(plate.text.trim(), reason.text.trim());
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (!mounted) return;
      setState(() => sending = false);
      if ((e is ApiError && _plateCodes.contains(e.code)) || invalidFields(e).contains('requested_plate')) {
        setState(() => plateError = errorText(context, widget.state, e));
      } else {
        showError(context, widget.state, e);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    return AlertDialog(
      title: Text(l.requestVehicleChange),
      content: Form(
        key: form,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextFormField(
              key: const Key('change-plate'),
              controller: plate,
              textDirection: TextDirection.ltr,
              textCapitalization: TextCapitalization.characters,
              decoration: InputDecoration(
                labelText: l.vehicleChangePlate,
                hintText: l.vehicleChangePlateHint,
                hintTextDirection: TextDirection.ltr,
                errorText: plateError,
                errorMaxLines: 3,
              ),
              onChanged: (_) {
                if (plateError != null) setState(() => plateError = null);
              },
              validator: (v) => (v ?? '').trim().isEmpty ? l.required : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              key: const Key('change-reason'),
              controller: reason,
              maxLines: 3,
              decoration: InputDecoration(labelText: l.vehicleChangeReason),
              validator: (v) => (v ?? '').trim().length < 3 ? l.required : null,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: sending ? null : () => Navigator.pop(context, false), child: Text(l.cancel)),
        FilledButton(
          key: const Key('send-change'),
          onPressed: sending ? null : _send,
          child: sending
              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
              : Text(l.send),
        ),
      ],
    );
  }
}

/// His documents with their expiry, and the renewed one sent for the office to check (BRD FR-APP-05).
class DocumentsScreen extends StatefulWidget {
  const DocumentsScreen({super.key, required this.state});

  final AppState state;

  @override
  State<DocumentsScreen> createState() => _DocumentsScreenState();
}

class _DocumentsScreenState extends State<DocumentsScreen> {
  bool loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      await widget.state.loadDocuments();
    } on ApiError catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
    if (mounted) setState(() => loading = false);
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final lang = widget.state.lang;
    return Scaffold(
      appBar: AppBar(title: Text(l.myDocuments)),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  for (final d in widget.state.documents)
                    Card(
                      key: Key('doc-${d.typeCode}'),
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    '${d.typeName[lang] ?? d.typeName['ar']}',
                                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                                  ),
                                ),
                                Pill(
                                  switch (d.state) {
                                    'valid' => l.docValid,
                                    'expiring' => l.docExpiring('${d.daysLeft}'),
                                    'expired' => l.docExpired,
                                    _ => l.docMissing,
                                  },
                                  tone: switch (d.state) {
                                    'valid' => BannerTone.success,
                                    'expiring' => BannerTone.warn,
                                    'expired' => BannerTone.danger,
                                    _ => BannerTone.info,
                                  },
                                ),
                              ],
                            ),
                            if (d.expiry != null) ...[
                              const SizedBox(height: 4),
                              Text(
                                [
                                  if (d.number != null) '\u2066${d.number}\u2069',
                                  l.docExpires(_date(d.expiry)),
                                ].join(' · '),
                                style: const TextStyle(color: AppColors.muted),
                              ),
                            ],
                            if (d.renewalPending) ...[
                              const SizedBox(height: 10),
                              Banner2(text: l.renewalPending, tone: BannerTone.warn, icon: Icons.hourglass_top),
                            ] else if (d.renewable) ...[
                              if (d.renewal?['status'] == 'rejected') ...[
                                const SizedBox(height: 10),
                                Banner2(
                                  text: l.renewalRejected('${d.renewal!['note'] ?? ''}'),
                                  tone: BannerTone.danger,
                                ),
                              ],
                              const SizedBox(height: 8),
                              Align(
                                alignment: AlignmentDirectional.centerStart,
                                child: TextButton.icon(
                                  key: Key('renew-${d.typeCode}'),
                                  icon: const Icon(Icons.upload_file),
                                  label: Text(l.uploadRenewal),
                                  onPressed: () async {
                                    await Navigator.of(context).push(
                                      MaterialPageRoute(
                                        builder: (_) => RenewalScreen(state: widget.state, document: d),
                                      ),
                                    );
                                    if (mounted) setState(() {});
                                  },
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                ],
              ),
            ),
    );
  }
}

/// The renewed document: its new expiry date, its number if any, and its photo or scan from the phone.
class RenewalScreen extends StatefulWidget {
  const RenewalScreen({super.key, required this.state, required this.document});

  final AppState state;
  final DriverDocument document;

  @override
  State<RenewalScreen> createState() => _RenewalScreenState();
}

class _RenewalScreenState extends State<RenewalScreen> {
  final _number = TextEditingController();
  final _form = GlobalKey<FormState>();
  DateTime? expiry;
  TakenPhoto? photo;

  String? get _expiry => expiry == null ? null : DateFormat('yyyy-MM-dd', 'en').format(expiry!);

  Future<void> _send() async {
    final l = context.l;
    if (!_form.currentState!.validate()) return;
    if (photo == null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l.photoRequired)));
      return;
    }
    try {
      final r = await widget.state.sendRenewal(
        typeCode: widget.document.typeCode,
        expiry: _expiry!,
        number: _number.text.trim().isEmpty ? null : _number.text.trim(),
        filePath: photo!.path,
      );
      if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(result: r)));
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final name = widget.document.typeName[widget.state.lang] ?? widget.document.typeName['ar'];
    return Scaffold(
      appBar: AppBar(title: Text('$name')),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            FormField<DateTime>(
              key: const Key('renewal-expiry'),
              validator: (_) => expiry == null ? l.required : null,
              builder: (field) => ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(l.newExpiry),
                subtitle: Text(
                  _expiry == null ? l.pickDate : '\u2066$_expiry\u2069',
                  style: TextStyle(color: field.hasError ? AppColors.danger : null),
                ),
                trailing: const Icon(Icons.calendar_month),
                onTap: () async {
                  final now = DateTime.now();
                  final picked = await showDatePicker(
                    context: context,
                    initialDate: now.add(const Duration(days: 365)),
                    firstDate: now.add(const Duration(days: 1)),
                    lastDate: now.add(const Duration(days: 3650)),
                  );
                  if (picked != null) {
                    setState(() => expiry = picked);
                    field.didChange(picked);
                  }
                },
              ),
            ),
            const SizedBox(height: 12),
            TextFormField(
              key: const Key('renewal-number'),
              controller: _number,
              textDirection: TextDirection.ltr,
              decoration: InputDecoration(labelText: l.documentNumber),
            ),
            const SizedBox(height: 16),
            Text(l.documentPhoto, style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            SizedBox(
              width: 180,
              child: PhotoTile(
                key: const Key('renewal-photo'),
                label: l.fromGallery,
                path: photo?.path,
                onTap: () async {
                  final p = await Photos.gallery();
                  if (p != null) setState(() => photo = p);
                },
              ),
            ),
            const SizedBox(height: 22),
            BusyButton(key: const Key('send-renewal'), label: l.send, icon: Icons.send, onPressed: _send),
          ],
        ),
      ),
    );
  }
}
