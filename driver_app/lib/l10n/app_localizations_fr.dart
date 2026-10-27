// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for French (`fr`).
class AppLocalizationsFr extends AppLocalizations {
  AppLocalizationsFr([String locale = 'fr']) : super(locale);

  @override
  String get appTitle => 'Application chauffeur';

  @override
  String get retry => 'Réessayer';

  @override
  String get cancel => 'Annuler';

  @override
  String get continueBtn => 'Continuer';

  @override
  String get save => 'Enregistrer';

  @override
  String get send => 'Envoyer';

  @override
  String get back => 'Retour';

  @override
  String get done => 'Terminé';

  @override
  String get networkError => 'Pas de connexion Internet. Réessayez.';

  @override
  String get genericError => 'Une erreur s\'est produite. Réessayez.';

  @override
  String get kwd => 'KWD';

  @override
  String get km => 'km';

  @override
  String get signInTitle => 'Connexion';

  @override
  String get signInHint =>
      'Saisissez votre numéro de téléphone enregistré auprès de l\'entreprise. Le code de connexion arrive sur WhatsApp.';

  @override
  String get phoneLabel => 'Téléphone';

  @override
  String get phoneInvalid =>
      '8 chiffres koweïtiens, ou un numéro international commençant par +';

  @override
  String get sendCode => 'Envoyer le code';

  @override
  String get activationTip =>
      'Si vous avez reçu un lien d\'activation sur WhatsApp, ouvrez-le sur ce téléphone : aucun code n\'est nécessaire.';

  @override
  String get otpTitle => 'Code de connexion';

  @override
  String otpHint(String phone) {
    return 'Saisissez le code à 6 chiffres envoyé sur WhatsApp au $phone.';
  }

  @override
  String get otpLabel => 'Code';

  @override
  String get verify => 'Se connecter';

  @override
  String get otpResend => 'Pas de code ? Renvoyer';

  @override
  String get activating => 'Activation de l\'application sur ce téléphone…';

  @override
  String get activationFailed => 'Échec de l\'activation';

  @override
  String get permTitle => 'Autorisations de l\'application';

  @override
  String get permIntro =>
      'Pour suivre le véhicule pendant votre garde, même application fermée, l\'application a besoin de ces autorisations. Votre position n\'est enregistrée que lorsqu\'un véhicule est sous votre garde.';

  @override
  String get permLocation => 'Position : « Toujours autoriser »';

  @override
  String get permLocationWhy =>
      'Pour que le superviseur voie le véhicule pendant votre garde.';

  @override
  String get permNotifications => 'Notifications';

  @override
  String get permNotificationsWhy =>
      'Une notification permanente s\'affiche pendant le suivi (règle Android).';

  @override
  String get permBattery => 'Ignorer l\'optimisation de la batterie';

  @override
  String get permBatteryWhy =>
      'Pour que le téléphone n\'arrête pas le suivi en arrière-plan.';

  @override
  String get permGrant => 'Autoriser';

  @override
  String get permGranted => 'Autorisé';

  @override
  String get permSettings => 'Ouvrir les paramètres';

  @override
  String get permLocationRequired =>
      'L\'autorisation de localisation est nécessaire pour continuer.';

  @override
  String get gpsOff =>
      'Le GPS est désactivé : activez-le dans les paramètres du téléphone.';

  @override
  String get obTitle => 'Finaliser l\'inscription';

  @override
  String get obIntro =>
      'Saisissez vos informations et photographiez vos documents et le véhicule. Rien n\'est officiel avant la vérification par l\'entreprise.';

  @override
  String obRejected(String reason) {
    return 'Votre inscription a été renvoyée : $reason';
  }

  @override
  String get obStepData => 'Informations';

  @override
  String get obStepDocs => 'Documents';

  @override
  String get obStepVehicle => 'Véhicule';

  @override
  String get obStepReview => 'Vérification';

  @override
  String get civilId => 'Carte d\'identité civile';

  @override
  String get civilIdInvalid =>
      'La carte d\'identité civile comporte 12 chiffres';

  @override
  String get nationality => 'Nationalité';

  @override
  String get docNumber => 'Numéro du document';

  @override
  String get docExpiry => 'Date d\'expiration';

  @override
  String get docFront => 'Recto';

  @override
  String get docBack => 'Verso';

  @override
  String get pickPhoto => 'Photo';

  @override
  String get takePhoto => 'Prendre une photo';

  @override
  String get fromGallery => 'Depuis la galerie';

  @override
  String get uploading => 'Envoi en cours…';

  @override
  String get required => 'Obligatoire';

  @override
  String get plate => 'Numéro d\'immatriculation';

  @override
  String get plateHint => 'Comme sur la plaque, ex. 18/23456';

  @override
  String get odometerKm => 'Compteur (km)';

  @override
  String get odometerPhoto => 'Photo du compteur';

  @override
  String get noVehicle => 'Pas de véhicule avec moi maintenant';

  @override
  String get vehiclePhotos => 'Photos de l\'état du véhicule';

  @override
  String get obSubmit => 'Envoyer pour vérification';

  @override
  String obMissing(String items) {
    return 'À compléter : $items';
  }

  @override
  String get obWaitingTitle => 'Vos informations sont en cours de vérification';

  @override
  String get obWaitingText =>
      'Vous recevrez un message WhatsApp une fois approuvé ou si quelque chose doit être corrigé.';

  @override
  String get refresh => 'Actualiser';

  @override
  String get position_front => 'Avant';

  @override
  String get position_back => 'Arrière';

  @override
  String get position_left => 'Côté gauche';

  @override
  String get position_right => 'Côté droit';

  @override
  String get position_interior => 'Intérieur';

  @override
  String get position_other => 'Autre';

  @override
  String get tabHome => 'Accueil';

  @override
  String get tabCash => 'Espèces';

  @override
  String get tabAccount => 'Compte';

  @override
  String get noCustody => 'Aucun véhicule sous votre garde actuellement';

  @override
  String get noCustodyHint =>
      'Quand un véhicule vous est remis, il s\'affiche ici et le suivi démarre tout seul.';

  @override
  String custodySince(String when) {
    return 'Sous votre garde depuis $when';
  }

  @override
  String lastKm(String km) {
    return 'Dernier relevé : $km km';
  }

  @override
  String get trackingOn => 'Suivi activé';

  @override
  String get trackingOff => 'Suivi désactivé';

  @override
  String trackingWaiting(String count) {
    return 'En attente d\'envoi : $count';
  }

  @override
  String get startDay => 'Commencer la journée';

  @override
  String get startDayDone => 'Journée commencée';

  @override
  String get endDay => 'Terminer la journée';

  @override
  String get dailyReport => 'Rapport quotidien';

  @override
  String get outboxTitle => 'En attente d\'envoi';

  @override
  String get outboxQueued => 'Envoyé automatiquement au retour du réseau';

  @override
  String outboxFailed(String reason) {
    return 'Non accepté : $reason';
  }

  @override
  String get outboxDiscard => 'Supprimer';

  @override
  String get kind_odometer => 'Relevé du compteur';

