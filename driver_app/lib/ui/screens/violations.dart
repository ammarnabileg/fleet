import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show NumberFormat;

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../../l10n/app_localizations.dart';
import '../photos.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'home.dart';

(String, BannerTone) violationStatus(AppLocalizations l, String status) => switch (status) {
  'objected' => (l.vioStatus_objected, BannerTone.warn),
  'upheld' => (l.vioStatus_upheld, BannerTone.danger),
  'overturned' => (l.vioStatus_overturned, BannerTone.success),
  _ => (l.vioStatus_approved, BannerTone.info),
};

String _money(String amount) => '\u2066${NumberFormat('#,##0.000', 'en').format(double.tryParse(amount) ?? 0)}\u2069';

/// The work violations recorded against the driver once the office approved them (FR-VIO-04): the penalty or a
/// warning, and an objection from here until the deadline (BR-09); the final decision with its reason.
class ViolationsScreen extends StatefulWidget {
  const ViolationsScreen({super.key, required this.state});

  final AppState state;

  @override
  State<ViolationsScreen> createState() => _ViolationsScreenState();
}

class _ViolationsScreenState extends State<ViolationsScreen> {
  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      await widget.state.loadViolations();
    } on ApiError {
      // offline: the last list stays
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final items = widget.state.violations;
    return Scaffold(
      appBar: AppBar(title: Text(l.violationsTitle)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(l.violationsIntro, style: const TextStyle(color: AppColors.muted, height: 1.6)),
            const SizedBox(height: 12),
            if (items.isEmpty) Text(l.violationsNone, style: const TextStyle(color: AppColors.muted)),
            for (final v in items) _ViolationCard(state: widget.state, violation: v, onChanged: _reload),
          ],
        ),
      ),
    );
  }
}

class _ViolationCard extends StatelessWidget {
  const _ViolationCard({required this.state, required this.violation, required this.onChanged});

  final AppState state;
  final DriverViolation violation;
  final Future<void> Function() onChanged;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final v = violation;
    final (label, tone) = violationStatus(l, v.status);
    final amount = double.tryParse(v.amount ?? '') ?? 0;
    final lines = [
      when(context, v.occurredAt),
      if (v.description != null) v.description!,
      if (v.reference != null) l.vioReference(v.reference!),
      amount > 0 ? l.vioPenalty(_money(v.amount!)) : l.vioWarning,
      if (v.objection != null) l.vioYourObjection(v.objection!),
      if (v.finalNote != null) l.vioDecision(v.finalNote!),
    ];
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    l.vioTitle('${v.number}', v.name(state.lang)),
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                Pill(label, tone: tone),
              ],
            ),
            const SizedBox(height: 6),
            Text(lines.join('\n'), style: const TextStyle(height: 1.6, color: AppColors.muted)),
            if (v.canObject) ...[
              const SizedBox(height: 10),
              Text(l.vioObjectUntil(when(context, v.deadline!)), style: const TextStyle(fontSize: 13)),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                key: Key('object-${v.number}'),
                icon: const Icon(Icons.gavel_outlined),
                label: Text(l.vioObject),
                onPressed: () async {
                  await Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => ObjectionScreen(state: state, violation: v),
                    ),
                  );
                  await onChanged();
                },
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// His objection: why the violation is not his (required), and a screenshot from the phone if he has one.
class ObjectionScreen extends StatefulWidget {
  const ObjectionScreen({super.key, required this.state, required this.violation});

  final AppState state;
  final DriverViolation violation;

  @override
  State<ObjectionScreen> createState() => _ObjectionScreenState();
}

class _ObjectionScreenState extends State<ObjectionScreen> {
  final _form = GlobalKey<FormState>();
  final _text = TextEditingController();
  TakenPhoto? file;

  Future<void> _pick() async {
    final p = await Photos.gallery();
    if (p != null) setState(() => file = p);
  }

  Future<void> _send() async {
    if (!_form.currentState!.validate()) return;
    try {
      final r = await widget.state.sendObjection(
        violationId: widget.violation.id,
        text: _text.text.trim(),
        filePath: file?.path,
      );
      if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(result: r)));
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final v = widget.violation;
    return Scaffold(
      appBar: AppBar(title: Text(l.vioObject)),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(
              l.vioTitle('${v.number}', v.name(widget.state.lang)),
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 6),
            Text(l.vioObjectIntro, style: const TextStyle(color: AppColors.muted, height: 1.6)),
            const SizedBox(height: 16),
            TextFormField(
              key: const Key('objection-text'),
              controller: _text,
              maxLines: 4,
              maxLength: 1000,
              decoration: InputDecoration(labelText: l.vioObjectionText),
              validator: (x) => (x ?? '').trim().length < 3 ? l.required : null,
            ),
            const SizedBox(height: 8),
            SizedBox(
              height: 140,
              child: PhotoTile(
                key: const Key('objection-file'),
                label: l.vioObjectionFile,
                path: file?.path,
                onTap: _pick,
              ),
            ),
            const SizedBox(height: 22),
            BusyButton(key: const Key('send-objection'), label: l.send, icon: Icons.send, onPressed: _send),
          ],
        ),
      ),
    );
  }
}
