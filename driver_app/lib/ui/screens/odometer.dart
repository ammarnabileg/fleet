import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/state.dart';
import '../photos.dart';
import '../widgets/common.dart';
import 'home.dart';

/// Start or end of the day: a photo of the odometer from the app's camera, then the reading. Saved with the
/// photo's own time and sent at once, or later if there is no network.
class OdometerScreen extends StatefulWidget {
  const OdometerScreen({super.key, required this.state, required this.kind, this.requestId, this.replacementPlate});

  final AppState state;
  final String kind; // start_day | end_day | pickup (the car collected from the maintenance center)
  final String? requestId; // pickup: the maintenance request
  final String? replacementPlate; // pickup: the replacement car he hands back in the same step (its reading too)

  @override
  State<OdometerScreen> createState() => _OdometerScreenState();
}

class _OdometerScreenState extends State<OdometerScreen> {
  TakenPhoto? photo;
  TakenPhoto? sparePhoto;
  final _km = TextEditingController();
  final _spareKm = TextEditingController();
  final _form = GlobalKey<FormState>();

  bool get _spare => widget.kind == 'pickup' && widget.replacementPlate != null;

  @override
  void dispose() {
    _km.dispose();
    _spareKm.dispose();
    super.dispose();
  }

  int? get lastKm => widget.state.today?.custody?.lastKm;

  Future<void> _take() async {
    final p = await Photos.camera(context);
    if (p != null) setState(() => photo = p);
  }

  Future<void> _send() async {
    final l = context.l;
    if (photo == null || (_spare && sparePhoto == null)) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l.photoRequired)));
      return;
    }
    if (!_form.currentState!.validate()) return;
    try {
      final r = widget.kind == 'pickup'
          ? await widget.state.sendPickup(
              requestId: widget.requestId!,
              km: int.parse(_km.text),
              photoPath: photo!.path,
              takenAt: photo!.takenAt,
              replacementKm: _spare ? int.parse(_spareKm.text) : null,
              replacementPhotoPath: _spare ? sparePhoto!.path : null,
            )
          : await widget.state.sendReading(
              kind: widget.kind,
              km: int.parse(_km.text),
              photoPath: photo!.path,
              takenAt: photo!.takenAt,
              lat: photo!.lat,
              lng: photo!.lng,
            );
      if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(result: r)));
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final typed = int.tryParse(_km.text);
    return Scaffold(
      appBar: AppBar(
        title: Text(switch (widget.kind) {
          'start_day' => l.startDayTitle,
          'pickup' => l.pickupTitle,
          _ => l.endDayTitle,
        }),
      ),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
          children: [
            DCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  FieldLabel(l.odometerPhoto, required: true),
                  PhotoTile(
                    key: const Key('odo-photo'),
                    label: photo == null ? l.takeOdometerPhoto : l.odometerPhoto,
                    hint: l.cameraOnly,
                    path: photo?.path,
                    onTap: _take,
                  ),
                  if (photo != null)
                    Align(
                      alignment: AlignmentDirectional.centerStart,
                      child: TextButton.icon(
                        onPressed: _take,
                        icon: const Icon(Icons.refresh, size: 18),
                        label: Text(l.retake),
                      ),
                    ),
                  const SizedBox(height: 12),
                  FieldLabel(l.odometerKm, required: true),
                  TextFormField(
                    key: const Key('km'),
                    controller: _km,
                    keyboardType: TextInputType.number,
                    textDirection: TextDirection.ltr,
                    style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w600, letterSpacing: 2),
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(7)],
                    decoration: InputDecoration(
                      hintText: '000000',
                      hintTextDirection: TextDirection.ltr,
                      helperMaxLines: 2,
                      suffixText: l.km,
                      helperText: lastKm == null ? null : l.lastKmHint(km(lastKm!)),
                    ),
                    onChanged: (_) => setState(() {}),
                    validator: (v) => int.tryParse(v ?? '') == null ? l.kmInvalid : null,
                  ),
                ],
              ),
            ),
            if (_spare) ...[
              const SizedBox(height: 12),
              DCard(
                key: const Key('pickup-replacement'),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      l.pickupReplacementTitle('\u2066${widget.replacementPlate}\u2069'),
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    const SizedBox(height: 4),
                    Text(l.pickupReplacementHint, style: const TextStyle(fontSize: 12.5, height: 1.5)),
                    const SizedBox(height: 10),
                    FieldLabel(l.pickupReplacementPhoto, required: true),
                    PhotoTile(
                      key: const Key('spare-photo'),
                      label: sparePhoto == null ? l.takeOdometerPhoto : l.pickupReplacementPhoto,
                      hint: l.cameraOnly,
                      path: sparePhoto?.path,
                      onTap: () async {
                        final p = await Photos.camera(context);
                        if (p != null) setState(() => sparePhoto = p);
                      },
                    ),
                    const SizedBox(height: 12),
                    FieldLabel(l.odometerKm, required: true),
                    TextFormField(
                      key: const Key('spare-km'),
                      controller: _spareKm,
                      keyboardType: TextInputType.number,
                      textDirection: TextDirection.ltr,
                      inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(7)],
                      decoration: InputDecoration(
                        hintText: '000000',
                        hintTextDirection: TextDirection.ltr,
                        suffixText: l.km,
                      ),
                      validator: (v) => int.tryParse(v ?? '') == null ? l.kmInvalid : null,
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 12),
            Banner2(text: widget.kind == 'pickup' ? l.pickupIntro : l.odometerIntro, icon: Icons.info_outline),
            if (typed != null && lastKm != null && typed < lastKm!) ...[
              const SizedBox(height: 10),
              Banner2(text: l.kmLower('\u2066$lastKm\u2069'), tone: BannerTone.warn),
            ],
            const SizedBox(height: 20),
            BusyButton(
              key: const Key('send-reading'),
              label: switch (widget.kind) {
                'start_day' => l.startDay,
                'end_day' => l.endDay,
                _ => l.mntPickedUp,
              },
              icon: switch (widget.kind) {
                'start_day' => Icons.play_arrow_rounded,
                'end_day' => Icons.nightlight_outlined,
                _ => Icons.key,
              },
              onPressed: _send,
            ),
          ],
        ),
      ),
    );
  }
}