  @override
  String get kind_report => 'Rapport quotidien';

  @override
  String get startDayTitle => 'Début de journée';

  @override
  String get endDayDone => 'Journée terminée';

  @override
  String get startAgain => 'Recommencer';

  @override
  String reportAddsToDay(String orders) {
    return 'Ce rapport s\'ajoute à ce que vous avez déjà envoyé aujourd\'hui ($orders commandes). Saisissez uniquement les commandes et les espèces de cette session.';
  }

  @override
  String reportSession(String n) {
    return 'Session $n';
  }

  @override
  String get endReadingIntro =>
      'Avant le rapport du jour : la photo et le relevé du compteur de fin de journée. Le relevé part d\'abord, puis le rapport.';

  @override
  String get status_returned => 'Renvoyé pour correction';

  @override
  String get editReportTitle => 'Modifier le rapport';

  @override
  String get changeReportTitle =>
      'Demander la modification d\'un rapport approuvé';

  @override
  String get changeReportIntro =>
      'Ce rapport est approuvé : votre demande va au bureau et s\'applique une fois approuvée.';

  @override
  String get changeReason => 'Motif de la modification';

  @override
  String get newScreenshotOptional => 'Nouvelle capture d\'écran (facultatif)';

  @override
  String get reportExistsForDay =>
      'Vous avez déjà envoyé le rapport de ce jour. Modifiez-le au lieu d\'en envoyer un second.';

  @override
  String get editReport => 'Modifier le rapport';

  @override
  String get changePending => 'Modification en attente du bureau';

  @override
  String returnedNote(Object note) {
    return 'Renvoyé par le bureau : $note';
  }

  @override
  String get myCar => 'Ma voiture';

  @override
  String get carSince => 'Sous votre garde depuis';

  @override
  String get lastReading => 'Dernier relevé du compteur';

  @override
  String get registrationExpiry => 'Expiration de l\'immatriculation';

  @override
  String get requestVehicleChange => 'Demander un autre véhicule';

  @override
  String get vehicleChangeReason => 'Motif';

  @override
  String get vehicleChangePending =>
      'Votre demande d\'un autre véhicule est chez le superviseur';

  @override
  String vehicleChangeRejected(Object note) {
    return 'Votre demande d\'un autre véhicule a été refusée : $note';
  }

  @override
  String get profileTitle => 'Mes informations';

  @override
  String get employeeNumber => 'N° d\'employé';

  @override
  String get companyLabel => 'Entreprise';

  @override
  String get platformLabel => 'Plateforme';

  @override
  String get bankLabel => 'Banque';

  @override
  String get myDocuments => 'Mes documents';

  @override
  String get docValid => 'Valide';

  @override
  String docExpiring(Object days) {
    return 'Expire dans $days jours';
  }

  @override
  String get docExpired => 'Expiré';

  @override
  String get docMissing => 'Non enregistré';

  @override
  String docExpires(Object date) {
    return 'Expire le $date';
  }

  @override
  String get uploadRenewal => 'Envoyer le document renouvelé';

  @override
  String get renewalPending => 'Renouvellement en attente du bureau';

  @override
  String renewalRejected(Object note) {
    return 'Renouvellement refusé : $note';
  }

  @override
  String get newExpiry => 'Nouvelle date d\'expiration';

  @override
  String get documentNumber => 'Numéro du document (facultatif)';

  @override
  String get documentPhoto => 'Photo du document';

  @override
  String get pickDate => 'Choisir la date';

  @override
  String cashNearLimit(Object limit) {
    return 'Votre solde approche de la limite d\'alerte ($limit) : remettez bientôt les espèces.';
  }

  @override
  String get movements => 'Mouvements';

  @override
  String get noMovements => 'Aucun mouvement pour l\'instant';

  @override
  String get moveCollection => 'Espèces du rapport quotidien';

  @override
  String get moveReceipt => 'Remis contre reçu';

  @override
  String get moveAdjustment => 'Correction';

  @override
  String get moveReversal => 'Annulation';

  @override
  String get moveSettlement => 'Solde de fin de service';

  @override
  String get moveOpening => 'Solde d\'ouverture';

  @override
  String get endDayTitle => 'Fin de journée';

  @override
  String get odometerIntro =>
      'Photographiez clairement le compteur, puis saisissez le relevé tel qu\'il apparaît sur la photo.';

  @override
  String get retake => 'Reprendre';

  @override
  String kmLower(String km) {
    return 'Inférieur au dernier relevé ($km km). Vérifiez-le : il sera examiné.';
  }

  @override
  String get kmInvalid => 'Saisissez le relevé en chiffres';

  @override
  String get photoRequired => 'La photo est obligatoire';

  @override
  String get sentTitle => 'Envoyé';

  @override
  String get queuedTitle => 'Enregistré sur le téléphone';

  @override
  String get sentText => 'L\'entreprise l\'a reçu.';

  @override
  String get queuedText =>
      'Pas de réseau pour le moment. Il sera envoyé automatiquement, avec son heure d\'origine, au retour de la connexion.';

  @override
  String get reportTitle => 'Rapport quotidien';

  @override
  String get reportDate => 'Jour de travail';

  @override
  String get today => 'Aujourd\'hui';

  @override
  String get yesterday => 'Hier';

  @override
  String get dayBefore => 'Avant-hier';

  @override
  String get ordersCount => 'Commandes';

  @override
  String get cashAmount => 'Espèces encaissées';

  @override
  String get cashInvalid => 'Un montant avec au plus trois décimales';

  @override
  String get screenshot =>
      'Capture d\'écran du résumé du jour dans l\'application de livraison';

  @override
  String get notes => 'Remarques';

  @override
  String get recentReports => 'Rapports récents';

  @override
  String get status_submitted => 'En attente de vérification';

  @override
  String get status_approved => 'Approuvé';

  @override
  String get status_rejected => 'Refusé';

  @override
  String approvedCash(String amount) {
    return 'Approuvé : $amount';
  }

  @override
  String get cashTitle => 'Espèces';

  @override
  String get cashTotal => 'Espèces que vous détenez';

  @override
  String get cashPosted => 'Approuvé';

  @override
  String get cashPending => 'En attente de vérification';

  @override
  String cashOverLimit(String limit) {
    return 'Au-dessus de la limite ($limit) : remettez les espèces au caissier.';
  }

  @override
  String get receipts => 'Reçus';

  @override
  String receiptNo(String no) {
    return 'Reçu n° $no';
  }

  @override
  String get confirmReceipt => 'Je confirme';

  @override
  String get receiptConfirmed => 'Confirmé';

  @override
  String confirmReceiptQ(String amount) {
    return 'Avez-vous remis $amount KWD au caissier ?';
  }

  @override
  String get noReceipts => 'Aucun reçu pour l\'instant';

  @override
  String get language => 'Langue';

  @override
  String get trackingDetails => 'État du suivi';

  @override
  String lastUpload(String when) {
    return 'Dernier envoi : $when';
  }

  @override
  String get never => 'pas encore';

