import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/state.dart';
import '../../core/errors.dart';
import '../../l10n/app_localizations.dart';
import '../theme.dart';

extension L10nX on BuildContext {
  AppLocalizations get l => AppLocalizations.of(this);
}

/// The server's message for any failure, in the app language.
String errorText(BuildContext context, AppState state, Object error) =>
    state.message(error, network: context.l.networkError, generic: context.l.genericError);

void showError(BuildContext context, AppState state, Object error) =>
    showErrorText(context, errorText(context, state, error));

void showErrorText(BuildContext context, String text) {
  ScaffoldMessenger.of(
    context,
  ).showSnackBar(SnackBar(content: Text(text), backgroundColor: AppColors.danger, behavior: SnackBarBehavior.floating));
}

/// The fields a 422 `validation_error` names (the last part of each `loc`), so the screen can say which one.
List<String> invalidFields(Object error) {
  if (error is! ApiError || error.code != 'validation_error') return const [];
  return [
    for (final e in error.body['errors'] as List? ?? const [])
      if ((e as Map)['loc'] case [..., final String field]) field,
  ];
}

/// Arabic-Indic digits (٠-٩, and the ۰-۹ some keyboards type) become 0-9: the server takes Latin digits only.
String latinDigits(String text) => text.replaceAllMapped(RegExp('[٠-٩۰-۹]'), (m) {
  final c = m[0]!.codeUnitAt(0);
  return String.fromCharCode(0x30 + c - (c >= 0x06F0 ? 0x06F0 : 0x0660));
});

class LatinDigits extends TextInputFormatter {
  const LatinDigits();

  @override
  TextEditingValue formatEditUpdate(TextEditingValue oldValue, TextEditingValue newValue) {
    final text = latinDigits(newValue.text);
    return text == newValue.text ? newValue : newValue.copyWith(text: text); // same length: the cursor stays
  }
}

class Banner2 extends StatelessWidget {
  const Banner2({super.key, required this.text, this.tone = BannerTone.info, this.icon});

  final String text;
  final BannerTone tone;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (tone) {
      BannerTone.info => (AppColors.infoSoft, AppColors.primary),
      BannerTone.warn => (AppColors.warningSoft, AppColors.warning),
      BannerTone.danger => (AppColors.dangerSoft, AppColors.danger),
      BannerTone.success => (AppColors.successSoft, AppColors.success),
    };
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(12)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon ?? Icons.info_outline, color: fg, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text, style: TextStyle(color: fg, height: 1.5)),
          ),
        ],
      ),
    );
  }
}

enum BannerTone { info, warn, danger, success }

class Pill extends StatelessWidget {
  const Pill(this.text, {super.key, this.tone = BannerTone.info});

  final String text;
  final BannerTone tone;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (tone) {
      BannerTone.info => (AppColors.infoSoft, AppColors.primary),
      BannerTone.warn => (AppColors.warningSoft, AppColors.warning),
      BannerTone.danger => (AppColors.dangerSoft, AppColors.danger),
      BannerTone.success => (AppColors.successSoft, AppColors.success),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(99)),
      child: Text(
        text,
        style: TextStyle(color: fg, fontSize: 12.5, fontWeight: FontWeight.w600),
      ),
    );
  }
}

/// A button that shows a spinner and blocks double taps while [onPressed] runs.
class BusyButton extends StatefulWidget {
  const BusyButton({super.key, required this.label, required this.onPressed, this.icon});

  final String label;
  final Future<void> Function()? onPressed;
  final IconData? icon;

  @override
  State<BusyButton> createState() => _BusyButtonState();
}

class _BusyButtonState extends State<BusyButton> {
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final onPressed = widget.onPressed == null || _busy
        ? null
        : () async {
            setState(() => _busy = true);
            try {
              await widget.onPressed!();
            } finally {
              if (mounted) setState(() => _busy = false);
            }
          };
    final child = _busy
        ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white))
        : Text(widget.label);
    return widget.icon == null || _busy
        ? FilledButton(onPressed: onPressed, child: child)
        : FilledButton.icon(onPressed: onPressed, icon: Icon(widget.icon), label: child);
  }
}

/// A photo slot: the picture once taken, otherwise a camera tile. [done] without a local file: uploaded earlier.
class PhotoTile extends StatelessWidget {
  const PhotoTile({
    super.key,
    required this.label,
    this.path,
    this.done = false,
    this.busy = false,
    required this.onTap,
  });

  final String label;
  final String? path;
  final bool done;
  final bool busy;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: busy ? null : onTap,
      borderRadius: BorderRadius.circular(14),
      child: AspectRatio(
        aspectRatio: 4 / 3,
        child: Container(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: done || path != null ? AppColors.success : AppColors.border,
              width: done || path != null ? 1.5 : 1,
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: Stack(
            fit: StackFit.expand,
            children: [
              if (path != null) Image.file(File(path!), fit: BoxFit.cover, errorBuilder: (_, _, _) => const SizedBox()),
              if (path == null)
                Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      done ? Icons.check_circle : Icons.photo_camera_outlined,
                      color: done ? AppColors.success : AppColors.primary,
                      size: 28,
                    ),
                    const SizedBox(height: 6),
                    Text(
                      label,
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 13, color: AppColors.muted),
                    ),
                  ],
                ),
              if (path != null)
                Positioned(
                  bottom: 0,
                  left: 0,
                  right: 0,
                  child: Container(
                    color: Colors.black45,
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Text(
                      label,
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white, fontSize: 12),
                    ),
                  ),
                ),
              if (busy)
                const ColoredBox(
                  color: Colors.white70,
                  child: Center(child: CircularProgressIndicator()),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 18, bottom: 8),
    child: Text(
      text,
      style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: AppColors.text),
    ),
  );
}

/// Amounts and numbers are written left to right with Latin digits, as on the receipts.
String money(String amount, String currency) => '\u2066$amount\u2069 $currency';

/// The ISO 13616 check digits (mod 97), as the server checks them: a mistyped IBAN is caught before it is sent.
bool ibanOk(String value) {
  final v = value.replaceAll(' ', '').toUpperCase();
  if (!RegExp(r'^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$').hasMatch(v)) return false;
  final digits = (v.substring(4) + v.substring(0, 4)).split('').map((c) {
    final code = c.codeUnitAt(0);
    return code >= 65 ? '${code - 55}' : c;
  }).join();
  var rest = 0;
  for (final ch in digits.split('')) {
    rest = (rest * 10 + int.parse(ch)) % 97;
  }
  return rest == 1;
}
