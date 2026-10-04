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
  });

  factory Onboarding.fromJson(Map<String, dynamic> j) => Onboarding(
    required: j['required'] as bool,
    status: j['status'] as String,
    data: Map<String, dynamic>.from(j['data'] as Map? ?? {}),
    reviewNote: j['review_note'] as String?,
    requiredDocuments: List<String>.from(j['required_documents'] as List),
    vehiclePhotos: List<String>.from(j['vehicle_photos'] as List),
    documentTypes: [for (final t in j['document_types'] as List) DocType.fromJson(t as Map<String, dynamic>)],
  );

  final bool required;
  final String status; // none, draft, submitted, approved, rejected
  final Map<String, dynamic> data;
  final String? reviewNote;
  final List<String> requiredDocuments;
  final List<String> vehiclePhotos;
  final List<DocType> documentTypes;

  /// The server says "required" only while the driver may still edit (draft, or sent back with a reason).
  bool get mustFill => required;
  bool get waiting => status == 'submitted';
}
