// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Swahili (`sw`).
class AppLocalizationsSw extends AppLocalizations {
  AppLocalizationsSw([String locale = 'sw']) : super(locale);

  @override
  String get appTitle => 'Programu ya dereva';

  @override
  String get retry => 'Jaribu tena';

  @override
  String get cancel => 'Ghairi';

  @override
  String get continueBtn => 'Endelea';

  @override
  String get save => 'Hifadhi';

  @override
  String get send => 'Tuma';

  @override
  String get back => 'Rudi';

  @override
  String get done => 'Imekamilika';

  @override
  String get networkError => 'Hakuna muunganisho wa intaneti. Jaribu tena.';

  @override
  String get genericError => 'Hitilafu imetokea. Jaribu tena.';

  @override
  String get kwd => 'KWD';

  @override
  String get km => 'km';

  @override
  String get signInTitle => 'Ingia';

  @override
  String get signInHint =>
      'Weka nambari yako ya simu iliyosajiliwa na kampuni. Msimbo wa kuingia unafika kwenye WhatsApp.';

  @override
  String get phoneLabel => 'Simu';

  @override
  String get phoneInvalid =>
      'Tarakimu 8 za Kuwait, au nambari ya kimataifa inayoanza na +';

  @override
  String get sendCode => 'Tuma msimbo';

  @override
  String get activationTip =>
      'Ukipokea kiungo cha kuwezesha kwenye WhatsApp, kifungue kwenye simu hii: hakuna haja ya msimbo.';

  @override
  String get otpTitle => 'Msimbo wa kuingia';

  @override
  String otpHint(String phone) {
    return 'Weka msimbo wa tarakimu 6 uliotumwa kwenye WhatsApp kwa $phone.';
  }

  @override
  String get otpLabel => 'Msimbo';

  @override
  String get verify => 'Ingia';

  @override
  String get otpResend => 'Hukupata msimbo? Tuma tena';

  @override
  String get activating => 'Inawezesha programu kwenye simu hii…';

  @override
  String get activationFailed => 'Kuwezesha kumeshindwa';

  @override
  String get permTitle => 'Ruhusa za programu';

  @override
  String get permIntro =>
      'Ili kufuatilia gari likiwa chini ya jukumu lako, hata programu ikiwa imefungwa, programu inahitaji ruhusa hizi. Eneo lako linarekodiwa tu wakati gari liko chini ya jukumu lako.';

  @override
  String get permLocation => 'Eneo: “Ruhusu kila wakati”';

  @override
  String get permLocationWhy =>
      'Ili msimamizi aone gari likiwa chini ya jukumu lako.';

  @override
  String get permNotifications => 'Arifa';

  @override
  String get permNotificationsWhy =>
      'Arifa ya kudumu huonekana wakati wa kufuatilia (sheria ya Android).';

  @override
  String get permBattery => 'Puuza uboreshaji wa betri';

  @override
  String get permBatteryWhy => 'Ili simu isisimamishe ufuatiliaji chinichini.';

  @override
  String get permGrant => 'Ruhusu';

  @override
  String get permGranted => 'Imeruhusiwa';

  @override
  String get permSettings => 'Fungua mipangilio';

  @override
  String get permLocationRequired =>
      'Ruhusa ya eneo inahitajika ili kuendelea.';

  @override
  String get gpsOff => 'GPS imezimwa: iwashe kwenye mipangilio ya simu.';

  @override
  String get obTitle => 'Kamilisha usajili';

  @override
  String get obIntro =>
      'Weka taarifa zako na upige picha za hati zako na gari. Hakuna kitu rasmi kabla kampuni haijakagua.';

  @override
  String obRejected(String reason) {
    return 'Usajili wako umerudishwa: $reason';
  }

  @override
  String get obStepData => 'Taarifa';

  @override
  String get obStepDocs => 'Hati';

  @override
  String get obStepVehicle => 'Gari';

  @override
  String get obStepReview => 'Ukaguzi';

  @override
  String get civilId => 'Kitambulisho cha kiraia';

  @override
  String get civilIdInvalid => 'Kitambulisho cha kiraia kina tarakimu 12';

  @override
  String get nationality => 'Uraia';

  @override
  String get docNumber => 'Nambari ya hati';

  @override
  String get docExpiry => 'Tarehe ya kuisha';

  @override
  String get docFront => 'Mbele';

  @override
  String get docBack => 'Nyuma';

  @override
  String get pickPhoto => 'Picha';

  @override
  String get takePhoto => 'Piga picha';

  @override
  String get fromGallery => 'Kutoka kwenye matunzio';

  @override
  String get uploading => 'Inapakia…';

  @override
  String get required => 'Inahitajika';

  @override
  String get plate => 'Nambari ya gari';

  @override
  String get plateHint => 'Kama ilivyo kwenye bamba, mf. 18/23456';

  @override
  String get odometerKm => 'Odomita (km)';

  @override
  String get odometerPhoto => 'Picha ya odomita';

  @override
  String get noVehicle => 'Sina gari kwa sasa';

  @override
  String get vehiclePhotos => 'Picha za hali ya gari';

  @override
  String get obSubmit => 'Tuma kwa ukaguzi';

  @override
  String obMissing(String items) {
    return 'Kamilisha: $items';
  }

  @override
  String get obWaitingTitle => 'Taarifa zako zinakaguliwa';

  @override
  String get obWaitingText =>
      'Utapata ujumbe wa WhatsApp zikikubaliwa au kama kuna kitu cha kurekebisha.';

  @override
  String get refresh => 'Onyesha upya';

  @override
  String get position_front => 'Mbele';

  @override
  String get position_back => 'Nyuma';

  @override
  String get position_left => 'Upande wa kushoto';

  @override
  String get position_right => 'Upande wa kulia';

  @override
  String get position_interior => 'Ndani';

  @override
  String get position_other => 'Nyingine';

  @override
  String get tabHome => 'Nyumbani';

  @override
  String get tabCash => 'Pesa taslimu';

  @override
  String get tabAccount => 'Akaunti';

  @override
  String get noCustody => 'Hakuna gari chini ya jukumu lako sasa';

  @override
  String get noCustodyHint =>
      'Ukikabidhiwa gari litaonekana hapa na ufuatiliaji utaanza wenyewe.';

  @override
  String custodySince(String when) {
    return 'Chini ya jukumu lako tangu $when';
  }

  @override
  String lastKm(String km) {
    return 'Usomaji wa mwisho: $km km';
  }

  @override
  String get trackingOn => 'Ufuatiliaji umewashwa';

  @override
  String get trackingOff => 'Ufuatiliaji umezimwa';

  @override
  String trackingWaiting(String count) {
    return 'Vinasubiri kutumwa: $count';
  }

  @override
  String get startDay => 'Anza siku';

  @override
  String get startDayDone => 'Siku imeanza';

  @override
  String get endDay => 'Maliza siku';

  @override
  String get dailyReport => 'Ripoti ya siku';

  @override
  String get outboxTitle => 'Vinasubiri kutumwa';

  @override
  String get outboxQueued => 'Vitatumwa vyenyewe mtandao ukirudi';

  @override
  String outboxFailed(String reason) {
    return 'Haikukubaliwa: $reason';
  }

  @override
  String get outboxDiscard => 'Ondoa';

  @override
  String get kind_odometer => 'Usomaji wa odomita';

  @override
  String get kind_report => 'Ripoti ya siku';

  @override
  String get startDayTitle => 'Mwanzo wa siku';

  @override
  String get endDayDone => 'Siku imeisha';

  @override
  String get startAgain => 'Anza tena';

  @override
  String reportAddsToDay(String orders) {
    return 'Ripoti hii inaongezwa kwa ulichotuma leo ($orders oda). Weka oda na pesa taslimu za kipindi hiki tu.';
  }

  @override
  String reportSession(String n) {
    return 'Kipindi $n';
  }

  @override
  String get endReadingIntro =>
      'Kabla ya ripoti ya leo: picha na usomaji wa odomita wa mwisho wa siku. Usomaji unatumwa kwanza, kisha ripoti.';

