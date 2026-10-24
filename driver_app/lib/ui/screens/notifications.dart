import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../core/models.dart';
import '../theme.dart';
import '../../l10n/app_localizations.dart';
import '../widgets/common.dart';
import '../../status/engine.dart';
import '../widgets/live_status.dart';
import 'accident.dart';
import 'home.dart';
import 'maintenance.dart';

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

/// A broadcast's style: its accent (a readable shade on the light screen) and icon. A style this app does not know
/// is drawn as information, the default icon.
(Color, IconData) broadcastStyle(String? style) => switch (style) {
  'announcement' => (const Color(0xFF7C3AED), Icons.campaign_outlined),
  'reminder' => (const Color(0xFFB45309), Icons.alarm),
  'warning' => (const Color(0xFFC2410C), Icons.warning_amber_rounded),
  'urgent' => (const Color(0xFFB91C1C), Icons.priority_high_rounded),
  'success' => (const Color(0xFF15803D), Icons.celebration_outlined),
  _ => (const Color(0xFF1D4ED8), Icons.info_outline),
};

const broadcastLayouts = {'standard', 'highlight', 'compact'};
const broadcastTargets = {'cash', 'documents', 'maintenance', 'leave'};

String broadcastActionLabel(AppLocalizations l, DriverNotice n, String lang) {
  final own = n.actionLabel[lang];
  if (own != null && own.trim().isNotEmpty) return own;
  return switch (n.actionTarget) {
    'cash' => l.statusOpenCash,
    'documents' => l.statusOpenDocuments,
    'maintenance' => l.statusOpenMaintenance,
    _ => l.noticeOpenLeave,
  };
}

/// What a current card's button does: only the actions built into the app (the engine hides any other); a button
/// that opens a screen goes back to home first, then there.
Future<void> runStatusAction(BuildContext context, AppState state, String action, StatusCard card) async {
  final l = context.l;
  final messenger = ScaffoldMessenger.of(context);
  switch (action) {
    case 'open_cash':
      state.navigate('cash');
    case 'open_custody' || 'open_documents':
      state.navigate('documents');
    case 'open_maintenance':
      state.navigate('maintenance');
    case 'open_location_settings':
      await state.platform.openLocationSettings?.call();
    case 'call_supervisor':
      final phone = card.alert?.data['phone'];
      final ok = phone is String && await (state.platform.dial?.call(phone) ?? Future.value(false));
      if (!ok) messenger.showSnackBar(SnackBar(content: Text(l.statusDialFailed)));
    case 'acknowledge':
      final id = card.alert?.data['request_id'];
      if (id is String) {
        await state.acknowledgeContact(id);
        messenger.showSnackBar(SnackBar(content: Text(l.statusContactSent)));
      }
    case 'open_contact':
      final message = card.alert?.data['message'];
      if (message is String) messenger.showSnackBar(SnackBar(content: Text(message)));
  }
}

/// The notifications' own place (BRD FR-NTF-01): on top, pinned, «current» — what is going on now and is not over
/// (the live status's alerts with their buttons, the car's state, a car ready at its center, an accident waiting for
/// its police report); below, what the office and the system told the driver, newest first. Opening the screen marks
/// the messages read; the current ones stay until they are over.
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
    widget.state.addListener(_changed);
    _reload(markRead: true);
  }

  @override
  void dispose() {
    widget.state.removeListener(_changed);
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  Future<void> _reload({bool markRead = false}) async {
    final s = widget.state;
    try {
      await Future.wait([
        s.loadNotices(),
        if (s.shows('maintenance')) s.loadMaintenance(),
        if (s.shows('accidents')) s.loadAccidents(),
        s.loadLiveStatus(),
      ]);
      fresh = {
        ...fresh,
        for (final n in s.notices?.items ?? <DriverNotice>[])
          if (!n.read) n.id,
      };
      if (markRead) await s.readNotices();
    } on ApiError {
      // offline: the last list stays
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final s = widget.state;
    final items = s.notices?.items ?? <DriverNotice>[];
    final alerts = s.currentAlerts;
    final ready = s.readyRequests;
    final police = s.awaitingPolice;
    final hasCurrent = alerts.isNotEmpty || ready.isNotEmpty || police.isNotEmpty;
    return Scaffold(
      appBar: AppBar(title: Text(l.noticesTitle)),
      body: RefreshIndicator(
        onRefresh: () => _reload(markRead: true),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (hasCurrent) ...[
              Padding(
                key: const Key('notices-current'),
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(l.noticesCurrent, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
              ),
              for (final c in alerts) ...[
                StatusCardView(
                  key: Key('current-${c.key}'),
                  card: c,
                  onAction: (a, card) => runStatusAction(context, s, a, card),
                ),
                const SizedBox(height: 10),
              ],
              for (final r in ready) ...[
                InkWell(
                  key: Key('current-mnt-ready-${r.number}'),
                  onTap: () => s.navigate('maintenance'),
                  child: ReadyBanner(request: r, state: s),
                ),
                const SizedBox(height: 10),
              ],
              for (final a in police) ...[
                InkWell(
                  key: Key('police-banner-${a.number}'),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => AccidentScreen(state: s))),
                  child: Banner2(
                    text: l.accAwaitingPolice('${a.number}'),
                    tone: BannerTone.warn,
                    icon: Icons.description_outlined,
                  ),
                ),
                const SizedBox(height: 10),
              ],
              Padding(
                padding: const EdgeInsets.only(top: 8, bottom: 8),
                child: Text(l.noticesHistory, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
              ),
            ],
            if (items.isEmpty) Text(l.noticesNone, style: const TextStyle(color: AppColors.muted)),
            for (final n in items) ...[
              n.kind == 'broadcast'
                  ? BroadcastCard(notice: n, state: s, fresh: fresh.contains(n.id))
                  : _NoticeItem(notice: n, fresh: fresh.contains(n.id)),
              const SizedBox(height: 10),
            ],
          ],
        ),
      ),
    );
  }
}

