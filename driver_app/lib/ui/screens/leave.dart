import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../../l10n/app_localizations.dart';
import '../photos.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'home.dart';

String _date(DateTime d) => '\u2066${DateFormat('dd-MM-yyyy', 'en').format(d)}\u2069';

/// The paid and unpaid parts of a leave's days, as the office will count them.
String leaveSplit(AppLocalizations l, List<PayPart> split) => [
  for (final p in split)
    p.payPercent == 0
        ? l.leaveUnpaidPart('\u2066${p.days}\u2069')
        : l.leavePaidPart('\u2066${p.days}\u2069', '\u2066${p.payPercent}\u2069'),
].join(' + ');

/// «طلب تغيب»: the leave types he may take now (with what is left), the days, the reason, an attachment where the
/// type needs one (a medical certificate: camera or gallery), and the date the office's follow-up counts from. The
/// server's preview shows the days counted and their pay before he sends; offline the request is queued and checked
/// when it arrives. Below: his requests, the office's decision and reason, and «withdraw» while one waits.
class LeaveScreen extends StatefulWidget {
  const LeaveScreen({super.key, required this.state});

  final AppState state;

  @override
  State<LeaveScreen> createState() => _LeaveScreenState();
}

class _LeaveScreenState extends State<LeaveScreen> {
  final _form = GlobalKey<FormState>();
  final _reason = TextEditingController();
  String? kind;
  late DateTime from;
  late DateTime to;
  late DateTime followupFrom;
  TakenPhoto? attachment;
  bool _attachmentMissing = false;
  LeavePreview? preview;
  bool previewOffline = false;
  int _previewTicket = 0;

  @override
  void initState() {
    super.initState();
    final now = DateTime.now();
    from = to = followupFrom = DateTime(now.year, now.month, now.day);
    _reload();
  }

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  Future<void> _reload() async {
    try {
      await widget.state.loadLeaves();
    } on ApiError {
      // offline: the last answer stays
    }
    if (mounted) setState(() {});
  }

  LeaveType? get _type => widget.state.leaves?.types.where((t) => t.code == kind).firstOrNull;

  Future<void> _preview() async {
    if (kind == null || to.isBefore(from)) return;
    final ticket = ++_previewTicket;
    try {
      final p = await widget.state.previewLeave(kind: kind!, from: from, to: to);
      if (!mounted || ticket != _previewTicket) return;
      setState(() {
        preview = p;
        previewOffline = p == null;
      });
    } catch (e) {
      if (mounted && ticket == _previewTicket) showError(context, widget.state, e);
    }
  }

