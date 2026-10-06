/* =====================================================================
   app/pages/people.js — الموظفون والسائقون
   القائمة والملف والمستندات، الهاتف ورابط التفعيل، تغيير الحالة،
   مراجعة التسجيل الذاتي، وطابور الروابط الجماعية.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;
  var statuses = null, docTypes = null;

  function loadStatuses() { return statuses ? Promise.resolve(statuses) : api.get('/employment-statuses').then(function (s) { statuses = s; return s; }); }
  function loadDocTypes() { return docTypes ? Promise.resolve(docTypes) : api.get('/document-types').then(function (t) { docTypes = t; return t; }); }
  function docTypeName(code) { var t = (docTypes || []).find(function (x) { return x.code === code; }); return t ? api.name(t.name) : code; }
  A.docTypes = loadDocTypes;
  A.docTypeName = docTypeName;
  A.statuses = loadStatuses;
  /* 8 أرقام كويتية أو رقم دولي يبدأ بـ + */
  A.phoneE164 = function (v) {
    v = String(v || '').replace(/[\s-]/g, '');
    if (!v) return null;
    if (/^00/.test(v)) v = '+' + v.slice(2);
    if (/^\d{8}$/.test(v)) v = '+965' + v;
    return v;
  };
  BT.validators.phone = function (v) { return /^\+[1-9]\d{7,14}$/.test(A.phoneE164(v) || '') ? '' : '8 أرقام كويتية، أو رقم دولي يبدأ بـ +'; };
  A.phoneShow = function (p) { return p ? h`<bdi dir="ltr" class="num">${p}</bdi>` : raw('<span class="muted">—</span>'); };

  /* ================= الصفحة ================= */
  /* كيف يدخل السائقون: الهاتف ورمز واتساب، أو (false) الرقم المدني وكلمة مرور فقط (إعدادات: دخول السائق للتطبيق) */
  A.phoneCodes = function () {
    if (!A._codes) A._codes = api.get('/driver/app-config').then(function (r) { A.codes = r.phone_codes; return r.phone_codes; }, function () { A._codes = null; return true; });
    return A._codes;
  };

  BT.pages['employees'] = function (p, q) {
    A.phoneCodes();
    A.setTitle('الموظفون والسائقون');
    var v = A.view(), tab = q.tab || 'list';
    var tabs = [['list', 'الموظفون']];
    if (api.can('documents.view')) tabs.push(['docs', 'مستندات تنتهي قريباً']);
    if (api.can('employees.onboarding')) tabs.push(['reg', 'طلبات التسجيل', A.counts.onboarding || null]);
    if (api.can('devices.manage')) tabs.push(['queue', 'طابور روابط التفعيل']);
    var actions = h`${api.can('devices.manage') ? A.btn('روابط تفعيل جماعية', { icon: 'send', cls: 'btn-outline', action: 'links-bulk' }) : ''}${api.can('employees.create') ? A.btn('إضافة موظف', { icon: 'user-plus', cls: 'btn-primary', action: 'employee-new' }) : ''}`;
    BT.render(v, h`${A.head('ملف لكل موظف وسائق', 'البيانات والمستندات والهاتف المربوط والحالة الوظيفية', actions)}
      ${BT.tabs('emp', tabs, tab, 'tabs-line')}
      <div data-panel="list" data-group="emp" class="${tab === 'list' ? 'active' : ''}"><div class="card"><div id="emp-table"></div></div></div>
      <div data-panel="docs" data-group="emp" class="${tab === 'docs' ? 'active' : ''}"><div id="doc-panel"></div></div>
      <div data-panel="reg" data-group="emp" class="${tab === 'reg' ? 'active' : ''}"><div class="banner info fs-sm mb-12">${icon('info', 15)}<div>ما يرسله السائق من التطبيق بعد رابط التفعيل. لا يدخل شيء في السجلات قبل الاعتماد، والاعتماد يسجّل البيانات والمستندات والعهدة معاً أو لا شيء.</div></div><div class="card"><div id="reg-table"></div></div></div>
      <div data-panel="queue" data-group="emp" class="${tab === 'queue' ? 'active' : ''}"><div id="queue-panel"></div></div>`);

    var drawn = {};
    function show(t) {
      if (drawn[t]) return;
      drawn[t] = true;
      if (t === 'list') listTable();
      if (t === 'docs') docsPanel(document.getElementById('doc-panel'));
      if (t === 'reg') regTable();
      if (t === 'queue') queuePanel(document.getElementById('queue-panel'));
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/employees?tab=' + e.detail); });
    show(tab);
  };

  function listTable() {
    var el = document.getElementById('emp-table');
    loadStatuses().then(null, function () { return []; }).then(function () {
      var filters = { status: '', company: '' };
      var tools = h`<select class="select" data-f="status" aria-label="الحالة"><option value="">كل الحالات</option>${(statuses || []).map(function (s) { return h`<option value="${s.code}">${api.name(s.name)}</option>`; })}</select>
        ${api.companies.length > 1 ? h`<select class="select" data-f="company" aria-label="الشركة"><option value="">كل الشركات</option>${api.companyOptions().map(function (c) { return h`<option value="${c.v}">${c.t}</option>`; })}</select>` : ''}`;
      var t = BT.table(el, {
        fetch: function (s) {
          return api.get('/employees', { q: s.q, is_driver: { 'true': true, 'false': false, no_phone: true }[s.chip], no_phone: s.chip === 'no_phone' || null, status_code: filters.status, company_id: filters.company, limit: s.limit, offset: s.offset });
        },
        search: { placeholder: 'الاسم أو الرقم الوظيفي أو الجوال أو رقم المنصة…' },
        chips: { options: [{ v: 'true', t: 'السائقون' }, { v: 'false', t: 'الإداريون' }, { v: 'no_phone', t: 'سائقون بلا هاتف' }] },
        tools: tools,
        selectable: api.can('devices.manage') || api.can('payroll.schemes'),
        bulk: [
          api.can('devices.manage') ? { label: 'إرسال رابط التفعيل على واتساب', icon: 'send', cls: 'btn-primary', run: function (rows, clear) { A.bulkLinks(rows.filter(function (r) { return r.is_driver; }), clear); } } : null,
          api.can('devices.manage') ? { label: 'الدخول بالرقم المدني', icon: 'key-round', cls: 'btn-outline', run: function (rows, clear) { A.claimForm(rows.filter(function (r) { return r.is_driver; }), clear); } } : null,
          api.can('payroll.schemes') ? { label: 'نظام الدفع', icon: 'banknote', cls: 'btn-outline', run: function (rows, clear) { A.assignScheme(rows, clear); } } : null
        ].filter(Boolean),
        columns: [
          { key: 'name', label: 'الموظف', render: function (e) { return BT.person(api.name(e.name), e.employee_number + (e.job_title ? ' · ' + e.job_title : '')); } },
          { key: 'company', label: 'الشركة / الفرع', render: function (e) { return h`${api.company(e.company_id)}<span class="sub">${api.branch(e.branch_id)}</span>`; } },
          { key: 'phone', label: 'الجوال', render: function (e) { return A.phoneShow(e.phone); } },
          { key: 'status', label: 'الحالة', render: function (e) { return BT.pill(api.name(e.status_name), e.is_terminal ? 'n' : e.status_code === 'active' ? 'g' : 'o'); } },
          { key: 'app', label: 'التطبيق', render: function (e) { return e.is_driver ? A.pill('app_access', e.app_access) : raw('<span class="muted">—</span>'); } }
        ],
        rowClick: function (e) { A.employee(e.id); },
        empty: { icon: 'users', title: 'لا يوجد موظفون مطابقون', text: 'أضف موظفاً أو استورد ملف Excel من صفحة الاستيراد' }
      });
      A.refreshEmployees = t.refresh;
      BT.on(el, 'change', '[data-f]', function (e, s) { filters[s.getAttribute('data-f')] = s.value; t.refresh(); });
    });
  }

  /* ---------- المستندات التي تنتهي ---------- */
  function docsPanel(el) {
    var days = 30;
    function draw() {
      A.load(el, Promise.all([api.get('/documents/expiring', { within_days: days }), loadDocTypes()]), function (res) {
        var docs = res[0];
        setTimeout(function () {
          var tbl = el.querySelector('[data-docs]');
          if (!tbl) return;
          BT.table(tbl, {
            rows: docs, pageSize: 25,
            search: { placeholder: 'اسم الموظف أو اللوحة أو المستند…', text: function (d) { return api.name(d.owner_name) + ' ' + docTypeName(d.type_code) + ' ' + (d.number || ''); } },
            chips: { key: 'owner_type', options: [{ v: 'employee', t: 'موظفون' }, { v: 'vehicle', t: 'سيارات' }, { v: 'company', t: 'شركات' }] },
            columns: [
              { key: 'owner', label: 'صاحب المستند', sort: function (d) { return api.name(d.owner_name); }, render: function (d) { return d.owner_type === 'vehicle' ? A.plate(d.owner_name, d.owner_id) : d.owner_type === 'employee' ? BT.person(api.name(d.owner_name) || '—') : h`${icon('building-2', 14)} ${api.name(d.owner_name)}`; } },
              { key: 'type_code', label: 'المستند', render: function (d) { return h`${docTypeName(d.type_code)}${d.number ? h`<span class="sub num">${d.number}</span>` : ''}`; } },
              { key: 'expiry_date', label: 'ينتهي', render: function (d) { return h`<span class="num">${fmt.date(d.expiry_date)}</span>`; } },
              { key: 'left', label: '', sort: function (d) { return BT.date.daysLeft(d.expiry_date); }, render: function (d) { var n = BT.date.daysLeft(d.expiry_date); return BT.pill(fmt.daysLabel(n), n < 0 ? 'r' : n <= 15 ? 'o' : 'b'); } }
            ],
            rowClick: function (d) { if (d.owner_type === 'employee') A.employee(d.owner_id, 'docs'); else if (d.owner_type === 'vehicle') A.go('vehicles/' + d.owner_id); },
            empty: { icon: 'circle-check', title: 'لا توجد مستندات تنتهي خلال ' + days + ' يوماً' }
          });
        });
        return h`<div class="card"><div class="card-h"><h3>${BT.fmt.int(docs.length)} مستند ينتهي أو انتهى</h3><select class="select ms-auto" data-days style="width:auto">${[15, 30, 60, 90, 180].map(function (n) { return h`<option value="${n}"${n === days ? raw(' selected') : ''}>خلال ${n} يوماً</option>`; })}</select></div><div data-docs></div></div>`;
      }).catch(function () {});
    }
    BT.on(el, 'change', '[data-days]', function (e, s) { days = +s.value; draw(); });
    draw();
  }

  /* ================= ملف الموظف ================= */
  A.employee = function (id, tab) {
    var dlg = BT.drawer.open({ title: 'ملف الموظف', icon: 'user-round', size: 'lg', body: A.spinner(), buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }] });
    var jobs = [api.get('/employees/' + id), loadStatuses(), loadDocTypes()];
    jobs.push(api.get('/employees/' + id + '/status-history').catch(function () { return []; }));
    jobs.push(api.can('documents.view') ? api.get('/documents', { owner_type: 'employee', owner_id: id }) : Promise.resolve(null));
    jobs.push(api.can('devices.manage') ? api.get('/employees/' + id + '/devices') : Promise.resolve(null));
    jobs.push(api.can('custody.view') ? api.get('/custodies', { driver_id: id, limit: 10 }) : Promise.resolve(null));
    Promise.all(jobs.concat([A.platforms ? A.platforms().catch(function () { return []; }) : [], A.phoneCodes()])).then(function (r) {
      r = r.slice(0, 7);
      // كشف الكاش للسائقين فقط
      return r[0].is_driver && api.can('cash.view') ? api.get('/cash/drivers/' + id + '/statement').then(function (c) { return r.concat([c]); }, function () { return r.concat([null]); }) : r.concat([null]);
    }).then(function (r) {
      var e = r[0], history = r[3], docs = r[4], devices = r[5], custodies = r[6], cash = r[7];
      var title = api.name(e.name);
      dlg.panel.querySelector('.modal-h h3').textContent = title;
      var st = (statuses || []).find(function (s) { return s.code === e.status_code; });
      var openCustody = (custodies || []).find(function (c) { return !c.ended_at; });
      var tabs = [['info', 'البيانات']];
      if (docs) tabs.push(['docs', 'المستندات', docs.length || null]);
      if (e.is_driver) tabs.push(['device', 'التطبيق والهاتف']);
      if (custodies && e.is_driver) tabs.push(['custody', 'العُهد']);
      tabs.push(['log', 'سجل الحالة']);
      var active = tab && tabs.some(function (t) { return t[0] === tab; }) ? tab : 'info';
      dlg.setBody(h`<div class="flex items-center gap-12 mb-16">${BT.avatar(title, 'xl')}<div class="flex-1"><div class="flex gap-8 items-center" style="flex-wrap:wrap">${BT.pill(api.name(e.status_name), e.is_terminal ? 'n' : e.status_code === 'active' ? 'g' : 'o', true)}${e.is_driver ? A.pill('app_access', e.app_access) : ''}${openCustody ? BT.pill('العهدة: ' + openCustody.vehicle.plate_number, 'b') : ''}</div><div class="muted fs-sm mt-4"><span class="num">${e.employee_number}</span> · ${api.company(e.company_id)} · ${api.branch(e.branch_id)}</div></div></div>
        ${BT.tabs('empd', tabs, active, 'tabs-line')}
        <div class="mt-16">
          <div data-panel="info" data-group="empd" class="${active === 'info' ? 'active' : ''}">${BT.kv([
            ['الاسم بالعربية', e.name.ar || '—'], ['الاسم بالإنجليزية', h`<bdi>${e.name.en || '—'}</bdi>`],
            ['الجوال', A.phoneShow(e.phone)], ['الرقم المدني', e.civil_id ? h`<span class="num">${e.civil_id}</span>` : '—'],
            ['الجنسية', e.nationality || '—'], ['القسم / الوظيفة', [e.department, e.job_title].filter(Boolean).join(' · ') || '—'],
            ['تاريخ الالتحاق', e.hire_date ? h`<span class="num">${fmt.date(e.hire_date)}</span>` : '—'],
            ['سائق', e.is_driver ? 'نعم' : 'لا'],
            ['الراتب الأساسي', e.basic_salary != null ? BT.amt(Number(e.basic_salary)) : raw('<span class="muted">محجوب (صلاحية الرواتب)</span>')],
            ['IBAN', e.iban ? h`<span class="num ltr">${e.iban}</span>` : '—'],
            e.bank_name || e.payment_method ? ['البنك / طريقة الدفع', [e.bank_name, e.payment_method ? api.t('payment_method', e.payment_method) : null].filter(Boolean).join(' · ')] : null,
            e.platform_id ? ['المنصة', h`${A.platformName(A._platList, e.platform_id)}${e.platform_driver_id ? h` · <span class="num ltr">${e.platform_driver_id}</span>` : ''}`] : null,
            cash ? ['رصيد الكاش', h`${BT.amt(Number(cash.total))}${Number(cash.pending) ? h` <span class="muted fs-sm">(منه غير معتمد ${fmt.money(cash.pending)})</span>` : ''}`] : null
          ].filter(Boolean))}${e.is_driver && api.can('payroll.view') ? h`<div data-scheme-box></div>` : ''}</div>
          ${docs ? h`<div data-panel="docs" data-group="empd" class="${active === 'docs' ? 'active' : ''}">${docsList(docs, 'employee', e.id)}</div>` : ''}
          ${e.is_driver ? h`<div data-panel="device" data-group="empd" class="${active === 'device' ? 'active' : ''}">${devicePanel(e, devices)}</div>` : ''}
          ${custodies && e.is_driver ? h`<div data-panel="custody" data-group="empd" class="${active === 'custody' ? 'active' : ''}">${custodies.length ? h`<div class="list">${custodies.map(function (c) { return h`<button type="button" class="li" data-custody="${c.id}" style="width:100%;text-align:start"><span class="li-ic">${icon('key-round', 16)}</span><div class="li-main"><div class="li-t"><span class="plate">${c.vehicle.plate_number}</span> ${c.kind === 'emergency' ? A.pill('custody_kind', 'emergency') : ''}</div><div class="li-d">${fmt.dt(c.started_at)} ← ${c.ended_at ? fmt.dt(c.ended_at) : 'مستمرة'}</div></div>${c.needs_review ? BT.pill('تحتاج مراجعة', 'o') : ''}</button>`; })}</div>` : BT.empty('key-round', 'لا توجد عُهد', '')}</div>` : ''}
          <div data-panel="log" data-group="empd" class="${active === 'log' ? 'active' : ''}">${history.length ? h`<div class="timeline">${history.map(function (x, i) { var s = (statuses || []).find(function (y) { return y.code === x.status_code; }); return h`<div class="tl-item"><span class="tl-ic ${i ? '' : 'g'}">${icon(i ? 'history' : 'check', 13)}</span><div><div class="tl-t">${s ? api.name(s.name) : x.status_code}</div><div class="tl-d">${fmt.dt(x.changed_at)}${x.note ? ' · ' + x.note : ''}</div></div></div>`; })}</div>` : BT.empty('history', 'لا يوجد سجل', '')}</div>
        </div>`);
      var foot = dlg.panel.querySelector('.modal-f');
      BT.render(foot, h`<span class="spacer"></span>${api.can('employees.update') && !e.is_terminal ? h`<button type="button" class="btn btn-outline" data-x="status">${icon('repeat', 15)}تغيير الحالة</button>` : ''}${api.can('employees.update') ? h`<button type="button" class="btn btn-outline" data-x="edit">${icon('pencil', 15)}تعديل</button>` : ''}<button type="button" class="btn btn-secondary" data-close>إغلاق</button>`);
      var reopen = function (t) { dlg.close(); A.employee(id, t); if (A.refreshEmployees) A.refreshEmployees(); };
      var claimBox = dlg.panel.querySelector('[data-claim]');
      if (claimBox) A.claimBox(claimBox, e, function () { reopen('device'); });
      var schemeBox = dlg.panel.querySelector('[data-scheme-box]');
      if (schemeBox && A.schemeBox) A.schemeBox(schemeBox, e, function () { reopen('info'); });
      BT.on(foot, 'click', '[data-x]', function (ev, b) {
        var x = b.getAttribute('data-x');
        if (x === 'edit') A.employeeForm(e, function () { reopen('info'); });
        if (x === 'status') A.changeStatus(e, st, function () { reopen('log'); });
      });
      BT.on(dlg.body, 'click', '[data-custody]', function (ev, b) { A.custody(b.getAttribute('data-custody')); });
      BT.on(dlg.body, 'click', '[data-doc-add]', function () { A.addDocument('employee', e.id, function () { reopen('docs'); }); });
      BT.on(dlg.body, 'click', '[data-dev]', function (ev, b) {
        var x = b.getAttribute('data-dev');
        if (x === 'link') A.activationLink(e, function () { reopen('device'); });
        else if (x === 'revoke') A.revokeDevice(b.getAttribute('data-id'), function () { reopen('device'); });
        else A.setAppAccess(e, x, function () { reopen('device'); });
      });
    }, function (err) { dlg.setBody(A.errorBox(err)); });
    return dlg;
  };

  function docsList(docs, ownerType, ownerId) {
    var list = docs.length ? h`<div class="list">${docs.map(function (d) {
      var n = d.expiry_date ? BT.date.daysLeft(d.expiry_date) : null;
      var files = [];
      if (d.has_file) files.push({ src: api.url('/documents/' + d.id + '/file'), caption: docTypeName(d.type_code) + ' · الوجه' });
      if (d.has_back_file) files.push({ src: api.url('/documents/' + d.id + '/file', { side: 'back' }), caption: docTypeName(d.type_code) + ' · الظهر' });
      return h`<div class="li" style="align-items:flex-start"><span class="li-ic ${n != null && n <= 30 ? 'o' : ''}">${icon('file-badge', 16)}</span><div class="li-main"><div class="li-t">${docTypeName(d.type_code)} ${d.number ? h`<span class="num muted fs-sm">${d.number}</span>` : ''}</div><div class="li-d">${d.expiry_date ? h`ينتهي <span class="num">${fmt.date(d.expiry_date)}</span>` : 'بلا تاريخ انتهاء'}</div>${files.length ? h`<div class="mt-8" style="max-width:260px">${A.thumbs(files)}</div>` : ''}</div>${n != null && n <= 30 ? BT.pill(fmt.daysLabel(n), n < 0 ? 'r' : n <= 15 ? 'o' : 'b') : ''}</div>`;
    })}</div>` : BT.empty('file-badge', 'لا توجد مستندات', '');
    return h`${list}${api.can('documents.manage') ? h`<div class="mt-12"><button type="button" class="btn btn-sm btn-soft" data-doc-add>${icon('file-plus', 14)} إضافة أو تجديد مستند</button></div><div class="hint mt-4">التجديد يضيف نسخة جديدة ويحفظ القديمة في السجل.</div>` : ''}`;
  }

  /* إضافة مستند (أو تجديده: النسخة الجديدة تصبح الحالية) */
  A.addDocument = function (ownerType, ownerId, after) {
    loadDocTypes().then(function (types) {
      var opts = types.filter(function (t) { return t.applies_to === ownerType; }).map(function (t) { return { v: t.code, t: api.name(t.name) }; });
      A.formModal({
        title: 'إضافة مستند', icon: 'file-plus', done: 'تم حفظ المستند', after: after,
        body: h`<div class="form-grid">${BT.f.select({ name: 'type_code', label: 'نوع المستند', required: true, options: opts, full: true })}
          ${BT.f.input({ name: 'number', label: 'الرقم', optional: true })}${BT.f.date({ name: 'expiry_date', label: 'تاريخ الانتهاء', optional: true, hint: 'مطلوب لأنواع لها انتهاء' })}
          ${BT.f.upload({ name: 'front', label: 'صورة الوجه', optional: true, accept: 'image/jpeg,image/png,application/pdf' })}${BT.f.upload({ name: 'back', label: 'صورة الظهر', optional: true, accept: 'image/jpeg,image/png,application/pdf' })}</div>`,
        submit: function (v) {
          var up = function (f) { return f && f[0] ? api.upload(f[0]).then(function (x) { return x.sha256; }) : Promise.resolve(null); };
          return Promise.all([up(v.front), up(v.back)]).then(function (shas) {
            return api.post('/documents', { owner_type: ownerType, owner_id: ownerId, type_code: v.type_code, number: v.number || null, expiry_date: v.expiry_date || null, file_sha256: shas[0], file_back_sha256: shas[1] });
          });
        }
      });
    }, api.fail).catch(function () {});
  };

  /* ---------- الهاتف والتطبيق ---------- */
  function devicePanel(e, devices) {
    var bound = (devices || []).filter(function (d) { return !d.revoked_at; });
    var canManage = api.can('devices.manage'), codes = A.codes !== false;
    var accessBtns = canManage && !e.is_terminal ? h`<div class="flex gap-8 mt-12" style="flex-wrap:wrap">
      ${e.app_access !== 'active' && (e.phone || !codes) ? h`<button type="button" class="btn btn-sm btn-soft" data-dev="active">${icon('check', 14)} تفعيل التطبيق</button>` : ''}
      ${e.app_access === 'active' ? h`<button type="button" class="btn btn-sm btn-outline" data-dev="suspended">${icon('pause', 14)} إيقاف مؤقت</button>` : ''}
      ${e.app_access !== 'disabled' && e.app_access !== 'none' ? h`<button type="button" class="btn btn-sm btn-danger" data-dev="disabled">${icon('ban', 14)} إلغاء الوصول</button>` : ''}</div>` : '';
    return h`${BT.kv([['حساب التطبيق', A.pill('app_access', e.app_access)], ['الجوال المسجل', A.phoneShow(e.phone)]])}${accessBtns}
      <div class="section-t mt-16">الهواتف</div>
      ${devices == null ? raw('<div class="muted fs-sm">عرض الأجهزة يحتاج صلاحية أجهزة السائقين</div>') : devices.length ? h`<div class="list">${devices.map(function (d) {
        return h`<div class="li"><span class="li-ic">${icon('smartphone', 16)}</span><div class="li-main"><div class="li-t">${d.model || 'هاتف'} <span class="muted fs-sm">${d.platform || ''} ${d.app_version ? '· ' + d.app_version : ''}</span></div><div class="li-d">رُبط ${fmt.dt(d.bound_at)} · آخر ظهور ${d.last_seen_at ? fmt.since(d.last_seen_at) : '—'}${d.revoked_at ? h` · فُصل ${fmt.dt(d.revoked_at)}` : ''}</div></div>${d.revoked_at ? BT.pill('مفصول', 'n') : h`${BT.pill('مربوط', 'g')}${canManage ? h`<button type="button" class="btn btn-sm btn-ghost" data-dev="revoke" data-id="${d.id}">فصل</button>` : ''}`}</div>`;
      })}</div>` : BT.empty('smartphone', 'لا يوجد هاتف مربوط', !codes ? 'يدخل السائق برقمه المدني وكلمة مروره من أي هاتف. أول مرة: كلمة مرور مبدئية من الأسفل' : e.phone ? 'أرسل رابط التفعيل: يفتحه السائق فيرتبط هاتفه دون رمز' : 'لا يوجد رقم جوال في الملف: أضفه، أو أعطِ السائق كلمة مرور مبدئية يدخل بها برقمه المدني ويسجل هاتفه')}
      ${canManage && e.app_access === 'active' ? h`<div class="mt-12"><button type="button" class="btn btn-sm btn-primary" data-dev="link">${icon('send', 14)} رابط التفعيل</button></div>
        <div class="banner info mt-12 fs-sm">${icon('shield-check', 15)}<div>${codes ? 'حساب السائق مربوط بهاتف واحد. عند تغيير الهاتف: أرسل رابطاً جديداً (يُفصل القديم تلقائياً)، أو يدخل السائق برمز يصله على واتساب الرقم المسجل.' : 'حساب السائق مربوط بهاتف واحد. عند تغيير الهاتف يدخل برقمه المدني وكلمة مروره على الهاتف الجديد (يُفصل القديم تلقائياً). نسي كلمة المرور: أعطه كلمة مرور مبدئية جديدة من الأسفل.'}</div></div>` : ''}
      ${e.app_access !== 'active' && !e.is_terminal && e.phone ? h`<div class="banner warn mt-12 fs-sm">${icon('info', 15)}<div>فعّل حساب التطبيق أولاً ليستطيع السائق الدخول أو استلام رابط التفعيل.</div></div>` : ''}
      ${canManage && (!bound.length || !codes) && !e.is_terminal ? h`<div data-claim="${e.id}"></div>` : ''}`;
  }

  /* الدخول مرة واحدة بالرقم المدني وكلمة مرور مبدئية، لسائق لا يُعرف هاتفه: يسجل هاتفه برمز واتساب ثم يكمل تسجيله */
  A.claimBox = function (box, e, after) {
    api.get('/employees/' + e.id + '/claim').then(function (c) {
      if (!document.contains(box)) return;
      var own = A.codes === false && c && c.own_password_set_at;
      BT.render(box, h`<div class="section-t mt-16">الدخول بالرقم المدني</div>
        ${c ? BT.kv([
          ['كلمة المرور المبدئية', c.used_at ? BT.pill('استُخدمت · ' + fmt.dt(c.used_at), 'g') : c.open ? (c.locked ? BT.pill('مقفلة مؤقتاً بعد محاولات خاطئة', 'r') : BT.pill('مفتوحة', 'o')) : BT.pill('انتهت', 'n')],
          c.used_at ? null : ['صالحة حتى', fmt.dt(c.expires_at)],
          c.used_phone ? ['الهاتف الذي سجّله', h`<span class="ltr num">${c.used_phone}</span>`] : null,
          own ? ['كلمة مروره', h`${c.locked ? BT.pill('مقفلة مؤقتاً بعد محاولات خاطئة', 'r') : BT.pill('اختارها ' + fmt.dt(c.own_password_set_at), 'g')}`] : null
        ].filter(Boolean)) : raw('<div class="muted fs-sm">لا توجد كلمة مرور مبدئية</div>')}
        <div class="flex gap-8 mt-8"><button type="button" class="btn btn-sm btn-outline" data-claim-set>${icon('key-round', 14)} ${own ? 'إعادة تعيين كلمة المرور' : c && c.open ? 'كلمة مرور جديدة' : 'كلمة مرور مبدئية'}</button>${c && c.open ? h`<button type="button" class="btn btn-sm btn-ghost" data-claim-revoke>إلغاؤها</button>` : ''}</div>`);
      box.querySelector('[data-claim-set]').onclick = function () { A.claimForm([e], after); };
      var rv = box.querySelector('[data-claim-revoke]');
      if (rv) rv.onclick = function () { A.confirmRun({ title: 'إلغاء كلمة المرور المبدئية', message: 'لا يستطيع السائق الدخول بها بعد الآن.', confirmText: 'إلغاء', tone: 'danger', done: 'أُلغيت', after: after, run: function () { return api.del('/employees/' + e.id + '/claim'); } }); };
    }, function () {});
  };
  A.claimForm = function (rows, after) {
    if (!rows.length) { BT.toast('لا يوجد سائقون في التحديد', { type: 'info' }); return; }
    var codes = A.codes !== false;
    A.formModal({
      title: 'الدخول بالرقم المدني', subtitle: rows.length === 1 ? api.name(rows[0].name) : rows.length + ' سائق', icon: 'key-round', submitText: 'حفظ', done: false,
      body: h`<div class="form">
        ${BT.f.input({ name: 'password', label: 'كلمة المرور المبدئية', required: true, pattern: '.{8,64}', msg: '8 أحرف على الأقل', hint: codes ? 'يدخل بها السائق مرة واحدة مع رقمه المدني، ثم يسجل هاتفه برمز يصله على واتساب' : 'يدخل بها السائق مرة واحدة مع رقمه المدني، ثم يختار كلمة مروره. لمن اختار كلمة مروره من قبل: تتوقف كلمته فوراً (نسيها)' })}
        ${BT.f.input({ name: 'days', label: 'صالحة لمدة (يوم)', value: 14, num: true, required: true })}
        <div class="banner warn fs-sm">${icon('shield-alert', 15)}<div>${codes ? 'كلمة مرور مشتركة يعرفها كل من أُبلغ بها، وزملاء السائق يعرفون رقمه المدني: ما يحمي الحساب هو رمز واتساب على هاتفه، والاستخدام مرة واحدة، والمدة القصيرة، ومراجعة التسجيل الذاتي قبل اعتماد بياناته (ومنها الآيبان). اجعل المدة قصيرة.' : 'كلمة مرور مشتركة يعرفها كل من أُبلغ بها، وزملاء السائق يعرفون رقمه المدني، ولا رمز واتساب يثبت الهاتف: من يسبق السائق يختار كلمة المرور ويدخل بحسابه. ما يحمي الحساب: الاستخدام مرة واحدة (السائق الحقيقي يُرفض فيبلغكم)، والمدة القصيرة، ومراجعة التسجيل الذاتي قبل اعتماد بياناته (ومنها الآيبان). اجعل المدة قصيرة وأبلغ كل سائق بنفسه.'}</div></div></div>`,
      submit: function (v) {
        return api.post('/driver-claims', { employee_ids: rows.map(function (r) { return r.id; }), password: v.password, days: Math.round(Number(v.days)) }).then(function (r) {
          BT.toast('كلمة المرور المبدئية جاهزة لـ ' + r.set + ' سائق', { sub: r.skipped.length ? r.skipped.length + ' تُخطّي: ' + r.skipped.map(function (x) { return api.name(x.employee.name) + ' (' + api.t('errors', x.code) + ')'; }).join('، ') : 'صالحة حتى ' + fmt.dt(r.expires_at), timeout: 8000 });
          return r;
        });
      },
      after: after
    });
  };

  A.setAppAccess = function (e, value, after) {
    var msg = { active: A.codes === false ? 'يستطيع السائق الدخول برقمه المدني وكلمة مروره، أو برابط التفعيل.' : 'يستطيع السائق الدخول للتطبيق برابط التفعيل أو برمز على واتساب.', suspended: 'يتوقف دخول السائق مؤقتاً وتتوقف أجهزته حتى إعادة التفعيل.', disabled: 'يُلغى وصول السائق للتطبيق وتُفصل أجهزته.' }[value];
    A.confirmRun({ title: api.t('app_access', value), message: msg, confirmText: 'تأكيد', tone: value === 'active' ? 'primary' : 'danger', icon: 'smartphone', done: 'تم التحديث', after: after,
      run: function () { return api.put('/employees/' + e.id + '/app-access', { app_access: value }); } });
  };
  A.revokeDevice = function (deviceId, after) {
    A.confirmRun({ title: 'فصل الهاتف', message: 'يُفصل الهاتف فوراً ويُطلب من السائق الدخول من جديد (' + (A.codes === false ? 'رقمه المدني وكلمة مروره، أو رابط تفعيل' : 'رابط تفعيل أو رمز على واتساب') + ').', confirmText: 'فصل', tone: 'danger', icon: 'smartphone', done: 'تم فصل الهاتف', after: after,
      run: function () { return api.post('/devices/' + deviceId + '/revoke'); } });
  };

  /* رابط تفعيل لمرة واحدة. واتساب يذهب للرقم المسجل فقط؛ "يدوي" يعرض الرابط ورمز QR للسائق في المكتب */
  A.activationLink = function (e, after) {
    var d = BT.modal.open({
      title: 'رابط تفعيل التطبيق', subtitle: api.name(e.name), icon: 'send', size: 'sm', form: true,
      body: h`<div class="form">${BT.kv([['يُرسل إلى', e.phone ? h`${A.phoneShow(e.phone)} <span class="muted fs-sm">(الرقم المسجل فقط)</span>` : raw('<span class="muted fs-sm">لا يوجد رقم في الملف: يُعرض الرابط ورمز QR ليفتحه السائق في المكتب</span>')]])}
        ${BT.f.radios({ name: 'onboarding', label: 'إكمال البيانات من التطبيق', value: '', options: [{ v: '', t: 'تلقائي', d: 'يُطلب إن لم يكتمل تسجيله' }, { v: 'true', t: 'نعم', d: 'بياناته ومستنداته وسيارته' }, { v: 'false', t: 'لا', d: 'تفعيل الهاتف فقط' }] })}
        <div class="banner info fs-sm">${icon('shield-check', 15)}<div>يفتح السائق الرابط فيرتبط هاتفه مباشرة دون رمز. أي رابط سابق لم يُستخدم يُلغى.</div></div><div data-result></div></div>`,
      buttons: e.phone ? [{ label: 'عرض الرابط يدوياً', cls: 'btn-ghost', icon: 'eye', close: false, onClick: function () { send('manual'); } }, { label: 'إرسال على واتساب', cls: 'btn-primary', icon: 'send', submit: true }] : [{ label: 'عرض الرابط يدوياً', cls: 'btn-primary', icon: 'eye', submit: true }],
      onSubmit: function () { send(e.phone ? 'whatsapp' : 'manual'); return false; }
    });
    var changed = false;
    d.promise.then(function () { if (changed && after) after(); });
    function send(channel) {
      var v = BT.form.values(d.form), btn = d.btn(channel === 'manual' ? 0 : 1);
      btn.classList.add('is-loading'); btn.disabled = true;
      api.post('/employees/' + e.id + '/activation-link', { channel: channel, onboarding: v.onboarding === '' ? null : v.onboarding === 'true' }).then(function (r) {
        btn.classList.remove('is-loading'); btn.disabled = false;
        changed = true;
        var box = d.el.querySelector('[data-result]');
        if (channel === 'whatsapp') {
          BT.render(box, h`<div class="banner success fs-sm mt-12">${icon('circle-check', 15)}<div>أُرسل على واتساب إلى ${A.phoneShow(r.sent_to)} · صالح حتى ${fmt.dt(r.expires_at)}${r.onboarding ? ' · سيكمل بياناته من التطبيق' : ''}</div></div>`);
          return;
        }
        A.loadScript('assets/vendor/qrcode/qrcode.js').then(function () {
          var qr = window.qrcode(0, 'M'); qr.addData(r.url); qr.make();
          BT.render(box, h`<div class="banner warn fs-sm mt-12">${icon('triangle-alert', 15)}<div>الرابط يفعّل حساب السائق لمن يملكه: اعرضه للسائق نفسه فقط. صالح حتى ${fmt.dt(r.expires_at)}.</div></div>
            <div class="center mt-12">${raw(qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true }).replace('<svg ', '<svg style="width:200px;height:200px;background:#fff;border-radius:10px" '))}</div>
            <div class="input-group mt-8"><input class="input ltr fs-sm" readonly value="${r.url}"><button type="button" class="addon" data-copy style="cursor:pointer">${icon('clipboard-check', 15)}</button></div>`);
          box.querySelector('[data-copy]').onclick = function () { navigator.clipboard.writeText(r.url).then(function () { BT.toast('تم نسخ الرابط'); }); };
        });
      }, function (err) { btn.classList.remove('is-loading'); btn.disabled = false; BT.toast(api.message(err), { type: 'error', timeout: 6000 }); });
    }
  };

  /* روابط جماعية: تمر بطابور بمعدل يحمي رقم واتساب من الحظر */
  A.bulkLinks = function (rows, clear) {
    // تحديد بلا سائقين لا يتحول أبداً إلى «كل غير المربوطين»
    if (rows && !rows.length) { BT.toast('لا يوجد سائقون في التحديد', { type: 'info' }); return; }
    var some = !!rows;
    A.formModal({
      title: 'روابط تفعيل جماعية', icon: 'send', submitText: 'إضافة للطابور', done: false,
      body: h`<div class="form">${some ? h`<p>إرسال رابط التفعيل إلى <b class="num">${rows.length}</b> سائق محدد.</p>` : BT.f.radios({ name: 'scope', label: 'لمن؟', required: true, value: 'all', options: [{ v: 'all', t: 'كل السائقين غير المربوطين', d: 'حساب التطبيق مفعّل ولا يوجد هاتف مربوط' }] })}
        <div class="banner info fs-sm">${icon('hourglass', 15)}<div>تُرسل الروابط من الطابور واحداً تلو الآخر بحد يومي، حتى لا يُحظر رقم واتساب. تتابع التقدم في تبويب «طابور روابط التفعيل».</div></div></div>`,
      submit: function () {
        return api.post('/activation-links/bulk', some ? { employee_ids: rows.map(function (r) { return r.id; }) } : { all_unbound: true }).then(function (r) {
          if (clear) clear();
          BT.toast('أُضيف ' + r.queued + ' للطابور', { sub: r.skipped.length ? 'تخطّي ' + r.skipped.length + ': ' + r.skipped.slice(0, 3).map(function (s) { return api.t('errors', s.reason, null, s.reason); }).join('، ') : '' });
        });
      }
    });
  };
  BT.actions['links-bulk'] = function () { A.bulkLinks(null); };

  function queuePanel(el) {
    A.load(el, api.get('/activation-links/queue'), function (qd) {
      setTimeout(function () {
        var tbl = el.querySelector('[data-queue]');
        if (tbl) BT.table(tbl, {
          rows: qd.items, pageSize: 25,
          columns: [
            { key: 'driver', label: 'السائق', render: function (x) { return x.driver ? BT.person(api.name(x.driver.name)) : '—'; } },
            { key: 'status', label: 'الحالة', render: function (x) { return h`${A.pill('link_status', x.status)}${x.onboarding ? h` <span class="muted fs-sm">مع إكمال البيانات</span>` : ''}`; } },
            { key: 'requested_at', label: 'الطلب', render: function (x) { return fmt.dt(x.requested_at); } },
            { key: 'sent_at', label: 'الإرسال', render: function (x) { return x.sent_at ? fmt.dt(x.sent_at) : '—'; } },
            { key: 'error', label: 'ملاحظة', render: function (x) { return x.error ? h`<span class="t-danger fs-sm">${api.t('errors', x.error, null, x.error)}</span>${x.attempts > 1 ? h` <span class="muted fs-sm">(${x.attempts} محاولات)</span>` : ''}` : ''; } }
          ],
          empty: { icon: 'inbox', title: 'الطابور فارغ' }
        });
        var c = el.querySelector('[data-cancel]');
        if (c) c.onclick = function () {
          A.confirmRun({ title: 'إلغاء المنتظر', message: 'يُلغى كل ما لم يُرسل بعد. ما أُرسل يبقى صالحاً.', confirmText: 'إلغاء المنتظر', tone: 'danger', run: function () { return api.post('/activation-links/queue/cancel'); }, after: function (r) { BT.toast('أُلغي ' + r.cancelled); queuePanel(el); } });
        };
      });
      return h`<div class="kpis">${BT.kpi({ label: 'في الانتظار', value: fmt.int(qd.waiting), dot: 'b' })}${BT.kpi({ label: 'أُرسل اليوم', value: fmt.int(qd.sent_today) + ' / ' + fmt.int(qd.daily_limit), dot: 'g', sub: 'الحد اليومي لحماية الرقم' })}${BT.kpi({ label: 'المدة المتوقعة', value: qd.waiting ? fmt.int(qd.estimated_days) + ' يوم' : '—', dot: 'o' })}</div>
        <div class="card"><div class="card-h"><h3>آخر الطلبات</h3>${qd.waiting ? h`<button type="button" class="btn btn-sm btn-danger ms-auto" data-cancel>${icon('x', 14)} إلغاء المنتظر</button>` : ''}</div><div data-queue></div></div>`;
    }).catch(function () {});
  }

  /* ================= إضافة / تعديل موظف ================= */
  BT.actions['employee-new'] = function () { A.employeeForm(null, function (e) { if (A.refreshEmployees) A.refreshEmployees(); A.employee(e.id); }); };
  A.employeeForm = function (e, after) {
    var salary = api.can('employees.view_salary'), plats = [];
    Promise.all([loadStatuses(), A.platforms ? A.platforms().catch(function () { return []; }) : []]).then(function (r) {
      plats = r[1] || [];
      var editing = !!e;
      e = e || { name: {}, is_driver: true, company_id: (api.companyOptions()[0] || {}).v, branch_id: api.defaultBranch() };
      var dlg = A.formModal({
        title: editing ? 'تعديل بيانات الموظف' : 'إضافة موظف', subtitle: editing ? api.name(e.name) : null, icon: editing ? 'pencil' : 'user-plus', size: 'lg',
        done: editing ? 'تم حفظ التعديلات' : 'تمت إضافة الموظف',
        body: h`<div class="form-grid">
          ${BT.f.input({ name: 'employee_number', label: 'الرقم الوظيفي', required: true, value: e.employee_number })}
          ${BT.f.switch({ name: 'is_driver', label: 'سائق (يستخدم تطبيق السائق)', checked: e.is_driver })}
          ${BT.f.input({ name: 'name_ar', label: 'الاسم بالعربية', required: true, value: e.name.ar })}
          ${BT.f.input({ name: 'name_en', label: 'الاسم بالإنجليزية (كما في الجواز)', required: true, value: e.name.en })}
          ${BT.f.input({ name: 'phone', label: 'الجوال', optional: true, value: e.phone, validate: 'phone', placeholder: '9xxxxxxx', hint: 'للسائق: عليه يصل رابط التفعيل ورموز الدخول، ولا تطبيق بدونه' })}
          ${BT.f.input({ name: 'civil_id', label: 'الرقم المدني', optional: true, value: e.civil_id, validate: 'civilId', maxlength: 12 })}
          ${BT.f.select({ name: 'company_id', label: 'الشركة (على أوراقها)', required: true, value: e.company_id, options: api.companyOptions(), placeholder: false })}
          ${BT.f.select({ name: 'branch_id', label: 'الفرع', required: true, value: e.branch_id, options: api.branchOptions(), placeholder: false })}
          ${BT.f.input({ name: 'nationality', label: 'الجنسية', optional: true, value: e.nationality })}
          ${BT.f.date({ name: 'hire_date', label: 'تاريخ الالتحاق', optional: true, value: e.hire_date })}
          ${BT.f.input({ name: 'department', label: 'القسم', optional: true, value: e.department })}
          ${BT.f.input({ name: 'job_title', label: 'الوظيفة', optional: true, value: e.job_title })}
          ${editing ? '' : BT.f.select({ name: 'status_code', label: 'الحالة', required: true, value: 'active', placeholder: false, options: statuses.filter(function (s) { return s.is_active && !s.is_terminal; }).map(function (s) { return { v: s.code, t: api.name(s.name) }; }) })}
          ${BT.f.select({ name: 'platform_id', label: 'منصة التوصيل', optional: true, value: e.platform_id || '', placeholder: '— لا يوجد —', options: plats.filter(function (x) { return x.is_active || x.id === e.platform_id; }).map(function (x) { return { v: x.id, t: api.name(x.name) }; }) })}
          ${BT.f.input({ name: 'platform_driver_id', label: 'رقمه في المنصة (driver id)', optional: true, value: e.platform_driver_id })}
          ${salary ? h`${BT.f.money({ name: 'basic_salary', label: 'الراتب الأساسي', optional: true, value: e.basic_salary })}${BT.f.input({ name: 'iban', label: 'IBAN', optional: true, value: e.iban, placeholder: 'KW..' })}${BT.f.input({ name: 'bank_name', label: 'البنك', optional: true, value: e.bank_name })}${BT.f.select({ name: 'payment_method', label: 'طريقة الدفع', optional: true, value: e.payment_method || '', placeholder: '—', options: [{ v: 'bank', t: api.t('payment_method', 'bank') }, { v: 'cash', t: api.t('payment_method', 'cash') }] })}` : ''}
        </div>`,
        submit: function (v) {
          var body = {
            employee_number: v.employee_number.trim(), name: Object.assign({}, e.name, { ar: v.name_ar.trim(), en: v.name_en.trim() }),
            is_driver: !!v.is_driver, phone: A.phoneE164(v.phone), civil_id: v.civil_id || null,
            company_id: +v.company_id, branch_id: +v.branch_id, nationality: v.nationality || null, hire_date: v.hire_date || null,
            department: v.department || null, job_title: v.job_title || null,
            platform_id: v.platform_id ? +v.platform_id : null, platform_driver_id: v.platform_driver_id ? v.platform_driver_id.trim() : null
          };
          if (salary) { body.basic_salary = v.basic_salary === '' ? null : String(v.basic_salary); body.iban = v.iban ? v.iban.replace(/\s/g, '').toUpperCase() : null; body.bank_name = v.bank_name || null; body.payment_method = v.payment_method || null; }
          if (!editing) { body.status_code = v.status_code; return api.post('/employees', body); }
          var changes = { version: e.version };
          Object.keys(body).forEach(function (k) { if (JSON.stringify(body[k]) !== JSON.stringify(k === 'basic_salary' && e[k] != null ? String(Number(e[k])) : e[k] == null ? null : e[k])) changes[k] = body[k]; });
          return api.patch('/employees/' + e.id, changes);
        },
        after: after
      });
      return dlg;
    }, api.fail).catch(function () {});
  };

  A.changeStatus = function (e, current, after) {
    loadStatuses().then(function () {
      var options = statuses.filter(function (s) { return s.is_active && s.code !== e.status_code; });
      var d = A.formModal({
        title: 'تغيير الحالة الوظيفية', subtitle: api.name(e.name) + ' · الحالية: ' + api.name(e.status_name), icon: 'repeat', done: 'تم تغيير الحالة',
        body: h`<div class="form">${BT.f.radios({ name: 'status_code', label: 'الحالة الجديدة', required: true, options: options.map(function (s) { return { v: s.code, t: api.name(s.name), d: s.is_terminal ? 'تنهي الخدمة' : s.is_working ? 'على رأس العمل' : '' }; }) })}
          <div data-warn class="hidden"><div class="banner danger fs-sm">${icon('triangle-alert', 16)}<div>إنهاء الخدمة نهائي: يُلغى وصول التطبيق فوراً، وتُعلَّم عهدته المفتوحة ورصيد الكاش للمتابعة حتى الاستلام والتسوية.</div></div></div>
          ${BT.f.textarea({ name: 'note', label: 'ملاحظة', optional: true, rows: 2 })}</div>`,
        submit: function (v) { return api.post('/employees/' + e.id + '/status', { status_code: v.status_code, note: v.note || null }); },
        after: after
      });
      BT.on(d.el, 'change', '[name=status_code]', function (ev, r) { var s = statuses.find(function (x) { return x.code === r.value; }); d.el.querySelector('[data-warn]').classList.toggle('hidden', !(s && s.is_terminal)); });
    }, api.fail).catch(function () {});
  };

  /* ================= طلبات التسجيل الذاتي ================= */
  function regTable() {
    BT.table(document.getElementById('reg-table'), {
      fetch: function (s) { return api.get('/onboarding', { status: s.chip, limit: s.limit, offset: s.offset }); },
      chips: { value: 'submitted', all: false, options: A.options('onboarding_status', ['submitted', 'rejected', 'draft', 'approved']) },
      columns: [
        { key: 'employee', label: 'السائق', render: function (r) { return A.person(r.employee); } },
        { key: 'plate', label: 'السيارة', render: function (r) { return r.plate_number ? BT.plate(r.plate_number) : raw('<span class="muted">—</span>'); } },
        { key: 'submitted_at', label: 'أُرسل', render: function (r) { return r.submitted_at ? fmt.dt(r.submitted_at) : '—'; } },
        { key: 'status', label: 'الحالة', render: function (r) { return A.pill('onboarding_status', r.status); } }
      ],
      rowClick: function (r) { A.reviewRegistration(r.id); },
      empty: { icon: 'inbox', title: 'لا توجد طلبات' }
    });
  }

  A.reviewRegistration = function (id) {
    var dlg = BT.drawer.open({ title: 'طلب تسجيل', icon: 'user-round-check', size: 'lg', body: A.spinner(), buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }] });
    Promise.all([api.get('/onboarding/' + id), loadDocTypes()]).then(function (res) {
      var r = res[0], data = r.data || {}, veh = data.vehicle || {}, file = function (sha) { return api.url('/onboarding/' + id + '/files/' + sha); };
      dlg.panel.querySelector('.modal-h h3').textContent = api.name(r.employee.name);
      var match = r.vehicle;
      var vehStatus = !match ? null : !match.found ? BT.pill('غير موجودة في النظام', 'r') : match.held_by_other ? BT.pill('في عهدة سائق آخر', 'r') : BT.pill('موجودة · ' + api.t('vehicle_status', match.status), 'g');
      dlg.setBody(h`${r.status === 'rejected' ? h`<div class="banner warn fs-sm mb-12">${icon('rotate-ccw', 15)}<div>أُعيد للسائق: ${r.review_note || ''}</div></div>` : ''}
        ${r.status === 'approved' ? h`<div class="banner success fs-sm mb-12">${icon('circle-check', 15)}<div>معتمد ${r.reviewed_at ? fmt.dt(r.reviewed_at) : ''}</div></div>` : ''}
        <div class="label mb-8">البيانات</div>${BT.kv([['الحالة', A.pill('onboarding_status', r.status)], ['الجوال', A.phoneShow(r.phone)], ['الرقم المدني', data.civil_id ? h`<span class="num">${data.civil_id}</span>` : '—'], ['الجنسية', data.nationality || '—'], ['أُرسل', r.submitted_at ? fmt.dt(r.submitted_at) : '—']])}
        <div class="label mt-16 mb-8">المستندات</div>
        ${(data.documents || []).length ? h`<div class="list">${data.documents.map(function (d) {
          var n = d.expiry_date ? BT.date.daysLeft(d.expiry_date) : null;
          var pics = [];
          if (d.front_sha256) pics.push({ src: file(d.front_sha256), caption: docTypeName(d.type_code) + ' · الوجه' });
          if (d.back_sha256) pics.push({ src: file(d.back_sha256), caption: docTypeName(d.type_code) + ' · الظهر' });
          return h`<div class="li" style="align-items:flex-start"><span class="li-ic ${n != null && n < 0 ? 'r' : ''}">${icon('file-badge', 16)}</span><div class="li-main"><div class="li-t">${docTypeName(d.type_code)} ${d.number ? h`<span class="num muted fs-sm">${d.number}</span>` : ''}</div><div class="li-d">${d.expiry_date ? h`ينتهي <span class="num">${fmt.date(d.expiry_date)}</span>` : 'بلا تاريخ انتهاء'} ${n != null && n < 0 ? BT.pill('منتهي', 'r') : ''}</div><div class="mt-8" style="max-width:280px">${A.thumbs(pics)}</div></div></div>`;
        })}</div>` : raw('<div class="muted fs-sm">لم يرسل مستندات</div>')}
        <div class="label mt-16 mb-8">السيارة</div>
        ${data.no_vehicle || !veh.plate_number ? BT.empty('car', 'لا توجد سيارة مع السائق', 'يُعتمد بدون عهدة') : h`${BT.kv([['اللوحة', BT.plate(veh.plate_number)], ['في النظام', vehStatus || '—'], ['العداد', veh.odometer_km != null ? h`<span class="num">${fmt.km(veh.odometer_km)}</span> كم` : '—']])}
          <div class="mt-12">${A.thumbs([].concat(veh.odometer_photo ? [{ src: file(veh.odometer_photo), caption: 'العداد' }] : []).concat((veh.photos || []).map(function (p) { return { src: file(p.sha256), caption: api.t('photo_position', p.position) }; })))}</div>
          ${r.status === 'submitted' ? h`<div class="banner info fs-sm mt-12">${icon('key-round', 15)}<div>عند الاعتماد تبدأ عهدة السائق بقراءة العداد وصور الحالة هذه.</div></div>` : ''}`}`);
      if (r.status !== 'submitted' || !api.can('employees.onboarding')) return;
      var foot = dlg.panel.querySelector('.modal-f');
      BT.render(foot, h`<span class="spacer"></span><button type="button" class="btn btn-outline" data-x="reject">${icon('x', 15)}إعادة للسائق مع السبب</button><button type="button" class="btn btn-primary" data-x="approve">${icon('check', 15)}اعتماد</button>`);
      var done = function () { dlg.close(); A.refreshCounts(); A.router.refresh(); };
      BT.on(foot, 'click', '[data-x]', function (ev, b) {
        if (b.getAttribute('data-x') === 'reject') {
          A.confirmRun({ title: 'إعادة الطلب للسائق', message: 'يصل السبب للسائق على واتساب وفي التطبيق، فيصحح ويرسل من جديد.', confirmText: 'إعادة للسائق', tone: 'warn', icon: 'rotate-ccw', reason: { label: 'السبب', required: true, placeholder: 'مثال: صورة الإقامة غير واضحة' },
            run: function (reason) { return api.post('/onboarding/' + id + '/reject', { reason: reason }); }, done: 'أُعيد الطلب للسائق', after: done });
        } else {
          A.confirmRun({ title: 'اعتماد التسجيل', message: 'تُسجَّل البيانات والمستندات' + (veh.plate_number && !data.no_vehicle ? ' وعهدة السيارة ' + veh.plate_number : '') + ' معاً. إذا فشل أي جزء لا يُسجَّل شيء ويظهر السبب.', confirmText: 'اعتماد', tone: 'success', icon: 'check',
            run: function () { return api.post('/onboarding/' + id + '/approve'); }, done: 'تم اعتماد التسجيل', after: done });
        }
      });
    }, function (err) { dlg.setBody(A.errorBox(err)); });
  };
})();