  @override
  String get status_returned => 'Imerudishwa kwa marekebisho';

  @override
  String get editReportTitle => 'Hariri ripoti';

  @override
  String get changeReportTitle => 'Omba kubadilisha ripoti iliyokubaliwa';

  @override
  String get changeReportIntro =>
      'Ripoti hii imekubaliwa: ombi lako linaenda ofisini na litatumika likikubaliwa.';

  @override
  String get changeReason => 'Sababu ya mabadiliko';

  @override
  String get newScreenshotOptional => 'Picha mpya ya skrini (si lazima)';

  @override
  String get reportExistsForDay =>
      'Tayari umetuma ripoti ya siku hii. Ihariri badala ya kutuma ripoti ya pili.';

  @override
  String get editReport => 'Hariri ripoti';

  @override
  String get changePending => 'Mabadiliko yanasubiri ofisi';

  @override
  String returnedNote(Object note) {
    return 'Imerudishwa na ofisi: $note';
  }

  @override
  String get myCar => 'Gari langu';

  @override
  String get carSince => 'Chini ya jukumu lako tangu';

  @override
  String get lastReading => 'Usomaji wa mwisho wa odomita';

  @override
  String get registrationExpiry => 'Usajili unaisha';

  @override
  String get requestVehicleChange => 'Omba gari jingine';

  @override
  String get vehicleChangeReason => 'Sababu';

  @override
  String get vehicleChangePending =>
      'Ombi lako la gari jingine liko kwa msimamizi';

  @override
  String vehicleChangeRejected(Object note) {
    return 'Ombi lako la gari jingine limekataliwa: $note';
  }

  @override
  String get profileTitle => 'Taarifa zangu';

  @override
  String get employeeNumber => 'Nambari ya mfanyakazi';

  @override
  String get companyLabel => 'Kampuni';

  @override
  String get platformLabel => 'Jukwaa';

  @override
  String get bankLabel => 'Benki';

  @override
  String get myDocuments => 'Hati zangu';

  @override
  String get docValid => 'Halali';

  @override
  String docExpiring(Object days) {
    return 'Inaisha baada ya siku $days';
  }

  @override
  String get docExpired => 'Imeisha muda';

  @override
  String get docMissing => 'Haipo kwenye kumbukumbu';

  @override
  String docExpires(Object date) {
    return 'Inaisha $date';
  }

  @override
  String get uploadRenewal => 'Pakia hati iliyofanywa upya';

  @override
  String get renewalPending => 'Upyaji unasubiri ofisi';

  @override
  String renewalRejected(Object note) {
    return 'Upyaji umekataliwa: $note';
  }

  @override
  String get newExpiry => 'Tarehe mpya ya kuisha';

  @override
  String get documentNumber => 'Nambari ya hati (si lazima)';

  @override
  String get documentPhoto => 'Picha ya hati';

  @override
  String get pickDate => 'Chagua tarehe';

  @override
  String cashNearLimit(Object limit) {
    return 'Salio lako linakaribia kikomo cha tahadhari ($limit): kabidhi pesa taslimu hivi karibuni.';
  }

  @override
  String get movements => 'Miamala';

  @override
  String get noMovements => 'Hakuna miamala bado';

  @override
  String get moveCollection => 'Pesa taslimu za ripoti ya siku';

  @override
  String get moveReceipt => 'Imekabidhiwa kwa risiti';

  @override
  String get moveAdjustment => 'Marekebisho';

  @override
  String get moveReversal => 'Kubatilisha';

  @override
  String get moveSettlement => 'Malipo ya mwisho wa huduma';

  @override
  String get moveOpening => 'Salio la kuanzia';

  @override
  String get endDayTitle => 'Mwisho wa siku';

  @override
  String get odometerIntro =>
      'Piga picha ya odomita ikionekana wazi, kisha andika usomaji kama unavyoonekana kwenye picha.';

  @override
  String get retake => 'Piga tena';

  @override
  String kmLower(String km) {
    return 'Ni chini ya usomaji wa mwisho ($km km). Hakikisha: utakaguliwa.';
  }

  @override
  String get kmInvalid => 'Andika usomaji kwa tarakimu';

  @override
  String get photoRequired => 'Picha inahitajika';

  @override
  String get sentTitle => 'Imetumwa';

  @override
  String get queuedTitle => 'Imehifadhiwa kwenye simu';

  @override
  String get sentText => 'Kampuni imeipokea.';

  @override
  String get queuedText =>
      'Hakuna mtandao sasa. Itatumwa yenyewe, pamoja na muda wake halisi, muunganisho ukirudi.';

  @override
  String get reportTitle => 'Ripoti ya siku';

  @override
  String get reportDate => 'Siku ya kazi';

  @override
  String get today => 'Leo';

  @override
  String get yesterday => 'Jana';

  @override
  String get dayBefore => 'Juzi';

  @override
  String get ordersCount => 'Oda';

  @override
  String get cashAmount => 'Pesa taslimu zilizokusanywa';

  @override
  String get cashInvalid => 'Kiasi chenye desimali zisizozidi tatu';

  @override
  String get screenshot =>
      'Picha ya skrini ya muhtasari wa siku kutoka programu ya usafirishaji';

  @override
  String get notes => 'Maelezo';

  @override
  String get recentReports => 'Ripoti za hivi karibuni';

  @override
  String get status_submitted => 'Inasubiri ukaguzi';

  @override
  String get status_approved => 'Imekubaliwa';

  @override
  String get status_rejected => 'Imekataliwa';

  @override
  String approvedCash(String amount) {
    return 'Imekubaliwa: $amount';
  }

  @override
  String get cashTitle => 'Pesa taslimu';

  @override
  String get cashTotal => 'Pesa taslimu ulizonazo';

  @override
  String get cashPosted => 'Imekubaliwa';

  @override
  String get cashPending => 'Inasubiri ukaguzi';

  @override
  String cashOverLimit(String limit) {
    return 'Zaidi ya kikomo ($limit): kabidhi pesa taslimu kwa keshia.';
  }

  @override
  String get receipts => 'Risiti';

  @override
  String receiptNo(String no) {
    return 'Risiti nambari $no';
  }

  @override
  String get confirmReceipt => 'Nathibitisha';

  @override
  String get receiptConfirmed => 'Imethibitishwa';

  @override
  String confirmReceiptQ(String amount) {
    return 'Je, ulimkabidhi keshia $amount KWD?';
  }

  @override
  String get noReceipts => 'Hakuna risiti bado';

  @override
  String get language => 'Lugha';

  @override
  String get trackingDetails => 'Hali ya ufuatiliaji';

  @override
  String lastUpload(String when) {
    return 'Ilitumwa mwisho: $when';
  }

  @override
  String get never => 'bado';

  @override
  String appVersion(String version) {
    return 'Toleo $version';
  }

  @override
  String get signOut => 'Toka';

  @override
  String get signOutQ =>
      'Ufuatiliaji utasimama na utahitaji kuwezeshwa upya ili kuingia. Uendelee?';

  @override
  String get blockedTitle => 'Akaunti yako imesimamishwa';

  @override
  String get blockedText => 'Wasiliana na msimamizi wako.';

  @override
  String get obReady => 'Kila kitu kiko tayari: kitume kwa ukaguzi.';

  @override
  String get maintenance => 'Matengenezo';

  @override
  String get maintenanceTitle => 'Maombi ya matengenezo';

  @override
  String get kind_maintenance => 'Ombi la matengenezo';

  @override
  String get mntNew => 'Ombi jipya la matengenezo';

  @override
  String get mntIntro =>
      'Eleza tatizo na upige picha. Gari lililopata ajali hutengenezwa kupitia ofisi.';

  @override
  String get mntDirectIntro =>
      'Eleza tatizo, piga picha, na uchague kituo cha matengenezo utakachopeleka gari. Ombi linaenda moja kwa moja kituoni, gari linabaki chini ya jukumu lako, na utaarifiwa likiwa tayari.';

