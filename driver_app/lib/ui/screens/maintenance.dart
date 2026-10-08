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
import 'odometer.dart';

const maintenanceKinds = ['periodic', 'mechanical', 'electrical', 'tyres', 'battery', 'ac', 'bodywork', 'other'];

String maintenanceKind(AppLocalizations l, String kind) => switch (kind) {
  'periodic' => l.mntKind_periodic,
  'mechanical' => l.mntKind_mechanical,
  'electrical' => l.mntKind_electrical,
  'tyres' => l.mntKind_tyres,
  'battery' => l.mntKind_battery,
  'ac' => l.mntKind_ac,
  'bodywork' => l.mntKind_bodywork,
  _ => l.mntKind_other,
};

/// The driver sees the center's work as one step ("at the center") until the vehicle is ready.
(String, BannerTone) maintenanceStatus(AppLocalizations l, String status) => switch (status) {
  'requested' => (l.mntStatus_requested, BannerTone.warn),
  'approved' => (l.mntStatus_approved, BannerTone.info),
  'rejected' => (l.mntStatus_rejected, BannerTone.danger),
  'referred' => (l.mntStatus_referred, BannerTone.info),
  'ready' => (l.mntStatus_ready, BannerTone.success),
  'picked_up' => (l.mntStatus_picked_up, BannerTone.info),
  'closed' => (l.mntStatus_closed, BannerTone.info),
  'cancelled' => (l.mntStatus_cancelled, BannerTone.info),
  _ => (l.mntStatus_at_center, BannerTone.info),
};

/// A maintenance request for the vehicle the driver holds (type, description, camera photos), and the driver's
/// requests with their status: the center's address appears once the vehicle is referred, "ready" when it is.
class MaintenanceScreen extends StatefulWidget {
  const MaintenanceScreen({super.key, required this.state});

  final AppState state;

  @override
  State<MaintenanceScreen> createState() => _MaintenanceScreenState();
}

class _MaintenanceScreenState extends State<MaintenanceScreen> {
  static const maxPhotos = 4;
  final _form = GlobalKey<FormState>();
  final _description = TextEditingController();
  final _km = TextEditingController();
  String kind = 'mechanical';
  String? centerId; // straight to the center: the one he leaves the car at
  final photos = <TakenPhoto>[];

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      await widget.state.loadMaintenance();
    } on ApiError {
      // offline: the last list stays
    }
    if (mounted) setState(() {});
  }

  Future<void> _addPhoto() async {
    final p = await Photos.camera(context);
    if (p != null) setState(() => photos.add(p));
  }

  Future<void> _send() async {
    if (!_form.currentState!.validate()) return;
    try {
      final r = await widget.state.sendMaintenance(
        kind: kind,
        description: _description.text.trim(),
        km: int.tryParse(_km.text),
        photoPaths: [for (final p in photos) p.path],
        centerId: widget.state.maintenanceForm.direct ? centerId : null,
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
    final requests = widget.state.maintenance;
    final form = widget.state.maintenanceForm;
    final picked = [
      for (final c in form.centers)
        if (c.id == centerId) c,
    ].firstOrNull;
    return Scaffold(
      appBar: AppBar(title: Text(l.maintenanceTitle)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              for (final r in requests.where((r) => r.isReady)) ...[
                ReadyBanner(request: r, state: widget.state),
                const SizedBox(height: 12),
              ],
              if (custody == null)
                Banner2(text: l.mntNoVehicle, tone: BannerTone.info)
              else ...[
                Text(l.mntNew, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                Text(
                  form.direct ? l.mntDirectIntro : l.mntIntro,
                  style: const TextStyle(color: AppColors.muted, height: 1.6),
                ),
                const SizedBox(height: 16),
                if (form.direct) ...[
                  DropdownButtonFormField<String>(
                    key: const Key('mnt-center'),
                    initialValue: centerId,
                    isExpanded: true,
                    decoration: InputDecoration(labelText: l.mntCenter),
                    items: [
                      for (final c in form.centers)
                        DropdownMenuItem(
                          value: c.id,
                          child: Text(
                            [c.name, if (c.specialty != null) c.specialty!].join(' · '),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                    ],
                    onChanged: (v) => setState(() => centerId = v),
                    validator: (v) => v == null ? l.required : null,
                  ),
                  if (picked != null && (picked.address != null || picked.phone != null)) ...[
                    const SizedBox(height: 6),
                    Text(
                      [
                        picked.address,
                        if (picked.phone != null) '\u2066${picked.phone}\u2069',
                      ].whereType<String>().join(' · '),
                      key: const Key('mnt-center-where'),
                      style: const TextStyle(color: AppColors.muted, height: 1.5),
                    ),
                  ],
                  const SizedBox(height: 12),
                ],
                DropdownButtonFormField<String>(
                  key: const Key('mnt-kind'),
                  initialValue: kind,
                  decoration: InputDecoration(labelText: l.mntKind),
                  items: [
                    for (final k in maintenanceKinds) DropdownMenuItem(value: k, child: Text(maintenanceKind(l, k))),
                  ],
                  onChanged: (v) => setState(() => kind = v ?? kind),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  key: const Key('mnt-description'),
                  controller: _description,
                  maxLines: 3,
                  maxLength: 2000,
                  decoration: InputDecoration(labelText: l.mntDescription),
                  validator: (v) => (v ?? '').trim().isEmpty ? l.required : null,
                ),
                const SizedBox(height: 4),
                TextFormField(
                  key: const Key('mnt-km'),
                  controller: _km,
                  keyboardType: TextInputType.number,
                  textDirection: TextDirection.ltr,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(7)],
                  decoration: InputDecoration(labelText: l.mntOdometer, suffixText: '  ${l.km}'),
                ),
                const SizedBox(height: 16),
                Text(l.mntPhotos, style: const TextStyle(fontWeight: FontWeight.w600)),
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
                    if (photos.length < maxPhotos)
                      PhotoTile(key: const Key('mnt-photo'), label: l.mntAddPhoto, onTap: _addPhoto),
                  ],
                ),
                const SizedBox(height: 22),
                BusyButton(key: const Key('mnt-send'), label: l.send, icon: Icons.send, onPressed: _send),
              ],
              SectionTitle(l.maintenanceTitle),
              if (requests.isEmpty) Text(l.mntNone, style: const TextStyle(color: AppColors.muted)),
              for (final r in requests) _RequestTile(request: r),
            ],
          ),
        ),
      ),
    );
  }
}

