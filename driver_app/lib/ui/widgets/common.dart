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

/// A decimal point as an Arabic keyboard types it (٫, or a comma): the dot the amount is read with.
class DecimalPoint extends TextInputFormatter {
  const DecimalPoint();

  @override
  TextEditingValue formatEditUpdate(TextEditingValue oldValue, TextEditingValue newValue) =>
      newValue.copyWith(text: newValue.text.replaceAll(RegExp('[\u066B,\u060C]'), '.'));
}

/// The IBAN as typed or pasted: only its letters and digits, upper case (a banking app's copy brings spaces, dashes
/// and invisible direction marks), at most 34 characters.
class IbanFormatter extends TextInputFormatter {
  const IbanFormatter();

  @override
  TextEditingValue formatEditUpdate(TextEditingValue oldValue, TextEditingValue newValue) {
    var text = latinDigits(newValue.text).toUpperCase().replaceAll(RegExp('[^A-Z0-9]'), '');
    if (text.length > 34) text = text.substring(0, 34);
    if (text == newValue.text) return newValue;
    return TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
  }
}

class LatinDigits extends TextInputFormatter {
  const LatinDigits();

  @override
  TextEditingValue formatEditUpdate(TextEditingValue oldValue, TextEditingValue newValue) {
    final text = latinDigits(newValue.text);
    return text == newValue.text ? newValue : newValue.copyWith(text: text); // same length: the cursor stays
  }
}

/// A soft-coloured notice: an icon and a line or two, in the tone's colours (the design's .banner).
class Banner2 extends StatelessWidget {
  const Banner2({super.key, required this.text, this.tone = BannerTone.info, this.icon});

  final String text;
  final BannerTone tone;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = toneColors(tone);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(10)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(icon ?? Icons.info_outline, color: fg, size: 17),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text, style: TextStyle(color: fg, fontSize: 13, height: 1.6)),
          ),
        ],
      ),
    );
  }
}

enum BannerTone { info, warn, danger, success, neutral }

/// The soft background and the readable text colour of a tone.
(Color, Color) toneColors(BannerTone tone) => switch (tone) {
  BannerTone.info => (AppColors.infoSoft, AppColors.info),
  BannerTone.warn => (AppColors.warningSoft, AppColors.warning),
  BannerTone.danger => (AppColors.dangerSoft, AppColors.danger),
  BannerTone.success => (AppColors.successSoft, AppColors.success),
  BannerTone.neutral => (AppColors.neutralSoft, AppColors.neutral),
};

class Pill extends StatelessWidget {
  const Pill(this.text, {super.key, this.tone = BannerTone.info});

  final String text;
  final BannerTone tone;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = toneColors(tone);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(99)),
      child: Text(
        text,
        style: TextStyle(color: fg, fontSize: 11.5, fontWeight: FontWeight.w600, height: 1.4),
      ),
    );
  }
}

/// The design's card: white, rounded 18, a hairline border and the lightest shadow.
class DCard extends StatelessWidget {
  const DCard({super.key, required this.child, this.padding = const EdgeInsets.fromLTRB(15, 14, 15, 14), this.onTap});

  /// A card holding a list of [DRow]s.
  const DCard.list({super.key, required this.child, this.onTap})
    : padding = const EdgeInsets.symmetric(horizontal: 14, vertical: 4);

  final Widget child;
  final EdgeInsetsGeometry padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final body = Padding(padding: padding, child: child);
    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.border),
        boxShadow: AppColors.shadowXs,
      ),
      clipBehavior: Clip.antiAlias,
      // its own ink layer: the splashes of the rows and buttons inside show on the card, not under it
      child: Material(
        type: MaterialType.transparency,
        child: onTap == null ? body : InkWell(onTap: onTap, child: body),
      ),
    );
  }
}

/// A rounded square holding an icon, in soft colours (the design's day-state and list icons).
class IconTile extends StatelessWidget {
  const IconTile(
    this.icon, {
    super.key,
    this.bg = AppColors.primarySoft,
    this.fg = AppColors.primaryStrong,
    this.size = 36,
    this.iconSize = 18,
  });

  final IconData icon;
  final Color bg;
  final Color fg;
  final double size;
  final double iconSize;

  @override
  Widget build(BuildContext context) => Container(
    width: size,
    height: size,
    decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(size * .31)),
    child: Icon(icon, color: fg, size: iconSize),
  );
}

/// A list row: an optional leading icon, a title and a line under it, something at the end; a hairline between
/// rows (the design's .d-row).
class DRow extends StatelessWidget {
  const DRow({
    super.key,
    this.leading,
    required this.title,
    this.subtitle,
    this.trailing,
    this.onTap,
    this.divider = true,
    this.chevron = false,
  });

