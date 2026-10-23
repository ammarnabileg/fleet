// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Filipino Pilipino (`fil`).
class AppLocalizationsFil extends AppLocalizations {
  AppLocalizationsFil([String locale = 'fil']) : super(locale);

  @override
  String get appTitle => 'App ng driver';

  @override
  String get retry => 'Subukan muli';

  @override
  String get cancel => 'Kanselahin';

  @override
  String get continueBtn => 'Magpatuloy';

  @override
  String get save => 'I-save';

  @override
  String get send => 'Ipadala';

  @override
  String get back => 'Bumalik';

  @override
  String get done => 'Tapos na';

  @override
  String get networkError => 'Walang koneksyon sa internet. Subukan muli.';

  @override
  String get genericError => 'May nangyaring mali. Subukan muli.';

  @override
  String get kwd => 'KWD';

  @override
  String get km => 'km';

  @override
  String get signInTitle => 'Mag-sign in';

  @override
  String get signInHint =>
      'Ilagay ang numero ng telepono mo na nakarehistro sa kumpanya. Darating ang sign-in code sa WhatsApp.';

  @override
  String get phoneLabel => 'Telepono';

  @override
  String get phoneInvalid =>
      '8 digit ng Kuwait, o internasyonal na numero na nagsisimula sa +';

  @override
  String get sendCode => 'Ipadala ang code';

  @override
  String get activationTip =>
      'Kung nakatanggap ka ng activation link sa WhatsApp, buksan ito sa teleponong ito: hindi na kailangan ng code.';

  @override
  String get otpTitle => 'Sign-in code';

  @override
  String otpHint(String phone) {
    return 'Ilagay ang 6-digit na code na ipinadala sa WhatsApp sa $phone.';
  }

  @override
  String get otpLabel => 'Code';

  @override
  String get verify => 'Mag-sign in';

  @override
  String get otpResend => 'Walang code? Ipadala muli';

  @override
  String get activating => 'Ina-activate ang app sa teleponong ito…';

  @override
  String get activationFailed => 'Hindi na-activate';

  @override
  String get permTitle => 'Mga pahintulot ng app';

  @override
  String get permIntro =>
      'Para ma-track habang nasa pangangalaga mo ang sasakyan, kahit nakasara ang app, kailangan ng app ang mga pahintulot na ito. Nire-record lang ang lokasyon mo habang may sasakyan sa pangangalaga mo.';

  @override
  String get permLocation => 'Lokasyon: “Payagan palagi”';

  @override
  String get permLocationWhy =>
      'Para makita ng supervisor ang sasakyan habang nasa pangangalaga mo.';

  @override
  String get permNotifications => 'Mga notification';

  @override
  String get permNotificationsWhy =>
      'May permanenteng notification habang nagta-track (patakaran ng Android).';

  @override
  String get permBattery => 'Huwag pansinin ang battery optimisation';

  @override
  String get permBatteryWhy =>
      'Para hindi ihinto ng telepono ang pag-track sa background.';

  @override
  String get permGrant => 'Payagan';

  @override
  String get permGranted => 'Pinayagan';

  @override
  String get permSettings => 'Buksan ang settings';

  @override
  String get permLocationRequired =>
      'Kailangan ang pahintulot sa lokasyon para magpatuloy.';

  @override
  String get gpsOff => 'Naka-off ang GPS: i-on ito sa settings ng telepono.';

  @override
  String get obTitle => 'Kumpletuhin ang pagpaparehistro';

  @override
  String get obIntro =>
      'Ilagay ang mga detalye mo at kunan ng litrato ang mga dokumento mo at ang sasakyan. Walang opisyal hangga\'t hindi pa nasusuri ng kumpanya.';

  @override
  String obRejected(String reason) {
    return 'Ibinalik ang pagpaparehistro mo: $reason';
  }

  @override
  String get obStepData => 'Mga detalye';

  @override
  String get obStepDocs => 'Mga dokumento';

  @override
  String get obStepVehicle => 'Sasakyan';

  @override
  String get obStepReview => 'Pagsusuri';

  @override
  String get civilId => 'Civil ID';

  @override
  String get civilIdInvalid => 'May 12 digit ang civil ID';

  @override
  String get nationality => 'Nasyonalidad';

  @override
  String get docNumber => 'Numero ng dokumento';

  @override
  String get docExpiry => 'Petsa ng pag-expire';

  @override
  String get docFront => 'Harap';

  @override
  String get docBack => 'Likod';

  @override
  String get pickPhoto => 'Litrato';

  @override
  String get takePhoto => 'Kumuha ng litrato';

  @override
  String get fromGallery => 'Mula sa gallery';

  @override
  String get uploading => 'Nag-a-upload…';

  @override
  String get required => 'Kailangan';

  @override
  String get plate => 'Numero ng plaka';

  @override
  String get plateHint => 'Gaya ng nasa plaka, hal. 18/23456';

  @override
  String get odometerKm => 'Odometer (km)';

  @override
  String get odometerPhoto => 'Litrato ng odometer';

  @override
  String get noVehicle => 'Wala akong sasakyan ngayon';

  @override
  String get vehiclePhotos => 'Mga litrato ng kondisyon ng sasakyan';

  @override
  String get obSubmit => 'Ipadala para suriin';

  @override
  String obMissing(String items) {
    return 'Kumpletuhin: $items';
  }

  @override
  String get obWaitingTitle => 'Sinusuri ang mga detalye mo';

  @override
  String get obWaitingText =>
      'Makakatanggap ka ng mensahe sa WhatsApp kapag naaprubahan o kung may kailangang ayusin.';

  @override
  String get refresh => 'I-refresh';

  @override
  String get position_front => 'Harap';

  @override
  String get position_back => 'Likod';

  @override
  String get position_left => 'Kaliwang gilid';

  @override
  String get position_right => 'Kanang gilid';

  @override
  String get position_interior => 'Loob';

  @override
  String get position_other => 'Iba pa';

  @override
  String get tabHome => 'Home';

  @override
  String get tabCash => 'Cash';