  @override
  String appVersion(String version) {
    return 'Version $version';
  }

  @override
  String get signOut => 'Se déconnecter';

  @override
  String get signOutQ =>
      'Le suivi s\'arrête et une nouvelle activation sera nécessaire pour vous connecter. Continuer ?';

  @override
  String get blockedTitle => 'Votre compte est suspendu';

  @override
  String get blockedText => 'Contactez votre superviseur.';

  @override
  String get obReady => 'Tout est prêt : envoyez pour vérification.';

  @override
  String get maintenance => 'Entretien';

  @override
  String get maintenanceTitle => 'Demandes d\'entretien';

  @override
  String get kind_maintenance => 'Demande d\'entretien';

  @override
  String get mntNew => 'Nouvelle demande d\'entretien';

  @override
  String get mntIntro =>
      'Décrivez le problème et prenez des photos. Une voiture accidentée est réparée par l\'intermédiaire du bureau.';

  @override
  String get mntDirectIntro =>
      'Décrivez le problème, prenez des photos et choisissez le centre d\'entretien où vous emmènerez la voiture. La demande va directement au centre, la voiture reste sous votre garde et vous êtes prévenu quand elle est prête.';

  @override
  String get mntCenter => 'Centre d\'entretien';

  @override
  String get mntPickedUp => 'J\'ai récupéré la voiture';

  @override
  String get pickupTitle => 'Récupération de la voiture au centre';

  @override
  String get pickupIntro =>
      'Photographiez le compteur et saisissez le relevé en récupérant la voiture : elle revient sous votre garde et vous commencez votre journée comme d\'habitude.';

  @override
  String get kind_pickup => 'Voiture récupérée de l\'entretien';

  @override
  String get mntNoVehicle =>
      'L\'entretien se demande pour le véhicule sous votre garde. Vous n\'en avez pas actuellement.';

  @override
  String get mntKind => 'Type';

  @override
  String get mntDescription => 'Quel est le problème';

  @override
  String get mntOdometer => 'Compteur (facultatif)';

  @override
  String get mntPhotos => 'Photos (jusqu\'à 4)';

  @override
  String get mntAddPhoto => 'Photo';

  @override
  String get mntNone => 'Aucune demande d\'entretien';

  @override
  String mntRequestNo(String number) {
    return 'Demande n° $number';
  }

  @override
  String mntAtCenter(String center) {
    return 'Centre : $center';
  }

  @override
  String mntReadyBanner(String plate, String center) {
    return 'Votre véhicule $plate est prêt à être récupéré chez $center';
  }

  @override
  String mntRejected(String reason) {
    return 'Refusée : $reason';
  }

  @override
  String get mntSent => 'Votre demande d\'entretien a été envoyée au centre';

  @override
  String get mntKind_periodic => 'Entretien périodique';

  @override
  String get mntKind_mechanical => 'Mécanique';

  @override
  String get mntKind_electrical => 'Électrique';

  @override
  String get mntKind_tyres => 'Pneus';

  @override
  String get mntKind_battery => 'Batterie';

  @override
  String get mntKind_ac => 'Climatisation';

  @override
  String get mntKind_bodywork => 'Carrosserie';

  @override
  String get mntKind_other => 'Autre';

  @override
  String get mntStatus_requested => 'En attente d\'approbation';

  @override
  String get mntStatus_approved => 'Approuvée';

  @override
  String get mntStatus_rejected => 'Refusée';

  @override
  String get mntStatus_referred => 'Envoyée au centre';

  @override
  String get mntStatus_at_center => 'Au centre';

  @override
  String get mntStatus_ready => 'Prête à récupérer';

  @override
  String get mntStatus_picked_up => 'Récupérée';

  @override
  String get mntStatus_closed => 'Clôturée';

  @override
  String get mntStatus_cancelled => 'Annulée';

  @override
  String get mntTapToRemove => 'touchez pour retirer';

  @override
  String get accident => 'Déclarer un accident';

  @override
  String get accidentsTitle => 'Accidents';

  @override
  String get kind_accident => 'Déclaration d\'accident';

  @override
  String get kind_police_report => 'Rapport de police';

  @override
  String get accNew => 'Nouvelle déclaration d\'accident';

  @override
  String get accEmergency =>
      'Si quelqu\'un est blessé, appelez d\'abord le 112.';

  @override
  String get accIntro =>
      'Photographiez le véhicule sous plusieurs angles : avant, arrière, les deux côtés et les dégâts. L\'heure et le lieu sont enregistrés automatiquement.';

  @override
  String get accNoVehicle =>
      'Un accident se déclare pour le véhicule que vous détenez. Vous n\'en avez pas actuellement : appelez votre superviseur.';

  @override
  String get accDescription => 'Que s\'est-il passé ?';

  @override
  String get accInjuries => 'Quelqu\'un est blessé';

  @override
  String get accInjuriesNote => 'Détails des blessures';

  @override
  String get accOtherParty => 'L\'autre partie (plaque, nom, assureur)';

  @override
  String accPhotos(String min) {
    return 'Photos de l\'accident (au moins $min)';
  }

  @override
  String accPhotosNeeded(String min) {
    return 'Prenez au moins $min photos sous différents angles';
  }

  @override
  String get accPoliceReport => 'Rapport de police';

  @override
  String get accPoliceReportNo => 'Numéro du rapport';

  @override
  String get accPoliceLater =>
      'Pas encore de rapport ? Envoyez maintenant et envoyez plus tard une photo du rapport de police depuis vos accidents ci-dessous.';

  @override
  String get accSendPolice => 'Envoyer le rapport de police';

  @override
  String get accNone => 'Aucun accident';

  @override
  String accNo(String number) {
    return 'Accident n° $number';
  }

  @override
  String get accStage_review => 'En cours d\'examen';

  @override
  String get accStage_outcome => 'En attente de la décision de responsabilité';

  @override
  String get accStage_recorded => 'Responsabilité décidée';

  @override
  String get accStage_closed => 'Clôturé';

  @override
  String get accLiability_none => 'Vous n\'êtes pas responsable';

  @override
  String get accLiability_driver => 'Vous êtes responsable';

  @override
  String accLiability_shared(String percent) {
    return 'Responsabilité partagée : votre part $percent %';
  }

  @override
  String accDeduction(String total, String count) {
    return 'Retenue $total KWD · échéances : $count';
  }

  @override
  String accInstallment(String month, String amount) {
    return '$month : $amount KWD';
  }

  @override
  String accAwaitingPolice(String number) {
    return 'L\'accident n° $number attend le rapport de police : touchez pour en envoyer une photo';
  }

  @override
  String get fines => 'Amendes de circulation';

  @override
  String get finesTitle => 'Amendes de circulation';

  @override
  String get finesIntro =>
      'Les amendes sur le véhicule pendant que vous le déteniez, selon l\'heure de l\'amende. L\'entreprise décide : elle les prend en charge, ou elles sont retenues sur votre salaire en échéances.';

  @override
  String get finesNone => 'Aucune amende';

  @override
  String get fineStatus_open => 'En cours d\'examen';

