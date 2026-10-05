// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Arabic (`ar`).
class AppLocalizationsAr extends AppLocalizations {
  AppLocalizationsAr([String locale = 'ar']) : super(locale);

  @override
  String get appTitle => 'تطبيق السائق';

  @override
  String get retry => 'إعادة المحاولة';

  @override
  String get cancel => 'إلغاء';

  @override
  String get continueBtn => 'متابعة';

  @override
  String get save => 'حفظ';

  @override
  String get send => 'إرسال';

  @override
  String get back => 'رجوع';

  @override
  String get done => 'تم';

  @override
  String get networkError => 'لا يوجد اتصال بالإنترنت. حاول مرة أخرى.';

  @override
  String get genericError => 'حدث خطأ غير متوقع. حاول مرة أخرى.';

  @override
  String get kwd => 'د.ك';

  @override
  String get km => 'كم';

  @override
  String get signInTitle => 'تسجيل الدخول';

  @override
  String get signInHint => 'أدخل رقم جوالك المسجل لدى الشركة. سيصلك رمز الدخول على واتساب.';

  @override
  String get phoneLabel => 'رقم الجوال';

  @override
  String get phoneInvalid => '8 أرقام كويتية، أو رقم دولي يبدأ بـ +';

  @override
  String get sendCode => 'إرسال الرمز';

  @override
  String get activationTip => 'إذا وصلك رابط التفعيل على واتساب، افتحه من هذا الهاتف ولن تحتاج رمزاً.';

  @override
  String get otpTitle => 'رمز الدخول';

  @override
  String otpHint(String phone) {
    return 'أدخل الرمز المكون من 6 أرقام الذي وصلك على واتساب على الرقم $phone.';
  }

  @override
  String get otpLabel => 'الرمز';

  @override
  String get verify => 'دخول';

  @override
  String get otpResend => 'لم يصل الرمز؟ إعادة الإرسال';

  @override
  String get activating => 'جاري تفعيل التطبيق على هذا الهاتف…';

  @override
  String get activationFailed => 'تعذر التفعيل';

  @override
  String get permTitle => 'صلاحيات التطبيق';

  @override
  String get permIntro =>
      'ليعمل التتبع أثناء العهدة حتى والتطبيق مغلق، يحتاج التطبيق هذه الصلاحيات. لا يُسجَّل موقعك إلا والسيارة في عهدتك.';

  @override
  String get permLocation => 'الموقع: «السماح طوال الوقت»';

  @override
  String get permLocationWhy => 'ليصل موقع السيارة للمشرف أثناء العهدة.';

  @override
  String get permNotifications => 'الإشعارات';

  @override
  String get permNotificationsWhy => 'يظهر إشعار ثابت أثناء التتبع (شرط من أندرويد).';

  @override
  String get permBattery => 'تجاهل تحسين البطارية';

  @override
  String get permBatteryWhy => 'حتى لا يوقف الهاتف التتبع في الخلفية.';

  @override
  String get permGrant => 'سماح';

  @override
  String get permGranted => 'مسموح';

  @override
  String get permSettings => 'فتح الإعدادات';

  @override
  String get permLocationRequired => 'صلاحية الموقع مطلوبة للمتابعة.';

  @override
  String get gpsOff => 'الـ GPS مغلق: شغّله من إعدادات الهاتف.';

  @override
  String get obTitle => 'إكمال التسجيل';

  @override
  String get obIntro => 'أدخل بياناتك وصوّر مستنداتك وسيارتك. لا يدخل شيء في السجلات قبل مراجعة الشركة.';

  @override
  String obRejected(String reason) {
    return 'أُعيد طلبك للتصحيح: $reason';
  }

  @override
  String get obStepData => 'البيانات';

  @override
  String get obStepDocs => 'المستندات';

  @override
  String get obStepVehicle => 'السيارة';

  @override
  String get obStepReview => 'المراجعة';

  @override
  String get civilId => 'الرقم المدني';

  @override
  String get civilIdInvalid => 'الرقم المدني 12 رقماً';

  @override
  String get nationality => 'الجنسية';

  @override
  String get docNumber => 'رقم المستند';

  @override
  String get docExpiry => 'تاريخ الانتهاء';

  @override
  String get docFront => 'الوجه';

  @override
  String get docBack => 'الظهر';

  @override
  String get pickPhoto => 'صورة';

  @override
  String get takePhoto => 'التقاط صورة';

  @override
  String get fromGallery => 'من المعرض';

  @override
  String get uploading => 'جاري الرفع…';

  @override
  String get required => 'مطلوب';

  @override
  String get plate => 'رقم اللوحة';

  @override
  String get plateHint => 'كما على اللوحة، مثال 18/23456';

  @override
  String get odometerKm => 'قراءة العداد (كم)';

