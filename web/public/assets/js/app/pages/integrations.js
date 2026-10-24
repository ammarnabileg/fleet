/* =====================================================================
   app/pages/integrations.js — الخدمات الخارجية من لوحة التحكم: تخزين الملفات
   (الخادم أو Cloudflare R2) وواتساب (Evolution API) وإشعارات Firebase. المفاتيح السرية تُكتب فقط:
   لا تعود من الخادم أبداً، ويظهر آخر 4 أحرف منها للتمييز. التشغيل يُجرَّب أولاً،
   وإن فشلت التجربة لا يُحفظ شيء. لكل قناة رسائل: حالتها (غير مهيأ/متوقف/يعمل/فشل)، وآخر اختبار اتصال،
   ومنفصلاً عنه آخر الرسائل كما رد عليها المزود (قُبلت أو فشلت وسببها) دون نصها.
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
  /* جاهزية القناة (واتساب، Firebase): الحالة، ثم آخر اختبار اتصال منفصلاً عن الرسائل نفسها */
  var STATE = {
    not_configured: { t: 'غير مهيأ', tone: 'n', d: 'الإعدادات أو المفتاح ناقصة' },
    disabled: { t: 'متوقف', tone: 'n', d: 'الإعدادات كاملة لكن الخدمة غير مفعّلة: لا يُرسل منها شيء' },
    untested: { t: 'مفعّل، لم يُختبر', tone: 'o', d: 'مفعّل ولم يُجرَّب الاتصال بعد' },
    working: { t: 'يعمل', tone: 'g', d: 'مفعّل وآخر اختبار اتصال نجح' },
    failed: { t: 'فشل', tone: 'r', d: 'مفعّل وآخر اختبار اتصال فشل: الرسائل لا تخرج على الأرجح' }
  };
  var PURPOSE = { otp: 'رمز دخول السائق', activation: 'رابط تفعيل', password_reset: 'استعادة كلمة المرور', claim_otp: 'رمز تحقق التسجيل', scheme_decision: 'قرار نظام الرواتب', registration_decision: 'قرار التسجيل', notice: 'إشعار للسائق' };
  var PROVIDER = { evolution: 'Evolution API', fcm: 'Firebase', log: 'سجل التطوير (لم يُرسل فعلياً)', none: 'غير مهيأ (لم يُرسل)' };
  function stateLine(c) {
    var st = STATE[c.state] || { t: c.state, tone: 'n', d: '' };
    return h`<span data-state="${c.state}" title="${st.d}">${BT.pill(st.t, st.tone, true)}</span>`;
  }
  function testLine(c) {
    var what = c.checked_at
      ? (c.check_ok ? h`${BT.pill('نجح', 'g')} <span class="muted fs-sm">${fmt.dt(c.checked_at)} · ${fmt.since(c.checked_at)}</span>` : h`${BT.pill('فشل', 'r')} <span class="muted fs-sm">${fmt.dt(c.checked_at)} · ${fmt.since(c.checked_at)}</span><div class="fs-sm t-danger ltr mt-4">${c.check_error}</div>`)
      : h`<span class="muted fs-sm">لم يُجرَّب بعد</span>`;
    return h`<div class="highlight-box mb-12" data-test-line><div class="fs-sm"><b>آخر اختبار اتصال:</b> ${what}</div><div class="hint mt-4">الاختبار يتأكد أن الخدمة ترد بهذه الإعدادات${c.kind === 'whatsapp' ? ' وأن جلسة واتساب متصلة (يتكرر تلقائياً كل 5 دقائق أثناء التفعيل)' : ''}. لا يرسل رسالة لأحد، ولا يثبت وصول الرسائل: ذلك في «آخر الرسائل» أدناه.</div></div>`;
  }
  function messagesBlock(c) {
    var m = c.status.messages;
    if (!m) return '';
    var push = c.kind === 'push';
    var note = push
      ? 'قبول Firebase للإشعار لا يعني ظهوره على الهاتف؛ «فُتح في التطبيق» هو الدليل على وصوله. ما لم يُرسل يُعاد تلقائياً كل 30 ثانية لمدة 48 ساعة.'
      : 'قبول Evolution للرسالة يعني أنها أُرسلت للإرسال، لا أنها وصلت: إيصالات الوصول والقراءة من واتساب لا تصل للنظام. لا إعادة تلقائية لرموز الدخول (يطلبها السائق مجدداً)، وروابط التفعيل الجماعية تُعاد حتى 3 مرات.';
    return h`<div data-messages><div class="between mb-8"><b class="fs-sm">آخر الرسائل</b><span class="fs-sm muted">آخر ${m.days} أيام: قبلها المزود <b class="num" data-accepted>${fmt.int(m.accepted)}</b> · فشلت <b class="num${m.failed ? ' t-danger' : ''}" data-failed>${fmt.int(m.failed)}</b></span></div>
      ${m.last_failed_at ? h`<div class="banner warn fs-sm mb-8">${icon('triangle-alert', 16)}<div>آخر فشل ${fmt.dt(m.last_failed_at)}: <span class="ltr">${m.error_label || m.last_error}</span></div></div>` : ''}
      ${m.recent.length ? h`<div class="table-wrap"><table class="t compact" data-messages-table><thead><tr><th>الوقت</th><th>الغرض</th><th>إلى</th><th>النتيجة</th>${push ? h`<th>في التطبيق</th>` : ''}</tr></thead><tbody>${m.recent.map(function (x) {
        return h`<tr><td>${fmt.dt(x.at)}</td><td>${PURPOSE[x.purpose] || x.purpose || '—'}</td><td><bdi dir="ltr">${x.recipient || '—'}</bdi></td><td>${x.status === 'accepted' ? BT.pill(x.provider === 'log' || x.provider === 'none' ? PROVIDER[x.provider] : 'قبلها ' + (PROVIDER[x.provider] || x.provider), x.provider === 'log' || x.provider === 'none' ? 'n' : 'g') : h`${BT.pill('فشل', 'r')} <span class="fs-sm muted ltr">${x.error === 'not_on_whatsapp' ? 'الرقم ليس على واتساب' : x.error}</span>`}${x.attempt > 1 ? h` <span class="fs-sm muted">محاولة ${x.attempt}</span>` : ''}</td>${push ? h`<td>${x.read ? BT.pill('فُتح', 'g') : h`<span class="muted fs-sm">لم يُفتح بعد</span>`}</td>` : ''}</tr>`;
      })}</tbody></table></div>` : h`<div class="muted fs-sm">لم تُرسل رسائل من هذه القناة بعد.</div>`}
      <div class="hint mt-8">${note}</div></div>`;
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
      <div class="card-h"><div class="card-t">${icon('message-square', 16)} واتساب (Evolution API)</div><span class="ms-auto">${stateLine(c)}</span></div>
      <div class="card-b">${testLine(c)}<div class="form">
        ${BT.f.switch({ name: 'enabled', label: 'إرسال رموز الدخول وروابط التفعيل من هذا الحساب', checked: cfg.enabled })}
        <div class="form-grid">
          ${BT.f.input({ name: 'url', label: 'عنوان Evolution API', value: cfg.url || '', placeholder: 'https://evolution.example.com', pattern: 'https?://[^\\s/?#]+(/[^\\s?#]*)?', msg: 'عنوان يبدأ بـ https://' })}
          ${BT.f.input({ name: 'instance', label: 'اسم الـ Instance', value: cfg.instance || '', pattern: '[A-Za-z0-9_.\\-]{1,100}', msg: 'حروف وأرقام إنجليزية' })}
          ${secretField(c, 'api_key')}
        </div>
        <div class="muted fs-sm">عند الإيقاف يُستخدم: ${MODE[c.status.server_mode] || c.status.server_mode}</div>
        <div class="row gap-8"><button type="submit" class="btn btn-sm btn-primary">${icon('check', 14)} حفظ</button><button type="button" class="btn btn-sm btn-secondary" data-check>${icon('refresh-cw', 14)} اختبار الاتصال</button></div>
        ${messagesBlock(c)}
      </div></div></form>`;
  }

  function pushCard(c) {
    var cfg = c.config, s = c.secrets.service_account;
    return h`<form class="card" data-kind="push" novalidate>
      <div class="card-h"><div class="card-t">${icon('bell-ring', 16)} الإشعارات الفورية (Firebase)</div><span class="ms-auto">${stateLine(c)}</span></div>
      <div class="card-b">${testLine(c)}${devicesBox(c)}<div class="form">
        ${BT.f.switch({ name: 'enabled', label: 'إرسال إشعارات السائقين إلى هواتفهم', checked: cfg.enabled })}
        <div class="form-grid">
          ${BT.f.input({ name: 'app_id', label: 'App ID (أندرويد)', value: cfg.app_id || '', placeholder: '1:123456789:android:abc…', pattern: '1:[0-9]{6,20}:android:[0-9a-f]{8,40}', msg: 'كما في إعدادات المشروع: 1:رقم:android:…' })}
          ${BT.f.input({ name: 'sender_id', label: 'Sender ID', value: cfg.sender_id || '', pattern: '[0-9]{6,20}', msg: 'أرقام فقط' })}
          ${BT.f.input({ name: 'client_api_key', label: 'Web/Android API Key', value: cfg.api_key || '', pattern: '[A-Za-z0-9_\\-]{20,60}', msg: 'كما في إعدادات المشروع' })}
        </div>
        <div class="field"><label for="f-service_account">${SECRET_LABEL.service_account}</label><textarea class="textarea ltr" rows="4" name="service_account" id="f-service_account" placeholder="${s.set ? 'محفوظ ' + s.hint + ' — اتركه فارغاً للإبقاء عليه' : 'الصق محتوى ملف JSON كاملاً'}"></textarea><div class="hint">${s.set ? h`يُخزَّن مشفّراً ولا يظهر مرة أخرى. <button type="button" class="btn btn-sm btn-ghost" data-clear="service_account">إزالة المفتاح المحفوظ</button>` : 'يُخزَّن مشفّراً ولا يظهر مرة أخرى'}</div><div class="err-msg"></div></div>
        <div class="banner info fs-sm">${icon('info', 16)}<div>من Firebase: إعدادات المشروع ← تطبيقاتك (App ID و Sender ID و API Key لتطبيق أندرويد)، ثم حسابات الخدمة ← إنشاء مفتاح خاص (ملف JSON). التطبيق يأخذ هذه القيم من الخادم فلا يحتاج إصداراً جديداً. الإشعارات تبقى في قائمة التطبيق دائماً؛ الدفع للهاتف إضافة.</div></div>
        <div class="row gap-8"><button type="submit" class="btn btn-sm btn-primary">${icon('check', 14)} حفظ</button><button type="button" class="btn btn-sm btn-secondary" data-check>${icon('refresh-cw', 14)} اختبار الاتصال</button></div>
        ${messagesBlock(c)}
      </div></div></form>`;
  }

  /* هواتف السائقين المسجلة للإشعارات، والإشعارات المنتظرة */
  function devicesBox(c) {
    var st = c.status, n = st.notices || {};
    var why = !st.phones
      ? (c.state === 'working' || c.state === 'untested' ? 'لم يسجل أي هاتف بعد: يسجل التطبيق هاتفه عند فتحه التالي بعد التفعيل' : 'صفر لأن Firebase غير مفعّلة: التطبيق لا يسجل هاتفه للإشعارات إلا بعد التفعيل هنا')
      : '';
    return h`<div class="highlight-box mb-12" data-push-devices><div class="between fs-sm"><span>هواتف مسجلة للإشعارات <b class="num" data-phones>${fmt.int(st.phones || 0)}</b> من <b class="num">${fmt.int(st.active_phones || 0)}</b> هاتف سائق مفعّل</span><span title="إشعارات آخر ${n.window_hours || 48} ساعة لم تصل لهاتف بعد: تُرسل تلقائياً عند تسجيل الهاتف أو تفعيل الخدمة">لم تُرسل لهاتف بعد <b class="num" data-waiting>${fmt.int(n.waiting || 0)}</b></span></div>${why ? h`<div class="hint mt-4">${why}</div>` : ''}${n.pushed_7d ? h`<div class="hint mt-4">آخر 7 أيام: أُرسل <b class="num">${fmt.int(n.pushed_7d)}</b> إشعاراً، فتح السائقون منها <b class="num">${fmt.int(n.read_7d)}</b> في التطبيق</div>` : ''}</div>`;
  }

  function configOf(kind, vals, cur) {
    if (kind === 'storage') {
      return { provider: vals.provider || cur.provider, account_id: vals.account_id || null, bucket: vals.bucket || null, access_key_id: vals.access_key_id || null, jurisdiction: vals.jurisdiction || 'default' };
    }
    if (kind === 'push') return { enabled: !!vals.enabled, app_id: vals.app_id || null, sender_id: vals.sender_id || null, api_key: vals.client_api_key || null };
    return { enabled: !!vals.enabled, url: vals.url || null, instance: vals.instance || null };
  }


  /* ================= نقل الإعدادات (JSON): من سيرفر التجربة إلى الإنتاج =================
     التصدير: الأقسام المختارة كملف JSON بمفاتيح طبيعية (الرموز والأسماء) لا بمعرّفات قاعدة البيانات، بلا أي سر؛
     «تضمين الأسرار» (لمن يملك كل الصلاحيات) يشفّرها بعبارة مرور يكتبها المستخدم ولا تُحفظ في أي مكان.
     الاستيراد (لمن يملك كل الصلاحيات): معاينة أولاً (لا يُحفظ شيء)، ثم الاستيراد في معاملة واحدة: يُنشئ الناقص ويحدّث
     الموجود، ولا يحذف شيئاً ليس في الملف. */
  function skippedList(s) {
    var notes = s.skipped.map(function (x) { return { t: 'r', x: x }; }).concat(s.warnings.map(function (x) { return { t: 'o', x: x }; }));
    if (!notes.length) return '';
    return h`<ul class="fs-sm mt-4" data-notes>${notes.slice(0, 12).map(function (n) {
      return h`<li class="${n.t === 'r' ? 't-danger' : 'muted'}"><bdi>${n.x.item}</bdi>: ${api.t('errors', n.x.code, n.x.params, n.x.code)}</li>`;
    })}${notes.length > 12 ? h`<li class="muted">و ${notes.length - 12} أخرى…</li>` : ''}</ul>`;
  }
  function reportTable(r, done) {
    var verb = done ? ['أُنشئ', 'حُدِّث'] : ['سيُنشأ', 'سيُحدَّث'];
    return h`<div data-report="${done ? 'done' : 'preview'}">
      <div class="fs-sm muted mb-8">الملف من <bdi dir="ltr">${r.source || '—'}</bdi> · صُدِّر ${r.exported_at ? fmt.dt(r.exported_at) : '—'} · إصدار النظام <bdi dir="ltr">${r.app_version || '—'}</bdi> · صيغة ${r.format_version}</div>
      ${r.secrets === 'skipped' ? h`<div class="banner warn fs-sm mb-8">${icon('triangle-alert', 16)}<div>في الملف أسرار مشفّرة ولم تُكتب عبارة المرور: ستُستورد التكاملات بدون أسرارها (وتُترك متوقفة إن احتاجتها).</div></div>` : ''}
      ${r.secrets === 'used' ? h`<div class="banner info fs-sm mb-8">${icon('key-round', 16)}<div>فُتحت الأسرار بعبارة المرور وستُحفظ مشفّرة بمفتاح هذا الخادم.</div></div>` : ''}
      ${r.unknown_sections.length ? h`<div class="banner warn fs-sm mb-8" data-unknown>${icon('info', 16)}<div>أقسام لا يعرفها هذا الإصدار وتُتخطّى: <bdi dir="ltr">${r.unknown_sections.join('، ')}</bdi></div></div>` : ''}
      <div class="table-wrap"><table class="t compact" data-report-table><thead><tr><th>القسم</th><th class="num">${verb[0]}</th><th class="num">${verb[1]}</th><th class="num">دون تغيير</th><th class="num">تُخطّي</th></tr></thead><tbody>
      ${r.sections.map(function (s) {
        return h`<tr data-row="${s.key}"><td>${api.name(s.label)}${skippedList(s)}</td><td class="num" data-created>${fmt.int(s.created)}</td><td class="num" data-updated>${fmt.int(s.updated)}</td><td class="num muted" data-unchanged>${fmt.int(s.unchanged)}</td><td class="num${s.skipped.length ? ' t-danger' : ''}" data-skipped>${fmt.int(s.skipped.length)}</td></tr>`;
      })}</tbody></table></div></div>`;
  }
  function filenameOf(res) {
    var m = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') || '');
    return m ? m[1] : 'fleet-config.json';
  }
  function transferCard(el, sections) {
    var owner = !!(api.me && api.me.all_permissions);
    BT.render(el, h`<div class="card mb-16" data-transfer>
      <div class="card-h"><div class="card-t">${icon('file-text', 16)} نقل الإعدادات (JSON)</div></div>
      <div class="card-b">
        <div class="hint mb-12">لنقل ما ضبطته هنا (سيرفر التجربة مثلاً) إلى نسخة أخرى (الإنتاج): القوائم والإعدادات والأدوار والمنصات وأنظمة الرواتب ودليل الحسابات وقوالب الطباعة والترجمات المنشورة. لا يحتوي الملف بيانات تشغيلية (موظفين، سيارات، عهد، مبالغ، تقارير) ولا مستخدمين أو كلمات مرور. المراجع بين الأقسام بالرموز والأسماء (رمز المنصة، رقم الحساب، السجل التجاري للشركة) لا بأرقام قاعدة البيانات.</div>
        <form data-export-form novalidate>
          <div class="between mb-8"><b class="fs-sm">التصدير</b>${BT.f.check({ name: 'all', label: 'تحديد الكل', checked: true })}</div>
          <div class="grid gap-8 mb-12" style="grid-template-columns:repeat(auto-fill,minmax(240px,1fr))" data-sections>${sections.map(function (s) {
            return h`<label class="check"><input type="checkbox" name="section" value="${s.key}" data-section="${s.key}" checked><span>${api.name(s.label)}</span></label>`;
          })}</div>
          ${owner ? h`<div class="highlight-box mb-12">${BT.f.switch({ name: 'include_secrets', label: 'تضمين الأسرار' })}
            <div class="hint mt-4">مفاتيح التكاملات (R2 وواتساب وFirebase) لا تُصدَّر إلا بهذا الخيار، مشفّرة (AES-256-GCM) بعبارة مرور تكتبها هنا ولا تُحفظ في أي مكان. بدونها لا يمكن فتحها، والاستيراد يطلبها. احفظها بعيداً عن الملف.</div>
            <div class="field mt-8" data-pass-box style="display:none"><label for="f-export-pass">عبارة المرور (10 أحرف على الأقل)</label><input class="input ltr" type="password" id="f-export-pass" name="passphrase" autocomplete="new-password" minlength="10"><div class="err-msg"></div></div></div>` : h`<div class="hint mb-12">${icon('lock', 14)} الملف بدون أسرار التكاملات (تصدير الأسرار والاستيراد لمن يملك كل الصلاحيات).</div>`}
          <button type="submit" class="btn btn-sm btn-primary" data-export>${icon('download', 14)} تصدير</button>
        </form>
        ${owner ? h`<hr style="margin:16px 0;border:0;border-top:1px solid var(--border, #e5e7eb)"><form data-import-form novalidate>
          <b class="fs-sm">الاستيراد</b>
          <div class="hint mb-8">اختر ملف إعدادات صُدِّر من هذا النظام. المعاينة تعرض ما سيُنشأ وما سيُحدَّث وما يُتخطّى وسببه دون أن تحفظ شيئاً، ثم «استيراد» يطبّقه كله في معاملة واحدة. الاستيراد يدمج فقط: لا يحذف ما ليس في الملف.</div>
          <div class="form-grid">
            <div class="field"><label for="f-config-file">ملف الإعدادات (JSON)</label><input class="input" type="file" id="f-config-file" name="file" accept=".json,application/json" data-import-file><div class="err-msg"></div></div>
            <div class="field"><label for="f-import-pass">عبارة المرور (إن كان في الملف أسرار)</label><input class="input ltr" type="password" id="f-import-pass" name="passphrase" autocomplete="off"><div class="hint">بدونها تُستورد التكاملات بلا أسرارها</div></div>
          </div>
          <div class="row gap-8 mt-8"><button type="submit" class="btn btn-sm btn-secondary" data-preview>${icon('eye', 14)} معاينة</button><button type="button" class="btn btn-sm btn-primary" data-import disabled>${icon('upload', 14)} استيراد</button></div>
          <div class="mt-12" data-import-out></div>
        </form>` : ''}
      </div></div>`);

    var ex = el.querySelector('[data-export-form]');
    var all = ex.querySelector('[name=all]'), boxes = BT.$$('[data-section]', ex);
    all.onchange = function () { boxes.forEach(function (b) { b.checked = all.checked; }); };
    boxes.forEach(function (b) { b.onchange = function () { all.checked = boxes.every(function (x) { return x.checked; }); }; });
    var sw = ex.querySelector('[name=include_secrets]'), passBox = ex.querySelector('[data-pass-box]');
    if (sw) sw.onchange = function () { passBox.style.display = sw.checked ? '' : 'none'; };
    ex.addEventListener('submit', function (e) {
      e.preventDefault();
      var chosen = boxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
      if (!chosen.length) { BT.toast('اختر قسماً واحداً على الأقل', { type: 'error' }); return; }
      var secrets = !!(sw && sw.checked), pass = secrets ? ex.querySelector('[name=passphrase]').value : '';
      if (secrets && pass.length < 10) { BT.toast(api.t('errors', 'config_passphrase_short', { min: 10 }), { type: 'error' }); return; }
      var button = ex.querySelector('[data-export]');
      button.classList.add('is-loading');
      var body = { sections: chosen.length === boxes.length ? [] : chosen, include_secrets: secrets, passphrase: secrets ? pass : null };
      fetch(api.url('/config/export'), { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': api.csrf, 'Accept-Language': api.lang }, body: JSON.stringify(body) })
        .then(function (res) {
          if (!res.ok) return res.json().then(function (b) { throw new api.ApiError(res.status, b); }, function () { throw new api.ApiError(res.status, {}); });
          return res.blob().then(function (blob) { return { blob: blob, name: filenameOf(res) }; });
        })
        .then(function (f) {
          button.classList.remove('is-loading');
          var a = document.createElement('a'); a.href = URL.createObjectURL(f.blob); a.download = f.name; document.body.appendChild(a); a.click(); a.remove();
          setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
          BT.toast('صُدِّرت الإعدادات', { sub: secrets ? 'الأسرار مشفّرة بعبارة المرور' : 'بدون أسرار' });
        }, function (err) { button.classList.remove('is-loading'); BT.toast(api.message(err), { type: 'error', timeout: 8000 }); });
    });

    var im = el.querySelector('[data-import-form]');
    if (!im) return;
    var out = im.querySelector('[data-import-out]'), go = im.querySelector('[data-import]');
    function send(dry) {
      var file = im.querySelector('[data-import-file]').files[0];
      if (!file) { BT.toast('اختر ملف الإعدادات أولاً', { type: 'error' }); return Promise.reject(null); }
      var fd = new FormData();
      fd.append('file', file, file.name);
      fd.append('dry_run', dry ? 'true' : 'false');
      var pass = im.querySelector('[name=passphrase]').value;
      if (pass) fd.append('passphrase', pass);
      return api.request('POST', '/config/import', { form: fd });
    }
    im.querySelector('[data-import-file]').onchange = function () { go.disabled = true; BT.render(out, ''); };
    im.addEventListener('submit', function (e) {
      e.preventDefault();
      var b = im.querySelector('[data-preview]');
      b.classList.add('is-loading');
      send(true).then(function (r) {
        b.classList.remove('is-loading');
        BT.render(out, h`<div class="fs-sm mb-8"><b>المعاينة</b> — لم يُحفظ شيء بعد.</div>${reportTable(r, false)}`);
        go.disabled = false;
      }, function (err) { b.classList.remove('is-loading'); go.disabled = true; if (err) BT.toast(api.message(err), { type: 'error', timeout: 9000 }); });
    });
    go.onclick = function () {
      BT.confirm({ title: 'استيراد الإعدادات؟', tone: 'warn', message: 'تُنشأ الأقسام الناقصة وتُحدَّث الموجودة كما في المعاينة، في معاملة واحدة، ويُسجَّل ذلك في سجل التدقيق. لا يُحذف شيء ليس في الملف.', confirmText: 'استيراد' }).then(function (c) {
        if (!c.ok) return;
        go.classList.add('is-loading');
        send(false).then(function (r) {
          go.classList.remove('is-loading'); go.disabled = true;
          var created = 0, updated = 0;
          r.sections.forEach(function (s) { created += s.created; updated += s.updated; });
          BT.render(out, h`<div class="banner success fs-sm mb-8" data-result>${icon('circle-check', 16)}<div>تم الاستيراد: أُنشئ ${fmt.int(created)} وحُدِّث ${fmt.int(updated)}.</div></div>${reportTable(r, true)}`);
          BT.toast('تم استيراد الإعدادات');
        }, function (err) { go.classList.remove('is-loading'); if (err) BT.toast(api.message(err), { type: 'error', timeout: 9000 }); });
      });
    };
  }

  BT.pages['integrations'] = function () {
    A.setTitle('التكاملات');
    var v = A.view();
    BT.render(v, h`${A.head('التكاملات', 'الخدمات الخارجية التي يتصل بها النظام. كل تغيير يُسجَّل في سجل التدقيق، والمفاتيح لا تُعرض بعد حفظها.', '')}<div data-transfer-box></div><div data-list></div>`);
    var el = v.querySelector('[data-list]'), tbox = v.querySelector('[data-transfer-box]');
    if (api.can('settings.view')) A.load(tbox, api.get('/config/sections'), function (sections) { setTimeout(function () { transferCard(tbox, sections); }); return ''; }).catch(function () {});
    function draw() {
      if (!api.can('integrations.manage')) return;
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
