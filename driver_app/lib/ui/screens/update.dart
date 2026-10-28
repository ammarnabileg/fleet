import 'package:flutter/material.dart';

import '../../app/state.dart';
import '../../core/config.dart';
import '../../core/updater.dart';
import '../theme.dart';
import '../widgets/common.dart';

String _mb(int bytes) => '\u2066${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB\u2069';

/// What waits on the phone to be sent: queued actions and tracking points.
int _waiting(AppState s) =>
    s.queued.where((i) => i.state != 'failed' && i.state != 'parked').length +
    ((s.tracking['queue'] as num?) ?? 0).toInt();

/// The optional update: a banner on the home screen the driver may close (not shown again for this version).
class UpdateBanner extends StatelessWidget {
  const UpdateBanner({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) => ListenableBuilder(listenable: state.updater, builder: _build);

  Widget _build(BuildContext context, Widget? _) {
    final u = state.updater;
    if (!u.showBanner) return const SizedBox.shrink();
    final l = context.l;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
      child: Material(
        key: const Key('update-banner'),
        color: AppColors.infoSoft,
        borderRadius: BorderRadius.circular(10),
        child: InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: () => showUpdateSheet(context, state),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 6, 4, 6),
            child: Row(
              children: [
                const Icon(Icons.system_update_rounded, color: AppColors.info, size: 19),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    l.updateAvailable('\u2066${u.available!.versionName}\u2069'),
                    style: const TextStyle(color: AppColors.info, fontWeight: FontWeight.w600, fontSize: 13),
                  ),
                ),
                TextButton(
                  key: const Key('update-open'),
                  onPressed: () => showUpdateSheet(context, state),
                  child: Text(l.updateNow),
                ),
                IconButton(
                  key: const Key('update-dismiss'),
                  tooltip: l.updateLater,
                  icon: const Icon(Icons.close_rounded, size: 18, color: AppColors.info),
                  onPressed: () => u.dismiss(),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

Future<void> showUpdateSheet(BuildContext context, AppState state) => showModalBottomSheet<void>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (_) => Padding(
    padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
    child: SingleChildScrollView(child: UpdatePanel(state: state)),
  ),
);

/// The new version: its notes and size, and the button through download, check and install. Shared by the sheet
/// and the blocking screen.
class UpdatePanel extends StatefulWidget {
  const UpdatePanel({super.key, required this.state});

  final AppState state;

  @override
  State<UpdatePanel> createState() => _UpdatePanelState();
}

class _UpdatePanelState extends State<UpdatePanel> {
  bool? _unmetered;

  @override
  void initState() {
    super.initState();
    widget.state.updater.addListener(_changed);
    widget.state.updater.hooks.unmetered().then((v) {
      if (mounted) setState(() => _unmetered = v);
    }, onError: (Object _) {});
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    widget.state.updater.removeListener(_changed);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final u = widget.state.updater;
    final a = u.available;
    if (a == null) return Banner2(text: l.upToDate, tone: BannerTone.success, icon: Icons.verified_outlined);
    final percent = '\u2066${((u.progress ?? 0) * 100).clamp(0, 100).toStringAsFixed(0)}%\u2069';
    final failure = switch (u.error) {
      null => null,
      'checksum' => l.updateChecksum,
      'install' => l.updateInstallFailed,
      _ => l.updateFailed,
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          l.updateAvailable('\u2066${a.versionName}\u2069'),
          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 4),
        Text(l.updateSize(_mb(a.size)), style: const TextStyle(color: AppColors.muted, fontSize: 12.5)),
        if (a.notes != null && a.notes!.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(l.whatsNew, style: const TextStyle(fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Text(a.notes!, key: const Key('update-notes'), style: const TextStyle(height: 1.6)),
        ],
        const SizedBox(height: 14),
        if (_unmetered == false && u.stage != UpdateStage.ready) ...[
          Banner2(text: l.updateMobileData, tone: BannerTone.warn, icon: Icons.signal_cellular_alt_rounded),
          const SizedBox(height: 10),
        ],
        if (failure != null) ...[
          Banner2(key: const Key('update-error'), text: failure, tone: BannerTone.danger),
          const SizedBox(height: 10),
        ],
        if (u.stage == UpdateStage.needsPermission) ...[
          Banner2(
            key: const Key('update-permission'),
            text: '${l.updatePermissionTitle}\n${l.updatePermissionBody}',
            tone: BannerTone.warn,
            icon: Icons.security_rounded,
          ),
          const SizedBox(height: 10),
          FilledButton.icon(
            key: const Key('update-settings'),
            icon: const Icon(Icons.settings_rounded),
            label: Text(l.updateOpenSettings),
            onPressed: u.openInstallSettings,
          ),
        ] else if (u.stage == UpdateStage.downloading) ...[
          LinearProgressIndicator(value: u.progress),
          const SizedBox(height: 6),
          Text(l.updateDownloading(percent), textAlign: TextAlign.center),
        ] else ...[
          FilledButton.icon(
            key: const Key('update-go'),
            icon: Icon(u.stage == UpdateStage.ready ? Icons.install_mobile_rounded : Icons.download_rounded),
            label: Text(u.stage == UpdateStage.ready ? l.updateInstall : l.updateNow),
            onPressed: u.stage == UpdateStage.installing ? null : u.install,
          ),
          const SizedBox(height: 8),
          Text(
            l.updateInstallHint,
            textAlign: TextAlign.center,
            style: const TextStyle(color: AppColors.muted, fontSize: 12),
          ),
        ],
      ],
    );
  }
}

/// A required update: the screens wait for it. The tracking service and the outbox are not stopped: they keep
/// sending in the background (and were given their chance before this showed); the count says what still waits.
class UpdateRequiredScreen extends StatelessWidget {
  const UpdateRequiredScreen({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final waiting = _waiting(state);
    return Scaffold(
      key: const Key('update-required'),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 24),
            const Center(
              child: IconTile(Icons.system_update_rounded, bg: AppColors.primarySoft, fg: AppColors.primary),
            ),
            const SizedBox(height: 16),
            Text(
              l.updateRequiredTitle,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            Text(
              l.updateRequiredBody,
              textAlign: TextAlign.center,
              style: const TextStyle(color: AppColors.muted),
            ),
            if (waiting > 0) ...[
              const SizedBox(height: 12),
              Banner2(
                key: const Key('update-waiting'),
                text: l.updateQueued('\u2066$waiting\u2069'),
                icon: Icons.cloud_upload_outlined,
              ),
            ],
            const SizedBox(height: 20),
            DCard(child: UpdatePanel(state: state)),
            const SizedBox(height: 12),
            Text(
              l.appVersion('\u2066${AppConfig.appVersion} (${AppConfig.appBuild})\u2069'),
              textAlign: TextAlign.center,
              style: const TextStyle(color: AppColors.faint, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}

/// The account tab's row: this version, and «Check for updates».
class UpdateRow extends StatefulWidget {
  const UpdateRow({super.key, required this.state});

  final AppState state;

  @override
  State<UpdateRow> createState() => _UpdateRowState();
}

class _UpdateRowState extends State<UpdateRow> {
  bool? _reached;

  Future<void> _check() async {
    final u = widget.state.updater;
    final ok = await u.check(force: true);
    if (!mounted) return;
    setState(() => _reached = ok);
    if (ok && u.available != null) {
      await showUpdateSheet(context, widget.state);
    } else {
      // said out loud: a quiet line under the version looked like a button that does nothing
      final l = context.l;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(key: const Key('update-checked'), content: Text(ok ? l.upToDate : l.updateCheckFailed)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final u = widget.state.updater;
    final status = u.checking
        ? null
        : u.available != null
        ? l.updateAvailable('\u2066${u.available!.versionName}\u2069')
        : _reached == false
        ? l.updateCheckFailed
        : _reached == true
        ? l.upToDate
        : null;
    return DRow(
      key: const Key('check-updates'),
      divider: false,
      leading: const Icon(Icons.smartphone_rounded, size: 19, color: AppColors.text3),
      title: l.thisPhone,
      subtitle: [l.appVersion('\u2066${AppConfig.appVersion} (${AppConfig.appBuild})\u2069'), ?status].join(' · '),
      trailing: u.checking
          ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
          : TextButton(
              onPressed: u.available != null ? () => showUpdateSheet(context, widget.state) : _check,
              child: Text(u.available != null ? l.updateNow : l.checkUpdates),
            ),
    );
  }
}
