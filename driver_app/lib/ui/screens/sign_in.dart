import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../app/state.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Phone number, then the 6-digit code that arrives on WhatsApp. The activation link (no code) is handled by the
/// app as soon as it is opened.
class SignInScreen extends StatefulWidget {
  const SignInScreen({super.key, required this.state});

  final AppState state;

  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<SignInScreen> {
  final _phone = TextEditingController();
  final _code = TextEditingController();
  final _form = GlobalKey<FormState>();
  String? _sentTo;

  static String? e164(String v) {
    var s = v.replaceAll(RegExp(r'[\s-]'), '');
    if (s.startsWith('00')) s = '+${s.substring(2)}';
    if (RegExp(r'^\d{8}$').hasMatch(s)) s = '+965$s';
    return RegExp(r'^\+[1-9]\d{7,14}$').hasMatch(s) ? s : null;
  }

  Future<void> _send() async {
    if (!_form.currentState!.validate()) return;
    final phone = e164(_phone.text)!;
    try {
      await widget.state.requestCode(phone);
      setState(() => _sentTo = phone);
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  Future<void> _verify() async {
    if (!_form.currentState!.validate()) return;
    try {
      await widget.state.verifyCode(_sentTo!, _code.text.trim());
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    return Scaffold(
      body: SafeArea(
        child: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              const SizedBox(height: 32),
              Row(
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(color: AppColors.primary, borderRadius: BorderRadius.circular(14)),
                    child: const Icon(Icons.local_shipping_outlined, color: Colors.white),
                  ),
                  const SizedBox(width: 12),
                  Text(l.appTitle, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
                ],
              ),
              const SizedBox(height: 32),
              Text(
                _sentTo == null ? l.signInTitle : l.otpTitle,
                style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 8),
              Text(
                _sentTo == null ? l.signInHint : l.otpHint('\u2066$_sentTo\u2069'),
                style: const TextStyle(color: AppColors.muted, height: 1.6),
              ),
              const SizedBox(height: 24),
              if (_sentTo == null) ...[
                TextFormField(
                  key: const Key('phone'),
                  controller: _phone,
                  keyboardType: TextInputType.phone,
                  textDirection: TextDirection.ltr,
                  decoration: InputDecoration(
                    labelText: l.phoneLabel,
                    hintText: '9xxxxxxx',
                    prefixIcon: const Icon(Icons.phone_iphone),
                  ),
                  validator: (v) => e164(v ?? '') == null ? l.phoneInvalid : null,
                ),
                const SizedBox(height: 20),
                BusyButton(key: const Key('send-code'), label: l.sendCode, onPressed: _send),
                const SizedBox(height: 8),
                TextButton.icon(
                  key: const Key('civil-sign-in'),
                  icon: const Icon(Icons.badge_outlined),
                  label: Text(l.civilSignIn),
                  onPressed: () =>
                      Navigator.of(context)
                          .push(MaterialPageRoute(builder: (_) => CivilIdSignInScreen(state: widget.state))),
                ),
                const SizedBox(height: 12),
                Banner2(text: l.activationTip, icon: Icons.link),
              ] else ...[
                TextFormField(
                  key: const Key('code'),
                  controller: _code,
                  keyboardType: TextInputType.number,
                  textDirection: TextDirection.ltr,
                  textAlign: TextAlign.center,
                  maxLength: 6,
                  style: const TextStyle(fontSize: 26, letterSpacing: 10, fontWeight: FontWeight.w600),
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: InputDecoration(labelText: l.otpLabel, counterText: ''),
                  validator: (v) => (v ?? '').length == 6 ? null : l.otpLabel,
                ),
                const SizedBox(height: 20),
                BusyButton(key: const Key('verify'), label: l.verify, onPressed: _verify),
                TextButton(
                  onPressed: () => setState(() {
                    _sentTo = null;
                    _code.clear();
                  }),
                  child: Text(l.otpResend),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// For a driver the office has no phone for: his civil ID and the initial password the office gave him, then his phone
/// and the WhatsApp code sent to it. The self-registration (documents, IBAN) and its review follow.
class CivilIdSignInScreen extends StatefulWidget {
  const CivilIdSignInScreen({super.key, required this.state});

  final AppState state;

  @override
  State<CivilIdSignInScreen> createState() => _CivilIdSignInScreenState();
}

class _CivilIdSignInScreenState extends State<CivilIdSignInScreen> {
  final _civil = TextEditingController();
  final _password = TextEditingController();
  final _phone = TextEditingController();
  final _code = TextEditingController();
  final _form = GlobalKey<FormState>();
  String? _token;
  String _name = '';
  String? _sentTo;

  Future<void> _run(Future<void> Function() step) async {
    if (!_form.currentState!.validate()) return;
    try {
      await step();
      if (mounted) setState(() {});
    } catch (e) {
      if (mounted) showError(context, widget.state, e);
    }
  }

  Future<void> _start() => _run(() async {
    final r = await widget.state.claimStart(_civil.text.trim(), _password.text);
    _token = r.token;
    _name = (r.name[widget.state.lang] ?? r.name['ar'] ?? r.name.values.first) as String;
  });

  Future<void> _sendCode() =>
      _run(() async => _sentTo = await widget.state.claimPhone(_token!, _SignInScreenState.e164(_phone.text)!));

  Future<void> _verify() => _run(() async {
    await widget.state.claimVerify(_token!, _code.text.trim());
    if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
  });

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    return Scaffold(
      appBar: AppBar(title: Text(l.civilSignIn)),
      body: SafeArea(
        child: Form(
          key: _form,
          child: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              if (_token == null) ...[
                Text(l.civilSignInHint, style: const TextStyle(color: AppColors.muted, height: 1.6)),
                const SizedBox(height: 20),
                TextFormField(
                  key: const Key('claim-civil'),
                  controller: _civil,
                  keyboardType: TextInputType.number,
                  textDirection: TextDirection.ltr,
                  maxLength: 12,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: InputDecoration(labelText: l.civilId, prefixIcon: const Icon(Icons.badge_outlined)),
                  validator: (v) => RegExp(r'^\d{12}$').hasMatch(v ?? '') ? null : l.civilId,
                ),
                TextFormField(
                  key: const Key('claim-password'),
                  controller: _password,
                  obscureText: true,
                  textDirection: TextDirection.ltr,
                  decoration: InputDecoration(labelText: l.initialPassword, prefixIcon: const Icon(Icons.lock_outline)),
                  validator: (v) => (v ?? '').isEmpty ? l.required : null,
                ),
                const SizedBox(height: 20),
                BusyButton(key: const Key('claim-start'), label: l.claimContinue, onPressed: _start),
              ] else if (_sentTo == null) ...[
                Text(l.claimWelcome(_name), style: const TextStyle(height: 1.6)),
                const SizedBox(height: 20),
                TextFormField(
                  key: const Key('claim-phone'),
                  controller: _phone,
                  keyboardType: TextInputType.phone,
                  textDirection: TextDirection.ltr,
                  decoration: InputDecoration(
                    labelText: l.phoneLabel,
                    hintText: '9xxxxxxx',
                    prefixIcon: const Icon(Icons.phone_iphone),
                  ),
                  validator: (v) => _SignInScreenState.e164(v ?? '') == null ? l.phoneInvalid : null,
                ),
                const SizedBox(height: 20),
                BusyButton(key: const Key('claim-send'), label: l.sendCode, onPressed: _sendCode),
              ] else ...[
                Text(l.otpHint('\u2066$_sentTo\u2069'), style: const TextStyle(color: AppColors.muted, height: 1.6)),
                const SizedBox(height: 20),
                TextFormField(
                  key: const Key('claim-code'),
                  controller: _code,
                  keyboardType: TextInputType.number,
                  textDirection: TextDirection.ltr,
                  textAlign: TextAlign.center,
                  maxLength: 6,
                  style: const TextStyle(fontSize: 26, letterSpacing: 10, fontWeight: FontWeight.w600),
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: InputDecoration(labelText: l.otpLabel, counterText: ''),
                  validator: (v) => (v ?? '').length == 6 ? null : l.otpLabel,
                ),
                const SizedBox(height: 20),
                BusyButton(key: const Key('claim-verify'), label: l.verify, onPressed: _verify),
                TextButton(
                  onPressed: () => setState(() {
                    _sentTo = null;
                    _code.clear();
                  }),
                  child: Text(l.otpResend),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Shown while an activation link is being used.
class ActivatingScreen extends StatelessWidget {
  const ActivatingScreen({super.key, this.error, this.onBack});

  final String? error;
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    final l = context.l;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (error == null)
                  const CircularProgressIndicator()
                else
                  const Icon(Icons.link_off, size: 48, color: AppColors.danger),
                const SizedBox(height: 20),
                Text(
                  error == null ? l.activating : l.activationFailed,
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                ),
                if (error != null) ...[
                  const SizedBox(height: 10),
                  Text(
                    error!,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: AppColors.muted, height: 1.6),
                  ),
                  const SizedBox(height: 20),
                  OutlinedButton(onPressed: onBack, child: Text(l.back)),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
