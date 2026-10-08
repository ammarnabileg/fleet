import 'package:geolocator/geolocator.dart';

import 'tracker.dart';

/// A plugin position as a [Fix]. Android leaves out the speed and the bearing when it did not measure them, and the
/// plugin then fills in 0.0: only the has* flags tell a real stop from no measurement, which stays null (the tracker
/// works the speed out from the distance between fixes).
Fix fixFromPosition(Position p) => Fix(
  at: p.timestamp,
  lat: p.latitude,
  lng: p.longitude,
  accuracyM: p.accuracy,
  speedKmh: p.hasSpeed && p.speed >= 0 ? p.speed * 3.6 : null,
  heading: p.hasHeading && p.heading >= 0 ? p.heading.round() % 360 : null,
  isMock: p.isMocked,
);
