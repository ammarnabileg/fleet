import 'package:flutter/material.dart';

import '../../app/state.dart';
import '../../core/errors.dart';
import '../theme.dart';
import '../../core/models.dart';
import '../widgets/common.dart';
import 'scheme_offers.dart';

/// The first screen after sign-in for a driver with no company: «which company do you work with?», then that company's
/// pay schemes to pick one from (SchemeOffersScreen). Both go to the office as one request (approved with his ID on the platform, or rejected with a reason); a rejection shows here
/// with its reason so he picks again.
class CompanyScreen extends StatefulWidget {
  const CompanyScreen({super.key, required this.state});

  final AppState state;

  @override
  State<CompanyScreen> createState() => _CompanyScreenState();
}

class _CompanyScreenState extends State<CompanyScreen> {
  int? _picked;

  void _next(List<Company> offered) {
    final c = offered.firstWhere((p) => p.id == _picked);
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => SchemeOffersScreen(state: widget.state, company: c),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final s = widget.state;
    final c = s.company;
    final offered = c?.offered ?? const [];
    final rejected = c?.status == 'rejected' ? c : null;
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: s.refresh,
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              const SizedBox(height: 40),
              const Icon(Icons.storefront_outlined, size: 56, color: AppColors.primary),
              const SizedBox(height: 16),
              Text(
                l.companyTitle,
                key: const Key('company-title'),
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 8),
              Text(
                l.companyIntro,
                textAlign: TextAlign.center,
                style: const TextStyle(color: AppColors.muted, height: 1.6),
              ),
              const SizedBox(height: 20),
              if (rejected != null) ...[
                Banner2(
                  key: const Key('company-rejected'),
                  text: l.companyRejected(rejected.requested?.nameIn(s.lang) ?? '', rejected.adminNote ?? ''),
                  tone: BannerTone.danger,
                  icon: Icons.block,
                ),
                const SizedBox(height: 16),
              ],
              if (offered.isEmpty) Banner2(text: l.companyNone, tone: BannerTone.warn),
              for (final p in offered)
                Card(
                  key: Key('company-${p.code}'),
                  margin: const EdgeInsets.only(bottom: 10),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                    side: BorderSide(color: _picked == p.id ? AppColors.primary : AppColors.border, width: 1.5),
                  ),
                  child: ListTile(
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                    leading: Icon(
                      _picked == p.id ? Icons.radio_button_checked : Icons.radio_button_unchecked,
                      color: _picked == p.id ? AppColors.primary : AppColors.muted,
                    ),
                    title: Text(p.nameIn(s.lang), style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
                    onTap: () => setState(() => _picked = p.id),
                  ),
                ),
              const SizedBox(height: 12),
              FilledButton(
                key: const Key('company-next'),
                onPressed: _picked == null ? null : () => _next(offered),
                child: Text(l.offerNext),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// On the home screen while the office decides: the company he picked, and a way to change his choice.
class CompanyPendingBanner extends StatelessWidget {
  const CompanyPendingBanner({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final c = state.company;
    if (c == null || !c.pending) return const SizedBox.shrink();
    final l = context.l;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Banner2(
            key: const Key('company-pending'),
            text: l.companyPending(c.requested?.nameIn(state.lang) ?? ''),
            tone: BannerTone.warn,
            icon: Icons.hourglass_top_rounded,
          ),
          Align(
            alignment: AlignmentDirectional.centerEnd,
            child: TextButton(
              key: const Key('company-change'),
              onPressed: () async {
                try {
                  await state.cancelCompanyRequest();
                } on ApiError catch (e) {
                  if (context.mounted) showError(context, state, e);
                }
              },
              child: Text(l.companyChange),
            ),
          ),
        ],
      ),
    );
  }
}