  @override
  String get mntCenter => 'Kituo cha matengenezo';

  @override
  String get mntPickedUp => 'Nimechukua gari';

  @override
  String get pickupTitle => 'Kuchukua gari kutoka kituoni';

  @override
  String get pickupIntro =>
      'Piga picha ya odomita na uweke usomaji unapochukua gari: linarudi chini ya jukumu lako na unaanza siku yako kama kawaida.';

  @override
  String get kind_pickup => 'Gari limechukuliwa kutoka matengenezo';

  @override
  String get mntNoVehicle =>
      'Matengenezo huombwa kwa gari lililo chini ya jukumu lako. Huna gari kwa sasa.';

  @override
  String get mntKind => 'Aina';

  @override
  String get mntDescription => 'Tatizo ni nini';

  @override
  String get mntOdometer => 'Odomita (si lazima)';

  @override
  String get mntPhotos => 'Picha (hadi 4)';

  @override
  String get mntAddPhoto => 'Picha';

  @override
  String get mntNone => 'Hakuna maombi ya matengenezo';

  @override
  String mntRequestNo(String number) {
    return 'Ombi #$number';
  }

  @override
  String mntAtCenter(String center) {
    return 'Kituo: $center';
  }

  @override
  String mntReadyBanner(String plate, String center) {
    return 'Gari lako $plate liko tayari kuchukuliwa $center';
  }

  @override
  String mntRejected(String reason) {
    return 'Limekataliwa: $reason';
  }

  @override
  String get mntSent => 'Ombi lako la matengenezo limetumwa kituoni';

  @override
  String get mntKind_periodic => 'Huduma ya kawaida';

  @override
  String get mntKind_mechanical => 'Mitambo';

  @override
  String get mntKind_electrical => 'Umeme';

  @override
  String get mntKind_tyres => 'Matairi';

  @override
  String get mntKind_battery => 'Betri';

  @override
  String get mntKind_ac => 'Kiyoyozi';

  @override
  String get mntKind_bodywork => 'Bodi ya gari';

  @override
  String get mntKind_other => 'Nyingine';

  @override
  String get mntStatus_requested => 'Inasubiri idhini';

  @override
  String get mntStatus_approved => 'Imeidhinishwa';

  @override
  String get mntStatus_rejected => 'Imekataliwa';

  @override
  String get mntStatus_referred => 'Imetumwa kituoni';

  @override
  String get mntStatus_at_center => 'Iko kituoni';

  @override
  String get mntStatus_ready => 'Tayari kuchukuliwa';

  @override
  String get mntStatus_picked_up => 'Imechukuliwa';

  @override
  String get mntStatus_closed => 'Imefungwa';

  @override
  String get mntStatus_cancelled => 'Imeghairiwa';

  @override
  String get mntTapToRemove => 'gusa ili kuondoa';

  @override
  String get accident => 'Ripoti ajali';

  @override
  String get accidentsTitle => 'Ajali';

  @override
  String get kind_accident => 'Ripoti ya ajali';

  @override
  String get kind_police_report => 'Ripoti ya polisi';

  @override
  String get accNew => 'Ripoti mpya ya ajali';

  @override
  String get accEmergency => 'Kama kuna aliyejeruhiwa, piga 112 kwanza.';

  @override
  String get accIntro =>
      'Piga picha za gari kutoka pande kadhaa: mbele, nyuma, pande zote mbili na uharibifu. Muda na mahali vinarekodiwa vyenyewe.';

  @override
  String get accNoVehicle =>
      'Ajali inaripotiwa kwa gari ulilonalo. Huna gari kwa sasa: mpigie msimamizi wako.';

  @override
  String get accDescription => 'Nini kilitokea?';

  @override
  String get accInjuries => 'Kuna aliyejeruhiwa';

  @override
  String get accInjuriesNote => 'Maelezo ya majeraha';

  @override
  String get accOtherParty => 'Upande mwingine (nambari ya gari, jina, bima)';

  @override
  String accPhotos(String min) {
    return 'Picha za ajali (angalau $min)';
  }

  @override
  String accPhotosNeeded(String min) {
    return 'Piga angalau picha $min kutoka pande tofauti';
  }

  @override
  String get accPoliceReport => 'Ripoti ya polisi';

  @override
  String get accPoliceReportNo => 'Nambari ya ripoti';

  @override
  String get accPoliceLater =>
      'Huna ripoti bado? Tuma sasa na utume picha ya ripoti ya polisi baadaye kutoka kwenye ajali zako hapa chini.';

  @override
  String get accSendPolice => 'Tuma ripoti ya polisi';

  @override
  String get accNone => 'Hakuna ajali';

  @override
  String accNo(String number) {
    return 'Ajali #$number';
  }

  @override
  String get accStage_review => 'Inakaguliwa';

  @override
  String get accStage_outcome => 'Inasubiri uamuzi wa dhamana';

  @override
  String get accStage_recorded => 'Dhamana imeamuliwa';

  @override
  String get accStage_closed => 'Imefungwa';

  @override
  String get accLiability_none => 'Huna dhamana';

  @override
  String get accLiability_driver => 'Una dhamana';

  @override
  String accLiability_shared(String percent) {
    return 'Dhamana ya pamoja: sehemu yako $percent%';
  }

  @override
  String accDeduction(String total, String count) {
    return 'Makato $total KWD · awamu: $count';
  }

  @override
  String accInstallment(String month, String amount) {
    return '$month: $amount KWD';
  }

  @override
  String accAwaitingPolice(String number) {
    return 'Ajali #$number inasubiri ripoti ya polisi: gusa ili kutuma picha yake';
  }

  @override
  String get fines => 'Faini za barabarani';

  @override
  String get finesTitle => 'Faini za barabarani';

  @override
  String get finesIntro =>
      'Faini za gari ulipokuwa nalo, kulingana na muda wa faini. Kampuni huamua: inazilipa, au zinakatwa kwenye mshahara wako kwa awamu.';

  @override
  String get finesNone => 'Hakuna faini';

  @override
  String get fineStatus_open => 'Inakaguliwa';

  @override
  String get fineStatus_charged => 'Imekatwa kwenye mshahara wako';

  @override
  String get fineStatus_company => 'Inalipwa na kampuni';

  @override
  String get monthlyStatement => 'Taarifa ya mwezi ya jukwaa';

  @override
  String get payslips => 'Hati za mshahara';

  @override
  String get statementTitle => 'Taarifa ya mwezi ya jukwaa';

  @override
  String statementIntro(String platform) {
    return 'Mwanzoni mwa kila mwezi, tuma picha za skrini za muhtasari wa mwezi kutoka programu ya $platform na uandike takwimu kama zinavyoonekana. Ofisi inazilinganisha na picha kabla ya mishahara.';
  }

  @override
  String get statementNoPlatform =>
      'Jukwaa lako bado halijawekwa. Wasiliana na ofisi.';

  @override
  String get statementNoMonth =>
      'Umetuma kila mwezi ulio wazi. Subiri ukaguzi wa ofisi.';

  @override
  String get statementMonth => 'Mwezi';

  @override
  String get statementShots =>
      'Picha za skrini kutoka programu ya jukwaa (hadi 6)';

  @override
  String get statementShotRequired => 'Ongeza angalau picha moja ya skrini';

  @override
  String get statementHistory => 'Ulichotuma';

  @override
  String statementSentDays(String days) {
    return 'Imetumwa: siku halali $days';
  }

  @override
  String statementApprovedDays(String days) {
    return 'Imekubaliwa: siku halali $days';
  }

  @override
  String get statementStatus_submitted => 'Inasubiri ukaguzi';

  @override
  String get statementStatus_approved => 'Imekubaliwa';

  @override
  String get statementStatus_rejected => 'Imekataliwa: itume tena';

  @override
  String get addShot => 'Ongeza picha ya skrini';

  @override
  String get validDays => 'Siku halali';

  @override
  String get ordersTotal => 'Jumla ya oda';