  @override
  String get tabAccount => 'Account';

  @override
  String get noCustody => 'Walang sasakyan sa pangangalaga mo ngayon';

  @override
  String get noCustodyHint =>
      'Kapag may sasakyang ipinasa sa iyo, lalabas ito rito at kusang magsisimula ang pag-track.';

  @override
  String custodySince(String when) {
    return 'Nasa pangangalaga mo mula $when';
  }

  @override
  String lastKm(String km) {
    return 'Huling reading: $km km';
  }

  @override
  String get trackingOn => 'Naka-on ang pag-track';

  @override
  String get trackingOff => 'Naka-off ang pag-track';

  @override
  String trackingWaiting(String count) {
    return 'Naghihintay maipadala: $count';
  }

  @override
  String get startDay => 'Simulan ang araw';

  @override
  String get startDayDone => 'Nagsimula na ang araw';

  @override
  String get endDay => 'Tapusin ang araw';

  @override
  String get dailyReport => 'Pang-araw-araw na report';

  @override
  String get outboxTitle => 'Naghihintay maipadala';

  @override
  String get outboxQueued => 'Kusang ipapadala kapag bumalik ang network';

  @override
  String outboxFailed(String reason) {
    return 'Hindi tinanggap: $reason';
  }

  @override
  String get outboxDiscard => 'Alisin';

  @override
  String get kind_odometer => 'Reading ng odometer';

  @override
  String get kind_report => 'Pang-araw-araw na report';

  @override
  String get startDayTitle => 'Simula ng araw';

  @override
  String get endDayDone => 'Natapos ang araw';

  @override
  String get startAgain => 'Magsimula muli';

  @override
  String reportAddsToDay(String orders) {
    return 'Idaragdag ang report na ito sa naipadala mo na ngayong araw ($orders order). Ilagay lang ang mga order at cash ng session na ito.';
  }

  @override
  String reportSession(String n) {
    return 'Session $n';
  }

  @override
  String get endReadingIntro =>
      'Bago ang report ngayong araw: ang litrato at reading ng odometer sa pagtatapos ng araw. Unang ipapadala ang reading, saka ang report.';

  @override
  String get status_returned => 'Ibinalik para itama';

  @override
  String get editReportTitle => 'I-edit ang report';

  @override
  String get changeReportTitle => 'Humiling na baguhin ang naaprubahang report';

  @override
  String get changeReportIntro =>
      'Naaprubahan na ang report na ito: mapupunta sa opisina ang hiling mo at ilalapat kapag naaprubahan.';

  @override
  String get changeReason => 'Dahilan ng pagbabago';

  @override
  String get newScreenshotOptional => 'Bagong screenshot (opsyonal)';

  @override
  String get reportExistsForDay =>
      'Naipadala mo na ang report ng araw na ito. I-edit ito sa halip na magpadala ng pangalawa.';

  @override
  String get editReport => 'I-edit ang report';

  @override
  String get changePending => 'Naghihintay sa opisina ang pagbabago';

  @override
  String returnedNote(Object note) {
    return 'Ibinalik ng opisina: $note';
  }

  @override
  String get myCar => 'Kotse ko';

  @override
  String get carSince => 'Nasa pangangalaga mo mula';

  @override
  String get lastReading => 'Huling reading ng odometer';

  @override
  String get registrationExpiry => 'Pag-expire ng rehistro';

  @override
  String get requestVehicleChange => 'Humiling ng ibang sasakyan';

  @override
  String get vehicleChangeReason => 'Dahilan';

  @override
  String get vehicleChangePending =>
      'Nasa supervisor ang hiling mo para sa ibang sasakyan';

  @override
  String vehicleChangeRejected(Object note) {
    return 'Tinanggihan ang hiling mo para sa ibang sasakyan: $note';
  }

  @override
  String get profileTitle => 'Mga detalye ko';

  @override
  String get employeeNumber => 'Employee no.';

  @override
  String get companyLabel => 'Kumpanya';

  @override
  String get platformLabel => 'Platform';

  @override
  String get bankLabel => 'Bangko';

  @override
  String get myDocuments => 'Mga dokumento ko';

  @override
  String get docValid => 'Valid';

  @override
  String docExpiring(Object days) {
    return 'Mag-e-expire sa loob ng $days araw';
  }

  @override
  String get docExpired => 'Expired na';

  @override
  String get docMissing => 'Wala sa file';

  @override
  String docExpires(Object date) {
    return 'Mag-e-expire sa $date';
  }

  @override
  String get uploadRenewal => 'I-upload ang na-renew na dokumento';

  @override
  String get renewalPending => 'Naghihintay sa opisina ang renewal';

  @override
  String renewalRejected(Object note) {
    return 'Tinanggihan ang renewal: $note';
  }

  @override
  String get newExpiry => 'Bagong petsa ng pag-expire';

  @override
  String get documentNumber => 'Numero ng dokumento (opsyonal)';

  @override
  String get documentPhoto => 'Litrato ng dokumento';

  @override
  String get pickDate => 'Pumili ng petsa';

  @override
  String cashNearLimit(Object limit) {
    return 'Malapit na ang balanse mo sa alert limit ($limit): ibigay agad ang cash.';
  }

  @override
  String get movements => 'Mga galaw';

  @override
  String get noMovements => 'Wala pang galaw';

  @override
  String get moveCollection => 'Cash ng pang-araw-araw na report';

  @override
  String get moveReceipt => 'Ibinigay na may resibo';

  @override
  String get moveAdjustment => 'Pagwawasto';

  @override
  String get moveReversal => 'Pagbawi';

  @override
  String get moveSettlement => 'Settlement sa pagtatapos ng serbisyo';

  @override
  String get moveOpening => 'Panimulang balanse';

  @override
  String get endDayTitle => 'Pagtatapos ng araw';

  @override
  String get odometerIntro =>
      'Kunan nang malinaw ang odometer, saka i-type ang reading gaya ng nasa litrato.';

  @override
  String get retake => 'Kunan muli';

