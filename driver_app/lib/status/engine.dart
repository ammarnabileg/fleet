import 'dart:convert';

/// The driver's live status, as the server computes it (GET /driver/live-status): separate states (shift, car,
/// tracking) and the alerts, several at once. The office's templates say what each card says and looks like; this
/// engine only fills them with values and picks among the layouts, icons and actions built into the app. It never
/// runs anything from the server: an unknown kind is drawn as the generic card, an unknown icon as the default one,
/// an unknown action is not shown.
class StatusEngine {
  /// The template features this app understands; a config that needs more is ignored (built-in templates are used).
  static const version = 1;

  static const kinds = {
    'shift_working',
    'shift_off',
    'vehicle_maintenance',
    'custody',
    'contact',
    'location',
    'generic',
  };
  static const icons = {
    'work',
    'off',
    'car',
    'wrench',
    'breakdown',
    'wallet',
    'phone',
    'location',
    'location_off',
    'document',
    'warning',
    'info',
    'check',
    'clock',
  };
  static const actions = {
    'open_cash',
    'open_custody',
    'open_contact',
    'call_supervisor',
    'open_location_settings',
    'open_maintenance',
    'open_documents',
    'acknowledge',
  };
  static const defaultIcon = 'info';
  static const empty = '—';
  static final _placeholder = RegExp(r'\{([^{}]*)\}');

  /// The server's rule: a variable takes its value, or "—" when there is none.
  static String fill(String text, Map<String, String?> values) => text.replaceAllMapped(_placeholder, (m) {
    final v = values[m.group(1)];
    return v == null || v.isEmpty ? empty : v;
  });

  static String kindOf(String? kind) => kinds.contains(kind) ? kind! : 'generic';
  static String iconOf(String? icon) => icons.contains(icon) ? icon! : defaultIcon;
  static List<String> actionsOf(List<String> list) => [
    for (final a in list)
      if (actions.contains(a)) a,
  ];

  /// "#RRGGBB" as an ARGB int, or the fallback.
  static int colorOf(String? hex, int fallback) {
    if (hex == null || !RegExp(r'^#[0-9A-Fa-f]{6}$').hasMatch(hex)) return fallback;
    return 0xFF000000 | int.parse(hex.substring(1), radix: 16);
  }
}

class StatusTemplate {
  StatusTemplate({
    required this.code,
    required this.kind,
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
    required this.priority,
    required this.actions,
  });

  /// Tolerant: whatever is missing or of the wrong type takes the safe value.
  factory StatusTemplate.fromJson(Map<String, dynamic> j) {
    Map<String, String> texts(Object? v) => v is Map
        ? {
            for (final e in v.entries)
              if (e.value is String) '${e.key}': e.value as String,
          }
        : const {};
    return StatusTemplate(
      code: '${j['code']}',
      kind: j['kind'] is String ? j['kind'] as String : 'generic',
      icon: j['icon'] is String ? j['icon'] as String : StatusEngine.defaultIcon,
      color: j['color'] is String ? j['color'] as String : '',
      title: texts(j['title']),
      subtitle: texts(j['subtitle']),
      priority: j['priority'] is num ? (j['priority'] as num).toInt() : 0,
      actions: [
        for (final a in j['actions'] is List ? j['actions'] as List : const [])
          if (a is String) a,
      ],
    );
  }

  final String code;
  final String kind;
  final String icon;
  final String color;
  final Map<String, String> title;
  final Map<String, String> subtitle;
  final int priority;
  final List<String> actions;

  String text(Map<String, String> t, String lang) => t[lang] ?? t['ar'] ?? t['en'] ?? '';
}

/// The templates in force (cached with their version) and the ones built into the app, used when the server sent
/// none, or a config this app cannot read.
class StatusConfig {
  StatusConfig(this.version, this.templates);

  final int version;
  final Map<String, StatusTemplate> templates;

  static StatusConfig? fromJson(Object? j) {
    if (j is! Map) return null;
    final min = j['min_app_template_version'];
    if (min is num && min > StatusEngine.version) return null; // made for a newer app
    final list = j['templates'];
    if (list is! List || j['version'] is! num) return null;
    return StatusConfig((j['version'] as num).toInt(), {
      for (final t in list)
        if (t is Map) '${t['code']}': StatusTemplate.fromJson(t.cast<String, dynamic>()),
    });
  }