  @override
  String get hoursTotal => 'Jumla ya saa';

  @override
  String get payslipsTitle => 'Hati za mshahara';

  @override
  String get payslipsNone => 'Hakuna hati ya mshahara iliyokubaliwa bado';

  @override
  String get payslipNet => 'Mshahara halisi';

  @override
  String get payslipStatus_approved => 'Imekubaliwa';

  @override
  String get payslipStatus_paid => 'Imelipwa';

  @override
  String get iban => 'IBAN';

  @override
  String get ibanHint =>
      'Mshahara wako hulipwa kwake: inakili kutoka programu ya benki yako';

  @override
  String get bankName => 'Jina la benki';

  @override
  String get civilSignIn => 'Ingia kwa kitambulisho cha kiraia';

  @override
  String get civilSignInHint =>
      'Kama kampuni haina nambari yako ya simu: ingia kwa kitambulisho chako cha kiraia na nenosiri la awali ulilopewa na ofisi, kisha sajili simu yako. Nenosiri linatumika mara moja tu.';

  @override
  String get initialPassword => 'Nenosiri la awali';

  @override
  String get claimContinue => 'Endelea';

  @override
  String claimWelcome(String name) {
    return 'Karibu $name. Weka nambari yako ya simu yenye WhatsApp: msimbo unatumwa kwake, na kuanzia sasa utaingia kwa nambari hiyo.';
  }

  @override
  String get password => 'Nenosiri';

  @override
  String get civilSignInOnly =>
      'Ingia kwa kitambulisho chako cha kiraia na nenosiri lako. Mara ya kwanza: nenosiri la awali ulilopewa na ofisi, kisha utachagua lako mwenyewe.';

  @override
  String get forgotPassword =>
      'Umesahau nenosiri? Muombe msimamizi wako nenosiri jipya la awali.';

  @override
  String choosePassword(String name) {
    return 'Karibu $name. Chagua nenosiri lako: kwa hilo na kitambulisho chako cha kiraia utaingia kuanzia sasa, kwenye simu yoyote. Angalau herufi 8, lisiwe nenosiri la awali wala kitambulisho chako cha kiraia, na usimwambie mtu yeyote.';
  }

  @override
  String get newPassword => 'Nenosiri jipya';

  @override
  String get confirmPassword => 'Andika nenosiri tena';

  @override
  String get passwordTooShort => 'Angalau herufi 8';

  @override
  String get passwordsDiffer => 'Manenosiri mawili hayafanani';

  @override
  String get passwordIsCivilId =>
      'Usitumie kitambulisho chako cha kiraia kama nenosiri';

  @override
  String get saveAndSignIn => 'Hifadhi na uingie';

  @override
  String get validDayQuestion =>
      'Je, programu ya jukwaa ilihesabu siku hii kuwa halali?';

  @override
  String get validDayYes => 'Siku halali';

  @override
  String get validDayNo => 'Si halali';

  @override
  String get paySchemes => 'Mpango wa malipo';

  @override
  String get schemesIntro =>
      'Mpango wako unaamua jinsi mshahara wako unavyohesabiwa kutokana na oda zako. Unaweza kuomba mpango mwingine unaotolewa na jukwaa lako; unaanza tarehe moja ya mwezi ujao ofisi ikikubali.';

  @override
  String get schemeNow => 'Mpango wako mwezi huu';

  @override
  String get schemeNone => 'Ofisi bado haijaweka mpango wako';

  @override
  String schemeNextMonth(String name) {
    return 'Kuanzia mwezi ujao: $name';
  }

  @override
  String get schemeOthers => 'Mipango mingine kwenye jukwaa lako';

  @override
  String get schemeAsk => 'Omba mpango huu';

  @override
  String schemeAskBody(String name, String month) {
    return 'Unaomba “$name” kuanzia $month. Ofisi italikagua na utapata jibu hapa na kwenye WhatsApp.';
  }

  @override
  String get schemeNoteHint => 'Ujumbe kwa ofisi (si lazima)';

  @override
  String get schemeSend => 'Tuma ombi';

  @override
  String get schemeSent => 'Ombi lako limetumwa ofisini';

  @override
  String schemePending(String name, String month) {
    return 'Ombi lako la “$name” kuanzia $month linasubiri ofisi';
  }

  @override
  String schemeApproved(String name, String month) {
    return 'Limekubaliwa: “$name” kuanzia $month';
  }

  @override
  String schemeRejected(String name, String note) {
    return 'Ofisi imekataa “$name”: $note';
  }

  @override
  String get schemeCancel => 'Ghairi ombi';

  @override
  String schemePerOrder(String rate) {
    return 'Kwa kila oda: $rate KWD';
  }

  @override
  String get schemeBatchRates =>
      'Bei ya kila oda kulingana na kiwango cha batch cha mwezi:';

  @override
  String schemeBatchRow(String level, String rate) {
    return 'Batch $level: $rate KWD';
  }

  @override
  String schemeReduced(String rate, String marks) {
    return 'Inashuka hadi $rate KWD kwa kila oda ya mwezi ukikosa Star Day au ukifikia alama $marks';
  }

  @override
  String schemeReducedStar(String rate) {
    return 'Inashuka hadi $rate KWD kwa kila oda ya mwezi ukikosa Star Day';
  }

  @override
  String get schemeReducedLoses => 'Mwezi uliopunguzwa haulipi bonasi ya ngazi';

  @override
  String get schemeTiers =>
      'Bonasi ya ngazi (ngazi ya juu kabisa unayofikia tu):';

  @override
  String schemeTierRow(String orders, String amount) {
    return 'Oda $orders: $amount KWD';
  }

  @override
  String get schemeMarks => 'Makato ya alama za mahudhurio:';

  @override
  String schemeMarkRow(String marks, String amount) {
    return 'Alama $marks: $amount KWD';
  }

  @override
  String schemeTarget(String orders, String days) {
    return 'Lengo: oda $orders na siku halali $days kwa mwezi';
  }

  @override
  String schemeMissing(String rate) {
    return 'Kila oda iliyopungua kwenye lengo inakata $rate KWD';
  }

  @override
  String get schemeNoMissing =>
      'Hakuna makato kwa oda zilizopungua kwenye lengo';

  @override
  String schemeCovers(String items) {
    return 'Kampuni inalipa: $items';
  }

  @override
  String get schemeCoversNone =>
      'Unalipa gharama: matengenezo, makazi, mafuta na laini ya simu';

  @override
  String get schemePlatformRates =>
      'Kanuni ya jukwaa yenyewe: mshahara wa msingi na viwango vya kampuni';

  @override
  String get expense_maintenance => 'matengenezo';

  @override
  String get expense_housing => 'makazi';

  @override
  String get expense_gas => 'mafuta';

  @override
  String get expense_sim => 'laini ya simu';

  @override
  String get schemeChoose => 'Mpango wa malipo';

  @override
  String get schemeChooseHint =>
      'Chagua mpango unaofanyia kazi. Ofisi itaukagua pamoja na usajili wako, na unaweza kuomba kuubadilisha baadaye kupitia programu.';

  @override
  String payslipScheme(String name) {
    return 'Jinsi mpango wako ulivyohesabu mwezi: $name';
  }

  @override
  String get payItem_orders_pay => 'Oda';

  @override
  String get payItem_tier_bonus => 'Bonasi ya ngazi';

  @override
  String get payItem_missing_target => 'Upungufu wa lengo';

  @override
  String get payItem_marks_deduction => 'Alama za mahudhurio';

  @override
  String get payItem_uncovered_penalty => 'Makato yasiyokusanywa (kwa ukaguzi)';

  @override
  String payWhyOrders(String orders, String rate) {
    return 'Oda $orders × $rate KWD';
  }

  @override
  String payWhyBatch(String level) {
    return 'batch $level';
  }

  @override
  String get payWhyReducedStar => 'bei iliyopunguzwa: Star Day iliyokosekana';

  @override
  String get payWhyReducedMarks => 'bei iliyopunguzwa: alama za mahudhurio';