class _RequestTile extends StatelessWidget {
  const _RequestTile({required this.request});

  final MaintenanceRequest request;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final (label, tone) = maintenanceStatus(l, request.status);
    final lines = [
      '${maintenanceKind(l, request.kind)} · \u2066${request.plate}\u2069 · ${when(context, request.createdAt)}',
      request.description,
      if (request.centerName != null) l.mntAtCenter(request.centerName!),
      if (request.rejectedReason != null) l.mntRejected(request.rejectedReason!),
    ];
    return Card(
      child: ListTile(
        title: Text(l.mntRequestNo('${request.number}')),
        subtitle: Text(lines.join('\n'), style: const TextStyle(height: 1.5)),
        isThreeLine: true,
        trailing: Pill(label, tone: tone),
      ),
    );
  }
}

/// "Your vehicle is ready at the center": where to collect it (home screen and the maintenance screen). Straight
/// to the center, he confirms the pickup himself and the car is his again.
class ReadyBanner extends StatelessWidget {
  const ReadyBanner({super.key, required this.request, required this.state});

  final MaintenanceRequest request;
  final AppState state;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final phone = request.centerPhone == null
        ? null
        : '\u2066${request.centerPhone}\u2069'; // a number reads left to right
    final where = [request.centerAddress, phone].whereType<String>().join(' · ');
    final banner = Banner2(
      text:
          l.mntReadyBanner('\u2066${request.plate}\u2069', request.centerName ?? '') +
          (where.isEmpty ? '' : '\n$where'),
      tone: BannerTone.success,
      icon: Icons.car_repair,
    );
    if (!state.maintenanceForm.direct) return banner;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        banner,
        const SizedBox(height: 8),
        FilledButton.icon(
          key: Key('mnt-picked-up-${request.number}'),
          icon: const Icon(Icons.key),
          label: Text(l.mntPickedUp),
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => OdometerScreen(state: state, kind: 'pickup', requestId: request.id),
            ),
          ),
        ),
      ],
    );
  }
}
