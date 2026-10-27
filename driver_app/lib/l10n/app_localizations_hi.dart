// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Hindi (`hi`).
class AppLocalizationsHi extends AppLocalizations {
  AppLocalizationsHi([String locale = 'hi']) : super(locale);

  @override
  String get appTitle => 'ड्राइवर ऐप';

  @override
  String get retry => 'फिर से कोशिश करें';

  @override
  String get cancel => 'रद्द करें';

  @override
  String get continueBtn => 'जारी रखें';

  @override
  String get save => 'सेव करें';

  @override
  String get send => 'भेजें';

  @override
  String get back => 'वापस';

  @override
  String get done => 'हो गया';

  @override
  String get networkError => 'इंटरनेट कनेक्शन नहीं है। फिर से कोशिश करें।';

  @override
  String get genericError => 'कुछ गलत हो गया। फिर से कोशिश करें।';

  @override
  String get kwd => 'KWD';

  @override
  String get km => 'कि.मी.';

  @override
  String get signInTitle => 'साइन इन';

  @override
  String get signInHint =>
      'कंपनी में दर्ज अपना फ़ोन नंबर डालें। साइन-इन कोड WhatsApp पर आएगा।';

  @override
  String get phoneLabel => 'फ़ोन';

  @override
  String get phoneInvalid =>
      'कुवैत के 8 अंक, या + से शुरू होने वाला अंतरराष्ट्रीय नंबर';

  @override
  String get sendCode => 'कोड भेजें';

  @override
  String get activationTip =>
      'अगर आपको WhatsApp पर एक्टिवेशन लिंक मिला है, तो उसे इसी फ़ोन पर खोलें: कोड की ज़रूरत नहीं।';

  @override
  String get otpTitle => 'साइन-इन कोड';

  @override
  String otpHint(String phone) {
    return '$phone पर WhatsApp से भेजा गया 6 अंकों का कोड डालें।';
  }

  @override
  String get otpLabel => 'कोड';

  @override
  String get verify => 'साइन इन करें';

  @override
  String get otpResend => 'कोड नहीं मिला? फिर से भेजें';

  @override
  String get activating => 'इस फ़ोन पर ऐप एक्टिवेट हो रहा है…';

  @override
  String get activationFailed => 'एक्टिवेशन विफल रहा';

  @override
  String get permTitle => 'ऐप की अनुमतियाँ';

  @override
  String get permIntro =>
      'आपकी ज़िम्मेदारी के दौरान ट्रैकिंग के लिए, ऐप बंद होने पर भी, ऐप को ये अनुमतियाँ चाहिए। आपकी लोकेशन सिर्फ़ तभी दर्ज होती है जब कोई गाड़ी आपकी ज़िम्मेदारी में हो।';

  @override
  String get permLocation => 'लोकेशन: “हमेशा अनुमति दें”';

  @override
  String get permLocationWhy =>
      'ताकि सुपरवाइज़र आपकी ज़िम्मेदारी के दौरान गाड़ी देख सके।';

  @override
  String get permNotifications => 'सूचनाएँ';

  @override
  String get permNotificationsWhy =>
      'ट्रैकिंग के दौरान एक स्थायी सूचना दिखती है (Android का नियम)।';

  @override
  String get permBattery => 'बैटरी ऑप्टिमाइज़ेशन को अनदेखा करें';

  @override
  String get permBatteryWhy => 'ताकि फ़ोन बैकग्राउंड में ट्रैकिंग बंद न करे।';

  @override
  String get permGrant => 'अनुमति दें';

  @override
  String get permGranted => 'अनुमति दी गई';

  @override
  String get permSettings => 'सेटिंग्स खोलें';

  @override
  String get permLocationRequired =>
      'आगे बढ़ने के लिए लोकेशन की अनुमति ज़रूरी है।';

  @override
  String get gpsOff => 'GPS बंद है: फ़ोन की सेटिंग्स में इसे चालू करें।';

  @override
  String get obTitle => 'पंजीकरण पूरा करें';

  @override
  String get obIntro =>
      'अपनी जानकारी डालें और अपने दस्तावेज़ों और गाड़ी की फ़ोटो लें। कंपनी की जाँच से पहले कुछ भी आधिकारिक नहीं है।';

  @override
  String obRejected(String reason) {
    return 'आपका पंजीकरण वापस भेजा गया: $reason';
  }

  @override
  String get obStepData => 'जानकारी';

  @override
  String get obStepDocs => 'दस्तावेज़';

  @override
  String get obStepVehicle => 'गाड़ी';

  @override
  String get obStepReview => 'जाँच';

  @override
  String get civilId => 'सिविल आईडी';

  @override
  String get civilIdInvalid => 'सिविल आईडी में 12 अंक होते हैं';

  @override
  String get nationality => 'राष्ट्रीयता';

  @override
  String get docNumber => 'दस्तावेज़ संख्या';

  @override
  String get docExpiry => 'समाप्ति तिथि';

  @override
  String get docFront => 'आगे का भाग';

  @override
  String get docBack => 'पीछे का भाग';

  @override
  String get pickPhoto => 'फ़ोटो';

  @override
  String get takePhoto => 'फ़ोटो लें';

  @override
  String get fromGallery => 'गैलरी से';

  @override
  String get uploading => 'अपलोड हो रहा है…';

  @override
  String get required => 'ज़रूरी';

  @override
  String get plate => 'नंबर प्लेट';

  @override
  String get plateHint => 'जैसा प्लेट पर लिखा है, जैसे 18/23456';

  @override
  String get odometerKm => 'ओडोमीटर (कि.मी.)';

  @override
  String get odometerPhoto => 'ओडोमीटर की फ़ोटो';

  @override
  String get noVehicle => 'अभी मेरे पास कोई गाड़ी नहीं है';

  @override
  String get vehiclePhotos => 'गाड़ी की हालत की फ़ोटो';

  @override
  String get obSubmit => 'जाँच के लिए भेजें';

  @override
  String obMissing(String items) {
    return 'पूरा करें: $items';
  }

  @override
  String get obWaitingTitle => 'आपकी जानकारी की जाँच हो रही है';

  @override
  String get obWaitingText =>
      'मंज़ूरी मिलने पर या कुछ ठीक करना हो तो आपको WhatsApp संदेश मिलेगा।';

  @override
  String get refresh => 'रिफ़्रेश करें';

  @override
  String get position_front => 'आगे';

  @override
  String get position_back => 'पीछे';

  @override
  String get position_left => 'बायाँ हिस्सा';

  @override
  String get position_right => 'दायाँ हिस्सा';

  @override
  String get position_interior => 'अंदर का हिस्सा';

  @override
  String get position_other => 'अन्य';

  @override
  String get tabHome => 'होम';

  @override
  String get tabCash => 'कैश';

  @override
  String get tabAccount => 'खाता';

  @override
  String get noCustody => 'अभी कोई गाड़ी आपकी ज़िम्मेदारी में नहीं है';

  @override
  String get noCustodyHint =>
      'जब आपको कोई गाड़ी सौंपी जाएगी तो वह यहाँ दिखेगी और ट्रैकिंग अपने आप शुरू हो जाएगी।';

  @override
  String custodySince(String when) {
    return '$when से आपकी ज़िम्मेदारी में';
  }

  @override
  String lastKm(String km) {
    return 'आख़िरी रीडिंग: $km कि.मी.';
  }

  @override
  String get trackingOn => 'ट्रैकिंग चालू';

  @override
  String get trackingOff => 'ट्रैकिंग बंद';

  @override
  String trackingWaiting(String count) {
    return 'भेजने के लिए बाकी: $count';
  }

  @override
  String get startDay => 'दिन शुरू करें';

  @override
  String get startDayDone => 'दिन शुरू हो गया';

  @override
  String get endDay => 'दिन समाप्त करें';

  @override
  String get dailyReport => 'दैनिक रिपोर्ट';

  @override
  String get outboxTitle => 'भेजने के लिए बाकी';

  @override
  String get outboxQueued => 'नेटवर्क लौटने पर अपने आप भेजा जाएगा';

  @override
  String outboxFailed(String reason) {
    return 'स्वीकार नहीं हुआ: $reason';
  }

  @override
  String get outboxDiscard => 'हटाएँ';

  @override
  String get kind_odometer => 'ओडोमीटर रीडिंग';

  @override
  String get kind_report => 'दैनिक रिपोर्ट';

  @override
  String get startDayTitle => 'दिन की शुरुआत';

  @override
  String get endDayDone => 'दिन समाप्त हुआ';

  @override
  String get startAgain => 'फिर से शुरू करें';