  @override
  String payWhyTier(String orders, String from) {
    return 'Oda $orders: ngazi ya $from';
  }

  @override
  String payWhyMissing(String missing, String target, String rate) {
    return 'Oda $missing zimepungua kwenye $target × $rate KWD';
  }

  @override
  String payWhyMarks(String marks) {
    return 'Alama $marks za mahudhurio';
  }

  @override
  String get payWhyUncovered =>
      'Makato yanayozidi malipo ya mwezi hayakatwi, na kiasi halisi hakishuki chini ya sifuri: ofisi inakagua kilichobaki';

  @override
  String get noticesTitle => 'Arifa';

  @override
  String get noticesNone => 'Hakuna arifa bado';

  @override
  String get nameLabel => 'Jina';

  @override
  String get obOnFile =>
      'Sehemu zilizofungwa ziko kwenye kumbukumbu za kampuni. Kama moja si sahihi, muombe ofisi airekebishe.';

  @override
  String get nationalityPick => 'Chagua uraia wako';

  @override
  String get searchArEn => 'Tafuta kwa Kiarabu au Kiingereza';

  @override
  String get noMatches => 'Hakuna kinacholingana';

  @override
  String get ibanInvalid =>
      'Herufi moja kwenye IBAN hii si sahihi (tarakimu za uthibitisho hazilingani): inakili kutoka programu ya benki yako';

  @override
  String obFieldsInvalid(String fields) {
    return 'Angalia sehemu hizi: $fields';
  }

  @override
  String ibanLengthKw(int count) {
    return 'IBAN ya Kuwait ina herufi 30 zinazoanza na KW; hii ina $count';
  }

  @override
  String get driverWorking => 'Dereva yuko kazini';

  @override
  String get driverNotWorking => 'Dereva hayuko kazini';

  @override
  String greeting(String name) {
    return 'Habari, $name';
  }

  @override
  String get yourCar => 'Gari lako';

  @override
  String get quickActions => 'Vitendo vya haraka';

  @override
  String get dayNotStarted => 'Hujaanza siku yako';

  @override
  String get dayNotStartedHint => 'Anza kwa picha ya odomita kwa kamera';

  @override
  String dayStartedAt(String time) {
    return 'Siku yako ilianza saa $time';
  }

  @override
  String dayStartKm(String km) {
    return 'Odomita ya kuanzia $km';
  }

  @override
  String get dayEndedHint => 'Unafanya kazi tena leo? Anza tena';

  @override
  String get agoNow => 'sasa hivi';

  @override
  String agoMinutes(String n) {
    return 'dakika $n zilizopita';
  }

  @override
  String agoHours(String n) {
    return 'saa $n zilizopita';
  }

  @override
  String agoDays(String n) {
    return 'siku $n zilizopita';
  }

  @override
  String lastSentAgo(String ago) {
    return 'ilitumwa mwisho $ago';
  }

  @override
  String get qaBalance => 'Salio langu';

  @override
  String get qaReceipts => 'Risiti zangu';

  @override
  String qaReceiptsWaiting(String n) {
    return '$n za kuthibitisha';
  }

  @override
  String get qaReceiptsDone => 'Zote zimethibitishwa';

  @override
  String get qaMaintenanceSub => 'Hitilafu au maelezo';

  @override
  String get qaAccidentSub => 'Picha + ripoti ya polisi';

  @override
  String get qaReportSub => 'Oda na pesa taslimu za leo';

  @override
  String get qaFinesSub => 'Faini za gari lako';

  @override
  String get qaStatementSub => 'Picha za skrini za jukwaa kila mwezi';

  @override
  String get qaPayslipsSub => 'Malipo yako ya mwezi';

  @override
  String get qaSchemesSub => 'Jinsi malipo yako yanavyohesabiwa';

  @override
  String get tabWork => 'Kazi ya siku';

  @override
  String get todayReport => 'Ripoti ya leo';

  @override
  String get workReportSent => 'Ripoti ya leo imetumwa';

  @override
  String get workReportDue => 'Ripoti ya leo bado haijatumwa';

  @override
  String get workReportDueHint =>
      'Tuma oda na pesa taslimu kama zinavyoonekana kwenye programu ya jukwaa';

  @override
  String get sendDailyReport => 'Tuma ripoti ya siku';

  @override
  String ordersCash(String orders, String cash) {
    return 'Oda $orders · $cash';
  }

  @override
  String get myRequests => 'Maombi yangu';

  @override
  String get cashBalanceTitle => 'Salio lako (KWD)';

  @override
  String cashPendingPart(String amount) {
    return '$amount kati yake bado haijakubaliwa';
  }

  @override
  String cashLimit(String amount) {
    return 'Kikomo cha tahadhari $amount';
  }

  @override
  String employeeAt(String number, String company) {
    return '$number · $company';
  }

  @override
  String get thisPhone => 'Simu hii';

  @override
  String get takeOdometerPhoto => 'Piga picha ya odomita';

  @override
  String get cameraOnly => 'Kamera tu — matunzio hayaruhusiwi';

  @override
  String lastKmHint(String km) {
    return 'Usomaji wa mwisho uliorekodiwa wa gari: $km';
  }

  @override
  String get cashHint =>
      'Kama inavyoonekana kwenye programu ya kampuni ya usafirishaji';

  @override
  String get mntDescriptionHint => 'mf. kelele wakati wa kufunga breki';

  @override
  String get accSend => 'Tuma ripoti';

  @override
  String get workReportQueued => 'Ripoti ya leo imehifadhiwa kwenye simu';

  @override
  String get reportQueuedForDay =>
      'Ripoti ya siku hii imehifadhiwa kwenye simu na itatumwa yenyewe muunganisho ukirudi. Usiitume tena.';

  @override
  String ordersN(String n) {
    return 'Oda $n';
  }

  @override
  String get workReportDueHintDays =>
      'Tuma oda na kama siku ilihesabiwa kuwa halali';

  @override
  String get qaReportSubDays => 'Oda za leo na siku halali';

  @override
  String get notSentYet => 'Bado haijatumwa';

  @override
  String get fuel => 'Mafuta';

  @override
  String get qaFuelSub => 'Mafuta uliyolipa kwa pesa taslimu';

  @override
  String get fuelTitle => 'Mafuta yaliyolipwa kwa pesa taslimu';

  @override
  String get fuelIntro =>
      'Piga picha ya risiti ya mafuta na uweke kiasi. Mhasibu ataikagua akipokea pesa zako taslimu; ikikubaliwa, kiasi hicho kinatolewa kwenye pesa taslimu ulizonazo.';

  @override
  String get fuelReceipt => 'Picha ya risiti ya mafuta';

  @override
  String get fuelTakeReceipt => 'Piga picha ya risiti';

  @override
  String get fuelReceiptMissing => 'Picha ya risiti inahitajika';

  @override
  String get fuelAmount => 'Kiasi kilicholipwa';

  @override
  String get fuelAmountInvalid => 'Weka kiasi kwa KWD, hadi desimali 3';

  @override
  String fuelAmountMax(String max) {
    return 'Risiti moja haiwezi kuzidi $max KWD';
  }

  @override
  String get fuelOdometer => 'Usomaji wa odomita (si lazima)';

  @override
  String get fuelNotes => 'Maelezo (si lazima)';

  @override
  String get fuelSend => 'Tuma kwa ukaguzi';

  @override
  String get fuelMine => 'Risiti za mafuta';

  @override
  String get fuelNone => 'Hakuna risiti za mafuta bado';

  @override
  String get fuelPending => 'Inasubiri ukaguzi';

  @override
  String fuelApproved(String amount) {
    return 'Imekubaliwa ($amount)';
  }

  @override
  String get fuelRejected => 'Imekataliwa';

  @override
  String get fuelOff_fuel_card =>
      'Una kadi ya mafuta ya kampuni: ofisi inaiongezea salio, na mafuta hayadaiwi kutoka kwa pesa zako taslimu.';

