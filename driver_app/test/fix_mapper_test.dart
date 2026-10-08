import 'package:fleet_driver/tracking/fix_mapper.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';

Position position({required double speed, required bool hasSpeed, double heading = 0, bool hasHeading = false}) =>
    Position(
      latitude: 29.3,
      longitude: 48.0,
      timestamp: DateTime.utc(2026, 10, 8, 9),
      accuracy: 8,
      altitude: 0,
      altitudeAccuracy: 0,
      heading: heading,
      headingAccuracy: 0,
      speed: speed,
      speedAccuracy: 0,
      hasSpeed: hasSpeed,
      hasHeading: hasHeading,
    );

void main() {
  test('no measurement is unknown, not 0 (Android fills in 0.0 when it measured nothing)', () {
    final f = fixFromPosition(position(speed: 0, hasSpeed: false));
    expect((f.speedKmh, f.heading), (null, null));
  });

  test('a measured speed is in km/h, a measured bearing within 0-359, a real stop stays 0', () {
    final moving = fixFromPosition(position(speed: 10, hasSpeed: true, heading: 370, hasHeading: true));
    expect((moving.speedKmh, moving.heading), (36, 10));
    expect(fixFromPosition(position(speed: 0, hasSpeed: true)).speedKmh, 0);
  });
}
