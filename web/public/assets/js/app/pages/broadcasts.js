/* =====================================================================
   app/pages/broadcasts.js — ركن الإشعارات: رسالة من المكتب لكل السائقين أو لمجموعة منهم، عبر كل قناة
   مفعّلة: صندوق إشعارات التطبيق (دائماً)، وإشعار Firebase على الهاتف، وواتساب — كل قناة فقط إن كانت
   مفعّلة في «التكاملات». قبل الإرسال: كم سائقاً تصله كل قناة ولماذا لا تصل الباقين. بعده: السجل
   وإحصاء كل قناة (وصل/فشل/تخطّي) والفشل بأسبابه وإعادة إرسال الفاشل.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  var LANGS = [['ar', 'العربية'], ['en', 'English'], ['fr', 'Français'], ['sw', 'Kiswahili'], ['hi', 'हिन्दी'], ['fil', 'Filipino']];
  var REQUIRED = { ar: true, en: true };
  var CHANNEL = { inbox: 'صندوق إشعارات التطبيق', push: 'إشعار على الهاتف (Firebase)', whatsapp: 'واتساب' };
  var CHANNEL_HINT = {
    inbox: 'دائماً: تظهر في قائمة الإشعارات داخل التطبيق',
    push: 'تصل فقط للهواتف المسجلة للإشعارات',
    whatsapp: 'تُرسل رسالة كل فترة حسب إعدادات الإرسال الجماعي حتى لا يُحظر الرقم'
  };
  var STATUS = { draft: ['مسودة', 'n'], scheduled: ['مجدول', 'b'], sending: ['قيد الإرسال', 'o'], sent: ['أُرسل', 'g'], cancelled: ['ملغى', 'n'] };
  var DSTATUS = { queued: ['بالانتظار', 'b'], sent: ['وصل', 'g'], failed: ['فشل', 'r'], skipped: ['تخطّي', 'n'] };
  var REASON = {
    channel_disabled: 'القناة غير مفعّلة', no_token: 'الهاتف غير مسجل للإشعارات', no_phone: 'لا يوجد رقم هاتف',
    invalid_token: 'رمز الهاتف لم يعد صالحاً', provider_error: 'خطأ من مزود الخدمة', not_on_whatsapp: 'الرقم ليس على واتساب',
    interrupted: 'انقطع الإرسال (لم يُعد تلقائياً)', cancelled: 'أُلغي قبل الإرسال', opted_out: 'ألغى الاشتراك'
  };
  var AUDIENCE = { all: 'كل السائقين', company: 'حسب الشركة', platform: 'حسب المنصة', on_duty: 'المناوبون الآن', selected: 'سائقون محددون' };
  var WA_LIMIT = 4096, TITLE_MAX = 120, BODY_MAX = 2000;
  // the looks the app knows (an older app draws an unknown one as its standard card): icon and accent per style
  var STYLES = [
    ['info', 'معلومة', 'info', '#1D4ED8'],
    ['announcement', 'إعلان', 'radio', '#7C3AED'],
    ['reminder', 'تذكير', 'clock', '#B45309'],
    ['warning', 'تحذير', 'triangle-alert', '#C2410C'],
    ['urgent', 'عاجل', 'siren', '#B91C1C'],
    ['success', 'تهنئة / نجاح', 'badge-check', '#15803D']
  ];
  var STYLE = {}; STYLES.forEach(function (x) { STYLE[x[0]] = { label: x[1], icon: x[2], color: x[3] }; });
  var LAYOUTS = [['standard', 'عادية', 'عنوان ونص'], ['highlight', 'بارزة', 'أيقونة كبيرة وعنوان ونص'], ['compact', 'مختصرة', 'سطر واحد']];
  // the app's button opens one of its own screens only: no links (a link in a message is what phishing looks like)
  var TARGETS = [['', 'بدون زر'], ['cash', 'العهدة والنقد'], ['documents', 'المستندات'], ['maintenance', 'الصيانة'], ['leave', 'طلب إجازة']];
  var TARGET_LABEL = { cash: 'افتح العهدة', documents: 'افتح المستندات', maintenance: 'افتح الصيانة', leave: 'اطلب إجازة' };
  var IMAGE_MAX = 2 * 1024 * 1024, URGENT_MARK = '⚠️';
  var HEADS_UP = { urgent: true, warning: true };
  function styleOf(k) { return STYLE[k] || STYLE.info; }
  function stylePill(k) { var s = styleOf(k); return h`<span class="pill nowrap" data-style-pill="${k}" style="color:${s.color};background:${s.color}1a">${icon(s.icon, 12)} ${s.label}</span>`; }
  function markedTitle(style, title) { return style === 'urgent' ? URGENT_MARK + ' ' + title : title; }

  function status(b) { var s = STATUS[b.status] || [b.status, 'n']; return BT.pill(s[0], s[1]); }
  function audienceText(a) {
    var n = (a.company_ids || a.platform_ids || a.employee_ids || []).length;
    return AUDIENCE[a.kind] + (n ? ' (' + fmt.int(n) + ')' : '');
  }
  function statsLine(b) {
    return h`<span class="row gap-8 wrap">${Object.keys(b.stats).map(function (c) {
      var s = b.stats[c];
      return h`<span class="fs-sm nowrap" data-stat="${c}" title="${CHANNEL[c] || c}">${icon(c === 'inbox' ? 'inbox' : c === 'push' ? 'bell-ring' : 'message-square', 13)} <b class="num">${fmt.int(s.sent)}</b>${s.failed ? h` · <span class="t-danger num">${fmt.int(s.failed)} فشل</span>` : ''}${s.queued ? h` · <span class="num">${fmt.int(s.queued)} بالانتظار</span>` : ''}</span>`;
    })}</span>`;
  }

  BT.pages['broadcasts'] = function (p, q) {
    A.setTitle('ركن الإشعارات');
    var v = A.view();
    BT.render(v, h`${A.head('ركن الإشعارات', 'رسالة لكل السائقين أو لمجموعة منهم: تصل دائماً في صندوق إشعارات التطبيق، وعلى الهاتف وواتساب إن كانت القناة مفعّلة في التكاملات',
        api.can('broadcasts.send') ? A.btn('إشعار جديد', { icon: 'plus', cls: 'btn-primary', action: 'broadcast-new' }) : '')}
      <div class="card"><div data-t></div></div>`);
    var t = BT.table(v.querySelector('[data-t]'), {
      key: 'broadcasts',
      fetch: function (s) { return api.get('/broadcasts', { limit: s.limit, offset: s.offset, q: s.q || undefined, status: s.chip || undefined }); },
      search: { placeholder: 'بحث في العنوان…' },
      chips: { value: '', all: 'الكل', options: [{ v: 'scheduled', t: 'مجدولة' }, { v: 'sending', t: 'قيد الإرسال' }, { v: 'sent', t: 'أُرسلت' }, { v: 'draft', t: 'مسودات' }, { v: 'cancelled', t: 'ملغاة' }] },
      columns: [
        { key: 'title', label: 'الإشعار', render: function (b) { return h`<b data-title>${b.title.ar}</b><span class="sub">${b.title.en}</span>`; } },
        { key: 'style', label: 'النوع', render: function (b) { return stylePill(b.style); } },
        { key: 'audience', label: 'إلى', render: function (b) { return h`${audienceText(b.audience)}<span class="sub num">${b.recipients ? fmt.int(b.recipients) + ' سائق' : ''}</span>`; } },
        { key: 'stats', label: 'الوصول', render: statsLine },
        { key: 'status', label: 'الحالة', render: status },
        { key: 'at', label: 'الوقت', render: function (b) { return h`${fmt.dt(b.sent_at || b.started_at || b.scheduled_at || b.created_at)}${b.status === 'scheduled' ? h`<span class="sub">مجدول</span>` : ''}`; } }
      ],
      rowClick: function (b) { view(b.id, function () { t.refresh(); }); },
      empty: { icon: 'send', title: 'لم يُرسل إشعار بعد' }
    });
    A._broadcastsTable = t;
    if (q.broadcast) view(q.broadcast, function () { t.refresh(); });
  };
  BT.actions['broadcast-new'] = function () { compose(function () { if (A._broadcastsTable) A._broadcastsTable.refresh(); }); };

  /* ---------- الكتابة ---------- */
  function langPanel(code) {
    return h`<div data-panel="${code}" data-group="bc-lang"${code === 'ar' ? raw(' class="active"') : ''}>
      <div class="form">
        ${BT.f.input({ name: 'title_' + code, label: 'العنوان', required: !!REQUIRED[code], optional: !REQUIRED[code], maxlength: TITLE_MAX, ltr: code !== 'ar' })}
        ${BT.f.textarea({ name: 'body_' + code, label: 'النص', required: !!REQUIRED[code], optional: !REQUIRED[code], rows: 4, maxlength: BODY_MAX, ltr: code !== 'ar' })}
        <div class="between fs-sm muted"><span data-count="${code}">0 / ${BODY_MAX}</span><span data-wa-note="${code}"></span></div>
      </div></div>`;
  }
  function channelBox(c) {
    var off = !c.enabled;
    return h`<div class="mb-8" data-channel="${c.name}"><label class="check"><input type="checkbox" name="ch_${c.name}"${c.always || !off ? raw(' checked') : ''}${c.always || off ? raw(' disabled') : ''}><span>${CHANNEL[c.name] || c.name}</span></label>
      <div class="hint">${off ? h`غير مفعّلة: لا يُرسل منها شيء. ${api.can('integrations.manage') ? h`<a href="#/integrations">تفعيلها من التكاملات</a>` : 'يفعّلها مدير النظام من التكاملات'}` : CHANNEL_HINT[c.name] || ''}</div></div>`;
  }
  function multi(name, items) {
    if (!items.length) return h`<div class="muted fs-sm">لا يوجد</div>`;
    return h`${items.length > 8 ? h`<input class="input mb-8" type="search" placeholder="تصفية…" data-filter="${name}">` : ''}<div class="multi" data-multi="${name}" style="max-height:200px;overflow:auto">${items.map(function (x) {
      return h`<label class="check" data-label="${x.label}"><input type="checkbox" name="${name}" value="${x.id}"><span>${x.label}</span></label>`;
    })}</div>`;
  }
  /* the in-app card exactly as the app draws it: the style's accent bar, icon tile, layout; the picture; the button */
  function appCard(o) {
    var st = styleOf(o.style), c = st.color, title = o.title || 'العنوان', body = o.body || 'نص الإشعار';
    var img = o.image ? h`<img data-pv-image src="${o.image}" alt="" style="display:block;width:100%;max-height:140px;object-fit:cover;border-radius:10px;margin-top:8px">` : '';
    var btn = o.target ? h`<div data-pv-action style="margin-top:10px;text-align:center;padding:9px;border-radius:10px;font-weight:600;font-size:13px;color:${c};background:${c}1a">${o.label || TARGET_LABEL[o.target]}</div>` : '';
    var frame = 'border-inline-start:3px solid ' + c + ';border-radius:14px;padding:12px;background:' + (o.layout === 'highlight' ? c + '12' : 'var(--surface,#fff)') + ';box-shadow:0 1px 2px rgba(0,0,0,.06)';
    if (o.layout === 'compact') {
      return h`<div data-pv-card="compact" data-pv-style="${o.style}" style="${frame};display:flex;align-items:center;gap:8px"><span style="color:${c}">${icon(st.icon, 16)}</span><b class="fs-sm" data-pv-title style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${title}</b>${o.target ? h`<span data-pv-action class="fs-sm" style="color:${c};font-weight:600">${o.label || TARGET_LABEL[o.target]}</span>` : ''}</div>`;
    }
    if (o.layout === 'highlight') {
      return h`<div data-pv-card="highlight" data-pv-style="${o.style}" style="${frame};text-align:center"><div style="width:52px;height:52px;margin:4px auto 8px;border-radius:16px;display:flex;align-items:center;justify-content:center;color:${c};background:${c}1f">${icon(st.icon, 28)}</div><b data-pv-title style="color:${c}">${title}</b><div class="fs-sm" style="white-space:pre-wrap" data-pv-body>${body}</div>${img}${btn}</div>`;
    }
    return h`<div data-pv-card="standard" data-pv-style="${o.style}" style="${frame}"><div style="display:flex;gap:10px"><div style="flex:none;width:38px;height:38px;border-radius:12px;display:flex;align-items:center;justify-content:center;color:${c};background:${c}1f">${icon(st.icon, 20)}</div><div style="min-width:0"><b data-pv-title>${title}</b><div class="fs-sm" style="white-space:pre-wrap" data-pv-body>${body}</div></div></div>${img}${btn}</div>`;
  }
  function previewCard(o) {
    var title = o.title || 'العنوان', body = o.body || 'نص الإشعار', pop = HEADS_UP[o.style];
    return h`<div class="highlight-box" data-preview>
      <div class="fs-sm muted mb-4">${icon('inbox', 13)} في صندوق إشعارات التطبيق</div>
      <div class="mb-12">${appCard(o)}</div>
      <div class="fs-sm muted mb-4">${icon('bell-ring', 13)} على شاشة الهاتف</div>
      <div class="card mb-4" style="padding:8px 12px" data-pv-push><b class="fs-sm" data-pv-push-title>${markedTitle(o.style, title)}</b><div class="fs-sm muted" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${body}</div></div>
      <div class="hint mb-12" data-pv-push-mode="${pop ? 'heads_up' : 'quiet'}">${pop ? 'يظهر فوق الشاشة بصوت (أولوية عالية)' : 'يصل بهدوء في شريط الإشعارات دون أن يظهر فوق الشاشة'}</div>
      <div class="fs-sm muted mb-4">${icon('message-square', 13)} في واتساب</div>
      <div data-pv-wa style="padding:8px 12px;border-radius:10px;background:#dcf8c6;color:#111;white-space:pre-wrap;font-size:13px"><b>${markedTitle(o.style, title)}</b>\n\n${body}</div>
    </div>`;
  }
  function lookFields() {
    return h`<div class="section-t mt-16">شكل الرسالة</div>
      <div class="row gap-8 wrap mb-8" data-styles>${STYLES.map(function (x, i) {
        return h`<label class="option-card" data-style="${x[0]}" style="padding:6px 10px;cursor:pointer"><input class="radio-in" type="radio" name="style" value="${x[0]}"${i === 0 ? raw(' checked') : ''}><span style="color:${x[3]}">${icon(x[2], 14)} <b>${x[1]}</b></span></label>`;
      })}</div>
      <div class="fs-sm muted mb-4">شكل البطاقة</div>
      <div class="grid mb-8" style="grid-template-columns:repeat(3,minmax(0,1fr));gap:8px" data-layouts>${LAYOUTS.map(function (x, i) {
        var thumb = x[0] === 'compact'
          ? h`<div style="height:10px;border-radius:3px;background:currentColor;opacity:.35"></div>`
          : x[0] === 'highlight'
            ? h`<div style="width:18px;height:18px;border-radius:6px;margin:0 auto 4px;background:currentColor;opacity:.5"></div><div style="height:5px;width:60%;margin:0 auto 3px;border-radius:3px;background:currentColor;opacity:.5"></div><div style="height:4px;width:80%;margin:0 auto;border-radius:3px;background:currentColor;opacity:.25"></div>`
            : h`<div style="display:flex;gap:4px"><div style="width:12px;height:12px;border-radius:4px;background:currentColor;opacity:.5"></div><div style="flex:1"><div style="height:5px;width:70%;border-radius:3px;margin-bottom:3px;background:currentColor;opacity:.5"></div><div style="height:4px;border-radius:3px;background:currentColor;opacity:.25"></div></div></div>`;
        return h`<label class="option-card" data-layout="${x[0]}" style="display:block;padding:8px;cursor:pointer"><input class="radio-in" type="radio" name="layout" value="${x[0]}"${i === 0 ? raw(' checked') : ''}><div class="muted" style="border:1px solid var(--border,#ddd);border-radius:8px;padding:6px;margin:4px 0">${thumb}</div><b class="fs-sm">${x[1]}</b><div class="hint">${x[2]}</div></label>`;
      })}</div>
      ${BT.f.upload({ name: 'image', label: 'صورة في البطاقة', optional: true, accept: 'image/jpeg,image/png', icon: 'image', accept_label: 'JPEG أو PNG · حتى 2MB' })}
      <div class="grid" style="grid-template-columns:minmax(0,1fr) minmax(0,1fr) minmax(0,1fr);gap:8px">
        ${BT.f.select({ name: 'action_target', label: 'زر في البطاقة', value: '', placeholder: false, optional: true, options: TARGETS.map(function (x) { return { v: x[0], t: x[1] }; }) })}
        ${BT.f.input({ name: 'action_label_ar', label: 'نص الزر (عربي)', optional: true, maxlength: 30 })}
        ${BT.f.input({ name: 'action_label_en', label: 'نص الزر (English)', optional: true, maxlength: 30, ltr: true })}
      </div>
      <div class="hint">الزر يفتح شاشة من التطبيق فقط (لا روابط خارجية). بدون نص يظهر نص التطبيق الافتراضي بلغة السائق.</div>`;
  }

  function compose(done) {
    Promise.all([
      api.get('/broadcasts/channels'),
      api.get('/companies').catch(function () { return []; }),
      api.get('/payroll/platforms').catch(function () { return []; }),
      A.all('/employees', { is_driver: true }).catch(function () { return []; })
    ]).then(function (r) {
      var states = r[0], companies = r[1], platforms = r[2], drivers = r[3];
      var dlg = BT.modal.open({
        title: 'إشعار جديد', subtitle: 'العربية والإنجليزية مطلوبتان؛ اللغات الأخرى اختيارية (من لم تُكتب لغته يصله بالإنجليزية)', icon: 'send', size: 'xl', form: true,
        body: h`<div class="grid" style="grid-template-columns:minmax(0,1fr) 300px;gap:16px">
          <div>
            ${BT.tabs('bc-lang', LANGS.map(function (l) { return [l[0], l[1] + (REQUIRED[l[0]] ? ' *' : '')]; }), 'ar', 'tabs-line')}
            <div class="mt-12">${LANGS.map(function (l) { return langPanel(l[0]); })}</div>
            ${lookFields()}
            <div class="section-t mt-16">إلى من؟</div>
            ${BT.f.radios({ name: 'audience', value: 'all', options: Object.keys(AUDIENCE).map(function (k) { return { v: k, t: AUDIENCE[k] }; }) })}
            <div data-aud="company" class="hidden">${multi('company_ids', companies.map(function (c) { return { id: c.id, label: api.name(c.name) }; }))}</div>
            <div data-aud="platform" class="hidden">${multi('platform_ids', platforms.map(function (x) { return { id: x.id, label: api.name(x.name) }; }))}</div>
            <div data-aud="selected" class="hidden">${multi('employee_ids', drivers.map(function (d) { return { id: d.id, label: api.name(d.name) + ' · ' + (d.employee_number || '') }; }))}</div>
            <div data-aud="on_duty" class="hidden hint">من بدأ يومه بسيارته ولم ينهه بعد، وقت الإرسال</div>
            <div class="section-t mt-16">القنوات</div>
            ${states.map(channelBox)}
            <div class="section-t mt-16">الموعد</div>
            ${BT.f.input({ name: 'scheduled_at', label: 'إرسال لاحقاً (بتوقيت الكويت)', type: 'datetime-local', optional: true, hint: 'اتركه فارغاً للإرسال الآن' })}
          </div>
          <div><div class="section-t">المعاينة</div>${BT.f.select({ name: 'pv_lang', label: 'بلغة', value: 'ar', placeholder: false, options: LANGS.map(function (l) { return { v: l[0], t: l[1] }; }) })}<div data-pv></div></div>
        </div>`,
        buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ كمسودة', cls: 'btn-outline', close: false, onClick: function (d) { submit(d, false); } }, { label: 'متابعة', cls: 'btn-primary', submit: true }],
        onSubmit: function (vals, d) { submit(d, true); return false; }
      });
      var f = dlg.form;
      BT.hydrate(dlg.panel);
      function val(n) { var el = f.querySelector('[name="' + n + '"]'); return el ? el.value.trim() : ''; }
      function text(kind, lang) { return val(kind + '_' + lang) || val(kind + '_en') || val(kind + '_ar'); }
      var picture = { file: null, url: null, sha: null };
      function checked(n, d) { var el = f.querySelector('[name="' + n + '"]:checked'); return el ? el.value : d; }
      function redraw() {
        var lang = val('pv_lang') || 'ar';
        var inp = f.querySelector('[name=image]'), file = inp && inp.files && inp.files[0] || null;
        if (file !== picture.file) {
          if (picture.url) URL.revokeObjectURL(picture.url);
          picture = { file: file, url: file ? URL.createObjectURL(file) : null, sha: null };
        }
        var target = val('action_target');
        BT.render(f.querySelector('[data-pv]'), previewCard({
          title: text('title', lang), body: text('body', lang), style: checked('style', 'info'), layout: checked('layout', 'standard'),
          image: picture.url, target: target, label: target ? (lang === 'ar' ? val('action_label_ar') : val('action_label_en') || val('action_label_ar')) : ''
        }));
        BT.$$('[data-style],[data-layout]', f).forEach(function (el) { var i = el.querySelector('input'); el.style.outline = i && i.checked ? '2px solid var(--primary,#1D4ED8)' : ''; });
        LANGS.forEach(function (l) {
          var t = val('title_' + l[0]), b = val('body_' + l[0]), n = b.length;
          f.querySelector('[data-count="' + l[0] + '"]').textContent = fmt.int(n) + ' / ' + fmt.int(BODY_MAX);
          f.querySelector('[data-wa-note="' + l[0] + '"]').textContent = (t.length + n + 6) > 1000 ? 'رسالة واتساب طويلة: يُفضّل أقل من 1000 حرف' : 'واتساب يقبل حتى ' + fmt.int(WA_LIMIT) + ' حرف';
        });
        var aud = (f.querySelector('[name=audience]:checked') || {}).value;
        BT.$$('[data-aud]', f).forEach(function (el) { el.classList.toggle('hidden', el.getAttribute('data-aud') !== aud); });
      }
      f.addEventListener('input', function (e) {
        var flt = e.target.getAttribute && e.target.getAttribute('data-filter');
        if (flt) {
          var needle = e.target.value.trim().toLowerCase();
          BT.$$('[data-multi="' + flt + '"] label', f).forEach(function (l) { l.style.display = l.getAttribute('data-label').toLowerCase().indexOf(needle) >= 0 ? '' : 'none'; });
        }
        redraw();
      });
      f.addEventListener('change', redraw);
      redraw();

      function body() {
        var title = {}, text_ = {};
        LANGS.forEach(function (l) { var t = val('title_' + l[0]), b = val('body_' + l[0]); if (t) title[l[0]] = t; if (b) text_[l[0]] = b; });
        var kind = (f.querySelector('[name=audience]:checked') || {}).value || 'all';
        var picked = function (n) { return BT.$$('[name="' + n + '"]:checked', f).map(function (i) { return i.value; }); };
        var audience = { kind: kind };
        if (kind === 'company') audience.company_ids = picked('company_ids').map(Number);
        if (kind === 'platform') audience.platform_ids = picked('platform_ids').map(Number);
        if (kind === 'selected') audience.employee_ids = picked('employee_ids');
        var chans = states.filter(function (c) { var el = f.querySelector('[name="ch_' + c.name + '"]'); return !c.always && el && el.checked; }).map(function (c) { return c.name; });
        var at = val('scheduled_at');
        var out = { title: title, body: text_, audience: audience, channels: chans, scheduled_at: at ? fmt.kwIso(at) : null, style: checked('style', 'info'), layout: checked('layout', 'standard'), image: picture.sha };
        var target = val('action_target');
        if (target) {
          var label = {};
          if (val('action_label_ar')) label.ar = val('action_label_ar');
          if (val('action_label_en')) label.en = val('action_label_en');
          out.action = { target: target, label: label };
        }
        return out;
      }
      // the picture goes up once, before the broadcast that names it
      function withImage() {
        if (!picture.file || picture.sha) return Promise.resolve();
        if (picture.file.size > IMAGE_MAX) return Promise.reject({ code: 'file_too_large', message: 'الصورة أكبر من 2MB' });
        return api.upload(picture.file).then(function (r) { picture.sha = r.sha256; });
      }
      function submit(d, send) {
        if (!BT.form.validate(f)) return;
        var b = body();
        var k = b.audience.kind;
        if ((k === 'company' && !b.audience.company_ids.length) || (k === 'platform' && !b.audience.platform_ids.length) || (k === 'selected' && !b.audience.employee_ids.length)) {
          BT.toast('اختر من يصله الإشعار', { type: 'error' });
          return;
        }
        if (picture.file && picture.file.size > IMAGE_MAX) { BT.toast('الصورة أكبر من 2MB', { type: 'error' }); return; }
        if (picture.file && !picture.sha) { withImage().then(function () { submit(d, send); }, api.fail); return; }
        if (!send) {
          api.post('/broadcasts', Object.assign({}, b, { send: false })).then(function () { BT.toast('حُفظت المسودة'); d.close(); if (done) done(); }, api.fail);
          return;
        }
        api.post('/broadcasts/preview', { audience: b.audience, channels: b.channels }).then(function (pv) {
          A.confirmRun({
            title: b.scheduled_at ? 'جدولة الإشعار؟' : 'إرسال الإشعار الآن؟', confirmText: b.scheduled_at ? 'جدولة' : 'إرسال', tone: 'primary',
            message: h`يصل الإشعار إلى <b class="num" data-confirm-recipients>${fmt.int(pv.recipients)}</b> سائق${b.scheduled_at ? h` في ${fmt.dt(b.scheduled_at)}` : ''}.`,
            details: confirmDetails(pv),
            run: function () { return api.post('/broadcasts', Object.assign({}, b, { send: true })); },
            after: function (res) {
              if (!res) return;
              BT.toast(res.status === 'scheduled' ? 'جُدول الإشعار' : 'أُرسل الإشعار', { sub: res.status === 'sending' ? 'الهاتف وواتساب يُرسلان في الخلفية' : undefined });
              d.close();
              if (done) done();
            }
          });
        }, api.fail);
      }
    }, api.fail);
  }
  function confirmDetails(pv) {
    return h`<div class="table-wrap mt-12"><table class="t compact" data-confirm-counts><thead><tr><th>القناة</th><th>تصل</th><th>لا تصل</th></tr></thead><tbody>${Object.keys(pv.channels).map(function (c) {
      var x = pv.channels[c];
      return h`<tr data-count-channel="${c}"><td>${CHANNEL[c] || c}</td><td class="num"><b>${fmt.int(x.will)}</b></td><td class="fs-sm">${Object.keys(x.skipped).map(function (r) { return (REASON[r] || r) + ': ' + fmt.int(x.skipped[r]); }).join(' · ') || '—'}</td></tr>`;
    })}</tbody></table></div>
    <div class="hint mt-8"><span data-inbox-only>${fmt.int(pv.inbox_only)}</span> سائق يصله في التطبيق فقط.${pv.channels.whatsapp && pv.channels.whatsapp.will ? h` واتساب: رسالة كل ${fmt.int(pv.pace.interval_seconds)} ثانية بين ${pv.pace.from_hour}:00 و${pv.pace.until_hour}:00، وحتى ${fmt.int(pv.pace.daily_limit)} رسالة يومياً.` : ''}</div>`;
  }

  /* ---------- التفاصيل ---------- */
  function view(id, done) {
    Promise.all([api.get('/broadcasts/' + id), api.get('/broadcasts/' + id + '/deliveries', { status: 'failed', limit: 200 }), api.get('/broadcasts/' + id + '/deliveries', { status: 'skipped', limit: 200 })]).then(function (r) {
      var b = r[0], problems = r[1].concat(r[2]);
      var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
      var failed = Object.keys(b.stats).reduce(function (n, c) { return n + b.stats[c].failed; }, 0);
      function after(dlg) { return function () { dlg.close(); if (done) done(); view(id, done); }; }
      if (api.can('broadcasts.send')) {
        if (b.status === 'draft') btns.push({ label: 'إرسال', cls: 'btn-primary', icon: 'send', close: false, onClick: function (dlg) { A.confirmRun({ title: 'إرسال المسودة؟', confirmText: 'إرسال', run: function () { return api.post('/broadcasts/' + id + '/send'); }, done: 'أُرسل', after: after(dlg) }); } });
        if (['draft', 'scheduled', 'sending'].indexOf(b.status) >= 0) btns.push({ label: 'إلغاء الإشعار', cls: 'btn-ghost', icon: 'ban', close: false, onClick: function (dlg) { A.confirmRun({ title: 'إلغاء الإشعار؟', message: b.status === 'sending' ? 'ما أُرسل لا يُسترجع؛ يتوقف إرسال الباقي.' : 'لن يُرسل.', confirmText: 'إلغاء الإشعار', tone: 'danger', run: function () { return api.post('/broadcasts/' + id + '/cancel'); }, done: 'أُلغي', after: after(dlg) }); } });
        if (failed && ['sending', 'sent'].indexOf(b.status) >= 0) btns.push({ label: 'إعادة إرسال الفاشل (' + fmt.int(failed) + ')', cls: 'btn-outline', icon: 'refresh-cw', close: false, onClick: function (dlg) { A.confirmRun({ title: 'إعادة إرسال الفاشل؟', message: 'يُعاد فقط ما فشل؛ ما وصل لا يُرسل مرة أخرى.', confirmText: 'إعادة الإرسال', run: function () { return api.post('/broadcasts/' + id + '/resend', {}); }, done: 'أُعيد للإرسال', after: after(dlg) }); } });
      }
      BT.drawer.open({
        title: b.title.ar, subtitle: audienceText(b.audience) + ' · ' + fmt.dt(b.sent_at || b.started_at || b.scheduled_at || b.created_at), icon: 'send', size: 'lg',
        body: h`<div data-broadcast="${b.id}">${BT.kv([
            ['الحالة', status(b)],
            ['النوع', h`${stylePill(b.style)} <span class="fs-sm muted">${(LAYOUTS.filter(function (x) { return x[0] === b.layout; })[0] || LAYOUTS[0])[1]}</span>`],
            b.action ? ['الزر', (TARGETS.filter(function (x) { return x[0] === b.action.target; })[0] || ['', b.action.target])[1]] : null,
            ['المستلمون', h`<span class="num">${fmt.int(b.recipients)}</span>`],
            b.scheduled_at ? ['موعد الإرسال', fmt.dt(b.scheduled_at)] : null,
            b.sent_at ? ['اكتمل', fmt.dt(b.sent_at)] : null
          ].filter(Boolean))}
          <div class="section-t mt-16">الوصول حسب القناة</div>
          <div class="table-wrap"><table class="t compact" data-stats><thead><tr><th>القناة</th><th>وصل</th><th>فشل</th><th>تخطّي</th><th>بالانتظار</th></tr></thead><tbody>${Object.keys(b.stats).map(function (c) {
            var s = b.stats[c];
            return h`<tr data-stats-channel="${c}"><td>${CHANNEL[c] || c}</td><td class="num">${fmt.int(s.sent)}</td><td class="num${s.failed ? ' t-danger' : ''}">${fmt.int(s.failed)}</td><td class="num">${fmt.int(s.skipped)}</td><td class="num">${fmt.int(s.queued)}</td></tr>`;
          })}</tbody></table></div>
          <div class="hint mt-4">«وصل» للهاتف وواتساب يعني أن المزود قبل الرسالة؛ فتحها في التطبيق هو الدليل على قراءتها.</div>
          <div class="section-t mt-16">ما لم يصل وسببه</div>
          ${problems.length ? h`<div class="table-wrap"><table class="t compact" data-problems><thead><tr><th>السائق</th><th>القناة</th><th>النتيجة</th><th>السبب</th></tr></thead><tbody>${problems.map(function (x) {
            var s = DSTATUS[x.status] || [x.status, 'n'];
            return h`<tr><td>${A.person(x.driver)}</td><td>${CHANNEL[x.channel] || x.channel}</td><td>${BT.pill(s[0], s[1])}</td><td class="fs-sm">${REASON[x.reason] || x.reason || '—'}</td></tr>`;
          })}</tbody></table></div>` : h`<div class="muted fs-sm">وصل لكل المستلمين في كل القنوات المطلوبة.</div>`}
          <div class="section-t mt-16">كما تظهر في التطبيق</div>
          <div style="max-width:360px" data-history-card>${appCard({ title: b.title.ar, body: b.body.ar, style: b.style, layout: b.layout, image: b.image ? api.url('/broadcasts/images/' + b.image) : null, target: b.action && b.action.target, label: b.action && b.action.label && b.action.label.ar })}</div>
          <div class="section-t mt-16">النص</div>
          ${LANGS.filter(function (l) { return b.title[l[0]]; }).map(function (l) { return h`<div class="highlight-box mb-8" lang="${l[0]}"><div class="fs-sm muted">${l[1]}</div><b>${b.title[l[0]]}</b><div class="fs-sm" style="white-space:pre-wrap">${b.body[l[0]] || ''}</div></div>`; })}</div>`,
        buttons: btns
      });
    }, api.fail);
  }
})();
