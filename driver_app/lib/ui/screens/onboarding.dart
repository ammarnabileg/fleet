import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/state.dart';
import '../../core/models.dart';
import '../photos.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'schemes.dart';

/// First launch after the activation link: details, documents (both sides), the vehicle the driver holds and its
/// photos. Every photo is uploaded as soon as it is taken and the draft is saved on the server, so nothing is lost
/// if the app closes; nothing is official until the company approves.
class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key, required this.state});

  final AppState state;

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  late Map<String, dynamic> draft;
  final _local = <String, String>{}; // sha256 -> local file, for previews in this session
  final _busy = <String>{};
  int step = 0;
  final _civil = TextEditingController();
  final _nat = TextEditingController();
  final _iban = TextEditingController();
  final _bank = TextEditingController();
  final _plate = TextEditingController();
  final _km = TextEditingController();
  final _numbers = <String, TextEditingController>{};

  Onboarding get ob => widget.state.onboarding!;
  AppState get state => widget.state;

  @override
  void initState() {
    super.initState();
    final d = ob.data;
    draft = {
      'civil_id': d['civil_id'],
      'nationality': d['nationality'],
      'iban': d['iban'],
      'bank_name': d['bank_name'],
      'documents': [
        for (final code in ob.requiredDocuments)
          Map<String, dynamic>.from(
            (d['documents'] as List? ?? []).cast<Map>().firstWhere(
              (x) => x['type_code'] == code,
              orElse: () => {'type_code': code},
            ),
          ),
      ],
      'vehicle': Map<String, dynamic>.from(d['vehicle'] as Map? ?? {'photos': []}),
      'no_vehicle': d['no_vehicle'] ?? false,
      'scheme_id': d['scheme_id'],
    };
    (draft['vehicle'] as Map)['photos'] ??= [];
    _civil.text = draft['civil_id'] ?? '';
    _nat.text = draft['nationality'] ?? '';
    _iban.text = draft['iban'] ?? '';
    _bank.text = draft['bank_name'] ?? '';
    _plate.text = (draft['vehicle'] as Map)['plate_number'] ?? '';
    _km.text = '${(draft['vehicle'] as Map)['odometer_km'] ?? ''}';
    for (final doc in docs) {
      _numbers[doc['type_code'] as String] = TextEditingController(text: doc['number'] as String? ?? '');
    }
  }

  /// His choice among his platform's schemes (one that is no longer offered is no choice).
  PayScheme? get _scheme => ob.schemes.where((s) => s.id == draft['scheme_id']).firstOrNull;

  List<Map<String, dynamic>> get docs => (draft['documents'] as List).cast<Map<String, dynamic>>();
  Map<String, dynamic> get vehicle => draft['vehicle'] as Map<String, dynamic>;

  void _collect() {
    draft['civil_id'] = _civil.text.trim().isEmpty ? null : _civil.text.trim();
    draft['nationality'] = _nat.text.trim().isEmpty ? null : _nat.text.trim();
    final iban = _iban.text.replaceAll(' ', '').toUpperCase();
    draft['iban'] = iban.isEmpty ? null : iban;
    draft['bank_name'] = _bank.text.trim().isEmpty ? null : _bank.text.trim();
    vehicle['plate_number'] = _plate.text.trim().isEmpty ? null : _plate.text.trim();
    vehicle['odometer_km'] = int.tryParse(_km.text.trim());
    for (final doc in docs) {
      final n = _numbers[doc['type_code']]!.text.trim();
      doc['number'] = n.isEmpty ? null : n;
    }
  }

  Map<String, dynamic> _payload() {
    _collect();
    return {
      'civil_id': draft['civil_id'],
      'nationality': draft['nationality'],
      'iban': draft['iban'] != null && ibanOk(draft['iban'] as String) ? draft['iban'] : null,
      'bank_name': draft['bank_name'],
      'documents': docs,
      'no_vehicle': draft['no_vehicle'],
      'vehicle': draft['no_vehicle'] == true ? null : vehicle,
      'scheme_id': ?_scheme?.id,
    };
  }

  Future<void> _save() async {
    final r = await state.api.put('/driver/onboarding', body: _payload());
    state.onboarding = Onboarding.fromJson(r as Map<String, dynamic>);
  }

  Future<void> _photo(String key, {required bool cameraOnly, required void Function(String sha) apply}) async {
    TakenPhoto? shot;
    if (cameraOnly) {
      shot = await Photos.camera(context);
    } else {
      final pick = await showModalBottomSheet<String>(
        context: context,
        builder: (c) => SafeArea(
          child: Wrap(
            children: [
              ListTile(
                leading: const Icon(Icons.photo_camera_outlined),
                title: Text(c.l.takePhoto),
                onTap: () => Navigator.pop(c, 'camera'),
              ),
              ListTile(
                leading: const Icon(Icons.photo_library_outlined),
                title: Text(c.l.fromGallery),
                onTap: () => Navigator.pop(c, 'gallery'),
              ),
            ],
          ),
        ),
      );
      if (pick == null || !mounted) return;
      shot = pick == 'camera' ? await Photos.camera(context) : await Photos.gallery();
    }
    if (shot == null) return;
    setState(() => _busy.add(key));
    try {
      // vehicle and odometer photos must come from the camera path: the server checks it
      final f = await state.api.upload(shot.path, source: cameraOnly ? 'camera' : 'upload');
      final sha = f['sha256'] as String;
      _local[sha] = shot.path;
      setState(() => apply(sha));
      await _save();
    } catch (e) {
      if (mounted) showError(context, state, e);
    } finally {
      if (mounted) setState(() => _busy.remove(key));
    }
  }

  List<String> _missing() {
    final l = context.l;
    _collect();
    final out = <String>[];
    if (!RegExp(r'^\d{12}$').hasMatch(draft['civil_id'] ?? '')) out.add(l.civilId);
    if ((draft['nationality'] ?? '').isEmpty) out.add(l.nationality);
    final iban = draft['iban'] as String?;
    if ((ob.requireBank && iban == null) || (iban != null && !ibanOk(iban))) out.add(l.iban);
    if (ob.requireBank && (draft['bank_name'] ?? '').isEmpty) out.add(l.bankName);
    if (ob.schemeRequired && _scheme == null) out.add(l.paySchemes);
    for (final doc in docs) {
      final t = ob.documentTypes.where((x) => x.code == doc['type_code']).firstOrNull;
      final name = t?.label(state.lang) ?? doc['type_code'] as String;
      if (doc['front_sha256'] == null ||
          doc['back_sha256'] == null ||
          (t?.requiresExpiry == true && doc['expiry_date'] == null)) {
        out.add(name);
      }
    }
    if (draft['no_vehicle'] != true) {
      final photos = {for (final p in (vehicle['photos'] as List).cast<Map>()) p['position']};
      if (vehicle['plate_number'] == null ||
          vehicle['odometer_km'] == null ||
          vehicle['odometer_photo'] == null ||
          !ob.vehiclePhotos.every(photos.contains)) {
        out.add(l.obStepVehicle);
      }
    }
    return out;
  }

  Future<void> _submit() async {
    try {
      await _save();
      final r = await state.api.post('/driver/onboarding/submit');
      state.onboarding = Onboarding.fromJson(r as Map<String, dynamic>);
      await state.refresh();
    } catch (e) {
      if (mounted) showError(context, state, e);
    }
  }

  Future<void> _next() async {
    try {
      await _save();
      setState(() => step++);
    } catch (e) {
      if (mounted) showError(context, state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final steps = [l.obStepData, l.obStepDocs, l.obStepVehicle, l.obStepReview];
    return Scaffold(
      appBar: AppBar(
        title: Text(l.obTitle),
        leading: step > 0 ? IconButton(icon: const BackButtonIcon(), onPressed: () => setState(() => step--)) : null,
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Row(
              children: [
                for (var i = 0; i < steps.length; i++)
                  Expanded(
                    child: Column(
                      children: [
                        Container(
                          height: 4,
                          margin: const EdgeInsets.symmetric(horizontal: 2),
                          color: i <= step ? AppColors.primary : AppColors.border,
                        ),
                        const SizedBox(height: 6),
                        Text(
                          steps[i],
                          style: TextStyle(
                            fontSize: 12,
                            color: i == step ? AppColors.primary : AppColors.muted,
                            fontWeight: i == step ? FontWeight.w600 : null,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [
                if (step == 0 && ob.status == 'rejected' && ob.reviewNote != null) ...[
                  Banner2(text: l.obRejected(ob.reviewNote!), tone: BannerTone.warn, icon: Icons.replay),
                  const SizedBox(height: 14),
                ],
                if (step == 0) ..._dataStep(),
                if (step == 1) ..._docsStep(),
                if (step == 2) ..._vehicleStep(),
                if (step == 3) ..._reviewStep(),
              ],
            ),
          ),
          SafeArea(
            minimum: const EdgeInsets.fromLTRB(20, 0, 20, 16),
            child: step < 3
                ? BusyButton(key: const Key('ob-next'), label: l.continueBtn, onPressed: _next)
                : BusyButton(
                    key: const Key('ob-submit'),
                    label: l.obSubmit,
                    onPressed: _missing().isEmpty ? _submit : null,
                  ),
          ),
        ],
      ),
    );
  }

  List<Widget> _dataStep() {
    final l = context.l;
    return [
      Text(l.obIntro, style: const TextStyle(color: AppColors.muted, height: 1.7)),
      const SizedBox(height: 18),
      TextField(
        key: const Key('civil'),
        controller: _civil,
        keyboardType: TextInputType.number,
        textDirection: TextDirection.ltr,
        maxLength: 12,
        inputFormatters: [FilteringTextInputFormatter.digitsOnly],
        decoration: InputDecoration(labelText: l.civilId),
      ),
      const SizedBox(height: 8),
      TextField(
        key: const Key('nationality'),
        controller: _nat,
        decoration: InputDecoration(labelText: l.nationality),
      ),
      const SizedBox(height: 8),
      TextField(
        key: const Key('iban'),
        controller: _iban,
        textDirection: TextDirection.ltr,
        textCapitalization: TextCapitalization.characters,
        inputFormatters: [LengthLimitingTextInputFormatter(42)], // banks show it in groups of 4
        decoration: InputDecoration(
          labelText: l.iban,
          hintText: 'KW00XXXX0000000000000000000000',
          helperText: l.ibanHint,
        ),
      ),
      TextField(
        key: const Key('bank'),
        controller: _bank,
        decoration: InputDecoration(labelText: l.bankName),
      ),
      if (ob.schemes.isNotEmpty) ...[
        SectionTitle(l.schemeChoose),
        Text(l.schemeChooseHint, style: const TextStyle(color: AppColors.muted, height: 1.6)),
        const SizedBox(height: 8),
        for (final s in ob.schemes)
          SchemeCard(
            key: Key('ob-scheme-${s.code}'),
            scheme: s,
            lang: state.lang,
            selected: draft['scheme_id'] == s.id,
            onTap: () => setState(() => draft['scheme_id'] = s.id),
          ),
      ],
    ];
  }

  List<Widget> _docsStep() {
    final l = context.l;
    return [
      for (final doc in docs) ...[
        Builder(
          builder: (context) {
            final code = doc['type_code'] as String;
            final t = ob.documentTypes.where((x) => x.code == code).firstOrNull;
            return Card(
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      t?.label(state.lang) ?? code,
                      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
                    ),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        for (final side in ['front', 'back']) ...[
                          Expanded(
                            child: PhotoTile(
                              label: side == 'front' ? l.docFront : l.docBack,
                              path: _local[doc['${side}_sha256']],
                              done: doc['${side}_sha256'] != null,
                              busy: _busy.contains('$code-$side'),
                              onTap: () =>
                                  _photo('$code-$side', cameraOnly: false, apply: (sha) => doc['${side}_sha256'] = sha),
                            ),
                          ),
                          if (side == 'front') const SizedBox(width: 10),
                        ],
                      ],
                    ),
                    const SizedBox(height: 10),
                    TextField(
                      controller: _numbers[code],
                      textDirection: TextDirection.ltr,
                      decoration: InputDecoration(labelText: l.docNumber),
                    ),
                    const SizedBox(height: 10),
                    OutlinedButton.icon(
                      icon: const Icon(Icons.event_outlined),
                      label: Text(
                        doc['expiry_date'] == null ? l.docExpiry : '${l.docExpiry}: \u2066${doc['expiry_date']}\u2069',
                      ),
                      onPressed: () async {
                        final now = DateTime.now();
                        final d = await showDatePicker(
                          context: context,
                          firstDate: now.subtract(const Duration(days: 365)),
                          lastDate: DateTime(now.year + 15),
                          initialDate: now.add(const Duration(days: 180)),
                        );
                        if (d == null) return;
                        final day =
                            '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
                        setState(() => doc['expiry_date'] = day);
                      },
                    ),
                  ],
                ),
              ),
            );
          },
        ),
        const SizedBox(height: 12),
      ],
    ];
  }

  List<Widget> _vehicleStep() {
    final l = context.l;
    final none = draft['no_vehicle'] == true;
    final photos = (vehicle['photos'] as List).cast<Map>();
    String? shaOf(String pos) =>
        photos.where((p) => p['position'] == pos).map((p) => p['sha256'] as String).firstOrNull;
    return [
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(l.noVehicle),
        value: none,
        onChanged: (v) => setState(() => draft['no_vehicle'] = v),
      ),
      if (!none) ...[
        TextField(
          key: const Key('plate'),
          controller: _plate,
          textDirection: TextDirection.ltr,
          decoration: InputDecoration(labelText: l.plate, helperText: l.plateHint),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: PhotoTile(
                label: l.odometerPhoto,
                path: _local[vehicle['odometer_photo']],
                done: vehicle['odometer_photo'] != null,
                busy: _busy.contains('odo'),
                onTap: () => _photo('odo', cameraOnly: true, apply: (sha) => vehicle['odometer_photo'] = sha),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                key: const Key('ob-km'),
                controller: _km,
                keyboardType: TextInputType.number,
                textDirection: TextDirection.ltr,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                decoration: InputDecoration(labelText: l.odometerKm),
              ),
            ),
          ],
        ),
        SectionTitle(l.vehiclePhotos),
        GridView.count(
          crossAxisCount: 2,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 10,
          crossAxisSpacing: 10,
          childAspectRatio: 4 / 3,
          children: [
            for (final pos in ob.vehiclePhotos)
              PhotoTile(
                label: positionLabel(context, pos),
                path: _local[shaOf(pos)],
                done: shaOf(pos) != null,
                busy: _busy.contains('pos-$pos'),
                onTap: () => _photo(
                  'pos-$pos',
                  cameraOnly: true,
                  apply: (sha) {
                    photos.removeWhere((p) => p['position'] == pos);
                    photos.add({'position': pos, 'sha256': sha});
                  },
                ),
              ),
          ],
        ),
      ],
    ];
  }

  List<Widget> _reviewStep() {
    final l = context.l;
    final missing = _missing();
    return [
      if (missing.isEmpty)
        Banner2(text: l.obReady, tone: BannerTone.success, icon: Icons.check_circle_outline)
      else
        Banner2(text: l.obMissing(missing.join('، ')), tone: BannerTone.warn),
      const SizedBox(height: 14),
      Card(
        child: Column(
          children: [
            ListTile(title: Text(l.civilId), trailing: Text('\u2066${draft['civil_id'] ?? '—'}\u2069')),
            ListTile(title: Text(l.nationality), trailing: Text(draft['nationality'] ?? '—')),
            ListTile(title: Text(l.iban), trailing: Text('\u2066${draft['iban'] ?? '—'}\u2069')),
            ListTile(title: Text(l.bankName), trailing: Text(draft['bank_name'] ?? '—')),
            if (ob.schemes.isNotEmpty)
              ListTile(title: Text(l.paySchemes), trailing: Text(_scheme?.label(state.lang) ?? '—')),
            for (final doc in docs)
              ListTile(
                title: Text(
                  ob.documentTypes.where((x) => x.code == doc['type_code']).firstOrNull?.label(state.lang) ??
                      doc['type_code'] as String,
                ),
                trailing: Icon(
                  doc['front_sha256'] != null && doc['back_sha256'] != null
                      ? Icons.check_circle
                      : Icons.radio_button_unchecked,
                  color: doc['front_sha256'] != null && doc['back_sha256'] != null
                      ? AppColors.success
                      : AppColors.muted,
                ),
              ),
            ListTile(
              title: Text(l.plate),
              trailing: Text(
                draft['no_vehicle'] == true ? l.noVehicle : '\u2066${vehicle['plate_number'] ?? '—'}\u2069',
              ),
            ),
          ],
        ),
      ),
    ];
  }
}

String positionLabel(BuildContext context, String pos) {
  final l = context.l;
  return switch (pos) {
    'front' => l.position_front,
    'back' => l.position_back,
    'left' => l.position_left,
    'right' => l.position_right,
    'interior' => l.position_interior,
    _ => l.position_other,
  };
}