  @override
  String reportAddsToDay(String orders) {
    return 'यह रिपोर्ट आज भेजी गई रिपोर्ट में जुड़ेगी ($orders ऑर्डर)। सिर्फ़ इस सत्र के ऑर्डर और कैश डालें।';
  }

  @override
  String reportSession(String n) {
    return 'सत्र $n';
  }

  @override
  String get endReadingIntro =>
      'आज की रिपोर्ट से पहले: दिन के अंत की ओडोमीटर फ़ोटो और रीडिंग। पहले रीडिंग जाएगी, फिर रिपोर्ट।';

  @override
  String get status_returned => 'सुधार के लिए वापस भेजा गया';

  @override
  String get editReportTitle => 'रिपोर्ट संपादित करें';

  @override
  String get changeReportTitle => 'मंज़ूर रिपोर्ट बदलने का अनुरोध करें';

  @override
  String get changeReportIntro =>
      'यह रिपोर्ट मंज़ूर हो चुकी है: आपका अनुरोध दफ़्तर जाएगा और मंज़ूरी के बाद लागू होगा।';

  @override
  String get changeReason => 'बदलाव का कारण';

  @override
  String get newScreenshotOptional => 'नया स्क्रीनशॉट (वैकल्पिक)';

  @override
  String get reportExistsForDay =>
      'आप इस दिन की रिपोर्ट पहले ही भेज चुके हैं। दूसरी भेजने के बजाय उसे संपादित करें।';

  @override
  String get editReport => 'रिपोर्ट संपादित करें';

  @override
  String get changePending => 'बदलाव दफ़्तर की मंज़ूरी का इंतज़ार कर रहा है';

  @override
  String returnedNote(Object note) {
    return 'दफ़्तर ने वापस भेजा: $note';
  }

  @override
  String get myCar => 'मेरी गाड़ी';

  @override
  String get carSince => 'आपकी ज़िम्मेदारी में कब से';

  @override
  String get lastReading => 'ओडोमीटर की आख़िरी रीडिंग';

  @override
  String get registrationExpiry => 'रजिस्ट्रेशन की समाप्ति';

  @override
  String get requestVehicleChange => 'दूसरी गाड़ी माँगें';

  @override
  String get vehicleChangeReason => 'कारण';

  @override
  String get vehicleChangePending =>
      'दूसरी गाड़ी का आपका अनुरोध सुपरवाइज़र के पास है';

  @override
  String vehicleChangeRejected(Object note) {
    return 'दूसरी गाड़ी का आपका अनुरोध अस्वीकार हुआ: $note';
  }

  @override
  String get profileTitle => 'मेरी जानकारी';

  @override
  String get employeeNumber => 'कर्मचारी संख्या';

  @override
  String get companyLabel => 'कंपनी';

  @override
  String get platformLabel => 'प्लेटफ़ॉर्म';

  @override
  String get bankLabel => 'बैंक';

  @override
  String get myDocuments => 'मेरे दस्तावेज़';

  @override
  String get docValid => 'मान्य';

  @override
  String docExpiring(Object days) {
    return '$days दिनों में समाप्त';
  }

  @override
  String get docExpired => 'समाप्त हो चुका';

  @override
  String get docMissing => 'रिकॉर्ड में नहीं';

  @override
  String docExpires(Object date) {
    return '$date को समाप्त';
  }

  @override
  String get uploadRenewal => 'नवीनीकृत दस्तावेज़ अपलोड करें';

  @override
  String get renewalPending =>
      'नवीनीकरण दफ़्तर की मंज़ूरी का इंतज़ार कर रहा है';

  @override
  String renewalRejected(Object note) {
    return 'नवीनीकरण अस्वीकार हुआ: $note';
  }

  @override
  String get newExpiry => 'नई समाप्ति तिथि';

  @override
  String get documentNumber => 'दस्तावेज़ संख्या (वैकल्पिक)';

  @override
  String get documentPhoto => 'दस्तावेज़ की फ़ोटो';

  @override
  String get pickDate => 'तारीख चुनें';

  @override
  String cashNearLimit(Object limit) {
    return 'आपका बैलेंस अलर्ट सीमा ($limit) के करीब है: जल्दी कैश जमा करें।';
  }

  @override
  String get movements => 'लेन-देन';

  @override
  String get noMovements => 'अभी कोई लेन-देन नहीं';

  @override
  String get moveCollection => 'दैनिक रिपोर्ट का कैश';

  @override
  String get moveReceipt => 'रसीद के साथ जमा किया';

  @override
  String get moveAdjustment => 'सुधार';

  @override
  String get moveReversal => 'रिवर्सल';

  @override
  String get moveSettlement => 'सेवा समाप्ति का निपटान';

  @override
  String get moveOpening => 'शुरुआती बैलेंस';

  @override
  String get endDayTitle => 'दिन का अंत';

  @override
  String get odometerIntro =>
      'ओडोमीटर की साफ़ फ़ोटो लें, फिर फ़ोटो में दिख रही रीडिंग लिखें।';

  @override
  String get retake => 'फिर से लें';

  @override
  String kmLower(String km) {
    return 'आख़िरी रीडिंग ($km कि.मी.) से कम है। जाँच लें: इसकी समीक्षा होगी।';
  }

  @override
  String get kmInvalid => 'रीडिंग अंकों में लिखें';

  @override
  String get photoRequired => 'फ़ोटो ज़रूरी है';

  @override
  String get sentTitle => 'भेज दिया गया';

  @override
  String get queuedTitle => 'फ़ोन पर सेव किया गया';

  @override
  String get sentText => 'कंपनी को मिल गया।';

  @override
  String get queuedText =>
      'अभी नेटवर्क नहीं है। कनेक्शन लौटने पर यह अपने मूल समय के साथ अपने आप भेजा जाएगा।';

  @override
  String get reportTitle => 'दैनिक रिपोर्ट';

  @override
  String get reportDate => 'काम का दिन';

  @override
  String get today => 'आज';

  @override
  String get yesterday => 'कल';

  @override
  String get dayBefore => 'परसों';

  @override
  String get ordersCount => 'ऑर्डर';

  @override
  String get cashAmount => 'वसूला गया कैश';

  @override
  String get cashInvalid => 'अधिकतम तीन दशमलव वाली राशि';

  @override
  String get screenshot => 'डिलीवरी ऐप से दिन के सारांश का स्क्रीनशॉट';

  @override
  String get notes => 'टिप्पणी';

  @override
  String get recentReports => 'हाल की रिपोर्टें';

  @override
  String get status_submitted => 'जाँच का इंतज़ार';

  @override
  String get status_approved => 'मंज़ूर';

  @override
  String get status_rejected => 'अस्वीकृत';

  @override
  String approvedCash(String amount) {
    return 'मंज़ूर: $amount';
  }

  @override
  String get cashTitle => 'कैश';

  @override
  String get cashTotal => 'आपके पास कैश';

  @override
  String get cashPosted => 'मंज़ूर';

  @override
  String get cashPending => 'जाँच का इंतज़ार';

  @override
  String cashOverLimit(String limit) {
    return 'सीमा ($limit) से ज़्यादा: कैश कैशियर को सौंपें।';
  }

  @override
  String get receipts => 'रसीदें';

  @override
  String receiptNo(String no) {
    return 'रसीद संख्या $no';
  }

  @override
  String get confirmReceipt => 'मैं पुष्टि करता हूँ';

  @override
  String get receiptConfirmed => 'पुष्टि हो गई';

  @override
  String confirmReceiptQ(String amount) {
    return 'क्या आपने कैशियर को $amount KWD सौंपे?';
  }

  @override
  String get noReceipts => 'अभी कोई रसीद नहीं';

  @override
  String get language => 'भाषा';

  @override
  String get trackingDetails => 'ट्रैकिंग की स्थिति';

  @override
  String lastUpload(String when) {
    return 'आख़िरी बार भेजा: $when';
  }

  @override
  String get never => 'अभी नहीं';

  @override
  String appVersion(String version) {
    return 'संस्करण $version';
  }

  @override
  String get signOut => 'साइन आउट';

  @override
  String get signOutQ =>
      'ट्रैकिंग बंद हो जाएगी और साइन इन करने के लिए नए एक्टिवेशन की ज़रूरत होगी। जारी रखें?';

  @override
  String get blockedTitle => 'आपका खाता निलंबित है';

  @override
  String get blockedText => 'अपने सुपरवाइज़र से संपर्क करें।';

  @override
  String get obReady => 'सब तैयार है: जाँच के लिए भेजें।';

  @override
  String get maintenance => 'मेंटेनेंस';

  @override
  String get maintenanceTitle => 'मेंटेनेंस अनुरोध';

  @override
  String get kind_maintenance => 'मेंटेनेंस अनुरोध';

