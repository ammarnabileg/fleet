import 'package:flutter/material.dart';

/// The driver app's identity, from its design (web/public/driver.html: assets/css/tokens.css, driver.css).
/// success, warning and danger are the readable text shades; the bright fills are their *Fill.
class AppColors {
  static const primary = Color(0xFF0A84FF);
  static const primaryStrong = Color(0xFF0A6CFF);
  static const primarySoft = Color(0xFFE4EEFF);
  static const primarySofter = Color(0xFFF1F6FF);
  static const bg = Color(0xFFF7F9FC);
  static const surface = Colors.white;
  static const surface3 = Color(0xFFF1F3F8);
  static const sunken = Color(0xFFF4F7FB);
  static const text = Color(0xFF0B1F3A);
  static const text2 = Color(0xFF3A4254);
  static const text3 = Color(0xFF6B7385);
  static const muted = Color(0xFF8A93A6);
  static const faint = Color(0xFF9AA3B5);
  static const border = Color(0xFFECEFF4);
  static const borderStrong = Color(0xFFDCE2EC);
  static const divider = Color(0xFFF2F4F8);
  static const success = Color(0xFF1E8E3E);
  static const successFill = Color(0xFF28A745);
  static const successSoft = Color(0xFFE2F5E7);
  static const warning = Color(0xFFB85F00);
  static const warningFill = Color(0xFFFF9F0A);
  static const warningSoft = Color(0xFFFFF0DA);
  static const danger = Color(0xFFD12F2F);
  static const dangerFill = Color(0xFFFF3B30);
  static const dangerSoft = Color(0xFFFDE6E6);
  static const info = Color(0xFF1A5FD0);
  static const infoSoft = Color(0xFFE5EFFF);
  static const neutral = Color(0xFF5B6478);
  static const neutralSoft = Color(0xFFEEF0F4);

  /// The vehicle card: a blue gradient, as on the design.
  static const vehicleGradient = LinearGradient(
    begin: AlignmentDirectional.topStart,
    end: AlignmentDirectional.bottomEnd,
    colors: [Color(0xFF1E7BFF), Color(0xFF0A5BD8), Color(0xFF2C3FC4)],
    stops: [0, .55, 1],
  );

  static const shadowXs = [BoxShadow(color: Color(0x0F000000), blurRadius: 3, offset: Offset(0, 1))];
}

const _font = 'IBMPlexSansArabic';