  @override
  String get odometerPhoto => 'صورة العداد';

  @override
  String get noVehicle => 'لا توجد سيارة معي الآن';

  @override
  String get vehiclePhotos => 'صور حالة السيارة';

  @override
  String get obSubmit => 'إرسال للمراجعة';

  @override
  String obMissing(String items) {
    return 'أكمل: $items';
  }

  @override
  String get obWaitingTitle => 'بياناتك قيد المراجعة';

  @override
  String get obWaitingText => 'سيصلك إشعار على واتساب عند الاعتماد أو إذا احتاج شيء للتصحيح.';

  @override
  String get refresh => 'تحديث';

  @override
  String get position_front => 'الأمام';

  @override
  String get position_back => 'الخلف';

  @override
  String get position_left => 'الجانب الأيسر';

  @override
  String get position_right => 'الجانب الأيمن';

  @override
  String get position_interior => 'الداخل';

  @override
  String get position_other => 'أخرى';

  @override
  String get tabHome => 'الرئيسية';

  @override
  String get tabCash => 'الكاش';

  @override
  String get tabAccount => 'الحساب';

  @override
  String get noCustody => 'لا توجد سيارة في عهدتك الآن';

  @override
  String get noCustodyHint => 'عند تسليمك سيارة تظهر هنا ويبدأ التتبع تلقائياً.';

  @override
  String custodySince(String when) {
    return 'في عهدتك منذ $when';
  }

  @override
  String lastKm(String km) {
    return 'آخر قراءة: $km كم';
  }

  @override
  String get trackingOn => 'التتبع يعمل';

  @override
  String get trackingOff => 'التتبع متوقف';

  @override
  String trackingWaiting(String count) {
    return 'بانتظار الإرسال: $count';
  }

  @override
  String get startDay => 'ابدأ اليوم';

  @override
  String get startDayDone => 'بدأت اليوم';

  @override
  String get endDay => 'إنهاء اليوم';

  @override
  String get dailyReport => 'التقرير اليومي';

  @override
  String get outboxTitle => 'بانتظار الإرسال';

  @override
  String get outboxQueued => 'سيُرسل تلقائياً عند توفر الشبكة';

  @override
  String outboxFailed(String reason) {
    return 'لم يُقبل: $reason';
  }

  @override
  String get outboxDiscard => 'حذف';

  @override
  String get kind_odometer => 'قراءة عداد';

  @override
  String get kind_report => 'تقرير يومي';

  @override
  String get startDayTitle => 'بداية اليوم';

  @override
  String get endDayTitle => 'نهاية اليوم';

  @override
  String get odometerIntro => 'صوّر العداد بوضوح ثم اكتب القراءة كما تظهر في الصورة.';

  @override
  String get retake => 'إعادة التصوير';

  @override
  String kmLower(String km) {
    return 'القراءة أقل من آخر قراءة ($km كم). تأكد منها: سترسل للمراجعة.';
  }

  @override
  String get kmInvalid => 'اكتب القراءة بالأرقام';

  @override
  String get photoRequired => 'الصورة مطلوبة';

  @override
  String get sentTitle => 'تم الإرسال';

  @override
  String get queuedTitle => 'حُفظ على الهاتف';

  @override
  String get sentText => 'وصل للشركة.';

  @override
  String get queuedText => 'لا توجد شبكة الآن. سيُرسل تلقائياً بوقته الأصلي عند عودة الاتصال.';

  @override
  String get reportTitle => 'التقرير اليومي';

  @override
  String get reportDate => 'يوم العمل';

  @override
  String get today => 'اليوم';

  @override
  String get yesterday => 'أمس';

  @override
  String get dayBefore => 'قبل أمس';

  @override
  String get ordersCount => 'عدد الطلبات';

  @override
  String get cashAmount => 'الكاش المحصّل';

  @override
  String get cashInvalid => 'مبلغ بثلاث خانات عشرية كحد أقصى';

  @override
  String get screenshot => 'لقطة شاشة ملخص اليوم من تطبيق الطلبات';

  @override
  String get notes => 'ملاحظات';

  @override
  String get recentReports => 'آخر التقارير';

  @override
  String get status_submitted => 'بانتظار المراجعة';

  @override
  String get status_approved => 'معتمد';

  @override
  String get status_rejected => 'مرفوض';

  @override
  String approvedCash(String amount) {
    return 'المعتمد: $amount';
  }

  @override
  String get cashTitle => 'الكاش';

  @override
  String get cashTotal => 'رصيد الكاش معك';

  @override
  String get cashPosted => 'معتمد';

  @override
  String get cashPending => 'بانتظار المراجعة';

  @override
  String cashOverLimit(String limit) {
    return 'الرصيد فوق الحد ($limit): سلّم الكاش للصراف.';
  }

  @override
  String get receipts => 'الإيصالات';

