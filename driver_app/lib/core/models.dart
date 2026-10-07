/// The shapes the driver API returns. Amounts stay strings with three decimals, exactly as the server sends them.
class Custody {
  Custody({required this.id, required this.plate, required this.startedAt, this.lastKm});

  factory Custody.fromJson(Map<String, dynamic> j) => Custody(
    id: j['id'] as String,
    plate: j['plate_number'] as String,
    startedAt: DateTime.parse(j['started_at'] as String),
    lastKm: (j['last_odometer_km'] as num?)?.toInt(),
  );

  final String id;
  final String plate;
  final DateTime startedAt;
  final int? lastKm;
}

class Today {
  Today({this.custody, required this.startDayDone, this.endDayDone = false});

  factory Today.fromJson(Map<String, dynamic> j) => Today(
    custody: j['custody'] == null ? null : Custody.fromJson(j['custody'] as Map<String, dynamic>),
    startDayDone: j['start_day_done'] as bool? ?? false,
    endDayDone: j['end_day_done'] as bool? ?? false,
  );

  final Custody? custody;
  final bool startDayDone;
  final bool endDayDone; // closed by the end-of-day reading, or the vehicle returned
}

class Receipt {
  Receipt({required this.id, required this.number, required this.amount, required this.createdAt, this.confirmedAt});

  factory Receipt.fromJson(Map<String, dynamic> j) => Receipt(
    id: j['id'] as String,
    number: (j['receipt_no'] as num).toInt(),
    amount: j['amount'] as String,
    createdAt: DateTime.parse(j['created_at'] as String),
    confirmedAt: j['driver_confirmed_at'] == null ? null : DateTime.parse(j['driver_confirmed_at'] as String),
  );

  final String id;
  final int number;
  final String amount;
  final DateTime createdAt;
  final DateTime? confirmedAt;
}

class Cash {
  Cash({
    required this.posted,
    required this.pending,
    required this.total,
    required this.alertLimit,
    required this.receipts,
    this.nearLimit = false,
    this.lines = const [],
  });

  factory Cash.fromJson(Map<String, dynamic> j) => Cash(
    posted: j['posted'] as String,
    pending: j['pending'] as String,
    total: j['total'] as String,
    alertLimit: j['alert_limit'] as String,
    receipts: [for (final r in j['receipts'] as List) Receipt.fromJson(r as Map<String, dynamic>)],
    nearLimit: j['near_limit'] as bool? ?? false,
    lines: [for (final x in (j['lines'] as List?) ?? const []) CashLine.fromJson(x as Map<String, dynamic>)],
  );

  final String posted;
  final String pending;
  final String total;
  final String alertLimit;
  final List<Receipt> receipts;
  final bool nearLimit; // close to the alert limit: warned before the office is
  final List<CashLine> lines; // his movements, newest first

  bool get overLimit => (double.tryParse(total) ?? 0) > (double.tryParse(alertLimit) ?? double.infinity);
}

class Report {
  Report({
    required this.id,
    required this.businessDate,
    this.orders,
    required this.cash,
    this.approvedCash,
    this.validDay,
    required this.status,
    this.reviewNote,
    this.notes,
    this.changePending = false,
  });

  factory Report.fromJson(Map<String, dynamic> j) => Report(
    id: j['id'] as String,
    businessDate: j['business_date'] as String,
    orders: (j['orders_count'] as num?)?.toInt(),
    cash: j['cash_amount'] as String,
    approvedCash: j['approved_cash'] as String?,
    validDay: j['valid_day'] as bool?,
    status: j['status'] as String,
    reviewNote: j['review_note'] as String?,
    notes: j['notes'] as String?,
    changePending: j['change_pending'] as bool? ?? false,
  );

  final String id;
  final String businessDate;
  final int? orders;
  final String cash;
  final String? approvedCash;
  final bool? validDay;
  final String status; // submitted | returned | approved | rejected
  final String? reviewNote;
  final String? notes;
  final bool changePending; // a change asked for after approval waits for the office

