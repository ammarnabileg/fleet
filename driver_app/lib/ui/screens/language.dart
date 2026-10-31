import 'package:flutter/material.dart';

import '../../app/state.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// The first launch: the driver picks the app's language before anything else. The phone's language is ticked when
/// the app has it, else English; the choice applies at once and is kept (the settings change it later).
class LanguageScreen extends StatelessWidget {
  const LanguageScreen({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 32, 20, 20),
          children: [
            const Icon(Icons.translate_rounded, size: 40, color: AppColors.primary),
            const SizedBox(height: 12),
            Text(
              l.language,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 4),
            Text(
              l.languageFirst,
              textAlign: TextAlign.center,
              style: const TextStyle(color: AppColors.muted, height: 1.5),
            ),
            const SizedBox(height: 16),
            for (final x in state.translations.languages)
              Card(
                child: ListTile(
                  key: Key('first-lang-${x.code}'),
                  title: Text(
                    x.nameNative,
                    textDirection: x.rtl ? TextDirection.rtl : TextDirection.ltr,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                  subtitle: x.nameNative == x.nameEn ? null : Text(x.nameEn),
                  trailing: x.code == state.lang
                      ? const Icon(Icons.check_circle_rounded, color: AppColors.primary)
                      : null,
                  onTap: () => state.setLang(x.code),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