  @override
  String get fuelOff_not_covered =>
      'Mafuta ni jukumu lako kulingana na mpango wako wa malipo, kwa hiyo hayatozwi kwa kampuni.';

  @override
  String get fuelOff_no_vehicle =>
      'Hakuna gari chini ya jukumu lako sasa: mafuta yanarekodiwa kwa gari ulilonalo.';

  @override
  String get kind_fuel => 'Risiti ya mafuta';

  @override
  String get moveFuel => 'Mafuta';

  @override
  String get vehicleChangePlate => 'Nambari ya gari jingine';

  @override
  String get vehicleChangePlateHint => '12-34567';

  @override
  String vehicleChangePendingFor(String plate) {
    return 'Ombi lako la kubadilisha kwenda $plate linakaguliwa';
  }

  @override
  String get claimVehicle => 'Sajili gari jipya';

  @override
  String get claimVehicleHint =>
      'Umechukua gari? Lisajili hapa pamoja na usomaji wa odomita; jukumu lako linaanza ofisi ikikubali.';

  @override
  String get claimTitle => 'Sajili gari jipya';

  @override
  String get claimPlate => 'Nambari ya gari';

  @override
  String get claimIntro =>
      'Piga picha ya odomita kwa kamera na uweke usomaji. Ombi linaenda ofisini; likikubaliwa, gari ni lako tangu muda wa picha.';

  @override
  String get claimConditionPhotos => 'Picha za hali ya gari (si lazima)';

  @override
  String get claimSend => 'Tuma ofisini';

  @override
  String claimPending(String plate) {
    return 'Ombi lako la kuchukua gari $plate linasubiri idhini ya ofisi';
  }

  @override
  String claimRejected(String plate, String reason) {
    return 'Ofisi imekataa ombi lako la kuchukua gari $plate: $reason';
  }

  @override
  String get kind_vehicle_claim => 'Usajili wa gari';

  @override
  String get mntNoCenter =>
      'Hakuna kituo cha matengenezo kinachopatikana: piga simu ofisini';

  @override
  String mntInMaintenance(String center) {
    return 'Gari lako liko kituo cha matengenezo: $center';
  }

  @override
  String get mntInMaintenanceAny => 'Gari lako liko kituo cha matengenezo';

  @override
  String get mntInMaintenanceHint =>
      'Gari bado liko chini ya jukumu lako, lakini hakuna siku ya kazi itakayoanza nalo hadi ulichukue kutoka kituoni na uthibitishe hapa.';

  @override
  String get fieldYes => 'Ndiyo';

  @override
  String get fieldNo => 'Hapana';

  @override
  String get fieldInvalid => 'Thamani si sahihi';

  @override
  String get choose => 'Chagua';

  @override
  String get objectPayslip => 'Pinga hati hii ya mshahara';

  @override
  String get objectLine => 'Pinga mstari huu';

  @override
  String get objectionTitle => 'Pingamizi la hati ya mshahara';

  @override
  String objectionOn(String what) {
    return 'Kuhusu: $what';
  }

  @override
  String get objectionWhole => 'Hati nzima ya mshahara';

  @override
  String get objectionReason => 'Kwa nini unapinga';

  @override
  String get objectionReasonShort => 'Andika sababu (angalau herufi 3)';

  @override
  String get objectionFile => 'Picha inayoonyesha hilo (si lazima)';

  @override
  String get objectionCamera => 'Kamera';

  @override
  String get objectionGallery => 'Matunzio';

  @override
  String get objectionSent => 'Pingamizi lako limetumwa; ofisi itajibu';

  @override
  String get objectionQueued => 'Pingamizi lako litatumwa muunganisho ukirudi';

  @override
  String get myObjections => 'Pingamizi zangu';

  @override
  String objectionResponse(String text) {
    return 'Ofisi: $text';
  }

  @override
  String objectionAction(String text) {
    return 'Hatua iliyochukuliwa: $text';
  }

  @override
  String get objectionStatus_open => 'Wazi';

  @override
  String get objectionStatus_in_review => 'Inakaguliwa';

  @override
  String get objectionStatus_accepted => 'Limekubaliwa';

  @override
  String get objectionStatus_rejected => 'Limekataliwa';

  @override
  String get objectionStatus_closed => 'Limefungwa';

  @override
  String get objectionInstallment => 'Awamu';

  @override
  String vehicleChangeApprovedFor(String plate) {
    return 'Mabadiliko yako kwenda $plate yamekubaliwa: lichukue ofisini';
  }

  @override
  String get receiptReversed => 'Imeghairiwa';

  @override
  String pickupReplacementTitle(String plate) {
    return 'Gari la akiba $plate';
  }

  @override
  String get pickupReplacementHint =>
      'Unalirudisha unapochukua gari lako: piga picha ya odomita yake na uweke usomaji.';

  @override
  String get pickupReplacementPhoto => 'Picha ya odomita ya gari la akiba';

  @override
  String get fuelLitres => 'Lita (si lazima)';

  @override
  String get fuelLitresInvalid =>
      'Weka lita kama zilivyo kwenye risiti (hadi 500)';

  @override
  String get fuelLitresUnit => 'L';

  @override
  String get replacementCar => 'Gari la akiba — lako liko kituoni';

  @override
  String outboxAttention(String reason) {
    return 'Inahitaji umakini wako: $reason';
  }

  @override
  String get outboxTooOld => 'haijatumwa kwa siku mbili';

  @override
  String get outboxKeptFailing => 'seva haikuweza kuipokea';

  @override
  String outboxAttentionCount(int n) {
    return '$n zinahitaji umakini wako';
  }

  @override
  String get startFailedTitle => 'Programu imeshindwa kuanza';

  @override
  String get startFailedBody =>
      'Hitilafu imetokea wakati wa kupakia. Angalia muunganisho na ujaribu tena.';

  @override
  String get activationReplaceTitle => 'Badilisha dereva aliyeingia?';

  @override
  String get activationReplaceBody =>
      'Dereva mwingine tayari ameingia kwenye simu hii. Kuwezesha kiungo hiki kunamtoa na kuondoa chochote chake ambacho bado hakijatumwa.';

  @override
  String get activationReplaceConfirm => 'Wezesha';

  @override
  String get trackingActive => 'Eneo linatumwa';

  @override
  String get trackingStale => 'Eneo halifiki';

  @override
  String get trackingUnknown => 'Hali ya ufuatiliaji haijulikani';

  @override
  String noticeBigActive(String time) {
    return 'Eneo la mwisho lilitumwa $time';
  }

  @override
  String noticeBigStale(String time) {
    return 'Hakuna eneo tangu $time. Fungua programu na uangalie mipangilio ya eneo';
  }

  @override
  String get noticeBigStaleNever =>
      'Hakuna eneo lililotumwa bado. Fungua programu na uangalie mipangilio ya eneo';

  @override
  String get noticeBigOff => 'Eneo lako halifuatiliwi sasa';

  @override
  String get openApp => 'Fungua programu';

  @override
  String get alertsChannel => 'Tahadhari muhimu';

  @override
  String offlineSince(String time) {
    return 'Nje ya mtandao · ilisasishwa mwisho $time';
  }

  @override
  String get statusCall => 'Piga simu';

  @override
  String get statusDone => 'Imekamilika';

  @override
  String get statusCheckSettings => 'Angalia mipangilio';

  @override
  String get statusOpenCash => 'Pesa taslimu';

  @override
  String get statusOpenCustody => 'Gari langu';

  @override
  String get statusOpenMaintenance => 'Matengenezo';

  @override
  String get statusOpenDocuments => 'Hati zangu';

  @override
  String get statusOpenContact => 'Maelezo';

  @override
  String statusMore(String count) {
    return 'na tahadhari nyingine $count';
  }

  @override
  String statusDaySummary(String count) {
    return 'Vipindi vya leo: $count';
  }

  @override
  String get statusContactSent => 'Msimamizi wako ameambiwa';

  @override
  String get statusDialFailed => 'Imeshindwa kupiga simu kwenye simu hii';