  @override
  String get fineStatus_charged => 'Retenue sur votre salaire';

  @override
  String get fineStatus_company => 'Prise en charge par l\'entreprise';

  @override
  String get monthlyStatement => 'Relevé mensuel de la plateforme';

  @override
  String get payslips => 'Bulletins de paie';

  @override
  String get statementTitle => 'Relevé mensuel de la plateforme';

  @override
  String statementIntro(String platform) {
    return 'Au début de chaque mois, envoyez des captures d\'écran du résumé du mois depuis l\'application $platform et saisissez les chiffres tels qu\'ils apparaissent. Le bureau les vérifie avec les captures avant la paie.';
  }

  @override
  String get statementNoPlatform =>
      'Votre plateforme n\'est pas encore définie. Contactez le bureau.';

  @override
  String get statementNoMonth =>
      'Vous avez envoyé tous les mois ouverts. Attendez la vérification du bureau.';

  @override
  String get statementMonth => 'Mois';

  @override
  String get statementShots =>
      'Captures d\'écran de l\'application de la plateforme (jusqu\'à 6)';

  @override
  String get statementShotRequired => 'Ajoutez au moins une capture d\'écran';

  @override
  String get statementHistory => 'Ce que vous avez envoyé';

  @override
  String statementSentDays(String days) {
    return 'Envoyé : $days jours valides';
  }

  @override
  String statementApprovedDays(String days) {
    return 'Approuvé : $days jours valides';
  }

  @override
  String get statementStatus_submitted => 'En attente de vérification';

  @override
  String get statementStatus_approved => 'Approuvé';

  @override
  String get statementStatus_rejected => 'Refusé : renvoyez-le';

  @override
  String get addShot => 'Ajouter une capture d\'écran';

  @override
  String get validDays => 'Jours valides';

  @override
  String get ordersTotal => 'Total des commandes';

  @override
  String get hoursTotal => 'Total des heures';

  @override
  String get payslipsTitle => 'Bulletins de paie';

  @override
  String get payslipsNone => 'Aucun bulletin de paie approuvé pour l\'instant';

  @override
  String get payslipNet => 'Salaire net';

  @override
  String get payslipStatus_approved => 'Approuvé';

  @override
  String get payslipStatus_paid => 'Payé';

  @override
  String get iban => 'IBAN';

  @override
  String get ibanHint =>
      'Votre salaire y est versé : copiez-le depuis l\'application de votre banque';

  @override
  String get bankName => 'Nom de la banque';

  @override
  String get civilSignIn => 'Se connecter avec la carte d\'identité civile';

  @override
  String get civilSignInHint =>
      'Si l\'entreprise n\'a pas votre numéro de téléphone : connectez-vous avec votre carte d\'identité civile et le mot de passe initial donné par le bureau, puis enregistrez votre téléphone. Le mot de passe ne sert qu\'une fois.';

  @override
  String get initialPassword => 'Mot de passe initial';

  @override
  String get claimContinue => 'Continuer';

  @override
  String claimWelcome(String name) {
    return 'Bienvenue $name. Saisissez votre numéro de téléphone qui a WhatsApp : le code y est envoyé, et vous vous connectez avec lui désormais.';
  }

  @override
  String get password => 'Mot de passe';

  @override
  String get civilSignInOnly =>
      'Connectez-vous avec votre carte d\'identité civile et votre mot de passe. La première fois : le mot de passe initial donné par le bureau, puis vous choisissez le vôtre.';

  @override
  String get forgotPassword =>
      'Mot de passe oublié ? Demandez un nouveau mot de passe initial à votre superviseur.';

  @override
  String choosePassword(String name) {
    return 'Bienvenue $name. Choisissez votre mot de passe : avec lui et votre carte d\'identité civile, vous vous connectez désormais sur n\'importe quel téléphone. Au moins 8 caractères, ni le mot de passe initial ni votre numéro d\'identité civile, et ne le dites à personne.';
  }

  @override
  String get newPassword => 'Nouveau mot de passe';

  @override
  String get confirmPassword => 'Saisissez à nouveau le mot de passe';

  @override
  String get passwordTooShort => 'Au moins 8 caractères';

  @override
  String get passwordsDiffer => 'Les deux mots de passe sont différents';

  @override
  String get passwordIsCivilId =>
      'N\'utilisez pas votre numéro d\'identité civile comme mot de passe';

  @override
  String get saveAndSignIn => 'Enregistrer et se connecter';

  @override
  String get validDayQuestion =>
      'L\'application de la plateforme a-t-elle compté ce jour comme valide ?';

  @override
  String get validDayYes => 'Jour valide';

  @override
  String get validDayNo => 'Non valide';

  @override
  String get paySchemes => 'Formule de rémunération';

  @override
  String get schemesIntro =>
      'Votre formule détermine comment votre salaire est calculé à partir de vos commandes. Vous pouvez demander une autre formule proposée par votre plateforme ; elle commence le premier du mois suivant si le bureau accepte.';

  @override
  String get schemeNow => 'Votre formule ce mois-ci';

  @override
  String get schemeNone => 'Le bureau n\'a pas encore défini votre formule';

  @override
  String schemeNextMonth(String name) {
    return 'À partir du mois prochain : $name';
  }

  @override
  String get schemeOthers => 'Autres formules de votre plateforme';

  @override
  String get schemeAsk => 'Demander cette formule';

  @override
  String schemeAskBody(String name, String month) {
    return 'Vous demandez « $name » à partir de $month. Le bureau l\'examine et vous recevez la réponse ici et sur WhatsApp.';
  }

  @override
  String get schemeNoteHint => 'Une remarque pour le bureau (facultatif)';

  @override
  String get schemeSend => 'Envoyer la demande';

  @override
  String get schemeSent => 'Votre demande a été envoyée au bureau';

  @override
  String schemePending(String name, String month) {
    return 'Votre demande pour « $name » à partir de $month attend le bureau';
  }

  @override
  String schemeApproved(String name, String month) {
    return 'Approuvée : « $name » à partir de $month';
  }

  @override
  String schemeRejected(String name, String note) {
    return 'Le bureau a refusé « $name » : $note';
  }

  @override
  String get schemeCancel => 'Annuler la demande';

  @override
  String schemePerOrder(String rate) {
    return 'Par commande : $rate KWD';
  }

  @override
  String get schemeBatchRates =>
      'Prix par commande selon le niveau de batch du mois :';

  @override
  String schemeBatchRow(String level, String rate) {
    return 'Batch $level : $rate KWD';
  }

  @override
  String schemeReduced(String rate, String marks) {
    return 'Descend à $rate KWD pour chaque commande du mois si vous manquez un Star Day ou atteignez $marks points';
  }

  @override
  String schemeReducedStar(String rate) {
    return 'Descend à $rate KWD pour chaque commande du mois si vous manquez un Star Day';
  }

  @override
  String get schemeReducedLoses =>
      'Un mois réduit ne donne pas de prime de palier';

  @override
  String get schemeTiers =>
      'Prime de palier (uniquement le plus haut palier atteint) :';