  @override
  String get mntNew => 'नया मेंटेनेंस अनुरोध';

  @override
  String get mntIntro =>
      'समस्या बताएँ और फ़ोटो लें। दुर्घटना वाली गाड़ी की मरम्मत दफ़्तर के ज़रिए होती है।';

  @override
  String get mntDirectIntro =>
      'समस्या बताएँ, फ़ोटो लें, और वह मेंटेनेंस सेंटर चुनें जहाँ आप गाड़ी ले जाएँगे। अनुरोध सीधे सेंटर जाता है, गाड़ी आपकी ज़िम्मेदारी में रहती है, और तैयार होने पर आपको बताया जाएगा।';

  @override
  String get mntCenter => 'मेंटेनेंस सेंटर';

  @override
  String get mntPickedUp => 'मैंने गाड़ी ले ली';

  @override
  String get pickupTitle => 'सेंटर से गाड़ी लेना';

  @override
  String get pickupIntro =>
      'गाड़ी लेते समय ओडोमीटर की फ़ोटो लें और रीडिंग डालें: गाड़ी आपकी ज़िम्मेदारी में लौट आती है और आप हमेशा की तरह अपना दिन शुरू करते हैं।';

  @override
  String get kind_pickup => 'मेंटेनेंस से गाड़ी ली गई';

  @override
  String get mntNoVehicle =>
      'मेंटेनेंस आपकी ज़िम्मेदारी वाली गाड़ी के लिए माँगा जाता है। अभी आपके पास कोई गाड़ी नहीं है।';

  @override
  String get mntKind => 'प्रकार';

  @override
  String get mntDescription => 'क्या खराबी है';

  @override
  String get mntOdometer => 'ओडोमीटर (वैकल्पिक)';

  @override
  String get mntPhotos => 'फ़ोटो (अधिकतम 4)';

  @override
  String get mntAddPhoto => 'फ़ोटो';

  @override
  String get mntNone => 'कोई मेंटेनेंस अनुरोध नहीं';

  @override
  String mntRequestNo(String number) {
    return 'अनुरोध #$number';
  }

  @override
  String mntAtCenter(String center) {
    return 'सेंटर: $center';
  }

  @override
  String mntReadyBanner(String plate, String center) {
    return 'आपकी गाड़ी $plate $center पर लेने के लिए तैयार है';
  }

  @override
  String mntRejected(String reason) {
    return 'अस्वीकृत: $reason';
  }

  @override
  String get mntSent => 'आपका मेंटेनेंस अनुरोध सेंटर को भेज दिया गया';

  @override
  String get mntKind_periodic => 'नियमित सर्विस';

  @override
  String get mntKind_mechanical => 'मैकेनिकल';

  @override
  String get mntKind_electrical => 'इलेक्ट्रिकल';

  @override
  String get mntKind_tyres => 'टायर';

  @override
  String get mntKind_battery => 'बैटरी';

  @override
  String get mntKind_ac => 'एयर कंडीशनिंग';

  @override
  String get mntKind_bodywork => 'बॉडीवर्क';

  @override
  String get mntKind_other => 'अन्य';

  @override
  String get mntStatus_requested => 'मंज़ूरी का इंतज़ार';

  @override
  String get mntStatus_approved => 'मंज़ूर';

  @override
  String get mntStatus_rejected => 'अस्वीकृत';

  @override
  String get mntStatus_referred => 'सेंटर भेजा गया';

  @override
  String get mntStatus_at_center => 'सेंटर पर';

  @override
  String get mntStatus_ready => 'लेने के लिए तैयार';

  @override
  String get mntStatus_picked_up => 'ले ली गई';

  @override
  String get mntStatus_closed => 'बंद';

  @override
  String get mntStatus_cancelled => 'रद्द';

  @override
  String get mntTapToRemove => 'हटाने के लिए टैप करें';

  @override
  String get accident => 'दुर्घटना की रिपोर्ट करें';

  @override
  String get accidentsTitle => 'दुर्घटनाएँ';

  @override
  String get kind_accident => 'दुर्घटना रिपोर्ट';

  @override
  String get kind_police_report => 'पुलिस रिपोर्ट';

  @override
  String get accNew => 'नई दुर्घटना रिपोर्ट';

  @override
  String get accEmergency => 'अगर कोई घायल है, तो पहले 112 पर कॉल करें।';

  @override
  String get accIntro =>
      'गाड़ी की कई तरफ़ से फ़ोटो लें: आगे, पीछे, दोनों तरफ़ और नुकसान। समय और जगह अपने आप दर्ज होते हैं।';

  @override
  String get accNoVehicle =>
      'दुर्घटना की रिपोर्ट आपके पास की गाड़ी के लिए होती है। अभी आपके पास कोई गाड़ी नहीं है: अपने सुपरवाइज़र को कॉल करें।';

  @override
  String get accDescription => 'क्या हुआ?';

  @override
  String get accInjuries => 'कोई घायल है';

  @override
  String get accInjuriesNote => 'चोट का विवरण';

  @override
  String get accOtherParty => 'दूसरा पक्ष (प्लेट, नाम, बीमा कंपनी)';

  @override
  String accPhotos(String min) {
    return 'दुर्घटना की फ़ोटो (कम से कम $min)';
  }

  @override
  String accPhotosNeeded(String min) {
    return 'अलग-अलग कोणों से कम से कम $min फ़ोटो लें';
  }

  @override
  String get accPoliceReport => 'पुलिस रिपोर्ट';

  @override
  String get accPoliceReportNo => 'रिपोर्ट संख्या';

  @override
  String get accPoliceLater =>
      'अभी रिपोर्ट नहीं है? अभी भेजें और पुलिस रिपोर्ट की फ़ोटो बाद में नीचे अपनी दुर्घटनाओं से भेजें।';

  @override
  String get accSendPolice => 'पुलिस रिपोर्ट भेजें';

  @override
  String get accNone => 'कोई दुर्घटना नहीं';

  @override
  String accNo(String number) {
    return 'दुर्घटना #$number';
  }

  @override
  String get accStage_review => 'जाँच में';

  @override
  String get accStage_outcome => 'ज़िम्मेदारी के फ़ैसले का इंतज़ार';

  @override
  String get accStage_recorded => 'ज़िम्मेदारी तय हो गई';

  @override
  String get accStage_closed => 'बंद';

  @override
  String get accLiability_none => 'आप ज़िम्मेदार नहीं हैं';

  @override
  String get accLiability_driver => 'आप ज़िम्मेदार हैं';

  @override
  String accLiability_shared(String percent) {
    return 'साझा ज़िम्मेदारी: आपका हिस्सा $percent%';
  }

  @override
  String accDeduction(String total, String count) {
    return 'कटौती $total KWD · किस्तें: $count';
  }

  @override
  String accInstallment(String month, String amount) {
    return '$month: $amount KWD';
  }

  @override
  String accAwaitingPolice(String number) {
    return 'दुर्घटना #$number पुलिस रिपोर्ट का इंतज़ार कर रही है: उसकी फ़ोटो भेजने के लिए टैप करें';
  }

  @override
  String get fines => 'ट्रैफ़िक जुर्माने';

  @override
  String get finesTitle => 'ट्रैफ़िक जुर्माने';

  @override
  String get finesIntro =>
      'गाड़ी आपके पास रहते हुए लगे जुर्माने, जुर्माने के समय के अनुसार। कंपनी तय करती है: वह उन्हें भरती है, या वे आपकी तनख्वाह से किस्तों में काटे जाते हैं।';

  @override
  String get finesNone => 'कोई जुर्माना नहीं';

  @override
  String get fineStatus_open => 'जाँच में';

  @override
  String get fineStatus_charged => 'आपकी तनख्वाह से काटा गया';

  @override
  String get fineStatus_company => 'कंपनी ने भरा';

  @override
  String get monthlyStatement => 'प्लेटफ़ॉर्म का मासिक विवरण';

  @override
  String get payslips => 'वेतन पर्ची';

  @override
  String get statementTitle => 'प्लेटफ़ॉर्म का मासिक विवरण';

  @override
  String statementIntro(String platform) {
    return 'हर महीने की शुरुआत में $platform ऐप से महीने के सारांश के स्क्रीनशॉट भेजें और आँकड़े वैसे ही लिखें जैसे दिखते हैं। दफ़्तर वेतन से पहले उन्हें स्क्रीनशॉट से मिलाता है।';
  }

  @override
  String get statementNoPlatform =>
      'आपका प्लेटफ़ॉर्म अभी तय नहीं है। दफ़्तर से संपर्क करें।';

  @override
  String get statementNoMonth =>
      'आपने सभी खुले महीने भेज दिए हैं। दफ़्तर की जाँच का इंतज़ार करें।';

