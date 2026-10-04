import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/state.dart';
import '../photos.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'home.dart';

/// The daily report: day (today or the two before), orders, cash, the delivery app's summary screenshot.
class ReportScreen extends StatefulWidget {
  const ReportScreen({super.key, required this.state, DateTime Function()? clock}) : clock = clock ?? DateTime.now;

  final AppState state;
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

  /// Business days follow Kuwait time (UTC+3, no daylight saving), like the server.
  String _day(int back) {
    final k = widget.clock().toUtc().add(const Duration(hours: 3)).subtract(Duration(days: back));
    return '${k.year.toString().padLeft(4, '0')}-${k.month.toString().padLeft(2, '0')}-${k.day.toString().padLeft(2, '0')}';
  }

  static final _amount = RegExp(r'^\d{1,6}(\.\d{1,3})?$');

  Future<void> _send() async {
    if (!_form.currentState!.validate()) return;
    try {
      final r = await widget.state.sendReport(
        businessDate: _day(daysBack),
        orders: int.parse(_orders.text),
        cash: double.parse(_cash.text).toStringAsFixed(3),
        screenshotPath: shot?.path,
        notes: _notes.text.trim().isEmpty ? null : _notes.text.trim(),
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
    return Scaffold(
      appBar: AppBar(title: Text(l.reportTitle)),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(l.reportDate, style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
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
            Text('\u2066${_day(daysBack)}\u2069', style: const TextStyle(color: AppColors.muted)),
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
            const SizedBox(height: 16),
            Text(l.screenshot, style: const TextStyle(fontWeight: FontWeight.w600)),
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
            const SizedBox(height: 22),
            BusyButton(key: const Key('send-report'), label: l.send, icon: Icons.send, onPressed: _send),
            if (reports.isNotEmpty) ...[
              SectionTitle(l.recentReports),
              for (final r in reports.take(10))
                Card(
                  child: ListTile(
                    title: Text('\u2066${r.businessDate}\u2069 · ${r.orders ?? '—'} · ${money(r.cash, l.kwd)}'),
                    subtitle: r.reviewNote != null
                        ? Text(r.reviewNote!)
                        : (r.approvedCash != null && r.approvedCash != r.cash
                              ? Text(l.approvedCash(money(r.approvedCash!, l.kwd)))
                              : null),
                    trailing: Pill(
                      switch (r.status) {
                        'approved' => l.status_approved,
                        'rejected' => l.status_rejected,
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
