import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_ar.dart';
import 'app_localizations_en.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale) : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate = _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates = <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[Locale('ar'), Locale('en')];

  /// No description provided for @appTitle.
  ///
  /// In ar, this message translates to:
  /// **'تطبيق السائق'**
  String get appTitle;

  /// No description provided for @retry.
  ///
  /// In ar, this message translates to:
  /// **'إعادة المحاولة'**
  String get retry;

  /// No description provided for @cancel.
  ///
  /// In ar, this message translates to:
  /// **'إلغاء'**
  String get cancel;

  /// No description provided for @continueBtn.
  ///
  /// In ar, this message translates to:
  /// **'متابعة'**
  String get continueBtn;

  /// No description provided for @save.
  ///
  /// In ar, this message translates to:
  /// **'حفظ'**
  String get save;

  /// No description provided for @send.
  ///
  /// In ar, this message translates to:
  /// **'إرسال'**
  String get send;

  /// No description provided for @back.
  ///
  /// In ar, this message translates to:
  /// **'رجوع'**
  String get back;

  /// No description provided for @done.
  ///
  /// In ar, this message translates to:
  /// **'تم'**
  String get done;

  /// No description provided for @networkError.
  ///
  /// In ar, this message translates to:
  /// **'لا يوجد اتصال بالإنترنت. حاول مرة أخرى.'**
  String get networkError;

  /// No description provided for @genericError.
  ///
  /// In ar, this message translates to:
  /// **'حدث خطأ غير متوقع. حاول مرة أخرى.'**
  String get genericError;

  /// No description provided for @kwd.
  ///
  /// In ar, this message translates to:
  /// **'د.ك'**
  String get kwd;

  /// No description provided for @km.
  ///
  /// In ar, this message translates to:
  /// **'كم'**
  String get km;

  /// No description provided for @signInTitle.
  ///
  /// In ar, this message translates to:
  /// **'تسجيل الدخول'**
  String get signInTitle;

  /// No description provided for @signInHint.
  ///
  /// In ar, this message translates to:
  /// **'أدخل رقم جوالك المسجل لدى الشركة. سيصلك رمز الدخول على واتساب.'**
  String get signInHint;

  /// No description provided for @phoneLabel.
  ///
  /// In ar, this message translates to:
  /// **'رقم الجوال'**
  String get phoneLabel;

  /// No description provided for @phoneInvalid.
  ///
  /// In ar, this message translates to:
  /// **'8 أرقام كويتية، أو رقم دولي يبدأ بـ +'**
  String get phoneInvalid;

  /// No description provided for @sendCode.
  ///
  /// In ar, this message translates to:
  /// **'إرسال الرمز'**
  String get sendCode;

  /// No description provided for @activationTip.
  ///
  /// In ar, this message translates to:
  /// **'إذا وصلك رابط التفعيل على واتساب، افتحه من هذا الهاتف ولن تحتاج رمزاً.'**
  String get activationTip;

  /// No description provided for @otpTitle.
  ///
  /// In ar, this message translates to:
  /// **'رمز الدخول'**
  String get otpTitle;

  /// No description provided for @otpHint.
  ///
  /// In ar, this message translates to:
  /// **'أدخل الرمز المكون من 6 أرقام الذي وصلك على واتساب على الرقم {phone}.'**
  String otpHint(String phone);

  /// No description provided for @otpLabel.
  ///
  /// In ar, this message translates to:
  /// **'الرمز'**
  String get otpLabel;

  /// No description provided for @verify.
  ///
  /// In ar, this message translates to:
  /// **'دخول'**
  String get verify;

  /// No description provided for @otpResend.
  ///
  /// In ar, this message translates to:
  /// **'لم يصل الرمز؟ إعادة الإرسال'**
  String get otpResend;

  /// No description provided for @activating.
  ///
  /// In ar, this message translates to:
  /// **'جاري تفعيل التطبيق على هذا الهاتف…'**
  String get activating;

  /// No description provided for @activationFailed.
  ///
  /// In ar, this message translates to:
  /// **'تعذر التفعيل'**
  String get activationFailed;

  /// No description provided for @permTitle.
  ///
  /// In ar, this message translates to:
  /// **'صلاحيات التطبيق'**
  String get permTitle;

  /// No description provided for @permIntro.
  ///
  /// In ar, this message translates to:
  /// **'ليعمل التتبع أثناء العهدة حتى والتطبيق مغلق، يحتاج التطبيق هذه الصلاحيات. لا يُسجَّل موقعك إلا والسيارة في عهدتك.'**
  String get permIntro;

  /// No description provided for @permLocation.
  ///
  /// In ar, this message translates to:
  /// **'الموقع: «السماح طوال الوقت»'**
  String get permLocation;

  /// No description provided for @permLocationWhy.
  ///
  /// In ar, this message translates to:
  /// **'ليصل موقع السيارة للمشرف أثناء العهدة.'**
  String get permLocationWhy;

  /// No description provided for @permNotifications.
  ///
  /// In ar, this message translates to:
  /// **'الإشعارات'**
  String get permNotifications;

  /// No description provided for @permNotificationsWhy.
  ///
  /// In ar, this message translates to:
  /// **'يظهر إشعار ثابت أثناء التتبع (شرط من أندرويد).'**
  String get permNotificationsWhy;

  /// No description provided for @permBattery.
  ///
  /// In ar, this message translates to:
  /// **'تجاهل تحسين البطارية'**
  String get permBattery;

  /// No description provided for @permBatteryWhy.
  ///
  /// In ar, this message translates to:
  /// **'حتى لا يوقف الهاتف التتبع في الخلفية.'**
  String get permBatteryWhy;

  /// No description provided for @permGrant.
  ///
  /// In ar, this message translates to:
  /// **'سماح'**
  String get permGrant;

  /// No description provided for @permGranted.
  ///
  /// In ar, this message translates to:
  /// **'مسموح'**
  String get permGranted;

  /// No description provided for @permSettings.
  ///
  /// In ar, this message translates to:
  /// **'فتح الإعدادات'**
  String get permSettings;

  /// No description provided for @permLocationRequired.
  ///
  /// In ar, this message translates to:
  /// **'صلاحية الموقع مطلوبة للمتابعة.'**
  String get permLocationRequired;

  /// No description provided for @gpsOff.
  ///
  /// In ar, this message translates to:
  /// **'الـ GPS مغلق: شغّله من إعدادات الهاتف.'**
  String get gpsOff;

  /// No description provided for @obTitle.
  ///
  /// In ar, this message translates to:
  /// **'إكمال التسجيل'**
  String get obTitle;

  /// No description provided for @obIntro.
  ///
  /// In ar, this message translates to:
  /// **'أدخل بياناتك وصوّر مستنداتك وسيارتك. لا يدخل شيء في السجلات قبل مراجعة الشركة.'**
  String get obIntro;

  /// No description provided for @obRejected.
  ///
  /// In ar, this message translates to:
  /// **'أُعيد طلبك للتصحيح: {reason}'**
  String obRejected(String reason);

  /// No description provided for @obStepData.
  ///
  /// In ar, this message translates to:
  /// **'البيانات'**
  String get obStepData;

  /// No description provided for @obStepDocs.
  ///
  /// In ar, this message translates to:
  /// **'المستندات'**
  String get obStepDocs;

  /// No description provided for @obStepVehicle.
  ///
  /// In ar, this message translates to:
  /// **'السيارة'**
  String get obStepVehicle;

  /// No description provided for @obStepReview.
  ///
  /// In ar, this message translates to:
  /// **'المراجعة'**
  String get obStepReview;

  /// No description provided for @civilId.
  ///
  /// In ar, this message translates to:
  /// **'الرقم المدني'**
  String get civilId;

  /// No description provided for @civilIdInvalid.
  ///
  /// In ar, this message translates to:
  /// **'الرقم المدني 12 رقماً'**
  String get civilIdInvalid;

  /// No description provided for @nationality.
  ///
  /// In ar, this message translates to:
  /// **'الجنسية'**
  String get nationality;

  /// No description provided for @docNumber.
  ///
  /// In ar, this message translates to:
  /// **'رقم المستند'**
  String get docNumber;

  /// No description provided for @docExpiry.
  ///
  /// In ar, this message translates to:
  /// **'تاريخ الانتهاء'**
  String get docExpiry;

  /// No description provided for @docFront.
  ///
  /// In ar, this message translates to:
  /// **'الوجه'**
  String get docFront;

  /// No description provided for @docBack.
  ///
  /// In ar, this message translates to:
  /// **'الظهر'**
  String get docBack;

  /// No description provided for @pickPhoto.
  ///
  /// In ar, this message translates to:
  /// **'صورة'**
  String get pickPhoto;

  /// No description provided for @takePhoto.
  ///
  /// In ar, this message translates to:
  /// **'التقاط صورة'**
  String get takePhoto;

  /// No description provided for @fromGallery.
  ///
  /// In ar, this message translates to:
  /// **'من المعرض'**
  String get fromGallery;

  /// No description provided for @uploading.
  ///
  /// In ar, this message translates to:
  /// **'جاري الرفع…'**
  String get uploading;

  /// No description provided for @required.
  ///
  /// In ar, this message translates to:
  /// **'مطلوب'**
  String get required;

  /// No description provided for @plate.
  ///
  /// In ar, this message translates to:
  /// **'رقم اللوحة'**
  String get plate;

  /// No description provided for @plateHint.
  ///
  /// In ar, this message translates to:
  /// **'كما على اللوحة، مثال 18/23456'**
  String get plateHint;

  /// No description provided for @odometerKm.
  ///
  /// In ar, this message translates to:
  /// **'قراءة العداد (كم)'**
  String get odometerKm;

  /// No description provided for @odometerPhoto.
  ///
  /// In ar, this message translates to:
  /// **'صورة العداد'**
  String get odometerPhoto;

  /// No description provided for @noVehicle.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد سيارة معي الآن'**
  String get noVehicle;

  /// No description provided for @vehiclePhotos.
  ///
  /// In ar, this message translates to:
  /// **'صور حالة السيارة'**
  String get vehiclePhotos;

  /// No description provided for @obSubmit.
  ///
  /// In ar, this message translates to:
  /// **'إرسال للمراجعة'**
  String get obSubmit;

  /// No description provided for @obMissing.
  ///
  /// In ar, this message translates to:
  /// **'أكمل: {items}'**
  String obMissing(String items);

  /// No description provided for @obWaitingTitle.
  ///
  /// In ar, this message translates to:
  /// **'بياناتك قيد المراجعة'**
  String get obWaitingTitle;

  /// No description provided for @obWaitingText.
  ///
  /// In ar, this message translates to:
  /// **'سيصلك إشعار على واتساب عند الاعتماد أو إذا احتاج شيء للتصحيح.'**
  String get obWaitingText;

  /// No description provided for @refresh.
  ///
  /// In ar, this message translates to:
  /// **'تحديث'**
  String get refresh;

  /// No description provided for @position_front.
  ///
  /// In ar, this message translates to:
  /// **'الأمام'**
  String get position_front;

  /// No description provided for @position_back.
  ///
  /// In ar, this message translates to:
  /// **'الخلف'**
  String get position_back;

  /// No description provided for @position_left.
  ///
  /// In ar, this message translates to:
  /// **'الجانب الأيسر'**
  String get position_left;

  /// No description provided for @position_right.
  ///
  /// In ar, this message translates to:
  /// **'الجانب الأيمن'**
  String get position_right;

  /// No description provided for @position_interior.
  ///
  /// In ar, this message translates to:
  /// **'الداخل'**
  String get position_interior;

  /// No description provided for @position_other.
  ///
  /// In ar, this message translates to:
  /// **'أخرى'**
  String get position_other;

  /// No description provided for @tabHome.
  ///
  /// In ar, this message translates to:
  /// **'الرئيسية'**
  String get tabHome;

  /// No description provided for @tabCash.
  ///
  /// In ar, this message translates to:
  /// **'الكاش'**
  String get tabCash;

  /// No description provided for @tabAccount.
  ///
  /// In ar, this message translates to:
  /// **'الحساب'**
  String get tabAccount;

  /// No description provided for @noCustody.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد سيارة في عهدتك الآن'**
  String get noCustody;

  /// No description provided for @noCustodyHint.
  ///
  /// In ar, this message translates to:
  /// **'عند تسليمك سيارة تظهر هنا ويبدأ التتبع تلقائياً.'**
  String get noCustodyHint;

  /// No description provided for @custodySince.
  ///
  /// In ar, this message translates to:
  /// **'في عهدتك منذ {when}'**
  String custodySince(String when);

  /// No description provided for @lastKm.
  ///
  /// In ar, this message translates to:
  /// **'آخر قراءة: {km} كم'**
  String lastKm(String km);

  /// No description provided for @trackingOn.
  ///
  /// In ar, this message translates to:
  /// **'التتبع يعمل'**
  String get trackingOn;

  /// No description provided for @trackingOff.
  ///
  /// In ar, this message translates to:
  /// **'التتبع متوقف'**
  String get trackingOff;

  /// No description provided for @trackingWaiting.
  ///
  /// In ar, this message translates to:
  /// **'بانتظار الإرسال: {count}'**
  String trackingWaiting(String count);

  /// No description provided for @startDay.
  ///
  /// In ar, this message translates to:
  /// **'ابدأ اليوم'**
  String get startDay;

  /// No description provided for @startDayDone.
  ///
  /// In ar, this message translates to:
  /// **'بدأت اليوم'**
  String get startDayDone;

  /// No description provided for @endDay.
  ///
  /// In ar, this message translates to:
  /// **'إنهاء اليوم'**
  String get endDay;

  /// No description provided for @dailyReport.
  ///
  /// In ar, this message translates to:
  /// **'التقرير اليومي'**
  String get dailyReport;

  /// No description provided for @outboxTitle.
  ///
  /// In ar, this message translates to:
  /// **'بانتظار الإرسال'**
  String get outboxTitle;

  /// No description provided for @outboxQueued.
  ///
  /// In ar, this message translates to:
  /// **'سيُرسل تلقائياً عند توفر الشبكة'**
  String get outboxQueued;

  /// No description provided for @outboxFailed.
  ///
  /// In ar, this message translates to:
  /// **'لم يُقبل: {reason}'**
  String outboxFailed(String reason);

  /// No description provided for @outboxDiscard.
  ///
  /// In ar, this message translates to:
  /// **'حذف'**
  String get outboxDiscard;

  /// No description provided for @kind_odometer.
  ///
  /// In ar, this message translates to:
  /// **'قراءة عداد'**
  String get kind_odometer;

  /// No description provided for @kind_report.
  ///
  /// In ar, this message translates to:
  /// **'تقرير يومي'**
  String get kind_report;

  /// No description provided for @startDayTitle.
  ///
  /// In ar, this message translates to:
  /// **'بداية اليوم'**
  String get startDayTitle;

  /// No description provided for @endDayDone.
  ///
  /// In ar, this message translates to:
  /// **'أنهيت اليوم'**
  String get endDayDone;

  /// No description provided for @endReadingIntro.
  ///
  /// In ar, this message translates to:
  /// **'قبل إرسال تقرير اليوم: صورة عداد نهاية اليوم ورقمه. تُرسل القراءة أولاً ثم التقرير.'**
  String get endReadingIntro;

  /// No description provided for @endDayTitle.
  ///
  /// In ar, this message translates to:
  /// **'نهاية اليوم'**
  String get endDayTitle;

  /// No description provided for @odometerIntro.
  ///
  /// In ar, this message translates to:
  /// **'صوّر العداد بوضوح ثم اكتب القراءة كما تظهر في الصورة.'**
  String get odometerIntro;

  /// No description provided for @retake.
  ///
  /// In ar, this message translates to:
  /// **'إعادة التصوير'**
  String get retake;

  /// No description provided for @kmLower.
  ///
  /// In ar, this message translates to:
  /// **'القراءة أقل من آخر قراءة ({km} كم). تأكد منها: سترسل للمراجعة.'**
  String kmLower(String km);

  /// No description provided for @kmInvalid.
  ///
  /// In ar, this message translates to:
  /// **'اكتب القراءة بالأرقام'**
  String get kmInvalid;

  /// No description provided for @photoRequired.
  ///
  /// In ar, this message translates to:
  /// **'الصورة مطلوبة'**
  String get photoRequired;

  /// No description provided for @sentTitle.
  ///
  /// In ar, this message translates to:
  /// **'تم الإرسال'**
  String get sentTitle;

  /// No description provided for @queuedTitle.
  ///
  /// In ar, this message translates to:
  /// **'حُفظ على الهاتف'**
  String get queuedTitle;

  /// No description provided for @sentText.
  ///
  /// In ar, this message translates to:
  /// **'وصل للشركة.'**
  String get sentText;

  /// No description provided for @queuedText.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد شبكة الآن. سيُرسل تلقائياً بوقته الأصلي عند عودة الاتصال.'**
  String get queuedText;

  /// No description provided for @reportTitle.
  ///
  /// In ar, this message translates to:
  /// **'التقرير اليومي'**
  String get reportTitle;

  /// No description provided for @reportDate.
  ///
  /// In ar, this message translates to:
  /// **'يوم العمل'**
  String get reportDate;

  /// No description provided for @today.
  ///
  /// In ar, this message translates to:
  /// **'اليوم'**
  String get today;

  /// No description provided for @yesterday.
  ///
  /// In ar, this message translates to:
  /// **'أمس'**
  String get yesterday;

  /// No description provided for @dayBefore.
  ///
  /// In ar, this message translates to:
  /// **'قبل أمس'**
  String get dayBefore;

  /// No description provided for @ordersCount.
  ///
  /// In ar, this message translates to:
  /// **'عدد الطلبات'**
  String get ordersCount;

  /// No description provided for @cashAmount.
  ///
  /// In ar, this message translates to:
  /// **'الكاش المحصّل'**
  String get cashAmount;

  /// No description provided for @cashInvalid.
  ///
  /// In ar, this message translates to:
  /// **'مبلغ بثلاث خانات عشرية كحد أقصى'**
  String get cashInvalid;

  /// No description provided for @screenshot.
  ///
  /// In ar, this message translates to:
  /// **'لقطة شاشة ملخص اليوم من تطبيق الطلبات'**
  String get screenshot;

  /// No description provided for @notes.
  ///
  /// In ar, this message translates to:
  /// **'ملاحظات'**
  String get notes;

  /// No description provided for @recentReports.
  ///
  /// In ar, this message translates to:
  /// **'آخر التقارير'**
  String get recentReports;

  /// No description provided for @status_submitted.
  ///
  /// In ar, this message translates to:
  /// **'بانتظار المراجعة'**
  String get status_submitted;

  /// No description provided for @status_approved.
  ///
  /// In ar, this message translates to:
  /// **'معتمد'**
  String get status_approved;

  /// No description provided for @status_rejected.
  ///
  /// In ar, this message translates to:
  /// **'مرفوض'**
  String get status_rejected;

  /// No description provided for @approvedCash.
  ///
  /// In ar, this message translates to:
  /// **'المعتمد: {amount}'**
  String approvedCash(String amount);

  /// No description provided for @cashTitle.
  ///
  /// In ar, this message translates to:
  /// **'الكاش'**
  String get cashTitle;

  /// No description provided for @cashTotal.
  ///
  /// In ar, this message translates to:
  /// **'رصيد الكاش معك'**
  String get cashTotal;

  /// No description provided for @cashPosted.
  ///
  /// In ar, this message translates to:
  /// **'معتمد'**
  String get cashPosted;

  /// No description provided for @cashPending.
  ///
  /// In ar, this message translates to:
  /// **'بانتظار المراجعة'**
  String get cashPending;

  /// No description provided for @cashOverLimit.
  ///
  /// In ar, this message translates to:
  /// **'الرصيد فوق الحد ({limit}): سلّم الكاش للصراف.'**
  String cashOverLimit(String limit);

  /// No description provided for @receipts.
  ///
  /// In ar, this message translates to:
  /// **'الإيصالات'**
  String get receipts;

  /// No description provided for @receiptNo.
  ///
  /// In ar, this message translates to:
  /// **'إيصال رقم {no}'**
  String receiptNo(String no);

  /// No description provided for @confirmReceipt.
  ///
  /// In ar, this message translates to:
  /// **'أؤكد التسليم'**
  String get confirmReceipt;

  /// No description provided for @receiptConfirmed.
  ///
  /// In ar, this message translates to:
  /// **'مؤكد'**
  String get receiptConfirmed;

  /// No description provided for @confirmReceiptQ.
  ///
  /// In ar, this message translates to:
  /// **'هل سلّمت {amount} د.ك للصراف؟'**
  String confirmReceiptQ(String amount);

  /// No description provided for @noReceipts.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد إيصالات بعد'**
  String get noReceipts;

  /// No description provided for @language.
  ///
  /// In ar, this message translates to:
  /// **'اللغة'**
  String get language;

  /// No description provided for @trackingDetails.
  ///
  /// In ar, this message translates to:
  /// **'حالة التتبع'**
  String get trackingDetails;

  /// No description provided for @lastUpload.
  ///
  /// In ar, this message translates to:
  /// **'آخر إرسال: {when}'**
  String lastUpload(String when);

  /// No description provided for @never.
  ///
  /// In ar, this message translates to:
  /// **'لم يحدث بعد'**
  String get never;

  /// No description provided for @appVersion.
  ///
  /// In ar, this message translates to:
  /// **'الإصدار {version}'**
  String appVersion(String version);

  /// No description provided for @signOut.
  ///
  /// In ar, this message translates to:
  /// **'تسجيل الخروج'**
  String get signOut;

  /// No description provided for @signOutQ.
  ///
  /// In ar, this message translates to:
  /// **'سيتوقف التتبع وتحتاج تفعيلاً جديداً للدخول. متابعة؟'**
  String get signOutQ;

  /// No description provided for @blockedTitle.
  ///
  /// In ar, this message translates to:
  /// **'حسابك موقوف'**
  String get blockedTitle;

  /// No description provided for @blockedText.
  ///
  /// In ar, this message translates to:
  /// **'تواصل مع المشرف.'**
  String get blockedText;

  /// No description provided for @obReady.
  ///
  /// In ar, this message translates to:
  /// **'كل شيء جاهز: أرسله للمراجعة.'**
  String get obReady;

  /// No description provided for @maintenance.
  ///
  /// In ar, this message translates to:
  /// **'الصيانة'**
  String get maintenance;

  /// No description provided for @maintenanceTitle.
  ///
  /// In ar, this message translates to:
  /// **'طلبات الصيانة'**
  String get maintenanceTitle;

  /// No description provided for @kind_maintenance.
  ///
  /// In ar, this message translates to:
  /// **'طلب صيانة'**
  String get kind_maintenance;

  /// No description provided for @mntNew.
  ///
  /// In ar, this message translates to:
  /// **'طلب صيانة جديد'**
  String get mntNew;

  /// No description provided for @mntIntro.
  ///
  /// In ar, this message translates to:
  /// **'صِف المشكلة وصوّرها من الكاميرا. يصل الطلب للمشرف ليعتمده ويحدد مركز الصيانة.'**
  String get mntIntro;

  /// No description provided for @mntNoVehicle.
  ///
  /// In ar, this message translates to:
  /// **'تطلب الصيانة للسيارة التي في عهدتك. لا توجد سيارة معك الآن.'**
  String get mntNoVehicle;

  /// No description provided for @mntKind.
  ///
  /// In ar, this message translates to:
  /// **'النوع'**
  String get mntKind;

  /// No description provided for @mntDescription.
  ///
  /// In ar, this message translates to:
  /// **'وصف المشكلة'**
  String get mntDescription;

  /// No description provided for @mntOdometer.
  ///
  /// In ar, this message translates to:
  /// **'قراءة العداد (اختياري)'**
  String get mntOdometer;

  /// No description provided for @mntPhotos.
  ///
  /// In ar, this message translates to:
  /// **'صور (حتى 4)'**
  String get mntPhotos;

  /// No description provided for @mntAddPhoto.
  ///
  /// In ar, this message translates to:
  /// **'صورة'**
  String get mntAddPhoto;

  /// No description provided for @mntNone.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد طلبات صيانة'**
  String get mntNone;

  /// No description provided for @mntRequestNo.
  ///
  /// In ar, this message translates to:
  /// **'طلب #{number}'**
  String mntRequestNo(String number);

  /// No description provided for @mntAtCenter.
  ///
  /// In ar, this message translates to:
  /// **'المركز: {center}'**
  String mntAtCenter(String center);

  /// No description provided for @mntReadyBanner.
  ///
  /// In ar, this message translates to:
  /// **'سيارتك {plate} جاهزة للاستلام من {center}'**
  String mntReadyBanner(String plate, String center);

  /// No description provided for @mntRejected.
  ///
  /// In ar, this message translates to:
  /// **'رُفض: {reason}'**
  String mntRejected(String reason);

  /// No description provided for @mntSent.
  ///
  /// In ar, this message translates to:
  /// **'أُرسل طلب الصيانة للمشرف'**
  String get mntSent;

  /// No description provided for @mntKind_periodic.
  ///
  /// In ar, this message translates to:
  /// **'صيانة دورية'**
  String get mntKind_periodic;

  /// No description provided for @mntKind_mechanical.
  ///
  /// In ar, this message translates to:
  /// **'ميكانيكا'**
  String get mntKind_mechanical;

  /// No description provided for @mntKind_electrical.
  ///
  /// In ar, this message translates to:
  /// **'كهرباء'**
  String get mntKind_electrical;

  /// No description provided for @mntKind_tyres.
  ///
  /// In ar, this message translates to:
  /// **'إطارات'**
  String get mntKind_tyres;

  /// No description provided for @mntKind_battery.
  ///
  /// In ar, this message translates to:
  /// **'بطارية'**
  String get mntKind_battery;

  /// No description provided for @mntKind_ac.
  ///
  /// In ar, this message translates to:
  /// **'تكييف'**
  String get mntKind_ac;

  /// No description provided for @mntKind_bodywork.
  ///
  /// In ar, this message translates to:
  /// **'سمكرة وصبغ'**
  String get mntKind_bodywork;

  /// No description provided for @mntKind_other.
  ///
  /// In ar, this message translates to:
  /// **'أخرى'**
  String get mntKind_other;

  /// No description provided for @mntStatus_requested.
  ///
  /// In ar, this message translates to:
  /// **'بانتظار الاعتماد'**
  String get mntStatus_requested;

  /// No description provided for @mntStatus_approved.
  ///
  /// In ar, this message translates to:
  /// **'معتمد'**
  String get mntStatus_approved;

  /// No description provided for @mntStatus_rejected.
  ///
  /// In ar, this message translates to:
  /// **'مرفوض'**
  String get mntStatus_rejected;

  /// No description provided for @mntStatus_referred.
  ///
  /// In ar, this message translates to:
  /// **'محال لمركز الصيانة'**
  String get mntStatus_referred;

  /// No description provided for @mntStatus_at_center.
  ///
  /// In ar, this message translates to:
  /// **'في مركز الصيانة'**
  String get mntStatus_at_center;

  /// No description provided for @mntStatus_ready.
  ///
  /// In ar, this message translates to:
  /// **'جاهزة للاستلام'**
  String get mntStatus_ready;

  /// No description provided for @mntStatus_picked_up.
  ///
  /// In ar, this message translates to:
  /// **'تم الاستلام'**
  String get mntStatus_picked_up;

  /// No description provided for @mntStatus_closed.
  ///
  /// In ar, this message translates to:
  /// **'مغلق'**
  String get mntStatus_closed;

  /// No description provided for @mntStatus_cancelled.
  ///
  /// In ar, this message translates to:
  /// **'ملغى'**
  String get mntStatus_cancelled;

  /// No description provided for @mntTapToRemove.
  ///
  /// In ar, this message translates to:
  /// **'اضغط للحذف'**
  String get mntTapToRemove;

  /// No description provided for @accident.
  ///
  /// In ar, this message translates to:
  /// **'الإبلاغ عن حادث'**
  String get accident;

  /// No description provided for @accidentsTitle.
  ///
  /// In ar, this message translates to:
  /// **'الحوادث'**
  String get accidentsTitle;

  /// No description provided for @kind_accident.
  ///
  /// In ar, this message translates to:
  /// **'بلاغ حادث'**
  String get kind_accident;

  /// No description provided for @kind_police_report.
  ///
  /// In ar, this message translates to:
  /// **'محضر الشرطة'**
  String get kind_police_report;

  /// No description provided for @accNew.
  ///
  /// In ar, this message translates to:
  /// **'بلاغ حادث جديد'**
  String get accNew;

  /// No description provided for @accEmergency.
  ///
  /// In ar, this message translates to:
  /// **'إن وُجدت إصابات اتصل بالطوارئ 112 أولاً.'**
  String get accEmergency;

  /// No description provided for @accIntro.
  ///
  /// In ar, this message translates to:
  /// **'صوّر السيارة من عدة زوايا: الأمام والخلف والجانبين ومكان الضرر. يُسجّل الوقت والموقع تلقائياً.'**
  String get accIntro;

  /// No description provided for @accNoVehicle.
  ///
  /// In ar, this message translates to:
  /// **'يُبلّغ عن الحادث للسيارة التي في عهدتك. لا توجد سيارة معك الآن؛ كلّم المشرف.'**
  String get accNoVehicle;

  /// No description provided for @accDescription.
  ///
  /// In ar, this message translates to:
  /// **'ماذا حدث؟'**
  String get accDescription;

  /// No description provided for @accInjuries.
  ///
  /// In ar, this message translates to:
  /// **'توجد إصابات'**
  String get accInjuries;

  /// No description provided for @accInjuriesNote.
  ///
  /// In ar, this message translates to:
  /// **'تفاصيل الإصابات'**
  String get accInjuriesNote;

  /// No description provided for @accOtherParty.
  ///
  /// In ar, this message translates to:
  /// **'الطرف الآخر (اللوحة، الاسم، التأمين)'**
  String get accOtherParty;

  /// No description provided for @accPhotos.
  ///
  /// In ar, this message translates to:
  /// **'صور الحادث ({min} على الأقل)'**
  String accPhotos(String min);

  /// No description provided for @accPhotosNeeded.
  ///
  /// In ar, this message translates to:
  /// **'صوّر {min} صور على الأقل من زوايا مختلفة'**
  String accPhotosNeeded(String min);

  /// No description provided for @accPoliceReport.
  ///
  /// In ar, this message translates to:
  /// **'محضر الشرطة'**
  String get accPoliceReport;

  /// No description provided for @accPoliceReportNo.
  ///
  /// In ar, this message translates to:
  /// **'رقم المحضر'**
  String get accPoliceReportNo;

  /// No description provided for @accPoliceLater.
  ///
  /// In ar, this message translates to:
  /// **'لم يصدر المحضر بعد؟ أرسل البلاغ الآن وأرسل صورة المحضر لاحقاً من قائمة حوادثك.'**
  String get accPoliceLater;

  /// No description provided for @accSendPolice.
  ///
  /// In ar, this message translates to:
  /// **'إرسال محضر الشرطة'**
  String get accSendPolice;

  /// No description provided for @accNone.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد حوادث'**
  String get accNone;

  /// No description provided for @accNo.
  ///
  /// In ar, this message translates to:
  /// **'حادث #{number}'**
  String accNo(String number);

  /// No description provided for @accStage_review.
  ///
  /// In ar, this message translates to:
  /// **'قيد المراجعة'**
  String get accStage_review;

  /// No description provided for @accStage_outcome.
  ///
  /// In ar, this message translates to:
  /// **'بانتظار تحديد المسؤولية'**
  String get accStage_outcome;

  /// No description provided for @accStage_recorded.
  ///
  /// In ar, this message translates to:
  /// **'المسؤولية محددة'**
  String get accStage_recorded;

  /// No description provided for @accStage_closed.
  ///
  /// In ar, this message translates to:
  /// **'مغلق'**
  String get accStage_closed;

  /// No description provided for @accLiability_none.
  ///
  /// In ar, this message translates to:
  /// **'لا مسؤولية عليك'**
  String get accLiability_none;

  /// No description provided for @accLiability_driver.
  ///
  /// In ar, this message translates to:
  /// **'المسؤولية عليك'**
  String get accLiability_driver;

  /// No description provided for @accLiability_shared.
  ///
  /// In ar, this message translates to:
  /// **'مسؤولية مشتركة: نصيبك {percent}%'**
  String accLiability_shared(String percent);

  /// No description provided for @accDeduction.
  ///
  /// In ar, this message translates to:
  /// **'خصم {total} د.ك · عدد الأقساط: {count}'**
  String accDeduction(String total, String count);

  /// No description provided for @accInstallment.
  ///
  /// In ar, this message translates to:
  /// **'{month}: {amount} د.ك'**
  String accInstallment(String month, String amount);

  /// No description provided for @accAwaitingPolice.
  ///
  /// In ar, this message translates to:
  /// **'الحادث #{number} بانتظار محضر الشرطة: اضغط لإرسال صورته'**
  String accAwaitingPolice(String number);

  /// No description provided for @fines.
  ///
  /// In ar, this message translates to:
  /// **'المخالفات المرورية'**
  String get fines;

  /// No description provided for @finesTitle.
  ///
  /// In ar, this message translates to:
  /// **'المخالفات المرورية'**
  String get finesTitle;

  /// No description provided for @finesIntro.
  ///
  /// In ar, this message translates to:
  /// **'المخالفات على السيارة وهي في عهدتك، حسب وقت المخالفة. الشركة تقرر: على الشركة أو خصم من راتبك بأقساط.'**
  String get finesIntro;

  /// No description provided for @finesNone.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد مخالفات'**
  String get finesNone;

  /// No description provided for @fineStatus_open.
  ///
  /// In ar, this message translates to:
  /// **'قيد المراجعة'**
  String get fineStatus_open;

  /// No description provided for @fineStatus_charged.
  ///
  /// In ar, this message translates to:
  /// **'تُخصم من راتبك'**
  String get fineStatus_charged;

  /// No description provided for @fineStatus_company.
  ///
  /// In ar, this message translates to:
  /// **'على الشركة'**
  String get fineStatus_company;

  /// No description provided for @monthlyStatement.
  ///
  /// In ar, this message translates to:
  /// **'كشف المنصة الشهري'**
  String get monthlyStatement;

  /// No description provided for @payslips.
  ///
  /// In ar, this message translates to:
  /// **'كشوف الراتب'**
  String get payslips;

  /// No description provided for @statementTitle.
  ///
  /// In ar, this message translates to:
  /// **'كشف المنصة الشهري'**
  String get statementTitle;

  /// No description provided for @statementIntro.
  ///
  /// In ar, this message translates to:
  /// **'في بداية كل شهر أرسل لقطات شاشة ملخص الشهر من تطبيق {platform} واكتب الأرقام كما تظهر فيها. يراجعها المكتب مع اللقطات قبل احتساب الراتب.'**
  String statementIntro(String platform);

  /// No description provided for @statementNoPlatform.
  ///
  /// In ar, this message translates to:
  /// **'لم تُحدَّد منصتك بعد. تواصل مع المكتب.'**
  String get statementNoPlatform;

  /// No description provided for @statementNoMonth.
  ///
  /// In ar, this message translates to:
  /// **'أرسلت كشف كل الأشهر المفتوحة. انتظر مراجعة المكتب.'**
  String get statementNoMonth;

  /// No description provided for @statementMonth.
  ///
  /// In ar, this message translates to:
  /// **'الشهر'**
  String get statementMonth;

  /// No description provided for @statementShots.
  ///
  /// In ar, this message translates to:
  /// **'لقطات الشاشة من تطبيق المنصة (حتى 6)'**
  String get statementShots;

  /// No description provided for @statementShotRequired.
  ///
  /// In ar, this message translates to:
  /// **'أضف لقطة شاشة واحدة على الأقل'**
  String get statementShotRequired;

  /// No description provided for @statementHistory.
  ///
  /// In ar, this message translates to:
  /// **'ما أرسلته'**
  String get statementHistory;

  /// No description provided for @statementSentDays.
  ///
  /// In ar, this message translates to:
  /// **'أرسلت: {days} يوم صالح'**
  String statementSentDays(String days);

  /// No description provided for @statementApprovedDays.
  ///
  /// In ar, this message translates to:
  /// **'المعتمد: {days} يوم صالح'**
  String statementApprovedDays(String days);

  /// No description provided for @statementStatus_submitted.
  ///
  /// In ar, this message translates to:
  /// **'بانتظار المراجعة'**
  String get statementStatus_submitted;

  /// No description provided for @statementStatus_approved.
  ///
  /// In ar, this message translates to:
  /// **'معتمد'**
  String get statementStatus_approved;

  /// No description provided for @statementStatus_rejected.
  ///
  /// In ar, this message translates to:
  /// **'مرفوض: أرسله من جديد'**
  String get statementStatus_rejected;

  /// No description provided for @addShot.
  ///
  /// In ar, this message translates to:
  /// **'إضافة لقطة'**
  String get addShot;

  /// No description provided for @validDays.
  ///
  /// In ar, this message translates to:
  /// **'عدد الأيام الصالحة'**
  String get validDays;

  /// No description provided for @ordersTotal.
  ///
  /// In ar, this message translates to:
  /// **'إجمالي الطلبات'**
  String get ordersTotal;

  /// No description provided for @hoursTotal.
  ///
  /// In ar, this message translates to:
  /// **'إجمالي الساعات'**
  String get hoursTotal;

  /// No description provided for @payslipsTitle.
  ///
  /// In ar, this message translates to:
  /// **'كشوف الراتب'**
  String get payslipsTitle;

  /// No description provided for @payslipsNone.
  ///
  /// In ar, this message translates to:
  /// **'لا يوجد كشف راتب معتمد بعد'**
  String get payslipsNone;

  /// No description provided for @payslipNet.
  ///
  /// In ar, this message translates to:
  /// **'صافي الراتب'**
  String get payslipNet;

  /// No description provided for @payslipStatus_approved.
  ///
  /// In ar, this message translates to:
  /// **'معتمد'**
  String get payslipStatus_approved;

  /// No description provided for @payslipStatus_paid.
  ///
  /// In ar, this message translates to:
  /// **'مدفوع'**
  String get payslipStatus_paid;

  /// No description provided for @iban.
  ///
  /// In ar, this message translates to:
  /// **'رقم الآيبان (IBAN)'**
  String get iban;

  /// No description provided for @ibanHint.
  ///
  /// In ar, this message translates to:
  /// **'يُحوَّل عليه راتبك: انسخه من تطبيق البنك'**
  String get ibanHint;

  /// No description provided for @bankName.
  ///
  /// In ar, this message translates to:
  /// **'اسم البنك'**
  String get bankName;

  /// No description provided for @civilSignIn.
  ///
  /// In ar, this message translates to:
  /// **'الدخول بالرقم المدني'**
  String get civilSignIn;

  /// No description provided for @civilSignInHint.
  ///
  /// In ar, this message translates to:
  /// **'إن لم يكن رقم هاتفك مسجلاً لدى الشركة: ادخل برقمك المدني وكلمة المرور المبدئية التي أعطاك إياها المكتب، ثم سجّل هاتفك. كلمة المرور تعمل مرة واحدة.'**
  String get civilSignInHint;

  /// No description provided for @initialPassword.
  ///
  /// In ar, this message translates to:
  /// **'كلمة المرور المبدئية'**
  String get initialPassword;

  /// No description provided for @claimContinue.
  ///
  /// In ar, this message translates to:
  /// **'متابعة'**
  String get claimContinue;

  /// No description provided for @claimWelcome.
  ///
  /// In ar, this message translates to:
  /// **'أهلاً {name}. اكتب رقم هاتفك الذي عليه واتساب: يصلك عليه رمز التحقق، وبه تدخل التطبيق بعد ذلك.'**
  String claimWelcome(String name);

  /// No description provided for @password.
  ///
  /// In ar, this message translates to:
  /// **'كلمة المرور'**
  String get password;

  /// No description provided for @civilSignInOnly.
  ///
  /// In ar, this message translates to:
  /// **'ادخل برقمك المدني وكلمة مرورك. أول مرة: كلمة المرور المبدئية التي أعطاك إياها المكتب، ثم تختار كلمة مرورك.'**
  String get civilSignInOnly;

  /// No description provided for @forgotPassword.
  ///
  /// In ar, this message translates to:
  /// **'نسيت كلمة المرور؟ اطلب من المشرف كلمة مرور مبدئية جديدة.'**
  String get forgotPassword;

  /// No description provided for @choosePassword.
  ///
  /// In ar, this message translates to:
  /// **'أهلاً {name}. اختر كلمة مرورك: بها وبرقمك المدني تدخل التطبيق بعد ذلك من أي هاتف. 8 أحرف على الأقل، غير كلمة المرور المبدئية ورقمك المدني، ولا تخبر بها أحداً.'**
  String choosePassword(String name);

  /// No description provided for @newPassword.
  ///
  /// In ar, this message translates to:
  /// **'كلمة المرور الجديدة'**
  String get newPassword;

  /// No description provided for @confirmPassword.
  ///
  /// In ar, this message translates to:
  /// **'أعد كتابة كلمة المرور'**
  String get confirmPassword;

  /// No description provided for @passwordTooShort.
  ///
  /// In ar, this message translates to:
  /// **'8 أحرف على الأقل'**
  String get passwordTooShort;

  /// No description provided for @passwordsDiffer.
  ///
  /// In ar, this message translates to:
  /// **'كلمتا المرور غير متطابقتين'**
  String get passwordsDiffer;

  /// No description provided for @passwordIsCivilId.
  ///
  /// In ar, this message translates to:
  /// **'لا تستخدم رقمك المدني كلمة مرور'**
  String get passwordIsCivilId;

  /// No description provided for @saveAndSignIn.
  ///
  /// In ar, this message translates to:
  /// **'حفظ والدخول'**
  String get saveAndSignIn;

  /// No description provided for @validDayQuestion.
  ///
  /// In ar, this message translates to:
  /// **'هل احتسب تطبيق المنصة هذا اليوم يوماً صالحاً؟'**
  String get validDayQuestion;

  /// No description provided for @validDayYes.
  ///
  /// In ar, this message translates to:
  /// **'يوم صالح'**
  String get validDayYes;

  /// No description provided for @validDayNo.
  ///
  /// In ar, this message translates to:
  /// **'غير صالح'**
  String get validDayNo;

  /// No description provided for @paySchemes.
  ///
  /// In ar, this message translates to:
  /// **'نظام الدفع'**
  String get paySchemes;

  /// No description provided for @schemesIntro.
  ///
  /// In ar, this message translates to:
  /// **'النظام يحدد كيف يُحسب راتبك من طلباتك. تقدر تطلب نظاماً آخر تعرضه منصتك، ويبدأ من أول الشهر التالي لو وافق المكتب.'**
  String get schemesIntro;

  /// No description provided for @schemeNow.
  ///
  /// In ar, this message translates to:
  /// **'نظامك هذا الشهر'**
  String get schemeNow;

  /// No description provided for @schemeNone.
  ///
  /// In ar, this message translates to:
  /// **'لم يحدد المكتب نظامك بعد'**
  String get schemeNone;

  /// No description provided for @schemeNextMonth.
  ///
  /// In ar, this message translates to:
  /// **'من الشهر القادم: {name}'**
  String schemeNextMonth(String name);

  /// No description provided for @schemeOthers.
  ///
  /// In ar, this message translates to:
  /// **'الأنظمة الأخرى في منصتك'**
  String get schemeOthers;

  /// No description provided for @schemeAsk.
  ///
  /// In ar, this message translates to:
  /// **'اطلب هذا النظام'**
  String get schemeAsk;

  /// No description provided for @schemeAskBody.
  ///
  /// In ar, this message translates to:
  /// **'تطلب «{name}» من {month}. يراجعه المكتب ويصلك الرد هنا وعلى واتساب.'**
  String schemeAskBody(String name, String month);

  /// No description provided for @schemeNoteHint.
  ///
  /// In ar, this message translates to:
  /// **'ملاحظة للمكتب (اختياري)'**
  String get schemeNoteHint;

  /// No description provided for @schemeSend.
  ///
  /// In ar, this message translates to:
  /// **'إرسال الطلب'**
  String get schemeSend;

  /// No description provided for @schemeSent.
  ///
  /// In ar, this message translates to:
  /// **'أُرسل طلبك للمكتب'**
  String get schemeSent;

  /// No description provided for @schemePending.
  ///
  /// In ar, this message translates to:
  /// **'طلبك «{name}» من {month} بانتظار المكتب'**
  String schemePending(String name, String month);

  /// No description provided for @schemeApproved.
  ///
  /// In ar, this message translates to:
  /// **'وافق المكتب: «{name}» من {month}'**
  String schemeApproved(String name, String month);

  /// No description provided for @schemeRejected.
  ///
  /// In ar, this message translates to:
  /// **'رفض المكتب طلبك «{name}»: {note}'**
  String schemeRejected(String name, String note);

  /// No description provided for @schemeCancel.
  ///
  /// In ar, this message translates to:
  /// **'إلغاء الطلب'**
  String get schemeCancel;

  /// No description provided for @schemePerOrder.
  ///
  /// In ar, this message translates to:
  /// **'سعر الطلب: {rate} د.ك'**
  String schemePerOrder(String rate);

  /// No description provided for @schemeBatchRates.
  ///
  /// In ar, this message translates to:
  /// **'سعر الطلب حسب مستوى الباتش في الشهر:'**
  String get schemeBatchRates;

  /// No description provided for @schemeBatchRow.
  ///
  /// In ar, this message translates to:
  /// **'باتش {level}: {rate} د.ك'**
  String schemeBatchRow(String level, String rate);

  /// No description provided for @schemeReduced.
  ///
  /// In ar, this message translates to:
  /// **'ينخفض إلى {rate} د.ك لكل طلبات الشهر لو فوّت Star Day أو وصلت علاماتك {marks}'**
  String schemeReduced(String rate, String marks);

  /// No description provided for @schemeReducedStar.
  ///
  /// In ar, this message translates to:
  /// **'ينخفض إلى {rate} د.ك لكل طلبات الشهر لو فوّت Star Day'**
  String schemeReducedStar(String rate);

  /// No description provided for @schemeReducedLoses.
  ///
  /// In ar, this message translates to:
  /// **'في شهر السعر المخفض لا يُصرف البونص'**
  String get schemeReducedLoses;

  /// No description provided for @schemeTiers.
  ///
  /// In ar, this message translates to:
  /// **'بونص الشرائح (أعلى شريحة تصلها فقط):'**
  String get schemeTiers;

  /// No description provided for @schemeTierRow.
  ///
  /// In ar, this message translates to:
  /// **'{orders} طلب: {amount} د.ك'**
  String schemeTierRow(String orders, String amount);

  /// No description provided for @schemeMarks.
  ///
  /// In ar, this message translates to:
  /// **'خصم علامات الحضور:'**
  String get schemeMarks;

  /// No description provided for @schemeMarkRow.
  ///
  /// In ar, this message translates to:
  /// **'{marks} علامات: {amount} د.ك'**
  String schemeMarkRow(String marks, String amount);

  /// No description provided for @schemeTarget.
  ///
  /// In ar, this message translates to:
  /// **'التارجت: {orders} طلب و{days} يوم صالح في الشهر'**
  String schemeTarget(String orders, String days);

  /// No description provided for @schemeMissing.
  ///
  /// In ar, this message translates to:
  /// **'كل طلب ناقص عن التارجت يُخصم {rate} د.ك'**
  String schemeMissing(String rate);

  /// No description provided for @schemeNoMissing.
  ///
  /// In ar, this message translates to:
  /// **'لا خصم على الطلبات الناقصة عن التارجت'**
  String get schemeNoMissing;

  /// No description provided for @schemeCovers.
  ///
  /// In ar, this message translates to:
  /// **'على الشركة: {items}'**
  String schemeCovers(String items);

  /// No description provided for @schemeCoversNone.
  ///
  /// In ar, this message translates to:
  /// **'المصاريف عليك: الصيانة والسكن والبنزين والشريحة'**
  String get schemeCoversNone;

  /// No description provided for @schemePlatformRates.
  ///
  /// In ar, this message translates to:
  /// **'حسب قاعدة المنصة: راتب أساسي وأسعار الشركة'**
  String get schemePlatformRates;

  /// No description provided for @expense_maintenance.
  ///
  /// In ar, this message translates to:
  /// **'الصيانة'**
  String get expense_maintenance;

  /// No description provided for @expense_housing.
  ///
  /// In ar, this message translates to:
  /// **'السكن'**
  String get expense_housing;

  /// No description provided for @expense_gas.
  ///
  /// In ar, this message translates to:
  /// **'البنزين'**
  String get expense_gas;

  /// No description provided for @expense_sim.
  ///
  /// In ar, this message translates to:
  /// **'الشريحة'**
  String get expense_sim;

  /// No description provided for @schemeChoose.
  ///
  /// In ar, this message translates to:
  /// **'نظام الدفع'**
  String get schemeChoose;

  /// No description provided for @schemeChooseHint.
  ///
  /// In ar, this message translates to:
  /// **'اختر النظام الذي تشتغل عليه. يراجعه المكتب مع تسجيلك، وتقدر تطلب تغييره لاحقاً من التطبيق.'**
  String get schemeChooseHint;

  /// No description provided for @payslipScheme.
  ///
  /// In ar, this message translates to:
  /// **'كيف حسب نظامك الشهر: {name}'**
  String payslipScheme(String name);

  /// No description provided for @payItem_orders_pay.
  ///
  /// In ar, this message translates to:
  /// **'قيمة الطلبات'**
  String get payItem_orders_pay;

  /// No description provided for @payItem_tier_bonus.
  ///
  /// In ar, this message translates to:
  /// **'بونص الشريحة'**
  String get payItem_tier_bonus;

  /// No description provided for @payItem_missing_target.
  ///
  /// In ar, this message translates to:
  /// **'خصم نقص التارجت'**
  String get payItem_missing_target;

  /// No description provided for @payItem_marks_deduction.
  ///
  /// In ar, this message translates to:
  /// **'خصم علامات الحضور'**
  String get payItem_marks_deduction;

  /// No description provided for @payItem_uncovered_penalty.
  ///
  /// In ar, this message translates to:
  /// **'عقوبات لم تُخصم'**
  String get payItem_uncovered_penalty;

  /// No description provided for @payWhyOrders.
  ///
  /// In ar, this message translates to:
  /// **'{orders} طلب × {rate} د.ك'**
  String payWhyOrders(String orders, String rate);

  /// No description provided for @payWhyBatch.
  ///
  /// In ar, this message translates to:
  /// **'باتش {level}'**
  String payWhyBatch(String level);

  /// No description provided for @payWhyReducedStar.
  ///
  /// In ar, this message translates to:
  /// **'السعر المخفض: فوّت Star Day'**
  String get payWhyReducedStar;

  /// No description provided for @payWhyReducedMarks.
  ///
  /// In ar, this message translates to:
  /// **'السعر المخفض: علامات الحضور'**
  String get payWhyReducedMarks;

  /// No description provided for @payWhyTier.
  ///
  /// In ar, this message translates to:
  /// **'وصلت {orders} طلب: شريحة {from}'**
  String payWhyTier(String orders, String from);

  /// No description provided for @payWhyMissing.
  ///
  /// In ar, this message translates to:
  /// **'{missing} طلب ناقص عن {target} × {rate} د.ك'**
  String payWhyMissing(String missing, String target, String rate);

  /// No description provided for @payWhyMarks.
  ///
  /// In ar, this message translates to:
  /// **'{marks} علامات حضور'**
  String payWhyMarks(String marks);

  /// No description provided for @payWhyUncovered.
  ///
  /// In ar, this message translates to:
  /// **'العقوبات أكبر من المستحق، والشهر لا ينزل تحت الصفر: هذا الباقي لم يُخصم'**
  String get payWhyUncovered;

  /// No description provided for @noticesTitle.
  ///
  /// In ar, this message translates to:
  /// **'الإشعارات'**
  String get noticesTitle;

  /// No description provided for @noticesNone.
  ///
  /// In ar, this message translates to:
  /// **'لا توجد إشعارات بعد'**
  String get noticesNone;
}

class _AppLocalizationsDelegate extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) => <String>['ar', 'en'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'ar':
      return AppLocalizationsAr();
    case 'en':
      return AppLocalizationsEn();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
