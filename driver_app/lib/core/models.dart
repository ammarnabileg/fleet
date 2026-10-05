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
  Today({this.custody, required this.startDayDone});

  factory Today.fromJson(Map<String, dynamic> j) => Today(
    custody: j['custody'] == null ? null : Custody.fromJson(j['custody'] as Map<String, dynamic>),
    startDayDone: j['start_day_done'] as bool? ?? false,
  );

  final Custody? custody;
  final bool startDayDone;
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
  });

  factory Cash.fromJson(Map<String, dynamic> j) => Cash(
    posted: j['posted'] as String,
    pending: j['pending'] as String,
    total: j['total'] as String,
    alertLimit: j['alert_limit'] as String,
    receipts: [for (final r in j['receipts'] as List) Receipt.fromJson(r as Map<String, dynamic>)],
  );

  final String posted;
  final String pending;
  final String total;
  final String alertLimit;
  final List<Receipt> receipts;

  bool get overLimit => (double.tryParse(total) ?? 0) > (double.tryParse(alertLimit) ?? double.infinity);
}

class Report {
  Report({
    required this.id,
    required this.businessDate,
    this.orders,
    required this.cash,
    this.approvedCash,
    required this.status,
    this.reviewNote,
  });

  factory Report.fromJson(Map<String, dynamic> j) => Report(
    id: j['id'] as String,
    businessDate: j['business_date'] as String,
    orders: (j['orders_count'] as num?)?.toInt(),
    cash: j['cash_amount'] as String,
    approvedCash: j['approved_cash'] as String?,
    status: j['status'] as String,
    reviewNote: j['review_note'] as String?,
  );

  final String id;
  final String businessDate;
  final int? orders;
  final String cash;
  final String? approvedCash;
  final String status;
  final String? reviewNote;
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
  );

  final bool required;
  final String status; // none, draft, submitted, approved, rejected
  final Map<String, dynamic> data;
  final String? reviewNote;
  final List<String> requiredDocuments;
  final List<String> vehiclePhotos;
  final List<DocType> documentTypes;
  final bool requireBank; // the IBAN and the bank name (salaries are paid by transfer)

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
  );

  final String month;
  final String status; // approved | paid
  final List<({String header, String code, String? value})> rows;
  final String gross;
  final String deductions;
  final String net;
}