  StatusTemplate template(String code) => templates[code] ?? builtIn[code] ?? builtIn['generic']!;

  static StatusTemplate _t(
    String code,
    String kind,
    String icon,
    String color,
    String ar,
    String en,
    String subAr,
    String subEn,
    int priority, [
    List<String> actions = const [],
  ]) => StatusTemplate(
    code: code,
    kind: kind,
    icon: icon,
    color: color,
    title: {'ar': ar, 'en': en},
    subtitle: {'ar': subAr, 'en': subEn},
    priority: priority,
    actions: actions,
  );

  static final builtIn = {
    'shift_working': _t(
      'shift_working',
      'shift_working',
      'work',
      '#15803D',
      'في العمل',
      'Working',
      'منذ {shift_duration}',
      'For {shift_duration}',
      10,
    ),
    'shift_off': _t(
      'shift_off',
      'shift_off',
      'off',
      '#6B7280',
      'خارج الدوام',
      'Off duty',
      'لم يبدأ يوم العمل',
      'The work day has not started',
      10,
    ),
    'vehicle_maintenance': _t(
      'vehicle_maintenance',
      'vehicle_maintenance',
      'wrench',
      '#B45309',
      'السيارة في الصيانة',
      'Your car is in maintenance',
      '{center} · {stage}',
      '{center} · {stage}',
      50,
      ['open_maintenance'],
    ),
    'vehicle_breakdown': _t(
      'vehicle_breakdown',
      'vehicle_maintenance',
      'breakdown',
      '#B91C1C',
      'السيارة لا تصلح للقيادة',
      'The car is not drivable',
      'حادث مفتوح · راجع المكتب',
      'Open accident · contact the office',
      70,
    ),
    'custody_settlement': _t(
      'custody_settlement',
      'custody',
      'wallet',
      '#B45309',
      'معك {amount} د.ك للتسوية',
      'You hold {amount} KWD to settle',
      'التسوية قبل {due}',
      'Settle by {due}',
      60,
      ['open_cash'],
    ),
    'contact_request': _t(
      'contact_request',
      'contact',
      'phone',
      '#1D4ED8',
      '{supervisor} يطلب التواصل معك',
      '{supervisor} asks you to get in touch',
      'اضغط «اتصل» أو «تم»',
      'Tap Call or Done',
      90,
      ['call_supervisor', 'acknowledge'],
    ),
    'document_missing': _t(
      'document_missing',
      'generic',
      'document',
      '#B91C1C',
      '{document}',
      '{document}',
      'ناقص أو منتهٍ',
      'Missing or expired',
      40,
      ['open_documents'],
    ),
    'location_problem': _t(
      'location_problem',
      'location',
      'location_off',
      '#B91C1C',
      'الموقع لا يصل',
      'Your location is not coming through',
      'آخر تحديث {last_update}',
      'Last update {last_update}',
      80,
      ['open_location_settings'],
    ),
    'generic': _t('generic', 'generic', 'info', '#374151', '{document}', '{document}', '', '', 0),
  };
}

class StatusAlert {
  StatusAlert({
    required this.id,
    required this.code,
    required this.kind,
    required this.priority,
    required this.values,
    required this.data,
    this.expiresAt,
    this.title,
    this.subtitle,
  });

  static StatusAlert? fromJson(Object? j) {
    if (j is! Map || j['id'] is! String || j['code'] is! String) return null;
    final values = j['values'] is Map ? (j['values'] as Map) : const {};
    return StatusAlert(
      id: j['id'] as String,
      code: j['code'] as String,
      kind: j['kind'] is String ? j['kind'] as String : 'generic',
      priority: j['priority'] is num ? (j['priority'] as num).toInt() : 0,
      values: {for (final e in values.entries) '${e.key}': e.value?.toString()},
      data: j['data'] is Map ? (j['data'] as Map).cast<String, dynamic>() : const {},
      expiresAt: j['expires_at'] is String ? DateTime.tryParse(j['expires_at'] as String) : null,
      title: j['title'] as String?,
      subtitle: j['subtitle'] as String?,
    );
  }

