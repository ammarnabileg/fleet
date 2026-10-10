import 'package:flutter/material.dart';

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../theme.dart';
import '../widgets/common.dart';
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
  _ => Icons.notifications_outlined,
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
            for (final n in items)
              Card(
                key: Key('notice-${n.id}'),
                color: fresh.contains(n.id) ? AppColors.infoSoft : null,
                child: ListTile(
                  leading: Icon(noticeIcon(n.kind), color: AppColors.primary),
                  title: Text(n.message, style: const TextStyle(height: 1.5)),
                  subtitle: Text(when(context, n.createdAt)),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