  bool get editable => status == 'submitted' || status == 'returned';
}

class DocType {
  DocType({required this.code, required this.name, required this.requiresExpiry});

  factory DocType.fromJson(Map<String, dynamic> j) => DocType(
    code: j['code'] as String,
    name: Map<String, String>.from(j['name'] as Map),
    requiresExpiry: j['requires_expiry'] as bool? ?? true,
  );

  final String code;
  final Map<String, String> name;
  final bool requiresExpiry;

  String label(String lang) => name[lang] ?? name['en'] ?? name.values.first;
}

/// The self-registration as the driver sees it (GET /driver/onboarding).
class Onboarding {
  Onboarding({
    required this.required,
    required this.status,
    required this.data,
    this.reviewNote,
    required this.requiredDocuments,
    required this.vehiclePhotos,
    required this.documentTypes,
    this.requireBank = false,
    this.schemes = const [],
    this.schemeRequired = false,
  });

  factory Onboarding.fromJson(Map<String, dynamic> j) => Onboarding(
    required: j['required'] as bool,
    status: j['status'] as String,
    data: Map<String, dynamic>.from(j['data'] as Map? ?? {}),
    reviewNote: j['review_note'] as String?,
    requiredDocuments: List<String>.from(j['required_documents'] as List),
    vehiclePhotos: List<String>.from(j['vehicle_photos'] as List),
    documentTypes: [for (final t in j['document_types'] as List) DocType.fromJson(t as Map<String, dynamic>)],
    requireBank: j['require_bank'] as bool? ?? false,
    schemes: [for (final s in j['schemes'] as List? ?? const []) PayScheme.fromJson(s as Map<String, dynamic>)],
    schemeRequired: j['scheme_required'] as bool? ?? false,
  );

  final bool required;
  final String status; // none, draft, submitted, approved, rejected
  final Map<String, dynamic> data;
  final String? reviewNote;
  final List<String> requiredDocuments;
  final List<String> vehiclePhotos;
  final List<DocType> documentTypes;
  final bool requireBank; // the IBAN and the bank name (salaries are paid by transfer)
  final List<PayScheme> schemes; // his platform's pay schemes, with their terms
  final bool schemeRequired; // choose one to submit

  /// The server says "required" only while the driver may still edit (draft, or sent back with a reason).
  bool get mustFill => required;
  bool get waiting => status == 'submitted';
}

/// A maintenance request as the driver follows it (the office and the center do the rest).
class MaintenanceRequest {
  MaintenanceRequest({
    required this.id,
    required this.number,
    required this.plate,
    required this.kind,
    required this.description,
    required this.status,
    required this.createdAt,
    this.centerName,
    this.centerPhone,
    this.centerAddress,
    this.readyAt,
    this.rejectedReason,
  });

  factory MaintenanceRequest.fromJson(Map<String, dynamic> j) {
    final center = j['center'] as Map<String, dynamic>?;
    return MaintenanceRequest(
      id: j['id'] as String,
      number: (j['number'] as num).toInt(),
      plate: j['vehicle_plate'] as String,
      kind: j['kind'] as String,
      description: j['description'] as String,
      status: j['status'] as String,
      createdAt: DateTime.parse(j['created_at'] as String),
      centerName: center?['name'] as String?,
      centerPhone: center?['phone'] as String?,
      centerAddress: center?['address'] as String?,
      readyAt: j['ready_at'] == null ? null : DateTime.parse(j['ready_at'] as String),
      rejectedReason: j['decision_note'] as String?,
    );
  }

  final String id;
  final int number;
  final String plate;
  final String kind;
  final String description;
  final String status;
  final DateTime createdAt;
  final String? centerName;
  final String? centerPhone;
  final String? centerAddress;
  final DateTime? readyAt;
  final String? rejectedReason;

  bool get isReady => status == 'ready';
}

/// A deduction as the driver sees it: the total and its monthly installments (amounts as the server sends them).
class Deduction {
  Deduction({required this.total, required this.installments, required this.schedule});

