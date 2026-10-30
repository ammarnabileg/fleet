import 'dart:async';
import 'dart:io';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:geolocator/geolocator.dart';
import 'package:path_provider/path_provider.dart';

import 'app/push.dart';
import 'app/remote_config.dart';
import 'app/state.dart';
import 'core/db.dart';
import 'core/device.dart';
import 'core/error_log.dart';
import 'core/translations.dart';
import 'core/updater.dart';
import 'l10n/app_localizations.dart';
import 'tracking/notice.dart';
import 'tracking/service.dart';
import 'tracking/system_notices.dart';
import 'ui/screens/company.dart';
import 'ui/screens/home.dart';
import 'ui/screens/language.dart';
import 'ui/screens/notifications.dart' show noticeTarget;
import 'ui/screens/onboarding.dart';
import 'ui/screens/permissions.dart';
import 'ui/screens/sign_in.dart';
import 'ui/screens/splash.dart';
import 'ui/screens/update.dart';
import 'ui/screens/waiting.dart';
import 'ui/theme.dart';
import 'ui/widgets/common.dart';

final _theme = appTheme(); // built once, not on every rebuild
const _phone = MethodChannel('fleet/phone'); // the dialer (MainActivity): no call permission, the driver presses call
const _update = MethodChannel('fleet/update'); // the in-app update's installer side (MainActivity)

Future<bool> _ask(String method, [Object? arg]) async {
  try {
    return await _update.invokeMethod<bool>(method, arg) ?? false;
  } on PlatformException {
    return false;
  } on MissingPluginException {
    return false;
  }
}

Future<void> main() async {
  // whatever escapes goes to the phone's local error log (no outside service, no driver data in it)
  AppDb? opened;
  await runZonedGuarded(
    () async {
      WidgetsFlutterBinding.ensureInitialized();
      FlutterError.onError = (d) {
        FlutterError.presentError(d);
        if (opened != null) unawaited(ErrorLog(opened!).record('flutter', d.exception, d.stack));
      };
      final db = opened = await AppDb.open();
      await _main(db);
    },
    (e, st) {
      if (opened != null) unawaited(ErrorLog(opened!).record('zone', e, st));
    },
  );
}

Future<void> _main(AppDb db) async {
  final notices = FlutterLocalNotificationsPlugin();
  late final AppState state;
  state = AppState(
    db: db,
    stringsDir: () => getApplicationSupportDirectory().then<Directory?>((d) => d, onError: (Object _) => null),
    platform: PhoneHooks(
      permissionsOk: Perms.ok,
      startTracking: () async {
        final always = await Geolocator.checkPermission() == LocationPermission.always;
        await TrackingService.configure(startOnBoot: always);
        await TrackingService.start();
      },
      stopTracking: () async => TrackingService.stop(),
      deviceMeta: DeviceIdentity.meta,
      pushToken: FirebasePush.token,
      remoteVersion: FirebaseRemoteVersion(),
      dial: (phone) async {
        try {
          return await _phone.invokeMethod<bool>('dial', phone) ?? false;
        } on PlatformException {
          return false;
        }
      },
      openLocationSettings: () async => Geolocator.openLocationSettings(),
      // the current situations as system notifications (system_notices.dart), in the app's language
      notices: PluginPoster(notices, strings: () async => state.strings),
      updates: UpdateHooks(
        // the cache's "updates" folder: the only one the FileProvider shares with the installer
        dir: () async => Directory('${(await getTemporaryDirectory()).path}/updates'),
        canInstall: () => _ask('canInstall'),
        openInstallSettings: () => _ask('openInstallSettings'),
        install: (path) => _ask('install', path),
        unmetered: () => _ask('unmetered'),
      ),
    ),
  );
  final links = AppLinks();
  // a tap on a notification: its button («Call», «Open location settings»), or the app at the right place (the inbox,
  // the maintenance or accident screen)
  Future<void> tapped(NotificationResponse r) => runNoticeTap(
    noticeTap(r.actionId, r.payload),
    dial: state.platform.dial,
    openLocationSettings: state.platform.openLocationSettings,
    acknowledge: state.acknowledgeContact,
    open: state.navigate,
  );
  // a tapped push from the office: the screen it is about (his car, a payslip, a maintenance request...), the inbox
  // for a broadcast or a kind this app does not know
  FirebasePush.onOpened = (data) => state.navigate(noticeTarget('${data['kind'] ?? ''}'));
  // Firebase started: Remote Config (the newest version the office announced) fetched in the background
  FirebasePush.onReady = () => unawaited(FirebaseRemoteVersion.prefetch());
  NotificationResponse? launched;
  try {
    await notices.initialize(
      settings: const InitializationSettings(android: AndroidInitializationSettings('ic_bg_service_small')),
      onDidReceiveNotificationResponse: (r) => unawaited(tapped(r)),
      onDidReceiveBackgroundNotificationResponse: noticeBackgroundTap,
    );
    await PluginPoster.createChannels(notices, state.strings); // before any push arrives on them
    final launch = await notices.getNotificationAppLaunchDetails();
    if (launch?.didNotificationLaunchApp == true) launched = launch!.notificationResponse;
  } catch (_) {
    // no notifications on this phone (or none set up): the cards in the app say the same
  }
  runApp(DriverApp(state: state, links: links.uriLinkStream, initialLink: links.getInitialLink()));
  await state.boot(deviceLang: WidgetsBinding.instance.platformDispatcher.locale.languageCode);
  if (launched != null) await tapped(launched);
}

