import 'package:flutter/material.dart';

import '../../app/state.dart';
import '../theme.dart';
import 'common.dart';

/// The app's language: the current one by its own name, and a list of every language the server offers (the
/// built-in six before it ever answered). The choice applies at once, offline too.
class LanguagePicker extends StatelessWidget {
  const LanguagePicker({super.key, required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final current = state.translations.language(state.lang);
    return OutlinedButton.icon(
      key: const Key('language-picker'),
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(0, 40),
        padding: const EdgeInsets.symmetric(horizontal: 14),
      ),
      icon: const Icon(Icons.translate_rounded, size: 18),
      label: Text(current.nameNative),
      onPressed: () => pick(context),
    );
  }

  Future<void> pick(BuildContext context) async {
    final chosen = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (c) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
              child: Text(c.l.language, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
            ),
            for (final l in state.translations.languages)
              ListTile(
                key: Key('lang-${l.code}'),
                title: Text(l.nameNative, textDirection: l.rtl ? TextDirection.rtl : TextDirection.ltr),
                subtitle: l.nameNative == l.nameEn ? null : Text(l.nameEn),
                trailing: l.code == state.lang ? const Icon(Icons.check_rounded, color: AppColors.primary) : null,
                onTap: () => Navigator.pop(c, l.code),
              ),
          ],
        ),
      ),
    );
    if (chosen != null && chosen != state.lang) await state.setLang(chosen);
  }
}