ThemeData appTheme() {
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      primary: AppColors.primary,
      surface: AppColors.surface,
      error: AppColors.danger,
    ),
    scaffoldBackgroundColor: AppColors.bg,
    fontFamily: _font,
  );
  OutlineInputBorder field(Color c, [double w = 1]) => OutlineInputBorder(
    borderRadius: BorderRadius.circular(10),
    borderSide: BorderSide(color: c, width: w),
  );
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: AppColors.text, displayColor: AppColors.text),
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.bg,
      surfaceTintColor: Colors.transparent,
      foregroundColor: AppColors.text,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleSpacing: 18,
      titleTextStyle: TextStyle(fontFamily: _font, fontSize: 20, fontWeight: FontWeight.w700, color: AppColors.text),
    ),
    // the back button: a white circle, as on the design
    actionIconTheme: ActionIconThemeData(
      backButtonIconBuilder: (_) => const _RoundIcon(Icons.arrow_back),
      closeButtonIconBuilder: (_) => const _RoundIcon(Icons.close),
    ),
    cardTheme: CardThemeData(
      color: AppColors.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: AppColors.border),
      ),
    ),
    listTileTheme: const ListTileThemeData(
      iconColor: AppColors.text3,
      titleTextStyle: TextStyle(fontFamily: _font, fontSize: 13.5, fontWeight: FontWeight.w600, color: AppColors.text),
      subtitleTextStyle: TextStyle(fontFamily: _font, fontSize: 11.5, color: AppColors.muted, height: 1.5),
    ),
    dividerTheme: const DividerThemeData(color: AppColors.divider, space: 1, thickness: 1),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surface,
      border: field(AppColors.borderStrong),
      enabledBorder: field(AppColors.borderStrong),
      focusedBorder: field(AppColors.primary, 1.5),
      errorBorder: field(AppColors.danger),
      focusedErrorBorder: field(AppColors.danger, 1.5),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      labelStyle: const TextStyle(color: AppColors.text3),
      floatingLabelStyle: const TextStyle(color: AppColors.primaryStrong, fontWeight: FontWeight.w600),
      hintStyle: const TextStyle(color: AppColors.faint),
      helperStyle: const TextStyle(color: AppColors.muted, fontSize: 11.5),
      errorStyle: const TextStyle(color: AppColors.danger, fontSize: 11.5),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        minimumSize: const Size.fromHeight(52),
        elevation: 2,
        shadowColor: AppColors.primary.withValues(alpha: .35),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        textStyle: const TextStyle(fontFamily: _font, fontSize: 15.5, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.text,
        backgroundColor: AppColors.surface,
        minimumSize: const Size.fromHeight(48),
        side: const BorderSide(color: AppColors.borderStrong),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: const TextStyle(fontFamily: _font, fontSize: 14.5, fontWeight: FontWeight.w600),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: AppColors.primaryStrong,
        textStyle: const TextStyle(fontFamily: _font, fontSize: 13, fontWeight: FontWeight.w600),
      ),
    ),
    // a segmented choice drawn like the design's language switch: grey track, the chosen one white
    segmentedButtonTheme: SegmentedButtonThemeData(
      selectedIcon: const SizedBox.shrink(),
      style: ButtonStyle(
        visualDensity: VisualDensity.compact,
        backgroundColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? AppColors.surface : AppColors.surface3,
        ),
        foregroundColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? AppColors.text : AppColors.text3,
        ),
        textStyle: WidgetStateProperty.resolveWith(
          (s) => TextStyle(
            fontFamily: _font,
            fontSize: 13,
            fontWeight: s.contains(WidgetState.selected) ? FontWeight.w700 : FontWeight.w500,
          ),
        ),
        side: const WidgetStatePropertyAll(BorderSide(color: AppColors.surface3, width: 3)),
        shape: WidgetStatePropertyAll(RoundedRectangleBorder(borderRadius: BorderRadius.circular(10))),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      height: 66,
      indicatorColor: Colors.transparent,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      iconTheme: WidgetStateProperty.resolveWith(
        (s) => IconThemeData(size: 23, color: s.contains(WidgetState.selected) ? AppColors.primary : AppColors.muted),
      ),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (s) => TextStyle(
          fontFamily: _font,
          fontSize: 11,
          fontWeight: s.contains(WidgetState.selected) ? FontWeight.w700 : FontWeight.w400,
          color: s.contains(WidgetState.selected) ? AppColors.primary : AppColors.muted,
        ),
      ),
    ),
    switchTheme: SwitchThemeData(
      trackColor: WidgetStateProperty.resolveWith(
        (s) => s.contains(WidgetState.selected) ? AppColors.successFill : AppColors.borderStrong,
      ),
      thumbColor: const WidgetStatePropertyAll(Colors.white),
      trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
    ),
    checkboxTheme: CheckboxThemeData(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(5))),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      showDragHandle: true,
      dragHandleColor: AppColors.borderStrong,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      contentTextStyle: const TextStyle(fontFamily: _font, fontSize: 14, color: AppColors.text2, height: 1.7),
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: AppColors.text,
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      contentTextStyle: const TextStyle(fontFamily: _font, fontSize: 13, color: Colors.white),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(color: AppColors.primary),
  );
}

class _RoundIcon extends StatelessWidget {
  const _RoundIcon(this.icon);

  final IconData icon;

  @override
  Widget build(BuildContext context) => Container(
    width: 34,
    height: 34,
    decoration: const BoxDecoration(color: AppColors.surface, shape: BoxShape.circle, boxShadow: AppColors.shadowXs),
    child: Icon(icon, size: 18, color: AppColors.text),
  );
}