class DriverApp extends StatefulWidget {
  const DriverApp({super.key, required this.state, this.links, this.initialLink});

  final AppState state;
  final Stream<Uri>? links;
  final Future<Uri?>? initialLink;

  @override
  State<DriverApp> createState() => _DriverAppState();
}

class _DriverAppState extends State<DriverApp> with WidgetsBindingObserver {
  StreamSubscription<Uri>? _links;
  String? _activating;
  String? _activationError;
  String? _confirming; // a link opened while a driver is signed in: waits for his yes

  @override
  void initState() {
    super.initState();
    widget.state.addListener(_changed);
    WidgetsBinding.instance.addObserver(this);
    // the activation link opens the app: an Android App Link (https://<server>/activate#t=...) or btfleet://
    // from the fallback page. The link that launched the app comes through initialLink.
    _links = widget.links?.listen(_onLink);
    widget.initialLink?.then((uri) {
      if (uri != null) _onLink(uri);
    });
  }

  void _changed() => setState(() {});

  // back to the app: his car may have changed meanwhile (handed over, swapped, taken back)
  @override
  void didChangeAppLifecycleState(AppLifecycleState s) {
    if (s == AppLifecycleState.resumed) unawaited(widget.state.resumed());
  }

  Future<void> _onLink(Uri uri) async {
    final token = AppState.activationToken(uri);
    if (token == null || _activating != null || _confirming != null) return;
    // a driver signed in already: the link (any app or page can open it) replaces him only when he says so
    if (await widget.state.hasSession()) {
      if (mounted) setState(() => _confirming = token);
      return;
    }
    await _activate(token);
  }

  Future<void> _activate(String token) async {
    if (!mounted) return;
    setState(() {
      _activating = token;
      _activationError = null;
    });
    try {
      await widget.state.activate(token);
      if (mounted) setState(() => _activating = null);
    } catch (e) {
      if (!mounted) return;
      setState(() => _activationError = errorText(context, widget.state, e));
    }
  }

  @override
  void dispose() {
    widget.state.removeListener(_changed);
    WidgetsBinding.instance.removeObserver(this);
    _links?.cancel();
    super.dispose();
  }

  Widget _home() {
    final s = widget.state;
    if (_confirming != null) {
      final token = _confirming!;
      return ConfirmActivationScreen(
        onConfirm: () {
          setState(() => _confirming = null);
          unawaited(_activate(token));
        },
        onCancel: () => setState(() => _confirming = null),
      );
    }
    if (_activating != null) {
      return ActivatingScreen(error: _activationError, onBack: () => setState(() => _activating = null));
    }
    if (s.splashing && s.splashImage != null && s.splash != null) {
      return SplashView(image: s.splashImage!, color: s.splash!.color);
    }
    // a required update: the screens wait (the tracking service and the outbox keep sending behind)
    if (s.updater.blocking && s.phase != Phase.booting) return UpdateRequiredScreen(state: s);
    return switch (s.phase) {
      Phase.booting => const Scaffold(body: Center(child: CircularProgressIndicator())),
      Phase.signedOut when !s.langChosen => LanguageScreen(state: s),
      Phase.signedOut => SignInScreen(state: s),
      Phase.permissions => PermissionsScreen(state: s),
      Phase.onboarding => OnboardingScreen(key: ValueKey(s.onboarding?.status), state: s),
      Phase.waiting => WaitingScreen(state: s),
      Phase.company => CompanyScreen(state: s),
      Phase.blocked => WaitingScreen(state: s, blocked: true),
      Phase.ready => HomeScreen(state: s),
      Phase.failed => StartFailedScreen(onRetry: () => unawaited(s.retryStart())),
    };
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Ajwad Driver',
      debugShowCheckedModeBanner: false,
      theme: _theme,
      locale: Locale(widget.state.lang),
      supportedLocales: AppLocalizations.supportedLocales,
      // the driver's language even when the app has no built-in strings for it (one added on the server)
      localeResolutionCallback: (locale, _) => locale,
      localizationsDelegates: [
        AppStringsDelegate(widget.state.translations.active),
        const FallbackDelegate(GlobalMaterialLocalizations.delegate),
        const FallbackDelegate(GlobalWidgetsLocalizations.delegate),
        const FallbackDelegate(GlobalCupertinoLocalizations.delegate),
      ],
      // right to left for Arabic only (the language list's direction), whatever Flutter guesses for the locale
      builder: (context, child) =>
          Directionality(textDirection: widget.state.rtl ? TextDirection.rtl : TextDirection.ltr, child: child!),
      home: _home(),
    );
  }
}