  @override
  String schemeTierRow(String orders, String amount) {
    return '$orders commandes : $amount KWD';
  }

  @override
  String get schemeMarks => 'Retenue pour points d\'assiduité :';

  @override
  String schemeMarkRow(String marks, String amount) {
    return '$marks points : $amount KWD';
  }

  @override
  String schemeTarget(String orders, String days) {
    return 'Objectif : $orders commandes et $days jours valides par mois';
  }

  @override
  String schemeMissing(String rate) {
    return 'Chaque commande manquante par rapport à l\'objectif retient $rate KWD';
  }

  @override
  String get schemeNoMissing => 'Pas de retenue pour les commandes manquantes';

  @override
  String schemeCovers(String items) {
    return 'L\'entreprise paie : $items';
  }

  @override
  String get schemeCoversNone =>
      'Vous payez les frais : entretien, logement, essence et carte SIM';

  @override
  String get schemePlatformRates =>
      'La règle propre à la plateforme : un salaire de base et les tarifs de l\'entreprise';

  @override
  String get expense_maintenance => 'l\'entretien';

  @override
  String get expense_housing => 'le logement';

  @override
  String get expense_gas => 'l\'essence';

  @override
  String get expense_sim => 'la carte SIM';

  @override
  String get schemeChoose => 'Formule de rémunération';

  @override
  String get schemeChooseHint =>
      'Choisissez la formule sur laquelle vous travaillez. Le bureau l\'examine avec votre inscription, et vous pourrez demander à la changer plus tard depuis l\'application.';

  @override
  String payslipScheme(String name) {
    return 'Comment votre formule a calculé le mois : $name';
  }

  @override
  String get payItem_orders_pay => 'Commandes';

  @override
  String get payItem_tier_bonus => 'Prime de palier';

  @override
  String get payItem_missing_target => 'Sous l\'objectif';

  @override
  String get payItem_marks_deduction => 'Points d\'assiduité';

  @override
  String get payItem_uncovered_penalty => 'Retenues non prélevées (à examiner)';

  @override
  String payWhyOrders(String orders, String rate) {
    return '$orders commandes × $rate KWD';
  }

  @override
  String payWhyBatch(String level) {
    return 'batch $level';
  }

  @override
  String get payWhyReducedStar => 'prix réduit : un Star Day manqué';

  @override
  String get payWhyReducedMarks => 'prix réduit : points d\'assiduité';

  @override
  String payWhyTier(String orders, String from) {
    return '$orders commandes : le palier $from';
  }

  @override
  String payWhyMissing(String missing, String target, String rate) {
    return '$missing commandes sous l\'objectif de $target × $rate KWD';
  }

  @override
  String payWhyMarks(String marks) {
    return '$marks points d\'assiduité';
  }

  @override
  String get payWhyUncovered =>
      'Les retenues supérieures à la paie du mois ne sont pas prélevées, le net ne descend jamais sous zéro : le bureau examine le reste';

  @override
  String get noticesTitle => 'Notifications';

  @override
  String get noticesNone => 'Aucune notification pour l\'instant';

  @override
  String get nameLabel => 'Nom';

  @override
  String get obOnFile =>
      'Les champs verrouillés sont enregistrés par l\'entreprise. Si l\'un d\'eux est faux, demandez au bureau de le corriger.';

  @override
  String get nationalityPick => 'Choisissez votre nationalité';

  @override
  String get searchArEn => 'Rechercher en arabe ou en anglais';

  @override
  String get noMatches => 'Aucun résultat';

  @override
  String get ibanInvalid =>
      'Un caractère de cet IBAN est faux (les chiffres de contrôle ne correspondent pas) : copiez-le depuis l\'application de votre banque';

  @override
  String obFieldsInvalid(String fields) {
    return 'Vérifiez ces champs : $fields';
  }

  @override
  String ibanLengthKw(int count) {
    return 'Un IBAN koweïtien a 30 caractères et commence par KW ; celui-ci en a $count';
  }

  @override
  String get driverWorking => 'Chauffeur au travail';

  @override
  String get driverNotWorking => 'Chauffeur hors service';

  @override
  String greeting(String name) {
    return 'Bonjour, $name';
  }

  @override
  String get yourCar => 'Votre voiture';

  @override
  String get quickActions => 'Actions rapides';

  @override
  String get dayNotStarted => 'Vous n\'avez pas commencé votre journée';

  @override
  String get dayNotStartedHint =>
      'Commencez par une photo du compteur avec l\'appareil photo';

  @override
  String dayStartedAt(String time) {
    return 'Votre journée a commencé à $time';
  }

  @override
  String dayStartKm(String km) {
    return 'Compteur de départ $km';
  }

  @override
  String get dayEndedHint => 'Vous retravaillez aujourd\'hui ? Recommencez';

  @override
  String get agoNow => 'à l\'instant';

  @override
  String agoMinutes(String n) {
    return 'il y a $n min';
  }

  @override
  String agoHours(String n) {
    return 'il y a $n h';
  }

  @override
  String agoDays(String n) {
    return 'il y a $n j';
  }

  @override
  String lastSentAgo(String ago) {
    return 'dernier envoi $ago';
  }

  @override
  String get qaBalance => 'Mon solde';

  @override
  String get qaReceipts => 'Mes reçus';

  @override
  String qaReceiptsWaiting(String n) {
    return '$n à confirmer';
  }

  @override
  String get qaReceiptsDone => 'Tous confirmés';

  @override
  String get qaMaintenanceSub => 'Une panne ou une remarque';

  @override
  String get qaAccidentSub => 'Photos + rapport de police';

  @override
  String get qaReportSub => 'Commandes et espèces du jour';

  @override
  String get qaFinesSub => 'Amendes sur votre voiture';

  @override
  String get qaStatementSub => 'Captures mensuelles de la plateforme';

  @override
  String get qaPayslipsSub => 'Votre paie mensuelle';

  @override
  String get qaSchemesSub => 'Comment votre paie est calculée';

  @override
  String get tabWork => 'Travail du jour';

  @override
  String get todayReport => 'Rapport du jour';

  @override
  String get workReportSent => 'Le rapport du jour est envoyé';

  @override
  String get workReportDue => 'Le rapport du jour n\'est pas encore envoyé';

  @override
  String get workReportDueHint =>
      'Envoyez les commandes et les espèces comme dans l\'application de la plateforme';

  @override
  String get sendDailyReport => 'Envoyer le rapport quotidien';

  @override
  String ordersCash(String orders, String cash) {
    return '$orders commandes · $cash';
  }

  @override
  String get myRequests => 'Mes demandes';

  @override
  String get cashBalanceTitle => 'Votre solde (KWD)';

  @override
  String cashPendingPart(String amount) {
    return 'dont $amount pas encore approuvé';
  }

  @override
  String cashLimit(String amount) {
    return 'Limite d\'alerte $amount';
  }

  @override
  String employeeAt(String number, String company) {
    return '$number · $company';
  }

  @override
  String get thisPhone => 'Ce téléphone';

  @override
  String get takeOdometerPhoto => 'Prendre la photo du compteur';

