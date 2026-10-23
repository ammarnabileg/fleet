import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../status/engine.dart';
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

/// The status area of the home screen: offline, a clear line with the time of the last update; the most important
/// alert on top (it goes back to the base state once it expires or is resolved); then the shift card, always there
/// with the real tracking state, and the car's card when the car is not simply available.
class LiveStatusPanel extends StatelessWidget {
  const LiveStatusPanel({super.key, required this.view, required this.onAction, this.sessionsToday = 0});

  final StatusView view;
  final void Function(String action, StatusCard card) onAction;
  final int sessionsToday;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final still = MediaQuery.of(context).disableAnimations;
    final duration = still ? Duration.zero : const Duration(milliseconds: 280);
    final top = view.top;
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
          switchInCurve: Curves.easeOut,
          switchOutCurve: Curves.easeIn,
          child: top == null
              ? const SizedBox.shrink(key: ValueKey('no-alert'))
              : Padding(
                  key: ValueKey('alert-${top.key}'),
                  padding: const EdgeInsets.only(bottom: 10),
                  child: _StatusCardView(card: top, more: view.more, onAction: onAction),
                ),
        ),
        AnimatedSwitcher(
          duration: duration,
          child: _ShiftCard(
            key: ValueKey('shift-${view.shift.code}-${view.tracking}'),
            card: view.shift,
            tracking: view.tracking,
            sessionsToday: sessionsToday,
          ),
        ),
        if (view.vehicle != null) ...[
          const SizedBox(height: 10),
          AnimatedSwitcher(
            duration: duration,
            child: _StatusCardView(
              key: ValueKey('vehicle-${view.vehicle!.code}'),
              card: view.vehicle!,
              onAction: onAction,
            ),
          ),
        ],
      ],
    );
  }
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
    return Semantics(
      container: true,
      label: '${card.title}. ${card.subtitle}. $text',
      child: DCard(
        key: const Key('status-shift'),
        child: Row(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(color: color.withValues(alpha: 0.12), shape: BoxShape.circle),
              child: Icon(statusIcon(card.icon), color: color),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      if (working) ...[
                        Container(
                          key: const Key('status-working-dot'),
                          width: 9,
                          height: 9,
                          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                        ),
                        const SizedBox(width: 6),
                      ],
                      Flexible(
                        child: Text(
                          card.title,
                          style: TextStyle(fontWeight: FontWeight.w700, color: color),
                        ),
                      ),
                    ],
                  ),
                  if (card.subtitle.isNotEmpty) Text(card.subtitle, key: const Key('status-shift-sub')),
                  if (!working && sessionsToday > 0)
                    Text(
                      l.statusDaySummary('\u2066$sessionsToday\u2069'),
                      style: const TextStyle(color: Color(0xFF6B7280)),
                    ),
                  const SizedBox(height: 4),
                  Row(
                    key: Key('status-tracking-$tracking'),
                    children: [
                      Icon(Icons.circle, size: 8, color: dot),
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(text, style: TextStyle(color: dot, fontSize: 12.5)),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusCardView extends StatelessWidget {
  const _StatusCardView({super.key, required this.card, required this.onAction, this.more = 0});

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
    return Container(
      key: Key('status-card-${card.code}'),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        border: BorderDirectional(start: BorderSide(color: color, width: 4)),
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(statusIcon(card.icon), color: color, key: Key('status-icon-${card.icon}')),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(card.title, style: const TextStyle(fontWeight: FontWeight.w700)),
                    if (card.subtitle.isNotEmpty) Text(card.subtitle),
                    if (message != null && message.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text('«$message»', key: const Key('status-contact-message')),
                      ),
                    if (more > 0)
                      Text(
                        l.statusMore('\u2066$more\u2069'),
                        style: const TextStyle(fontSize: 12, color: Color(0xFF6B7280)),
                      ),
                  ],
                ),
              ),
            ],
          ),
          if (actions.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 6,
              children: [
                for (final (i, a) in actions.indexed)
                  i == 0
                      ? FilledButton(
                          key: Key('status-action-$a'),
                          style: FilledButton.styleFrom(backgroundColor: color),
                          onPressed: () => onAction(a, card),
                          child: Text(actionLabel(l, a)),
                        )
                      : OutlinedButton(
                          key: Key('status-action-$a'),
                          onPressed: () => onAction(a, card),
                          child: Text(actionLabel(l, a)),
                        ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
