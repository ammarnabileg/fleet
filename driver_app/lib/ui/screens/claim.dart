import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/outbox.dart';
import '../photos.dart';
import '../widgets/common.dart';
import 'home.dart';

/// Without a car: the car he registered (waiting for the office, or refused with the reason) and the button to
/// register one. Nothing while the office has not answered what he holds.
class ClaimBox extends StatelessWidget {
  const ClaimBox({super.key, required this.state, this.onChanged});

  final AppState state;
  final VoidCallback? onChanged;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final mine = state.myVehicle;
    final claim = mine?.claim;
    final plate = '\u2066${claim?['plate'] ?? ''}\u2069';
    if (mine != null && mine.claimPending) {
      return Banner2(
        key: const Key('claim-pending'),
        text: l.claimPending(plate),
        tone: BannerTone.warn,
        icon: Icons.hourglass_top,
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (mine != null && mine.claimRejected) ...[
          Banner2(
            key: const Key('claim-rejected'),
            text: l.claimRejected(plate, '${claim?['note'] ?? ''}'),
            tone: BannerTone.danger,
          ),
          const SizedBox(height: 10),
        ],
        OutlinedButton.icon(
          key: const Key('claim-vehicle'),
          icon: const Icon(Icons.add_road),
          label: Text(l.claimVehicle),
          onPressed: () async {
            await Navigator.of(context).push(MaterialPageRoute(builder: (_) => ClaimScreen(state: state)));
            onChanged?.call();
          },
        ),
      ],
    );
  }
}

/// A new car: its plate, the odometer from the app's camera and the reading, condition photos if he wants. It goes to
/// the office; his custody starts once approved, from the photo's time. A plate the server refuses (not one of his
/// company's cars, with another driver, not available) shows its message under the field, to correct it.
class ClaimScreen extends StatefulWidget {
  const ClaimScreen({super.key, required this.state});

  final AppState state;

  @override
  State<ClaimScreen> createState() => _ClaimScreenState();
}

class _ClaimScreenState extends State<ClaimScreen> {
  static const _plateCodes = {'vehicle_plate_not_found', 'vehicle_held_by_other', 'vehicle_not_available'};
  static const maxPhotos = 4;

  final _plate = TextEditingController();
  final _km = TextEditingController();
  final _form = GlobalKey<FormState>();
  TakenPhoto? photo;
  final photos = <TakenPhoto>[];
  String? plateError;

  @override
  void dispose() {
    _plate.dispose();
    _km.dispose();
    super.dispose();
  }

  Future<void> _take() async {
    final p = await Photos.camera(context);
    if (p != null) setState(() => photo = p);
  }

  Future<void> _addPhoto() async {
    final p = await Photos.camera(context);
    if (p != null) setState(() => photos.add(p));
  }

  Future<void> _send() async {
    final l = context.l;
    setState(() => plateError = null);
    if (!_form.currentState!.validate()) return;
    if (photo == null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l.photoRequired)));
      return;
    }
    try {
      final r = await widget.state.sendClaim(
        plate: _plate.text.trim(),
        km: int.parse(_km.text),
        photoPath: photo!.path,
        takenAt: photo!.takenAt,
        photoPaths: [for (final p in photos) p.path],
      );
      if (!mounted) return;
      if (r == SendResult.sent) {
        Navigator.of(context).pop(true);
      } else {
        Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(result: r)));
      }
    } catch (e) {
      if (!mounted) return;
      if ((e is ApiError && _plateCodes.contains(e.code)) || invalidFields(e).contains('plate')) {
        setState(() => plateError = errorText(context, widget.state, e));
      } else {
        showError(context, widget.state, e);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    return Scaffold(
      appBar: AppBar(title: Text(l.claimTitle)),
      body: Form(
        key: _form,
        child: ListView(
          key: const Key('claim-form'),
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
          children: [
            DCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  FieldLabel(l.claimPlate, required: true),
                  TextFormField(
                    key: const Key('claim-plate'),
                    controller: _plate,
                    textDirection: TextDirection.ltr,
                    textCapitalization: TextCapitalization.characters,
                    decoration: InputDecoration(
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
                  const SizedBox(height: 14),
                  FieldLabel(l.odometerPhoto, required: true),
                  PhotoTile(
                    key: const Key('claim-odo-photo'),
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
                    key: const Key('claim-km'),
                    controller: _km,
                    keyboardType: TextInputType.number,
                    textDirection: TextDirection.ltr,
                    style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w600, letterSpacing: 2),
                    inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(7)],
                    decoration: InputDecoration(
                      hintText: '000000',
                      hintTextDirection: TextDirection.ltr,
                      suffixText: l.km,
                    ),
                    validator: (v) => int.tryParse(v ?? '') == null ? l.kmInvalid : null,
                  ),
                  const SizedBox(height: 14),
                  FieldLabel(l.claimConditionPhotos),
                  GridView.count(
                    crossAxisCount: 2,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    mainAxisSpacing: 10,
                    crossAxisSpacing: 10,
                    childAspectRatio: 4 / 3,
                    children: [
                      for (var i = 0; i < photos.length; i++)
                        PhotoTile(
                          label: '${l.mntAddPhoto} ${i + 1} · ${l.mntTapToRemove}',
                          path: photos[i].path,
                          onTap: () => setState(() => photos.removeAt(i)),
                        ),
                      if (photos.length < maxPhotos)
                        PhotoTile(key: const Key('claim-photo'), label: l.mntAddPhoto, onTap: _addPhoto),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Banner2(text: l.claimIntro, icon: Icons.info_outline),
            const SizedBox(height: 20),
            BusyButton(key: const Key('send-claim'), label: l.claimSend, icon: Icons.send, onPressed: _send),
          ],
        ),
      ),
    );
  }
}
