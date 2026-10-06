/* =====================================================================
   app/pages/payroll.js — الرواتب: كشوف المنصات الشهرية (لقطات الشاشة والأيام
   الصالحة من السائق، ومراجعة المكتب)، كشوف الرواتب (تحضير، اعتماد، إعادة فتح،
   دفع، وتصدير Excel بأعمدة العميل)، والمنصات (قاعدة الدفع وأعمدة الكشف من نموذج
   العميل).
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  var COUNTS = [['working_days', 'أيام الدوام'], ['valid_days', 'الأيام الصالحة'], ['orders', 'الطلبات'], ['hours', 'الساعات']];
  var AMOUNTS = [['bonus', 'البونص'], ['tips', 'البقشيش'], ['cancelled_orders', 'خصومات الطلبات الملغاة'], ['platform_deductions', 'خصومات المنصة'], ['late', 'خصم التأخير'], ['cash_shortage', 'خصم الكاش']];
  var ST_TONE = { submitted: 'o', approved: 'g', rejected: 'r' };
  var RUN_TONE = { draft: 'o', approved: 'g', paid: 'b' };
  var BLOCKING = ['statement_missing', 'statement_pending', 'net_negative'];
  var IDENTITY = ['platform_driver_id', 'name', 'job_title', 'civil_id', 'iban', 'bank_name', 'payment_method', 'blank'];

  var plats = null;
  A.platforms = function (force) {
    if (!plats || force) plats = api.get('/payroll/platforms').then(function (r) { A._platList = r; return r; }, function (e) { plats = null; throw e; });
    return plats;
  };
  A.platformName = function (list, id) { var p = (list || []).find(function (x) { return x.id === id; }); return p ? api.name(p.name) : '—'; };
  function thisMonth() { return BT.config.today.slice(0, 7); }
  function monthLabel(iso) { var m = String(iso).split('-'); return fmt.month(+m[0], +m[1]); }
  function amt(v) { return v == null ? '—' : BT.amt(Number(v)); }
  function flagPills(flags) { return h`${(flags || []).map(function (f) { return BT.pill(api.t('line_flag', f), BLOCKING.indexOf(f) >= 0 ? 'r' : f === 'carried' ? 'b' : 'o'); })}`; }
  function allEmployees(params) {
    var out = [];
    function page(offset) {
      return api.get('/employees', Object.assign({ limit: 200, offset: offset }, params)).then(function (rows) {
        out = out.concat(rows);
        return rows.length === 200 && offset < 1800 ? page(offset + 200) : out;
      });
    }
    return page(0);
  }

  BT.pages['payroll'] = function (p, q) {
    A.setTitle('الرواتب');
    var v = A.view();
    var tabs = [];
    if (api.can('payroll.view')) tabs.push(['statements', 'كشوف المنصات'], ['runs', 'كشوف الرواتب']);
    if (api.can('payroll.view') || api.can('settings.update')) tabs.push(['platforms', 'المنصات']);
    if (!tabs.length) { BT.render(v, A.forbidden()); return; }
    var tab = tabs.some(function (t) { return t[0] === q.tab; }) ? q.tab : tabs[0][0];
    BT.render(v, h`${A.head('الرواتب', 'كشف المنصة الشهري لكل سائق، ثم كشف الرواتب لكل شركة وشهر بأعمدة نموذجكم، والحد الأقصى للخصم وترحيل الباقي')}
      ${BT.tabs('pay', tabs.map(function (t) { return [t[0], t[1]]; }), tab, 'tabs-line')}
      ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="pay" class="${t[0] === tab ? 'active' : ''}"><div data-p="${t[0]}"></div></div>`; })}`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      ({ statements: statementsPanel, runs: runsPanel, platforms: platformsPanel })[t](v.querySelector('[data-p="' + t + '"]'), q);
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/payroll?tab=' + e.detail); });
    show(tab);
  };

  /* ================= كشوف المنصات ================= */
  function statementsPanel(el, q) {
    var month = q.month || thisMonth(), list = [];
    BT.render(el, h`<div class="card"><div class="flex gap-8 items-end wrap mb-12">
        <div class="field" style="max-width:200px"><label for="f-st-month">الشهر</label><input class="input" type="month" id="f-st-month" value="${month}"></div>
        <span class="spacer"></span>${api.can('payroll.prepare') ? A.btn('إدخال كشف من المكتب', { icon: 'plus', cls: 'btn-outline', id: 'st-new' }) : ''}</div>
        <div class="banner note fs-sm mb-12">${icon('info', 15)}<div>لقطة الشاشة دليل يرفعه السائق نفسه: قارن الأرقام باللقطات، وبتقرير المنصة للشركاء إن وُجد، قبل الاعتماد. الرواتب لا تستخدم إلا الكشوف المعتمدة.</div></div>
        <div data-t></div></div>`);
    A.platforms().then(function (r) { list = r; t.refresh(); }, function () {});
    var t = BT.table(el.querySelector('[data-t]'), {
      fetch: function (s) { return api.get('/payroll/statements', { month: month + '-01', status: s.chip === 'all' ? null : s.chip, limit: s.limit, offset: s.offset }); },
      chips: { value: 'submitted', all: false, options: [{ v: 'submitted', t: 'بانتظار المراجعة' }, { v: 'approved', t: 'المعتمدة' }, { v: 'rejected', t: 'المرفوضة' }, { v: 'all', t: 'الكل' }] },
      columns: [
        { key: 'employee', label: 'السائق', render: function (s) { return A.person(s.employee); } },
        { key: 'platform', label: 'المنصة', render: function (s) { return s.platform ? api.name(s.platform.name) : '—'; } },
        { key: 'declared', label: 'ما أرسله السائق', render: function (s) { var d = s.declared || {}; return Object.keys(d).length ? h`${Object.keys(d).map(function (k) { return h`<span class="sub">${api.t('driver_field', k)}: <b class="num">${d[k]}</b></span>`; })}` : h`<span class="muted fs-sm">${s.from_driver ? '—' : 'أُدخل من المكتب'}</span>`; } },
        { key: 'valid_days', label: 'المعتمد', render: function (s) { return s.status === 'approved' ? h`${s.valid_days != null ? h`<span class="num">${s.valid_days}</span> يوم صالح` : ''}${s.working_days != null ? h`<span class="sub">من ${s.working_days} يوم دوام</span>` : ''}` : '—'; } },
        { key: 'status', label: 'الحالة', render: function (s) { return h`${BT.pill(api.t('statement_status', s.status), ST_TONE[s.status])}${s.locked ? h` ${BT.pill('الشهر مقفل', 'n')}` : ''}`; } },
        { key: 'submitted_at', label: 'الإرسال', render: function (s) { return h`<span class="num">${fmt.dt(s.submitted_at)}</span>`; } }
      ],
      rowClick: function (s) { statementView(s.id, function () { t.refresh(); A.refreshCounts && A.refreshCounts(); }); },
      empty: { icon: 'file-text', title: 'لا توجد كشوف هنا', text: 'يرسل السائق كشف الشهر من التطبيق: لقطات من تطبيق المنصة والأيام الصالحة' }
    });
    el.querySelector('#f-st-month').addEventListener('change', function (e) { month = e.target.value || thisMonth(); t.refresh(); });
    var add = el.querySelector('#st-new');
    if (add) add.onclick = function () { officeStatement(month, function () { t.refresh(); }); };
  }

  function figureFields(s, platform) {
    var counts = COUNTS.map(function (c) { return BT.f.input({ name: c[0], label: c[1], value: s[c[0]] == null ? '' : s[c[0]], num: true, optional: true, hint: c[0] === 'working_days' ? 'فارغ = ما سجله النظام (التقارير اليومية وبدء اليوم)' : c[0] === 'orders' ? 'فارغ = طلبات التقارير اليومية المعتمدة' : '' }); });
    var amounts = AMOUNTS.map(function (c) { return BT.f.money({ name: c[0], label: c[1], value: s[c[0]] != null && Number(s[c[0]]) ? s[c[0]] : '', optional: true }); });
    return h`<div class="section-t">أرقام المنصة للشهر</div><div class="form-grid">${counts}</div><div class="section-t mt-12">من تسوية المنصة</div><div class="form-grid">${amounts}</div>${BT.f.input({ name: 'note', label: 'ملاحظة', optional: true, value: '' })}`;
  }
  function figuresOf(vals) {
    var out = {};
    COUNTS.forEach(function (c) { var x = vals[c[0]]; out[c[0]] = x === '' || x == null ? null : (c[0] === 'hours' ? String(x) : Math.round(Number(x))); });
    AMOUNTS.forEach(function (c) { var x = vals[c[0]]; out[c[0]] = x === '' || x == null ? '0.000' : Number(x).toFixed(3); });
    out.note = vals.note || null;
    return out;
  }

  function statementView(id, done) {
    api.get('/payroll/statements/' + id).then(function (s) {
      var editable = !s.locked && s.status !== 'rejected' && api.can('payroll.prepare');
      var shots = s.screenshots.map(function (sha, i) { return { src: api.url('/payroll/statements/' + s.id + '/files/' + sha), caption: 'لقطة ' + (i + 1) }; });
      var d = s.declared || {}, sys = s.system || {};
      var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
      if (editable && s.status === 'submitted') btns.push({ label: 'رفض', cls: 'btn-ghost', icon: 'ban', close: false, onClick: function (dlg) {
        A.confirmRun({ title: 'رفض الكشف', message: 'يعود للسائق بالسبب ليرسله من جديد.', tone: 'danger', confirmText: 'رفض', reason: { label: 'السبب (يراه السائق)', required: true }, run: function (reason) { return api.post('/payroll/statements/' + s.id + '/reject', { reason: reason }); }, done: 'رُفض الكشف', after: function () { dlg.close(); done(); } });
      } });
      if (editable) btns.push({ label: s.status === 'approved' ? 'حفظ التصحيح' : 'اعتماد', cls: 'btn-primary', icon: 'check', close: false, onClick: function (dlg) {
        var form = dlg.panel.querySelector('form[data-fig]');
        if (!BT.form.validate(form)) return;
        api.post('/payroll/statements/' + s.id + '/approve', figuresOf(BT.form.values(form))).then(function () { BT.toast('اعتُمد الكشف'); dlg.close(); done(); }, api.fail);
      } });
      BT.drawer.open({
        title: 'كشف ' + monthLabel(s.month), subtitle: api.name(s.employee.name) + (s.platform ? ' · ' + api.name(s.platform.name) : ''), icon: 'file-text', size: 'lg',
        body: h`<div class="flex gap-8 wrap mb-12">${BT.pill(api.t('statement_status', s.status), ST_TONE[s.status], true)}${s.locked ? BT.pill('رواتب الشهر معتمدة: لا يتغير', 'n') : ''}${s.from_driver ? BT.pill('من تطبيق السائق', 'b') : BT.pill('أُدخل من المكتب', 'n')}</div>
          ${s.review_note ? h`<div class="banner ${s.status === 'rejected' ? 'danger' : 'note'} fs-sm mb-12">${icon('message-square', 15)}<div>${s.review_note}${s.reviewed_by ? ' — ' + s.reviewed_by : ''}</div></div>` : ''}
          ${s.from_driver ? h`<div class="section-t">لقطات الشاشة</div>${A.thumbs(shots)}` : ''}
          <div class="table-wrap mt-12"><table class="t compact"><thead><tr><th></th><th class="num">السائق</th><th class="num">النظام</th><th class="num">المعتمد</th></tr></thead><tbody>
            ${COUNTS.map(function (c) { return h`<tr><td>${c[1]}</td><td class="num">${d[c[0]] != null ? d[c[0]] : '—'}</td><td class="num">${sys[c[0]] != null ? sys[c[0]] : '—'}</td><td class="num">${s.status === 'approved' && s[c[0]] != null ? s[c[0]] : '—'}</td></tr>`; })}
          </tbody></table></div>
          <div class="muted fs-sm mt-4">«النظام» = أيام فيها تقرير يومي أو بدء يوم من التطبيق، وطلبات التقارير اليومية المعتمدة.</div>
          ${editable ? h`<form data-fig class="form mt-16" novalidate>${figureFields(s.status === 'approved' ? s : Object.assign({}, s, { working_days: s.working_days }), s.platform)}</form>` : h`<div class="section-t mt-16">المبالغ</div>${BT.kv(AMOUNTS.map(function (c) { return [c[1], amt(s[c[0]])]; }))}`}`,
        buttons: btns
      });
    }, api.fail);
  }

  function officeStatement(month, done) {
    allEmployees({ is_driver: true }).then(function (rows) {
      A.formModal({
        title: 'إدخال كشف من المكتب', subtitle: 'من تقرير المنصة: يُعتمد مباشرة', icon: 'file-plus', size: 'lg', done: 'سُجّل الكشف',
        body: h`<div class="form-grid"><div class="full">${A.picker({ name: 'employee', label: 'السائق', required: true, items: rows.map(function (e) { return { id: e.id, label: api.name(e.name) + ' — ' + e.employee_number + (e.platform_driver_id ? ' — ' + e.platform_driver_id : '') }; }) })}</div>
          ${BT.f.input({ name: 'month', label: 'الشهر', type: 'month', required: true, value: month })}</div>${figureFields({}, null)}`,
        submit: function (v) { return api.post('/payroll/statements', Object.assign(figuresOf(v), { employee_id: A.picked('employee', v.employee), month: v.month + '-01' })); },
        after: done
      });
    }, api.fail);
  }

  /* ================= كشوف الرواتب ================= */
  function runsPanel(el) {
    BT.render(el, h`<div class="card"><div class="flex gap-8 items-center mb-12"><div class="muted fs-sm">كشف واحد لكل شركة وشهر. المسودة تُعاد حسابها متى شئت، والاعتماد يعيد الحساب مرة أخيرة ثم يقفل الشهر.</div><span class="spacer"></span>${api.can('payroll.prepare') ? A.btn('تحضير كشف رواتب', { icon: 'plus', cls: 'btn-primary', id: 'run-new' }) : ''}</div><div data-t></div></div>`);
    var t = BT.table(el.querySelector('[data-t]'), {
      fetch: function () { return api.get('/payroll/runs'); },
      columns: [
        { key: 'month', label: 'الشهر', render: function (r) { return h`<b>${monthLabel(r.month)}</b><span class="sub">${api.company(r.company_id)}</span>`; } },
        { key: 'lines', label: 'الموظفون', num: true, render: function (r) { return h`<span class="num">${r.totals.lines || 0}</span>`; } },
        { key: 'net', label: 'صافي الرواتب', num: true, render: function (r) { return amt(r.totals.net); } },
        { key: 'status', label: 'الحالة', render: function (r) { return h`${BT.pill(api.t('run_status', r.status), RUN_TONE[r.status])}${r.status === 'draft' && r.blocking ? h` ${BT.pill(r.blocking + ' سطر غير جاهز', 'r')}` : ''}`; } },
        { key: 'cap', label: 'حد الخصم', render: function (r) { return h`<span class="num">${Number(r.cap_percent)}%</span><span class="sub">من ${r.cap_base === 'basic' ? 'الأساسي' : 'المستحق'}</span>`; } }
      ],
      rowClick: function (r) { A.go('payroll/run/' + r.id); },
      empty: { icon: 'banknote', title: 'لا توجد كشوف رواتب بعد' }
    });
    var add = el.querySelector('#run-new');
    if (add) add.onclick = function () {
      A.formModal({
        title: 'تحضير كشف رواتب', icon: 'banknote', size: 'sm', done: false,
        body: h`<div class="form">${BT.f.select({ name: 'company_id', label: 'الشركة', required: true, options: api.companyOptions(), placeholder: false })}${BT.f.input({ name: 'month', label: 'الشهر', type: 'month', required: true, value: thisMonth() })}</div>`,
        submit: function (v) { return api.post('/payroll/runs', { company_id: +v.company_id, month: v.month + '-01' }); },
        after: function (r) { A.go('payroll/run/' + r.id); }
      });
    };
  }

  BT.pages['payroll/run/:id'] = function (p) {
    var id = p.id;
    A.setTitle('كشف الرواتب', [['الرواتب', 'payroll?tab=runs'], ['كشف الرواتب']]);
    var v = A.view();
    A.load(v, Promise.all([api.get('/payroll/runs/' + id), A.platforms()]), function (r) { return runView(r[0], r[1]); }).then(function (r) { if (r) wireRun(v, r[0], r[1]); }).catch(function () {});
  };
  function runView(run, list) {
    var T = run.totals || {}, byPlat = {};
    run.lines.forEach(function (l) { var k = l.platform_id || 0; (byPlat[k] = byPlat[k] || []).push(l); });
    var acts = [];
    if (run.status === 'draft' && api.can('payroll.prepare')) acts.push(A.btn('إعادة الحساب', { icon: 'refresh-cw', cls: 'btn-outline', id: 'run-recompute' }));
    if (api.can('payroll.export')) acts.push(A.btn(run.status === 'draft' ? 'تصدير مسودة Excel' : 'تصدير Excel', { icon: 'download', cls: 'btn-outline', id: 'run-export' }));
    if (run.status === 'approved' && api.can('payroll.unlock')) acts.push(A.btn('إعادة فتح', { icon: 'rotate-ccw', cls: 'btn-ghost', id: 'run-reopen' }));
    if (run.status === 'approved' && api.can('payroll.approve')) acts.push(A.btn('تسجيل الدفع', { icon: 'banknote', cls: 'btn-success', id: 'run-paid' }));
    if (run.status === 'draft' && api.can('payroll.approve')) acts.push(A.btn('اعتماد الكشف', { icon: 'check', cls: 'btn-primary', id: 'run-approve' }));
    return h`${A.head('رواتب ' + monthLabel(run.month) + ' — ' + api.company(run.company_id), h`${BT.pill(api.t('run_status', run.status), RUN_TONE[run.status], true)} حد الخصم ${Number(run.cap_percent)}% من ${run.cap_base === 'basic' ? 'الراتب الأساسي' : 'الراتب المستحق في الشهر'}${run.reopened ? ' · أُعيد فتحه ' + run.reopened + ' مرة' : ''}`, h`${acts}`)}
      ${run.status === 'draft' && run.blocking ? h`<div class="banner danger mb-12">${icon('circle-x', 16)}<div><b>${run.blocking} سطر غير جاهز للاعتماد</b>: كشف منصة ناقص أو بانتظار المراجعة، أو خصومات الشهر أكبر من المستحق. أكمل الكشوف ثم أعد الحساب.</div></div>` : ''}
      <div class="kpis mb-16">${BT.kpi({ label: 'الموظفون', value: fmt.int(T.lines || 0), dot: 'b' })}${BT.kpi({ label: 'إجمالي المستحق', value: fmt.money(T.gross), dot: 'g' })}${BT.kpi({ label: 'إجمالي الخصومات', value: fmt.money(T.deductions), dot: 'o' })}${BT.kpi({ label: 'صافي الرواتب', value: fmt.money(T.net), dot: 'p' })}</div>
      ${Object.keys(byPlat).sort(function (a, b) { return (+a === 0) - (+b === 0) || +a - +b; }).map(function (k) {
        var lines = byPlat[k];
        return h`<div class="card mb-12"><div class="card-h"><div class="card-t">${+k ? A.platformName(list, +k) : 'بدون منصة'}</div><span class="muted fs-sm">${lines.length} موظف · صافي ${fmt.money(lines.reduce(function (a, l) { return a + Number(l.net); }, 0))}</span></div>
          <div class="table-wrap"><table class="t compact"><thead><tr><th>الموظف</th><th class="num">المستحق</th><th class="num">الخصومات</th><th class="num">الصافي</th><th>ملاحظات</th></tr></thead><tbody>${lines.map(function (l) {
            return h`<tr class="clickable" data-line="${l.employee.id}"><td>${A.person(l.employee, l.cells.platform_driver_id || '')}</td><td class="num">${amt(l.gross)}</td><td class="num">${amt(l.deductions)}</td><td class="num"><b>${amt(l.net)}</b></td><td>${flagPills(l.flags)}</td></tr>`;
          })}</tbody></table></div></div>`;
      })}`;
  }
  function lineView(run, line, list) {
    var platform = (list || []).find(function (p) { return p.id === line.platform_id; });
    var cols = platform && platform.columns.length ? platform.columns : Object.keys(line.cells).filter(function (c) { return c !== 'blank'; }).map(function (c) { return { code: c, header: api.t('payroll_column', c) }; });
    function val(code) {
      var x = line.cells[code];
      if (x == null || x === '') return '—';
      if (code === 'payment_method') return api.t('payment_method', x);
      if (/^-?\d+\.\d{3}$/.test(String(x))) return BT.amt(Number(x));
      return h`<span class="num">${x}</span>`;
    }
    BT.drawer.open({
      title: api.name(line.employee.name), subtitle: (platform ? api.name(platform.name) + ' · ' : '') + monthLabel(run.month), icon: 'receipt-text',
      body: h`${line.flags.length ? h`<div class="flex gap-8 wrap mb-12">${flagPills(line.flags)}</div>` : ''}${BT.kv(cols.filter(function (c) { return c.code !== 'blank'; }).map(function (c) { return [c.header, val(c.code)]; }).concat([['مُرحَّل للشهر القادم', amt(line.cells.carried)]]))}`,
      buttons: [{ label: 'إغلاق', cls: 'btn-ghost' }]
    });
  }
  function wireRun(v, run, list) {
    var reload = function () { A.router.refresh(); };
    BT.on(v, 'click', '[data-line]', function (e, tr) { var l = run.lines.find(function (x) { return x.employee.id === tr.getAttribute('data-line'); }); if (l) lineView(run, l, list); });
    function act(id, fn) { var b = v.querySelector('#' + id); if (b) b.onclick = fn; }
    act('run-recompute', function (e) { var b = e.currentTarget; b.classList.add('is-loading'); api.post('/payroll/runs/' + run.id + '/recompute').then(function () { BT.toast('أُعيد الحساب'); reload(); }, function (err) { b.classList.remove('is-loading'); api.fail(err); }); });
    act('run-export', function () { A.download('/payroll/runs/' + run.id + '/export'); });
    act('run-approve', function () {
      A.confirmRun({ title: 'اعتماد كشف الرواتب', message: 'يُعاد الحساب مرة أخيرة ثم يُقفل الكشف وكشوف المنصات لهذا الشهر، ويصبح كشف الراتب ظاهراً لكل سائق في التطبيق.', confirmText: 'اعتماد', tone: 'success', run: function () { return api.post('/payroll/runs/' + run.id + '/approve'); }, done: 'اعتُمد كشف الرواتب' }).then(function (res) { if (res !== null) reload(); });
    });
    act('run-reopen', function () {
      A.confirmRun({ title: 'إعادة فتح الكشف', message: 'يعود مسودة وتُفتح كشوف المنصات للشهر. يُسجَّل السبب في سجل التدقيق.', confirmText: 'إعادة فتح', tone: 'danger', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/payroll/runs/' + run.id + '/reopen', { reason: reason }); }, done: 'أُعيد فتح الكشف', after: reload });
    });
    act('run-paid', function () {
      A.formModal({ title: 'تسجيل دفع الرواتب', icon: 'banknote', size: 'sm', done: 'سُجّل الدفع', body: h`<div class="form">${BT.f.input({ name: 'payment_ref', label: 'مرجع التحويل البنكي', optional: true })}</div>`, submit: function (x) { return api.post('/payroll/runs/' + run.id + '/paid', { payment_ref: x.payment_ref || null }); }, after: reload });
    });
  }

  /* ================= المنصات ================= */
  var RULE_HINT = 'الصافي = الأساسي (إن كانت المنصة تدفعه) + الطلبات × السعر + الساعات × السعر + الأيام الصالحة × السعر + البونص والبقشيش − الأيام غير الصالحة − خصومات الشهر − الأقساط (بحد الخصم)';
  function platformsPanel(el) {
    var canEdit = api.can('settings.update');
    A.load(el, A.platforms(true), function (list) {
      setTimeout(function () {
        var b = el.querySelector('#plat-template'); if (b) b.onclick = function () { fromTemplate(function () { platformsPanel(el); }); };
        BT.on(el, 'click', '[data-edit]', function (e, x) { var p = list.find(function (y) { return y.id === +x.getAttribute('data-edit'); }); platformForm(p, null, function () { platformsPanel(el); }); });
      });
      return h`<div class="flex gap-8 items-center mb-12"><div class="muted fs-sm">${RULE_HINT}</div><span class="spacer"></span>${canEdit ? A.btn('منصة جديدة من نموذج Excel', { icon: 'file-spreadsheet', cls: 'btn-primary', id: 'plat-template' }) : ''}</div>
        ${list.length ? h`<div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(360px,1fr))">${list.map(function (p) {
          return h`<div class="card"><div class="card-h"><div class="card-t">${api.name(p.name)}</div><span class="muted fs-sm ltr">${p.code}</span>${p.is_active ? '' : BT.pill('موقوفة', 'n')}${canEdit ? h`<button type="button" class="btn btn-sm btn-ghost ms-auto" data-edit="${p.id}">${icon('pencil', 14)} تعديل</button>` : ''}</div>
            <div class="card-b">${BT.kv([
              ['السائقون', fmt.int(p.drivers)],
              ['التقرير اليومي', (p.daily_fields || []).length ? p.daily_fields.map(function (f) { return api.t('daily_field', f); }).join('، ') : 'لقطة الشاشة فقط'],
              ['كشف الشهر من السائق', p.driver_fields.length ? p.driver_fields.map(function (f) { return api.t('driver_field', f); }).join('، ') + ' مع لقطات الشاشة' : 'لا يُطلب: الشهر من التقارير اليومية المعتمدة'],
              ['الراتب الأساسي', p.pay_basic ? 'يُدفع' : 'لا يُدفع'],
              ['الأسعار', 'طلب ' + fmt.money(p.per_order) + ' · ساعة ' + fmt.money(p.per_hour) + ' · يوم صالح ' + fmt.money(p.per_valid_day)],
              ['الأيام غير الصالحة', api.t('invalid_days_rule', p.invalid_days) + (p.invalid_days === 'daily_wage' ? ' (÷ ' + p.day_divisor + ')' : p.invalid_days === 'fixed' ? ' ' + fmt.money(p.invalid_day_amount) : '')],
              ['أعمدة الكشف', p.columns.length ? p.columns.length + ' عموداً: ' + p.columns.slice(0, 4).map(function (c) { return c.header; }).join('، ') + '…' : 'كل الأعمدة (لا نموذج)']
            ])}</div></div>`;
        })}</div>` : h`<div class="card"><div class="card-b">${BT.empty('banknote', 'لا توجد منصات بعد', 'ارفع نموذج كشف الرواتب الذي تستخدمونه (Excel): كل ورقة فيه تصبح منصة بأعمدتها وترتيبها.')}</div></div>`}`;
    }).catch(function () {});
  }
  function fromTemplate(done) {
    A.formModal({
      title: 'منصة من نموذج كشف الرواتب', icon: 'file-spreadsheet', size: 'sm', submitText: 'قراءة النموذج', done: false,
      body: h`<div class="form">${BT.f.upload({ name: 'file', label: 'نموذج Excel', accept: '.xlsx', accept_label: 'كل ورقة بصف عناوين = منصة', required: true })}</div>`,
      submit: function (v) { return api.uploadForm('/payroll/platforms/template', v.file[0]); },
      after: function (sheets) {
        if (!sheets.length) { BT.toast('لم يُعثر على ورقة بعناوين أعمدة في الملف', { type: 'error' }); return; }
        (function next(i) { if (i < sheets.length) platformForm(null, sheets[i], function () { next(i + 1); }); else done(); })(0);
      }
    });
  }
  function columnRows(cols) {
    var codes = Object.keys(api.cat.payroll_column || {}).length ? Object.keys(api.cat.payroll_column) : ['platform_driver_id', 'name', 'job_title', 'civil_id', 'iban', 'bank_name', 'payment_method', 'basic', 'hours', 'orders', 'working_days', 'valid_days', 'bonus', 'tips', 'gross', 'invalid_days_deduction', 'car_repair', 'traffic_fines', 'cancelled_orders', 'platform_deductions', 'sim', 'advance', 'cash_shortage', 'late', 'other_deductions', 'carried', 'net', 'blank'];
    return h`${cols.map(function (c, i) { return h`<tr><td class="num">${i + 1}</td><td><input class="input" data-col-h="${i}" value="${c.header}" maxlength="80"></td><td><select class="select" data-col-c="${i}">${codes.map(function (k) { return h`<option value="${k}"${k === c.code ? raw(' selected') : ''}>${api.t('payroll_column', k)}</option>`; })}</select></td></tr>`; })}`;
  }
  function platformForm(p, sheet, done) {
    var editing = !!p;
    p = p || { code: '', name: { ar: sheet.suggested_name, en: '' }, driver_fields: sheet.driver_fields, daily_fields: ['orders', 'cash'], pay_basic: true, per_order: '0.000', per_hour: '0.000', per_valid_day: '0.000', invalid_days: sheet.invalid_days, invalid_day_amount: null, day_divisor: 30, columns: sheet.columns };
    var cols = p.columns.map(function (c) { return { code: c.code, header: c.header }; });
    var unknown = cols.filter(function (c) { return c.code === 'blank'; }).length;
    A.formModal({
      title: editing ? 'تعديل المنصة' : 'منصة جديدة' + (sheet ? ': ' + sheet.sheet : ''), icon: 'banknote', size: 'lg', done: editing ? 'حُفظت المنصة' : 'أُضيفت المنصة',
      body: h`<div class="form-grid">
          ${editing ? '' : BT.f.input({ name: 'code', label: 'الرمز', required: true, value: p.code, pattern: '[a-z][a-z0-9_]{1,30}', msg: 'حروف إنجليزية صغيرة وأرقام وشرطة سفلية', hint: 'لا يتغير بعد الحفظ' })}
          ${BT.f.input({ name: 'name_ar', label: 'الاسم بالعربية', required: true, value: p.name.ar || '' })}
          ${BT.f.input({ name: 'name_en', label: 'الاسم بالإنجليزية', required: true, value: p.name.en || '' })}
          ${editing ? BT.f.switch({ name: 'is_active', label: 'نشطة', checked: p.is_active }) : ''}
        </div>
        <div class="section-t mt-12">ما يرسله السائق في تقريره اليومي مع لقطة شاشة يومه من تطبيق المنصة</div>
        <div class="flex gap-12 wrap">${['orders', 'cash', 'valid_day'].map(function (f) { return BT.f.check({ name: 'dy_' + f, label: api.t('daily_field', f), checked: (p.daily_fields || []).indexOf(f) >= 0 }); })}</div>
        <div class="hint">الطلبات والأيام الصالحة في الشهر تُجمع من التقارير اليومية المعتمدة؛ وتقرير لم يُراجع يوقف رواتب صاحبه حتى يُراجع.</div>
        <div class="section-t mt-12">ما يرسله السائق كل شهر مع لقطات الشاشة (اتركه فارغاً إن كان الشهر من التقارير اليومية)</div>
        <div class="flex gap-12 wrap">${['valid_days', 'orders', 'hours'].map(function (f) { return BT.f.check({ name: 'df_' + f, label: api.t('driver_field', f), checked: p.driver_fields.indexOf(f) >= 0 }); })}</div>
        <div class="section-t mt-12">قاعدة الدفع</div>
        <div class="banner note fs-sm mb-8">${icon('info', 15)}<div>نموذجكم لا يذكر كيف يُحسب المستحق، فاضبطوا القاعدة هنا. ${RULE_HINT}</div></div>
        <div class="form-grid">
          ${BT.f.switch({ name: 'pay_basic', label: 'يُدفع الراتب الأساسي للموظف', checked: p.pay_basic })}
          ${BT.f.money({ name: 'per_order', label: 'لكل طلب', value: p.per_order })}
          ${BT.f.money({ name: 'per_hour', label: 'لكل ساعة', value: p.per_hour })}
          ${BT.f.money({ name: 'per_valid_day', label: 'لكل يوم صالح', value: p.per_valid_day })}
          ${BT.f.select({ name: 'invalid_days', label: 'الأيام غير الصالحة (أيام الدوام − الصالحة)', value: p.invalid_days, placeholder: false, options: ['none', 'daily_wage', 'fixed'].map(function (k) { return { v: k, t: api.t('invalid_days_rule', k) }; }) })}
          ${BT.f.input({ name: 'day_divisor', label: 'قاسم أجر اليوم', value: p.day_divisor, num: true, hint: 'أجر اليوم = الأساسي ÷ هذا الرقم' })}
          ${BT.f.money({ name: 'invalid_day_amount', label: 'المبلغ الثابت لليوم', value: p.invalid_day_amount || '', optional: true })}
        </div>
        <div class="section-t mt-12">أعمدة كشف الراتب (بترتيب نموذجكم)</div>
        ${unknown ? h`<div class="banner warn fs-sm mb-8">${icon('triangle-alert', 15)}<div>${unknown} عمود لم يُعرف معناه: اختر له المعنى أو اتركه «عمود فارغ».</div></div>` : ''}
        <div class="table-wrap"><table class="t compact"><thead><tr><th class="num">#</th><th>العنوان في الكشف</th><th>ما يحتويه</th></tr></thead><tbody data-cols>${columnRows(cols)}</tbody></table></div>`,
      submit: function (v, dlg) {
        var panel = dlg && dlg.panel ? dlg.panel : document;
        var columns = cols.map(function (c, i) { return { header: (panel.querySelector('[data-col-h="' + i + '"]') || {}).value || c.header, code: (panel.querySelector('[data-col-c="' + i + '"]') || {}).value || c.code }; });
        var body = {
          name: Object.assign({}, p.name, { ar: v.name_ar, en: v.name_en }),
          driver_fields: ['valid_days', 'orders', 'hours'].filter(function (f) { return v['df_' + f]; }),
          daily_fields: ['orders', 'cash', 'valid_day'].filter(function (f) { return v['dy_' + f]; }),
          pay_basic: !!v.pay_basic, per_order: Number(v.per_order || 0).toFixed(3), per_hour: Number(v.per_hour || 0).toFixed(3), per_valid_day: Number(v.per_valid_day || 0).toFixed(3),
          invalid_days: v.invalid_days, day_divisor: Math.round(Number(v.day_divisor || 30)), invalid_day_amount: v.invalid_day_amount === '' || v.invalid_day_amount == null ? null : Number(v.invalid_day_amount).toFixed(3),
          columns: columns
        };
        if (editing) return api.patch('/payroll/platforms/' + p.id, Object.assign(body, { version: p.version, is_active: !!v.is_active }));
        return api.post('/payroll/platforms', Object.assign(body, { code: v.code }));
      },
      after: function () { A.platforms(true); done(); }
    });
  }

  /* ================= خصم يدوي: سلفة أو شريحة هاتف ================= */
  A.manualDeduction = function (done) {
    allEmployees({}).then(function (rows) {
      A.formModal({
        title: 'خصم جديد', subtitle: 'سلفة أو شريحة هاتف أو غيرها، بأقساط شهرية', icon: 'minus-circle', done: 'سُجّل الخصم',
        body: h`<div class="form-grid"><div class="full">${A.picker({ name: 'employee', label: 'الموظف', required: true, items: rows.map(function (e) { return { id: e.id, label: api.name(e.name) + ' — ' + e.employee_number }; }) })}</div>
          ${BT.f.select({ name: 'source_type', label: 'النوع', required: true, placeholder: false, options: ['advance', 'sim', 'other'].map(function (k) { return { v: k, t: api.t('deduction_source', k) }; }) })}
          ${BT.f.input({ name: 'reason', label: 'السبب (يظهر في كشف الراتب)', required: true })}
          ${BT.f.money({ name: 'total', label: 'الإجمالي', required: true })}
          ${BT.f.input({ name: 'installments', label: 'عدد الأقساط', value: 1, num: true, required: true })}
          ${BT.f.input({ name: 'start', label: 'أول شهر', type: 'month', value: thisMonth(), required: true })}</div>`,
        submit: function (v) { return api.post('/deductions', { employee_id: A.picked('employee', v.employee), source_type: v.source_type, reason: v.reason, total: Number(v.total).toFixed(3), installments: Math.round(Number(v.installments)), start_month: v.start + '-01' }); },
        after: done
      });
    }, api.fail);
  };
})();
