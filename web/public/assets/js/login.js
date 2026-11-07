/* =====================================================================
   BrilliantTech — login.js  (تسجيل الدخول)
   اسم المستخدم وكلمة المرور ← رمز التحقق بخطوتين من تطبيق المصادقة (إن كان مفعّلاً)
   ← لوحة الإدارة. الجلسة كوكي HttpOnly يضعها الخادم؛ الصفحة لا تحفظ أي رمز.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, api = BT.api;
  var s1 = document.getElementById('step1'), s2 = document.getElementById('step2');
  var next = new URLSearchParams(location.search).get('next') || '';
  var target = 'admin.html' + (/^#\/[\w\-/?=&%.]*$/.test(next) ? next : '');
  /* إلى لوحة الإدارة، أو إلى بوابة المراكز لحساب مركز صيانة */
  function enter(me) { location.replace(api.isCenterAccount(me) ? 'center.html' : target); }
  function go() { api.get('/auth/me', null, { noRedirect: true }).then(enter, function () { location.replace(target); }); }

  BT.hydrate(document);
  BT.render(document.getElementById('otp-box'), BT.otp.html(6));
  BT.form.live(s1);

  // الجلسة صالحة؟ إلى اللوحة مباشرة
  api.get('/auth/me', null, { noRedirect: true }).then(enter, function () { /* سجّل الدخول */ });
  api.get('/branding', null, { noRedirect: true }).then(function (b) {
    document.getElementById('client-name').textContent = b.display_name;
    document.title = 'تسجيل الدخول — ' + b.display_name;
  }, function () { /* الاسم الافتراضي */ });
  api.loadCatalog('ar').catch(function () { /* الرسائل الافتراضية */ });

  function showError(id, msg) { var el = document.getElementById(id); el.textContent = msg; el.style.display = msg ? 'block' : 'none'; }

  document.getElementById('show-pw').onclick = function () { var p = document.getElementById('p'); p.type = p.type === 'password' ? 'text' : 'password'; };

  s1.addEventListener('submit', function (e) {
    e.preventDefault();
    showError('login-err', '');
    if (!BT.form.validate(s1)) return;
    var b = s1.querySelector('[type=submit]'); b.classList.add('is-loading'); b.disabled = true;
    var v = BT.form.values(s1);
    api.request('POST', '/auth/login', { body: { username: v.user.trim(), password: v.pw }, noRedirect: true }).then(function (r) {
      b.classList.remove('is-loading'); b.disabled = false;
      if (r.mfa_required) {
        s1.classList.add('hidden'); s2.classList.remove('hidden');
        s2.querySelector('.otp input').focus();
        return;
      }
      go();
    }, function (err) {
      b.classList.remove('is-loading'); b.disabled = false;
      showError('login-err', api.message(err));
      document.getElementById('p').select();
    });
  });

  document.getElementById('back1').onclick = function () { s2.classList.add('hidden'); s1.classList.remove('hidden'); showError('otp-err', ''); };

  var verifying = false;
  function verify() {
    var box = s2.querySelector('.otp'), code = BT.otp.value(box);
    if (code.length < 6) { box.classList.add('invalid'); showError('otp-err', 'أدخل الرمز من 6 أرقام'); return; }
    if (verifying) return;
    verifying = true;
    var b = s2.querySelector('[type=submit]'); b.classList.add('is-loading');
    api.request('POST', '/auth/mfa/verify', { body: { code: code }, noRedirect: true }).then(function () {
      go();
    }, function (err) {
      verifying = false; b.classList.remove('is-loading');
      box.classList.add('invalid');
      BT.$$('input', box).forEach(function (i) { i.value = ''; });
      box.querySelector('input').focus();
      // انتهت مهلة الخطوة الثانية: من البداية
      if (err.status === 401) { s2.classList.add('hidden'); s1.classList.remove('hidden'); showError('login-err', api.message(err)); return; }
      showError('otp-err', api.message(err));
    });
  }
  s2.addEventListener('submit', function (e) { e.preventDefault(); verify(); });
  s2.addEventListener('otp:complete', verify);

  /* FR-USR-03: a code on WhatsApp to the phone saved on the account, then a new password (and the authenticator's
     code when two-step verification is on). The page says the same for any username. */
  document.getElementById('forgot').onclick = function () {
    var h = BT.h, user = document.getElementById('u').value.trim();
    var dlg = BT.modal.open({
      title: 'نسيت كلمة المرور؟', icon: 'key-round', size: 'sm',
      body: h`<form class="form" data-reset-ask novalidate><p class="fs-sm">اكتب اسم المستخدم. إن كان للحساب رقم جوال مسجل يصله رمز على واتساب صالح 10 دقائق.</p>
        ${BT.f.input({ name: 'username', label: 'اسم المستخدم', required: true, value: user })}</form>
        <form class="form hidden" data-reset-set novalidate><p class="fs-sm" data-reset-sent></p>
        ${BT.f.input({ name: 'code', label: 'الرمز من واتساب', required: true })}
        ${BT.f.input({ name: 'new_password', label: 'كلمة المرور الجديدة', required: true, type: 'password' })}
        ${BT.f.input({ name: 'mfa_code', label: 'رمز تطبيق المصادقة', optional: true, hint: 'فقط إن كان التحقق بخطوتين مفعلاً لحسابك' })}</form>
        <div class="err-msg center" data-reset-err role="alert"></div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-secondary' }, { label: 'أرسل الرمز', cls: 'btn-primary', close: false, onClick: function () { step(); return false; } }]
    });
    var ask = dlg.body.querySelector('[data-reset-ask]'), set = dlg.body.querySelector('[data-reset-set]'), sent = false;
    function err(msg) { var e = dlg.body.querySelector('[data-reset-err]'); e.textContent = msg || ''; e.style.display = msg ? 'block' : 'none'; }
    function step() {
      err('');
      var form = sent ? set : ask;
      if (!BT.form.validate(form)) return;
      var a = BT.form.values(ask), v = BT.form.values(set), digits = function (x) { return String(x == null ? '' : x).replace(/\s/g, ''); };
      dlg.busy(1, true);
      var call = sent
        ? api.request('POST', '/auth/password-reset/confirm', { body: { username: a.username.trim(), code: digits(v.code), new_password: v.new_password, mfa_code: digits(v.mfa_code) || null }, noRedirect: true })
        : api.request('POST', '/auth/password-reset', { body: { username: a.username.trim() }, noRedirect: true });
      call.then(function () {
        dlg.busy(1, false);
        if (!sent) {
          sent = true;
          ask.classList.add('hidden'); set.classList.remove('hidden');
          set.querySelector('[data-reset-sent]').textContent = 'إن كان «' + a.username.trim() + '» حساباً له جوال مسجل فقد أُرسل الرمز إليه. لم يصل؟ اطلب من مدير النظام إعادة تعيين كلمة المرور.';
          dlg.btn(1).textContent = 'تغيير كلمة المرور';
          set.querySelector('[name=code]').focus();
          return;
        }
        dlg.close();
        document.getElementById('u').value = a.username.trim();
        document.getElementById('p').value = '';
        document.getElementById('p').focus();
        BT.toast('تم تغيير كلمة المرور. سجّل الدخول بها الآن');
      }, function (e) { dlg.busy(1, false); err(api.message(e)); });
    }
  };
})();
