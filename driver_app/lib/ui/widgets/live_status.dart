import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../status/engine.dart';
import '../theme.dart';
import 'common.dart';

/// The icons the templates may name: anything else is the default one.
const statusIcons = <String, IconData>{
  'work': Icons.directions_car_filled_outlined,
  'off': Icons.nightlight_outlined,
  'car': Icons.directions_car_outlined,
  'wrench': Icons.build_outlined,
  'breakdown': Icons.car_crash_outlined,
  'wallet': Icons.account_balance_wallet_outlined,
  'phone': Icons.phone_in_talk_outlined,
  'location': Icons.location_on_outlined,
  'location_off': Icons.location_off_outlined,
  'document': Icons.description_outlined,
  'warning': Icons.warning_amber_rounded,
  'info': Icons.info_outline,
  'check': Icons.check_circle_outline,
  'clock': Icons.schedule,
};

IconData statusIcon(String name) => statusIcons[name] ?? Icons.info_outline;

String actionLabel(AppLocalizations l, String action) => switch (action) {
  'open_cash' => l.statusOpenCash,
  'open_custody' => l.statusOpenCustody,
  'open_contact' => l.statusOpenContact,
  'call_supervisor' => l.statusCall,
  'open_location_settings' => l.statusCheckSettings,
  'open_maintenance' => l.statusOpenMaintenance,
  'open_documents' => l.statusOpenDocuments,
  _ => l.statusDone,
};

String _hm(DateTime t) {
  final l = t.toLocal();
  return '\u2066${l.hour.toString().padLeft(2, '0')}:${l.minute.toString().padLeft(2, '0')}\u2069';
}

/// The status area of the home screen: the shift card only (the work state, the real tracking state) and, offline, a
/// clear line with the time of the last update. Alerts and the car's state are never drawn here: they are system
/// notifications and the inbox's «current» section (StatusCardView there).
class LiveStatusPanel extends StatelessWidget {
  const LiveStatusPanel({super.key, required this.view, this.sessionsToday = 0});

  final StatusView view;
  final int sessionsToday;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final still = MediaQuery.of(context).disableAnimations;
    final duration = still ? Duration.zero : const Duration(milliseconds: 280);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (view.offline && view.lastUpdate != null) ...[
          Banner2(
            key: const Key('status-offline'),
            text: l.offlineSince(_hm(view.lastUpdate!)),
            tone: BannerTone.warn,
            icon: Icons.cloud_off_outlined,
          ),
          const SizedBox(height: 10),
        ],
        AnimatedSwitcher(
          duration: duration,
          child: _ShiftCard(
            key: ValueKey('shift-${view.shift.code}-${view.tracking}'),
            card: view.shift,
            tracking: view.tracking,
            sessionsToday: sessionsToday,
          ),
        ),
      ],
    );
  }
}

/// A colour of the design's palette made for a dark screen (#67e7b4, #8dc8ff, ...) has a readable shade for the
/// app's light one: the templates' colours are those shades, a dark theme lightens them.
Color accentFor(BuildContext context, Color c) {
  if (Theme.of(context).brightness != Brightness.dark) return c;
  return Color.lerp(c, Colors.white, 0.45)!;
}

/// The design's card: an accent bar at its start, an icon tile tinted with the accent, the title, the text, a meta
/// row, and the actions as tinted buttons. It slides in when it appears, unless the phone asks for less motion.
class AccentCard extends StatelessWidget {
  const AccentCard({
    super.key,
    required this.accent,
    required this.icon,
    required this.title,
    this.subtitle,
    this.titleColor,
    this.leadingTitle,
    this.extra = const [],
    this.meta,
    this.actions = const [],
    this.iconKey,
    this.highlight = false,
  });

  final Color accent;
  final IconData icon;
  final String title;
  final String? subtitle;
  final Color? titleColor;
  final Widget? leadingTitle;
  final List<Widget> extra;
  final Widget? meta;
  final List<Widget> actions;
  final Key? iconKey;
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    final a = accentFor(context, accent);
    final dark = Theme.of(context).brightness == Brightness.dark;
    final card = Container(
      decoration: BoxDecoration(
        color: highlight ? a.withValues(alpha: 0.07) : (dark ? const Color(0xFF1D2631) : AppColors.surface),
        border: BorderDirectional(start: BorderSide(color: a, width: 3)),
        borderRadius: BorderRadius.circular(16),
        boxShadow: AppColors.shadowXs,
      ),
      padding: const EdgeInsetsDirectional.fromSTEB(14, 13, 14, 13),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(color: a.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(13)),
                child: Icon(icon, color: a, size: 22, key: iconKey),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        ?leadingTitle,
                        Flexible(
                          child: Text(
                            title,
                            style: TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 15,
                              height: 1.45,
                              color: titleColor,
                            ),
                          ),
                        ),
                      ],
                    ),
                    if (subtitle != null && subtitle!.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          subtitle!,
                          style: TextStyle(fontSize: 13, height: 1.55, color: dark ? null : AppColors.text2),
                        ),
                      ),
                    ...extra,
                    if (meta != null) Padding(padding: const EdgeInsets.only(top: 6), child: meta),
                  ],
                ),
              ),
            ],
          ),
          if (actions.isNotEmpty) ...[
            const SizedBox(height: 10),
            Row(
              children: [
                for (final (i, b) in actions.indexed) ...[if (i > 0) const SizedBox(width: 8), Expanded(child: b)],
              ],
            ),
          ],
        ],
      ),
    );
    if (MediaQuery.of(context).disableAnimations) return card;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: const Duration(milliseconds: 450),
      curve: const Cubic(.18, .85, .25, 1),
      builder: (context, v, child) => Opacity(
        opacity: v,
        child: Transform.translate(offset: Offset(0, (1 - v) * 10), child: child),
      ),
      child: card,
    );
  }
}