  @override
  String get statementMonth => 'महीना';

  @override
  String get statementShots => 'प्लेटफ़ॉर्म ऐप के स्क्रीनशॉट (अधिकतम 6)';

  @override
  String get statementShotRequired => 'कम से कम एक स्क्रीनशॉट जोड़ें';

  @override
  String get statementHistory => 'आपने क्या भेजा';

  @override
  String statementSentDays(String days) {
    return 'भेजा गया: $days मान्य दिन';
  }

  @override
  String statementApprovedDays(String days) {
    return 'मंज़ूर: $days मान्य दिन';
  }

  @override
  String get statementStatus_submitted => 'जाँच का इंतज़ार';

  @override
  String get statementStatus_approved => 'मंज़ूर';

  @override
  String get statementStatus_rejected => 'अस्वीकृत: फिर से भेजें';

  @override
  String get addShot => 'स्क्रीनशॉट जोड़ें';

  @override
  String get validDays => 'मान्य दिन';

  @override
  String get ordersTotal => 'कुल ऑर्डर';

  @override
  String get hoursTotal => 'कुल घंटे';

  @override
  String get payslipsTitle => 'वेतन पर्ची';

  @override
  String get payslipsNone => 'अभी कोई मंज़ूर वेतन पर्ची नहीं';

  @override
  String get payslipNet => 'कुल शुद्ध वेतन';

  @override
  String get payslipStatus_approved => 'मंज़ूर';

  @override
  String get payslipStatus_paid => 'भुगतान हो गया';

  @override
  String get iban => 'IBAN';

  @override
  String get ibanHint =>
      'आपकी तनख्वाह इसी में आती है: इसे अपने बैंक के ऐप से कॉपी करें';

  @override
  String get bankName => 'बैंक का नाम';

  @override
  String get civilSignIn => 'सिविल आईडी से साइन इन करें';

  @override
  String get civilSignInHint =>
      'अगर कंपनी के पास आपका फ़ोन नंबर नहीं है: अपनी सिविल आईडी और दफ़्तर से मिले शुरुआती पासवर्ड से साइन इन करें, फिर अपना फ़ोन दर्ज करें। पासवर्ड एक ही बार काम करता है।';

  @override
  String get initialPassword => 'शुरुआती पासवर्ड';

  @override
  String get claimContinue => 'जारी रखें';

  @override
  String claimWelcome(String name) {
    return 'स्वागत है $name। अपना वह फ़ोन नंबर डालें जिस पर WhatsApp है: कोड उसी पर जाएगा, और अब से आप उसी से साइन इन करेंगे।';
  }

  @override
  String get password => 'पासवर्ड';

  @override
  String get civilSignInOnly =>
      'अपनी सिविल आईडी और पासवर्ड से साइन इन करें। पहली बार: दफ़्तर से मिला शुरुआती पासवर्ड, फिर आप अपना पासवर्ड चुनेंगे।';

  @override
  String get forgotPassword =>
      'पासवर्ड भूल गए? अपने सुपरवाइज़र से नया शुरुआती पासवर्ड माँगें।';

  @override
  String choosePassword(String name) {
    return 'स्वागत है $name। अपना पासवर्ड चुनें: इससे और अपनी सिविल आईडी से अब आप किसी भी फ़ोन पर साइन इन करेंगे। कम से कम 8 अक्षर, शुरुआती पासवर्ड या सिविल आईडी नहीं, और किसी को न बताएँ।';
  }

  @override
  String get newPassword => 'नया पासवर्ड';

  @override
  String get confirmPassword => 'पासवर्ड फिर से लिखें';

  @override
  String get passwordTooShort => 'कम से कम 8 अक्षर';

  @override
  String get passwordsDiffer => 'दोनों पासवर्ड अलग हैं';

  @override
  String get passwordIsCivilId => 'अपनी सिविल आईडी को पासवर्ड न बनाएँ';

  @override
  String get saveAndSignIn => 'सेव करें और साइन इन करें';

  @override
  String get validDayQuestion =>
      'क्या प्लेटफ़ॉर्म के ऐप ने इस दिन को मान्य गिना?';

  @override
  String get validDayYes => 'मान्य दिन';

  @override
  String get validDayNo => 'मान्य नहीं';

  @override
  String get paySchemes => 'वेतन योजना';

  @override
  String get schemesIntro =>
      'आपकी योजना तय करती है कि आपके ऑर्डर से आपकी तनख्वाह कैसे बनती है। आप अपने प्लेटफ़ॉर्म की कोई दूसरी योजना माँग सकते हैं; दफ़्तर के मानने पर वह अगले महीने की पहली तारीख से शुरू होती है।';

  @override
  String get schemeNow => 'इस महीने आपकी योजना';

  @override
  String get schemeNone => 'दफ़्तर ने अभी आपकी योजना तय नहीं की है';

  @override
  String schemeNextMonth(String name) {
    return 'अगले महीने से: $name';
  }

  @override
  String get schemeOthers => 'आपके प्लेटफ़ॉर्म की दूसरी योजनाएँ';

  @override
  String get schemeAsk => 'यह योजना माँगें';

  @override
  String schemeAskBody(String name, String month) {
    return 'आप $month से “$name” माँग रहे हैं। दफ़्तर इसकी जाँच करेगा और आपको जवाब यहाँ और WhatsApp पर मिलेगा।';
  }

  @override
  String get schemeNoteHint => 'दफ़्तर के लिए टिप्पणी (वैकल्पिक)';

  @override
  String get schemeSend => 'अनुरोध भेजें';

  @override
  String get schemeSent => 'आपका अनुरोध दफ़्तर को भेज दिया गया';

  @override
  String schemePending(String name, String month) {
    return '$month से “$name” के लिए आपका अनुरोध दफ़्तर के पास लंबित है';
  }

  @override
  String schemeApproved(String name, String month) {
    return 'मंज़ूर: $month से “$name”';
  }

  @override
  String schemeRejected(String name, String note) {
    return 'दफ़्तर ने “$name” अस्वीकार किया: $note';
  }

  @override
  String get schemeCancel => 'अनुरोध रद्द करें';

  @override
  String schemePerOrder(String rate) {
    return 'प्रति ऑर्डर: $rate KWD';
  }

  @override
  String get schemeBatchRates =>
      'महीने के बैच स्तर के अनुसार प्रति ऑर्डर कीमत:';

  @override
  String schemeBatchRow(String level, String rate) {
    return 'बैच $level: $rate KWD';
  }

  @override
  String schemeReduced(String rate, String marks) {
    return 'अगर आप कोई Star Day चूकते हैं या $marks अंक तक पहुँचते हैं, तो महीने के हर ऑर्डर का भाव $rate KWD हो जाता है';
  }

  @override
  String schemeReducedStar(String rate) {
    return 'अगर आप कोई Star Day चूकते हैं, तो महीने के हर ऑर्डर का भाव $rate KWD हो जाता है';
  }

  @override
  String get schemeReducedLoses => 'घटाए गए महीने में स्तर बोनस नहीं मिलता';

  @override
  String get schemeTiers =>
      'स्तर बोनस (सिर्फ़ सबसे ऊँचा स्तर जहाँ तक आप पहुँचते हैं):';

  @override
  String schemeTierRow(String orders, String amount) {
    return '$orders ऑर्डर: $amount KWD';
  }

  @override
  String get schemeMarks => 'हाज़िरी अंकों की कटौती:';

  @override
  String schemeMarkRow(String marks, String amount) {
    return '$marks अंक: $amount KWD';
  }

  @override
  String schemeTarget(String orders, String days) {
    return 'लक्ष्य: हर महीने $orders ऑर्डर और $days मान्य दिन';
  }

  @override
  String schemeMissing(String rate) {
    return 'लक्ष्य से कम हर ऑर्डर पर $rate KWD कटते हैं';
  }

  @override
  String get schemeNoMissing => 'लक्ष्य से कम ऑर्डर पर कोई कटौती नहीं';

  @override
  String schemeCovers(String items) {
    return 'कंपनी भुगतान करती है: $items';
  }

  @override
  String get schemeCoversNone =>
      'खर्च आप भरते हैं: मेंटेनेंस, रहना, पेट्रोल और सिम';

  @override
  String get schemePlatformRates =>
      'प्लेटफ़ॉर्म का अपना नियम: मूल वेतन और कंपनी की दरें';

  @override
  String get expense_maintenance => 'मेंटेनेंस';

  @override
  String get expense_housing => 'रहना';

  @override
  String get expense_gas => 'पेट्रोल';

  @override
  String get expense_sim => 'सिम';

  @override
  String get schemeChoose => 'वेतन योजना';

