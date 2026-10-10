import 'dart:convert';

import 'api.dart';
import 'db.dart';
import 'errors.dart';

/// The server's own texts for its error codes (`errors` namespace), in the app's language, cached for offline
/// use. The app never writes its own wording for a server rule, so a message changed on the server (or a new
/// language added there) reaches the drivers without an app update.
class Catalog {
  Catalog(this.db);

  final AppDb db;
  Map<String, String> _errors = {};
  String? _lang;

  Future<void> load(Api api, String lang) async {
    _lang = lang;
    final cached = await db.get('catalog_$lang');
    if (cached != null) _errors = Map<String, String>.from(jsonDecode(cached) as Map);
    try {
      final c = await api.get('/i18n/catalog/$lang', query: {'ns': 'errors'}, auth: false) as Map<String, dynamic>;
      final errors = Map<String, String>.from((c['messages'] as Map)['errors'] as Map? ?? {});
      if (lang == _lang) _errors = errors;
      await db.put('catalog_$lang', jsonEncode(errors));
    } on ApiError {
      // offline: the cached texts (or the fallback below) are used
    }
  }

  /// A readable message for any failure; [fallback] is the app's own generic text for that situation.
  String message(Object error, {required String network, required String generic}) {
    if (error is ApiError) {
      if (error.isNetwork) return network;
      final text = _errors[error.code];
      if (text != null) {
        return text.replaceAllMapped(RegExp(r'\{(\w+)\}'), (m) => '${error.params[m[1]] ?? m[0]}');
      }
    }
    return generic;
  }
}
