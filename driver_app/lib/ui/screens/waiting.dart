import 'package:flutter/material.dart';

import '../../app/state.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Registration sent, waiting for the company's review; or the account is suspended.
class WaitingScreen extends StatelessWidget {
  const WaitingScreen({super.key, required this.state, this.blocked = false});

  final AppState state;
  final bool blocked;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: state.refresh,
          child: ListView(
            padding: const EdgeInsets.all(28),
            children: [
              const SizedBox(height: 90),
              Icon(
                blocked ? Icons.block : Icons.hourglass_top_rounded,
                size: 64,
                color: blocked ? AppColors.danger : AppColors.warning,
              ),
              const SizedBox(height: 20),
              Text(
                blocked ? l.blockedTitle : l.obWaitingTitle,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 10),
              Text(
                blocked ? l.blockedText : l.obWaitingText,
                textAlign: TextAlign.center,
                style: const TextStyle(color: AppColors.muted, height: 1.7),
              ),
              const SizedBox(height: 28),
              OutlinedButton.icon(onPressed: state.refresh, icon: const Icon(Icons.refresh), label: Text(l.refresh)),
            ],
          ),
        ),
      ),
    );
  }
}
