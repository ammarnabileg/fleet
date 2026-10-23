import 'package:flutter/material.dart';

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../theme.dart';
import '../../l10n/app_localizations.dart';
import '../widgets/common.dart';
import '../widgets/live_status.dart';
import 'home.dart';

IconData noticeIcon(String kind) => switch (kind) {
  'receipt_issued' => Icons.receipt_long_outlined,
  'report_corrected' || 'report_rejected' => Icons.assignment_late_outlined,
  'maintenance_ready' => Icons.car_repair,
  'maintenance_approved' || 'maintenance_rejected' => Icons.build_outlined,
  'accident_no_liability' || 'accident_charged' => Icons.car_crash_outlined,
  'fine_charged' => Icons.local_police_outlined,
  'deduction_added' => Icons.remove_circle_outline,
  'payslip_ready' => Icons.payments_outlined,
  'document_expiring' || 'document_expired' => Icons.badge_outlined,
  _ => categoryStyle(noticeCategory(kind)).$2,
};

/// The design's five groups of messages, each with its icon and accent: alerts; cash and reports; the car and
/// custody; maintenance and deductions; documents and payslip. A kind this app does not know is an alert.
String noticeCategory(String kind) {
  if (kind.startsWith('vehicle_')) return 'car';
  if (kind.startsWith('maintenance_') || kind.startsWith('accident_') || kind == 'fine_charged') return 'maintenance';
  if (kind == 'deduction_added') return 'maintenance';
  if (kind.startsWith('receipt_') || kind.startsWith('report_') || kind.startsWith('fuel_')) return 'cash';
  if (kind.startsWith('document_') || kind.startsWith('scheme_request_')) return 'documents';
  if (kind == 'payslip_ready' || kind == 'objection_updated') return 'documents';
  return 'alerts';
}

/// The group's accent (a readable shade on the light screen) and icon.
(Color, IconData) categoryStyle(String category) => switch (category) {
  'cash' => (const Color(0xFF7C3AED), Icons.account_balance_wallet_outlined),
  'car' => (const Color(0xFF1D4ED8), Icons.directions_car_outlined),
  'maintenance' => (const Color(0xFFB45309), Icons.build_outlined),
  'documents' => (const Color(0xFF0F766E), Icons.description_outlined),
  _ => (const Color(0xFFB91C1C), Icons.warning_amber_rounded),
};

String categoryLabel(AppLocalizations l, String category) => switch (category) {
  'cash' => l.noticeCatCash,
  'car' => l.noticeCatCar,
  'maintenance' => l.noticeCatMaintenance,
  'documents' => l.noticeCatDocuments,
  _ => l.noticeCatAlerts,
};

/// What the office and the system told the driver, newest first (BRD FR-NTF-01). Opening the screen marks them read.
class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key, required this.state});

  final AppState state;

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  Set<String> fresh = {}; // unread when the screen opened: they stay highlighted while it is open

  @override
  void initState() {
    super.initState();
    _reload(markRead: true);
  }

  Future<void> _reload({bool markRead = false}) async {
    try {
      await widget.state.loadNotices();
      fresh = {
        ...fresh,
        for (final n in widget.state.notices?.items ?? <DriverNotice>[])
          if (!n.read) n.id,
      };
      if (markRead) await widget.state.readNotices();
    } on ApiError {
      // offline: the last list stays
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final items = widget.state.notices?.items ?? <DriverNotice>[];
    return Scaffold(
      appBar: AppBar(title: Text(l.noticesTitle)),
      body: RefreshIndicator(
        onRefresh: () => _reload(markRead: true),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (items.isEmpty) Text(l.noticesNone, style: const TextStyle(color: AppColors.muted)),
            for (final n in items) ...[_NoticeItem(notice: n, fresh: fresh.contains(n.id)), const SizedBox(height: 10)],
          ],
        ),
      ),
    );
  }
}

/// One message, as the design draws it: the group's icon tile and accent, the group's name, the text, the time;
/// an unread one keeps its accent tint while the screen is open.
class _NoticeItem extends StatelessWidget {
  const _NoticeItem({required this.notice, required this.fresh});

  final DriverNotice notice;
  final bool fresh;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final category = noticeCategory(notice.kind);
    final (accent, _) = categoryStyle(category);
    final shown = accentFor(context, accent);
    return Semantics(
      container: true,
      child: AccentCard(
        key: Key('notice-${notice.id}'),
        accent: accent,
        icon: noticeIcon(notice.kind),
        iconKey: Key('notice-category-$category'),
        title: categoryLabel(l, category),
        titleColor: shown,
        subtitle: notice.message,
        highlight: fresh,
        meta: Text(when(context, notice.createdAt), style: const TextStyle(color: AppColors.muted, fontSize: 12)),
      ),
    );
  }
}