  @override
  String get schemeChooseHint =>
      'वह योजना चुनें जिस पर आप काम करते हैं। दफ़्तर आपके पंजीकरण के साथ इसकी जाँच करेगा, और आप बाद में ऐप से इसे बदलने का अनुरोध कर सकते हैं।';

  @override
  String payslipScheme(String name) {
    return 'आपकी योजना से महीने का हिसाब: $name';
  }

  @override
  String get payItem_orders_pay => 'ऑर्डर';

  @override
  String get payItem_tier_bonus => 'स्तर बोनस';

  @override
  String get payItem_missing_target => 'लक्ष्य से कमी';

  @override
  String get payItem_marks_deduction => 'हाज़िरी अंक';

  @override
  String get payItem_uncovered_penalty => 'न काटी गई कटौतियाँ (जाँच के लिए)';

  @override
  String payWhyOrders(String orders, String rate) {
    return '$orders ऑर्डर × $rate KWD';
  }

  @override
  String payWhyBatch(String level) {
    return 'बैच $level';
  }

  @override
  String get payWhyReducedStar => 'घटा हुआ भाव: एक Star Day छूटा';

  @override
  String get payWhyReducedMarks => 'घटा हुआ भाव: हाज़िरी अंक';

  @override
  String payWhyTier(String orders, String from) {
    return '$orders ऑर्डर: $from वाला स्तर';
  }

  @override
  String payWhyMissing(String missing, String target, String rate) {
    return '$target से $missing ऑर्डर कम × $rate KWD';
  }

  @override
  String payWhyMarks(String marks) {
    return '$marks हाज़िरी अंक';
  }

  @override
  String get payWhyUncovered =>
      'महीने के वेतन से ज़्यादा कटौतियाँ नहीं काटी जातीं, शुद्ध वेतन कभी शून्य से नीचे नहीं जाता: बाकी की जाँच दफ़्तर करता है';

  @override
  String get noticesTitle => 'सूचनाएँ';

  @override
  String get noticesNone => 'अभी कोई सूचना नहीं';

  @override
  String get nameLabel => 'नाम';

  @override
  String get obOnFile =>
      'लॉक किए गए फ़ील्ड कंपनी के रिकॉर्ड में हैं। अगर कोई गलत है, तो दफ़्तर से उसे ठीक करने को कहें।';

  @override
  String get nationalityPick => 'अपनी राष्ट्रीयता चुनें';

  @override
  String get searchArEn => 'अरबी या अंग्रेज़ी में खोजें';

  @override
  String get noMatches => 'कोई मिलान नहीं';

  @override
  String get ibanInvalid =>
      'इस IBAN में कोई अक्षर गलत है (जाँच अंक मेल नहीं खाते): इसे अपने बैंक के ऐप से कॉपी करें';

  @override
  String obFieldsInvalid(String fields) {
    return 'ये फ़ील्ड जाँचें: $fields';
  }

  @override
  String ibanLengthKw(int count) {
    return 'कुवैती IBAN में KW से शुरू होने वाले 30 अक्षर होते हैं; इसमें $count हैं';
  }

  @override
  String get driverWorking => 'ड्राइवर काम पर है';

  @override
  String get driverNotWorking => 'ड्राइवर काम पर नहीं है';

  @override
  String greeting(String name) {
    return 'नमस्ते, $name';
  }

  @override
  String get yourCar => 'आपकी गाड़ी';

  @override
  String get quickActions => 'त्वरित काम';

  @override
  String get dayNotStarted => 'आपने अपना दिन शुरू नहीं किया है';

  @override
  String get dayNotStartedHint => 'कैमरे से ओडोमीटर की फ़ोटो लेकर शुरू करें';

  @override
  String dayStartedAt(String time) {
    return 'आपका दिन $time बजे शुरू हुआ';
  }

  @override
  String dayStartKm(String km) {
    return 'शुरुआती ओडोमीटर $km';
  }

  @override
  String get dayEndedHint => 'आज फिर काम कर रहे हैं? फिर से शुरू करें';

  @override
  String get agoNow => 'अभी-अभी';

  @override
  String agoMinutes(String n) {
    return '$n मिनट पहले';
  }

  @override
  String agoHours(String n) {
    return '$n घंटे पहले';
  }

  @override
  String agoDays(String n) {
    return '$n दिन पहले';
  }

  @override
  String lastSentAgo(String ago) {
    return 'आख़िरी बार भेजा $ago';
  }

  @override
  String get qaBalance => 'मेरा बैलेंस';

  @override
  String get qaReceipts => 'मेरी रसीदें';

  @override
  String qaReceiptsWaiting(String n) {
    return '$n पुष्टि के लिए';
  }

  @override
  String get qaReceiptsDone => 'सबकी पुष्टि हो गई';

  @override
  String get qaMaintenanceSub => 'कोई खराबी या टिप्पणी';

  @override
  String get qaAccidentSub => 'फ़ोटो + पुलिस रिपोर्ट';

  @override
  String get qaReportSub => 'आज के ऑर्डर और कैश';

  @override
  String get qaFinesSub => 'आपकी गाड़ी पर जुर्माने';

  @override
  String get qaStatementSub => 'प्लेटफ़ॉर्म के मासिक स्क्रीनशॉट';

  @override
  String get qaPayslipsSub => 'आपका मासिक वेतन';

  @override
  String get qaSchemesSub => 'आपका वेतन कैसे बनता है';

  @override
  String get tabWork => 'रोज़ का काम';

  @override
  String get todayReport => 'आज की रिपोर्ट';

  @override
  String get workReportSent => 'आज की रिपोर्ट भेज दी गई';

  @override
  String get workReportDue => 'आज की रिपोर्ट अभी नहीं भेजी गई';

  @override
  String get workReportDueHint =>
      'प्लेटफ़ॉर्म के ऐप में दिखे अनुसार ऑर्डर और कैश भेजें';

  @override
  String get sendDailyReport => 'दैनिक रिपोर्ट भेजें';

  @override
  String ordersCash(String orders, String cash) {
    return '$orders ऑर्डर · $cash';
  }

  @override
  String get myRequests => 'मेरे अनुरोध';

  @override
  String get cashBalanceTitle => 'आपका बैलेंस (KWD)';

  @override
  String cashPendingPart(String amount) {
    return 'इसमें से $amount अभी मंज़ूर नहीं';
  }

  @override
  String cashLimit(String amount) {
    return 'अलर्ट सीमा $amount';
  }

  @override
  String employeeAt(String number, String company) {
    return '$number · $company';
  }

  @override
  String get thisPhone => 'यह फ़ोन';

  @override
  String get takeOdometerPhoto => 'ओडोमीटर की फ़ोटो लें';

  @override
  String get cameraOnly => 'सिर्फ़ कैमरा — गैलरी की अनुमति नहीं है';

  @override
  String lastKmHint(String km) {
    return 'गाड़ी की आख़िरी दर्ज रीडिंग: $km';
  }

  @override
  String get cashHint => 'जैसा डिलीवरी कंपनी के ऐप में दिखता है';

  @override
  String get mntDescriptionHint => 'जैसे ब्रेक लगाते समय आवाज़';

  @override
  String get accSend => 'रिपोर्ट भेजें';

  @override
  String get workReportQueued => 'आज की रिपोर्ट फ़ोन पर सेव है';

  @override
  String get reportQueuedForDay =>
      'इस दिन की रिपोर्ट फ़ोन पर सेव है और कनेक्शन लौटने पर अपने आप चली जाएगी। इसे दोबारा न भेजें।';

  @override
  String ordersN(String n) {
    return '$n ऑर्डर';
  }

  @override
  String get workReportDueHintDays =>
      'ऑर्डर भेजें और बताएँ कि दिन मान्य गिना गया या नहीं';

  @override
  String get qaReportSubDays => 'आज के ऑर्डर और मान्य दिन';

  @override
  String get notSentYet => 'अभी नहीं भेजा गया';

  @override
  String get fuel => 'ईंधन';

  @override
  String get qaFuelSub => 'कैश से दिया गया ईंधन';

  @override
  String get fuelTitle => 'कैश से दिया गया ईंधन';

  @override
  String get fuelIntro =>
      'ईंधन की रसीद की फ़ोटो लें और राशि डालें। आपका कैश मिलने पर अकाउंटेंट इसकी जाँच करता है; मंज़ूरी के बाद यह राशि आपके पास के कैश से घट जाती है।';

  @override
  String get fuelReceipt => 'ईंधन रसीद की फ़ोटो';

  @override
  String get fuelTakeReceipt => 'रसीद की फ़ोटो लें';

  @override
  String get fuelReceiptMissing => 'रसीद की फ़ोटो ज़रूरी है';

