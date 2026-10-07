import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show DateFormat, NumberFormat;

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../../l10n/app_localizations.dart';
import '../photos.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'home.dart';

/// The server's default for the photos an accident needs (several angles); the server enforces its own setting.
const accidentMinPhotos = 3;
const accidentMaxPhotos = 8;

/// The driver sees the office's steps as one ("under review") until the liability is decided.
(String, BannerTone) accidentStage(AppLocalizations l, String stage) => switch (stage) {
  'awaiting_outcome' => (l.accStage_outcome, BannerTone.warn),
  'outcome_recorded' => (l.accStage_recorded, BannerTone.info),
  'closed' => (l.accStage_closed, BannerTone.info),
  'cancelled' => (l.accStage_closed, BannerTone.info),
  _ => (l.accStage_review, BannerTone.info),
};

String accidentLiability(AppLocalizations l, Accident a) => switch (a.liability) {
  'none' => l.accLiability_none,
  'driver' => l.accLiability_driver,
  'shared' => l.accLiability_shared(_percent(a.liabilityPercent)),
  _ => '',
};

String _percent(String? p) => NumberFormat('0.##', 'en').format(double.tryParse(p ?? '') ?? 0);

String _money(String amount) => '\u2066${NumberFormat('#,##0.000', 'en').format(double.tryParse(amount) ?? 0)}\u2069';

/// Report an accident with the vehicle the driver holds: what happened, injuries, the other party, camera photos
/// from several angles, and the police report if it is already issued (otherwise later, from the list below).
/// Time and place are taken automatically. Below: the driver's accidents, their outcome and any deduction.
class AccidentScreen extends StatefulWidget {
  const AccidentScreen({super.key, required this.state});

  final AppState state;

  @override
  State<AccidentScreen> createState() => _AccidentScreenState();
}

class _AccidentScreenState extends State<AccidentScreen> {
  final _form = GlobalKey<FormState>();
  final _description = TextEditingController();
  final _injuriesNote = TextEditingController();
  final _otherParty = TextEditingController();
  final _policeNo = TextEditingController();
  final _openedAt = DateTime.now(); // the accident time: when the driver started the report
  final photos = <TakenPhoto>[];
  TakenPhoto? police;
  bool injuries = false;
  bool _photosMissing = false;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      await widget.state.loadAccidents();
    } on ApiError {
      // offline: the last list stays
    }
    if (mounted) setState(() {});
  }

  Future<void> _addPhoto() async {
    final p = await Photos.camera(context);
    if (p != null) setState(() => photos.add(p));
  }

  /// From the phone's files, not the camera (BRD FR-APP-06): the police hand it over as a paper or a file.
  Future<void> _takePolice() async {
    final p = await Photos.gallery();
    if (p != null) setState(() => police = p);
  }

  Future<void> _send() async {
    final ok = _form.currentState!.validate();
    setState(() => _photosMissing = photos.length < accidentMinPhotos);
    if (!ok || _photosMissing) return;
    final where = photos.where((p) => p.lat != null).firstOrNull;
    String? text(TextEditingController c) => c.text.trim().isEmpty ? null : c.text.trim();
    try {
      final r = await widget.state.sendAccident(
        occurredAt: _openedAt,
        lat: where?.lat,
        lng: where?.lng,
        description: _description.text.trim(),
        injuries: injuries,
        injuriesNote: injuries ? text(_injuriesNote) : null,
        otherParty: text(_otherParty),
        photoPaths: [for (final p in photos) p.path],
        policeReportPath: police?.path,
        policeReportNo: police == null ? null : text(_policeNo),
      );
      if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(result: r)));
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final custody = widget.state.today?.custody;
    final accidents = widget.state.accidents;
    return Scaffold(
      appBar: AppBar(title: Text(l.accidentsTitle)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              if (custody == null)
                Banner2(text: l.accNoVehicle, tone: BannerTone.info)
              else ...[
                Banner2(text: l.accEmergency, tone: BannerTone.danger, icon: Icons.local_hospital_outlined),
                const SizedBox(height: 14),
                Text(l.accNew, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                Text(l.accIntro, style: const TextStyle(color: AppColors.muted, height: 1.6)),
                const SizedBox(height: 16),
                TextFormField(
                  key: const Key('acc-description'),
                  controller: _description,
                  maxLines: 3,
                  maxLength: 2000,
                  decoration: InputDecoration(labelText: l.accDescription),
                  validator: (v) => (v ?? '').trim().isEmpty ? l.required : null,
                ),
                SwitchListTile(
                  key: const Key('acc-injuries'),
                  contentPadding: EdgeInsets.zero,
                  title: Text(l.accInjuries),
                  value: injuries,
                  onChanged: (v) => setState(() => injuries = v),
                ),
                if (injuries)
                  TextFormField(
                    key: const Key('acc-injuries-note'),
                    controller: _injuriesNote,
                    maxLines: 2,
                    maxLength: 2000,
                    decoration: InputDecoration(labelText: l.accInjuriesNote),
                  ),
                TextFormField(
                  key: const Key('acc-other-party'),
                  controller: _otherParty,
                  maxLines: 2,
                  maxLength: 2000,
                  decoration: InputDecoration(labelText: l.accOtherParty),
                ),
                const SizedBox(height: 12),
                Text(l.accPhotos('$accidentMinPhotos'), style: const TextStyle(fontWeight: FontWeight.w600)),
                if (_photosMissing) ...[
                  const SizedBox(height: 4),
                  Text(
                    l.accPhotosNeeded('$accidentMinPhotos'),
                    key: const Key('acc-photos-missing'),
                    style: const TextStyle(color: AppColors.danger),
                  ),
                ],
                const SizedBox(height: 8),
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
                    if (photos.length < accidentMaxPhotos)
                      PhotoTile(key: const Key('acc-photo'), label: l.mntAddPhoto, onTap: _addPhoto),
                  ],
                ),
                const SizedBox(height: 16),
                Text(l.accPoliceReport, style: const TextStyle(fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(l.accPoliceLater, style: const TextStyle(color: AppColors.muted, height: 1.6)),
                const SizedBox(height: 8),
                SizedBox(
                  height: 120,
                  child: PhotoTile(
                    key: const Key('acc-police'),
                    label: police == null ? l.accPoliceReport : l.mntTapToRemove,
                    path: police?.path,
                    onTap: police == null ? _takePolice : () => setState(() => police = null),
                  ),
                ),
                if (police != null)
                  TextFormField(
                    key: const Key('acc-police-no'),
                    controller: _policeNo,
                    textDirection: TextDirection.ltr,
                    decoration: InputDecoration(labelText: l.accPoliceReportNo),
                  ),
                const SizedBox(height: 22),
                BusyButton(key: const Key('acc-send'), label: l.send, icon: Icons.send, onPressed: _send),
              ],
              SectionTitle(l.accidentsTitle),
              if (accidents.isEmpty) Text(l.accNone, style: const TextStyle(color: AppColors.muted)),
              for (final a in accidents) AccidentTile(state: widget.state, accident: a, onChanged: _reload),
            ],
          ),
        ),
      ),
    );
  }
}