  @override
  String kmLower(String km) {
    return 'Mas mababa sa huling reading ($km km). Suriin ito: mapupunta ito sa pagsusuri.';
  }

  @override
  String get kmInvalid => 'I-type ang reading sa mga numero';

  @override
  String get photoRequired => 'Kailangan ang litrato';

  @override
  String get sentTitle => 'Naipadala';

  @override
  String get queuedTitle => 'Naka-save sa telepono';

  @override
  String get sentText => 'Natanggap ito ng kumpanya.';

  @override
  String get queuedText =>
      'Walang network ngayon. Kusa itong ipapadala, kasama ang orihinal na oras nito, kapag bumalik ang koneksyon.';

  @override
  String get reportTitle => 'Pang-araw-araw na report';

  @override
  String get reportDate => 'Araw ng trabaho';

  @override
  String get today => 'Ngayon';

  @override
  String get yesterday => 'Kahapon';

  @override
  String get dayBefore => 'Kamakalawa';

  @override
  String get ordersCount => 'Mga order';

  @override
  String get cashAmount => 'Nakolektang cash';

  @override
  String get cashInvalid => 'Halagang may hanggang tatlong decimal';

  @override
  String get screenshot => 'Screenshot ng buod ng araw mula sa delivery app';

  @override
  String get notes => 'Mga tala';

  @override
  String get recentReports => 'Mga kamakailang report';

  @override
  String get status_submitted => 'Naghihintay ng pagsusuri';

  @override
  String get status_approved => 'Naaprubahan';

  @override
  String get status_rejected => 'Tinanggihan';

  @override
  String approvedCash(String amount) {
    return 'Naaprubahan: $amount';
  }

  @override
  String get cashTitle => 'Cash';

  @override
  String get cashTotal => 'Cash na hawak mo';

  @override
  String get cashPosted => 'Naaprubahan';

  @override
  String get cashPending => 'Naghihintay ng pagsusuri';

  @override
  String cashOverLimit(String limit) {
    return 'Lampas sa limit ($limit): ibigay ang cash sa cashier.';
  }

  @override
  String get receipts => 'Mga resibo';

  @override
  String receiptNo(String no) {
    return 'Resibo blg. $no';
  }

  @override
  String get confirmReceipt => 'Kinukumpirma ko';

  @override
  String get receiptConfirmed => 'Nakumpirma';

  @override
  String confirmReceiptQ(String amount) {
    return 'Ibinigay mo ba ang $amount KWD sa cashier?';
  }

  @override
  String get noReceipts => 'Wala pang resibo';

  @override
  String get language => 'Wika';

  @override
  String get trackingDetails => 'Status ng pag-track';

  @override
  String lastUpload(String when) {
    return 'Huling naipadala: $when';
  }

  @override
  String get never => 'wala pa';

  @override
  String appVersion(String version) {
    return 'Bersyon $version';
  }

  @override
  String get signOut => 'Mag-sign out';

  @override
  String get signOutQ =>
      'Hihinto ang pag-track at kakailanganin mo ng bagong activation para mag-sign in. Magpatuloy?';

  @override
  String get blockedTitle => 'Suspendido ang account mo';

  @override
  String get blockedText => 'Kontakin ang supervisor mo.';

  @override
  String get obReady => 'Handa na ang lahat: ipadala para suriin.';

  @override
  String get maintenance => 'Maintenance';

  @override
  String get maintenanceTitle => 'Mga request sa maintenance';

  @override
  String get kind_maintenance => 'Request sa maintenance';

  @override
  String get mntNew => 'Bagong request sa maintenance';

  @override
  String get mntIntro =>
      'Ilarawan ang problema at kumuha ng mga litrato. Ang kotseng naaksidente ay ipinapaayos sa pamamagitan ng opisina.';

  @override
  String get mntDirectIntro =>
      'Ilarawan ang problema, kumuha ng mga litrato, at piliin ang maintenance center kung saan mo dadalhin ang kotse. Direktang mapupunta sa center ang request, mananatili sa pangangalaga mo ang kotse, at sasabihan ka kapag handa na ito.';

  @override
  String get mntCenter => 'Maintenance center';

  @override
  String get mntPickedUp => 'Nakuha ko na ang kotse';

  @override
  String get pickupTitle => 'Pagkuha ng kotse mula sa center';

  @override
  String get pickupIntro =>
      'Kunan ang odometer at ilagay ang reading kapag kinuha mo ang kotse: babalik ito sa pangangalaga mo at sisimulan mo ang araw gaya ng dati.';

  @override
  String get kind_pickup => 'Nakuha ang kotse mula sa maintenance';

  @override
  String get mntNoVehicle =>
      'Ang maintenance ay hinihiling para sa sasakyang nasa pangangalaga mo. Wala kang sasakyan ngayon.';

  @override
  String get mntKind => 'Uri';

  @override
  String get mntDescription => 'Ano ang sira';

  @override
  String get mntOdometer => 'Odometer (opsyonal)';

  @override
  String get mntPhotos => 'Mga litrato (hanggang 4)';

  @override
  String get mntAddPhoto => 'Litrato';

  @override
  String get mntNone => 'Walang request sa maintenance';

  @override
  String mntRequestNo(String number) {
    return 'Request #$number';
  }

  @override
  String mntAtCenter(String center) {
    return 'Center: $center';
  }

  @override
  String mntReadyBanner(String plate, String center) {
    return 'Handa nang kunin ang sasakyan mong $plate sa $center';
  }

  @override
  String mntRejected(String reason) {
    return 'Tinanggihan: $reason';
  }

  @override
  String get mntSent => 'Naipadala sa center ang request mo sa maintenance';

  @override
  String get mntKind_periodic => 'Regular na serbisyo';

  @override
  String get mntKind_mechanical => 'Mekanikal';

  @override
  String get mntKind_electrical => 'Elektrikal';

  @override
  String get mntKind_tyres => 'Gulong';

  @override
  String get mntKind_battery => 'Baterya';

  @override
  String get mntKind_ac => 'Aircon';

