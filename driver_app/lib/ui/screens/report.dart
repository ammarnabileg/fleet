import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/state.dart';
import '../../core/models.dart';
import '../../core/outbox.dart';
import '../photos.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'home.dart';

/// The daily report: day (today or the two before), what the driver's platform asks (orders and cash for one, orders
/// and whether the platform counted the day for another), the delivery app's day summary screenshot. Today's report
/// after a started day also carries the end-of-day odometer photo and reading, sent first (BRD FR-DWR-02).
///
/// With [report], the same form corrects a report already sent: directly until it is approved, or, once approved, as
/// a request with its reason that the office decides (FR-DWR-06, BR-06). A day already reported opens that report
/// instead of a second one (UAT-04).
class ReportScreen extends StatefulWidget {
  const ReportScreen({super.key, required this.state, this.report, DateTime Function()? clock})
    : clock = clock ?? DateTime.now;

  final AppState state;
  final Report? report;
  final DateTime Function() clock;

  @override
  State<ReportScreen> createState() => _ReportScreenState();
}

class _ReportScreenState extends State<ReportScreen> {
  int daysBack = 0;
  final _orders = TextEditingController();
  final _cash = TextEditingController();
  final _notes = TextEditingController();
  final _form = GlobalKey<FormState>();
  TakenPhoto? shot;
  bool? validDay;
  TakenPhoto? odometer;
  final _km = TextEditingController();
  final _reason = TextEditingController();

  Report? get _editing => widget.report;
  bool get _endDue => _editing == null && daysBack == 0 && widget.state.endReadingDue;

  /// The day's work session this report is for: after ending the day the driver may start again, and each session
  /// sends its own report. A day before: the sessions the server counted for it.
  int get _session => daysBack == 0 ? widget.state.sessionsToday : (widget.state.today?.recent[_day(daysBack)] ?? 0);

  /// This session's report already sent (not refused): it is edited, never sent twice. A report of an earlier
  /// session today is not it: the new one adds to it.
  Report? get _sent {
    final day = _day(daysBack);
    for (final r in widget.state.reports) {
      if (r.businessDate == day && r.status != 'rejected' && r.session >= _session) return r;
    }
    return null;
  }

  /// What the earlier sessions of today already reported (their orders), when this report adds to them.
  int? get _earlierOrders {
    final day = _day(daysBack);
    final earlier = [
      for (final r in widget.state.reports)
        if (r.businessDate == day && r.status != 'rejected' && r.session < _session) r,
    ];
    return earlier.isEmpty ? null : earlier.fold<int>(0, (n, r) => n + (r.orders ?? 0));
  }

  @override
  void initState() {
    super.initState();
    final r = _editing;
    if (r != null) {
      _orders.text = r.orders?.toString() ?? '';
      _cash.text = r.status == 'approved' ? (r.approvedCash ?? r.cash) : r.cash;
      validDay = r.validDay;
      _notes.text = r.notes ?? '';
    }
  }

  Future<void> _change(Report r) async {
    final asks = widget.state.reportForm.fields;
    try {
      final result = await widget.state.changeReport(
        r,
        orders: asks.contains('orders') ? int.parse(_orders.text) : null,
        cash: asks.contains('cash') ? double.parse(_cash.text).toStringAsFixed(3) : null,
        validDay: asks.contains('valid_day') ? validDay : null,
        screenshotPath: shot?.path,
        notes: _notes.text.trim().isEmpty ? null : _notes.text.trim(),
        reason: r.editable ? null : _reason.text.trim(),
      );
      if (mounted) {
        Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(result: result)));
      }
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  /// Business days follow Kuwait time (UTC+3, no daylight saving), like the server.
  String _day(int back) {
    final k = widget.clock().toUtc().add(const Duration(hours: 3)).subtract(Duration(days: back));
    return '${k.year.toString().padLeft(4, '0')}-${k.month.toString().padLeft(2, '0')}-${k.day.toString().padLeft(2, '0')}';
  }

  static final _amount = RegExp(r'^\d{1,6}(\.\d{1,3})?$');

  void _open(Report r) => Navigator.of(context).pushReplacement(
    MaterialPageRoute(
      builder: (_) => ReportScreen(state: widget.state, report: r),
    ),
  );

