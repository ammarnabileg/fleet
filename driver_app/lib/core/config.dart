/// Build-time settings: `flutter build apk --dart-define=API_URL=https://fleet.example.com`.
/// The activation links the supervisors send point at the same host (`<API_URL>/activate#t=...`).
class AppConfig {
  static const apiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000');
  static const appVersion = String.fromEnvironment('APP_VERSION', defaultValue: '0.1.0');

  /// How long a queued action (a reading, a report) is kept before it is shown as failed. The server accepts
  /// readings up to 48 hours late and reports up to two days back, so waiting longer is pointless.
  static const outboxMaxAge = Duration(hours: 47);
}
