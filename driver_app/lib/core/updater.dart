import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'api.dart';
import 'db.dart';
import 'errors.dart';
import 'remote_version.dart';

/// A published release newer than this app (GET /driver/app-update).
class AppUpdate {
  AppUpdate({
    required this.versionCode,
    required this.versionName,
    required this.size,
    required this.sha256,
    required this.url,
    this.notes,
  });

  factory AppUpdate.fromJson(Map<String, dynamic> j) => AppUpdate(
    versionCode: (j['version_code'] as num).toInt(),
    versionName: j['version_name'] as String,
    size: (j['size'] as num).toInt(),
    sha256: j['sha256'] as String,
    url: j['url'] as String,
    notes: j['notes'] as String?,
  );

  Map<String, dynamic> toJson() => {
    'version_code': versionCode,
    'version_name': versionName,
    'size': size,
    'sha256': sha256,
    'url': url,
    'notes': notes,
  };

  final int versionCode;
  final String versionName;
  final int size;
  final String sha256;
  final String url;
  final String? notes;
}

/// What needs Android (MainActivity's "fleet/update" channel); fakes in tests.
class UpdateHooks {
  UpdateHooks({
    required this.dir,
    required this.canInstall,
    required this.openInstallSettings,
    required this.install,
    required this.unmetered,
  });

  /// Where the APK is downloaded (the app's cache: the FileProvider shares only that folder with the installer).
  final Future<Directory> Function() dir;

  /// Whether Android lets this app install packages ("Install unknown apps" for this app, Android 8+).
  final Future<bool> Function() canInstall;

  /// The system page where the driver allows it.
  final Future<void> Function() openInstallSettings;

  /// Hands the APK to Android's package installer, which asks the driver to confirm (a sideloaded app can never
  /// install silently). False when it could not be started.
  final Future<bool> Function(String path) install;

  /// On Wi-Fi (or another unmetered network): a download may start without asking.
  final Future<bool> Function() unmetered;
}

enum UpdateStage { idle, downloading, ready, needsPermission, installing, failed }

/// Finds, downloads, checks and hands over the app's new versions. The app is installed from an APK, not from a
/// store: the office's «تحديث التطبيق» says which version is the newest and whether it is required, in Firebase
/// Remote Config ([remote]) and on the server.
///
/// - Remote Config first, when Firebase is started: its versionCode not above this build means up to date, with no
///   request to the server; above it, the server gives the file to download (size, sha256), and a forced update in
///   Remote Config makes it required. Remote Config not available (Firebase off, nothing fetched): the server
///   decides alone, as before.
/// - Checks after the first screen, on resume at most every [every], and when the driver asks.
/// - A required update blocks the screens (never the tracking service or the outbox: [beforeBlock] sends what is
///   queued first, and they keep sending in the background meanwhile).
/// - Downloads to the cache, resuming a cut download with a Range request, then checks size and sha256: a file that
///   does not match is deleted, never installed.
/// - Never downloads on mobile data unless the driver tapped «Update».
class Updater extends ChangeNotifier {
  Updater({
    required this.db,
    required this.api,
    required this.hooks,
    required this.currentBuild,
    http.Client? client,
    this.every = const Duration(hours: 6),
    this.beforeBlock,
    this.remote,
    DateTime Function()? now,
  }) : _http = client ?? api.client,
       _now = now ?? DateTime.now;

  final AppDb db;
  final Api api;
  final UpdateHooks hooks;
  final int currentBuild;
  final Duration every;
  final http.Client _http;
  final DateTime Function() _now;

  /// Sends what is queued (outbox, positions) before a required update blocks the screens.
  final Future<void> Function()? beforeBlock;

  /// Firebase Remote Config's version (null: the server only).
  RemoteVersionSource? remote;

  /// Who answered the last check: 'remote' (Remote Config, the server giving the file) or 'server'.
  String? source;

  AppUpdate? available;
  bool _required = false;
  UpdateStage stage = UpdateStage.idle;
  int received = 0;
  String? error; // an ApiError code, 'checksum', 'install'
  bool checking = false;
  bool dismissed = false; // the optional banner, closed for this version
  DateTime? checkedAt;

  /// The screens are blocked: a required update, after the queue was given its chance.
  bool get blocking => _required && available != null;
  bool get requiredUpdate => _required;
  double? get progress => available == null || available!.size == 0 ? null : received / available!.size;
  bool get showBanner => available != null && !_required && !dismissed;

  static const _key = 'app_update';
  static const _checkedKey = 'app_update_checked_at';
  static const _dismissedKey = 'app_update_dismissed';