  @override
  String get mntKind_bodywork => 'Bodywork';

  @override
  String get mntKind_other => 'Iba pa';

  @override
  String get mntStatus_requested => 'Naghihintay ng pag-apruba';

  @override
  String get mntStatus_approved => 'Naaprubahan';

  @override
  String get mntStatus_rejected => 'Tinanggihan';

  @override
  String get mntStatus_referred => 'Ipinadala sa center';

  @override
  String get mntStatus_at_center => 'Nasa center';

  @override
  String get mntStatus_ready => 'Handa nang kunin';

  @override
  String get mntStatus_picked_up => 'Nakuha na';

  @override
  String get mntStatus_closed => 'Sarado';

  @override
  String get mntStatus_cancelled => 'Kinansela';

  @override
  String get mntTapToRemove => 'i-tap para alisin';

  @override
  String get accident => 'Mag-report ng aksidente';

  @override
  String get accidentsTitle => 'Mga aksidente';

  @override
  String get kind_accident => 'Report ng aksidente';

  @override
  String get kind_police_report => 'Police report';

  @override
  String get accNew => 'Bagong report ng aksidente';

  @override
  String get accEmergency => 'Kung may nasaktan, tumawag muna sa 112.';

  @override
  String get accIntro =>
      'Kunan ang sasakyan mula sa iba\'t ibang anggulo: harap, likod, magkabilang gilid at ang pinsala. Kusang nire-record ang oras at lugar.';

  @override
  String get accNoVehicle =>
      'Ang aksidente ay nire-report para sa sasakyang hawak mo. Wala kang sasakyan ngayon: tawagan ang supervisor mo.';

  @override
  String get accDescription => 'Ano ang nangyari?';

  @override
  String get accInjuries => 'May nasaktan';

  @override
  String get accInjuriesNote => 'Detalye ng pinsala sa tao';

  @override
  String get accOtherParty => 'Ang kabilang panig (plaka, pangalan, insurer)';

  @override
  String accPhotos(String min) {
    return 'Mga litrato ng aksidente (hindi bababa sa $min)';
  }

  @override
  String accPhotosNeeded(String min) {
    return 'Kumuha ng hindi bababa sa $min litrato mula sa iba\'t ibang anggulo';
  }

  @override
  String get accPoliceReport => 'Police report';

  @override
  String get accPoliceReportNo => 'Numero ng report';

  @override
  String get accPoliceLater =>
      'Wala pang report? Ipadala na ngayon at ipadala mamaya ang litrato ng police report mula sa mga aksidente mo sa ibaba.';

  @override
  String get accSendPolice => 'Ipadala ang police report';

  @override
  String get accNone => 'Walang aksidente';

  @override
  String accNo(String number) {
    return 'Aksidente #$number';
  }

  @override
  String get accStage_review => 'Sinusuri';

  @override
  String get accStage_outcome => 'Naghihintay ng desisyon sa pananagutan';

  @override
  String get accStage_recorded => 'Napagpasyahan ang pananagutan';

  @override
  String get accStage_closed => 'Sarado';

  @override
  String get accLiability_none => 'Hindi ka mananagot';

  @override
  String get accLiability_driver => 'Ikaw ang mananagot';

  @override
  String accLiability_shared(String percent) {
    return 'Hating pananagutan: ang bahagi mo $percent%';
  }

  @override
  String accDeduction(String total, String count) {
    return 'Kaltas $total KWD · mga hulog: $count';
  }

  @override
  String accInstallment(String month, String amount) {
    return '$month: $amount KWD';
  }

  @override
  String accAwaitingPolice(String number) {
    return 'Naghihintay ng police report ang aksidente #$number: i-tap para ipadala ang litrato nito';
  }

  @override
  String get fines => 'Mga multa sa trapiko';

  @override
  String get finesTitle => 'Mga multa sa trapiko';

  @override
  String get finesIntro =>
      'Mga multa sa sasakyan habang hawak mo ito, ayon sa oras ng multa. Ang kumpanya ang magpapasya: sasagutin nito, o kakaltasin sa sahod mo nang hulugan.';

  @override
  String get finesNone => 'Walang multa';

  @override
  String get fineStatus_open => 'Sinusuri';

  @override
  String get fineStatus_charged => 'Kinaltas sa sahod mo';

  @override
  String get fineStatus_company => 'Sinagot ng kumpanya';

  @override
  String get monthlyStatement => 'Buwanang statement ng platform';

  @override
  String get payslips => 'Mga payslip';

  @override
  String get statementTitle => 'Buwanang statement ng platform';

  @override
  String statementIntro(String platform) {
    return 'Sa simula ng bawat buwan, ipadala ang mga screenshot ng buod ng buwan mula sa $platform app at i-type ang mga numero gaya ng nakikita. Ikinukumpara ito ng opisina sa mga screenshot bago ang payroll.';
  }

  @override
  String get statementNoPlatform =>
      'Hindi pa naitatakda ang platform mo. Kontakin ang opisina.';

  @override
  String get statementNoMonth =>
      'Naipadala mo na ang lahat ng bukas na buwan. Hintayin ang pagsusuri ng opisina.';

  @override
  String get statementMonth => 'Buwan';

  @override
  String get statementShots =>
      'Mga screenshot mula sa platform app (hanggang 6)';

  @override
  String get statementShotRequired => 'Magdagdag ng kahit isang screenshot';

  @override
  String get statementHistory => 'Ang naipadala mo';

  @override
  String statementSentDays(String days) {
    return 'Naipadala: $days valid na araw';
  }

  @override
  String statementApprovedDays(String days) {
    return 'Naaprubahan: $days valid na araw';
  }

  @override
  String get statementStatus_submitted => 'Naghihintay ng pagsusuri';

  @override
  String get statementStatus_approved => 'Naaprubahan';

  @override
  String get statementStatus_rejected => 'Tinanggihan: ipadala muli';

  @override
  String get addShot => 'Magdagdag ng screenshot';

  @override
  String get validDays => 'Mga valid na araw';

