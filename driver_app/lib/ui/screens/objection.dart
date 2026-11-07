import 'package:flutter/material.dart';

import '../../app/state.dart';
import '../../core/models.dart';
import '../../core/outbox.dart' show SendResult;
import '../../l10n/app_localizations.dart';
import '../photos.dart';
import '../theme.dart';
import '../widgets/common.dart';

String _month(String iso) => '\u2066${iso.substring(0, 7)}\u2069';

(String, BannerTone) objectionStatus(AppLocalizations l, String status) => switch (status) {
  'in_review' => (l.objectionStatus_in_review, BannerTone.info),
  'accepted' => (l.objectionStatus_accepted, BannerTone.success),
  'rejected' => (l.objectionStatus_rejected, BannerTone.danger),
  'closed' => (l.objectionStatus_closed, BannerTone.info),
  _ => (l.objectionStatus_open, BannerTone.warn),
};

/// What the driver objects to, in his words: the whole payslip, or the line's label and amount.
String objectionSubject(AppLocalizations l, {String? label, String? amount}) =>
    label == null ? l.objectionWhole : (amount == null ? label : '$label · ${money(amount, l.kwd)}');

/// The objection form: his reason (required) and, if he has one, a photo from the camera or the gallery. Sent to the
/// office through the outbox; the approved payslip itself never changes.
class ObjectionScreen extends StatefulWidget {
  const ObjectionScreen({
    super.key,
    required this.state,
    required this.payslip,
    this.itemCode,
    this.label,
    this.amount,
  });

  final AppState state;
  final Payslip payslip;
  final String? itemCode; // none: the whole payslip
  final String? label;
  final String? amount;

  @override
  State<ObjectionScreen> createState() => _ObjectionScreenState();
}

class _ObjectionScreenState extends State<ObjectionScreen> {
  final _form = GlobalKey<FormState>();
  final _reason = TextEditingController();
  TakenPhoto? _photo;

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  Future<void> _pick(Future<TakenPhoto?> Function() from) async {
    final p = await from();
    if (p != null && mounted) setState(() => _photo = p);
  }

  Future<void> _send() async {
    final l = context.l;
    if (!_form.currentState!.validate()) return;
    try {
      final r = await widget.state.sendObjection(
        runId: widget.payslip.runId!,
        itemCode: widget.itemCode,
        reason: _reason.text.trim(),
        attachmentPath: _photo?.path,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(r == SendResult.sent ? l.objectionSent : l.objectionQueued)));
      Navigator.of(context).pop(r);
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    return Scaffold(
      appBar: AppBar(title: Text(l.objectionTitle)),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(_month(widget.payslip.month), style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            const SizedBox(height: 4),
            Text(
              l.objectionOn(objectionSubject(l, label: widget.label, amount: widget.amount)),
              key: const Key('objection-subject'),
              style: const TextStyle(color: AppColors.muted),
            ),
            const SizedBox(height: 16),
            TextFormField(
              key: const Key('objection-reason'),
              controller: _reason,
              minLines: 3,
              maxLines: 6,
              maxLength: 1000,
              decoration: InputDecoration(labelText: l.objectionReason),
              validator: (v) => (v ?? '').trim().length < 3 ? l.objectionReasonShort : null,
            ),
            const SizedBox(height: 8),
            Text(l.objectionFile, style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            if (_photo != null)
              SizedBox(
                width: 140,
                child: PhotoTile(
                  key: const Key('objection-photo'),
                  label: '1',
                  path: _photo!.path,
                  onTap: () => setState(() => _photo = null),
                ),
              )
            else
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      key: const Key('objection-camera'),
                      onPressed: () => _pick(() => Photos.camera(context)),
                      icon: const Icon(Icons.photo_camera_outlined),
                      label: Text(l.objectionCamera),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: OutlinedButton.icon(
                      key: const Key('objection-gallery'),
                      onPressed: () => _pick(Photos.gallery),
                      icon: const Icon(Icons.photo_library_outlined),
                      label: Text(l.objectionGallery),
                    ),
                  ),
                ],
              ),
            const SizedBox(height: 22),
            BusyButton(key: const Key('send-objection'), label: l.send, icon: Icons.send, onPressed: _send),
          ],
        ),
      ),
    );
  }
}

/// One of his objections: the month and what it is about, its status, and the office's answer.
class ObjectionTile extends StatelessWidget {
  const ObjectionTile({super.key, required this.objection, required this.label});

  final Objection objection;
  final String label; // what it is about, as the payslip calls it

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final o = objection;
    final (status, tone) = objectionStatus(l, o.status);
    return Card(
      key: Key('objection-${o.id}'),
      child: ListTile(
        title: Text('${_month(o.month)} · $label'),
        subtitle: Text(
          [
            o.reason,
            if (o.response != null) l.objectionResponse(o.response!),
            if (o.actionTaken != null) l.objectionAction(o.actionTaken!),
          ].join('\n'),
        ),
        isThreeLine: o.response != null || o.actionTaken != null,
        trailing: Pill(status, tone: tone),
      ),
    );
  }
}