  factory Deduction.fromJson(Map<String, dynamic> j) => Deduction(
    total: j['total'] as String,
    installments: (j['installments'] as num).toInt(),
    schedule: [
      for (final s in j['schedule'] as List)
        (month: DateTime.parse((s as Map<String, dynamic>)['month'] as String), amount: s['amount'] as String),
    ],
  );

  final String total;
  final int installments;
  final List<({DateTime month, String amount})> schedule;
}

/// An accident the driver reported (or the office recorded for the vehicle the driver held then), with its outcome.
class Accident {
  Accident({
    required this.id,
    required this.number,
    required this.plate,
    required this.occurredAt,
    required this.description,
    required this.stage,
    required this.hasPoliceReport,
    this.liability,
    this.liabilityPercent,
    this.deduction,
  });

  factory Accident.fromJson(Map<String, dynamic> j) => Accident(
    id: j['id'] as String,
    number: (j['number'] as num).toInt(),
    plate: j['vehicle_plate'] as String,
    occurredAt: DateTime.parse(j['occurred_at'] as String),
    description: j['description'] as String,
    stage: j['stage'] as String,
    hasPoliceReport: j['has_police_report'] as bool,
    liability: j['liability'] as String?,
    liabilityPercent: j['liability_percent'] as String?,
    deduction: j['deduction'] == null ? null : Deduction.fromJson(j['deduction'] as Map<String, dynamic>),
  );

  final String id;
  final int number;
  final String plate;
  final DateTime occurredAt;
  final String description;
  final String stage;
  final bool hasPoliceReport;
  final String? liability;
  final String? liabilityPercent;
  final Deduction? deduction;

  bool get isOpen => stage != 'closed' && stage != 'cancelled';

  /// The driver can still send the police report (once the liability is decided it is too late from the app).
  bool get awaitsPoliceReport => isOpen && !hasPoliceReport && liability == null;
}

/// A traffic fine on the vehicle the driver held at that time, and how it was settled.
class Fine {
  Fine({
    required this.id,
    required this.number,
    required this.plate,
    required this.occurredAt,
    required this.violation,
    required this.amount,
    required this.status,
    this.location,
    this.deduction,
  });

  factory Fine.fromJson(Map<String, dynamic> j) => Fine(
    id: j['id'] as String,
    number: (j['number'] as num).toInt(),
    plate: j['vehicle_plate'] as String,
    occurredAt: DateTime.parse(j['occurred_at'] as String),
    violation: j['violation'] as String,
    amount: j['amount'] as String,
    status: j['status'] as String,
    location: j['location_text'] as String?,
    deduction: j['deduction'] == null ? null : Deduction.fromJson(j['deduction'] as Map<String, dynamic>),
  );

  final String id;
  final int number;
  final String plate;
  final DateTime occurredAt;
  final String violation;
  final String amount;
  final String status; // open | charged | company
  final String? location;
  final Deduction? deduction;
}

/// One month the driver sent from the platform's app (screenshots and the figures read on them), and its review.
class PlatformStatement {
  PlatformStatement({
    required this.id,
    required this.month,
    required this.status,
    required this.declared,
    this.validDays,
    this.orders,
    this.hours,
    this.reviewNote,
  });

  factory PlatformStatement.fromJson(Map<String, dynamic> j) => PlatformStatement(
    id: j['id'] as String,
    month: j['month'] as String,
    status: j['status'] as String,
    declared: Map<String, dynamic>.from(j['declared'] as Map? ?? {}),
    validDays: (j['valid_days'] as num?)?.toInt(),
    orders: (j['orders'] as num?)?.toInt(),
    hours: j['hours'] as String?,
    reviewNote: j['review_note'] as String?,
  );

  final String id;
  final String month; // yyyy-mm-01
  final String status; // submitted | approved | rejected
  final Map<String, dynamic> declared; // what the driver sent
  final int? validDays; // what was approved (the reviewer may have corrected it)
  final int? orders;
  final String? hours;
  final String? reviewNote;
}