  Future<DateTime?> _pick(DateTime initial, {int back = 30}) {
    final now = DateTime.now();
    return showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: now.subtract(Duration(days: back)),
      lastDate: now.add(const Duration(days: 365)),
    );
  }

  Future<void> _attach(bool camera) async {
    final p = camera ? await Photos.camera(context) : await Photos.gallery();
    if (p != null) {
      setState(() {
        attachment = p;
        _attachmentMissing = false;
      });
    }
  }

  Future<void> _send() async {
    final ok = _form.currentState!.validate();
    setState(() => _attachmentMissing = (_type?.requiresAttachment ?? false) && attachment == null);
    if (!ok || _attachmentMissing) return;
    final reason = _reason.text.trim();
    try {
      final r = await widget.state.sendLeave(
        kind: kind!,
        from: from,
        to: to,
        followupFrom: followupFrom,
        reason: reason.isEmpty ? null : reason,
        attachmentPath: attachment?.path,
      );
      if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(result: r)));
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  Widget _dateTile(String key, String label, DateTime value, ValueChanged<DateTime> onPicked, {int back = 30}) =>
      ListTile(
        key: Key(key),
        contentPadding: EdgeInsets.zero,
        title: Text(label),
        subtitle: Text(_date(value)),
        trailing: const Icon(Icons.calendar_month),
        onTap: () async {
          final d = await _pick(value, back: back);
          if (d != null) onPicked(d);
        },
      );

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final leaves = widget.state.leaves;
    final types = leaves?.types ?? const <LeaveType>[];
    final requests = leaves?.requests ?? const <LeaveRequest>[];
    final lang = widget.state.lang;
    final p = preview;
    return Scaffold(
      appBar: AppBar(title: Text(l.leaves)),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
            children: [
              if (leaves != null && types.isEmpty)
                DCard(
                  key: const Key('leave-no-types'),
                  child: Banner2(text: l.leaveNoTypes, tone: BannerTone.neutral, icon: Icons.event_busy),
                )
              else if (leaves != null) ...[
                DCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      FieldLabel(l.leaveType, required: true),
                      DropdownButtonFormField<String>(
                        key: const Key('leave-type'),
                        initialValue: kind,
                        isExpanded: true,
                        items: [
                          for (final t in types)
                            DropdownMenuItem(
                              key: Key('leave-type-${t.code}'),
                              value: t.code,
                              child: Text(
                                [
                                  inLang(t.name, lang) ?? t.code,
                                  if (t.left != null) l.leaveLeft('\u2066${t.left}\u2069'),
                                ].join(' · '),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                        ],
                        validator: (v) => v == null ? l.leaveTypeMissing : null,
                        onChanged: (v) {
                          setState(() {
                            kind = v;
                            preview = null;
                          });
                          _preview();
                        },
                      ),
                      const SizedBox(height: 8),
                      _dateTile('leave-from', l.leaveFrom, from, (d) {
                        setState(() {
                          from = d;
                          if (to.isBefore(d)) to = d;
                        });
                        _preview();
                      }),
                      FormField<DateTime>(
                        validator: (_) => to.isBefore(from) ? l.leaveDatesInvalid : null,
                        builder: (field) => _dateTile('leave-to', l.leaveTo, to, (d) {
                          setState(() => to = d);
                          field.didChange(d);
                          _preview();
                        }),
                      ),
                      if (p != null)
                        Container(
                          key: const Key('leave-preview'),
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: p.problems.isEmpty ? AppColors.successSoft : AppColors.warningSoft,
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                l.leavePreviewDays('\u2066${p.days}\u2069'),
                                style: const TextStyle(fontWeight: FontWeight.w600),
                              ),
                              Text(leaveSplit(l, p.split), key: const Key('leave-split')),
                              for (final x in p.problems)
                                Text(
                                  errorText(context, widget.state, ApiError(422, x.code, params: x.params)),
                                  key: Key('leave-problem-${x.code}'),
                                  style: const TextStyle(color: AppColors.danger, fontSize: 12.5),
                                ),
                            ],
                          ),
                        )
                      else if (previewOffline)
                        Text(
                          l.leavePreviewOffline,
                          key: const Key('leave-preview-offline'),
                          style: const TextStyle(color: AppColors.muted, fontSize: 12.5),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                DCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      FieldLabel(l.leaveAttachment, required: _type?.requiresAttachment ?? false),
                      Row(
                        children: [
                          Expanded(
                            child: PhotoTile(
                              key: const Key('leave-camera'),
                              label: attachment == null ? l.leaveCamera : l.mntTapToRemove,
                              path: attachment?.path,
                              onTap: attachment == null ? () => _attach(true) : () => setState(() => attachment = null),
                            ),
                          ),
                          if (attachment == null) ...[
                            const SizedBox(width: 10),
                            Expanded(
                              child: PhotoTile(
                                key: const Key('leave-gallery'),
                                label: l.leaveGallery,
                                icon: Icons.photo_library_outlined,
                                onTap: () => _attach(false),
                              ),
                            ),
                          ],
                        ],
                      ),
                      if (_attachmentMissing) ...[
                        const SizedBox(height: 6),
                        Text(
                          l.leaveAttachmentRequired,
                          key: const Key('leave-attachment-missing'),
                          style: const TextStyle(color: AppColors.danger, fontSize: 12.5),
                        ),
                      ],
                      const SizedBox(height: 14),
                      FieldLabel(l.leaveReason),
                      TextFormField(key: const Key('leave-reason'), controller: _reason, maxLines: 2, maxLength: 500),
                      _dateTile(
                        'leave-followup',
                        l.leaveFollowupFrom,
                        followupFrom,
                        (d) => setState(() => followupFrom = d),
                        back: 365,
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                BusyButton(key: const Key('leave-send'), label: l.leaveSend, icon: Icons.send, onPressed: _send),
              ],
              SectionTitle(l.leaveMine),
              if (requests.isEmpty)
                DCard(
                  child: Text(l.leaveNone, style: const TextStyle(color: AppColors.muted)),
                )
              else
                DCard.list(
                  child: Column(
                    children: [
                      for (final (i, r) in requests.indexed)
                        _RequestRow(
                          request: r,
                          lang: lang,
                          last: i == requests.length - 1,
                          onCancel: r.status == 'pending' ? () => _cancel(r) : null,
                        ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _cancel(LeaveRequest r) async {
    try {
      await widget.state.cancelLeave(r.id);
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
    if (mounted) setState(() {});
  }
}

class _RequestRow extends StatelessWidget {
  const _RequestRow({required this.request, required this.lang, required this.last, this.onCancel});

  final LeaveRequest request;
  final String lang;
  final bool last;
  final VoidCallback? onCancel;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final r = request;
    final (label, tone) = switch (r.status) {
      'approved' => (l.leaveStatus_approved, BannerTone.success),
      'rejected' => (l.leaveStatus_rejected, BannerTone.danger),
      'cancelled' => (l.leaveStatus_cancelled, BannerTone.neutral),
      _ => (l.leaveStatus_pending, BannerTone.warn),
    };
    return Column(
      children: [
        DRow(
          key: Key('leave-request-${r.id}'),
          divider: !last && onCancel == null,
          leading: const IconTile(Icons.event_busy),
          title: inLang(r.kindName, lang) ?? r.kind,
          subtitle: [
            r.from == r.to ? _date(r.from) : '${_date(r.from)} - ${_date(r.to)}',
            leaveSplit(l, r.split),
            if (r.decisionNote != null) l.leaveOfficeSays(r.decisionNote!),
          ].join(' · '),
          trailing: Pill(label, tone: tone),
        ),
        if (onCancel != null)
          Align(
            alignment: AlignmentDirectional.centerEnd,
            child: TextButton.icon(
              key: Key('leave-cancel-${r.id}'),
              onPressed: onCancel,
              icon: const Icon(Icons.undo, size: 18),
              label: Text(l.leaveCancel),
            ),
          ),
      ],
    );
  }
}
