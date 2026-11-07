/* =====================================================================
   app/pages/driver-status.js — حالة السائقين: لكل سائق حالات منفصلة (الدوام، السيارة، التتبع الفعلي) وتنبيهاته معاً،
   وطلبات التواصل من الإدارة (مفتوح ← اطّلع السائق ← أُغلق)، وقوالب الحالة التي تعرضها بطاقات التطبيق (معاينة، نشر
   بإصدار جديد، رجوع للإعداد السابق). المعاينة يرسمها الخادم بالقواعد نفسها التي يرسم بها التطبيق.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  var SHIFT = { working: ['في العمل', 'g'], off_duty: ['خارج الدوام', 'n'] };
  var VEHICLE = { available: ['متاحة', 'g'], maintenance: ['في الصيانة', 'o'], breakdown: ['معطلة (حادث مفتوح)', 'r'], none: ['بلا سيارة', 'n'] };
  var TRACKING = { active: ['يُرسل', 'g'], stale: ['لا يصل', 'r'], off: ['متوقف', 'n'] };
  var CODES = {
    shift_working: 'في العمل', shift_off: 'خارج الدوام', shift_ended: 'خارج الدوام: أنهيت يومك', vehicle_maintenance: 'السيارة في الصيانة', vehicle_breakdown: 'السيارة معطلة',
    custody_settlement: 'تسوية العهدة النقدية', contact_request: 'طلب تواصل', document_missing: 'مستند ناقص أو منتهٍ', location_problem: 'مشكلة في الموقع'
  };
  var KINDS = { shift_working: 'دوام: في العمل', shift_off: 'دوام: خارج الدوام', vehicle_maintenance: 'سيارة: صيانة', custody: 'عهدة نقدية', contact: 'تواصل', location: 'الموقع', generic: 'عام' };
  var ICONS = { work: 'car', off: 'moon', car: 'car', wrench: 'wrench', breakdown: 'shield-alert', wallet: 'wallet', phone: 'phone', location: 'signal', location_off: 'map-pin-off', document: 'file-warning', warning: 'triangle-alert', info: 'info', check: 'circle-check', clock: 'clock' };
  var ACTIONS = { open_cash: 'فتح الكاش', open_custody: 'فتح سيارتي', open_contact: 'تفاصيل التواصل', call_supervisor: 'اتصل بالمشرف', open_location_settings: 'فحص الإعدادات', open_maintenance: 'فتح الصيانة', open_documents: 'فتح مستنداتي', acknowledge: 'تم' };
  var VISIBILITY = { always: 'دائماً', working: 'في الدوام فقط', off_duty: 'خارج الدوام فقط', has_vehicle: 'عندما تكون معه سيارة' };
  var REASONS = { permission_denied: 'إذن الموقع ليس «دائماً»', gps_off: 'GPS مغلق', service_stopped: 'خدمة التتبع متوقفة', stale: 'لم يصل موقع خلال مدة الانقطاع' };
  var CONTACT = { open: ['مفتوح', 'o'], acknowledged: ['اطّلع السائق', 'g'], closed: ['مغلق', 'n'] };

  function pill(map, k) { var x = map[k] || [k, 'n']; return BT.pill(x[0], x[1]); }

  BT.pages['driver-status'] = function (p, q) {
    A.setTitle('حالة السائقين');
    var v = A.view();
    var tabs = [];
    if (api.can('tracking.live')) tabs.push(['status', 'الحالة الآن'], ['contacts', 'طلبات التواصل']);
    if (api.can('settings.view')) tabs.push(['templates', 'قوالب الحالة']);
    var tab = tabs.some(function (t) { return t[0] === q.tab; }) ? q.tab : tabs[0][0];
    BT.render(v, h`${A.head('حالة السائقين', 'لكل سائق حالات منفصلة: الدوام، السيارة، والتتبع كما يصل فعلاً من هاتفه (لا كما يقول إشعار الهاتف)، وتنبيهاته معاً. القوالب تحدد ما تقوله بطاقات التطبيق وشكلها', '')}
      ${BT.tabs('dst', tabs, tab, 'tabs-line')}
      ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="dst" class="${t[0] === tab ? 'active' : ''}"><div id="dst-${t[0]}"></div></div>`; })}`);
    var drawn = {};
    A._dst = [];
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      var el = document.getElementById('dst-' + t);
      if (t === 'status') statusPanel(el);
      if (t === 'contacts') contactsPanel(el);
      if (t === 'templates') templatesPanel(el);
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/driver-status?tab=' + e.detail); });
    show(tab);
    // the live stream: a contact request answered, a template published -> redrawn at once
    if (api.can('tracking.live') && window.EventSource) {
      var es = new EventSource(api.url('/tracking/live/stream'));
      es.addEventListener('driver_status', function () { if (A._dst) A._dst.forEach(function (f) { f(); }); });
      A.onLeave(function () { es.close(); A._dst = null; });
    }
  };

  function onChange(f) { (A._dst = A._dst || []).push(f); }

  /* ---------- الحالة الآن ---------- */
  function alertsCell(r) {
    if (!r.alerts.length) return h`<span class="muted fs-sm">لا شيء</span>`;
    return h`<div class="flex gap-4" style="flex-wrap:wrap">${r.alerts.map(function (a) {
      var extra = a.code === 'location_problem' && a.data.reasons ? ' — ' + a.data.reasons.map(function (x) { return REASONS[x] || x; }).join('، ') : '';
      return h`<span class="pill ${a.priority >= 80 ? 'r' : a.priority >= 50 ? 'o' : 'b'}" title="${a.title + (a.subtitle ? ' · ' + a.subtitle : '') + extra}" data-alert-code="${a.code}">${CODES[a.code] || a.code}</span>`;
    })}</div>`;
  }
  function statusPanel(el) {
    BT.render(el, h`<div class="card"><div id="dst-table"></div></div>`);
    var rows = [];
    var t = BT.table(document.getElementById('dst-table'), {
      key: 'driver-status',
      rows: function () { return rows; },
      search: { placeholder: 'اسم السائق أو اللوحة…', text: function (r) { return api.name(r.driver.name) + ' ' + (r.vehicle.plate_number || ''); } },
      columns: [
        { key: 'driver', label: 'السائق', fixed: true, render: function (r) { return h`<bdi>${api.name(r.driver.name)}</bdi><span class="sub">${api.company(r.company_id)}</span>`; } },
        { key: 'shift', label: 'الدوام', render: function (r) { return h`${pill(SHIFT, r.shift.state)}${r.shift.started_at ? h`<span class="sub">منذ ${fmt.time(r.shift.started_at)} (${r.shift.duration})</span>` : ''}`; } },
        { key: 'vehicle', label: 'السيارة', render: function (r) { return h`${pill(VEHICLE, r.vehicle.state)}${r.vehicle.plate_number ? h` <span class="plate">${r.vehicle.plate_number}</span>` : ''}${r.vehicle.stage ? h`<span class="sub">${r.vehicle.center || ''} · ${r.vehicle.stage}</span>` : ''}`; } },
        { key: 'tracking', label: 'التتبع الفعلي', render: function (r) { return h`<span data-tracking="${r.tracking.state}">${pill(TRACKING, r.tracking.state)}</span>${r.tracking.last_update ? h`<span class="sub">آخر موقع ${fmt.since(r.tracking.last_update)}</span>` : ''}`; } },
        { key: 'alerts', label: 'التنبيهات', render: alertsCell },
        { key: 'act', label: '', render: function (r) { return h`<button type="button" class="btn btn-sm btn-outline" data-contact="${r.driver.id}">${icon('phone', 13)} طلب تواصل</button>`; } }
      ],
      empty: { icon: 'users', title: 'لا يوجد سائقون بعهدة الآن' }
    });
    function load() { return api.get('/driver-status').then(function (r) { rows = r; t.refresh(); }, function (err) { BT.render(el, A.errorBox(err)); }); }
    BT.on(el, 'click', '[data-contact]', function (e, b) {
      var r = rows.find(function (x) { return x.driver.id === b.getAttribute('data-contact'); });
      askContact(r.driver, load);
    });
    load();
    onChange(load);
    var poll = setInterval(function () { if (!document.hidden && document.contains(el)) load(); }, 30000);
    A.onLeave(function () { clearInterval(poll); });
  }

  function askContact(driver, after) {
    A.formModal({
      title: 'طلب تواصل', subtitle: api.name(driver.name), icon: 'phone', size: 'sm',
      body: h`<div class="form">${BT.f.textarea({ name: 'message', label: 'الرسالة', required: true, rows: 2, placeholder: 'مثال: اتصل بي عند وصولك', maxlength: 300 })}
        ${BT.f.input({ name: 'reason', label: 'السبب', optional: true, maxlength: 120 })}
        <div class="hint">يظهر في تطبيق السائق مع زر «اتصل» (برقم جوالك المسجل إن وجد) وزر «تم»</div></div>`,
      submitText: 'إرسال',
      submit: function (x) { return api.post('/driver-status/contact-requests', { driver_id: driver.id, message: x.message, reason: x.reason || null }); },
      done: 'أُرسل طلب التواصل',
      after: after
    });
  }

  /* ---------- طلبات التواصل ---------- */
  function contactsPanel(el) {
    BT.render(el, h`<div class="card"><div id="dst-contacts"></div></div>`);
    var t = BT.table(document.getElementById('dst-contacts'), {
      key: 'contact-requests',
      fetch: function (s) { return api.get('/driver-status/contact-requests', { status: s.chip || 'active' }); },
      chips: { value: 'active', all: false, options: [{ v: 'active', t: 'المفتوحة والمطّلع عليها' }, { v: 'open', t: 'لم يطّلع عليها' }, { v: 'acknowledged', t: 'اطّلع السائق' }, { v: 'closed', t: 'مغلقة' }, { v: 'all', t: 'الكل' }] },
      columns: [
        { key: 'driver', label: 'السائق', fixed: true, render: function (r) { return h`<bdi>${api.name(r.driver && r.driver.name)}</bdi>`; } },
        { key: 'message', label: 'الرسالة', render: function (r) { return h`${r.message}${r.reason ? h`<span class="sub">${r.reason}</span>` : ''}`; } },
        { key: 'status', label: 'الحالة', render: function (r) { return h`<span data-contact-status="${r.status}">${pill(CONTACT, r.status)}</span>${r.acknowledged_at ? h`<span class="sub">اطّلع ${fmt.since(r.acknowledged_at)}</span>` : ''}`; } },
        { key: 'created', label: 'أُرسل', render: function (r) { return h`<span class="num">${fmt.dt(r.created_at)}</span><span class="sub">${r.created_by ? r.created_by.name : ''}</span>`; } },
        { key: 'act', label: '', render: function (r) { return r.status === 'closed' ? '' : h`<button type="button" class="btn btn-sm btn-outline" data-close="${r.id}">${icon('circle-check', 13)} إغلاق</button>`; } }
      ],
      empty: { icon: 'phone', title: 'لا توجد طلبات تواصل هنا' }
    });
    BT.on(el, 'click', '[data-close]', function (e, b) {
      b.disabled = true;
      api.post('/driver-status/contact-requests/' + b.getAttribute('data-close') + '/close').then(function () { BT.toast('أُغلق الطلب'); t.refresh(); }, function (err) { b.disabled = false; BT.toast(api.message(err), { type: 'error' }); });
    });
    onChange(function () { t.refresh(); });
  }

  /* ---------- قوالب الحالة ---------- */
  function cardHtml(c) {
    return h`<div class="dst-card" data-preview style="border-inline-start:4px solid ${c.color};background:${c.color}14;border-radius:12px;padding:12px 14px">
      <div class="flex gap-8"><span style="color:${c.color}">${icon(ICONS[c.icon] || 'info', 20)}</span><div class="flex-1"><b data-preview-title>${c.title}</b>${c.subtitle ? h`<div class="fs-sm" data-preview-subtitle>${c.subtitle}</div>` : ''}</div></div>
      ${c.actions.length ? h`<div class="flex gap-8 mt-8" style="flex-wrap:wrap">${c.actions.map(function (a, i) { return h`<span class="btn btn-sm ${i ? 'btn-outline' : 'btn-primary'}" style="${i ? '' : 'background:' + c.color + ';border-color:' + c.color}">${ACTIONS[a] || a}</span>`; })}</div>` : ''}
    </div>`;
  }

  function templatesPanel(el) {
    var data = null, manage = api.can('settings.update');
    function load() {
      return api.get('/driver-status/templates').then(function (d) { data = d; draw(); }, function (err) { BT.render(el, A.errorBox(err)); });
    }
    function draw() {
      BT.render(el, h`<div class="card mb-16"><div class="card-h"><div class="card-t">${icon('layout-grid', 16)} القوالب المنشورة</div>
          <span class="ms-auto fs-sm">الإصدار <b class="num" data-config-version>${data.config_version}</b></span>
          ${manage ? h`<button type="button" class="btn btn-sm btn-outline" data-rollback ${data.can_rollback ? '' : 'disabled'}>${icon('rotate-ccw', 13)} رجوع للإعداد السابق</button>` : ''}</div>
        <div class="list">${data.templates.map(function (t) {
          return h`<div class="li" data-template="${t.code}"><span class="sdot ${t.active ? 'g' : 'n'}" style="margin-top:6px"></span><div class="li-main"><div class="li-t">${CODES[t.code] || t.code} <span class="muted fs-sm">· ${KINDS[t.kind] || t.kind} · أولوية ${t.priority}</span></div><div class="li-d" data-template-title>${api.name(t.title)}</div></div>
            <button type="button" class="btn btn-sm btn-outline" data-edit="${t.code}">${icon(manage ? 'pencil' : 'eye', 13)} ${manage ? 'تعديل' : 'عرض'}</button></div>`;
        })}</div></div>
        <div class="card"><div class="card-h"><div class="card-t">${icon('history', 16)} سجل النشر</div></div>
          ${data.history.length ? h`<div class="list">${data.history.map(function (x) { return h`<div class="li"><div class="li-main"><div class="li-t">الإصدار <b class="num">${x.version}</b> · ${x.restored_from != null ? 'رجوع إلى الإصدار ' + x.restored_from : (x.changed === 'import' ? 'استيراد إعدادات من ملف' : 'نشر «' + (CODES[x.changed] || x.changed) + '»')}</div><div class="li-d">${fmt.dt(x.created_at)} · ${x.created_by ? x.created_by.name : '—'}</div></div></div>`; })}</div>` : h`<div class="card-b muted fs-sm">لم يُنشر شيء بعد: يعمل التطبيق بالقوالب المدمجة (الإصدار 0)</div>`}</div>`);
    }
    BT.on(el, 'click', '[data-edit]', function (e, b) { edit(data.templates.find(function (t) { return t.code === b.getAttribute('data-edit'); })); });
    BT.on(el, 'click', '[data-rollback]', function () {
      A.confirmRun({ title: 'رجوع للإعداد السابق', message: 'تُنشر القوالب كما كانت قبل آخر نشر، بإصدار جديد. يأخذها التطبيق مع أول تحديث للحالة.', confirmText: 'رجوع', tone: 'warning',
        run: function () { return api.post('/driver-status/templates/rollback', { config_version: data.config_version }); },
        done: 'أُعيد الإعداد السابق', after: function (d) { if (d) { data = d; draw(); } } });
    });
    function edit(t) {
      var o = data.options;
      var text = function (name, label, val, req) {
        return h`<div class="grid-2">${BT.f.input({ name: name + '_ar', label: label + ' (عربي)', value: val.ar, required: req, maxlength: 120 })}${BT.f.input({ name: name + '_en', label: label + ' (English)', value: val.en, required: req, maxlength: 120 })}</div>`;
      };
      var body = h`<div class="form" data-template-form>
        ${text('name', 'الاسم', t.name, true)}
        <div class="grid-2">${BT.f.select({ name: 'kind', label: 'نوع البطاقة', value: t.kind, placeholder: false, options: o.kinds.map(function (k) { return { v: k, t: KINDS[k] || k }; }) })}
          ${BT.f.select({ name: 'icon', label: 'الأيقونة', value: t.icon, placeholder: false, options: o.icons.map(function (k) { return { v: k, t: k }; }) })}</div>
        <div class="grid-2">${BT.f.input({ name: 'color', label: 'اللون (#RRGGBB)', value: t.color, required: true, maxlength: 7, hint: 'من اللوحة: ' + o.palette.join(' ') })}
          ${BT.f.input({ name: 'priority', label: 'الأولوية (0–100)', type: 'number', value: t.priority, required: true })}</div>
        ${text('title', 'العنوان', t.title, true)}
        ${text('subtitle', 'السطر الثاني', t.subtitle, false)}
        <div class="hint">المتغيرات المسموحة: ${o.variables.map(function (x) { return '{' + x + '}'; }).join(' ')} — أي متغير آخر يُرفض عند الحفظ</div>
        <div class="grid-2">${BT.f.select({ name: 'visibility', label: 'شرط الظهور', value: t.visibility, placeholder: false, options: o.visibility.map(function (k) { return { v: k, t: VISIBILITY[k] || k }; }) })}
          ${BT.f.input({ name: 'ttl_minutes', label: 'مدة الصلاحية بالدقائق', type: 'number', value: t.ttl_minutes == null ? '' : t.ttl_minutes, optional: true })}</div>
        <div class="grid-2">${BT.f.select({ name: 'audience', label: 'الجمهور', value: t.audience, placeholder: false, options: [{ v: 'all', t: 'كل السائقين' }, { v: 'company', t: 'شركات محددة' }] })}
          <div class="field"><label>الشركات (للجمهور «شركات محددة»)</label><div class="flex gap-8" style="flex-wrap:wrap">${api.companyOptions().map(function (c) { return BT.f.check({ name: 'company_ids', value: c.v, label: c.t, checked: t.company_ids.indexOf(c.v) > -1 }); })}</div></div></div>
        <div class="field"><label>الأزرار (حتى ${o.max_actions})</label><div class="flex gap-8" style="flex-wrap:wrap">${o.actions.map(function (a) { return BT.f.check({ name: 'actions', value: a, label: ACTIONS[a] || a, checked: t.actions.indexOf(a) > -1 }); })}</div></div>
        ${BT.f.check({ name: 'active', label: 'مفعّل', checked: t.active })}
        <div class="section-t mt-12">المعاينة (بقيم تجريبية، كما يرسمها التطبيق)</div>
        <div data-preview-box></div>
      </div>`;
      function read(form) {
        var val = function (n) { var x = form.querySelector('[name="' + n + '"]'); return x ? x.value.trim() : ''; };
        var checked = function (n) { return BT.$$('input[name="' + n + '"]:checked', form).map(function (x) { return x.value; }); };
        return {
          kind: val('kind'), icon: val('icon'), color: val('color'),
          name: { ar: val('name_ar'), en: val('name_en') }, title: { ar: val('title_ar'), en: val('title_en') }, subtitle: { ar: val('subtitle_ar'), en: val('subtitle_en') },
          priority: parseInt(val('priority'), 10), visibility: val('visibility'),
          ttl_minutes: val('ttl_minutes') === '' ? null : parseInt(val('ttl_minutes'), 10),
          audience: val('audience'), company_ids: checked('company_ids').map(Number), actions: checked('actions'),
          active: !!form.querySelector('input[name="active"]:checked')
        };
      }
      var dlg = BT.modal.open({
        title: (manage ? 'تعديل قالب: ' : 'قالب: ') + (CODES[t.code] || t.code), icon: 'layout-grid', size: 'lg', form: manage, body: body,
        buttons: manage ? [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'نشر', cls: 'btn-primary', submit: true }] : [{ label: 'إغلاق', cls: 'btn-secondary' }],
        onOpen: function (d) {
          var form = d.body.querySelector('[data-template-form]'), box = d.body.querySelector('[data-preview-box]');
          var preview = BT.debounce(function () {
            var x = read(form);
            if (isNaN(x.priority) || !/^#[0-9A-Fa-f]{6}$/.test(x.color)) { BT.render(box, h`<div class="t-danger fs-sm" data-preview-error>اللون بصيغة ‎#RRGGBB والأولوية رقم</div>`); return; }
            api.post('/driver-status/templates/preview', { code: t.code, template: read(form), lang: 'ar' }).then(function (c) { BT.render(box, cardHtml(c)); }, function (err) { BT.render(box, h`<div class="t-danger fs-sm" data-preview-error>${api.message(err)}</div>`); });
          }, 250);
          form.addEventListener('input', preview);
          form.addEventListener('change', preview);
          preview();
        },
        onSubmit: function (vals, d) {
          var form = d.body.querySelector('[data-template-form]');
          return api.put('/driver-status/templates/' + t.code, { template: read(form), config_version: data.config_version }).then(function (res) {
            data = res; draw(); BT.toast('نُشر الإصدار ' + res.config_version); return true;
          }).catch(api.fail);
        }
      });
      return dlg;
    }
    load();
    onChange(function () { if (document.contains(el)) load(); });
  }
})();
