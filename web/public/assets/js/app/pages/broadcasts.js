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
  function previewCard(title, body) {
    return h`<div class="highlight-box" data-preview>
      <div class="fs-sm muted mb-4">${icon('inbox', 13)} في صندوق إشعارات التطبيق</div>
      <div class="mb-12"><b data-pv-title>${title || 'العنوان'}</b><div class="fs-sm" style="white-space:pre-wrap" data-pv-body>${body || 'نص الإشعار'}</div></div>
      <div class="fs-sm muted mb-4">${icon('bell-ring', 13)} على شاشة الهاتف</div>
      <div class="card" style="padding:8px 12px"><b class="fs-sm">${title || 'العنوان'}</b><div class="fs-sm muted" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${body || 'نص الإشعار'}</div></div>
    </div>`;
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
      function redraw() {
        var lang = val('pv_lang') || 'ar';
        BT.render(f.querySelector('[data-pv]'), previewCard(text('title', lang), text('body', lang)));
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
        return { title: title, body: text_, audience: audience, channels: chans, scheduled_at: at ? fmt.kwIso(at) : null };
      }
      function submit(d, send) {
        if (!BT.form.validate(f)) return;
        var b = body();
        var k = b.audience.kind;
        if ((k === 'company' && !b.audience.company_ids.length) || (k === 'platform' && !b.audience.platform_ids.length) || (k === 'selected' && !b.audience.employee_ids.length)) {
          BT.toast('اختر من يصله الإشعار', { type: 'error' });
          return;
        }
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
          <div class="section-t mt-16">النص</div>
          ${LANGS.filter(function (l) { return b.title[l[0]]; }).map(function (l) { return h`<div class="highlight-box mb-8" lang="${l[0]}"><div class="fs-sm muted">${l[1]}</div><b>${b.title[l[0]]}</b><div class="fs-sm" style="white-space:pre-wrap">${b.body[l[0]] || ''}</div></div>`; })}</div>`,
        buttons: btns
      });
    }, api.fail);
  }
})();
