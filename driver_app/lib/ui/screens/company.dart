import 'package:flutter/material.dart';

import '../../app/state.dart';
import '../../core/errors.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// The first screen after sign-in for a driver with no company: «which company do you work with?». His choice goes to
/// the office as a request (approved with his ID on the platform, or rejected with a reason); a rejection shows here
/// with its reason so he picks again.
class CompanyScreen extends StatefulWidget {
  const CompanyScreen({super.key, required this.state});

  final AppState state;

  @override
  State<CompanyScreen> createState() => _CompanyScreenState();
}

class _CompanyScreenState extends State<CompanyScreen> {
  int? _picked;
  final _note = TextEditingController();
  bool _busy = false;

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final id = _picked;
    if (id == null) return;
    setState(() => _busy = true);
    try {
      final note = _note.text.trim();
      await widget.state.chooseCompany(id, note: note.isEmpty ? null : note);
    } on ApiError catch (e) {
      if (mounted) showError(context, widget.state, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
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
                    onTap: _busy ? null : () => setState(() => _picked = p.id),
                  ),
                ),
              const SizedBox(height: 8),
              TextField(
                key: const Key('company-note'),
                controller: _note,
                maxLength: 500,
                decoration: InputDecoration(labelText: l.companyNote),
              ),
              const SizedBox(height: 12),
              FilledButton(
                key: const Key('company-send'),
                onPressed: _picked == null || _busy ? null : _send,
                child: _busy
                    ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                    : Text(l.companySend),
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
