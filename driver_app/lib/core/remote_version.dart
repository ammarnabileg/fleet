/// The newest version of the app as Firebase Remote Config says (the dashboard's «تحديث التطبيق» writes it there):
/// the app compares it with its own build number before asking the server.
class RemoteVersion {
  const RemoteVersion({required this.code, this.name = '', this.force = false, this.url = ''});

  /// driver_latest_version_code: the versionCode (the build number this app compares with its own).
  final int code;

  /// driver_latest_version_name, as the CI names the build ("0.1.1057").
  final String name;

  /// driver_force_update: older apps must update before they can be used.
  final bool force;

  /// driver_download_url: the public link on the server's own address.
  final String url;

  /// The values read from Remote Config; null when there is no usable version (never published: 0 or missing).
  static RemoteVersion? fromValues(Map<String, String> values) {
    final code = int.tryParse((values['driver_latest_version_code'] ?? '').trim());
    if (code == null || code <= 0) return null;
    return RemoteVersion(
      code: code,
      name: values['driver_latest_version_name'] ?? '',
      force: (values['driver_force_update'] ?? '').trim().toLowerCase() == 'true',
      url: values['driver_download_url'] ?? '',
    );
  }
}

/// Where the updater reads it; null from [read] means "not available" (Firebase off, never fetched, no value):
/// the updater then asks the server's /driver/app-update as before. Fakes in tests.
abstract class RemoteVersionSource {
  Future<RemoteVersion?> read();
}