  @override
  String get fuelAmount => 'भुगतान की गई राशि';

  @override
  String get fuelAmountInvalid => 'राशि KWD में डालें, अधिकतम 3 दशमलव';

  @override
  String fuelAmountMax(String max) {
    return 'एक रसीद अधिकतम $max KWD की हो सकती है';
  }

  @override
  String get fuelOdometer => 'ओडोमीटर रीडिंग (वैकल्पिक)';

  @override
  String get fuelNotes => 'टिप्पणी (वैकल्पिक)';

  @override
  String get fuelSend => 'जाँच के लिए भेजें';

  @override
  String get fuelMine => 'ईंधन रसीदें';

  @override
  String get fuelNone => 'अभी कोई ईंधन रसीद नहीं';

  @override
  String get fuelPending => 'जाँच का इंतज़ार';

  @override
  String fuelApproved(String amount) {
    return 'मंज़ूर ($amount)';
  }

  @override
  String get fuelRejected => 'अस्वीकृत';

  @override
  String get fuelOff_fuel_card =>
      'आपके पास कंपनी का फ़्यूल कार्ड है: दफ़्तर उसे रिचार्ज करता है, और ईंधन आपके कैश से नहीं लिया जाता।';

  @override
  String get fuelOff_not_covered =>
      'आपकी वेतन योजना में ईंधन आपकी ज़िम्मेदारी है, इसलिए इसका खर्च कंपनी पर नहीं डाला जाता।';

  @override
  String get fuelOff_no_vehicle =>
      'अभी कोई गाड़ी आपकी ज़िम्मेदारी में नहीं है: ईंधन आपके पास की गाड़ी के लिए दर्ज होता है।';

  @override
  String get kind_fuel => 'ईंधन रसीद';

  @override
  String get moveFuel => 'ईंधन';

  @override
  String get vehicleChangePlate => 'दूसरी गाड़ी का नंबर प्लेट';

  @override
  String get vehicleChangePlateHint => '12-34567';

  @override
  String vehicleChangePendingFor(String plate) {
    return '$plate में बदलने के आपके अनुरोध की जाँच हो रही है';
  }

  @override
  String get claimVehicle => 'नई गाड़ी दर्ज करें';

  @override
  String get claimVehicleHint =>
      'गाड़ी ली है? उसे ओडोमीटर रीडिंग के साथ यहाँ दर्ज करें; दफ़्तर की मंज़ूरी पर आपकी ज़िम्मेदारी शुरू होती है।';

  @override
  String get claimTitle => 'नई गाड़ी दर्ज करें';

  @override
  String get claimPlate => 'गाड़ी का नंबर प्लेट';

  @override
  String get claimIntro =>
      'कैमरे से ओडोमीटर की फ़ोटो लें और रीडिंग डालें। अनुरोध दफ़्तर जाता है; मंज़ूरी के बाद फ़ोटो के समय से गाड़ी आपकी है।';

  @override
  String get claimConditionPhotos => 'गाड़ी की हालत की फ़ोटो (वैकल्पिक)';

  @override
  String get claimSend => 'दफ़्तर को भेजें';

  @override
  String claimPending(String plate) {
    return 'गाड़ी $plate लेने का आपका अनुरोध दफ़्तर की मंज़ूरी का इंतज़ार कर रहा है';
  }

  @override
  String claimRejected(String plate, String reason) {
    return 'दफ़्तर ने गाड़ी $plate लेने का आपका अनुरोध अस्वीकार किया: $reason';
  }

  @override
  String get kind_vehicle_claim => 'गाड़ी का पंजीकरण';

  @override
  String get mntNoCenter =>
      'कोई मेंटेनेंस सेंटर उपलब्ध नहीं है: दफ़्तर को कॉल करें';

  @override
  String mntInMaintenance(String center) {
    return 'आपकी गाड़ी मेंटेनेंस सेंटर पर है: $center';
  }

  @override
  String get mntInMaintenanceAny => 'आपकी गाड़ी मेंटेनेंस सेंटर पर है';

  @override
  String get mntInMaintenanceHint =>
      'गाड़ी अभी भी आपकी ज़िम्मेदारी में है, लेकिन जब तक आप उसे सेंटर से लेकर यहाँ पुष्टि नहीं करते, उससे कोई काम का दिन शुरू नहीं होगा।';

  @override
  String get fieldYes => 'हाँ';

  @override
  String get fieldNo => 'नहीं';

  @override
  String get fieldInvalid => 'अमान्य मान';

  @override
  String get choose => 'चुनें';

  @override
  String get objectPayslip => 'इस वेतन पर्ची पर आपत्ति करें';

  @override
  String get objectLine => 'इस पंक्ति पर आपत्ति करें';

  @override
  String get objectionTitle => 'वेतन पर्ची पर आपत्ति';

  @override
  String objectionOn(String what) {
    return 'विषय: $what';
  }

  @override
  String get objectionWhole => 'पूरी वेतन पर्ची';

  @override
  String get objectionReason => 'आप आपत्ति क्यों कर रहे हैं';

  @override
  String get objectionReasonShort => 'कारण लिखें (कम से कम 3 अक्षर)';

  @override
  String get objectionFile => 'इसे दिखाने वाली फ़ोटो (वैकल्पिक)';

  @override
  String get objectionCamera => 'कैमरा';

  @override
  String get objectionGallery => 'गैलरी';

  @override
  String get objectionSent => 'आपकी आपत्ति भेज दी गई; दफ़्तर जवाब देगा';

  @override
  String get objectionQueued => 'कनेक्शन लौटने पर आपकी आपत्ति भेजी जाएगी';

  @override
  String get myObjections => 'मेरी आपत्तियाँ';

  @override
  String objectionResponse(String text) {
    return 'दफ़्तर: $text';
  }

  @override
  String objectionAction(String text) {
    return 'की गई कार्रवाई: $text';
  }

  @override
  String get objectionStatus_open => 'खुली';

  @override
  String get objectionStatus_in_review => 'जाँच में';

  @override
  String get objectionStatus_accepted => 'स्वीकृत';

  @override
  String get objectionStatus_rejected => 'अस्वीकृत';

  @override
  String get objectionStatus_closed => 'बंद';

  @override
  String get objectionInstallment => 'एक किस्त';

  @override
  String vehicleChangeApprovedFor(String plate) {
    return '$plate में आपका बदलाव मंज़ूर हुआ: उसे दफ़्तर से लें';
  }

  @override
  String get receiptReversed => 'रद्द';

  @override
  String pickupReplacementTitle(String plate) {
    return 'बदले की गाड़ी $plate';
  }

  @override
  String get pickupReplacementHint =>
      'अपनी गाड़ी लेते समय इसे लौटाएँ: इसके ओडोमीटर की फ़ोटो लें और रीडिंग डालें।';

  @override
  String get pickupReplacementPhoto => 'बदले की गाड़ी के ओडोमीटर की फ़ोटो';

  @override
  String get fuelLitres => 'लीटर (वैकल्पिक)';

  @override
  String get fuelLitresInvalid => 'रसीद के अनुसार लीटर डालें (अधिकतम 500)';

  @override
  String get fuelLitresUnit => 'ली.';

  @override
  String get replacementCar => 'बदले की गाड़ी — आपकी गाड़ी सेंटर पर है';

  @override
  String outboxAttention(String reason) {
    return 'आपका ध्यान चाहिए: $reason';
  }

  @override
  String get outboxTooOld => 'दो दिन से नहीं भेजा गया';

  @override
  String get outboxKeptFailing => 'सर्वर इसे स्वीकार नहीं कर सका';

  @override
  String outboxAttentionCount(int n) {
    return '$n पर आपका ध्यान चाहिए';
  }

  @override
  String get startFailedTitle => 'ऐप शुरू नहीं हो सका';

  @override
  String get startFailedBody =>
      'लोड करते समय कुछ गलत हो गया। कनेक्शन जाँचें और फिर से कोशिश करें।';

  @override
  String get activationReplaceTitle => 'साइन-इन किए ड्राइवर को बदलें?';

  @override
  String get activationReplaceBody =>
      'इस फ़ोन पर पहले से एक ड्राइवर साइन इन है। यह लिंक एक्टिवेट करने से वह साइन आउट हो जाएगा और उसका जो कुछ भी अभी नहीं भेजा गया, वह हट जाएगा।';

  @override
  String get activationReplaceConfirm => 'एक्टिवेट करें';

  @override
  String get trackingActive => 'लोकेशन भेजी जा रही है';

  @override
  String get trackingStale => 'लोकेशन नहीं पहुँच रही';

  @override
  String get trackingUnknown => 'ट्रैकिंग की स्थिति अज्ञात';

