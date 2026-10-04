import 'dart:io';

import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../app/state.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Location ("all the time"), notifications (the tracking notification) and battery: asked once, explained.
class Perms {
  static Future<bool> locationOk() async {
    final p = await Geolocator.checkPermission();
    return p == LocationPermission.always || p == LocationPermission.whileInUse;
  }

  static Future<bool> notificationsOk() async => !Platform.isAndroid || await Permission.notification.isGranted;

  /// Enough to start: location while in use (the foreground service keeps it while tracking) and notifications.
  static Future<bool> ok() async => await locationOk() && await notificationsOk();
}

class PermissionsScreen extends StatefulWidget {
  const PermissionsScreen({super.key, required this.state});

  final AppState state;

  @override
  State<PermissionsScreen> createState() => _PermissionsScreenState();
}

class _PermissionsScreenState extends State<PermissionsScreen> with WidgetsBindingObserver {
  LocationPermission _location = LocationPermission.denied;
  bool _notifications = false;
  bool _battery = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _check();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState s) {
    if (s == AppLifecycleState.resumed) _check(); // back from the settings screen
  }

  Future<void> _check() async {
    final loc = await Geolocator.checkPermission();
    final n = await Perms.notificationsOk();
    final b = await Permission.ignoreBatteryOptimizations.isGranted;
    if (!mounted) return;
    setState(() {
      _location = loc;
      _notifications = n;
      _battery = b;
    });
  }

  Future<void> _askLocation() async {
    var p = await Geolocator.checkPermission();
    if (p == LocationPermission.denied) p = await Geolocator.requestPermission();
    if (p == LocationPermission.whileInUse) await Permission.locationAlways.request(); // Android opens its own screen
    if (p == LocationPermission.deniedForever) await Geolocator.openAppSettings();
    await _check();
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    final locationOk = _location == LocationPermission.always || _location == LocationPermission.whileInUse;
    Widget row(
      IconData icon,
      String title,
      String why,
      bool granted, {
      bool partial = false,
      required Future<void> Function() ask,
    }) => Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(icon, color: granted ? AppColors.success : AppColors.primary),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 2),
                  Text(why, style: const TextStyle(color: AppColors.muted, fontSize: 13, height: 1.5)),
                ],
              ),
            ),
            const SizedBox(width: 8),
            granted && !partial
                ? Pill(l.permGranted, tone: BannerTone.success)
                : TextButton(onPressed: ask, child: Text(l.permGrant)),
          ],
        ),
      ),
    );
    return Scaffold(
      appBar: AppBar(title: Text(l.permTitle)),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text(l.permIntro, style: const TextStyle(height: 1.7)),
          const SizedBox(height: 16),
          row(
            Icons.location_on_outlined,
            l.permLocation,
            l.permLocationWhy,
            locationOk,
            partial: _location == LocationPermission.whileInUse,
            ask: _askLocation,
          ),
          const SizedBox(height: 10),
          row(
            Icons.notifications_outlined,
            l.permNotifications,
            l.permNotificationsWhy,
            _notifications,
            ask: () async {
              // refused for good: Android shows no dialog any more, only the app settings can allow it
              if (await Permission.notification.request() == PermissionStatus.permanentlyDenied) {
                await openAppSettings();
              }
              await _check();
            },
          ),
          const SizedBox(height: 10),
          row(
            Icons.battery_charging_full_outlined,
            l.permBattery,
            l.permBatteryWhy,
            _battery,
            ask: () async {
              await Permission.ignoreBatteryOptimizations.request();
              await _check();
            },
          ),
          const SizedBox(height: 24),
          if (!locationOk) Banner2(text: l.permLocationRequired, tone: BannerTone.warn),
          const SizedBox(height: 12),
          BusyButton(
            label: l.continueBtn,
            onPressed: locationOk && _notifications ? widget.state.permissionsGranted : null,
          ),
        ],
      ),
    );
  }
}
