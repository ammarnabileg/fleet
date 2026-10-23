import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/widgets.dart';

import '../l10n/app_localizations.dart';
import '../l10n/reference_en.dart';
import '../l10n/remote_localizations.dart';
import 'api.dart';
import 'db.dart';
import 'errors.dart';
import 'icu.dart';

/// A language the app offers: from the server's manifest, or the built-in list before it ever answered.
class AppLanguage {
  const AppLanguage(this.code, this.nameNative, this.nameEn, this.rtl);

  final String code;
  final String nameNative;
  final String nameEn;
  final bool rtl;

  static const builtIn = [
    AppLanguage('ar', 'العربية', 'Arabic', true),
    AppLanguage('en', 'English', 'English', false),
    AppLanguage('fr', 'Français', 'French', false),
    AppLanguage('sw', 'Kiswahili', 'Swahili', false),
    AppLanguage('hi', 'हिन्दी', 'Hindi', false),
    AppLanguage('fil', 'Filipino', 'Filipino', false),
  ];

  static AppLanguage? fromJson(Object? j) {
    if (j is! Map) return null;
    final code = j['code'];
    if (code is! String || !RegExp(r'^[a-z]{2,3}$').hasMatch(code)) return null;
    final native = j['name_native'] is String ? j['name_native'] as String : code;
    final en = j['name_en'] is String ? j['name_en'] as String : code;
    return AppLanguage(code, native, en, j['dir'] == 'rtl');
  }

  Map<String, Object> toJson() => {
    'code': code,
    'name_native': nameNative,
    'name_en': nameEn,
    'dir': rtl ? 'rtl' : 'ltr',
  };
}

/// The dashboard's published strings of one language, held in memory: each one parsed and checked against the
/// built-in English message when the bundle was read, so a lookup is a map read (no disk, no network). A key the
/// bundle lacks, or whose text failed the check, is null here and the built-in text shows instead.
class RemoteStrings {
  RemoteStrings(this.lang, this.version, Map<String, String> values) : _values = values;

  static final empty = RemoteStrings('', 0, const {});

  final String lang;
  final int version;
  final Map<String, String> _values;

  int get length => _values.length;

  String? text(String key) => _values[key];

  String? format(String key, Map<String, Object?> args) {
    final raw = _values[key];
    if (raw == null) return null;
    try {
      return IcuMessage.tryParse(raw)?.format(args, lang);
    } catch (_) {
      return null; // never a broken screen: the built-in text
    }
  }

  /// Only the valid strings of a decoded bundle: a string that does not parse, or whose arguments differ from the
  /// built-in English message, is left out (that key falls back alone). [rejected] gets the keys left out.
  static Map<String, String> validStrings(Object? strings, [List<String>? rejected]) {
    final out = <String, String>{};
    if (strings is! Map) return out;
    for (final e in strings.entries) {
      final key = e.key, value = e.value;
      final reference = englishMessages[key];
      if (key is! String || value is! String || reference == null || IcuMessage.check(value, reference) != null) {
        if (key is String) rejected?.add(key);
        continue;
      }
      out[key] = value;
    }
    return out;
  }
}

/// A bundle as read and checked: the document's header and its valid strings.
class Bundle {
  Bundle(this.lang, this.version, this.strings, {this.rejected = const []});

  final String lang;
  final int version;
  final Map<String, String> strings;
  final List<String> rejected;
}

/// The published bundles kept on the phone, one file per language (`<lang>.json`) and the one before it
/// (`<lang>.prev.json`, to go back to). A download is written to a temporary file, checked (checksum, language,
/// version, the app's compatibility, every string), then renamed over the old file: the file in use is never
/// written into. Installs run one at a time, and an older version never replaces a newer one.
class BundleStore {
  BundleStore(this._dir, {required this.appBuild, this.schema = 1});

  /// Where the files go, asked when first needed (null: no storage, the built-in strings only).
  final Future<Directory?> Function() _dir;
  Directory? _resolved;
  final int appBuild;

  /// The bundle document shape this app reads.
  final int schema;
  Future<void> _lock = Future.value();

  Future<Directory?> _folder() async {
    try {
      final d = _resolved ??= await _dir();
      if (d == null) return null;
      final f = Directory('${d.path}/l10n');
      if (!f.existsSync()) await f.create(recursive: true);
      return f;
    } catch (_) {
      return null; // no storage: the built-in texts
    }
  }