/// The design's action: the accent on its own tint.
Widget accentButton(
  BuildContext context, {
  required Key key,
  required Color accent,
  required String label,
  required VoidCallback onPressed,
}) {
  final a = accentFor(context, accent);
  return TextButton(
    key: key,
    style: TextButton.styleFrom(
      foregroundColor: a,
      backgroundColor: a.withValues(alpha: 0.10),
      minimumSize: const Size(0, 44),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(11)),
      textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
    ),
    onPressed: onPressed,
    child: Text(label, textAlign: TextAlign.center),
  );
}

class _ShiftCard extends StatelessWidget {
  const _ShiftCard({super.key, required this.card, required this.tracking, required this.sessionsToday});

  final StatusCard card;
  final String tracking;
  final int sessionsToday;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final color = Color(card.color);
    final working = card.kind == 'shift_working';
    final (dot, text) = switch (tracking) {
      'active' => (const Color(0xFF15803D), l.trackingActive),
      'stale' => (const Color(0xFFB45309), l.trackingStale),
      'off' => (const Color(0xFF6B7280), l.trackingOff),
      _ => (const Color(0xFF6B7280), l.trackingUnknown),
    };
    final shown = accentFor(context, dot);
    return Semantics(
      container: true,
      label: '${card.title}. ${card.subtitle}. $text',
      child: AccentCard(
        key: const Key('status-shift'),
        accent: color,
        icon: statusIcon(card.icon),
        title: card.title,
        titleColor: accentFor(context, color),
        leadingTitle: working
            ? Padding(
                padding: const EdgeInsetsDirectional.only(end: 6),
                child: Container(
                  key: const Key('status-working-dot'),
                  width: 9,
                  height: 9,
                  decoration: BoxDecoration(color: accentFor(context, color), shape: BoxShape.circle),
                ),
              )
            : null,
        extra: [
          if (card.subtitle.isNotEmpty) Text(card.subtitle, key: const Key('status-shift-sub')),
          if (!working && sessionsToday > 0 && card.code != 'shift_ended')
            Text(l.statusDaySummary('\u2066$sessionsToday\u2069'), style: const TextStyle(color: Color(0xFF6B7280))),
        ],
        // the design's status pill: the real tracking state, apart from the work state
        meta: Row(
          key: Key('status-tracking-$tracking'),
          children: [
            Icon(Icons.circle, size: 8, color: shown),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                text,
                style: TextStyle(color: shown, fontSize: 12.5, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A current situation's card (an alert, the car's state), in the inbox's «current» section, with its actions.
class StatusCardView extends StatelessWidget {
  const StatusCardView({super.key, required this.card, required this.onAction, this.more = 0});

  final StatusCard card;
  final void Function(String action, StatusCard card) onAction;
  final int more;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final color = Color(card.color);
    final data = card.alert?.data ?? const {};
    final phone = data['phone'];
    final actions = [
      for (final a in card.actions)
        // no phone for the supervisor: only «Done»
        if (a != 'call_supervisor' || (phone is String && phone.isNotEmpty)) a,
    ];
    final message = card.kind == 'contact' ? data['message'] as String? : null;
    return AccentCard(
      key: Key('status-card-${card.code}'),
      accent: color,
      icon: statusIcon(card.icon),
      iconKey: Key('status-icon-${card.icon}'),
      title: card.title,
      subtitle: card.subtitle,
      highlight: true,
      extra: [
        if (message != null && message.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text('«$message»', key: const Key('status-contact-message')),
          ),
      ],
      meta: more > 0
          ? Text(l.statusMore('\u2066$more\u2069'), style: const TextStyle(fontSize: 12, color: Color(0xFF6B7280)))
          : null,
      actions: [
        for (final a in actions)
          accentButton(
            context,
            key: Key('status-action-$a'),
            accent: color,
            label: actionLabel(l, a),
            onPressed: () => onAction(a, card),
          ),
      ],
    );
  }
}