  @override
  String receiptNo(String no) {
    return 'إيصال رقم $no';
  }

  @override
  String get confirmReceipt => 'أؤكد التسليم';

  @override
  String get receiptConfirmed => 'مؤكد';

  @override
  String confirmReceiptQ(String amount) {
    return 'هل سلّمت $amount د.ك للصراف؟';
  }

  @override
  String get noReceipts => 'لا توجد إيصالات بعد';

  @override
  String get language => 'اللغة';

  @override
  String get trackingDetails => 'حالة التتبع';

  @override
  String lastUpload(String when) {
    return 'آخر إرسال: $when';
  }

  @override
  String get never => 'لم يحدث بعد';

  @override
  String appVersion(String version) {
    return 'الإصدار $version';
  }

  @override
  String get signOut => 'تسجيل الخروج';

  @override
  String get signOutQ => 'سيتوقف التتبع وتحتاج تفعيلاً جديداً للدخول. متابعة؟';

  @override
  String get blockedTitle => 'حسابك موقوف';

  @override
  String get blockedText => 'تواصل مع المشرف.';

  @override
  String get obReady => 'كل شيء جاهز: أرسله للمراجعة.';

  @override
  String get maintenance => 'الصيانة';

  @override
  String get maintenanceTitle => 'طلبات الصيانة';

  @override
  String get kind_maintenance => 'طلب صيانة';

  @override
  String get mntNew => 'طلب صيانة جديد';

  @override
  String get mntIntro => 'صِف المشكلة وصوّرها من الكاميرا. يصل الطلب للمشرف ليعتمده ويحدد مركز الصيانة.';

  @override
  String get mntNoVehicle => 'تطلب الصيانة للسيارة التي في عهدتك. لا توجد سيارة معك الآن.';

  @override
  String get mntKind => 'النوع';

  @override
  String get mntDescription => 'وصف المشكلة';

  @override
  String get mntOdometer => 'قراءة العداد (اختياري)';

  @override
  String get mntPhotos => 'صور (حتى 4)';

  @override
  String get mntAddPhoto => 'صورة';

  @override
  String get mntNone => 'لا توجد طلبات صيانة';

  @override
  String mntRequestNo(String number) {
    return 'طلب #$number';
  }

  @override
  String mntAtCenter(String center) {
    return 'المركز: $center';
  }

  @override
  String mntReadyBanner(String plate, String center) {
    return 'سيارتك $plate جاهزة للاستلام من $center';
  }

  @override
  String mntRejected(String reason) {
    return 'رُفض: $reason';
  }

  @override
  String get mntSent => 'أُرسل طلب الصيانة للمشرف';

  @override
  String get mntKind_periodic => 'صيانة دورية';

  @override
  String get mntKind_mechanical => 'ميكانيكا';

  @override
  String get mntKind_electrical => 'كهرباء';

  @override
  String get mntKind_tyres => 'إطارات';

  @override
  String get mntKind_battery => 'بطارية';

  @override
  String get mntKind_ac => 'تكييف';

  @override
  String get mntKind_bodywork => 'سمكرة وصبغ';

  @override
  String get mntKind_other => 'أخرى';

  @override
  String get mntStatus_requested => 'بانتظار الاعتماد';

  @override
  String get mntStatus_approved => 'معتمد';

  @override
  String get mntStatus_rejected => 'مرفوض';

  @override
  String get mntStatus_referred => 'محال لمركز الصيانة';

  @override
  String get mntStatus_at_center => 'في مركز الصيانة';

  @override
  String get mntStatus_ready => 'جاهزة للاستلام';

  @override
  String get mntStatus_picked_up => 'تم الاستلام';

  @override
  String get mntStatus_closed => 'مغلق';

  @override
  String get mntStatus_cancelled => 'ملغى';

  @override
  String get mntTapToRemove => 'اضغط للحذف';

  @override
  String get accident => 'الإبلاغ عن حادث';

  @override
  String get accidentsTitle => 'الحوادث';

  @override
  String get kind_accident => 'بلاغ حادث';

  @override
  String get kind_police_report => 'محضر الشرطة';

  @override
  String get accNew => 'بلاغ حادث جديد';

  @override
  String get accEmergency => 'إن وُجدت إصابات اتصل بالطوارئ 112 أولاً.';

  @override
  String get accIntro =>
      'صوّر السيارة من عدة زوايا: الأمام والخلف والجانبين ومكان الضرر. يُسجّل الوقت والموقع تلقائياً.';

  @override
  String get accNoVehicle => 'يُبلّغ عن الحادث للسيارة التي في عهدتك. لا توجد سيارة معك الآن؛ كلّم المشرف.';

  @override
  String get accDescription => 'ماذا حدث؟';

  @override
  String get accInjuries => 'توجد إصابات';