class AccidentTile extends StatelessWidget {
  const AccidentTile({super.key, required this.state, required this.accident, this.onChanged});

  final AppState state;
  final Accident accident;
  final VoidCallback? onChanged;

  Future<void> _sendPolice(BuildContext context) async {
    final photo = await Photos.gallery();
    if (photo == null || !context.mounted) return;
    try {
      final r = await state.sendPoliceReport(accidentId: accident.id, photoPath: photo.path);
      if (context.mounted) {
        await Navigator.of(context).push(MaterialPageRoute(builder: (_) => ResultScreen(result: r)));
      }
      onChanged?.call();
    } catch (e) {
      if (context.mounted) showError(context, state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final a = accident;
    final (label, tone) = accidentStage(l, a.stage);
    final d = a.deduction;
    final queued = state.queued.any((q) => q.kind == 'police_report' && q.payload['accident_id'] == a.id);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(l.accNo('${a.number}'), style: const TextStyle(fontWeight: FontWeight.w700)),
                ),
                Pill(label, tone: tone),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              '\u2066${a.plate}\u2069 · ${when(context, a.occurredAt)}',
              style: const TextStyle(color: AppColors.muted),
            ),
            const SizedBox(height: 4),
            Text(a.description, style: const TextStyle(height: 1.5)),
            if (a.liability != null) ...[
              const SizedBox(height: 8),
              Text(
                accidentLiability(l, a),
                key: Key('acc-liability-${a.number}'),
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: a.liability == 'none' ? AppColors.success : AppColors.danger,
                ),
              ),
            ],
            if (d != null) ...[
              const SizedBox(height: 6),
              Text(l.accDeduction(_money(d.total), '${d.installments}'), key: Key('acc-deduction-${a.number}')),
              for (final s in d.schedule)
                Text(
                  l.accInstallment(DateFormat('MM-yyyy', 'en').format(s.month), _money(s.amount)),
                  style: const TextStyle(color: AppColors.muted),
                ),
            ],
            if (a.awaitsPoliceReport) ...[
              const SizedBox(height: 10),
              queued
                  ? Text(l.outboxQueued, style: const TextStyle(color: AppColors.warning))
                  : BusyButton(
                      key: Key('acc-send-police-${a.number}'),
                      icon: Icons.description_outlined,
                      label: l.accSendPolice,
                      onPressed: () => _sendPolice(context),
                    ),
            ],
          ],
        ),
      ),
    );
  }
}