  @override
  String get leaves => 'Ombi la kutokuwepo';

  @override
  String get qaLeavesSub => 'Likizo au kutokuwepo kwa sababu';

  @override
  String get leaveType => 'Aina ya likizo';

  @override
  String leaveLeft(String days) {
    return 'Siku $days zimebaki';
  }

  @override
  String get leaveFrom => 'Kuanzia';

  @override
  String get leaveTo => 'Hadi';

  @override
  String get leaveOneDay => 'Siku moja';

  @override
  String get leaveReason => 'Sababu';

  @override
  String get leaveFollowupFrom => 'Tarehe ya kuanza ufuatiliaji';

  @override
  String get leaveAttachment => 'Kiambatisho (kama cheti cha daktari)';

  @override
  String get leaveAttachmentRequired => 'Aina hii inahitaji kiambatisho';

  @override
  String get leaveCamera => 'Kamera';

  @override
  String get leaveGallery => 'Matunzio';

  @override
  String leavePreviewDays(String days) {
    return 'Siku $days zimehesabiwa';
  }

  @override
  String leavePaidPart(String days, String percent) {
    return 'Siku $days kwa malipo ya $percent%';
  }

  @override
  String leaveUnpaidPart(String days) {
    return 'Siku $days bila malipo';
  }

  @override
  String get leavePreviewOffline =>
      'Hesabu inahitaji mtandao: ombi litatumwa na kukaguliwa ofisini';

  @override
  String get leaveSend => 'Tuma ombi';

  @override
  String get leaveMine => 'Maombi yangu';

  @override
  String get leaveNone => 'Hakuna maombi';

  @override
  String get leaveCancel => 'Ondoa ombi';

  @override
  String get leaveStatus_pending => 'Inasubiri idhini';

  @override
  String get leaveStatus_approved => 'Imeidhinishwa';

  @override
  String get leaveStatus_rejected => 'Imekataliwa';

  @override
  String get leaveStatus_cancelled => 'Imeghairiwa';

  @override
  String leaveOfficeSays(String reason) {
    return 'Ofisi: $reason';
  }

  @override
  String get leaveNoTypes => 'Hakuna aina ya likizo inayopatikana kwako sasa';

  @override
  String get leaveDatesInvalid => 'Tarehe ya mwisho iko kabla ya mwanzo';

  @override
  String get leaveTypeMissing => 'Chagua aina ya likizo';

  @override
  String get noticeAtWork => 'Kazini';

  @override
  String get noticeOffDuty => 'Nje ya zamu';

  @override
  String get noticeInMaintenance => 'Gari liko matengenezoni';

  @override
  String get noticeAwaitingFirst => 'Inasubiri eneo la kwanza';

  @override
  String get noticeLocating => 'Inatafuta eneo lako…';

  @override
  String noticeShiftFrom(String time) {
    return 'Zamu tangu $time';
  }

  @override
  String noticeDayEnded(String count) {
    return 'Siku imeisha · oda $count';
  }

  @override
  String get noticeDayEndedNoCount => 'Siku imeisha';

  @override
  String get noticeDayNotStarted => 'Siku ya kazi haijaanza';

  @override
  String noticeLastConfirmed(String time) {
    return 'Utumaji wa mwisho uliothibitishwa $time';
  }

  @override
  String get noticeNoneConfirmed => 'Hakuna utumaji uliothibitishwa';

  @override
  String get headsUpContact => 'Ombi la mawasiliano';

  @override
  String headsUpLocationBody(String time) {
    return 'Sasisho la mwisho $time · fungua programu na uangalie mipangilio ya eneo.';
  }

  @override
  String get headsUpLocationBodyNever =>
      'Fungua programu na uangalie mipangilio ya eneo.';

  @override
  String get actionOpenLocationSettings => 'Fungua mipangilio ya eneo';

  @override
  String get noticeCatAlerts => 'Arifa';

  @override
  String get noticeCatCash => 'Pesa taslimu na ripoti';

  @override
  String get noticeCatCar => 'Gari na dhamana';

  @override
  String get noticeCatMaintenance => 'Matengenezo na makato';

  @override
  String get noticeCatDocuments => 'Hati na hati ya mshahara';

  @override
  String updateAvailable(String version) {
    return 'Toleo jipya $version linapatikana';
  }

  @override
  String get updateNow => 'Sasisha';

  @override
  String get updateLater => 'Baadaye';

  @override
  String get updateRequiredTitle =>
      'Unahitaji kusasisha programu ili kuendelea';

  @override
  String get updateRequiredBody =>
      'Kilichohifadhiwa kwenye simu kinaendelea kutumwa, na ufuatiliaji unaendelea.';

  @override
  String updateQueued(String count) {
    return 'Vinasubiri kutumwa: $count';
  }

  @override
  String updateSize(String size) {
    return 'Ukubwa $size';
  }

  @override
  String get updateMobileData =>
      'Uko kwenye data ya simu: upakuaji utatumia kifurushi chako.';

  @override
  String updateDownloading(String percent) {
    return 'Inapakua $percent';
  }

  @override
  String get updateInstall => 'Sakinisha';

  @override
  String get updateInstallHint =>
      'Android itakuomba uthibitishe usakinishaji. Fungua programu tena baada ya kusasisha.';

  @override
  String get updatePermissionTitle => 'Ruhusu kusakinisha sasisho';

  @override
  String get updatePermissionBody =>
      'Kwenye ukurasa unaofuata washa «Ruhusu kutoka chanzo hiki» kwa programu hii, kisha urudi.';

  @override
  String get updateOpenSettings => 'Fungua mipangilio';

  @override
  String get updateChecksum =>
      'Faili lililopakuliwa lilikuwa na hitilafu na limefutwa. Jaribu tena.';

  @override
  String get updateFailed => 'Upakuaji umeshindwa. Jaribu tena.';

  @override
  String get updateInstallFailed => 'Kisakinishi hakikuweza kufunguliwa.';

  @override
  String get checkUpdates => 'Angalia masasisho';

  @override
  String get upToDate => 'Una toleo jipya zaidi';

  @override
  String get updateCheckFailed => 'Imeshindwa kuangalia: hakuna mtandao';

  @override
  String get whatsNew => 'Kipya';

  @override
  String get noticesCurrent => 'Yanayoendelea';

  @override
  String get noticesHistory => 'Historia';

  @override
  String get messagesChannel => 'Ujumbe na taarifa';

  @override
  String get noticeOpenLeave => 'Omba likizo';

  @override
  String get pettyTitle => 'Fedha ndogo za dhamana';

  @override
  String get qaPettySub => 'Tumia kwa ankara';

  @override
  String get pettyCashRow => 'Fedha zako ndogo za dhamana';

  @override
  String get pettyNone =>
      'Huna fedha ndogo za dhamana sasa. Ofisi hukupa kutoka hazina ya tawi.';

  @override
  String get pettyBalance => 'Salio la dhamana';

  @override
  String pettyPendingPart(String pending, String available) {
    return '$pending kati yake inasubiri ukaguzi · $available bado inapatikana';
  }

  @override
  String get pettySpend => 'Tumia kutoka kwa dhamana';

  @override
  String get pettyMine => 'Miamala';

  @override
  String get pettyEmpty => 'Hakuna miamala kwenye dhamana bado';

  @override
  String get pettyQueued => 'Inasubiri kutumwa';

  @override
  String get pettyPending => 'Inasubiri ukaguzi';

  @override
  String get pettyApproved => 'Imekubaliwa';

  @override
  String get pettyRejected => 'Imekataliwa';

  @override
  String get pettyCancelled => 'Imeghairiwa';

  @override
  String pettyReason(String reason) {
    return 'Sababu: $reason';
  }

  @override
  String get pettyCancel => 'Ghairi matumizi';

  @override
  String pettyCancelQ(String amount) {
    return 'Ghairi matumizi ya $amount? Ofisi bado haijayakagua.';
  }

  @override
  String get pettyFunded => 'Imetolewa na ofisi';

