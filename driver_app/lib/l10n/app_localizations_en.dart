// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Driver app';

  @override
  String get retry => 'Retry';

  @override
  String get cancel => 'Cancel';

  @override
  String get continueBtn => 'Continue';

  @override
  String get save => 'Save';

  @override
  String get send => 'Send';

  @override
  String get back => 'Back';

  @override
  String get done => 'Done';

  @override
  String get networkError => 'No internet connection. Try again.';

  @override
  String get genericError => 'Something went wrong. Try again.';

  @override
  String get kwd => 'KWD';

  @override
  String get km => 'km';

  @override
  String get signInTitle => 'Sign in';

  @override
  String get signInHint => 'Enter your phone number registered with the company. The sign-in code arrives on WhatsApp.';

  @override
  String get phoneLabel => 'Phone number';

  @override
  String get phoneInvalid => '8 Kuwaiti digits, or an international number starting with +';

  @override
  String get sendCode => 'Send code';

  @override
  String get activationTip => 'If you received an activation link on WhatsApp, open it on this phone: no code needed.';

  @override
  String get otpTitle => 'Sign-in code';

  @override
  String otpHint(String phone) {
    return 'Enter the 6-digit code sent on WhatsApp to $phone.';
  }

  @override
  String get otpLabel => 'Code';

  @override
  String get verify => 'Sign in';

  @override
  String get otpResend => 'No code? Send again';

  @override
  String get activating => 'Activating the app on this phone…';

  @override
  String get activationFailed => 'Activation failed';

  @override
  String get permTitle => 'App permissions';

  @override
  String get permIntro =>
      'To track during your custody, even with the app closed, the app needs these permissions. Your location is recorded only while a vehicle is in your custody.';

  @override
  String get permLocation => 'Location: “Allow all the time”';

  @override
  String get permLocationWhy => 'So the supervisor sees the vehicle during your custody.';

  @override
  String get permNotifications => 'Notifications';

  @override
  String get permNotificationsWhy => 'A permanent notification shows while tracking (an Android rule).';

  @override
  String get permBattery => 'Ignore battery optimisation';

  @override
  String get permBatteryWhy => 'So the phone does not stop tracking in the background.';

  @override
  String get permGrant => 'Allow';

  @override
  String get permGranted => 'Allowed';

  @override
  String get permSettings => 'Open settings';

  @override
  String get permLocationRequired => 'Location permission is needed to continue.';

  @override
  String get gpsOff => 'GPS is off: turn it on in the phone settings.';

  @override
  String get obTitle => 'Complete registration';

  @override
  String get obIntro =>
      'Enter your details and photograph your documents and vehicle. Nothing is official before the company reviews it.';

  @override
  String obRejected(String reason) {
    return 'Your registration was sent back: $reason';
  }

  @override
  String get obStepData => 'Details';

  @override
  String get obStepDocs => 'Documents';

  @override
  String get obStepVehicle => 'Vehicle';

  @override
  String get obStepReview => 'Review';

  @override
  String get civilId => 'Civil ID';

  @override
  String get civilIdInvalid => 'The civil ID has 12 digits';

  @override
  String get nationality => 'Nationality';

  @override
  String get docNumber => 'Document number';

  @override
  String get docExpiry => 'Expiry date';

  @override
  String get docFront => 'Front';

  @override
  String get docBack => 'Back';

  @override
  String get pickPhoto => 'Photo';

  @override
  String get takePhoto => 'Take photo';

  @override
  String get fromGallery => 'From gallery';

  @override
  String get uploading => 'Uploading…';

  @override
  String get required => 'Required';

  @override
  String get plate => 'Plate number';

  @override
  String get plateHint => 'As on the plate, e.g. 18/23456';

  @override
  String get odometerKm => 'Odometer (km)';

  @override
  String get odometerPhoto => 'Odometer photo';

  @override
  String get noVehicle => 'No vehicle with me now';

  @override
  String get vehiclePhotos => 'Vehicle condition photos';

  @override
  String get obSubmit => 'Send for review';

  @override
  String obMissing(String items) {
    return 'Complete: $items';
  }

  @override
  String get obWaitingTitle => 'Your details are being reviewed';

  @override
  String get obWaitingText => 'You will get a WhatsApp message when approved or if something needs fixing.';

  @override
  String get refresh => 'Refresh';

  @override
  String get position_front => 'Front';

  @override
  String get position_back => 'Back';

  @override
  String get position_left => 'Left side';

  @override
  String get position_right => 'Right side';

  @override
  String get position_interior => 'Interior';

  @override
  String get position_other => 'Other';

  @override
  String get tabHome => 'Home';

  @override
  String get tabCash => 'Cash';

  @override
  String get tabAccount => 'Account';

  @override
  String get noCustody => 'No vehicle in your custody now';

  @override
  String get noCustodyHint => 'When a vehicle is handed to you it shows here and tracking starts by itself.';

  @override
  String custodySince(String when) {
    return 'In your custody since $when';
  }

  @override
  String lastKm(String km) {
    return 'Last reading: $km km';
  }

  @override
  String get trackingOn => 'Tracking on';

  @override
  String get trackingOff => 'Tracking off';

  @override
  String trackingWaiting(String count) {
    return 'Waiting to send: $count';
  }

  @override
  String get startDay => 'Start the day';

  @override
  String get startDayDone => 'Day started';

  @override
  String get endDay => 'End the day';

  @override
  String get dailyReport => 'Daily report';

  @override
  String get outboxTitle => 'Waiting to send';

  @override
  String get outboxQueued => 'Sent automatically when the network is back';

  @override
  String outboxFailed(String reason) {
    return 'Not accepted: $reason';
  }

  @override
  String get outboxDiscard => 'Remove';

  @override
  String get kind_odometer => 'Odometer reading';

  @override
  String get kind_report => 'Daily report';

  @override
  String get startDayTitle => 'Start of day';

  @override
  String get endDayTitle => 'End of day';

  @override
  String get odometerIntro => 'Photograph the odometer clearly, then type the reading as shown in the photo.';

  @override
  String get retake => 'Retake';

  @override
  String kmLower(String km) {
    return 'Lower than the last reading ($km km). Check it: it will go to review.';
  }

  @override
  String get kmInvalid => 'Type the reading in digits';

  @override
  String get photoRequired => 'The photo is required';

  @override
  String get sentTitle => 'Sent';

  @override
  String get queuedTitle => 'Saved on the phone';

  @override
  String get sentText => 'The company received it.';

  @override
  String get queuedText =>
      'No network now. It will be sent automatically, with its original time, when the connection is back.';

  @override
  String get reportTitle => 'Daily report';

  @override
  String get reportDate => 'Work day';

  @override
  String get today => 'Today';

  @override
  String get yesterday => 'Yesterday';

  @override
  String get dayBefore => 'Day before';

  @override
  String get ordersCount => 'Orders';

  @override
  String get cashAmount => 'Cash collected';

  @override
  String get cashInvalid => 'An amount with at most three decimals';

  @override
  String get screenshot => 'Screenshot of the day summary from the delivery app';

  @override
  String get notes => 'Notes';

  @override
  String get recentReports => 'Recent reports';

  @override
  String get status_submitted => 'Waiting for review';

  @override
  String get status_approved => 'Approved';

  @override
  String get status_rejected => 'Rejected';

  @override
  String approvedCash(String amount) {
    return 'Approved: $amount';
  }

  @override
  String get cashTitle => 'Cash';

  @override
  String get cashTotal => 'Cash you hold';

  @override
  String get cashPosted => 'Approved';

  @override
  String get cashPending => 'Waiting for review';

  @override
  String cashOverLimit(String limit) {
    return 'Above the limit ($limit): hand the cash to the cashier.';
  }

  @override
  String get receipts => 'Receipts';

  @override
  String receiptNo(String no) {
    return 'Receipt no. $no';
  }

  @override
  String get confirmReceipt => 'I confirm';

  @override
  String get receiptConfirmed => 'Confirmed';

  @override
  String confirmReceiptQ(String amount) {
    return 'Did you hand $amount KWD to the cashier?';
  }

  @override
  String get noReceipts => 'No receipts yet';

  @override
  String get language => 'Language';

  @override
  String get trackingDetails => 'Tracking status';

  @override
  String lastUpload(String when) {
    return 'Last sent: $when';
  }

  @override
  String get never => 'not yet';

  @override
  String appVersion(String version) {
    return 'Version $version';
  }

  @override
  String get signOut => 'Sign out';

  @override
  String get signOutQ => 'Tracking stops and you will need a new activation to sign in. Continue?';

  @override
  String get blockedTitle => 'Your account is suspended';

  @override
  String get blockedText => 'Contact your supervisor.';

  @override
  String get obReady => 'Everything is ready: send it for review.';

  @override
  String get maintenance => 'Maintenance';

  @override
  String get maintenanceTitle => 'Maintenance requests';

  @override
  String get kind_maintenance => 'Maintenance request';

  @override
  String get mntNew => 'New maintenance request';

  @override
  String get mntIntro =>
      'Describe the problem and take photos. Your supervisor approves the request and chooses the maintenance center.';

  @override
  String get mntNoVehicle => 'Maintenance is requested for the vehicle in your custody. You have none now.';

  @override
  String get mntKind => 'Type';

  @override
  String get mntDescription => 'What is wrong';

  @override
  String get mntOdometer => 'Odometer (optional)';

  @override
  String get mntPhotos => 'Photos (up to 4)';

  @override
  String get mntAddPhoto => 'Photo';

  @override
  String get mntNone => 'No maintenance requests';

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
    return 'Your vehicle $plate is ready for pickup at $center';
  }

  @override
  String mntRejected(String reason) {
    return 'Rejected: $reason';
  }

  @override
  String get mntSent => 'Your maintenance request was sent to your supervisor';

  @override
  String get mntKind_periodic => 'Periodic service';

  @override
  String get mntKind_mechanical => 'Mechanical';

  @override
  String get mntKind_electrical => 'Electrical';

  @override
  String get mntKind_tyres => 'Tyres';

  @override
  String get mntKind_battery => 'Battery';

  @override
  String get mntKind_ac => 'Air conditioning';

  @override
  String get mntKind_bodywork => 'Bodywork';

  @override
  String get mntKind_other => 'Other';

  @override
  String get mntStatus_requested => 'Waiting for approval';

  @override
  String get mntStatus_approved => 'Approved';

  @override
  String get mntStatus_rejected => 'Rejected';

  @override
  String get mntStatus_referred => 'Sent to the center';

  @override
  String get mntStatus_at_center => 'At the center';

  @override
  String get mntStatus_ready => 'Ready for pickup';

  @override
  String get mntStatus_picked_up => 'Picked up';

  @override
  String get mntStatus_closed => 'Closed';

  @override
  String get mntStatus_cancelled => 'Cancelled';

  @override
  String get mntTapToRemove => 'tap to remove';

  @override
  String get accident => 'Report an accident';

  @override
  String get accidentsTitle => 'Accidents';

  @override
  String get kind_accident => 'Accident report';

  @override
  String get kind_police_report => 'Police report';

  @override
  String get accNew => 'New accident report';

  @override
  String get accEmergency => 'If anyone is hurt, call 112 first.';

  @override
  String get accIntro =>
      'Photograph the vehicle from several angles: front, back, both sides and the damage. Time and place are recorded automatically.';

  @override
  String get accNoVehicle =>
      'An accident is reported for the vehicle you hold. You have none now: call your supervisor.';

  @override
  String get accDescription => 'What happened?';

  @override
  String get accInjuries => 'Someone is injured';

  @override
  String get accInjuriesNote => 'Injury details';

  @override
  String get accOtherParty => 'The other party (plate, name, insurer)';

  @override
  String accPhotos(String min) {
    return 'Accident photos (at least $min)';
  }

  @override
  String accPhotosNeeded(String min) {
    return 'Take at least $min photos from different angles';
  }

  @override
  String get accPoliceReport => 'Police report';

  @override
  String get accPoliceReportNo => 'Report number';

  @override
  String get accPoliceLater =>
      'No report yet? Send now and send a photo of the police report later from your accidents below.';

  @override
  String get accSendPolice => 'Send the police report';

  @override
  String get accNone => 'No accidents';

  @override
  String accNo(String number) {
    return 'Accident #$number';
  }

  @override
  String get accStage_review => 'Under review';

  @override
  String get accStage_outcome => 'Awaiting the liability decision';

  @override
  String get accStage_recorded => 'Liability decided';

  @override
  String get accStage_closed => 'Closed';

  @override
  String get accLiability_none => 'You are not liable';

  @override
  String get accLiability_driver => 'You are liable';

  @override
  String accLiability_shared(String percent) {
    return 'Shared liability: your share $percent%';
  }

  @override
  String accDeduction(String total, String count) {
    return 'Deduction $total KWD · installments: $count';
  }

  @override
  String accInstallment(String month, String amount) {
    return '$month: $amount KWD';
  }

  @override
  String accAwaitingPolice(String number) {
    return 'Accident #$number is waiting for the police report: tap to send a photo of it';
  }

  @override
  String get fines => 'Traffic fines';

  @override
  String get finesTitle => 'Traffic fines';

  @override
  String get finesIntro =>
      'Fines on the vehicle while you held it, by the time of the fine. The company decides: it bears them, or they are deducted from your salary in installments.';

  @override
  String get finesNone => 'No fines';

  @override
  String get fineStatus_open => 'Under review';

  @override
  String get fineStatus_charged => 'Deducted from your salary';

  @override
  String get fineStatus_company => 'Borne by the company';

  @override
  String get monthlyStatement => 'Monthly platform statement';

  @override
  String get payslips => 'Payslips';

  @override
  String get statementTitle => 'Monthly platform statement';

  @override
  String statementIntro(String platform) {
    return 'At the start of each month, send screenshots of the month\'s summary from the $platform app and type the figures as they show. The office checks them against the screenshots before the payroll.';
  }

  @override
  String get statementNoPlatform => 'Your platform is not set yet. Contact the office.';

  @override
  String get statementNoMonth => 'You sent every open month. Wait for the office\'s review.';

  @override
  String get statementMonth => 'Month';

  @override
  String get statementShots => 'Screenshots from the platform app (up to 6)';

  @override
  String get statementShotRequired => 'Add at least one screenshot';

  @override
  String get statementHistory => 'What you sent';

  @override
  String statementSentDays(String days) {
    return 'Sent: $days valid days';
  }

  @override
  String statementApprovedDays(String days) {
    return 'Approved: $days valid days';
  }

  @override
  String get statementStatus_submitted => 'Waiting for review';

  @override
  String get statementStatus_approved => 'Approved';

  @override
  String get statementStatus_rejected => 'Rejected: send it again';

  @override
  String get addShot => 'Add a screenshot';

  @override
  String get validDays => 'Valid days';

  @override
  String get ordersTotal => 'Total orders';

  @override
  String get hoursTotal => 'Total hours';

  @override
  String get payslipsTitle => 'Payslips';

  @override
  String get payslipsNone => 'No approved payslip yet';

  @override
  String get payslipNet => 'Net salary';

  @override
  String get payslipStatus_approved => 'Approved';

  @override
  String get payslipStatus_paid => 'Paid';

  @override
  String get iban => 'IBAN';

  @override
  String get ibanHint => 'Your salary is paid to it: copy it from your bank\'s app';

  @override
  String get bankName => 'Bank name';

  @override
  String get civilSignIn => 'Sign in with civil ID';

  @override
  String get civilSignInHint =>
      'If the company has no phone number for you: sign in with your civil ID and the initial password the office gave you, then register your phone. The password works once.';

  @override
  String get initialPassword => 'Initial password';

  @override
  String get claimContinue => 'Continue';

  @override
  String claimWelcome(String name) {
    return 'Welcome $name. Enter your phone number that has WhatsApp: the code goes to it, and you sign in with it from now on.';
  }

  @override
  String get password => 'Password';

  @override
  String get civilSignInOnly =>
      'Sign in with your civil ID and your password. The first time: the initial password the office gave you, then you choose your own.';

  @override
  String get forgotPassword => 'Forgot your password? Ask your supervisor for a new initial password.';

  @override
  String choosePassword(String name) {
    return 'Welcome $name. Choose your password: with it and your civil ID you sign in from now on, on any phone. At least 8 characters, not the initial password or your civil ID, and tell no one.';
  }

  @override
  String get newPassword => 'New password';

  @override
  String get confirmPassword => 'Type the password again';

  @override
  String get passwordTooShort => 'At least 8 characters';

  @override
  String get passwordsDiffer => 'The two passwords differ';

  @override
  String get passwordIsCivilId => 'Do not use your civil ID as a password';

  @override
  String get saveAndSignIn => 'Save and sign in';
}