  @override
  String get cameraOnly =>
      'Appareil photo uniquement — la galerie n\'est pas autorisée';

  @override
  String lastKmHint(String km) {
    return 'Dernier relevé enregistré pour la voiture : $km';
  }

  @override
  String get cashHint =>
      'Comme indiqué dans l\'application de la société de livraison';

  @override
  String get mntDescriptionHint => 'ex. un bruit au freinage';

  @override
  String get accSend => 'Envoyer la déclaration';

  @override
  String get workReportQueued =>
      'Le rapport du jour est enregistré sur le téléphone';

  @override
  String get reportQueuedForDay =>
      'Le rapport de ce jour est enregistré sur le téléphone et part tout seul au retour de la connexion. Ne le renvoyez pas.';

  @override
  String ordersN(String n) {
    return '$n commandes';
  }

  @override
  String get workReportDueHintDays =>
      'Envoyez les commandes et si le jour a été compté comme valide';

  @override
  String get qaReportSubDays => 'Commandes du jour et jour valide';

  @override
  String get notSentYet => 'Pas encore envoyé';

  @override
  String get fuel => 'Carburant';

  @override
  String get qaFuelSub => 'Carburant payé avec les espèces';

  @override
  String get fuelTitle => 'Carburant payé avec les espèces';

  @override
  String get fuelIntro =>
      'Photographiez le reçu de carburant et saisissez le montant. Le comptable le vérifie quand il reçoit vos espèces ; une fois approuvé, le montant est déduit des espèces que vous détenez.';

  @override
  String get fuelReceipt => 'Photo du reçu de carburant';

  @override
  String get fuelTakeReceipt => 'Photographier le reçu';

  @override
  String get fuelReceiptMissing => 'La photo du reçu est obligatoire';

  @override
  String get fuelAmount => 'Montant payé';

  @override
  String get fuelAmountInvalid =>
      'Saisissez le montant en KWD, jusqu\'à 3 décimales';

  @override
  String fuelAmountMax(String max) {
    return 'Un reçu ne peut pas dépasser $max KWD';
  }

  @override
  String get fuelOdometer => 'Relevé du compteur (facultatif)';

  @override
  String get fuelNotes => 'Remarques (facultatif)';

  @override
  String get fuelSend => 'Envoyer pour vérification';

  @override
  String get fuelMine => 'Reçus de carburant';

  @override
  String get fuelNone => 'Aucun reçu de carburant pour l\'instant';

  @override
  String get fuelPending => 'En attente de vérification';

  @override
  String fuelApproved(String amount) {
    return 'Approuvé ($amount)';
  }

  @override
  String get fuelRejected => 'Refusé';

  @override
  String get fuelOff_fuel_card =>
      'Vous avez une carte carburant de l\'entreprise : le bureau la recharge, et le carburant n\'est pas réclamé sur vos espèces.';

  @override
  String get fuelOff_not_covered =>
      'Le carburant est à votre charge selon votre formule de rémunération, il n\'est donc pas facturé à l\'entreprise.';

  @override
  String get fuelOff_no_vehicle =>
      'Aucun véhicule n\'est sous votre garde actuellement : le carburant est enregistré pour la voiture que vous détenez.';

  @override
  String get kind_fuel => 'Reçu de carburant';

  @override
  String get moveFuel => 'Carburant';

  @override
  String get vehicleChangePlate =>
      'Numéro d\'immatriculation de l\'autre véhicule';

  @override
  String get vehicleChangePlateHint => '12-34567';

  @override
  String vehicleChangePendingFor(String plate) {
    return 'Votre demande de changement pour $plate est en cours d\'examen';
  }

  @override
  String get claimVehicle => 'Enregistrer une nouvelle voiture';

  @override
  String get claimVehicleHint =>
      'Vous avez pris une voiture ? Enregistrez-la ici avec son relevé de compteur ; votre garde commence quand le bureau approuve.';

  @override
  String get claimTitle => 'Enregistrer une nouvelle voiture';

  @override
  String get claimPlate => 'Numéro d\'immatriculation de la voiture';

  @override
  String get claimIntro =>
      'Prenez la photo du compteur avec l\'appareil photo et saisissez le relevé. La demande va au bureau ; une fois approuvée, la voiture est à vous depuis l\'heure de la photo.';

  @override
  String get claimConditionPhotos =>
      'Photos de l\'état de la voiture (facultatif)';

  @override
  String get claimSend => 'Envoyer au bureau';

  @override
  String claimPending(String plate) {
    return 'Votre demande pour prendre la voiture $plate attend l\'approbation du bureau';
  }

  @override
  String claimRejected(String plate, String reason) {
    return 'Le bureau a refusé votre demande pour prendre la voiture $plate : $reason';
  }

  @override
  String get kind_vehicle_claim => 'Enregistrement de voiture';

  @override
  String get mntNoCenter =>
      'Aucun centre d\'entretien n\'est disponible : appelez le bureau';

  @override
  String mntInMaintenance(String center) {
    return 'Votre voiture est au centre d\'entretien : $center';
  }

  @override
  String get mntInMaintenanceAny => 'Votre voiture est au centre d\'entretien';

  @override
  String get mntInMaintenanceHint =>
      'La voiture est toujours sous votre garde, mais aucune journée de travail ne commence avec elle tant que vous ne l\'avez pas récupérée au centre et confirmé ici.';

  @override
  String get fieldYes => 'Oui';

  @override
  String get fieldNo => 'Non';

  @override
  String get fieldInvalid => 'Valeur non valide';

  @override
  String get choose => 'Choisir';

  @override
  String get objectPayslip => 'Contester ce bulletin de paie';

  @override
  String get objectLine => 'Contester cette ligne';

  @override
  String get objectionTitle => 'Contestation du bulletin de paie';

  @override
  String objectionOn(String what) {
    return 'Objet : $what';
  }

  @override
  String get objectionWhole => 'Tout le bulletin de paie';

  @override
  String get objectionReason => 'Pourquoi vous contestez';

  @override
  String get objectionReasonShort => 'Écrivez le motif (au moins 3 lettres)';

  @override
  String get objectionFile => 'Une photo qui le montre (facultatif)';

  @override
  String get objectionCamera => 'Appareil photo';

  @override
  String get objectionGallery => 'Galerie';

  @override
  String get objectionSent =>
      'Votre contestation a été envoyée ; le bureau répondra';

  @override
  String get objectionQueued =>
      'Votre contestation sera envoyée au retour de la connexion';

  @override
  String get myObjections => 'Mes contestations';

  @override
  String objectionResponse(String text) {
    return 'Le bureau : $text';
  }

  @override
  String objectionAction(String text) {
    return 'Mesure prise : $text';
  }

  @override
  String get objectionStatus_open => 'Ouverte';

  @override
  String get objectionStatus_in_review => 'En cours d\'examen';

  @override
  String get objectionStatus_accepted => 'Acceptée';

  @override
  String get objectionStatus_rejected => 'Refusée';

  @override
  String get objectionStatus_closed => 'Clôturée';