  @override
  String get pettyReturned => 'Imerudishwa hazina';

  @override
  String get pettyOfficeExpense => 'Matumizi yaliyowekwa na ofisi';

  @override
  String get pettyCorrection => 'Marekebisho';

  @override
  String pettyIntro(String available) {
    return 'Piga picha ya ankara na uweke kiasi na aina ya matumizi. Ofisi itakagua, na ikikubaliwa itatolewa kwenye dhamana yako. Bado inapatikana: $available KWD';
  }

  @override
  String get pettyInvoice => 'Picha ya ankara';

  @override
  String get pettyTakeInvoice => 'Piga picha ya ankara';

  @override
  String get pettyInvoiceMissing => 'Picha ya ankara inahitajika';

  @override
  String get pettyAmount => 'Kiasi';

  @override
  String get pettyAmountInvalid => 'Weka kiasi sahihi (hadi desimali 3)';

  @override
  String pettyAmountMax(String available) {
    return 'Zaidi ya unachoweza bado kutumia ($available KWD)';
  }

  @override
  String get pettyCategory => 'Aina ya matumizi';

  @override
  String get pettyCategoryMissing => 'Chagua aina ya matumizi';

  @override
  String get pettyDate => 'Tarehe ya ankara';

  @override
  String get pettyVendor => 'Muuzaji au duka';

  @override
  String get pettyNote => 'Maelezo';

  @override
  String get pettySend => 'Tuma kwa ukaguzi';

  @override
  String get kind_petty => 'Matumizi ya fedha ndogo';

  @override
  String get kind_petty_cancel => 'Kughairi matumizi ya fedha ndogo';

  @override
  String get companyTitle => 'Unafanya kazi na kampuni gani?';

  @override
  String get companyIntro =>
      'Chagua kampuni unayosafirishia. Chaguo lako linaenda ofisini kuidhinishwa; unaweza kuendelea na kazi ukisubiri.';

  @override
  String get companyNote => 'Ujumbe kwa ofisi (si lazima)';

  @override
  String get companySend => 'Tuma kwa ofisi';

  @override
  String companyRejected(String platform, String reason) {
    return 'Ofisi imekataa chaguo lako ($platform): $reason. Tafadhali chagua tena.';
  }

  @override
  String companyPending(String platform) {
    return 'Ombi lako la kufanya kazi na $platform linasubiri ofisi';
  }

  @override
  String get companyChange => 'Badilisha chaguo langu';

  @override
  String get companyNone =>
      'Hakuna kampuni inayopatikana sasa. Wasiliana na ofisi.';

  @override
  String get endOrdersKept =>
      'Imehifadhiwa na itaonekana kwenye ripoti ya leo, ambapo utajaza sehemu zilizobaki';

  @override
  String get languageFirst =>
      'Chagua lugha ya programu. Unaweza kuibadilisha baadaye kwenye mipangilio.';

  @override
  String get schemeKindPick => 'Chagua kwanza jinsi unavyolipwa';

  @override
  String get schemeKind_per_order => 'Kwa oda';

  @override
  String get schemeKind_fixed_salary => 'Mshahara wa kudumu';

  @override
  String get schemeKind_batch => 'Batch';

  @override
  String schemeFixedSalary(String amount) {
    return 'Mshahara wa kudumu: $amount KWD kwa mwezi';
  }

  @override
  String get schemeContractSalary => 'Mshahara wa msingi wa mkataba wako';

  @override
  String schemeOverTarget(String target, String rate) {
    return 'Lengo oda $target: + $rate KWD kwa kila oda juu yake';
  }

  @override
  String schemeUnderTarget(String rate) {
    return 'na − $rate KWD kwa kila oda iliyopungua';
  }

  @override
  String get schemeTierRates => 'Bei kwa oda kulingana na oda za mwezi:';

  @override
  String schemeTierRateRow(String orders, String rate) {
    return 'Kuanzia oda $orders: $rate KWD';
  }

  @override
  String schemeMonthlyBonus(String amount) {
    return 'Bonasi ya mwezi: $amount KWD';
  }

  @override
  String get schemeMarksTable => 'Alama nyekundu katika mwezi:';

  @override
  String schemeMarksFree(String marks) {
    return 'Hadi alama $marks: hakuna makato (siku zako za mapumziko)';
  }

  @override
  String schemeMarksRow(String marks, String amount) {
    return 'Alama $marks: − $amount KWD';
  }

  @override
  String schemeMarkEach(String amount) {
    return '− $amount KWD kwa kila alama nyekundu';
  }

  @override
  String schemeReducedStarDay(String rate) {
    return 'Alama nyekundu siku ya nyota: kila oda ya mwezi kwa $rate KWD badala ya mshahara na bonasi, makato bado yanakatwa';
  }

  @override
  String schemeReducedMarks(String marks, String rate) {
    return 'Zaidi ya alama nyekundu $marks: kila oda ya mwezi kwa $rate KWD badala ya mshahara na bonasi';
  }

  @override
  String schemeRequiredDays(String days) {
    return 'Siku $days halali zinahitajika katika mwezi';
  }

  @override
  String get schemePlatformAmounts =>
      'Bakshishi huongezwa; uharibifu wa chakula, marekebisho na punguzo la jukwaa hukatwa';

  @override
  String schemeDriverPays(String items) {
    return 'Juu yako: $items';
  }

  @override
  String get schemeChange => 'Omba kubadilisha mpango';

  @override
  String get schemeChangeBody =>
      'Ofisi itakagua ombi lako; ikikubali, mipango ya jukwaa lako itaonekana hapa uchague mpya.';

  @override
  String get schemeChangePending =>
      'Ombi lako la kubadilisha mpango linasubiri ofisi';

  @override
  String schemeChangeRejected(String note) {
    return 'Ofisi imekataa kubadilisha mpango wako: $note';
  }

  @override
  String get schemePickFirst => 'Chagua mpango wa malipo unaofanyia kazi';

  @override
  String schemePickAllowed(String month) {
    return 'Imekubaliwa: chagua mpango mpya, unaanza $month';
  }

  @override
  String get schemePick => 'Chagua mpango huu';

  @override
  String schemePickConfirm(String name, String month) {
    return 'Unachagua “$name”, kuanzia $month. Baada ya hapo ni ombi jipya kwa ofisi tu linaloweza kuubadilisha.';
  }

  @override
  String get schemePicked => 'Mpango wako umewekwa';

  @override
  String get offerTitle => 'Chagua mpango unaokufaa';

  @override
  String get offerSub =>
      'Maelezo yote ya mpango mahali pamoja. Ofisi itakagua chaguo lako pamoja na ombi la kampuni.';

  @override
  String get offerKwd => 'KWD';

  @override
  String get offerPerMonth => 'Mshahara wa kudumu wa mwezi';

  @override
  String get offerPerOrder => 'Kwa kila oda';

  @override
  String get offerByBatch => 'Kwa oda, kulingana na batch';

  @override
  String get offerTarget => 'Lengo la oda';

  @override
  String get offerOver => 'kila oda ya ziada';

  @override
  String get offerUnder => 'kila oda iliyopungua';

  @override
  String get offerBonus => 'Bonasi ya mwezi';

  @override
  String get offerBonusTop => 'Bonasi ya ngazi ya juu tu inalipwa';

  @override
  String offerOrders(String orders) {
    return 'Oda $orders';
  }

  @override
  String get offerCovers => 'Inalipwa na kampuni';

  @override
  String get offerYouPay => 'Unalipa wewe';

  @override
  String get offerTerms => 'Masharti na maelezo';

  @override
  String get offerSelect => 'Chagua mpango huu';

  @override
  String get offerSelected => 'Imechaguliwa';

  @override
  String get offerNext => 'Ifuatayo: chagua mpango wa malipo';

  @override
  String get offerNone =>
      'Kampuni hii haina mipango ya kuchagua: ofisi itaweka wako.';

  @override
  String get offerPickOne => 'Chagua mpango kwanza';
}