  Future<void> _send() async {
    final editing = _editing;
    if (editing != null) {
      if (_form.currentState!.validate()) await _change(editing);
      return;
    }
    final endDue = _endDue;
    if (endDue && odometer == null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(context.l.photoRequired)));
      return;
    }
    if (!_form.currentState!.validate()) return;
    final asks = widget.state.reportForm.fields;
    try {
      var waiting = false;
      if (endDue) {
        final reading = await widget.state.sendReading(
          kind: 'end_day',
          km: int.parse(_km.text),
          photoPath: odometer!.path,
          takenAt: odometer!.takenAt,
          lat: odometer!.lat,
          lng: odometer!.lng,
        );
        waiting = reading == SendResult.queued;
      }
      final r = await widget.state.sendReport(
        queueOnly: waiting,
        businessDate: _day(daysBack),
        orders: asks.contains('orders') ? int.parse(_orders.text) : null,
        cash: asks.contains('cash') ? double.parse(_cash.text).toStringAsFixed(3) : null,
        validDay: asks.contains('valid_day') ? validDay : null,
        screenshotPath: shot?.path,
        notes: _notes.text.trim().isEmpty ? null : _notes.text.trim(),
        session: _session,
      );
      if (mounted) Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(result: r)));
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final reports = widget.state.reports;
    final asks = widget.state.reportForm.fields;
    final editing = _editing;
    final sent = editing == null ? _sent : null;
    return Scaffold(
      appBar: AppBar(
        title: Text(
          editing == null
              ? l.reportTitle
              : editing.editable
              ? l.editReportTitle
              : l.changeReportTitle,
        ),
      ),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(l.reportDate, style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            if (editing == null)
              SegmentedButton<int>(
                segments: [
                  ButtonSegment(value: 0, label: Text(l.today)),
                  ButtonSegment(value: 1, label: Text(l.yesterday)),
                  ButtonSegment(value: 2, label: Text(l.dayBefore)),
                ],
                selected: {daysBack},
                onSelectionChanged: (s) => setState(() => daysBack = s.first),
              ),
            const SizedBox(height: 6),
            Text(
              '\u2066${editing?.businessDate ?? _day(daysBack)}\u2069',
              style: const TextStyle(color: AppColors.muted),
            ),
            if (editing != null && editing.status == 'returned' && editing.reviewNote != null) ...[
              const SizedBox(height: 12),
              Banner2(text: l.returnedNote(editing.reviewNote!), tone: BannerTone.warn, icon: Icons.undo),
            ],
            if (editing != null && !editing.editable) ...[
              const SizedBox(height: 12),
              Banner2(key: const Key('change-intro'), text: l.changeReportIntro, icon: Icons.info_outline),
            ],
            // UAT-04: this day is reported already; it is edited, not sent twice
            if (sent != null) ...[
              const SizedBox(height: 16),
              Banner2(key: const Key('report-exists'), text: l.reportExistsForDay, tone: BannerTone.warn),
              const SizedBox(height: 10),
              if (sent.status != 'approved' || !sent.changePending)
                OutlinedButton.icon(
                  key: const Key('edit-sent'),
                  icon: const Icon(Icons.edit_outlined),
                  label: Text(sent.editable ? l.editReport : l.changeReportTitle),
                  onPressed: () => _open(sent),
                ),
            ],
            if (sent == null) ...[
              if (editing == null && _earlierOrders != null) ...[
                const SizedBox(height: 16),
                Banner2(
                  key: const Key('report-adds'),
                  text: l.reportAddsToDay('\u2066${_earlierOrders!}\u2069'),
                  icon: Icons.add_circle_outline,
                ),
              ],
              if (_endDue) ...[
                const SizedBox(height: 16),
                Banner2(key: const Key('end-reading'), text: l.endReadingIntro, icon: Icons.speed),
                const SizedBox(height: 10),
                SizedBox(
                  width: 180,
                  child: PhotoTile(
                    key: const Key('end-photo'),
                    label: l.odometerPhoto,
                    path: odometer?.path,
                    onTap: () async {
                      final p = await Photos.camera(context);
                      if (p != null) setState(() => odometer = p);
                    },
                  ),
                ),
                const SizedBox(height: 10),
                TextFormField(
                  key: const Key('end-km'),
                  controller: _km,
                  keyboardType: TextInputType.number,
                  textDirection: TextDirection.ltr,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(7)],
                  decoration: InputDecoration(labelText: l.odometerKm, suffixText: l.km),
                  validator: (v) => int.tryParse(v ?? '') == null ? l.kmInvalid : null,
                ),
              ],
              if (asks.contains('valid_day')) ...[
                const SizedBox(height: 16),
                Text(l.validDayQuestion, style: const TextStyle(fontWeight: FontWeight.w600)),
                const SizedBox(height: 8),
                FormField<bool>(
                  key: const Key('valid-day'),
                  validator: (_) => validDay == null ? l.required : null,
                  builder: (field) => Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SegmentedButton<bool>(
                        emptySelectionAllowed: true,
                        segments: [
                          ButtonSegment(value: true, label: Text(l.validDayYes), icon: const Icon(Icons.check)),
                          ButtonSegment(value: false, label: Text(l.validDayNo), icon: const Icon(Icons.close)),
                        ],
                        selected: {?validDay},
                        onSelectionChanged: (s) {
                          setState(() => validDay = s.isEmpty ? null : s.first);
                          field.didChange(validDay);
                        },
                      ),
                      if (field.hasError)
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text(field.errorText!, style: const TextStyle(color: AppColors.danger, fontSize: 12)),
                        ),
                    ],
                  ),
                ),
              ],
              if (asks.contains('orders')) ...[
                const SizedBox(height: 16),
                TextFormField(
                  key: const Key('orders'),
                  controller: _orders,
                  keyboardType: TextInputType.number,
                  textDirection: TextDirection.ltr,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(4)],
                  decoration: InputDecoration(labelText: l.ordersCount),
                  validator: (v) => int.tryParse(v ?? '') == null ? l.required : null,
                ),
              ],
              if (asks.contains('cash')) ...[
                const SizedBox(height: 12),
                TextFormField(
                  key: const Key('cash'),
                  controller: _cash,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  textDirection: TextDirection.ltr,
                  inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.]'))],
                  decoration: InputDecoration(labelText: l.cashAmount, suffixText: '  ${l.kwd}', hintText: '0.000'),
                  validator: (v) => _amount.hasMatch((v ?? '').trim()) ? null : l.cashInvalid,
                ),
              ],
              const SizedBox(height: 16),
              Text(
                editing == null ? l.screenshot : l.newScreenshotOptional,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: 180,
                child: PhotoTile(
                  key: const Key('screenshot'),
                  label: l.fromGallery,
                  path: shot?.path,
                  onTap: () async {
                    final p = await Photos.gallery();
                    if (p != null) setState(() => shot = p);
                  },
                ),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _notes,
                maxLines: 2,
                decoration: InputDecoration(labelText: l.notes),
              ),
              if (editing != null && !editing.editable) ...[
                const SizedBox(height: 12),
                TextFormField(
                  key: const Key('change-reason'),
                  controller: _reason,
                  maxLines: 2,
                  decoration: InputDecoration(labelText: l.changeReason),
                  validator: (v) => (v ?? '').trim().length < 3 ? l.required : null,
                ),
              ],
              const SizedBox(height: 22),
              BusyButton(key: const Key('send-report'), label: l.send, icon: Icons.send, onPressed: _send),
            ],
            if (editing == null && reports.isNotEmpty) ...[
              SectionTitle(l.recentReports),
              for (final r in reports.take(10))
                Card(
                  child: ListTile(
                    key: Key(r.session > 1 ? 'report-${r.businessDate}-${r.session}' : 'report-${r.businessDate}'),
                    onTap: r.status == 'rejected' || r.changePending ? null : () => _open(r),
                    title: Text(
                      [
                        '\u2066${r.businessDate}\u2069',
                        if (r.session > 1) l.reportSession('${r.session}'),
                        if (r.validDay != null) r.validDay! ? l.validDayYes : l.validDayNo,
                        '${r.orders ?? '—'}',
                        if (asks.contains('cash')) money(r.cash, l.kwd),
                      ].join(' · '),
                    ),
                    subtitle: r.changePending
                        ? Text(l.changePending)
                        : r.reviewNote != null
                        ? Text(r.reviewNote!)
                        : (r.approvedCash != null && r.approvedCash != r.cash
                              ? Text(l.approvedCash(money(r.approvedCash!, l.kwd)))
                              : null),
                    trailing: Pill(
                      switch (r.status) {
                        'approved' => l.status_approved,
                        'rejected' => l.status_rejected,
                        'returned' => l.status_returned,
                        _ => l.status_submitted,
                      },
                      tone: switch (r.status) {
                        'approved' => BannerTone.success,
                        'rejected' => BannerTone.danger,
                        _ => BannerTone.warn,
                      },
                    ),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