  @override
  String get objectionInstallment => 'Une échéance';

  @override
  String vehicleChangeApprovedFor(String plate) {
    return 'Votre changement pour $plate a été approuvé : récupérez-la au bureau';
  }

  @override
  String get receiptReversed => 'Annulé';

  @override
  String pickupReplacementTitle(String plate) {
    return 'La voiture de remplacement $plate';
  }

  @override
  String get pickupReplacementHint =>
      'Vous la rendez en récupérant votre voiture : photographiez son compteur et saisissez le relevé.';

  @override
  String get pickupReplacementPhoto =>
      'Photo du compteur de la voiture de remplacement';

  @override
  String get fuelLitres => 'Litres (facultatif)';

  @override
  String get fuelLitresInvalid =>
      'Saisissez les litres comme sur le reçu (jusqu\'à 500)';

  @override
  String get fuelLitresUnit => 'L';

  @override
  String get replacementCar =>
      'Voiture de remplacement — la vôtre est au centre';

  @override
  String outboxAttention(String reason) {
    return 'Demande votre attention : $reason';
  }

  @override
  String get outboxTooOld => 'non envoyé depuis deux jours';

  @override
  String get outboxKeptFailing => 'le serveur n\'a pas pu l\'accepter';

  @override
  String outboxAttentionCount(int n) {
    return '$n demandent votre attention';
  }

  @override
  String get startFailedTitle => 'L\'application n\'a pas pu démarrer';

  @override
  String get startFailedBody =>
      'Une erreur s\'est produite au chargement. Vérifiez la connexion et réessayez.';

  @override
  String get activationReplaceTitle => 'Remplacer le chauffeur connecté ?';

  @override
  String get activationReplaceBody =>
      'Un chauffeur est déjà connecté sur ce téléphone. Activer ce lien le déconnecte et supprime tout ce qu\'il n\'a pas encore envoyé.';

  @override
  String get activationReplaceConfirm => 'Activer';

  @override
  String get trackingActive => 'La position est envoyée';

  @override
  String get trackingStale => 'La position n\'arrive pas';

  @override
  String get trackingUnknown => 'État du suivi inconnu';

  @override
  String noticeBigActive(String time) {
    return 'Dernière position envoyée $time';
  }

  @override
  String noticeBigStale(String time) {
    return 'Aucune position depuis $time. Ouvrez l\'application et vérifiez les paramètres de localisation';
  }

  @override
  String get noticeBigStaleNever =>
      'Aucune position envoyée pour l\'instant. Ouvrez l\'application et vérifiez les paramètres de localisation';

  @override
  String get noticeBigOff => 'Votre position n\'est pas suivie actuellement';

  @override
  String get openApp => 'Ouvrir l\'application';

  @override
  String get alertsChannel => 'Alertes importantes';

  @override
  String offlineSince(String time) {
    return 'Hors ligne · dernière mise à jour $time';
  }

  @override
  String get statusCall => 'Appeler';

  @override
  String get statusDone => 'Terminé';

  @override
  String get statusCheckSettings => 'Vérifier les paramètres';

  @override
  String get statusOpenCash => 'Espèces';

  @override
  String get statusOpenCustody => 'Ma voiture';

  @override
  String get statusOpenMaintenance => 'Entretien';

  @override
  String get statusOpenDocuments => 'Mes documents';

  @override
  String get statusOpenContact => 'Détails';

  @override
  String statusMore(String count) {
    return 'et $count autres alertes';
  }

  @override
  String statusDaySummary(String count) {
    return 'Sessions du jour : $count';
  }

  @override
  String get statusContactSent => 'Votre superviseur a été prévenu';

  @override
  String get statusDialFailed =>
      'Impossible de lancer un appel sur ce téléphone';

  @override
  String get leaves => 'Demande d\'absence';

  @override
  String get qaLeavesSub => 'Congé ou absence justifiée';

  @override
  String get leaveType => 'Type de congé';

  @override
  String leaveLeft(String days) {
    return '$days jours restants';
  }

  @override
  String get leaveFrom => 'Du';

  @override
  String get leaveTo => 'Au';

  @override
  String get leaveOneDay => 'Un jour';

  @override
  String get leaveReason => 'Motif';

  @override
  String get leaveFollowupFrom => 'Date de début du suivi';

  @override
  String get leaveAttachment => 'Pièce jointe (comme un certificat médical)';

  @override
  String get leaveAttachmentRequired => 'Ce type exige une pièce jointe';

  @override
  String get leaveCamera => 'Appareil photo';

  @override
  String get leaveGallery => 'Galerie';

  @override
  String leavePreviewDays(String days) {
    return '$days jours comptés';
  }

  @override
  String leavePaidPart(String days, String percent) {
    return '$days jours payés à $percent %';
  }

  @override
  String leaveUnpaidPart(String days) {
    return '$days jours sans solde';
  }

  @override
  String get leavePreviewOffline =>
      'Le calcul nécessite une connexion : la demande est envoyée et vérifiée au bureau';

  @override
  String get leaveSend => 'Envoyer la demande';

  @override
  String get leaveMine => 'Mes demandes';

  @override
  String get leaveNone => 'Aucune demande';

  @override
  String get leaveCancel => 'Retirer';

  @override
  String get leaveStatus_pending => 'En attente d\'approbation';

  @override
  String get leaveStatus_approved => 'Approuvée';

  @override
  String get leaveStatus_rejected => 'Refusée';

  @override
  String get leaveStatus_cancelled => 'Annulée';

  @override
  String leaveOfficeSays(String reason) {
    return 'Bureau : $reason';
  }

  @override
  String get leaveNoTypes =>
      'Aucun type de congé ne vous est disponible pour le moment';

  @override
  String get leaveDatesInvalid => 'La date de fin est avant le début';

  @override
  String get leaveTypeMissing => 'Choisissez le type de congé';

  @override
  String get noticeAtWork => 'Au travail';

  @override
  String get noticeOffDuty => 'Hors service';

  @override
  String get noticeInMaintenance => 'Voiture en maintenance';

  @override
  String get noticeAwaitingFirst => 'En attente de la première position';

  @override
  String get noticeLocating => 'Recherche de votre position…';

  @override
  String noticeShiftFrom(String time) {
    return 'Service depuis $time';
  }

  @override
  String noticeDayEnded(String count) {
    return 'Journée terminée · $count commandes';
  }

  @override
  String get noticeDayEndedNoCount => 'Journée terminée';

  @override
  String get noticeDayNotStarted => 'La journée de travail n\'a pas commencé';

  @override
  String noticeLastConfirmed(String time) {
    return 'Dernier envoi confirmé $time';
  }

  @override
  String get noticeNoneConfirmed => 'Aucun envoi confirmé';

  @override
  String get headsUpContact => 'Demande de contact';

  @override
  String headsUpLocationBody(String time) {
    return 'Dernière mise à jour $time · ouvrez l\'application et vérifiez les paramètres de localisation.';
  }

  @override
  String get headsUpLocationBodyNever =>
      'Ouvrez l\'application et vérifiez les paramètres de localisation.';

