/* =====================================================================
   صفحات: الموظفون · الرواتب
   بوب أب: إضافة موظف (معالج 4 خطوات) · ملف الموظف (drawer بتبويبات) ·
   تغيير الحالة · إعادة ربط الهاتف (OTP) · تعطيل الحساب · قسيمة الراتب (طباعة) ·
   إضافة خصم بالأقساط · اعتماد وإقفال الكشف (تأكيد بكتابة النص) · ملف البنك
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, D = BT.data, A = BT.A;
  var cfg = BT.config;
  function emp(id) { return D.employees.find(function (e) { return e.id === id; }); }

  /* =================================================================
     الموظفون  #/employees?tab=docs
     ================================================================= */
  BT.pages['employees'] = function (p, q) {
    A.setTitle('الموظفون');
    var c = function (s) { return D.employees.filter(function (e) { return e.status === s; }).length; };
    var docs = D.docsExpiring(30), tab = q.tab || 'list';
    BT.render(A.view(), h`
      ${A.head('ملف لكل موظف', 'الحالات والمستندات والخصومات في مكان واحد',
        h`${A.btn('استيراد من Excel', { icon: 'file-spreadsheet', cls: 'btn-outline', action: 'soon', arg: 'استيراد الموظفين' })}${A.btn('تصدير', { icon: 'download', cls: 'btn-outline', action: 'export', arg: 'قائمة الموظفين' })}${A.btn('إضافة موظف', { icon: 'user-plus', cls: 'btn-primary', action: 'employee-new' })}`)}
      <div class="kpis">
        ${BT.kpi({ label: 'الموظفون', value: fmt.int(D.employees.length), sub: 'في كل الفروع', dot: 'b', action: 'emp-chip', arg: '' })}
        ${BT.kpi({ label: 'على رأس العمل', value: fmt.int(c('على رأس العمل')), dot: 'g', action: 'emp-chip', arg: 'على رأس العمل' })}
        ${BT.kpi({ label: 'تحت إجراء الفيزا', value: fmt.int(c('تحت إجراء الفيزا')), dot: 'o', action: 'emp-chip', arg: 'تحت إجراء الفيزا' })}
        ${BT.kpi({ label: 'مستقيل', value: fmt.int(c('مستقيل')), sub: 'حسابات معطّلة', dot: 'n', action: 'emp-chip', arg: 'مستقيل' })}
      </div>
      ${BT.tabs('emp', [['list', 'الموظفون'], ['docs', 'مستندات تنتهي خلال 30 يوماً', docs.length]], tab, 'tabs-line')}
      <div data-panel="list" data-group="emp" class="${tab === 'list' ? 'active' : ''}"><div class="card"><div id="emp-table"></div></div></div>
      <div data-panel="docs" data-group="emp" class="${tab === 'docs' ? 'active' : ''}"><div class="card"><div id="doc-table"></div></div></div>`);
    var t = BT.table(document.getElementById('emp-table'), {
      rows: function () { return D.employees; },
      search: { placeholder: 'الاسم أو الرقم الوظيفي أو الجوال…', text: function (e) { return e.name + ' ' + e.id + ' ' + e.phone + ' ' + (e.vehicleId || ''); } },
      chips: { key: 'status', options: ['على رأس العمل', 'تحت إجراء الفيزا', 'مستقيل'].map(function (s) { return { v: s, t: s }; }) },
      columns: [
        { key: 'name', label: 'الموظف', render: function (e) { return BT.person(e.name, e.id); } },
        { key: 'role', label: 'الوظيفة' },
        { key: 'status', label: 'الحالة', render: function (e) { return BT.pill(e.status, D.empStatusTone[e.status]); } },
        { key: 'phone', label: 'الجوال', render: function (e) { return h`<span class="num">${e.phone}</span>`; } },
        { key: 'vehicleId', label: 'السيارة', render: function (e) { return e.vehicleId ? BT.plate(e.vehicleId) : raw('<span class="muted">—</span>'); } },
        { key: 'nationality', label: 'الجنسية' },
        { key: 'device', label: 'الهاتف', sort: false, render: function (e) { return e.device && e.device.bound ? raw('<span data-tip="مربوط برمز OTP">' + icon('smartphone', 16, 't-success') + '</span>') : e.role === 'سائق' && e.status === 'على رأس العمل' ? raw('<span data-tip="غير مربوط">' + icon('smartphone', 16, 'faint') + '</span>') : ''; } }
      ],
      rowClick: function (e) { A.employee(e); },
      rowMenu: function (e) { return [{ label: 'ملف الموظف', icon: 'user-round', onClick: function () { A.employee(e); } }, { label: 'تغيير الحالة', icon: 'repeat', onClick: function () { A.changeStatus(e); } }, { label: 'إضافة خصم', icon: 'minus-circle', onClick: function () { A.addDeduction(e); } }].concat(e.device ? [{ label: 'إعادة ربط الهاتف', icon: 'smartphone', onClick: function () { A.resetDevice(e); } }] : []); }
    });
    BT.table(document.getElementById('doc-table'), {
      rows: function () { return docs; }, pageSize: 0,
      columns: [
        { key: 'emp', label: 'الموظف', sort: function (d) { return d.emp.name; }, render: function (d) { return BT.person(d.emp.name, d.emp.id); } },
        { key: 'type', label: 'المستند' },
        { key: 'exp', label: 'ينتهي', render: function (d) { return h`<span class="num">${fmt.date(d.exp)}</span>`; } },
        { key: 'days', label: '', render: function (d) { return BT.pill(fmt.daysLabel(d.days), d.days <= 15 ? 'o' : 'b'); } },
        { key: '_a', label: '', sort: false, cls: 'actions', render: function (d) { return h`<button type="button" class="btn btn-sm btn-soft" data-renew="${d.emp.id}|${d.type}">${icon('refresh-cw', 13)} تجديد</button>`; } }
      ],
      rowClick: function (d) { A.employee(d.emp, 'docs'); }
    });
    BT.actions['emp-chip'] = function (s) { t.setChip(s); };
    BT.on(A.view(), 'click', '[data-renew]', function (ev, b) { var x = b.getAttribute('data-renew').split('|'); A.renewDoc(emp(x[0]), x[1]); });
  };
  BT.actions['employee-open'] = function (id) { A.employee(emp(id)); };

  /* ---------- ملف الموظف ---------- */
  A.employee = function (e, tab) {
    var v = D.vehicleOf(e), ded = D.deductions.filter(function (d) { return d.empId === e.id; });
    var dlg = BT.drawer.open({
      title: h`<bdi>${e.name}</bdi>`, subtitle: e.id + ' · ' + e.role, icon: 'user-round', size: 'lg',
      body: h`<div class="flex items-center gap-12 mb-16">${BT.avatar(e.name, 'xl')}<div class="flex-1"><div class="flex gap-8 items-center" style="flex-wrap:wrap">${BT.pill(e.status, D.empStatusTone[e.status], true)}${v ? BT.pill('السيارة ' + v.plate, 'b') : ''}</div><div class="muted fs-sm mt-4">منذ ${fmt.date(e.join)} · ${e.branch}</div></div></div>
        ${BT.tabs('empd', [['info', 'البيانات'], ['docs', 'المستندات'], ['ded', 'الخصومات', ded.length || null], ['device', 'الهاتف'], ['log', 'السجل']], tab || 'info', 'tabs-line')}
        <div class="mt-16">
        <div data-panel="info" data-group="empd" class="${!tab || tab === 'info' ? 'active' : ''}">${BT.kv([['الجوال', h`<a class="num" href="tel:+965${e.phone}">${e.phone}</a>`], ['الرقم المدني', e.civilId ? h`<span class="num">${e.civilId}</span>` : BT.pill('قيد الإصدار', 'o')], ['الجنسية', e.nationality], ['الوظيفة', e.role], ['الفرع', e.branch], ['الراتب الأساسي', BT.amt(e.basic)], ['رصيد الكاش', e.role === 'سائق' ? BT.amt(e.balance) : '—']])}</div>
        <div data-panel="docs" data-group="empd" class="${tab === 'docs' ? 'active' : ''}"><div class="list">${(e.docs || []).map(function (d) { var n = BT.date.daysLeft(d.exp); return h`<div class="li"><span class="li-ic ${n <= 30 ? 'o' : ''}">${icon('file-badge', 16)}</span><div class="li-main"><div class="li-t">${d.type}</div><div class="li-d">ينتهي ${fmt.date(d.exp)}</div></div>${n <= 30 ? BT.pill(fmt.daysLabel(n), n <= 15 ? 'o' : 'b') : ''}<button type="button" class="btn btn-sm btn-ghost" data-renew-d="${d.type}">${icon('upload', 13)} تحديث</button></div>`; })}</div></div>
        <div data-panel="ded" data-group="empd" class="${tab === 'ded' ? 'active' : ''}">${ded.length ? BT.chart.table(['السبب', 'الإجمالي', 'الأقساط', 'الشهري'], ded.map(function (d) { return [d.reason, fmt.kwd(d.total), d.paid + ' / ' + d.count, fmt.kwd(d.per)]; })) : BT.empty('circle-check', 'لا توجد خصومات', '')}
          <div class="mt-12">${A.btn('إضافة خصم', { icon: 'plus', cls: 'btn-sm btn-soft', action: 'emp-ded', arg: e.id })}</div></div>
        <div data-panel="device" data-group="empd" class="${tab === 'device' ? 'active' : ''}">${e.device ? h`${BT.kv([['الحالة', e.device.bound ? BT.pill('مربوط برمز OTP', 'g') : BT.pill('غير مربوط', 'o')], ['الجهاز', e.device.model], ['منذ', fmt.date(e.device.since)], ['آخر دخول', 'اليوم']])}
          <div class="banner info mt-12 fs-sm">${icon('shield-check', 15)}<div>حساب السائق مربوط بهاتف واحد. عند تغيير الهاتف يُعاد الربط برمز OTP جديد على الجوال المسجل.</div></div>` : BT.empty('smartphone', 'لا يوجد هاتف مربوط', '')}</div>
        <div data-panel="log" data-group="empd" class="${tab === 'log' ? 'active' : ''}"><div class="timeline">
          <div class="tl-item"><span class="tl-ic g">${icon('check', 13)}</span><div><div class="tl-t">${e.status}</div><div class="tl-d">منذ ${fmt.date(e.join)} · نورة الشمري</div></div></div>
          <div class="tl-item"><span class="tl-ic">${icon('user-plus', 13)}</span><div><div class="tl-t">إنشاء الملف</div><div class="tl-d">${fmt.date(e.join)}</div></div></div></div></div>
        </div>`,
      buttons: [
        { label: 'تغيير الحالة', cls: 'btn-outline', icon: 'repeat', close: false, onClick: function () { A.changeStatus(e); } },
        e.device ? { label: 'إعادة ربط الهاتف', cls: 'btn-ghost', icon: 'smartphone', close: false, onClick: function () { A.resetDevice(e); } } : null,
        { label: 'إغلاق', cls: 'btn-secondary' }
      ].filter(Boolean)
    });
    BT.on(dlg.el, 'click', '[data-renew-d]', function (ev, b) { A.renewDoc(e, b.getAttribute('data-renew-d')); });
  };
  BT.actions['emp-ded'] = function (id) { A.addDeduction(emp(id)); };
  A.renewDoc = function (e, type) {
    BT.modal.open({
      title: 'تحديث ' + type, subtitle: e.name, icon: 'file-badge', size: 'sm', form: true,
      body: h`<div class="form">${BT.f.date({ name: 'exp', label: 'تاريخ الانتهاء الجديد', required: true })}${BT.f.upload({ name: 'file', label: 'صورة المستند', required: true })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) { var d = (e.docs || []).find(function (x) { return x.type === type; }); if (d) d.exp = f.exp; BT.toast('تم تحديث ' + type + ' — ' + e.name); if (A.router.current === 'employees') A.router.refresh(); }
    });
  };
  A.changeStatus = function (e) {
    var d = BT.modal.open({
      title: 'تغيير الحالة الوظيفية', subtitle: e.name + ' · الحالة الحالية: ' + e.status, icon: 'repeat', form: true,
      body: h`<div class="form">${BT.f.radios({ name: 's', label: 'الحالة الجديدة', required: true, value: e.status, options: [{ v: 'على رأس العمل', t: 'على رأس العمل' }, { v: 'تحت إجراء الفيزا', t: 'تحت إجراء الفيزا' }, { v: 'مستقيل', t: 'مستقيل' }] })}
        <div id="res-warn" class="hidden"><div class="banner danger">${icon('triangle-alert', 16)}<div>سيُعطَّل حساب التطبيق فوراً${e.vehicleId ? h` ويلزم استلام السيارة <b class="plate">${e.vehicleId}</b>` : ''}${e.balance ? h`، ورصيد الكاش <b class="num">${fmt.kwd(e.balance)}</b> د.ك يجب تحصيله قبل التسوية النهائية` : ''}.</div></div></div>
        ${BT.f.date({ name: 'from', label: 'تاريخ السريان', required: true, value: cfg.today })}${BT.f.textarea({ name: 'why', label: 'السبب', required: true, rows: 2 })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) { if (f.s === e.status) { BT.toast('لم تتغير الحالة', { type: 'info' }); return false; } e.status = f.s; if (f.s === 'مستقيل' && e.device) e.device.bound = false; BT.toast('تم تغيير حالة ' + e.name + ' إلى: ' + f.s); A.router.refresh(); BT.closeAll(); }
    });
    BT.on(d.el, 'change', '[name=s]', function (ev, r) { d.el.querySelector('#res-warn').classList.toggle('hidden', r.value !== 'مستقيل'); });
  };
  A.resetDevice = function (e) {
    BT.confirm({ title: 'إعادة ربط الهاتف', message: h`سيُفصل الهاتف الحالي (${e.device.model}) فوراً، ويصل رمز OTP جديد إلى <b class="num">${e.phone}</b> عند أول دخول من الهاتف الجديد.`, confirmText: 'فصل الهاتف', tone: 'danger', icon: 'smartphone', reason: { label: 'السبب', placeholder: 'مثال: السائق غيّر هاتفه' } })
      .then(function (r) { if (!r.ok) return; e.device.bound = false; BT.toast('تم فصل هاتف ' + e.name, { sub: 'بانتظار الدخول برمز OTP من الهاتف الجديد' }); });
  };

  /* ---------- إضافة موظف (معالج) ---------- */
  BT.actions['employee-new'] = function () {
    var steps = ['البيانات الشخصية', 'المستندات', 'العمل والراتب', 'حساب التطبيق'], cur = 0;
    var d = BT.modal.open({
      title: 'إضافة موظف', icon: 'user-plus', size: 'lg',
      body: h`<div class="stepper" id="wz-steps"></div>
        <div data-step="0" class="form-grid">${BT.f.input({ name: 'name', label: 'الاسم الكامل (كما في الجواز)', required: true, full: true })}${BT.f.select({ name: 'nat', label: 'الجنسية', required: true, options: ['الهند', 'باكستان', 'بنغلاديش', 'نيبال', 'مصر', 'الفلبين', 'الكويت', 'أخرى'] })}${BT.f.input({ name: 'phone', label: 'الجوال', required: true, validate: 'kwPhone', placeholder: '9xxxxxxx', maxlength: 8 })}${BT.f.input({ name: 'civil', label: 'الرقم المدني', optional: true, validate: 'civilId', maxlength: 12, hint: 'اتركه فارغاً إذا كان تحت إجراء الفيزا' })}${BT.f.date({ name: 'dob', label: 'تاريخ الميلاد', optional: true })}</div>
        <div data-step="1" class="form-grid hidden">${BT.f.date({ name: 'resExp', label: 'انتهاء الإقامة', optional: true })}${BT.f.upload({ name: 'resFile', label: 'صورة الإقامة', optional: true })}${BT.f.date({ name: 'licExp', label: 'انتهاء رخصة القيادة', optional: true })}${BT.f.upload({ name: 'licFile', label: 'صورة الرخصة', optional: true })}${BT.f.date({ name: 'passExp', label: 'انتهاء الجواز', required: true })}${BT.f.upload({ name: 'passFile', label: 'صورة الجواز', required: true })}</div>
        <div data-step="2" class="form-grid hidden">${BT.f.select({ name: 'role', label: 'الوظيفة', required: true, value: 'سائق', options: ['سائق', 'مشرف تشغيل', 'محاسب', 'الموارد البشرية', 'أخرى'] })}${BT.f.select({ name: 'branch', label: 'الفرع', required: true, options: D.company.branches })}${BT.f.select({ name: 'status', label: 'الحالة', required: true, value: 'تحت إجراء الفيزا', options: ['على رأس العمل', 'تحت إجراء الفيزا'] })}${BT.f.date({ name: 'join', label: 'تاريخ الالتحاق', required: true, value: cfg.today })}${BT.f.money({ name: 'basic', label: 'الراتب الأساسي', required: true, min: 1 })}${BT.f.money({ name: 'allow', label: 'بدلات ثابتة', optional: true })}</div>
        <div data-step="3" class="hidden"><div class="form">${BT.f.switch({ name: 'app', label: 'إنشاء حساب في تطبيق السائق', checked: true })}
          <div class="banner info">${icon('message-square', 16)}<div>يصل للسائق رابط تحميل التطبيق. عند أول دخول يصل رمز OTP إلى جواله ويُربط الحساب بهاتفه.</div></div>
          <div class="highlight-box" id="wz-sum"></div></div></div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'رجوع', cls: 'btn-outline', icon: 'arrow-right', close: false, onClick: function () { go(-1); } }, { label: 'التالي', cls: 'btn-primary', close: false, onClick: function () { go(1); } }]
    });
    function draw() {
      BT.render(d.el.querySelector('#wz-steps'), h`${steps.map(function (s, i) { return h`${i ? raw('<div class="step-line' + (i <= cur ? ' done' : '') + '"></div>') : ''}<div class="step${i === cur ? ' active' : i < cur ? ' done' : ''}"><span class="sn">${i < cur ? icon('check', 13) : i + 1}</span>${s}</div>`; })}`);
      BT.$$('[data-step]', d.el).forEach(function (s) { s.classList.toggle('hidden', +s.getAttribute('data-step') !== cur); });
      d.btn(1).style.visibility = cur ? 'visible' : 'hidden';
      d.btn(2).innerHTML = cur === steps.length - 1 ? String(h`${icon('check', 15)}حفظ الموظف`) : 'التالي';
      if (cur === 3) { var v = BT.form.values(d.body); BT.render(d.el.querySelector('#wz-sum'), BT.kv([['الاسم', v.name], ['الوظيفة', v.role + ' · ' + v.branch], ['الحالة', v.status], ['الراتب', BT.amt(v.basic || 0)], ['الجوال', h`<span class="num">${v.phone}</span>`]])); }
    }
    function go(dir) {
      if (dir > 0) {
        var panel = d.el.querySelector('[data-step="' + cur + '"]');
        BT.form.live(panel);
        if (!BT.form.validate(panel)) return;
        if (cur === steps.length - 1) { var v = BT.form.values(d.body); D.employees.unshift({ id: 'E-' + (1429 + D.employees.length - 428), name: v.name, role: v.role, status: v.status, branch: v.branch, phone: v.phone, civilId: v.civil, nationality: v.nat, join: v.join, basic: v.basic, balance: 0, docs: [{ type: 'الجواز', exp: v.passExp }] }); d.close(); BT.toast('تمت إضافة ' + v.name, { sub: v.app ? 'أُرسل رابط تطبيق السائق إلى ' + v.phone : '' }); A.router.refresh(); return; }
      }
      cur = Math.max(0, Math.min(steps.length - 1, cur + dir)); draw();
    }
    draw();
  };

  /* =================================================================
     الرواتب  #/payroll?tab=deductions
     ================================================================= */
  BT.pages['payroll'] = function (p, q) {
    A.setTitle('الرواتب');
    var P = D.payroll, rows = P.rows, locked = P.status !== 'بانتظار الاعتماد';
    var sum = function (k) { return BT.sum(rows, function (r) { return r[k]; }); };
    var tab = q.tab || 'sheet';
    BT.render(A.view(), h`
      <div class="page-head"><div><div class="flex items-center gap-8"><h2>كشف رواتب ${P.month}</h2>${BT.pill(P.status, locked ? 'g' : 'o', true)}</div><p>الخصومات المعتمدة تُسحب تلقائياً · لا صافي سالب · الحد الأقصى للخصم ${cfg.maxDeductionPct}% والزيادة تُرحّل</p></div>
        <div class="page-actions">${A.btn('إضافة خصم', { icon: 'minus-circle', cls: 'btn-outline', action: 'ded-new' })}${A.btn('ملف البنك (Excel)', { icon: 'file-spreadsheet', cls: 'btn-outline', action: 'bank-file' })}${locked ? '' : A.btn('اعتماد وإقفال', { icon: 'lock', cls: 'btn-primary', action: 'payroll-lock' })}</div></div>
      <div class="kpis cols-5">
        ${BT.kpi({ label: 'في الكشف', value: fmt.int(rows.length), sub: 'على رأس العمل', dot: 'b' })}
        ${BT.kpi({ label: 'الأساسي', value: fmt.kwd(sum('basic')), dot: 'n' })}
        ${BT.kpi({ label: 'الحوافز', value: fmt.kwd(sum('incentives')), dot: 'g' })}
        ${BT.kpi({ label: 'الخصومات', value: fmt.kwd(sum('deductions')), dot: 'r' })}
        ${BT.kpi({ label: 'الصافي', value: fmt.kwd(sum('net')), dot: 'p' })}
      </div>
      ${BT.tabs('pay', [['sheet', 'الكشف'], ['deductions', 'الخصومات والأقساط', D.deductions.length]], tab, 'tabs-line')}
      <div data-panel="sheet" data-group="pay" class="${tab === 'sheet' ? 'active' : ''}"><div class="card"><div id="pay-table"></div></div></div>
      <div data-panel="deductions" data-group="pay" class="${tab === 'deductions' ? 'active' : ''}"><div class="card"><div id="ded-table"></div></div></div>`);
    BT.table(document.getElementById('pay-table'), {
      rows: function () { return rows; },
      search: { placeholder: 'ابحث بالاسم…', text: function (r) { return r.name + ' ' + r.id; } },
      chips: { key: 'role', options: [{ v: 'driver', t: 'السائقون' }, { v: 'staff', t: 'الإداريون' }, { v: 'ded', t: 'عليهم خصومات' }], match: function (r, v) { return v === 'driver' ? r.role === 'سائق' : v === 'staff' ? r.role !== 'سائق' : r.deductions > 0; } },
      columns: [
        { key: 'name', label: 'الموظف', render: function (r) { return BT.person(r.name, r.role); } },
        { key: 'basic', label: 'الأساسي', num: true, render: function (r) { return fmt.kwd(r.basic); } },
        { key: 'incentives', label: 'الحوافز', num: true, render: function (r) { return fmt.kwd(r.incentives); } },
        { key: 'deductions', label: 'الخصومات', num: true, render: function (r) { return r.deductions ? h`<span class="t-danger">${fmt.kwd(r.deductions)}</span>${r.dedNote ? h`<span class="sub">${r.dedNote}</span>` : ''}` : fmt.kwd(0); } },
        { key: 'net', label: 'الصافي', num: true, render: function (r) { return h`<b>${fmt.kwd(r.net)}</b>`; } }
      ],
      foot: function (rs) { return h`<tr><td>الإجمالي (${rs.length})</td><td class="num">${fmt.kwd(BT.sum(rs, function (r) { return r.basic; }))}</td><td class="num">${fmt.kwd(BT.sum(rs, function (r) { return r.incentives; }))}</td><td class="num">${fmt.kwd(BT.sum(rs, function (r) { return r.deductions; }))}</td><td class="num">${fmt.kwd(BT.sum(rs, function (r) { return r.net; }))}</td></tr>`; },
      rowClick: function (r) { A.payslip(r); }
    });
    BT.table(document.getElementById('ded-table'), {
      rows: function () { return D.deductions; },
      chips: { key: 'status', options: [{ v: 'معتمد', t: 'معتمد' }, { v: 'بانتظار الاعتماد', t: 'بانتظار الاعتماد' }] },
      columns: [
        { key: 'driver', label: 'الموظف', render: function (d) { return BT.person(d.driver); } },
        { key: 'reason', label: 'السبب' },
        { key: 'total', label: 'الإجمالي', num: true, render: function (d) { return fmt.kwd(d.total); } },
        { key: 'paid', label: 'الأقساط', render: function (d) { return h`<div class="flex items-center gap-8"><div class="meter ok" style="width:70px"><i style="width:${(d.paid / d.count * 100).toFixed(0)}%"></i></div><span class="num fs-sm">${d.paid} / ${d.count}</span></div>`; } },
        { key: 'per', label: 'الشهري', num: true, render: function (d) { return fmt.kwd(d.per); } },
        { key: 'start', label: 'يبدأ' },
        { key: 'status', label: 'الحالة', render: function (d) { return BT.pill(d.status, d.status === 'معتمد' ? 'g' : 'o'); } }
      ],
      rowMenu: function (d) { return [{ label: 'إيقاف مؤقت لشهر', icon: 'pause', onClick: function () { BT.toast('تم تأجيل قسط ' + d.driver + ' لشهر', { sub: 'يُرحّل للشهر التالي' }); } }, { sep: true }, { label: 'إلغاء الخصم', icon: 'x', danger: true, onClick: function () { BT.confirm({ title: 'إلغاء الخصم', message: 'إلغاء خصم «' + d.reason + '» على ' + d.driver + '؟', tone: 'danger', confirmText: 'إلغاء الخصم', reason: {} }).then(function (r) { if (r.ok) { D.deductions.splice(D.deductions.indexOf(d), 1); BT.toast('تم إلغاء الخصم'); A.go('payroll?tab=deductions'); } }); } }]; }
    });
  };

  A.payslipHtml = function (r) {
    var ded = D.deductions.filter(function (d) { return d.empId === r.empId && d.status === 'معتمد'; });
    return h`<div class="receipt" style="max-width:440px"><div class="r-head"><div><div style="font-weight:700;font-size:15px">${BT.config.client}</div><div style="color:#6B7385;font-size:11.5px">قسيمة راتب ${D.payroll.month}</div></div><div style="text-align:left"><b><bdi>${r.name}</bdi></b><div style="color:#6B7385;font-size:11.5px" class="num">${r.empId}</div></div></div>
      <div class="r-row"><span>الراتب الأساسي</span><span class="num">${fmt.kwd(r.basic)}</span></div><div class="r-row"><span>الحوافز</span><span class="num">${fmt.kwd(r.incentives)}</span></div>
      ${ded.map(function (d) { return h`<div class="r-row"><span>خصم: ${d.reason} (${d.paid + 1}/${d.count})</span><span class="num" style="color:#D12F2F">−${fmt.kwd(d.per)}</span></div>`; })}
      <div class="r-row" style="border-top:1px dashed #C9D1DE;margin-top:6px;padding-top:8px;font-weight:700;font-size:15px"><span style="color:#0B1F3A">الصافي</span><span class="num">${fmt.kwd(r.net)} د.ك</span></div></div>`;
  };
  A.payslip = function (r) {
    BT.modal.open({
      title: 'قسيمة الراتب', subtitle: r.name + ' · ' + D.payroll.month, icon: 'receipt', size: 'sm', body: A.payslipHtml(r),
      buttons: [{ label: 'طباعة', cls: 'btn-outline', icon: 'printer', close: false, onClick: function () { BT.print(A.payslipHtml(r)); } }, { label: 'إغلاق', cls: 'btn-primary' }]
    });
  };
  BT.actions['bank-file'] = function () { A.exportToast('ملف تحويل الرواتب للبنك — ' + D.payroll.month); };
  BT.actions['payroll-lock'] = function () {
    var P = D.payroll;
    BT.confirm({ title: 'اعتماد وإقفال كشف ' + P.month, message: 'بعد الإقفال لا يمكن تعديل الكشف، وتُسجَّل الأقساط كمدفوعة، ويظهر الراتب للسائقين في التطبيق. أي تصحيح بعد ذلك يكون في الشهر التالي.', details: BT.kv([['عدد الموظفين', fmt.int(P.rows.length)], ['الصافي', BT.amt(BT.sum(P.rows, function (r) { return r.net; }))]]), confirmText: 'اعتماد وإقفال', tone: 'warn', icon: 'lock', typed: P.month })
      .then(function (r) { if (!r.ok) return; P.status = 'معتمد ومقفل'; D.approvals = D.approvals.filter(function (a) { return a.id !== 'AP-3'; }); BT.toast('تم اعتماد وإقفال كشف ' + P.month); A.router.refresh(); });
  };

  /* ---------- إضافة خصم ---------- */
  BT.actions['ded-new'] = function () { A.addDeduction(null); };
  A.addDeduction = function (e) {
    var list = D.employees.filter(function (x) { return x.status === 'على رأس العمل'; });
    var d = BT.modal.open({
      title: 'إضافة خصم', icon: 'minus-circle', form: true,
      body: h`<div class="form-grid">
        <div class="full">${BT.f.select({ name: 'emp', label: 'الموظف', required: true, value: e && e.id, options: list.map(function (x) { return { v: x.id, t: x.name + ' · ' + x.id }; }) })}</div>
        ${BT.f.select({ name: 'type', label: 'النوع', required: true, options: ['مخالفة مرورية', 'حادث', 'سلفة', 'فقدان معدات', 'أخرى'] })}
        ${BT.f.money({ name: 'total', label: 'المبلغ الإجمالي', required: true, min: 0.25 })}
        ${BT.f.select({ name: 'n', label: 'عدد الأقساط', value: '1', placeholder: false, options: ['1', '2', '3', '4', '5', '6'] })}
        ${BT.f.select({ name: 'start', label: 'يبدأ من', value: 'نوفمبر 2026', placeholder: false, options: ['نوفمبر 2026', 'ديسمبر 2026', 'يناير 2027'] })}
        ${BT.f.textarea({ name: 'why', label: 'التفاصيل', required: true, full: true, rows: 2 })}
        ${BT.f.upload({ name: 'att', label: 'مرفق (مخالفة، فاتورة…)', optional: true, full: true })}
        <div class="full" id="dd-prev"></div></div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إرسال للاعتماد', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) {
        var x = emp(f.emp);
        D.deductions.push({ id: 'DD-' + (300 + D.deductions.length), empId: x.id, driver: x.name, reason: f.type, total: f.total, count: +f.n, paid: 0, per: BT.round3(f.total / f.n), start: f.start, status: 'بانتظار الاعتماد' });
        BT.toast('أُرسل الخصم للاعتماد', { sub: x.name + ' · ' + fmt.kwd(f.total) + ' على ' + f.n + ' قسط' }); if (A.router.current === 'payroll') A.go('payroll?tab=deductions');
      }
    });
    function prev() {
      var x = emp(d.el.querySelector('[name=emp]').value), total = Number((d.el.querySelector('[name=total]').value || '0').replace(/,/g, '')), n = +d.el.querySelector('[name=n]').value;
      if (!x || !total) { BT.render(d.el.querySelector('#dd-prev'), ''); return; }
      var per = total / n, max = x.basic * cfg.maxDeductionPct / 100;
      BT.render(d.el.querySelector('#dd-prev'), h`<div class="highlight-box between"><span>القسط الشهري</span><b>${BT.amt(per)}</b></div>${per > max ? h`<div class="banner warn mt-8 fs-sm">${icon('triangle-alert', 15)}<div>أعلى من الحد الأقصى للخصم (${cfg.maxDeductionPct}% = ${fmt.kwd(max)} د.ك). الزيادة تُرحّل للشهر التالي تلقائياً.</div></div>` : ''}`);
    }
    BT.on(d.el, 'input', '[name=total]', prev); BT.on(d.el, 'change', 'select', prev);
  };
})();