  /// Checks a bundle document (the bytes as downloaded or read back): null when anything is wrong.
  Bundle? decode(List<int> bytes, {required String lang, int? version, String? sha256}) {
    if (sha256 != null && sha256Of(bytes) != sha256) return null;
    final Object? doc;
    try {
      doc = jsonDecode(utf8.decode(bytes));
    } catch (_) {
      return null;
    }
    if (doc is! Map) return null;
    final s = doc['schema'], minBuild = doc['min_app_build'], v = doc['version'];
    if (s is! int || s > schema) return null; // a newer document shape than this app reads
    if (minBuild is! int || minBuild > appBuild) return null; // needs a newer app
    if (doc['lang'] != lang || v is! int || v < 1 || (version != null && v != version)) return null;
    if (doc['strings'] is! Map) return null;
    final rejected = <String>[];
    return Bundle(lang, v, RemoteStrings.validStrings(doc['strings'], rejected), rejected: rejected);
  }

  static String sha256Of(List<int> bytes) => sha256.convert(bytes).toString();

  /// The bundle kept for [lang]; a damaged file gives way to the one before it.
  Future<Bundle?> read(String lang) async {
    final dir = await _folder();
    if (dir == null) return null;
    for (final name in ['$lang.json', '$lang.prev.json']) {
      final f = File('${dir.path}/$name');
      try {
        if (!f.existsSync()) continue;
        final b = decode(await f.readAsBytes(), lang: lang);
        if (b != null) return b;
      } catch (_) {
        // unreadable: the next one
      }
    }
    return null;
  }

  /// Installs a downloaded bundle. False when it fails a check or is not newer than the one kept (a download that
  /// finished late after a newer one). The current file is kept as the previous one.
  Future<bool> install(String lang, List<int> bytes, {required int version, required String sha256}) {
    final done = _lock.then((_) => _install(lang, bytes, version: version, sha256: sha256));
    _lock = done.then((_) {}, onError: (Object _) {});
    return done;
  }

  Future<bool> _install(String lang, List<int> bytes, {required int version, required String sha256}) async {
    final bundle = decode(bytes, lang: lang, version: version, sha256: sha256);
    if (bundle == null) return false;
    final dir = await _folder();
    if (dir == null) return false;
    final current = await read(lang);
    if (current != null && current.version >= version) return false;
    final tmp = File('${dir.path}/$lang.$version.tmp');
    try {
      await tmp.writeAsBytes(bytes, flush: true);
      final file = File('${dir.path}/$lang.json');
      if (file.existsSync()) await file.rename('${dir.path}/$lang.prev.json');
      await tmp.rename(file.path);
      return true;
    } catch (_) {
      if (tmp.existsSync()) await tmp.delete();
      return false;
    }
  }
}

/// The app's strings: built in for every language (the first launch and offline need nothing else), and the
/// dashboard's published versions downloaded in the background. Lookup: the active published bundle of the language
/// (each string checked) -> the built-in text of the language -> built-in English.
///
/// Nothing here ever waits on the network before a screen: [use] reads the local file; [check] runs after the first
/// screen, at most every [every] (unless forced), asks for a small manifest with its ETag (304 when nothing changed)
/// and downloads only a newer bundle. A downloaded bundle is installed on disk and becomes active at a safe point
/// ([activatePending]: the next launch, or the next time a root screen shows), never in the middle of a screen; a
/// language the driver picks applies at once from what is on the phone.
class Translations {
  Translations(this.db, this.store, {this.every = const Duration(minutes: 15), this.onError});

  final AppDb db;
  final BundleStore store;
  final Duration every;
  final Future<void> Function(String where, Object error, StackTrace st)? onError;

  RemoteStrings active = RemoteStrings.empty;
  DateTime? _checkedAt;
  bool _pending = false;
  List<AppLanguage>? _languages;

  /// The languages to offer: the server's last list, or the built-in six.
  List<AppLanguage> get languages => _languages ?? AppLanguage.builtIn;

  AppLanguage language(String code) =>
      languages.where((l) => l.code == code).firstOrNull ??
      AppLanguage.builtIn.where((l) => l.code == code).firstOrNull ??
      AppLanguage(code, code, code, false);

  /// A newer bundle is on the phone, waiting for a safe point.
  bool get hasPending => _pending;

  /// Reads the kept language list (a database read, at start).
  Future<void> loadLanguages() async {
    try {
      final raw = await db.get('l10n_languages');
      if (raw == null) return;
      final list = [for (final j in jsonDecode(raw) as List) ?AppLanguage.fromJson(j)];
      if (list.isNotEmpty) _languages = list;
    } catch (e, st) {
      await onError?.call('l10n.languages', e, st);
    }
  }