  @override
  String noticeBigActive(String time) {
    return 'आख़िरी लोकेशन $time पर भेजी गई';
  }

  @override
  String noticeBigStale(String time) {
    return '$time से कोई लोकेशन नहीं। ऐप खोलें और लोकेशन सेटिंग्स जाँचें';
  }

  @override
  String get noticeBigStaleNever =>
      'अभी तक कोई लोकेशन नहीं भेजी गई। ऐप खोलें और लोकेशन सेटिंग्स जाँचें';

  @override
  String get noticeBigOff => 'अभी आपकी लोकेशन ट्रैक नहीं हो रही';

  @override
  String get openApp => 'ऐप खोलें';

  @override
  String get alertsChannel => 'ज़रूरी अलर्ट';

  @override
  String offlineSince(String time) {
    return 'ऑफ़लाइन · आख़िरी अपडेट $time';
  }

  @override
  String get statusCall => 'कॉल करें';

  @override
  String get statusDone => 'हो गया';

  @override
  String get statusCheckSettings => 'सेटिंग्स जाँचें';

  @override
  String get statusOpenCash => 'कैश';

  @override
  String get statusOpenCustody => 'मेरी गाड़ी';

  @override
  String get statusOpenMaintenance => 'मेंटेनेंस';

  @override
  String get statusOpenDocuments => 'मेरे दस्तावेज़';

  @override
  String get statusOpenContact => 'विवरण';

  @override
  String statusMore(String count) {
    return 'और $count अलर्ट';
  }

  @override
  String statusDaySummary(String count) {
    return 'आज के सत्र: $count';
  }

  @override
  String get statusContactSent => 'आपके सुपरवाइज़र को बता दिया गया';

  @override
  String get statusDialFailed => 'इस फ़ोन पर कॉल शुरू नहीं हो सकी';

  @override
  String get leaves => 'अनुपस्थिति अनुरोध';

  @override
  String get qaLeavesSub => 'अवकाश या कारण सहित अनुपस्थिति';

  @override
  String get leaveType => 'अवकाश का प्रकार';

  @override
  String leaveLeft(String days) {
    return '$days दिन शेष';
  }

  @override
  String get leaveFrom => 'से';

  @override
  String get leaveTo => 'तक';

  @override
  String get leaveOneDay => 'एक दिन';

  @override
  String get leaveReason => 'कारण';

  @override
  String get leaveFollowupFrom => 'अनुवर्ती आरंभ तिथि';

  @override
  String get leaveAttachment => 'संलग्नक (जैसे मेडिकल प्रमाणपत्र)';

  @override
  String get leaveAttachmentRequired => 'इस प्रकार के लिए संलग्नक चाहिए';

  @override
  String get leaveCamera => 'कैमरा';

  @override
  String get leaveGallery => 'गैलरी';

  @override
  String leavePreviewDays(String days) {
    return '$days दिन गिने गए';
  }

  @override
  String leavePaidPart(String days, String percent) {
    return '$days दिन $percent% वेतन पर';
  }

  @override
  String leaveUnpaidPart(String days) {
    return '$days दिन अवैतनिक';
  }

  @override
  String get leavePreviewOffline =>
      'गणना के लिए कनेक्शन चाहिए: अनुरोध भेजा जाएगा और कार्यालय में जांचा जाएगा';

  @override
  String get leaveSend => 'अनुरोध भेजें';

  @override
  String get leaveMine => 'मेरे अनुरोध';

  @override
  String get leaveNone => 'कोई अनुरोध नहीं';

  @override
  String get leaveCancel => 'वापस लें';

  @override
  String get leaveStatus_pending => 'स्वीकृति की प्रतीक्षा';

  @override
  String get leaveStatus_approved => 'स्वीकृत';

  @override
  String get leaveStatus_rejected => 'अस्वीकृत';

  @override
  String get leaveStatus_cancelled => 'रद्द';

  @override
  String leaveOfficeSays(String reason) {
    return 'कार्यालय: $reason';
  }

  @override
  String get leaveNoTypes => 'अभी आपके लिए कोई अवकाश प्रकार उपलब्ध नहीं है';

  @override
  String get leaveDatesInvalid => 'समाप्ति तिथि आरंभ से पहले है';

  @override
  String get leaveTypeMissing => 'अवकाश का प्रकार चुनें';

  @override
  String get noticeAtWork => 'काम पर';

  @override
  String get noticeOffDuty => 'ड्यूटी से बाहर';

  @override
  String get noticeInMaintenance => 'कार मरम्मत में है';

  @override
  String get noticeAwaitingFirst => 'पहले स्थान की प्रतीक्षा';

  @override
  String get noticeLocating => 'आपका स्थान खोजा जा रहा है…';

  @override
  String noticeShiftFrom(String time) {
    return 'शिफ्ट $time से';
  }

  @override
  String noticeDayEnded(String count) {
    return 'दिन समाप्त · $count ऑर्डर';
  }

  @override
  String get noticeDayEndedNoCount => 'दिन समाप्त';

  @override
  String get noticeDayNotStarted => 'काम का दिन शुरू नहीं हुआ है';

  @override
  String noticeLastConfirmed(String time) {
    return 'अंतिम पुष्ट भेजना $time';
  }

  @override
  String get noticeNoneConfirmed => 'अभी तक कोई भेजना पुष्ट नहीं हुआ';

  @override
  String get headsUpContact => 'संपर्क अनुरोध';

  @override
  String headsUpLocationBody(String time) {
    return 'अंतिम अपडेट $time · ऐप खोलें और स्थान सेटिंग जांचें।';
  }

  @override
  String get headsUpLocationBodyNever => 'ऐप खोलें और स्थान सेटिंग जांचें।';

  @override
  String get actionOpenLocationSettings => 'स्थान सेटिंग खोलें';

  @override
  String get noticeCatAlerts => 'अलर्ट';

  @override
  String get noticeCatCash => 'नकद और रिपोर्ट';

  @override
  String get noticeCatCar => 'कार और कस्टडी';

  @override
  String get noticeCatMaintenance => 'मरम्मत और कटौतियाँ';

  @override
  String get noticeCatDocuments => 'दस्तावेज़ और वेतन पर्ची';

  @override
  String updateAvailable(String version) {
    return 'नया संस्करण $version उपलब्ध है';
  }

  @override
  String get updateNow => 'अपडेट करें';

  @override
  String get updateLater => 'बाद में';

  @override
  String get updateRequiredTitle => 'जारी रखने के लिए ऐप अपडेट करना ज़रूरी है';

  @override
  String get updateRequiredBody =>
      'फ़ोन में सहेजा गया डेटा भेजा जाता रहेगा, और ट्रैकिंग जारी रहेगी।';

  @override
  String updateQueued(String count) {
    return 'भेजे जाने की प्रतीक्षा में: $count';
  }

  @override
  String updateSize(String size) {
    return 'आकार $size';
  }

  @override
  String get updateMobileData =>
      'आप मोबाइल डेटा पर हैं: डाउनलोड आपके डेटा प्लान से होगा।';

  @override
  String updateDownloading(String percent) {
    return 'डाउनलोड हो रहा है $percent';
  }

  @override
  String get updateInstall => 'इंस्टॉल करें';

  @override
  String get updateInstallHint =>
      'Android इंस्टॉल की पुष्टि करने को कहेगा। अपडेट के बाद ऐप फिर से खोलें।';

  @override
  String get updatePermissionTitle => 'अपडेट इंस्टॉल करने की अनुमति दें';

  @override
  String get updatePermissionBody =>
      'अगले पेज पर इस ऐप के लिए «इस स्रोत से अनुमति दें» चालू करें, फिर वापस आएँ।';

  @override
  String get updateOpenSettings => 'सेटिंग्स खोलें';

  @override
  String get updateChecksum =>
      'डाउनलोड की गई फ़ाइल खराब थी और हटा दी गई। फिर से कोशिश करें।';

  @override
  String get updateFailed => 'डाउनलोड नहीं हो सका। फिर से कोशिश करें।';

  @override
  String get updateInstallFailed => 'इंस्टॉलर नहीं खुल सका।';

  @override
  String get checkUpdates => 'अपडेट जाँचें';

  @override
  String get upToDate => 'आपके पास नवीनतम संस्करण है';

  @override
  String get updateCheckFailed => 'जाँच नहीं हो सकी: कनेक्शन नहीं है';

  @override
  String get whatsNew => 'नया क्या है';

  @override
  String get noticesCurrent => 'मौजूदा';

  @override
  String get noticesHistory => 'इतिहास';

  @override
  String get messagesChannel => 'संदेश और अपडेट';

  @override
  String get noticeOpenLeave => 'छुट्टी का अनुरोध';