  @override
  String get ordersTotal => 'Kabuuang order';

  @override
  String get hoursTotal => 'Kabuuang oras';

  @override
  String get payslipsTitle => 'Mga payslip';

  @override
  String get payslipsNone => 'Wala pang naaprubahang payslip';

  @override
  String get payslipNet => 'Net na sahod';

  @override
  String get payslipStatus_approved => 'Naaprubahan';

  @override
  String get payslipStatus_paid => 'Nabayaran';

  @override
  String get iban => 'IBAN';

  @override
  String get ibanHint =>
      'Dito ipinapasok ang sahod mo: kopyahin ito mula sa app ng bangko mo';

  @override
  String get bankName => 'Pangalan ng bangko';

  @override
  String get civilSignIn => 'Mag-sign in gamit ang civil ID';

  @override
  String get civilSignInHint =>
      'Kung walang numero ng telepono mo ang kumpanya: mag-sign in gamit ang civil ID mo at ang initial password na ibinigay ng opisina, saka irehistro ang telepono mo. Isang beses lang gumagana ang password.';

  @override
  String get initialPassword => 'Initial password';

  @override
  String get claimContinue => 'Magpatuloy';

  @override
  String claimWelcome(String name) {
    return 'Maligayang pagdating $name. Ilagay ang numero ng telepono mo na may WhatsApp: doon ipapadala ang code, at iyon na ang gagamitin mo sa pag-sign in.';
  }

  @override
  String get password => 'Password';

  @override
  String get civilSignInOnly =>
      'Mag-sign in gamit ang civil ID at password mo. Sa unang pagkakataon: ang initial password na ibinigay ng opisina, saka ka pipili ng sarili mong password.';

  @override
  String get forgotPassword =>
      'Nakalimutan ang password? Humingi sa supervisor mo ng bagong initial password.';

  @override
  String choosePassword(String name) {
    return 'Maligayang pagdating $name. Pumili ng password mo: ito at ang civil ID mo ang gagamitin mo sa pag-sign in mula ngayon, sa kahit anong telepono. Hindi bababa sa 8 character, hindi ang initial password o ang civil ID mo, at huwag sabihin kanino man.';
  }

  @override
  String get newPassword => 'Bagong password';

  @override
  String get confirmPassword => 'I-type muli ang password';

  @override
  String get passwordTooShort => 'Hindi bababa sa 8 character';

  @override
  String get passwordsDiffer => 'Magkaiba ang dalawang password';

  @override
  String get passwordIsCivilId =>
      'Huwag gamitin ang civil ID mo bilang password';

  @override
  String get saveAndSignIn => 'I-save at mag-sign in';

  @override
  String get validDayQuestion =>
      'Binilang ba ng app ng platform na valid ang araw na ito?';

  @override
  String get validDayYes => 'Valid na araw';

  @override
  String get validDayNo => 'Hindi valid';

  @override
  String get paySchemes => 'Pay scheme';

  @override
  String get schemesIntro =>
      'Ang scheme mo ang nagpapasya kung paano kinukuwenta ang sahod mo mula sa mga order mo. Puwede kang humiling ng ibang scheme na inaalok ng platform mo; magsisimula ito sa unang araw ng susunod na buwan kung papayag ang opisina.';

  @override
  String get schemeNow => 'Ang scheme mo ngayong buwan';

  @override
  String get schemeNone => 'Hindi pa naitatakda ng opisina ang scheme mo';

  @override
  String schemeNextMonth(String name) {
    return 'Mula sa susunod na buwan: $name';
  }

  @override
  String get schemeOthers => 'Iba pang scheme sa platform mo';

  @override
  String get schemeAsk => 'Hilingin ang scheme na ito';

  @override
  String schemeAskBody(String name, String month) {
    return 'Hinihiling mo ang “$name” mula $month. Susuriin ito ng opisina at makukuha mo ang sagot dito at sa WhatsApp.';
  }

  @override
  String get schemeNoteHint => 'Tala para sa opisina (opsyonal)';

  @override
  String get schemeSend => 'Ipadala ang request';

  @override
  String get schemeSent => 'Naipadala sa opisina ang request mo';

  @override
  String schemePending(String name, String month) {
    return 'Naghihintay sa opisina ang request mo para sa “$name” mula $month';
  }

  @override
  String schemeApproved(String name, String month) {
    return 'Naaprubahan: “$name” mula $month';
  }

  @override
  String schemeRejected(String name, String note) {
    return 'Tinanggihan ng opisina ang “$name”: $note';
  }

  @override
  String get schemeCancel => 'Kanselahin ang request';

  @override
  String schemePerOrder(String rate) {
    return 'Bawat order: $rate KWD';
  }

  @override
  String get schemeBatchRates =>
      'Presyo bawat order ayon sa batch level ng buwan:';

  @override
  String schemeBatchRow(String level, String rate) {
    return 'Batch $level: $rate KWD';
  }

  @override
  String schemeReduced(String rate, String marks) {
    return 'Bababa sa $rate KWD para sa bawat order ng buwan kung may ma-miss kang Star Day o umabot ka sa $marks marka';
  }

  @override
  String schemeReducedStar(String rate) {
    return 'Bababa sa $rate KWD para sa bawat order ng buwan kung may ma-miss kang Star Day';
  }

  @override
  String get schemeReducedLoses => 'Walang tier bonus ang buwang may bawas';

  @override
  String get schemeTiers =>
      'Tier bonus (ang pinakamataas na tier lang na naabot mo):';

  @override
  String schemeTierRow(String orders, String amount) {
    return '$orders order: $amount KWD';
  }

  @override
  String get schemeMarks => 'Kaltas sa attendance marks:';

  @override
  String schemeMarkRow(String marks, String amount) {
    return '$marks marka: $amount KWD';
  }

  @override
  String schemeTarget(String orders, String days) {
    return 'Target: $orders order at $days valid na araw kada buwan';
  }

  @override
  String schemeMissing(String rate) {
    return 'Bawat order na kulang sa target ay may kaltas na $rate KWD';
  }