  /// Makes [lang]'s kept bundle the active strings now (start, a language the driver picks).
  Future<void> use(String lang) async {
    try {
      final b = await store.read(lang);
      active = b == null ? RemoteStrings(lang, 0, const {}) : RemoteStrings(lang, b.version, b.strings);
      if (b != null && b.rejected.isNotEmpty) {
        await onError?.call(
          'l10n.rejected',
          'invalid strings in $lang v${b.version}: ${b.rejected.join(', ')}',
          StackTrace.current,
        );
      }
    } catch (e, st) {
      active = RemoteStrings(lang, 0, const {});
      await onError?.call('l10n.read', e, st);
    }
    _pending = false;
  }

  /// At a safe point: a newer bundle downloaded meanwhile becomes the active strings. True when it changed.
  Future<bool> activatePending() async {
    if (!_pending) return false;
    final before = active.version;
    await use(active.lang);
    return active.version != before;
  }

  /// The background update. Never throws, never removes what the phone has.
  Future<void> check(Api api, String lang, {bool force = false}) async {
    final now = DateTime.now();
    if (!force && _checkedAt != null && now.difference(_checkedAt!) < every) return;
    _checkedAt = now;
    try {
      final manifest = await _manifest(api);
      if (manifest == null) return;
      final entry = (manifest['languages'] as List?)?.whereType<Map>().where((l) => l['code'] == lang).firstOrNull;
      final version = entry?['version'], sha = entry?['sha256'];
      if (version is! int || sha is! String || version <= active.version) return;
      final kept = await store.read(lang);
      if (kept != null && kept.version >= version) {
        _pending = lang == active.lang && kept.version > active.version;
        return;
      }
      final res = await api.raw('/driver/translations/bundle/$lang/$version');
      if (res.statusCode != 200) return;
      final installed = await store.install(lang, res.bodyBytes, version: version, sha256: sha);
      if (installed && lang == active.lang) _pending = true;
      if (!installed) await onError?.call('l10n.install', 'bundle $lang v$version refused', StackTrace.current);
    } on ApiError {
      // offline or a server error: next time
    } catch (e, st) {
      await onError?.call('l10n.check', e, st);
    }
  }

  Future<Map?> _manifest(Api api) async {
    final etag = await db.get('l10n_etag');
    final res = await api.raw(
      '/driver/translations/manifest',
      headers: {'If-None-Match': ?etag},
      timeout: const Duration(seconds: 15),
    );
    Object? body;
    if (res.statusCode == 304) {
      final kept = await db.get('l10n_manifest');
      body = kept == null ? null : jsonDecode(kept);
    } else if (res.statusCode == 200) {
      body = jsonDecode(utf8.decode(res.bodyBytes));
      if (body is Map) {
        await db.put('l10n_manifest', jsonEncode(body));
        if (res.headers['etag'] != null) await db.put('l10n_etag', res.headers['etag']);
        final list = [for (final j in (body['languages'] as List? ?? const [])) ?AppLanguage.fromJson(j)];
        if (list.isNotEmpty) {
          _languages = list;
          await db.put('l10n_languages', jsonEncode([for (final l in list) l.toJson()]));
        }
      }
    }
    return body is Map ? body : null;
  }
}

/// The app's localizations for any locale: the built-in strings of the language (English for one the app does not
/// ship), with the active published strings over them when they are this language's.
AppLocalizations appStrings(Locale locale, RemoteStrings remote) {
  final supported = AppLocalizations.supportedLocales.any((l) => l.languageCode == locale.languageCode);
  final base = lookupAppLocalizations(supported ? Locale(locale.languageCode) : const Locale('en'));
  return RemoteLocalizations(base, remote.lang == locale.languageCode ? remote : RemoteStrings.empty);
}

class AppStringsDelegate extends LocalizationsDelegate<AppLocalizations> {
  const AppStringsDelegate(this.remote);

  final RemoteStrings remote;

  @override
  bool isSupported(Locale locale) => true;

  @override
  Future<AppLocalizations> load(Locale locale) => Future.value(appStrings(locale, remote));

  @override
  bool shouldReload(AppStringsDelegate old) => !identical(old.remote, remote);
}

/// Material's and Cupertino's own strings (dialogs, pickers): English for a language Flutter does not ship.
class FallbackDelegate<T> extends LocalizationsDelegate<T> {
  const FallbackDelegate(this.inner);

  final LocalizationsDelegate<T> inner;

  @override
  Type get type => inner.type;

  @override
  bool isSupported(Locale locale) => true;

  @override
  Future<T> load(Locale locale) => inner.load(inner.isSupported(locale) ? locale : const Locale('en'));

  @override
  bool shouldReload(FallbackDelegate<T> old) => false;
}