  @override
  String get actionOpenLocationSettings =>
      'Ouvrir les paramètres de localisation';

  @override
  String get noticeCatAlerts => 'Alertes';

  @override
  String get noticeCatCash => 'Espèces et rapports';

  @override
  String get noticeCatCar => 'Voiture et garde';

  @override
  String get noticeCatMaintenance => 'Maintenance et retenues';

  @override
  String get noticeCatDocuments => 'Documents et fiche de paie';

  @override
  String updateAvailable(String version) {
    return 'Nouvelle version $version disponible';
  }

  @override
  String get updateNow => 'Mettre à jour';

  @override
  String get updateLater => 'Plus tard';

  @override
  String get updateRequiredTitle =>
      'Vous devez mettre à jour l\'application pour continuer';

  @override
  String get updateRequiredBody =>
      'Ce qui est enregistré sur le téléphone continue d\'être envoyé, et le suivi continue.';

  @override
  String updateQueued(String count) {
    return 'En attente d\'envoi : $count';
  }

  @override
  String updateSize(String size) {
    return 'Taille $size';
  }

  @override
  String get updateMobileData =>
      'Vous êtes sur les données mobiles : le téléchargement utilise votre forfait.';

  @override
  String updateDownloading(String percent) {
    return 'Téléchargement $percent';
  }

  @override
  String get updateInstall => 'Installer';

  @override
  String get updateInstallHint =>
      'Android vous demandera de confirmer l\'installation. Rouvrez l\'application après la mise à jour.';

  @override
  String get updatePermissionTitle =>
      'Autoriser l\'installation de la mise à jour';

  @override
  String get updatePermissionBody =>
      'Sur la page suivante, activez « Autoriser cette source » pour cette application, puis revenez.';

  @override
  String get updateOpenSettings => 'Ouvrir les paramètres';

  @override
  String get updateChecksum =>
      'Le fichier téléchargé était endommagé et a été supprimé. Réessayez.';

  @override
  String get updateFailed => 'Le téléchargement a échoué. Réessayez.';

  @override
  String get updateInstallFailed => 'Impossible d\'ouvrir l\'installateur.';

  @override
  String get checkUpdates => 'Rechercher des mises à jour';

  @override
  String get upToDate => 'Vous avez la dernière version';

  @override
  String get updateCheckFailed => 'Vérification impossible : pas de connexion';

  @override
  String get whatsNew => 'Nouveautés';

  @override
  String get noticesCurrent => 'En cours';

  @override
  String get noticesHistory => 'Historique';

  @override
  String get messagesChannel => 'Messages et suivis';

  @override
  String get noticeOpenLeave => 'Demander un congé';

  @override
  String get pettyTitle => 'Caisse de menues dépenses';

  @override
  String get qaPettySub => 'Dépenser avec la facture';

  @override
  String get pettyCashRow => 'Votre caisse de menues dépenses';

  @override
  String get pettyNone =>
      'Vous ne détenez aucune caisse de menues dépenses. Le bureau vous la remet depuis la caisse de l\'agence.';

  @override
  String get pettyBalance => 'Solde de la caisse';

  @override
  String pettyPendingPart(String pending, String available) {
    return 'dont $pending en attente de vérification · $available encore disponibles';
  }

  @override
  String get pettySpend => 'Dépenser de la caisse';

  @override
  String get pettyMine => 'Mouvements';

  @override
  String get pettyEmpty => 'Aucun mouvement sur la caisse pour l\'instant';

  @override
  String get pettyQueued => 'En attente d\'envoi';

  @override
  String get pettyPending => 'En attente de vérification';

  @override
  String get pettyApproved => 'Approuvée';

  @override
  String get pettyRejected => 'Refusée';

  @override
  String get pettyCancelled => 'Annulée';

  @override
  String pettyReason(String reason) {
    return 'Motif : $reason';
  }

  @override
  String get pettyCancel => 'Annuler la dépense';

  @override
  String pettyCancelQ(String amount) {
    return 'Annuler la dépense de $amount ? Le bureau ne l\'a pas encore vérifiée.';
  }

  @override
  String get pettyFunded => 'Remise par le bureau';

  @override
  String get pettyReturned => 'Rendue à la caisse';

  @override
  String get pettyOfficeExpense => 'Dépense saisie par le bureau';

  @override
  String get pettyCorrection => 'Correction';

  @override
  String pettyIntro(String available) {
    return 'Photographiez la facture et saisissez le montant et le type de dépense. Le bureau la vérifie et, une fois approuvée, elle est déduite de votre caisse. Encore disponible : $available KWD';
  }

  @override
  String get pettyInvoice => 'Photo de la facture';

  @override
  String get pettyTakeInvoice => 'Photographier la facture';

  @override
  String get pettyInvoiceMissing => 'La photo de la facture est obligatoire';

  @override
  String get pettyAmount => 'Montant';

  @override
  String get pettyAmountInvalid =>
      'Saisissez un montant valide (jusqu\'à 3 décimales)';

  @override
  String pettyAmountMax(String available) {
    return 'Plus que ce que vous pouvez encore dépenser ($available KWD)';
  }

  @override
  String get pettyCategory => 'Type de dépense';

  @override
  String get pettyCategoryMissing => 'Choisissez le type de dépense';

  @override
  String get pettyDate => 'Date de la facture';

  @override
  String get pettyVendor => 'Fournisseur ou magasin';

  @override
  String get pettyNote => 'Remarque';

  @override
  String get pettySend => 'Envoyer pour vérification';

  @override
  String get kind_petty => 'Dépense de caisse';

  @override
  String get kind_petty_cancel => 'Annulation d\'une dépense de caisse';

  @override
  String get companyTitle => 'Avec quelle société travaillez-vous ?';

  @override
  String get companyIntro =>
      'Choisissez la société pour laquelle vous livrez. Votre choix est envoyé au bureau pour approbation ; vous pouvez continuer à travailler en attendant.';

  @override
  String get companyNote => 'Note pour le bureau (facultatif)';

  @override
  String get companySend => 'Envoyer au bureau';

  @override
  String companyRejected(String platform, String reason) {
    return 'Le bureau a refusé votre choix ($platform) : $reason. Choisissez à nouveau.';
  }

  @override
  String companyPending(String platform) {
    return 'Votre demande pour travailler avec $platform attend le bureau';
  }

  @override
  String get companyChange => 'Changer mon choix';

  @override
  String get companyNone =>
      'Aucune société n\'est disponible pour le moment. Contactez le bureau.';

  @override
  String get endOrdersKept =>
      'Conservé et affiché dans le rapport du jour, où vous remplissez le reste';

  @override
  String get languageFirst =>
      'Choisissez la langue de l\'application. Vous pourrez la changer plus tard dans les réglages.';

  @override
  String get schemeKindPick => 'Choisissez d\'abord votre mode de paiement';

  @override
  String get schemeKind_per_order => 'À la commande';

  @override
  String get schemeKind_fixed_salary => 'Salaire fixe';

  @override
  String get schemeKind_batch => 'Batch';
}