  @override
  String get schemeNoMissing =>
      'Walang kaltas para sa mga order na kulang sa target';

  @override
  String schemeCovers(String items) {
    return 'Ang kumpanya ang nagbabayad: $items';
  }

  @override
  String get schemeCoversNone =>
      'Ikaw ang nagbabayad ng gastos: maintenance, tirahan, gas at SIM';

  @override
  String get schemePlatformRates =>
      'Sariling patakaran ng platform: basic na sahod at mga rate ng kumpanya';

  @override
  String get expense_maintenance => 'maintenance';

  @override
  String get expense_housing => 'tirahan';

  @override
  String get expense_gas => 'gas';

  @override
  String get expense_sim => 'SIM';

  @override
  String get schemeChoose => 'Pay scheme';

  @override
  String get schemeChooseHint =>
      'Piliin ang scheme na pinagtatrabahuhan mo. Susuriin ito ng opisina kasama ng pagpaparehistro mo, at puwede kang humiling na palitan ito mamaya mula sa app.';

  @override
  String payslipScheme(String name) {
    return 'Paano kinuwenta ng scheme mo ang buwan: $name';
  }

  @override
  String get payItem_orders_pay => 'Mga order';

  @override
  String get payItem_tier_bonus => 'Tier bonus';

  @override
  String get payItem_missing_target => 'Kulang sa target';

  @override
  String get payItem_marks_deduction => 'Attendance marks';

  @override
  String get payItem_uncovered_penalty => 'Mga hindi nakaltas (para suriin)';

  @override
  String payWhyOrders(String orders, String rate) {
    return '$orders order × $rate KWD';
  }

  @override
  String payWhyBatch(String level) {
    return 'batch $level';
  }

  @override
  String get payWhyReducedStar => 'binawasang presyo: may na-miss na Star Day';

  @override
  String get payWhyReducedMarks => 'binawasang presyo: attendance marks';

  @override
  String payWhyTier(String orders, String from) {
    return '$orders order: ang $from na tier';
  }

  @override
  String payWhyMissing(String missing, String target, String rate) {
    return '$missing order na kulang sa $target × $rate KWD';
  }

  @override
  String payWhyMarks(String marks) {
    return '$marks attendance marks';
  }

  @override
  String get payWhyUncovered =>
      'Hindi kinakaltas ang mga kaltas na lampas sa sahod ng buwan, at hindi bumababa sa zero ang net: susuriin ng opisina ang natitira';

  @override
  String get noticesTitle => 'Mga notification';

  @override
  String get noticesNone => 'Wala pang notification';

  @override
  String get nameLabel => 'Pangalan';

  @override
  String get obOnFile =>
      'Ang mga naka-lock na field ay nasa file ng kumpanya. Kung may mali, hilingin sa opisina na itama ito.';

  @override
  String get nationalityPick => 'Piliin ang nasyonalidad mo';

  @override
  String get searchArEn => 'Maghanap sa Arabic o English';

  @override
  String get noMatches => 'Walang tugma';

  @override
  String get ibanInvalid =>
      'May maling character sa IBAN na ito (hindi tugma ang check digits): kopyahin ito mula sa app ng bangko mo';

  @override
  String obFieldsInvalid(String fields) {
    return 'Suriin ang mga field na ito: $fields';
  }

  @override
  String ibanLengthKw(int count) {
    return 'May 30 character ang Kuwaiti IBAN at nagsisimula sa KW; ang isang ito ay may $count';
  }

  @override
  String get driverWorking => 'Nasa trabaho ang driver';

  @override
  String get driverNotWorking => 'Wala sa trabaho ang driver';

  @override
  String greeting(String name) {
    return 'Kumusta, $name';
  }

  @override
  String get yourCar => 'Ang kotse mo';

  @override
  String get quickActions => 'Mabilisang aksyon';

  @override
  String get dayNotStarted => 'Hindi mo pa sinisimulan ang araw mo';

  @override
  String get dayNotStartedHint =>
      'Magsimula sa litrato ng odometer gamit ang camera';

  @override
  String dayStartedAt(String time) {
    return 'Nagsimula ang araw mo nang $time';
  }

  @override
  String dayStartKm(String km) {
    return 'Panimulang odometer $km';
  }

  @override
  String get dayEndedHint => 'Magtatrabaho ulit ngayong araw? Magsimula muli';

  @override
  String get agoNow => 'ngayon lang';

  @override
  String agoMinutes(String n) {
    return '$n min ang nakalipas';
  }

  @override
  String agoHours(String n) {
    return '$n oras ang nakalipas';
  }

  @override
  String agoDays(String n) {
    return '$n araw ang nakalipas';
  }

  @override
  String lastSentAgo(String ago) {
    return 'huling naipadala $ago';
  }

  @override
  String get qaBalance => 'Balanse ko';

  @override
  String get qaReceipts => 'Mga resibo ko';

  @override
  String qaReceiptsWaiting(String n) {
    return '$n na kukumpirmahin';
  }

  @override
  String get qaReceiptsDone => 'Kumpirmado lahat';

  @override
  String get qaMaintenanceSub => 'Sira o tala';

  @override
  String get qaAccidentSub => 'Mga litrato + police report';

  @override
  String get qaReportSub => 'Mga order at cash ngayong araw';

  @override
  String get qaFinesSub => 'Mga multa sa kotse mo';

  @override
  String get qaStatementSub => 'Buwanang screenshot ng platform';

  @override
  String get qaPayslipsSub => 'Ang buwanang sahod mo';

  @override
  String get qaSchemesSub => 'Paano kinukuwenta ang sahod mo';

  @override
  String get tabWork => 'Pang-araw-araw na trabaho';

  @override
  String get todayReport => 'Report ngayong araw';

  @override
  String get workReportSent => 'Naipadala na ang report ngayong araw';

  @override
  String get workReportDue => 'Hindi pa naipadala ang report ngayong araw';

  @override
  String get workReportDueHint =>
      'Ipadala ang mga order at cash gaya ng nasa app ng platform';

