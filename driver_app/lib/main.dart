import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:geolocator/geolocator.dart';

import 'app/push.dart';
import 'app/state.dart';
import 'core/db.dart';
import 'core/device.dart';
import 'l10n/app_localizations.dart';
import 'tracking/service.dart';
import 'ui/screens/home.dart';
import 'ui/screens/onboarding.dart';
import 'ui/screens/permissions.dart';
import 'ui/screens/sign_in.dart';
import 'ui/screens/splash.dart';
import 'ui/screens/waiting.dart';
import 'ui/theme.dart';
import 'ui/widgets/common.dart';

final _theme = appTheme(); // built once, not on every rebuild

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final db = await AppDb.open();
  final state = AppState(
    db: db,
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
    ),
  );
  final links = AppLinks();
  runApp(DriverApp(state: state, links: links.uriLinkStream, initialLink: links.getInitialLink()));
  await state.boot(deviceLang: WidgetsBinding.instance.platformDispatcher.locale.languageCode);
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
    if (token == null || _activating != null) return;
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
    if (_activating != null) {
      return ActivatingScreen(error: _activationError, onBack: () => setState(() => _activating = null));
    }
    if (s.splashing && s.splashImage != null && s.splash != null) {
      return SplashView(image: s.splashImage!, color: s.splash!.color);
    }
    return switch (s.phase) {
      Phase.booting => const Scaffold(body: Center(child: CircularProgressIndicator())),
      Phase.signedOut => SignInScreen(state: s),
      Phase.permissions => PermissionsScreen(state: s),
      Phase.onboarding => OnboardingScreen(key: ValueKey(s.onboarding?.status), state: s),
      Phase.waiting => WaitingScreen(state: s),
      Phase.blocked => WaitingScreen(state: s, blocked: true),
      Phase.ready => HomeScreen(state: s),
    };
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Driver',
      debugShowCheckedModeBanner: false,
      theme: _theme,
      locale: Locale(widget.state.lang),
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: _home(),
    );
  }
}