  final Widget? leading;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final VoidCallback? onTap;
  final bool divider;
  final bool chevron;

  @override
  Widget build(BuildContext context) {
    final row = Container(
      padding: const EdgeInsets.symmetric(vertical: 11, horizontal: 2),
      decoration: divider
          ? const BoxDecoration(
              border: Border(bottom: BorderSide(color: AppColors.divider)),
            )
          : null,
      child: Row(
        children: [
          if (leading != null) ...[leading!, const SizedBox(width: 10)],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: AppColors.text),
                ),
                if (subtitle != null)
                  Text(subtitle!, style: const TextStyle(fontSize: 11.5, color: AppColors.muted, height: 1.5)),
              ],
            ),
          ),
          if (trailing != null) ...[const SizedBox(width: 8), trailing!],
          if (chevron) ...[const SizedBox(width: 6), const Icon(Icons.chevron_right, size: 18, color: AppColors.faint)],
        ],
      ),
    );
    return onTap == null ? row : InkWell(onTap: onTap, child: row);
  }
}

/// A quick action tile on the home screen: an icon on a soft square, a title, a small line (the design's .qa).
class QuickAction extends StatelessWidget {
  const QuickAction({
    super.key,
    required this.icon,
    required this.title,
    this.subtitle,
    required this.onTap,
    this.danger = false,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback onTap;
  final bool danger;

  @override
  Widget build(BuildContext context) => Material(
    color: AppColors.surface,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(16),
      side: const BorderSide(color: AppColors.border),
    ),
    clipBehavior: Clip.antiAlias,
    child: InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            IconTile(
              icon,
              bg: danger ? AppColors.dangerSoft : AppColors.primarySoft,
              fg: danger ? AppColors.danger : AppColors.primaryStrong,
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w700, color: AppColors.text),
                ),
                if (subtitle != null)
                  Text(
                    subtitle!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 11, color: AppColors.muted),
                  ),
              ],
            ),
          ],
        ),
      ),
    ),
  );
}

/// How far along a limit (the cash alert limit): blue, orange from 85%, red at 100%.
class Meter extends StatelessWidget {
  const Meter(this.ratio, {super.key, this.tone});

  final double ratio;
  final BannerTone? tone; // the colour the server's judgement gives (near or over the limit); else from the ratio

  @override
  Widget build(BuildContext context) {
    final t = tone ?? (ratio >= 1 ? BannerTone.danger : (ratio >= .85 ? BannerTone.warn : BannerTone.info));
    final (track, fill) = switch (t) {
      BannerTone.danger => (AppColors.dangerSoft, AppColors.dangerFill),
      BannerTone.warn => (AppColors.warningSoft, AppColors.warningFill),
      _ => (AppColors.primarySoft, AppColors.primary),
    };
    return ClipRRect(
      borderRadius: BorderRadius.circular(5),
      child: LinearProgressIndicator(
        value: ratio.clamp(0, 1).toDouble(),
        minHeight: 8,
        backgroundColor: track,
        color: fill,
      ),
    );
  }
}

/// A round avatar with the name's initials, coloured from the name as on the panel.
class Avatar extends StatelessWidget {
  const Avatar(this.name, {super.key, this.size = 48});

  final String name;
  final double size;

  static const _colors = [
    Color(0xFF0A84FF),
    Color(0xFF7C4DFF),
    Color(0xFF28A745),
    Color(0xFFFF9F0A),
    Color(0xFFE0457B),
    Color(0xFF14A3A3),
  ];

  @override
  Widget build(BuildContext context) {
    final parts = name.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    final initials = parts.take(2).map((p) => p.characters.first).join().toUpperCase();
    final color = _colors[name.runes.fold<int>(0, (a, b) => a + b) % _colors.length];
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      child: Text(
        initials.isEmpty ? '?' : initials,
        textDirection: TextDirection.ltr,
        style: TextStyle(color: Colors.white, fontSize: size / 3, fontWeight: FontWeight.w700),
      ),
    );
  }
}

/// A button that shows a spinner and blocks double taps while [onPressed] runs.
class BusyButton extends StatefulWidget {
  const BusyButton({super.key, required this.label, required this.onPressed, this.icon, this.danger = false});

  final String label;
  final Future<void> Function()? onPressed;
  final IconData? icon;
  final bool danger; // the design's red button (send an accident report)

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
    final style = widget.danger
        ? FilledButton.styleFrom(
            backgroundColor: AppColors.dangerFill,
            shadowColor: AppColors.dangerFill.withValues(alpha: .35),
          )
        : null;
    return widget.icon == null || _busy
        ? FilledButton(style: style, onPressed: onPressed, child: child)
        : FilledButton.icon(style: style, onPressed: onPressed, icon: Icon(widget.icon, size: 19), label: child);
  }
}

