import 'package:battery_plus/battery_plus.dart';
import 'package:geolocator/geolocator.dart';
import 'package:permission_handler/permission_handler.dart';

/// The phone's state the supervisors need to trust the map: the server alerts when location permission, GPS or
/// the tracking service is off during a custody.
class PhoneHealth {
  static Future<String> locationPermission() async {
    switch (await Geolocator.checkPermission()) {
      case LocationPermission.always:
        return 'always';
      case LocationPermission.whileInUse:
        return 'while_in_use';
      case LocationPermission.denied:
      case LocationPermission.deniedForever:
        return 'denied';
      case LocationPermission.unableToDetermine:
        return 'unknown';
    }
  }

  static Future<Map<String, dynamic>> snapshot({
    required bool trackingRunning,
    required int queueSize,
    String? lastUploadAt,
    required String appVersion,
  }) async {
    int? battery;
    try {
      battery = await Battery().batteryLevel;
    } catch (_) {
      battery = null;
    }
    bool? batteryIgnored;
    try {
      batteryIgnored = await Permission.ignoreBatteryOptimizations.isGranted;
    } catch (_) {
      batteryIgnored = null;
    }
    return {
      'location_permission': await locationPermission(),
      'gps_enabled': await Geolocator.isLocationServiceEnabled(),
      'battery_optimization_ignored': batteryIgnored,
      'tracking_service_running': trackingRunning,
      'battery_level': battery,
      'queue_size': queueSize,
      'last_upload_at': lastUploadAt,
      'app_version': appVersion,
    };
  }
}