/// The driver's platform, what it asks for each month, the months open now and what he sent.
class PlatformStatus {
  PlatformStatus({required this.platform, required this.driverFields, required this.months, required this.statements});

  factory PlatformStatus.fromJson(Map<String, dynamic> j) => PlatformStatus(
    platform: j['platform'] == null ? null : Map<String, dynamic>.from(j['platform'] as Map),
    driverFields: List<String>.from(j['driver_fields'] as List),
    months: List<String>.from(j['months'] as List),
    statements: [for (final s in j['statements'] as List) PlatformStatement.fromJson(s as Map<String, dynamic>)],
  );

  final Map<String, dynamic>? platform; // {id, code, name: {ar, en}}
  final List<String> driverFields; // valid_days | orders | hours
  final List<String> months; // yyyy-mm-01
  final List<PlatformStatement> statements;

  String platformName(String lang) {
    final n = Map<String, dynamic>.from(platform?['name'] as Map? ?? {});
    return (n[lang] ?? n['ar'] ?? n.values.firstOrNull ?? '') as String;
  }
}

/// An approved month's salary, in the rows of the driver's platform sheet.
class Payslip {
  Payslip({
    required this.month,
    required this.status,
    required this.rows,
    required this.gross,
    required this.deductions,
    required this.net,
    this.schemeName,
    this.breakdown = const [],
  });

  factory Payslip.fromJson(Map<String, dynamic> j) => Payslip(
    month: j['month'] as String,
    status: j['status'] as String,
    rows: [
      for (final r in j['rows'] as List)
        (header: (r as Map)['header'] as String, code: r['code'] as String, value: r['value']?.toString()),
    ],
    gross: j['gross'] as String,
    deductions: j['deductions'] as String,
    net: j['net'] as String,
    schemeName: (j['scheme'] as Map?)?['name'] == null
        ? null
        : Map<String, String>.from((j['scheme'] as Map)['name'] as Map),
    breakdown: [
      for (final b in j['breakdown'] as List? ?? const [])
        PayItem(
          code: (b as Map)['code'] as String,
          amount: b['amount'] as String,
          why: Map<String, dynamic>.from(b['why'] as Map? ?? {}),
        ),
    ],
  );

  final String month;
  final String status; // approved | paid
  final List<({String header, String code, String? value})> rows;
  final String gross;
  final String deductions;
  final String net;
  final Map<String, String>? schemeName; // his pay scheme that month
  final List<PayItem> breakdown; // how the scheme computed the month

  String? scheme(String lang) => schemeName == null ? null : schemeName![lang] ?? schemeName!['ar'];
}

/// One item of a scheme's month: what it is (a salary-sheet column), the amount (penalties negative), and its reason.
class PayItem {
  const PayItem({required this.code, required this.amount, required this.why});

  final String code; // orders_pay | tier_bonus | missing_target | marks_deduction | uncovered_penalty
  final String amount;
  final Map<String, dynamic> why;
}

/// One row of a scheme's table: a batch level's price, a tier's bonus, a marks deduction, or the marks from which every
/// order is paid at the reduced price (no amount).
class SchemeStep {
  SchemeStep({required this.kind, required this.threshold, this.amount});

  factory SchemeStep.fromJson(Map<String, dynamic> j) =>
      SchemeStep(kind: j['kind'] as String, threshold: num.parse('${j['threshold']}'), amount: j['amount'] as String?);

  final String kind; // batch_rate | tier_bonus | marks_deduction | marks_reduce
  final num threshold;
  final String? amount;
}

/// A pay scheme's terms as the driver reads them before choosing or asking for it.
class PayScheme {
  PayScheme({
    required this.id,
    required this.code,
    required this.name,
    this.description,
    required this.calculator,
    this.perOrder,
    required this.targetOrders,
    required this.requiredValidDays,
    this.missingOrderRate,
    this.reducedRate,
    this.bonusWhenReduced = false,
    this.marksWhenReduced = false,
    required this.companyCovers,
    required this.steps,
  });