/// A photo slot (the design's camera tile): a dashed tile with a camera on a soft circle, or the picture once
/// taken with its name on a green chip. [done] without a local file: uploaded earlier.
class PhotoTile extends StatelessWidget {
  const PhotoTile({
    super.key,
    required this.label,
    this.path,
    this.done = false,
    this.busy = false,
    required this.onTap,
    this.hint,
    this.icon = Icons.photo_camera_outlined,
  });

  final String label;
  final IconData icon; // a camera, or a picture for one from the gallery
  final String? path;
  final bool done;
  final bool busy;
  final VoidCallback? onTap;
  final String? hint;

  @override
  Widget build(BuildContext context) {
    final taken = done || path != null;
    return InkWell(
      onTap: busy ? null : onTap,
      borderRadius: BorderRadius.circular(10),
      child: AspectRatio(
        aspectRatio: 4 / 3,
        child: CustomPaint(
          foregroundPainter: taken ? null : const _DashedBorder(),
          child: Container(
            decoration: BoxDecoration(
              color: path != null ? AppColors.surface : AppColors.sunken,
              borderRadius: BorderRadius.circular(10),
              border: taken ? Border.all(color: AppColors.successFill, width: 1.5) : null,
            ),
            clipBehavior: Clip.antiAlias,
            child: Stack(
              fit: StackFit.expand,
              children: [
                if (path != null)
                  Image.file(
                    File(path!),
                    fit: BoxFit.cover,
                    cacheWidth: 720, // decoded at tile size, not the photo's full resolution
                    errorBuilder: (_, _, _) => const SizedBox(),
                  ),
                if (path == null)
                  // a small tile (a row of screenshots) keeps the camera and the name, smaller, without the hint
                  LayoutBuilder(
                    builder: (context, c) {
                      final small = c.maxHeight < 110;
                      return Padding(
                        padding: EdgeInsets.all(small ? 4 : 8),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Container(
                              width: small ? 30 : 42,
                              height: small ? 30 : 42,
                              decoration: BoxDecoration(
                                color: done ? AppColors.successSoft : AppColors.primarySoft,
                                shape: BoxShape.circle,
                              ),
                              child: Icon(
                                done ? Icons.check : icon,
                                color: done ? AppColors.success : AppColors.primaryStrong,
                                size: small ? 16 : 20,
                              ),
                            ),
                            SizedBox(height: small ? 4 : 8),
                            Text(
                              label,
                              textAlign: TextAlign.center,
                              maxLines: small ? 1 : 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: small ? 11.5 : 12.5,
                                fontWeight: FontWeight.w600,
                                color: AppColors.text,
                              ),
                            ),
                            if (hint != null && !small)
                              Text(
                                hint!,
                                textAlign: TextAlign.center,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 11, color: AppColors.muted),
                              ),
                          ],
                        ),
                      );
                    },
                  ),
                if (path != null)
                  PositionedDirectional(
                    bottom: 8,
                    start: 8,
                    end: 8,
                    child: Align(
                      alignment: AlignmentDirectional.bottomStart,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: AppColors.successFill,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.check, size: 12, color: Colors.white),
                            const SizedBox(width: 4),
                            Flexible(
                              child: Text(
                                label,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(color: Colors.white, fontSize: 11),
                              ),
                            ),
                          ],
                        ),
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
      ),
    );
  }
}

class _DashedBorder extends CustomPainter {
  const _DashedBorder();

  @override
  void paint(Canvas canvas, Size size) {
    final path = Path()..addRRect(RRect.fromRectAndRadius(Offset.zero & size, const Radius.circular(10)).deflate(.75));
    final paint = Paint()
      ..color = AppColors.borderStrong
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    for (final metric in path.computeMetrics()) {
      for (var d = 0.0; d < metric.length; d += 9) {
        canvas.drawPath(metric.extractPath(d, d + 5), paint);
      }
    }
  }

  @override
  bool shouldRepaint(_DashedBorder oldDelegate) => false;
}

/// A section title between cards (the design's .d-sec), with an optional action at the end.
class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.action});

  final String text;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.fromLTRB(2, 16, 2, 8),
    child: Row(
      children: [
        Expanded(
          child: Text(
            text,
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppColors.text),
          ),
        ),
        ?action,
      ],
    ),
  );
}

/// A form label above its field, with a red star when required (the design's .field label).
class FieldLabel extends StatelessWidget {
  const FieldLabel(this.text, {super.key, this.required = false});

  final String text;
  final bool required;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Text.rich(
      TextSpan(
        text: text,
        children: [
          if (required)
            const TextSpan(
              text: ' *',
              style: TextStyle(color: AppColors.danger),
            ),
        ],
      ),
      style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: AppColors.text),
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
