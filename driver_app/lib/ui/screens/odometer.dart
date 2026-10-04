import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/state.dart';
import '../photos.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'home.dart';

/// Start or end of the day: a photo of the odometer from the app's camera, then the reading. Saved with the
/// photo's own time and sent at once, or later if there is no network.
class OdometerScreen extends StatefulWidget {
  const OdometerScreen({super.key, required this.state, required this.kind});

  final AppState state;
  final String kind; // start_day | end_day

  @override
  State<OdometerScreen> createState() => _OdometerScreenState();
}

class _OdometerScreenState extends State<OdometerScreen> {
  TakenPhoto? photo;
  final _km = TextEditingController();
  final _form = GlobalKey<FormState>();

  int? get lastKm => widget.state.today?.custody?.lastKm;

  Future<void> _take() async {
    final p = await Photos.camera(context);
    if (p != null) setState(() => photo = p);
  }

  Future<void> _send() async {
    final l = context.l;
    if (photo == null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l.photoRequired)));
      return;
    }
    if (!_form.currentState!.validate()) return;
    try {
      final r = await widget.state.sendReading(
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
    final km = int.tryParse(_km.text);
    return Scaffold(
      appBar: AppBar(title: Text(widget.kind == 'start_day' ? l.startDayTitle : l.endDayTitle)),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(l.odometerIntro, style: const TextStyle(color: AppColors.muted, height: 1.7)),
            const SizedBox(height: 16),
            PhotoTile(key: const Key('odo-photo'), label: l.odometerPhoto, path: photo?.path, onTap: _take),
            if (photo != null)
              TextButton.icon(onPressed: _take, icon: const Icon(Icons.refresh), label: Text(l.retake)),
            const SizedBox(height: 16),
            TextFormField(
              key: const Key('km'),
              controller: _km,
              keyboardType: TextInputType.number,
              textDirection: TextDirection.ltr,
              style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w600, letterSpacing: 2),
              inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(7)],
              decoration: InputDecoration(labelText: l.odometerKm, suffixText: l.km),
              onChanged: (_) => setState(() {}),
              validator: (v) => int.tryParse(v ?? '') == null ? l.kmInvalid : null,
            ),
            if (km != null && lastKm != null && km < lastKm!) ...[
              const SizedBox(height: 10),
              Banner2(text: l.kmLower('\u2066$lastKm\u2069'), tone: BannerTone.warn),
            ],
            const SizedBox(height: 24),
            BusyButton(key: const Key('send-reading'), label: l.send, icon: Icons.send, onPressed: _send),
          ],
        ),
      ),
    );
  }
}