/// A broadcast as the office styled it: the style's accent and icon, the layout (standard: title and text;
/// highlight: a big icon, the title and text, like the status card; compact: one line), the picture (downloaded
/// once and kept), the button to one of the app's screens. An unknown style or layout: the standard card.
class BroadcastCard extends StatelessWidget {
  const BroadcastCard({super.key, required this.notice, required this.state, this.fresh = false});

  final DriverNotice notice;
  final AppState state;
  final bool fresh;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final n = notice;
    final (accent, icon) = broadcastStyle(n.style);
    final a = accentFor(context, accent);
    final layout = broadcastLayouts.contains(n.layout) ? n.layout! : 'standard';
    final title = (n.title ?? '').isEmpty ? n.message : n.title!;
    final text = (n.title ?? '').isEmpty ? '' : (n.body ?? '');
    final time = Text(when(context, n.createdAt), style: const TextStyle(color: AppColors.muted, fontSize: 12));
    final target = broadcastTargets.contains(n.actionTarget) ? n.actionTarget : null;
    final button = target == null
        ? null
        : accentButton(
            context,
            key: Key('broadcast-action-$target'),
            accent: accent,
            label: broadcastActionLabel(l, n, state.lang),
            onPressed: () => state.navigate(target),
          );
    final image = n.image == null ? null : _BroadcastImage(state: state, sha: n.image!);
    final keyed = Key('broadcast-${n.id}');
    if (layout == 'compact') {
      return Semantics(
        container: true,
        child: Container(
          key: keyed,
          decoration: BoxDecoration(
            color: fresh ? a.withValues(alpha: 0.07) : Theme.of(context).cardColor,
            border: BorderDirectional(start: BorderSide(color: a, width: 3)),
            borderRadius: BorderRadius.circular(14),
            boxShadow: AppColors.shadowXs,
          ),
          padding: const EdgeInsetsDirectional.fromSTEB(12, 10, 12, 10),
          child: Row(
            key: const Key('broadcast-layout-compact'),
            children: [
              Icon(icon, color: a, size: 20, key: Key('broadcast-style-${n.style ?? 'info'}')),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
                ),
              ),
              if (button != null)
                TextButton(
                  key: Key('broadcast-action-$target'),
                  onPressed: () => state.navigate(target!),
                  style: TextButton.styleFrom(foregroundColor: a),
                  child: Text(broadcastActionLabel(l, n, state.lang)),
                )
              else
                time,
            ],
          ),
        ),
      );
    }
    if (layout == 'highlight') {
      return Semantics(
        container: true,
        child: Container(
          key: keyed,
          decoration: BoxDecoration(
            color: a.withValues(alpha: fresh ? 0.12 : 0.07),
            border: BorderDirectional(start: BorderSide(color: a, width: 3)),
            borderRadius: BorderRadius.circular(16),
            boxShadow: AppColors.shadowXs,
          ),
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 14),
          child: Column(
            key: const Key('broadcast-layout-highlight'),
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(color: a.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(18)),
                child: Icon(icon, color: a, size: 30, key: Key('broadcast-style-${n.style ?? 'info'}')),
              ),
              const SizedBox(height: 10),
              Text(
                title,
                textAlign: TextAlign.center,
                style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: a),
              ),
              if (text.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(text, textAlign: TextAlign.center, style: const TextStyle(fontSize: 13.5, height: 1.55)),
                ),
              ?image,
              if (button != null) ...[const SizedBox(height: 10), SizedBox(width: double.infinity, child: button)],
              const SizedBox(height: 6),
              time,
            ],
          ),
        ),
      );
    }
    return Semantics(
      container: true,
      child: AccentCard(
        key: keyed,
        accent: accent,
        icon: icon,
        iconKey: Key('broadcast-style-${n.style ?? 'info'}'),
        title: title,
        subtitle: text,
        highlight: fresh,
        extra: [
          const SizedBox.shrink(key: Key('broadcast-layout-standard')),
          ?image,
        ],
        meta: time,
        actions: [?button],
      ),
    );
  }
}

class _BroadcastImage extends StatelessWidget {
  const _BroadcastImage({required this.state, required this.sha});

  final AppState state;
  final String sha;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Uint8List?>(
      future: state.noticeImage(sha),
      builder: (context, snap) {
        final bytes = snap.data;
        if (bytes == null) return const SizedBox.shrink();
        return Padding(
          padding: const EdgeInsets.only(top: 8),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: Image.memory(
              bytes,
              key: const Key('broadcast-image'),
              height: 150,
              width: double.infinity,
              fit: BoxFit.cover,
              errorBuilder: (_, _, _) => const SizedBox.shrink(),
            ),
          ),
        );
      },
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