  final String id;
  final String code;
  final String kind;
  final int priority;
  final Map<String, String?> values;
  final Map<String, dynamic> data;
  final DateTime? expiresAt;
  final String? title; // as the server rendered it (an older app's fallback)
  final String? subtitle;

  bool expired(DateTime now) => expiresAt != null && !expiresAt!.isAfter(now);
}

/// One answer of GET /driver/live-status, with when the phone received it.
class LiveStatus {
  LiveStatus({
    required this.configVersion,
    required this.receivedAt,
    required this.shift,
    required this.shiftStartedAt,
    required this.vehicle,
    required this.plate,
    required this.stage,
    required this.center,
    required this.tracking,
    required this.lastUpdate,
    required this.alerts,
    required this.sessionsToday,
  });

  static DateTime? _time(Object? v) => v is String ? DateTime.tryParse(v) : null;

  static LiveStatus? fromJson(Object? json, DateTime receivedAt) {
    if (json is! Map) return null;
    final shift = json['shift'] is Map ? json['shift'] as Map : const {};
    final vehicle = json['vehicle'] is Map ? json['vehicle'] as Map : const {};
    final tracking = json['tracking'] is Map ? json['tracking'] as Map : const {};
    return LiveStatus(
      configVersion: json['config_version'] is num ? (json['config_version'] as num).toInt() : 0,
      receivedAt: receivedAt,
      shift: shift['state'] == 'working' ? 'working' : 'off_duty',
      shiftStartedAt: _time(shift['started_at']),
      sessionsToday: shift['sessions_today'] is num ? (shift['sessions_today'] as num).toInt() : 0,
      vehicle: const {'available', 'maintenance', 'breakdown', 'none'}.contains(vehicle['state'])
          ? vehicle['state'] as String
          : 'none',
      plate: vehicle['plate_number'] as String?,
      stage: vehicle['stage'] as String?,
      center: vehicle['center'] as String?,
      tracking: const {'active', 'stale', 'off'}.contains(tracking['state']) ? tracking['state'] as String : 'off',
      lastUpdate: _time(tracking['last_update']),
      alerts: [for (final a in json['alerts'] is List ? json['alerts'] as List : const []) ?StatusAlert.fromJson(a)],
    );
  }

  final int configVersion;
  final DateTime receivedAt;
  final String shift;
  final DateTime? shiftStartedAt;
  final int sessionsToday;
  final String vehicle;
  final String? plate;
  final String? stage;
  final String? center;
  final String tracking;
  final DateTime? lastUpdate;
  final List<StatusAlert> alerts;
}

/// One card as drawn: the kind's layout, the icon, colour, texts and the actions the app supports.
class StatusCard {
  StatusCard({
    required this.code,
    required this.kind,
    required this.icon,
    required this.color,
    required this.title,
    required this.subtitle,
    required this.actions,
    this.alert,
  });

  final String code;
  final String kind;
  final String icon;
  final int color;
  final String title;
  final String subtitle;
  final List<String> actions;
  final StatusAlert? alert;

  String get key => alert?.id ?? code;
}

/// What the status area shows: the shift card (always, with the real tracking state), the car's card when it is not
/// simply available, and the most important alert on top (the others counted).
class StatusView {
  StatusView({
    required this.shift,
    required this.tracking,
    required this.vehicle,
    required this.top,
    required this.more,
    required this.offline,
    required this.lastUpdate,
  });

  final StatusCard shift;

  /// active / stale / off as the server saw it; "unknown" offline: a state the phone cannot vouch for is never live.
  final String tracking;
  final StatusCard? vehicle;
  final StatusCard? top;
  final int more;
  final bool offline;
  final DateTime? lastUpdate; // when the shown state was received
}

const _grey = 0xFF6B7280;

String _duration(Duration d) {
  final m = d.inMinutes < 0 ? 0 : d.inMinutes;
  return '${m ~/ 60}:${(m % 60).toString().padLeft(2, '0')}';
}

String _hm(DateTime t) {
  final l = t.toLocal();
  return '${l.hour.toString().padLeft(2, '0')}:${l.minute.toString().padLeft(2, '0')}';
}