  factory PayScheme.fromJson(Map<String, dynamic> j) => PayScheme(
    id: j['id'] as String,
    code: j['code'] as String,
    name: Map<String, String>.from(j['name'] as Map),
    description: j['description'] == null ? null : Map<String, String>.from(j['description'] as Map),
    calculator: j['calculator'] as String,
    perOrder: j['per_order'] as String?,
    targetOrders: (j['target_orders'] as num).toInt(),
    requiredValidDays: (j['required_valid_days'] as num).toInt(),
    missingOrderRate: j['missing_order_rate'] as String?,
    reducedRate: j['reduced_rate'] as String?,
    bonusWhenReduced: j['bonus_when_reduced'] as bool? ?? false,
    marksWhenReduced: j['marks_when_reduced'] as bool? ?? false,
    companyCovers: List<String>.from(j['company_covers'] as List? ?? const []),
    steps: [for (final s in j['steps'] as List? ?? const []) SchemeStep.fromJson(s as Map<String, dynamic>)],
  );

  final String id;
  final String code;
  final Map<String, String> name;
  final Map<String, String>? description;
  final String calculator; // per_order | batch | tiered_target | platform_rates
  final String? perOrder;
  final int targetOrders;
  final int requiredValidDays;
  final String? missingOrderRate;
  final String? reducedRate;
  final bool bonusWhenReduced;
  final bool marksWhenReduced;
  final List<String> companyCovers; // maintenance | housing | gas | sim
  final List<SchemeStep> steps;

  String label(String lang) => name[lang] ?? name['ar'] ?? name.values.first;
  String? about(String lang) => description == null ? null : description![lang] ?? description!['ar'];
  List<SchemeStep> stepsOf(String kind) => [
    for (final s in steps)
      if (s.kind == kind) s,
  ]..sort((a, b) => a.threshold.compareTo(b.threshold));
}

/// The driver's request to move to another scheme, decided at the office.
class SchemeRequest {
  SchemeRequest({
    required this.id,
    required this.requested,
    required this.effectiveMonth,
    required this.status,
    this.driverNote,
    this.adminNote,
  });

  factory SchemeRequest.fromJson(Map<String, dynamic> j) {
    final r = Map<String, dynamic>.from(j['requested'] as Map? ?? {});
    return SchemeRequest(
      id: j['id'] as String,
      requested: Map<String, String>.from(r['name'] as Map? ?? {}),
      effectiveMonth: DateTime.parse(j['effective_month'] as String),
      status: j['status'] as String,
      driverNote: j['driver_note'] as String?,
      adminNote: j['admin_note'] as String?,
    );
  }

  final String id;
  final Map<String, String> requested; // the scheme's name
  final DateTime effectiveMonth;
  final String status; // pending | approved | rejected
  final String? driverNote;
  final String? adminNote;

  bool get pending => status == 'pending';
  String requestedLabel(String lang) => requested[lang] ?? requested['ar'] ?? requested.values.firstOrNull ?? '';
}

/// GET /driver/schemes: his scheme this month (and next month when it changes), what his platform offers, and his
/// latest request.
class DriverSchemes {
  DriverSchemes({this.current, this.nextMonth, required this.offered, this.request});

  factory DriverSchemes.fromJson(Map<String, dynamic> j) => DriverSchemes(
    current: j['current'] == null ? null : PayScheme.fromJson(j['current'] as Map<String, dynamic>),
    nextMonth: j['next_month'] == null ? null : PayScheme.fromJson(j['next_month'] as Map<String, dynamic>),
    offered: [for (final s in j['schemes'] as List) PayScheme.fromJson(s as Map<String, dynamic>)],
    request: j['request'] == null ? null : SchemeRequest.fromJson(j['request'] as Map<String, dynamic>),
  );

