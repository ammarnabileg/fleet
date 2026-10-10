/* =====================================================================
   app/pages/integrations.js — الخدمات الخارجية من لوحة التحكم: تخزين الملفات
   (الخادم أو Cloudflare R2) وواتساب (Evolution API). المفاتيح السرية تُكتب فقط:
   لا تعود من الخادم أبداً، ويظهر آخر 4 أحرف منها للتمييز. التشغيل يُجرَّب أولاً،
   وإن فشلت التجربة لا يُحفظ شيء.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  var SECRET_LABEL = { secret_access_key: 'Secret Access Key', api_key: 'API Key', service_account: 'مفتاح حساب الخدمة (JSON)' };
  var MODE = { log: 'سجل التطوير (لا يُرسل شيء)', whatsapp: 'إعداد الخادم (متغيرات البيئة)', panel: 'لا شيء: يجب تشغيله من هنا' };

  function checkLine(c) {
    if (!c.checked_at) return h`<span class="muted fs-sm">لم تُجرَّب بعد</span>`;
    return c.check_ok
      ? h`${BT.pill('الاتصال يعمل', 'g', true)} <span class="muted fs-sm">آخر تجربة ${fmt.dt(c.checked_at)}</span>`
      : h`${BT.pill('الاتصال فشل', 'r', true)} <span class="muted fs-sm">${fmt.dt(c.checked_at)}: <span class="ltr">${c.check_error}</span></span>`;
  }
  function secretField(c, name) {
    var s = c.secrets[name];
    return h`<div class="field"><label for="f-${name}">${SECRET_LABEL[name]}</label><input class="input ltr" type="password" name="${name}" id="f-${name}" autocomplete="new-password" placeholder="${s.set ? 'محفوظ ' + s.hint + ' — اتركه فارغاً للإبقاء عليه' : 'غير محفوظ'}"><div class="hint">${s.set ? h`يُخزَّن مشفّراً ولا يظهر مرة أخرى. <button type="button" class="btn btn-sm btn-ghost" data-clear="${name}">إزالة المفتاح المحفوظ</button>` : 'يُخزَّن مشفّراً ولا يظهر مرة أخرى'}</div><div class="err-msg"></div></div>`;
  }

  function storageCard(c) {
    var cfg = c.config, files = c.status.files || { local: 0, r2: 0 };
    return h`<form class="card" data-kind="storage" novalidate>
      <div class="card-h"><div class="card-t">${icon('inbox', 16)} تخزين الملفات</div><span class="ms-auto">${checkLine(c)}</span></div>
      <div class="card-b">
        <div class="highlight-box mb-12 between"><span>ملفات على الخادم <b class="num">${fmt.int(files.local)}</b></span><span>ملفات على R2 <b class="num">${fmt.int(files.r2)}</b></span></div>
        <div class="form">
          ${BT.f.radios({ name: 'provider', label: 'أين تُحفظ الملفات الجديدة', value: cfg.provider, options: [
            { v: 'local', t: 'خادم النظام', d: 'على قرص الخادم نفسه' },
            { v: 'r2', t: 'Cloudflare R2', d: 'حاوية خاصة؛ الملفات تمر عبر النظام فلا تُفتح إلا بصلاحية' }] })}
          <div class="form-grid" data-r2>
            ${BT.f.input({ name: 'account_id', label: 'Account ID', value: cfg.account_id || '', pattern: '[0-9a-f]{32}', msg: '32 حرفاً من 0-9 و a-f', hint: 'من لوحة Cloudflare: R2 ← Account details' })}
            ${BT.f.input({ name: 'bucket', label: 'اسم الحاوية (Bucket)', value: cfg.bucket || '', pattern: '[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', msg: 'حروف إنجليزية صغيرة وأرقام وشرطة' })}
            ${BT.f.input({ name: 'access_key_id', label: 'Access Key ID', value: cfg.access_key_id || '', pattern: '[A-Za-z0-9]{16,128}', msg: 'حروف وأرقام إنجليزية' })}
            ${secretField(c, 'secret_access_key')}
            ${BT.f.select({ name: 'jurisdiction', label: 'نطاق الحاوية (Jurisdiction)', value: cfg.jurisdiction, placeholder: false, options: [{ v: 'default', t: 'افتراضي' }, { v: 'eu', t: 'الاتحاد الأوروبي (EU)' }, { v: 'fedramp', t: 'FedRAMP' }] })}
          </div>
          <div class="banner info fs-sm">${icon('info', 16)}<div>أنشئ مفتاح R2 API Token بصلاحية <b>Object Read &amp; Write</b> على هذه الحاوية فقط، واترك الحاوية <b>خاصة</b> (بلا رابط عام). عند التشغيل تُكتب الملفات الجديدة في R2، وتُنسخ الملفات السابقة إليها في الخلفية (تبقى نسختها على الخادم حتى يحذفها المشغّل).${files.r2 ? h` <b>في الحاوية ${fmt.int(files.r2)} ملفاً:</b> يمكن استبدال المفتاح بمفتاح جديد للحاوية نفسها، ولا يمكن تغيير الحاوية.` : ''}</div></div>
          <div class="row gap-8"><button type="submit" class="btn btn-sm btn-primary">${icon('check', 14)} حفظ</button><button type="button" class="btn btn-sm btn-secondary" data-check>${icon('refresh-cw', 14)} اختبار الاتصال</button></div>
        </div>
      </div></form>`;
  }

  function whatsappCard(c) {
    var cfg = c.config;
    return h`<form class="card" data-kind="whatsapp" novalidate>
      <div class="card-h"><div class="card-t">${icon('message-square', 16)} واتساب (Evolution API)</div><span class="ms-auto">${checkLine(c)}</span></div>
      <div class="card-b"><div class="form">
        ${BT.f.switch({ name: 'enabled', label: 'إرسال رموز الدخول وروابط التفعيل من هذا الحساب', checked: cfg.enabled })}
        <div class="form-grid">
          ${BT.f.input({ name: 'url', label: 'عنوان Evolution API', value: cfg.url || '', placeholder: 'https://evolution.example.com', pattern: 'https?://[^\\s/?#]+(/[^\\s?#]*)?', msg: 'عنوان يبدأ بـ https://' })}
          ${BT.f.input({ name: 'instance', label: 'اسم الـ Instance', value: cfg.instance || '', pattern: '[A-Za-z0-9_.\\-]{1,100}', msg: 'حروف وأرقام إنجليزية' })}
          ${secretField(c, 'api_key')}
        </div>
        <div class="muted fs-sm">عند الإيقاف يُستخدم: ${MODE[c.status.server_mode] || c.status.server_mode}</div>
        <div class="row gap-8"><button type="submit" class="btn btn-sm btn-primary">${icon('check', 14)} حفظ</button><button type="button" class="btn btn-sm btn-secondary" data-check>${icon('refresh-cw', 14)} اختبار الاتصال</button></div>
      </div></div></form>`;
  }

  function pushCard(c) {
    var cfg = c.config, s = c.secrets.service_account;
    return h`<form class="card" data-kind="push" novalidate>
      <div class="card-h"><div class="card-t">${icon('bell-ring', 16)} الإشعارات الفورية (Firebase)</div><span class="ms-auto">${checkLine(c)}</span></div>
      <div class="card-b"><div class="form">
        ${BT.f.switch({ name: 'enabled', label: 'إرسال إشعارات السائقين إلى هواتفهم', checked: cfg.enabled })}
        <div class="form-grid">
          ${BT.f.input({ name: 'app_id', label: 'App ID (أندرويد)', value: cfg.app_id || '', placeholder: '1:123456789:android:abc…', pattern: '1:[0-9]{6,20}:android:[0-9a-f]{8,40}', msg: 'كما في إعدادات المشروع: 1:رقم:android:…' })}
          ${BT.f.input({ name: 'sender_id', label: 'Sender ID', value: cfg.sender_id || '', pattern: '[0-9]{6,20}', msg: 'أرقام فقط' })}
          ${BT.f.input({ name: 'client_api_key', label: 'Web/Android API Key', value: cfg.api_key || '', pattern: '[A-Za-z0-9_\\-]{20,60}', msg: 'كما في إعدادات المشروع' })}
        </div>
        <div class="field"><label for="f-service_account">${SECRET_LABEL.service_account}</label><textarea class="textarea ltr" rows="4" name="service_account" id="f-service_account" placeholder="${s.set ? 'محفوظ ' + s.hint + ' — اتركه فارغاً للإبقاء عليه' : 'الصق محتوى ملف JSON كاملاً'}"></textarea><div class="hint">${s.set ? h`يُخزَّن مشفّراً ولا يظهر مرة أخرى. <button type="button" class="btn btn-sm btn-ghost" data-clear="service_account">إزالة المفتاح المحفوظ</button>` : 'يُخزَّن مشفّراً ولا يظهر مرة أخرى'}</div><div class="err-msg"></div></div>
        <div class="banner info fs-sm">${icon('info', 16)}<div>من Firebase: إعدادات المشروع ← تطبيقاتك (App ID و Sender ID و API Key لتطبيق أندرويد)، ثم حسابات الخدمة ← إنشاء مفتاح خاص (ملف JSON). التطبيق يأخذ هذه القيم من الخادم فلا يحتاج إصداراً جديداً. هواتف مسجلة الآن: <b class="num">${fmt.int(c.status.phones || 0)}</b>. الإشعارات تبقى في قائمة التطبيق دائماً؛ الدفع للهاتف إضافة.</div></div>
        <div class="row gap-8"><button type="submit" class="btn btn-sm btn-primary">${icon('check', 14)} حفظ</button><button type="button" class="btn btn-sm btn-secondary" data-check>${icon('refresh-cw', 14)} اختبار الاتصال</button></div>
      </div></div></form>`;
  }

  function configOf(kind, vals, cur) {
    if (kind === 'storage') {
      return { provider: vals.provider || cur.provider, account_id: vals.account_id || null, bucket: vals.bucket || null, access_key_id: vals.access_key_id || null, jurisdiction: vals.jurisdiction || 'default' };
    }
    if (kind === 'push') return { enabled: !!vals.enabled, app_id: vals.app_id || null, sender_id: vals.sender_id || null, api_key: vals.client_api_key || null };
    return { enabled: !!vals.enabled, url: vals.url || null, instance: vals.instance || null };
  }

  BT.pages['integrations'] = function () {
    A.setTitle('التكاملات');
    var v = A.view();
    BT.render(v, h`${A.head('التكاملات', 'الخدمات الخارجية التي يتصل بها النظام. كل تغيير يُسجَّل في سجل التدقيق، والمفاتيح لا تُعرض بعد حفظها.', '')}<div data-list></div>`);
    var el = v.querySelector('[data-list]');
    function draw() {
      A.load(el, api.get('/integrations/connections'), function (rows) {
        var by = {};
        rows.forEach(function (c) { by[c.kind] = c; });
        setTimeout(function () { wire(by); });
        return h`<div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(420px,1fr))">${by.storage ? storageCard(by.storage) : ''}${by.whatsapp ? whatsappCard(by.whatsapp) : ''}${by.push ? pushCard(by.push) : ''}</div>`;
      }).catch(function () {});
    }
    function save(kind, cur, body, button) {
      button.classList.add('is-loading');
      return api.put('/integrations/connections/' + kind, Object.assign({ version: cur.version }, body)).then(function (r) {
        button.classList.remove('is-loading');
        BT.toast('تم الحفظ', { sub: r.check_ok ? 'جُرِّب الاتصال ونجح' : undefined });
        draw();
      }, function (err) { button.classList.remove('is-loading'); BT.toast(api.message(err), { type: 'error', timeout: 9000 }); });
    }
    function wire(by) {
      BT.$$('form[data-kind]', el).forEach(function (form) {
        var kind = form.getAttribute('data-kind'), cur = by[kind];
        var r2box = form.querySelector('[data-r2]');
        BT.$$('[name=account_id],[name=bucket],[name=access_key_id],[name=url],[name=instance],[name=app_id],[name=sender_id],[name=client_api_key]', form).forEach(function (i) { i.dir = 'ltr'; });
        function toggle() { if (r2box) r2box.style.display = (BT.form.values(form).provider === 'r2' || cur.config.account_id) ? '' : 'none'; }
        form.addEventListener('change', toggle); toggle();
        form.addEventListener('submit', function (e) {
          e.preventDefault();
          if (!BT.form.validate(form)) return;
          var vals = BT.form.values(form), secrets = {};
          Object.keys(cur.secrets).forEach(function (n) { if (vals[n]) secrets[n] = vals[n]; });
          save(kind, cur, { config: configOf(kind, vals, cur.config), secrets: secrets }, form.querySelector('[type=submit]'));
        });
        form.querySelector('[data-check]').onclick = function (e) {
          var b = e.currentTarget; b.classList.add('is-loading');
          api.post('/integrations/connections/' + kind + '/check').then(function (r) {
            b.classList.remove('is-loading');
            BT.toast(r.check_ok ? 'الاتصال يعمل' : 'الاتصال فشل', { type: r.check_ok ? undefined : 'error', sub: r.check_error || undefined, timeout: 8000 });
            draw();
          }, function (err) { b.classList.remove('is-loading'); BT.toast(api.message(err), { type: 'error', timeout: 8000 }); });
        };
        BT.$$('[data-clear]', form).forEach(function (b) {
          b.onclick = function () {
            var name = b.getAttribute('data-clear'), secrets = {};
            secrets[name] = null;
            A.confirmRun({ title: 'إزالة المفتاح المحفوظ؟', message: 'تتوقف الخدمة عن العمل حتى يُدخَل مفتاح جديد.', confirm: 'إزالة', danger: true,
              run: function () { return api.put('/integrations/connections/' + kind, { version: cur.version, config: cur.config, secrets: secrets }); },
              done: 'أُزيل المفتاح', after: draw });
          };
        });
      });
    }
    draw();
  };
})();