StatusCard renderCard(StatusTemplate t, Map<String, String?> values, String lang, {StatusAlert? alert}) {
  final title = StatusEngine.fill(t.text(t.title, lang), values);
  final sub = StatusEngine.fill(t.text(t.subtitle, lang), values);
  return StatusCard(
    code: t.code,
    kind: StatusEngine.kindOf(t.kind),
    icon: StatusEngine.iconOf(t.icon),
    color: StatusEngine.colorOf(t.color, _grey),
    title: title,
    subtitle: sub,
    actions: StatusEngine.actionsOf(t.actions),
    alert: alert,
  );
}

/// The state is "live" only while the last answer is recent: older (offline, or the server unreachable), the
/// tracking state shown is unknown, never the last "active".
const freshFor = Duration(minutes: 3);

StatusView compose(
  LiveStatus s,
  StatusConfig? config, {
  required DateTime now,
  required String lang,
  bool online = true,
}) {
  final c = config ?? StatusConfig(0, const {});
  final offline = !online || now.difference(s.receivedAt) > freshFor;
  final values = <String, String?>{
    'shift_duration': s.shiftStartedAt == null ? null : _duration(now.difference(s.shiftStartedAt!)),
    'last_update': s.lastUpdate == null ? null : _hm(s.lastUpdate!),
    'center': s.center,
    'stage': s.stage,
  };
  final shift = renderCard(c.template(s.shift == 'working' ? 'shift_working' : 'shift_off'), values, lang);
  final vehicle = switch (s.vehicle) {
    'maintenance' => renderCard(c.template('vehicle_maintenance'), values, lang),
    'breakdown' => renderCard(c.template('vehicle_breakdown'), values, lang),
    _ => null,
  };
  final alerts = [
    for (final a in s.alerts)
      if (!a.expired(now)) a,
  ]..sort((a, b) => b.priority.compareTo(a.priority));
  StatusCard? top;
  if (alerts.isNotEmpty) {
    final a = alerts.first;
    final t = c.templates[a.code] ?? StatusConfig.builtIn[a.code];
    if (t != null) {
      top = renderCard(t, {...values, ...a.values}, lang, alert: a);
    } else {
      // a state this app does not know: the server's text on the generic card
      top = StatusCard(
        code: a.code,
        kind: 'generic',
        icon: StatusEngine.defaultIcon,
        color: _grey,
        title: a.title ?? '',
        subtitle: a.subtitle ?? '',
        actions: const [],
        alert: a,
      );
    }
  }
  return StatusView(
    shift: shift,
    tracking: offline ? 'unknown' : s.tracking,
    vehicle: vehicle,
    top: top,
    more: alerts.length > 1 ? alerts.length - 1 : 0,
    offline: offline,
    lastUpdate: s.receivedAt,
  );
}

/// The last answer and the last valid config, kept in the phone's database (shared with the tracking service).
class LiveStatusStore {
  LiveStatusStore(this.get, this.put);

  final Future<String?> Function(String key) get;
  final Future<void> Function(String key, String? value) put;

  static const configKey = 'status_config';
  static const lastKey = 'live_status';

  Future<StatusConfig?> config() async {
    try {
      return StatusConfig.fromJson(jsonDecode(await get(configKey) ?? 'null'));
    } on FormatException {
      return null;
    }
  }

  Future<LiveStatus?> last() async {
    try {
      final raw = jsonDecode(await get(lastKey) ?? 'null');
      if (raw is! Map) return null;
      return LiveStatus.fromJson(raw['body'], DateTime.parse(raw['received_at'] as String));
    } on FormatException {
      return null;
    }
  }

  /// Keeps an answer; its config replaces the cached one only when this app can read it.
  Future<LiveStatus?> save(Object? body, DateTime receivedAt) async {
    final s = LiveStatus.fromJson(body, receivedAt);
    if (s == null) return null;
    final config = (body as Map)['config'];
    if (StatusConfig.fromJson(config) != null) await put(configKey, jsonEncode(config));
    await put(lastKey, jsonEncode({'body': body, 'received_at': receivedAt.toUtc().toIso8601String()}));
    return s;
  }

  /// The version to send: the cached one, or none (the server then sends its config).
  Future<int?> version() async => (await config())?.version;
}