  final PayScheme? current;
  final PayScheme? nextMonth;
  final List<PayScheme> offered;
  final SchemeRequest? request;
}

/// Something the office or the system told the driver (GET /driver/notifications): a receipt, a decision on his
/// report or request, a deduction, a payslip, a document about to expire. The text comes in the app's language.
class DriverNotice {
  DriverNotice({
    required this.id,
    required this.kind,
    required this.message,
    required this.createdAt,
    required this.read,
    this.entityType,
    this.entityId,
  });

  factory DriverNotice.fromJson(Map<String, dynamic> j) => DriverNotice(
    id: j['id'] as String,
    kind: j['kind'] as String,
    message: j['message'] as String,
    createdAt: DateTime.parse(j['created_at'] as String),
    read: j['read'] as bool,
    entityType: j['entity_type'] as String?,
    entityId: j['entity_id'] as String?,
  );

  final String id;
  final String kind;
  final String message;
  final DateTime createdAt;
  final bool read;
  final String? entityType;
  final String? entityId;
}

class Notices {
  Notices({required this.unread, required this.items});

  factory Notices.fromJson(Map<String, dynamic> j) => Notices(
    unread: (j['unread'] as num).toInt(),
    items: [for (final n in j['items'] as List) DriverNotice.fromJson(n as Map<String, dynamic>)],
  );

  final int unread;
  final List<DriverNotice> items;
}

/// One movement of the driver's cash account (FR-APP-03): a report's collection, a receipt, a correction.
class CashLine {
  CashLine({required this.kind, required this.status, required this.amount, required this.date, this.reason});

  factory CashLine.fromJson(Map<String, dynamic> j) => CashLine(
    kind: j['kind'] as String,
    status: j['status'] as String,
    amount: j['amount'] as String,
    date: j['business_date'] as String,
    reason: j['reason'] as String?,
  );

  final String kind; // collection | receipt | adjustment | reversal | settlement | opening
  final String status; // pending | posted | rejected
  final String amount; // + the driver owes more, - less
  final String date;
  final String? reason;
}

/// The driver's own record (FR-APP-01).
class Profile {
  Profile(this.raw);

  final Map<String, dynamic> raw;

  Map<String, dynamic> get name => Map<String, dynamic>.from(raw['name'] as Map);
  String get employeeNumber => raw['employee_number'] as String;
  String? text(String key) => raw[key] as String?;
  Map<String, dynamic>? named(String key) => raw[key] == null ? null : Map<String, dynamic>.from(raw[key] as Map);
}

/// "My car" (FR-APP-02) and the change of vehicle he asked for (FR-ASG-04).
class MyVehicle {
  MyVehicle({this.vehicle, this.request});

  factory MyVehicle.fromJson(Map<String, dynamic> j) => MyVehicle(
    vehicle: j['vehicle'] == null ? null : Map<String, dynamic>.from(j['vehicle'] as Map),
    request: j['change_request'] == null ? null : Map<String, dynamic>.from(j['change_request'] as Map),
  );

  final Map<String, dynamic>? vehicle;
  final Map<String, dynamic>? request;

  bool get requestPending => request?['status'] == 'pending';
}

/// One of his documents and the renewal he sent for it (FR-APP-05).
class DriverDocument {
  DriverDocument(this.raw);

  final Map<String, dynamic> raw;

  String get typeCode => raw['type_code'] as String;
  Map<String, dynamic> get typeName => Map<String, dynamic>.from(raw['type_name'] as Map);
  String? get number => raw['number'] as String?;
  String? get expiry => raw['expiry_date'] as String?;
  int? get daysLeft => (raw['days_left'] as num?)?.toInt();
  String get state => raw['state'] as String; // valid | expiring | expired | missing
  bool get renewable => raw['renewable'] == true;
  Map<String, dynamic>? get renewal => raw['renewal'] == null ? null : Map<String, dynamic>.from(raw['renewal'] as Map);
  bool get renewalPending => renewal?['status'] == 'pending';
}
