import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';

/// Firebase Cloud Messaging on the phone, set up from the values the server gives (GET /driver/app-config "push"),
/// so a client switches push on from its control panel without a new build of the app. Returns the phone's token, or
/// null when the driver refused notifications.
class FirebasePush {
  static bool _ready = false;

  /// Firebase is started on this phone (push is switched on and the driver signed in): Remote Config can be read.
  static bool get ready => _ready;

  /// Called once Firebase has started (the app fetches Remote Config then, in the background).
  static void Function()? onReady;

  /// A push the driver tapped (the app in the background or closed): its data, so the app opens at its place.
  static void Function(Map<String, dynamic> data)? onOpened;

  static Future<String?> token(
    Map<String, dynamic> config, {
    required void Function(String token) onRefresh,
    required void Function() onMessage,
  }) async {
    if (!_ready) {
      await Firebase.initializeApp(
        options: FirebaseOptions(
          apiKey: config['api_key'] as String,
          appId: config['app_id'] as String,
          messagingSenderId: config['sender_id'] as String,
          projectId: config['project_id'] as String,
        ),
      );
      _ready = true;
      onReady?.call();
      FirebaseMessaging.instance.onTokenRefresh.listen(onRefresh);
      FirebaseMessaging.onMessage.listen((_) => onMessage()); // in the foreground: the badge, not a banner
      FirebaseMessaging.onMessageOpenedApp.listen((m) => onOpened?.call(m.data));
      final initial = await FirebaseMessaging.instance.getInitialMessage();
      if (initial != null) onOpened?.call(initial.data);
    }
    final settings = await FirebaseMessaging.instance.requestPermission();
    if (settings.authorizationStatus == AuthorizationStatus.denied) return null;
    return FirebaseMessaging.instance.getToken();
  }
}