  /// At start: the last answer kept (a required update stays required offline), and old downloads removed.
  Future<void> load() async {
    try {
      final raw = await db.get(_key);
      final at = await db.get(_checkedKey);
      checkedAt = at == null ? null : DateTime.tryParse(at);
      if (raw != null) {
        final j = jsonDecode(raw) as Map<String, dynamic>;
        final u = j['latest'] == null ? null : AppUpdate.fromJson(j['latest'] as Map<String, dynamic>);
        if (u != null && u.versionCode > currentBuild) {
          available = u;
          _required = j['required'] == true;
          dismissed = await db.get(_dismissedKey) == '${u.versionCode}';
        }
      }
    } catch (_) {
      // nothing kept that can be read: the next check asks again
    }
    await cleanUp();
    if (available != null) await _findDownloaded();
    notifyListeners();
  }

  /// Asks the server (no session needed: the sign-in screen updates too). [force]: the driver's button, whatever
  /// the time since the last check. Returns false when the server could not be reached. Never throws.
  Future<bool> check({bool force = false}) async {
    if (checking) return true;
    final last = checkedAt;
    if (!force && last != null && _now().difference(last) < every) return true;
    checking = true;
    error = null;
    notifyListeners();
    try {
      final rv = await _remoteVersion();
      final Map<String, dynamic> j;
      if (rv != null && rv.code <= currentBuild) {
        j = {'latest': null, 'required': false}; // Remote Config: this build is the newest
      } else {
        final body = await api.get(
          '/driver/app-update',
          query: {'version_code': '$currentBuild', 'lang': api.lang},
          auth: false,
        );
        j = Map<String, dynamic>.of(body as Map<String, dynamic>);
        final latest = j['latest'] as Map<String, dynamic>?;
        // forced in Remote Config: required, for the version it names or a newer one the server offers
        if (rv != null && rv.force && latest != null && (latest['version_code'] as num).toInt() >= rv.code) {
          j['required'] = true;
        }
      }
      source = rv == null ? 'server' : 'remote';
      checkedAt = _now();
      await db.put(_checkedKey, checkedAt!.toIso8601String());
      await db.put(_key, jsonEncode(j));
      final u = j['latest'] == null ? null : AppUpdate.fromJson(j['latest'] as Map<String, dynamic>);
      final required = u != null && j['required'] == true;
      if (u?.versionCode != available?.versionCode) {
        stage = UpdateStage.idle;
        received = 0;
        dismissed = u != null && await db.get(_dismissedKey) == '${u.versionCode}';
      }
      available = u;
      if (required && !_required && beforeBlock != null) {
        // the queue goes first (it keeps going in the background after, the block is the screens only)
        try {
          await beforeBlock!().timeout(const Duration(seconds: 20));
        } catch (_) {
          // offline: what is queued stays queued, never lost, and is sent when the network is back
        }
      }
      _required = required;
      if (u != null) {
        await _findDownloaded();
        if (stage == UpdateStage.idle && await _quietly(hooks.unmetered)) unawaited(download());
      }
      return true;
    } on ApiError catch (e) {
      if (!e.isNetwork) error = e.code;
      return false;
    } catch (_) {
      return false;
    } finally {
      checking = false;
      notifyListeners();
    }
  }

  /// Remote Config's answer, or null when it is not available (never throws, never waits long).
  Future<RemoteVersion?> _remoteVersion() async {
    final r = remote;
    if (r == null) return null;
    try {
      return await r.read().timeout(const Duration(seconds: 15));
    } catch (_) {
      return null;
    }
  }

  Future<bool> _quietly(Future<bool> Function() f) async {
    try {
      return await f();
    } catch (_) {
      return false;
    }
  }

  /// The optional banner, closed: not shown again for this version (the Me screen still offers it).
  Future<void> dismiss() async {
    dismissed = true;
    notifyListeners();
    if (available != null) await db.put(_dismissedKey, '${available!.versionCode}');
  }

  Future<File> _file(AppUpdate u, {bool part = false}) async =>
      File('${(await hooks.dir()).path}/update-${u.versionCode}.apk${part ? '.part' : ''}');

  Future<void> _findDownloaded() async {
    final u = available;
    if (u == null || stage == UpdateStage.downloading) return;
    try {
      final f = await _file(u);
      if (await f.exists() && await f.length() == u.size) {
        stage = UpdateStage.ready;
        received = u.size;
      } else {
        final p = await _file(u, part: true);
        received = await p.exists() ? await p.length() : 0;
      }
    } catch (_) {
      // no cache folder now: downloaded when asked
    }
  }