  @override
  String get pettyTitle => 'छोटी नकदी की अमानत';

  @override
  String get qaPettySub => 'बिल के साथ खर्च करें';

  @override
  String get pettyCashRow => 'आपकी छोटी नकदी की अमानत';

  @override
  String get pettyNone =>
      'अभी आपके पास कोई छोटी नकदी की अमानत नहीं है। ऑफ़िस इसे शाखा के खज़ाने से देता है।';

  @override
  String get pettyBalance => 'अमानत की शेष राशि';

  @override
  String pettyPendingPart(String pending, String available) {
    return 'इसमें से $pending समीक्षा की प्रतीक्षा में · खर्च के लिए $available बचा';
  }

  @override
  String get pettySpend => 'अमानत से खर्च करें';

  @override
  String get pettyMine => 'लेन-देन';

  @override
  String get pettyEmpty => 'अमानत पर अभी कोई लेन-देन नहीं';

  @override
  String get pettyQueued => 'भेजे जाने की प्रतीक्षा में';

  @override
  String get pettyPending => 'समीक्षा की प्रतीक्षा में';

  @override
  String get pettyApproved => 'मंज़ूर';

  @override
  String get pettyRejected => 'अस्वीकृत';

  @override
  String get pettyCancelled => 'रद्द';

  @override
  String pettyReason(String reason) {
    return 'कारण: $reason';
  }

  @override
  String get pettyCancel => 'खर्च रद्द करें';

  @override
  String pettyCancelQ(String amount) {
    return '$amount का खर्च रद्द करें? ऑफ़िस ने अभी इसकी समीक्षा नहीं की है।';
  }

  @override
  String get pettyFunded => 'ऑफ़िस द्वारा दी गई';

  @override
  String get pettyReturned => 'खज़ाने को लौटाई गई';

  @override
  String get pettyOfficeExpense => 'ऑफ़िस द्वारा दर्ज खर्च';

  @override
  String get pettyCorrection => 'सुधार';

  @override
  String pettyIntro(String available) {
    return 'बिल की फ़ोटो लें और राशि व खर्च का प्रकार दर्ज करें। ऑफ़िस समीक्षा करेगा, और मंज़ूरी के बाद यह आपकी अमानत से घटेगा। खर्च के लिए बचा: $available KWD';
  }

  @override
  String get pettyInvoice => 'बिल की फ़ोटो';

  @override
  String get pettyTakeInvoice => 'बिल की फ़ोटो लें';

  @override
  String get pettyInvoiceMissing => 'बिल की फ़ोटो ज़रूरी है';

  @override
  String get pettyAmount => 'राशि';

  @override
  String get pettyAmountInvalid => 'सही राशि दर्ज करें (3 दशमलव तक)';

  @override
  String pettyAmountMax(String available) {
    return 'जितना आप अभी खर्च कर सकते हैं उससे अधिक ($available KWD)';
  }

  @override
  String get pettyCategory => 'खर्च का प्रकार';

  @override
  String get pettyCategoryMissing => 'खर्च का प्रकार चुनें';

  @override
  String get pettyDate => 'बिल की तारीख';

  @override
  String get pettyVendor => 'विक्रेता या दुकान';

  @override
  String get pettyNote => 'टिप्पणी';

  @override
  String get pettySend => 'समीक्षा के लिए भेजें';

  @override
  String get kind_petty => 'छोटी नकदी का खर्च';

  @override
  String get kind_petty_cancel => 'छोटी नकदी का खर्च रद्द करना';

  @override
  String get companyTitle => 'आप किस कंपनी के साथ काम करते हैं?';

  @override
  String get companyIntro =>
      'वह कंपनी चुनें जिसके लिए आप डिलीवरी करते हैं। आपका चुनाव मंज़ूरी के लिए ऑफ़िस जाता है; इंतज़ार करते हुए आप काम जारी रख सकते हैं।';

  @override
  String get companyNote => 'ऑफ़िस के लिए नोट (वैकल्पिक)';

  @override
  String get companySend => 'ऑफ़िस को भेजें';

  @override
  String companyRejected(String platform, String reason) {
    return 'ऑफ़िस ने आपका चुनाव ($platform) अस्वीकार किया: $reason। कृपया फिर से चुनें।';
  }

  @override
  String companyPending(String platform) {
    return '$platform के साथ काम करने का आपका अनुरोध ऑफ़िस के पास लंबित है';
  }

  @override
  String get companyChange => 'मेरा चुनाव बदलें';

  @override
  String get companyNone =>
      'अभी कोई कंपनी उपलब्ध नहीं है। ऑफ़िस से संपर्क करें।';

  @override
  String get endOrdersKept =>
      'यह सहेजा जाएगा और आज की रिपोर्ट में दिखेगा, जहाँ आप बाकी भरेंगे';

  @override
  String get languageFirst =>
      'ऐप की भाषा चुनें। आप इसे बाद में सेटिंग्स में बदल सकते हैं।';

  @override
  String get schemeKindPick => 'पहले चुनें कि आपको कैसे भुगतान मिलेगा';

  @override
  String get schemeKind_per_order => 'प्रति ऑर्डर';

  @override
  String get schemeKind_fixed_salary => 'निश्चित वेतन';

  @override
  String get schemeKind_batch => 'बैच';

  @override
  String schemeFixedSalary(String amount) {
    return 'निश्चित वेतन: $amount KWD प्रति माह';
  }

  @override
  String get schemeContractSalary => 'आपके अनुबंध का मूल वेतन';

  @override
  String schemeOverTarget(String target, String rate) {
    return 'लक्ष्य $target ऑर्डर: इसके ऊपर हर ऑर्डर पर + $rate KWD';
  }

  @override
  String schemeUnderTarget(String rate) {
    return 'और हर कम ऑर्डर पर − $rate KWD';
  }

  @override
  String get schemeTierRates => 'महीने के ऑर्डर के अनुसार प्रति ऑर्डर कीमत:';

  @override
  String schemeTierRateRow(String orders, String rate) {
    return '$orders ऑर्डर से: $rate KWD';
  }

  @override
  String schemeMonthlyBonus(String amount) {
    return 'मासिक बोनस: $amount KWD';
  }

  @override
  String get schemeMarksTable => 'महीने में लाल निशान:';

  @override
  String schemeMarksFree(String marks) {
    return '$marks निशान तक: कोई कटौती नहीं (आपकी छुट्टियां)';
  }

  @override
  String schemeMarksRow(String marks, String amount) {
    return '$marks निशान: − $amount KWD';
  }

  @override
  String schemeMarkEach(String amount) {
    return 'हर लाल निशान पर − $amount KWD';
  }

  @override
  String schemeReducedStarDay(String rate) {
    return 'स्टार दिन पर लाल निशान: महीने के हर ऑर्डर पर $rate KWD, वेतन और बोनस के बजाय, कटौतियां फिर भी';
  }

  @override
  String schemeReducedMarks(String marks, String rate) {
    return '$marks से अधिक लाल निशान: महीने के हर ऑर्डर पर $rate KWD, वेतन और बोनस के बजाय';
  }

  @override
  String schemeRequiredDays(String days) {
    return 'महीने में $days मान्य दिन आवश्यक';
  }

  @override
  String get schemePlatformAmounts =>
      'टिप्स जोड़ी जाती हैं; खाने का नुकसान, समायोजन और प्लेटफ़ॉर्म की छूट काटी जाती है';

  @override
  String schemeDriverPays(String items) {
    return 'आप पर: $items';
  }

  @override
  String get schemeChange => 'योजना बदलने का अनुरोध';

  @override
  String get schemeChangeBody =>
      'ऑफिस आपका अनुरोध देखेगा; मंज़ूरी के बाद आपके प्लेटफ़ॉर्म की योजनाएँ यहाँ दिखेंगी ताकि आप नई चुनें।';

  @override
  String get schemeChangePending =>
      'योजना बदलने का आपका अनुरोध ऑफिस के पास लंबित है';

  @override
  String schemeChangeRejected(String note) {
    return 'ऑफिस ने योजना बदलने से मना किया: $note';
  }

  @override
  String get schemePickFirst => 'अपनी वेतन योजना चुनें';

  @override
  String schemePickAllowed(String month) {
    return 'मंज़ूर: अपनी नई योजना चुनें, यह $month से शुरू होगी';
  }

  @override
  String get schemePick => 'यह योजना चुनें';

  @override
  String schemePickConfirm(String name, String month) {
    return 'आप “$name” चुन रहे हैं, $month से। इसके बाद केवल ऑफिस को नया अनुरोध ही इसे बदल सकता है।';
  }

  @override
  String get schemePicked => 'आपकी योजना तय हो गई';
}