  @override
  String get sendDailyReport => 'Ipadala ang pang-araw-araw na report';

  @override
  String ordersCash(String orders, String cash) {
    return '$orders order · $cash';
  }

  @override
  String get myRequests => 'Mga request ko';

  @override
  String get cashBalanceTitle => 'Balanse mo (KWD)';

  @override
  String cashPendingPart(String amount) {
    return '$amount dito ang hindi pa naaprubahan';
  }

  @override
  String cashLimit(String amount) {
    return 'Alert limit $amount';
  }

  @override
  String employeeAt(String number, String company) {
    return '$number · $company';
  }

  @override
  String get thisPhone => 'Ang teleponong ito';

  @override
  String get takeOdometerPhoto => 'Kunan ang odometer';

  @override
  String get cameraOnly => 'Camera lang — hindi puwede ang gallery';

  @override
  String lastKmHint(String km) {
    return 'Huling naitalang reading ng kotse: $km';
  }

  @override
  String get cashHint => 'Gaya ng nasa app ng delivery company';

  @override
  String get mntDescriptionHint => 'hal. may ingay kapag nagpe-preno';

  @override
  String get accSend => 'Ipadala ang report';

  @override
  String get workReportQueued =>
      'Naka-save sa telepono ang report ngayong araw';

  @override
  String get reportQueuedForDay =>
      'Naka-save sa telepono ang report ng araw na ito at kusang ipapadala kapag bumalik ang koneksyon. Huwag itong ipadala ulit.';

  @override
  String ordersN(String n) {
    return '$n order';
  }

  @override
  String get workReportDueHintDays =>
      'Ipadala ang mga order at kung binilang na valid ang araw';

  @override
  String get qaReportSubDays => 'Mga order ngayong araw at valid na araw';

  @override
  String get notSentYet => 'Hindi pa naipadala';

  @override
  String get fuel => 'Gasolina';

  @override
  String get qaFuelSub => 'Gasolinang binayaran mula sa cash';

  @override
  String get fuelTitle => 'Gasolinang binayaran mula sa cash';

  @override
  String get fuelIntro =>
      'Kunan ang resibo ng gasolina at ilagay ang halaga. Susuriin ito ng accountant kapag natanggap niya ang cash mo; kapag naaprubahan, ibabawas ang halaga sa cash na hawak mo.';

  @override
  String get fuelReceipt => 'Litrato ng resibo ng gasolina';

  @override
  String get fuelTakeReceipt => 'Kunan ang resibo';

  @override
  String get fuelReceiptMissing => 'Kailangan ang litrato ng resibo';

  @override
  String get fuelAmount => 'Halagang binayaran';

  @override
  String get fuelAmountInvalid =>
      'Ilagay ang halaga sa KWD, hanggang 3 decimal';

  @override
  String fuelAmountMax(String max) {
    return 'Hanggang $max KWD lang ang isang resibo';
  }

  @override
  String get fuelOdometer => 'Reading ng odometer (opsyonal)';

  @override
  String get fuelNotes => 'Mga tala (opsyonal)';

  @override
  String get fuelSend => 'Ipadala para suriin';

  @override
  String get fuelMine => 'Mga resibo ng gasolina';

  @override
  String get fuelNone => 'Wala pang resibo ng gasolina';

  @override
  String get fuelPending => 'Naghihintay ng pagsusuri';

  @override
  String fuelApproved(String amount) {
    return 'Naaprubahan ($amount)';
  }

  @override
  String get fuelRejected => 'Tinanggihan';

  @override
  String get fuelOff_fuel_card =>
      'May fuel card ka mula sa kumpanya: ang opisina ang naglo-load nito, at hindi kinukuha ang gasolina mula sa cash mo.';

  @override
  String get fuelOff_not_covered =>
      'Ikaw ang sumasagot sa gasolina ayon sa pay scheme mo, kaya hindi ito sinisingil sa kumpanya.';

  @override
  String get fuelOff_no_vehicle =>
      'Walang sasakyan sa pangangalaga mo ngayon: nire-record ang gasolina para sa kotseng hawak mo.';

  @override
  String get kind_fuel => 'Resibo ng gasolina';

  @override
  String get moveFuel => 'Gasolina';

  @override
  String get vehicleChangePlate => 'Numero ng plaka ng ibang sasakyan';

  @override
  String get vehicleChangePlateHint => '12-34567';

  @override
  String vehicleChangePendingFor(String plate) {
    return 'Sinusuri ang request mong lumipat sa $plate';
  }

  @override
  String get claimVehicle => 'Magrehistro ng bagong kotse';

  @override
  String get claimVehicleHint =>
      'Kumuha ka ng kotse? Irehistro ito rito kasama ang reading ng odometer; magsisimula ang pangangalaga mo kapag inaprubahan ng opisina.';

  @override
  String get claimTitle => 'Magrehistro ng bagong kotse';

  @override
  String get claimPlate => 'Numero ng plaka ng kotse';

  @override
  String get claimIntro =>
      'Kunan ang odometer gamit ang camera at ilagay ang reading. Mapupunta sa opisina ang request; kapag naaprubahan, sa iyo na ang kotse mula sa oras ng litrato.';

  @override
  String get claimConditionPhotos =>
      'Mga litrato ng kondisyon ng kotse (opsyonal)';

  @override
  String get claimSend => 'Ipadala sa opisina';

  @override
  String claimPending(String plate) {
    return 'Naghihintay ng pag-apruba ng opisina ang request mong kunin ang kotseng $plate';
  }

  @override
  String claimRejected(String plate, String reason) {
    return 'Tinanggihan ng opisina ang request mong kunin ang kotseng $plate: $reason';
  }

  @override
  String get kind_vehicle_claim => 'Pagrehistro ng kotse';

  @override
  String get mntNoCenter =>
      'Walang available na maintenance center: tawagan ang opisina';

  @override
  String mntInMaintenance(String center) {
    return 'Nasa maintenance center ang kotse mo: $center';
  }