  @override
  String get accInjuriesNote => 'تفاصيل الإصابات';

  @override
  String get accOtherParty => 'الطرف الآخر (اللوحة، الاسم، التأمين)';

  @override
  String accPhotos(String min) {
    return 'صور الحادث ($min على الأقل)';
  }

  @override
  String accPhotosNeeded(String min) {
    return 'صوّر $min صور على الأقل من زوايا مختلفة';
  }

  @override
  String get accPoliceReport => 'محضر الشرطة';

  @override
  String get accPoliceReportNo => 'رقم المحضر';

  @override
  String get accPoliceLater => 'لم يصدر المحضر بعد؟ أرسل البلاغ الآن وأرسل صورة المحضر لاحقاً من قائمة حوادثك.';

  @override
  String get accSendPolice => 'إرسال محضر الشرطة';

  @override
  String get accNone => 'لا توجد حوادث';

  @override
  String accNo(String number) {
    return 'حادث #$number';
  }

  @override
  String get accStage_review => 'قيد المراجعة';

  @override
  String get accStage_outcome => 'بانتظار تحديد المسؤولية';

  @override
  String get accStage_recorded => 'المسؤولية محددة';

  @override
  String get accStage_closed => 'مغلق';

  @override
  String get accLiability_none => 'لا مسؤولية عليك';

  @override
  String get accLiability_driver => 'المسؤولية عليك';

  @override
  String accLiability_shared(String percent) {
    return 'مسؤولية مشتركة: نصيبك $percent%';
  }

  @override
  String accDeduction(String total, String count) {
    return 'خصم $total د.ك · عدد الأقساط: $count';
  }

  @override
  String accInstallment(String month, String amount) {
    return '$month: $amount د.ك';
  }

  @override
  String accAwaitingPolice(String number) {
    return 'الحادث #$number بانتظار محضر الشرطة: اضغط لإرسال صورته';
  }

  @override
  String get fines => 'المخالفات المرورية';

  @override
  String get finesTitle => 'المخالفات المرورية';

  @override
  String get finesIntro =>
      'المخالفات على السيارة وهي في عهدتك، حسب وقت المخالفة. الشركة تقرر: على الشركة أو خصم من راتبك بأقساط.';

  @override
  String get finesNone => 'لا توجد مخالفات';

  @override
  String get fineStatus_open => 'قيد المراجعة';

  @override
  String get fineStatus_charged => 'تُخصم من راتبك';

  @override
  String get fineStatus_company => 'على الشركة';

  @override
  String get monthlyStatement => 'كشف المنصة الشهري';

  @override
  String get payslips => 'كشوف الراتب';

  @override
  String get statementTitle => 'كشف المنصة الشهري';

  @override
  String statementIntro(String platform) {
    return 'في بداية كل شهر أرسل لقطات شاشة ملخص الشهر من تطبيق $platform واكتب الأرقام كما تظهر فيها. يراجعها المكتب مع اللقطات قبل احتساب الراتب.';
  }

  @override
  String get statementNoPlatform => 'لم تُحدَّد منصتك بعد. تواصل مع المكتب.';

  @override
  String get statementNoMonth => 'أرسلت كشف كل الأشهر المفتوحة. انتظر مراجعة المكتب.';

  @override
  String get statementMonth => 'الشهر';

  @override
  String get statementShots => 'لقطات الشاشة من تطبيق المنصة (حتى 6)';

  @override
  String get statementShotRequired => 'أضف لقطة شاشة واحدة على الأقل';

  @override
  String get statementHistory => 'ما أرسلته';

  @override
  String statementSentDays(String days) {
    return 'أرسلت: $days يوم صالح';
  }

  @override
  String statementApprovedDays(String days) {
    return 'المعتمد: $days يوم صالح';
  }

  @override
  String get statementStatus_submitted => 'بانتظار المراجعة';

  @override
  String get statementStatus_approved => 'معتمد';

  @override
  String get statementStatus_rejected => 'مرفوض: أرسله من جديد';

  @override
  String get addShot => 'إضافة لقطة';

  @override
  String get validDays => 'عدد الأيام الصالحة';

  @override
  String get ordersTotal => 'إجمالي الطلبات';

  @override
  String get hoursTotal => 'إجمالي الساعات';

  @override
  String get payslipsTitle => 'كشوف الراتب';

  @override
  String get payslipsNone => 'لا يوجد كشف راتب معتمد بعد';

  @override
  String get payslipNet => 'صافي الراتب';

  @override
  String get payslipStatus_approved => 'معتمد';

  @override
  String get payslipStatus_paid => 'مدفوع';

  @override
  String get iban => 'رقم الآيبان (IBAN)';

  @override
  String get ibanHint => 'يُحوَّل عليه راتبك: انسخه من تطبيق البنك';

  @override
  String get bankName => 'اسم البنك';
}