  /// Downloads the APK (resuming a part already there), then checks its size and sha256.
  Future<void> download() async {
    final u = available;
    if (u == null || stage == UpdateStage.downloading || stage == UpdateStage.ready) return;
    stage = UpdateStage.downloading;
    error = null;
    notifyListeners();
    try {
      final part = await _file(u, part: true);
      await part.parent.create(recursive: true);
      var have = await part.exists() ? await part.length() : 0;
      if (have > u.size) {
        await part.delete();
        have = 0;
      }
      if (have < u.size) {
        final req = http.Request('GET', Uri.parse('${api.baseUrl}${u.url}'))
          ..headers['User-Agent'] = api.userAgent
          ..headers['Accept-Language'] = api.lang;
        if (have > 0) req.headers['Range'] = 'bytes=$have-';
        final res = await _http.send(req).timeout(const Duration(seconds: 30));
        if (res.statusCode != 200 && res.statusCode != 206) {
          throw ApiError(res.statusCode, res.statusCode == 404 ? 'app_release_not_found' : 'http_${res.statusCode}');
        }
        final resume = res.statusCode == 206 && have > 0;
        received = resume ? have : 0;
        final sink = part.openWrite(mode: resume ? FileMode.append : FileMode.write);
        var last = DateTime.now();
        try {
          await for (final chunk in res.stream.timeout(const Duration(seconds: 60))) {
            sink.add(chunk);
            received += chunk.length;
            if (received > u.size) break;
            if (DateTime.now().difference(last) > const Duration(milliseconds: 200)) {
              last = DateTime.now();
              notifyListeners();
            }
          }
        } finally {
          await sink.close();
        }
      }
      if (!await _verify(part, u)) {
        await part.delete();
        received = 0;
        stage = UpdateStage.failed;
        error = 'checksum';
        return;
      }
      await part.rename((await _file(u)).path);
      stage = UpdateStage.ready;
    } on ApiError catch (e) {
      stage = UpdateStage.failed;
      error = e.code;
    } on SocketException {
      stage = UpdateStage.failed;
      error = 'network';
    } on TimeoutException {
      stage = UpdateStage.failed;
      error = 'network';
    } on http.ClientException {
      stage = UpdateStage.failed;
      error = 'network';
    } on FileSystemException {
      stage = UpdateStage.failed;
      error = 'storage';
    } finally {
      notifyListeners();
    }
  }

  Future<bool> _verify(File f, AppUpdate u) async {
    if (await f.length() != u.size) return false;
    final digest = await sha256.bind(f.openRead()).first;
    return digest.toString() == u.sha256.toLowerCase();
  }

  /// Opens Android's installer on the checked APK; without the permission, says so (the screen offers the setting).
  Future<void> install() async {
    final u = available;
    if (u == null) return;
    if (stage != UpdateStage.ready && stage != UpdateStage.needsPermission) {
      await download();
      if (stage != UpdateStage.ready) return;
    }
    final f = await _file(u);
    if (!await f.exists() || !await _verify(f, u)) {
      // changed on the disk since: never installed
      if (await f.exists()) await f.delete();
      stage = UpdateStage.failed;
      error = 'checksum';
      received = 0;
      notifyListeners();
      return;
    }
    if (!await _quietly(hooks.canInstall)) {
      stage = UpdateStage.needsPermission;
      notifyListeners();
      return;
    }
    stage = UpdateStage.installing;
    notifyListeners();
    final ok = await _quietly(() => hooks.install(f.path));
    stage = ok ? UpdateStage.ready : UpdateStage.failed;
    if (!ok) error = 'install';
    notifyListeners();
  }

  Future<void> openInstallSettings() async {
    try {
      await hooks.openInstallSettings();
    } catch (_) {
      // no such page on this phone: the message says where it is
    }
  }

  /// Back from the system setting (or the installer): allowed now? Then on to the installer.
  Future<void> resumed() async {
    if (stage == UpdateStage.needsPermission && await _quietly(hooks.canInstall)) {
      await install();
    } else if (stage == UpdateStage.installing) {
      stage = UpdateStage.ready; // the installer was left without installing: the button again
      notifyListeners();
    }
  }

  /// The downloads that are of no use any more: the installed version or older, and parts of other versions.
  Future<void> cleanUp() async {
    try {
      final dir = await hooks.dir();
      if (!await dir.exists()) return;
      await for (final e in dir.list()) {
        final m = RegExp(r'update-(\d+)\.apk(\.part)?$').firstMatch(e.path);
        if (e is! File || m == null) continue;
        final code = int.parse(m.group(1)!);
        if (code <= currentBuild || (available != null && code != available!.versionCode)) await e.delete();
      }
    } catch (_) {
      // tried again at the next start
    }
  }
}