  @override
  String get mntInMaintenanceAny => 'Nasa maintenance center ang kotse mo';

  @override
  String get mntInMaintenanceHint =>
      'Nasa pangangalaga mo pa rin ang kotse, pero walang araw ng trabaho na magsisimula gamit ito hangga\'t hindi mo ito nakukuha sa center at kinukumpirma rito.';

  @override
  String get fieldYes => 'Oo';

  @override
  String get fieldNo => 'Hindi';

  @override
  String get fieldInvalid => 'Hindi valid na halaga';

  @override
  String get choose => 'Pumili';

  @override
  String get objectPayslip => 'Tumutol sa payslip na ito';

  @override
  String get objectLine => 'Tumutol sa linyang ito';

  @override
  String get objectionTitle => 'Pagtutol sa payslip';

  @override
  String objectionOn(String what) {
    return 'Tungkol sa: $what';
  }

  @override
  String get objectionWhole => 'Ang buong payslip';

  @override
  String get objectionReason => 'Bakit ka tumututol';

  @override
  String get objectionReasonShort =>
      'Isulat ang dahilan (hindi bababa sa 3 titik)';

  @override
  String get objectionFile => 'Litratong nagpapakita nito (opsyonal)';

  @override
  String get objectionCamera => 'Camera';

  @override
  String get objectionGallery => 'Gallery';

  @override
  String get objectionSent => 'Naipadala ang pagtutol mo; sasagot ang opisina';

  @override
  String get objectionQueued =>
      'Ipapadala ang pagtutol mo kapag bumalik ang koneksyon';

  @override
  String get myObjections => 'Mga pagtutol ko';

  @override
  String objectionResponse(String text) {
    return 'Ang opisina: $text';
  }

  @override
  String objectionAction(String text) {
    return 'Aksyong ginawa: $text';
  }

  @override
  String get objectionStatus_open => 'Bukas';

  @override
  String get objectionStatus_in_review => 'Sinusuri';

  @override
  String get objectionStatus_accepted => 'Tinanggap';

  @override
  String get objectionStatus_rejected => 'Tinanggihan';

  @override
  String get objectionStatus_closed => 'Sarado';

  @override
  String get objectionInstallment => 'Isang hulog';

  @override
  String vehicleChangeApprovedFor(String plate) {
    return 'Naaprubahan ang paglipat mo sa $plate: kunin ito sa opisina';
  }

  @override
  String get receiptReversed => 'Kinansela';

  @override
  String pickupReplacementTitle(String plate) {
    return 'Ang pamalit na kotse $plate';
  }

  @override
  String get pickupReplacementHint =>
      'Ibabalik mo ito kapag kinuha mo ang kotse mo: kunan ang odometer nito at ilagay ang reading.';

  @override
  String get pickupReplacementPhoto =>
      'Litrato ng odometer ng pamalit na kotse';

  @override
  String get fuelLitres => 'Litro (opsyonal)';

  @override
  String get fuelLitresInvalid =>
      'Ilagay ang litro gaya ng nasa resibo (hanggang 500)';

  @override
  String get fuelLitresUnit => 'L';

  @override
  String get replacementCar => 'Pamalit na kotse — nasa center ang kotse mo';

  @override
  String outboxAttention(String reason) {
    return 'Kailangan ng atensyon mo: $reason';
  }

  @override
  String get outboxTooOld => 'hindi naipadala sa loob ng dalawang araw';

  @override
  String get outboxKeptFailing => 'hindi ito matanggap ng server';

  @override
  String outboxAttentionCount(int n) {
    return '$n ang kailangan ng atensyon mo';
  }

  @override
  String get startFailedTitle => 'Hindi nakapagsimula ang app';

  @override
  String get startFailedBody =>
      'May nangyaring mali habang naglo-load. Suriin ang koneksyon at subukan muli.';

  @override
  String get activationReplaceTitle => 'Palitan ang naka-sign in na driver?';

  @override
  String get activationReplaceBody =>
      'May driver nang naka-sign in sa teleponong ito. Kapag in-activate ang link na ito, masa-sign out siya at mabubura ang anumang hindi pa niya naipapadala.';

  @override
  String get activationReplaceConfirm => 'I-activate';

  @override
  String get trackingActive => 'Ipinapadala ang lokasyon';

  @override
  String get trackingStale => 'Hindi dumarating ang lokasyon';

  @override
  String get trackingUnknown => 'Hindi alam ang status ng pag-track';

  @override
  String noticeBigActive(String time) {
    return 'Huling lokasyon na naipadala $time';
  }

  @override
  String noticeBigStale(String time) {
    return 'Walang lokasyon mula $time. Buksan ang app at suriin ang settings ng lokasyon';
  }

  @override
  String get noticeBigStaleNever =>
      'Wala pang naipadalang lokasyon. Buksan ang app at suriin ang settings ng lokasyon';

  @override
  String get noticeBigOff => 'Hindi tina-track ang lokasyon mo ngayon';

  @override
  String get openApp => 'Buksan ang app';

  @override
  String get alertsChannel => 'Mahahalagang alerto';

  @override
  String offlineSince(String time) {
    return 'Offline · huling update $time';
  }

  @override
  String get statusCall => 'Tumawag';

  @override
  String get statusDone => 'Tapos na';

  @override
  String get statusCheckSettings => 'Suriin ang settings';

  @override
  String get statusOpenCash => 'Cash';

  @override
  String get statusOpenCustody => 'Kotse ko';

  @override
  String get statusOpenMaintenance => 'Maintenance';

  @override
  String get statusOpenDocuments => 'Mga dokumento ko';

  @override
  String get statusOpenContact => 'Mga detalye';

  @override
  String statusMore(String count) {
    return 'at $count pang alerto';
  }

  @override
  String statusDaySummary(String count) {
    return 'Mga session ngayong araw: $count';
  }

  @override
  String get statusContactSent => 'Nasabihan na ang supervisor mo';

  @override
  String get statusDialFailed => 'Hindi makatawag gamit ang teleponong ito';
}
