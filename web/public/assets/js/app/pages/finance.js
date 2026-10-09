/* =====================================================================
   app/pages/finance.js — المالية: المصروفات (بأنواعها، مرتبطة بسيارة أو موظف أو مركز،
   تُدفع فوراً أو لاحقاً)، والقيود التي ينشئها النظام من المستندات على دليل حسابات
   محاسب العميل (مسودة ← اعتماد ← لا تتغير، والتصحيح بقيد عكسي)، وتصديرها،
   وميزان المراجعة، ودليل الحسابات وربط الأدوار وأنواع المصروفات.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  A.tone.expense_status = { pending: 'o', approved: 'g', rejected: 'r', cancelled: 'n' };
  A.tone.entry_status = { draft: 'o', approved: 'g' };
  var ROLES = ['treasury', 'bank', 'driver_cash', 'cod_clearing', 'suppliers_payable', 'salaries_expense', 'salaries_payable',
    'employee_receivable', 'payroll_recovery', 'maintenance_expense', 'traffic_fines_expense', 'deduction_accident',
    'deduction_fine', 'deduction_advance', 'deduction_sim', 'deduction_other', 'cash_adjustments', 'cash_writeoff', 'opening_equity',
    'driver_salaries_expense', 'fuel_expense'];
  var CLASSES = ['1', '2', '3', '4', '5', '6'];

  function amt(v) { return v == null ? '—' : BT.amt(Number(v)); }
  function money(v) { return v == null || Number(v) === 0 ? '' : fmt.money(v); }
  function month() {
    var first = BT.config.today.slice(0, 8) + '01', p = first.split('-'), y = +p[0], m = +p[1] + 1;
    if (m > 12) { m = 1; y++; }
    return { from: first, to: BT.date.add(y + '-' + (m < 10 ? '0' : '') + m + '-01', -1) };
  }
  // how the books are kept (settings «المحاسبة»): fetched once per visit of the page
  var cfg = null;
  function config() { return api.get('/finance/config').then(function (c) { cfg = c; return c; }); }
  function fiscalRange() { return { from: cfg && cfg.fiscal_year_start ? cfg.fiscal_year_start : month().from, to: BT.config.today }; }
  function accountLabel(a) { return a.code + ' · ' + api.name(a.name); }
  function err(code, params) {
    params = Object.assign({}, params || {});
    if (params.role) params.role = api.t('finance_role', params.role);
    return api.t('errors', code, params, code);
  }
  function rangeTools(r, extra) {
    return h`<input class="input" type="date" data-from value="${r.from}" aria-label="من" title="من">
      <input class="input" type="date" data-to value="${r.to}" aria-label="إلى" title="إلى">${extra || ''}`;
  }
  function wireRange(el, r, reload) {
    el.addEventListener('change', function (e) {
      if (!e.target.matches('[data-from],[data-to]')) return;
      var from = el.querySelector('[data-from]').value, to = el.querySelector('[data-to]').value;
      if (!from || !to) return;
      if (to < from) { BT.toast('تاريخ النهاية قبل البداية', { type: 'error' }); return; }
      r.from = from; r.to = to; reload();
    });
  }

  BT.pages['finance'] = function (p, q) {
    A.setTitle('المالية');
    var v = A.view();
    var tabs = [['expenses', 'المصروفات'], ['entries', 'القيود'], ['balance', 'ميزان المراجعة'], ['chart', 'دليل الحسابات'], ['periods', 'إقفال الشهور']];
    var tab = tabs.some(function (t) { return t[0] === q.tab; }) ? q.tab : 'expenses';
    BT.render(v, h`${A.head('المالية', 'المصروفات، والقيود التي ينشئها النظام من المستندات على دليل حسابات محاسبكم: تُعتمد ثم لا تتغير، والتصحيح بقيد عكسي',
        api.can('finance.create') ? A.btn('تسجيل مصروف', { icon: 'plus', cls: 'btn-primary', action: 'expense-new' }) : '')}
      ${BT.tabs('fin', tabs, tab, 'tabs-line')}
      ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="fin" class="${t[0] === tab ? 'active' : ''}"><div id="fin-${t[0]}"></div></div>`; })}`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      var el = document.getElementById('fin-' + t);
      if (t === 'expenses') expensesPanel(el, q.chip);
      if (t === 'entries') entriesPanel(el);
      if (t === 'balance') config().then(function () { balancePanel(el); }, function () { balancePanel(el); });
      if (t === 'chart') chartPanel(el);
      if (t === 'periods') periodsPanel(el, q.month);
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/finance?tab=' + e.detail); });
    show(tab);
  };
  BT.actions['expense-new'] = function () { newExpense(function () { A.refreshIfAt('finance'); A.refreshCounts(); }); };

  /* ================= المصروفات ================= */
  var CHIPS = { pending: { status: 'pending' }, unpaid: { unpaid: true }, approved: { status: 'approved' }, rejected: { status: 'rejected' }, cancelled: { status: 'cancelled' } };
  function expenseStatus(e) { return h`${A.pill('expense_status', e.status)}${e.unpaid ? h` ${BT.pill('غير مسدد', 'o')}` : ''}`; }
  function links(e) {
    return [e.vehicle ? BT.plate(e.vehicle.plate_number) : '', e.employee ? api.name(e.employee.name) : '', e.center ? e.center.name : ''].filter(Boolean);
  }
  function expensesPanel(el, chip) {
    BT.render(el, h`<div class="card"><div data-t></div></div>`);
    var t = BT.table(el.querySelector('[data-t]'), {
      fetch: function (s) { return api.get('/finance/expenses', Object.assign({ limit: s.limit, offset: s.offset }, CHIPS[s.chip] || {})); },
      chips: { value: chip || 'pending', all: 'الكل', options: [
        { v: 'pending', t: 'بانتظار الاعتماد' }, { v: 'unpaid', t: 'آجلة غير مسددة' }, { v: 'approved', t: 'معتمدة' }, { v: 'rejected', t: 'مرفوضة' }, { v: 'cancelled', t: 'ملغاة' }
      ] },
      columns: [
        { key: 'number', label: 'المصروف', render: function (e) { return h`<span class="num">#${e.number}</span><span class="sub">${fmt.date(e.expense_date)}</span>`; } },
        { key: 'type', label: 'النوع', render: function (e) { return h`${api.name(e.type.name)}${e.supplier ? h`<span class="sub">${e.supplier}</span>` : ''}`; } },
        { key: 'company', label: 'الشركة', render: function (e) { return api.company(e.company_id); } },
        { key: 'links', label: 'يخص', render: function (e) { var l = links(e); return l.length ? h`${l.map(function (x, i) { return h`${i ? ' · ' : ''}${x}`; })}` : '—'; } },
        { key: 'method', label: 'الدفع', render: function (e) { return h`${api.t('expense_payment', e.payment_method)}${e.petty_employee ? h`<span class="sub">${api.name(e.petty_employee.name)}</span>` : e.branch_id ? h`<span class="sub">${api.branch(e.branch_id)}</span>` : ''}`; } },
        { key: 'amount', label: 'المبلغ', num: true, render: function (e) { return amt(e.amount); } },
        { key: 'status', label: 'الحالة', render: expenseStatus }
      ],
      rowClick: function (e) { expense(e.id, function () { t.refresh(); A.refreshCounts(); }); },
      empty: { icon: 'receipt', title: 'لا توجد مصروفات هنا' }
    });
  }

  /* whose treasury pays: required when the money comes out of a treasury; the only branch is chosen already */
  function branchField(value) {
    var opts = api.branchOptions();
    return BT.f.select({ name: 'branch', label: 'الفرع (خزينته تدفع)', placeholder: 'اختر الفرع…', options: opts, value: value || (opts.length === 1 ? opts[0].v : ''), hint: 'مطلوب للدفع من الخزينة: ينقص رصيد خزينة الفرع عند الاعتماد أو السداد' });
  }
  function needBranch(method, branch) {
    return method === 'treasury' && !branch ? Promise.reject(new Error('اختر الفرع الذي تُدفع من خزينته')) : null;
  }

  function newExpense(done) {
    var jobs = [api.get('/finance/expense-types'), A.all('/vehicles'), A.allEmployees({}),
      api.can('maintenance.view') ? api.get('/maintenance/centers') : Promise.resolve([]),
      api.get('/companies/options').then(function (c) { api.companies = c; }), // a company added since sign-in is listed
      // the petty cash custodies (not a company's): for a user over every company who sees the treasury
      api.me.all_companies && api.can('treasury.view') ? api.get('/cash/petty') : Promise.resolve([])];
    Promise.all(jobs).then(function (r) {
      var types = r[0].filter(function (t) { return t.active; }), vehicles = r[1], people = r[2], centers = r[3], holders = r[5];
      var methods = ['treasury', 'bank', 'payable'].concat(holders.length ? ['petty'] : []);
      var companies = api.companyOptions().filter(function (c) { return api.me.all_companies || api.me.company_ids.indexOf(c.v) > -1; });
      A.formModal({
        title: 'تسجيل مصروف', subtitle: 'يُعتمد ثم يدخل القيود تلقائياً', icon: 'receipt', size: 'lg',
        body: h`<div class="form-grid">
          ${BT.f.select({ name: 'company', label: 'الشركة', required: true, placeholder: false, options: companies })}
          ${BT.f.select({ name: 'type', label: 'النوع', required: true, placeholder: false, options: types.map(function (t) { return { v: t.id, t: api.name(t.name) }; }) })}
          ${BT.f.input({ name: 'date', label: 'التاريخ', type: 'date', required: true, value: BT.config.today })}
          ${BT.f.money({ name: 'amount', label: 'المبلغ', required: true })}
          ${BT.f.select({ name: 'method', label: 'الدفع', required: true, placeholder: false, options: A.options('expense_payment', methods) })}
          ${branchField()}
          ${holders.length ? BT.f.select({ name: 'petty_holder', label: 'صاحب العهدة', placeholder: 'اختر الموظف…', options: holders.map(function (x) { return { v: x.employee.id, t: api.name(x.employee.name) + ' — ' + fmt.money(x.balance) }; }), hint: 'للدفع «من عهدة موظف»: تنقص عهدته عند الاعتماد' }) : ''}
          ${BT.f.input({ name: 'quantity', label: 'الكمية (لتر للوقود)', optional: true, num: true })}
          ${BT.f.input({ name: 'supplier', label: 'المورد', optional: true })}
          ${BT.f.input({ name: 'ref', label: 'رقم الفاتورة أو الإيصال', optional: true })}
          <div class="full">${A.picker({ name: 'vehicle', label: 'السيارة (اختياري)', items: vehicles.map(function (x) { return { id: x.id, label: A.vehicleLabel(x) }; }) })}</div>
          <div class="full">${A.picker({ name: 'employee', label: 'الموظف أو السائق (اختياري)', items: people.map(function (x) { return { id: x.id, label: x.employee_number + ' · ' + api.name(x.name) }; }) })}</div>
          ${centers.length ? h`<div class="full">${BT.f.select({ name: 'center', label: 'مركز الصيانة (اختياري)', options: centers.map(function (c) { return { v: c.id, t: c.name }; }) })}</div>` : ''}
          ${BT.f.upload({ name: 'files', label: 'صورة الفاتورة أو الإيصال', optional: true, full: true, multiple: true, accept: 'image/*,application/pdf' })}
          ${BT.f.textarea({ name: 'notes', label: 'ملاحظات', optional: true, full: true, rows: 2 })}</div>`,
        submitText: 'تسجيل', done: false,
        submit: function (f, dlg) {
          var vehicle = f.vehicle ? A.picked('vehicle', f.vehicle) : null, employee = f.employee ? A.picked('employee', f.employee) : null;
          if (f.vehicle && !vehicle) return Promise.reject(new Error('اختر السيارة من القائمة'));
          if (f.employee && !employee) return Promise.reject(new Error('اختر الموظف من القائمة'));
          var missing = needBranch(f.method, f.branch);
          if (missing) return missing;
          if (f.method === 'petty' && !f.petty_holder) return Promise.reject(new Error('اختر الموظف صاحب العهدة التي دفعت'));
          var chosen = [].slice.call((dlg.form.querySelector('[name=files]') || {}).files || []);
          return Promise.all(chosen.map(function (file) { return api.upload(file).then(function (x) { return x.sha256; }); })).then(function (shas) {
            return api.post('/finance/expenses', {
              company_id: Number(f.company), branch_id: f.branch ? Number(f.branch) : null, type_id: Number(f.type), expense_date: f.date, amount: String(f.amount), payment_method: f.method,
              petty_employee_id: f.method === 'petty' ? f.petty_holder : null, quantity: f.quantity ? String(f.quantity) : null, supplier: f.supplier || null, reference_no: f.ref || null,
              vehicle_id: vehicle, employee_id: employee, center_id: f.center || null, notes: f.notes || null, files: shas
            });
          });
        },
        after: function (e) { BT.toast('سُجّل المصروف #' + e.number, { sub: 'بانتظار الاعتماد' }); if (done) done(); }
      });
    }, api.fail).catch(function () {});
  }

  function expense(id, done) {
    api.get('/finance/expenses/' + id).then(function (e) {
      var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
      function act(fn) { return function (dlg) { fn(e, function () { dlg.close(); if (done) done(); expense(id, done); }); }; }
      if ((e.status === 'pending' || e.status === 'approved') && !e.paid_at && api.can('finance.create')) btns.push({ label: 'إلغاء', cls: 'btn-ghost', icon: 'ban', close: false, onClick: act(cancelExpense) });
      if (e.unpaid && api.can('finance.create')) btns.push({ label: 'سداد', cls: 'btn-outline', icon: 'banknote', close: false, onClick: act(payExpense) });
      if (e.status === 'pending' && api.can('finance.approve')) {
        btns.push({ label: 'رفض', cls: 'btn-outline', icon: 'x', close: false, onClick: act(rejectExpense) });
        btns.push({ label: 'اعتماد', cls: 'btn-primary', icon: 'check', close: false, onClick: act(approveExpense) });
      }
      var d = BT.drawer.open({
        title: h`مصروف <span class="num">#${e.number}</span> · ${amt(e.amount)}`, subtitle: api.name(e.type.name) + ' · ' + fmt.date(e.expense_date), icon: 'receipt', size: 'lg',
        body: h`${BT.kv([
          ['الحالة', expenseStatus(e)],
          ['الشركة', api.company(e.company_id)],
          ['النوع', api.name(e.type.name)],
          ['المبلغ', amt(e.amount)],
          e.quantity ? ['الكمية', h`<span class="num">${e.quantity}</span>`] : null,
          e.branch_id ? ['الفرع', api.branch(e.branch_id)] : null,
          ['الدفع', api.t('expense_payment', e.payment_method) + (e.petty_employee ? ': ' + api.name(e.petty_employee.name) : '') + (e.paid_at ? ' · سُدد ' + api.t('expense_payment', e.paid_from) + ' ' + fmt.dt(e.paid_at) + (e.payment_ref ? ' · ' + e.payment_ref : '') : '')],
          e.supplier ? ['المورد', e.supplier] : null,
          e.reference_no ? ['رقم الفاتورة', h`<span class="num">${e.reference_no}</span>`] : null,
          e.vehicle ? ['السيارة', BT.plate(e.vehicle.plate_number)] : null,
          e.employee ? ['الموظف', A.person(e.employee)] : null,
          e.center ? ['مركز الصيانة', e.center.name] : null,
          e.files.length ? ['الملفات', h`${e.files.map(function (sha, i) { return h`<a href="${api.url('/finance/expenses/' + e.id + '/files/' + sha)}" target="_blank" rel="noopener">${icon('file-text', 14)} ملف ${i + 1}</a> `; })}`] : null,
          e.notes ? ['ملاحظات', h`<span style="white-space:normal">${e.notes}</span>`] : null,
          ['التسجيل', (e.created_by || '') + ' · ' + fmt.dt(e.created_at)],
          e.decided_at ? ['القرار', (e.decided_by || '') + ' · ' + fmt.dt(e.decided_at) + (e.decision_note ? ' · ' + e.decision_note : '')] : null,
          e.cancel_reason ? ['سبب الإلغاء', e.cancel_reason] : null
        ].filter(Boolean))}<div data-approvals></div>`,
        buttons: btns
      });
      if (A.approvalHistory) A.approvalHistory(d.body.querySelector('[data-approvals]'), 'expense', e.id);
    }, api.fail);
  }
  function approveExpense(e, done) {
    A.confirmRun({ title: 'اعتماد المصروف', message: e.payment_method === 'treasury' && e.branch_id ? 'يُصرف المبلغ من خزينة ' + api.branch(e.branch_id) + ' الآن، ويدخل القيود عند التوليد التالي.' : e.petty_employee ? 'يُصرف المبلغ من عهدة ' + api.name(e.petty_employee.name) + ' الآن، ويدخل القيود عند التوليد التالي.' : 'يدخل القيود عند التوليد التالي.', confirmText: 'اعتماد', tone: 'success', run: function () { return api.post('/finance/expenses/' + e.id + '/approve', {}); }, after: function (res) {
      BT.toast(res.status === 'pending' ? 'سُجّل اعتمادك' : 'اعتُمد المصروف', res.status === 'pending' ? { sub: 'بانتظار الخطوة التالية من مسار الاعتماد' } : undefined); done(res);
    } });
  }
  function rejectExpense(e, done) {
    A.confirmRun({ title: 'رفض المصروف', confirmText: 'رفض', tone: 'danger', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/finance/expenses/' + e.id + '/reject', { note: reason }); }, done: 'رُفض المصروف', after: done });
  }
  function cancelExpense(e, done) {
    A.confirmRun({ title: 'إلغاء المصروف', message: e.status === 'approved' ? 'لإدخال خاطئ. إن كان له قيد فسيظهر عند التوليد لعكسه' + (e.payment_method === 'treasury' && e.branch_id ? '، ويرجع مبلغه إلى خزينة الفرع الآن.' : e.petty_employee ? '، ويرجع مبلغه إلى العهدة الآن.' : '.') : 'لإدخال خاطئ.', confirmText: 'إلغاء المصروف', tone: 'danger', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/finance/expenses/' + e.id + '/cancel', { reason: reason }); }, done: 'أُلغي المصروف', after: done });
  }
  function payExpense(e, done) {
    A.formModal({ title: 'سداد المصروف', subtitle: '#' + e.number + ' · ' + fmt.money(e.amount), icon: 'banknote', size: 'sm',
      body: h`<div class="form">${BT.f.select({ name: 'from', label: 'من', required: true, placeholder: false, options: A.options('expense_payment', ['bank', 'treasury']) })}${branchField(e.branch_id)}${BT.f.input({ name: 'ref', label: 'مرجع السداد', optional: true })}</div>`,
      submitText: 'تم السداد', done: 'سُجّل السداد',
      submit: function (v) {
        return needBranch(v.from, v.branch) || api.post('/finance/expenses/' + e.id + '/pay', { paid_from: v.from, branch_id: v.branch ? Number(v.branch) : null, payment_ref: v.ref || null });
      }, after: done });
  }

  /* ================= القيود ================= */
  function entriesPanel(el) {
    var r = month();
    var tools = h`${api.can('finance.create') ? h`<button type="button" class="btn btn-sm btn-primary" data-post>${icon('refresh-cw', 14)} توليد القيود</button><button type="button" class="btn btn-sm btn-soft" data-manual>${icon('plus', 14)} قيد يدوي</button>` : ''}
      ${api.can('finance.approve') ? h`<button type="button" class="btn btn-sm btn-soft" data-opening>${icon('scale', 14)} الأرصدة الافتتاحية</button><button type="button" class="btn btn-sm btn-ghost" data-old-import>${icon('file-up', 14)} استيراد من نظام قديم</button>` : ''}
      ${api.can('finance.approve') ? h`<button type="button" class="btn btn-sm btn-outline" data-approve-all>${icon('check', 14)} اعتماد المسودات</button><button type="button" class="btn btn-sm btn-ghost" data-discard>حذف المسودات</button>` : ''}
      ${api.can('finance.export') ? h`<button type="button" class="btn btn-sm btn-outline" data-export="xlsx">${icon('file-spreadsheet', 14)} Excel</button><button type="button" class="btn btn-sm btn-ghost" data-export="csv">CSV</button>` : ''}`;
    BT.render(el, h`<div class="card"><div data-t></div></div>`);
    var host = el.querySelector('[data-t]');
    var t = BT.table(host, {
      fetch: function (s) { return api.get('/finance/entries', { status: s.chip || null, date_from: r.from, date_to: r.to, limit: s.limit, offset: s.offset }); },
      chips: { value: 'draft', all: 'الكل', options: A.options('entry_status', ['draft', 'approved']) },
      tools: rangeTools(r, tools),
      columns: [
        { key: 'number', label: 'القيد', render: function (e) { return h`<span class="num">#${e.number}</span><span class="sub">${fmt.date(e.entry_date)}</span>`; } },
        { key: 'kind', label: 'المصدر', render: function (e) { return h`${api.t('entry_source', e.source_kind)}<span class="sub ltr">${e.source_ref}</span>`; } },
        { key: 'description', label: 'البيان', render: function (e) { return h`<span style="white-space:normal">${e.description}</span>`; } },
        { key: 'amount', label: 'المبلغ', num: true, render: function (e) { return amt(e.amount); } },
        { key: 'status', label: 'الحالة', render: function (e) { return h`${A.pill('entry_status', e.status)}${e.reversed_by ? h` ${BT.pill('معكوس بـ #' + e.reversed_by, 'n')}` : ''}`; } }
      ],
      rowClick: function (e) { entry(e.id, t.refresh); },
      empty: { icon: 'book-open', title: 'لا توجد قيود في هذه الفترة', text: 'ولّد القيود من مستندات الفترة' }
    });
    wireRange(host, r, function () { t.refresh(); });
    var period = function () { return { date_from: r.from, date_to: r.to }; };
    BT.on(host, 'click', '[data-post]', function () {
      api.post('/finance/entries/post', period()).then(function (res) { postResult(res); t.refresh(); }, api.fail).catch(function () {});
    });
    BT.on(host, 'click', '[data-approve-all]', function () {
      A.confirmRun({ title: 'اعتماد مسودات الفترة', message: 'من ' + fmt.date(r.from) + ' إلى ' + fmt.date(r.to) + '. القيد المعتمد لا يتغير بعدها؛ التصحيح بقيد عكسي.', confirmText: 'اعتماد', tone: 'success',
        run: function () { return api.post('/finance/entries/approve', period()); }, after: function (res) { BT.toast('اعتُمد ' + res.count + ' قيد'); t.refresh(); } });
    });
    BT.on(host, 'click', '[data-discard]', function () {
      A.confirmRun({ title: 'حذف مسودات الفترة', message: 'لتُنشأ من جديد بعد تعديل دليل الحسابات. المستندات لا تتأثر.', confirmText: 'حذف', tone: 'danger',
        run: function () { return api.post('/finance/entries/discard', period()); }, after: function (res) { BT.toast('حُذفت ' + res.count + ' مسودة'); t.refresh(); } });
    });
    BT.on(host, 'click', '[data-manual]', function () { manualEntry(function () { t.refresh(); }); });
    BT.on(host, 'click', '[data-opening]', function () { openingBalances(function () { t.refresh(); }); });
    BT.on(host, 'click', '[data-old-import]', function () { oldImport(function () { t.refresh(); }); });
    BT.on(host, 'click', '[data-export]', function (e, b) {
      var ext = b.getAttribute('data-export');
      A.downloadFile('/finance/entries/export', Object.assign(period(), { format: ext }), 'entries-' + r.from + '-' + r.to + '.' + ext);
    });
  }

  function postResult(res) {
    var kinds = Object.keys(res.by_kind);
    BT.modal.open({
      title: res.created ? 'أُنشئت ' + res.created + ' مسودة' : 'لا مستندات جديدة', icon: 'book-open', size: res.stale.length ? 'lg' : 'md',
      body: h`${kinds.length ? BT.kv(kinds.map(function (k) { return [api.t('entry_source', k), h`<span class="num">${res.by_kind[k]}</span>`]; })) : ''}
        ${res.stale.length ? h`<div class="banner warn mt-12">${icon('triangle-alert', 16)}<div>مستندات تغيّرت بعد قيدها (أُلغيت أو أعيد فتحها أو تغيّر مبلغها). القيد لا يُعدّل: اعكسه، ثم ولّد القيود من جديد.</div></div>
          ${BT.chart.table(['القيد', 'المرجع', 'في القيد', 'في المستند'], res.stale.map(function (s) { return ['#' + s.number, s.source_ref, fmt.money(s.entered), fmt.money(s.document)]; }))}` : ''}
        ${res.errors.length ? h`<div class="banner danger mt-12">${icon('circle-alert', 16)}<div>${res.errors.map(function (x) { return h`<div>${x.source_ref}: ${err(x.code, x.params)}</div>`; })}</div></div>` : ''}`,
      buttons: [{ label: 'إغلاق', cls: 'btn-primary' }]
    });
  }

  function entry(id, done) {
    api.get('/finance/entries/' + id).then(function (e) {
      var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
      var debit = 0, credit = 0;
      e.lines.forEach(function (l) { debit += Number(l.debit); credit += Number(l.credit); });
      if (e.status === 'draft' && api.can('finance.approve')) btns.push({ label: 'اعتماد', cls: 'btn-primary', icon: 'check', close: false, onClick: function (dlg) {
        api.post('/finance/entries/approve', { ids: [e.id] }).then(function () { BT.toast('اعتُمد القيد'); dlg.close(); if (done) done(); }, api.fail).catch(function () {});
      } });
      if (e.status === 'draft' && (e.source_kind === 'manual' || e.source_kind === 'opening') && api.can('finance.create')) btns.push({ label: 'حذف', cls: 'btn-ghost', icon: 'trash-2', close: false, onClick: function (dlg) {
        A.confirmRun({ title: 'حذف القيد #' + e.number, message: 'مسودة كتبتموها: تُحذف نهائياً.', confirmText: 'حذف', tone: 'danger',
          run: function () { return api.del('/finance/entries/' + e.id); }, done: 'حُذف القيد', after: function () { dlg.close(); if (done) done(); } });
      } });
      if (e.status === 'approved' && !e.reversed_by && e.source_kind !== 'reversal' && api.can('finance.approve')) btns.push({ label: 'قيد عكسي', cls: 'btn-outline', icon: 'undo-2', close: false, onClick: function (dlg) {
        // dated by the accountant (today by default): not before the entry it reverses, not in the future; an
        // opening balance reverses on its own date
        var opening = e.source_kind === 'opening';
        A.formModal({ title: 'عكس القيد #' + e.number, icon: 'undo-2', size: 'sm', submitText: 'عكس القيد', submitCls: 'btn-danger', done: 'أُنشئ القيد العكسي',
          body: h`<div class="form"><p class="fs-sm">يُنشأ قيد معتمد بعكس كل سطر، ويصبح المستند جاهزاً ليُقيَّد من جديد.</p>
            ${opening ? h`<div class="hint">قيد الأرصدة الافتتاحية يُعكس بتاريخه (${fmt.date(e.entry_date)}).</div>` : BT.f.date({ name: 'entry_date', label: 'تاريخ القيد العكسي', required: true, value: BT.config.today, min: e.entry_date, max: e.entry_date > BT.config.today ? e.entry_date : BT.config.today })}
            ${BT.f.textarea({ name: 'reason', label: 'السبب', required: true, rows: 2 })}</div>`,
          submit: function (v) { return api.post('/finance/entries/' + e.id + '/reverse', opening ? { reason: v.reason } : { reason: v.reason, entry_date: v.entry_date }); },
          after: function () { dlg.close(); if (done) done(); } });
      } });
      BT.drawer.open({
        title: h`قيد <span class="num">#${e.number}</span> · ${amt(e.amount)}`, subtitle: api.t('entry_source', e.source_kind) + ' · ' + fmt.date(e.entry_date), icon: 'book-open', size: 'lg',
        body: h`${BT.kv([
            ['الحالة', A.pill('entry_status', e.status)],
            ['البيان', h`<span style="white-space:normal">${e.description}</span>`],
            ['المرجع', h`<span class="ltr">${e.source_ref}</span>`],
            e.company_id ? ['الشركة', api.company(e.company_id)] : null,
            e.reverses ? ['يعكس القيد', '#' + e.reverses] : null,
            e.reversed_by ? ['معكوس بالقيد', '#' + e.reversed_by] : null,
            e.reason ? ['السبب', e.reason] : null,
            ['الإنشاء', (e.created_by || 'النظام') + ' · ' + fmt.dt(e.created_at)],
            e.approved_at ? ['الاعتماد', (e.approved_by || '') + ' · ' + fmt.dt(e.approved_at)] : null
          ].filter(Boolean))}
          <div class="table-wrap mt-16"><table class="t compact"><thead><tr><th>الحساب</th><th class="num">مدين</th><th class="num">دائن</th></tr></thead><tbody>
            ${e.lines.map(function (l) { return h`<tr><td><span class="num">${l.account.code}</span> ${api.name(l.account.name)}${l.employee || l.memo ? h`<span class="sub">${[l.employee ? api.name(l.employee.name) : '', l.memo || ''].filter(Boolean).join(' · ')}</span>` : ''}</td><td class="num">${money(l.debit)}</td><td class="num">${money(l.credit)}</td></tr>`; })}
          </tbody><tfoot><tr><td>الإجمالي</td><td class="num"><b>${fmt.money(debit)}</b></td><td class="num"><b>${fmt.money(credit)}</b></td></tr></tfoot></table></div>`,
        buttons: btns
      });
    }, api.fail);
  }

  /* ================= ميزان المراجعة ================= */
  function balancePanel(el) {
    var r = fiscalRange();
    var fy = cfg ? h`<span class="muted fs-sm" data-fiscal>السنة المالية من ${fmt.date(cfg.fiscal_year_start)}</span>` : '';
    BT.render(el, h`<div class="card"><div class="toolbar"><div class="page-actions">${rangeTools(r)}${fy}</div></div><div data-tb></div></div>`);
    function load() {
      A.load(el.querySelector('[data-tb]'), api.get('/finance/trial-balance', { date_from: r.from, date_to: r.to }), function (rows) {
        if (!rows.length) return BT.empty('scale', 'لا قيود معتمدة حتى نهاية الفترة', 'اعتمد القيود أولاً من تبويب «القيود»');
        var sum = function (k) { return rows.reduce(function (s, x) { return s + Number(x[k]); }, 0); };
        return h`<div class="table-wrap"><table class="t compact"><thead><tr><th>الحساب</th><th>النوع</th><th class="num">أول المدة</th><th class="num">مدين</th><th class="num">دائن</th><th class="num">آخر المدة</th></tr></thead><tbody>
          ${rows.map(function (x) { return h`<tr data-account="${x.account.id}" class="clickable" title="اضغط لكشف الحساب: كل حركة ومع مين"><td>${icon('chevron-left', 13)} <span class="num">${x.account.code}</span> ${api.name(x.account.name)}</td><td>${api.t('account_type', x.account.type)}</td><td class="num">${fmt.money(x.opening)}</td><td class="num">${fmt.money(x.debit)}</td><td class="num">${fmt.money(x.credit)}</td><td class="num"><b>${fmt.money(x.closing)}</b></td></tr>`; })}
          </tbody><tfoot><tr><td colspan="2">الإجمالي</td><td class="num">${fmt.money(sum('opening'))}</td><td class="num">${fmt.money(sum('debit'))}</td><td class="num">${fmt.money(sum('credit'))}</td><td class="num"><b data-tb-total>${fmt.money(sum('closing'))}</b></td></tr></tfoot></table></div>
          <div class="hint mt-8">اضغط على أي حساب يفتح تحته كشفه: كل حركة في الفترة ومع مين (السائق أو الموظف أو المركز أو المورد)، والرصيد بعدها، ورصيد كل طرف. مجموع «آخر المدة» صفر دائماً: كل قيد متوازن.</div>`;
      }).catch(function () {});
    }
    // a row opens its account's statement under it (a second click closes it)
    BT.on(el, 'click', 'tr[data-account]', function (e, row) {
      var next = row.nextElementSibling;
      if (next && next.hasAttribute('data-ledger')) { next.remove(); row.classList.remove('open'); return; }
      var holder = document.createElement('tr');
      holder.setAttribute('data-ledger', row.getAttribute('data-account'));
      holder.innerHTML = '<td colspan="6" class="ledger-cell"></td>';
      row.after(holder);
      row.classList.add('open');
      ledger(holder.firstChild, row.getAttribute('data-account'), r);
    });
    wireRange(el, r, load);
    load();
  }

  function party(p) {
    if (!p) return h`<span class="muted">—</span>`;
    var kind = { employee: 'user-round', center: 'wrench', supplier: 'store' }[p.type] || 'user-round';
    return h`<span class="nowrap">${icon(kind, 13)} ${api.name(p.name)}</span>`;
  }

  /* كشف حساب: رصيد أول المدة، كل سطر بطرفه ورصيده، ورصيد كل طرف حتى آخر المدة */
  function ledger(cell, accountId, r) {
    A.load(cell, api.get('/finance/ledger', { account_id: accountId, date_from: r.from, date_to: r.to }), function (b) {
      var parties = b.parties.length ? h`<div class="mt-8"><div class="fw-600 mb-4">رصيد كل طرف حتى ${fmt.date(r.to)}</div><div class="table-wrap"><table class="t compact" data-ledger-parties><thead><tr><th>الطرف</th><th class="num">مدين</th><th class="num">دائن</th><th class="num">الرصيد</th></tr></thead><tbody>
        ${b.parties.map(function (x) { return h`<tr><td>${party(x.party)}</td><td class="num">${money(x.debit)}</td><td class="num">${money(x.credit)}</td><td class="num"><b>${fmt.money(x.balance)}</b></td></tr>`; })}
        </tbody></table></div></div>` : '';
      var lines = b.lines.length ? h`<div class="table-wrap mt-8"><table class="t compact" data-ledger-lines><thead><tr><th>التاريخ</th><th>القيد</th><th>البيان</th><th>مع مين</th><th class="num">مدين</th><th class="num">دائن</th><th class="num">الرصيد</th></tr></thead><tbody>
        <tr class="muted"><td colspan="6">رصيد أول المدة</td><td class="num">${fmt.money(b.opening)}</td></tr>
        ${b.lines.map(function (ln) { return h`<tr><td class="nowrap">${fmt.date(ln.date)}</td><td><a href="#" data-ledger-entry="${ln.entry_id}" class="num">#${ln.number}</a>${ln.reversal ? h` ${BT.pill('عكسي', 'n')}` : ''}<span class="sub ltr">${ln.ref}</span></td><td style="white-space:normal">${ln.description}</td><td>${party(ln.party)}</td><td class="num">${money(ln.debit)}</td><td class="num">${money(ln.credit)}</td><td class="num">${fmt.money(ln.balance)}</td></tr>`; })}
        </tbody><tfoot><tr><td colspan="4">رصيد آخر المدة</td><td class="num">${fmt.money(b.debit)}</td><td class="num">${fmt.money(b.credit)}</td><td class="num"><b>${fmt.money(b.closing)}</b></td></tr></tfoot></table></div>
        ${b.truncated ? h`<div class="hint">ظاهر أول ${b.lines.length} حركة: ضيّق الفترة لترى الباقي.</div>` : ''}` : h`<div class="muted mt-8">لا حركات في الفترة. رصيد أول المدة ${fmt.money(b.opening)}.</div>`;
      return h`<div class="ledger"><div class="fw-600">كشف حساب <span class="num">${b.account.code}</span> ${api.name(b.account.name)}</div>${parties}${lines}</div>`;
    }).catch(function () {});
    BT.on(cell, 'click', '[data-ledger-entry]', function (e, a) { e.preventDefault(); entry(a.getAttribute('data-ledger-entry')); });
  }

  /* ================= القيد اليدوي ================= */
  // an amount: at most 3 decimals (fils) — more is refused, never rounded in silence
  function num(v) {
    var t = String(v || '').replace(/,/g, '').trim();
    if (t && !/^\d+(\.\d{1,3})?$/.test(t)) return NaN;
    var n = Number(t); return isFinite(n) ? n : NaN;
  }
  function fils(n) { return Math.round(n * 1000); }
  function companySelect(label) {
    var companies = api.companyOptions ? api.companyOptions() : [];
    return companies.length ? BT.f.select({ name: 'company', label: label, optional: true, placeholder: 'بلا شركة', options: companies }) : '';
  }
  function manualEntry(done) {
    Promise.all([api.get('/finance/accounts'), api.can('employees.view') ? A.allEmployees({}).catch(function () { return []; }) : Promise.resolve([]), config(), api.get('/companies/options').then(function (c) { api.companies = c; })]).then(function (r) {
      var accounts = r[0].filter(function (a) { return a.active; }), people = r[1];
      var opts = accounts.map(function (a) { return { v: a.id, t: accountLabel(a) }; });
      var emps = {}; people.forEach(function (p) { emps[p.employee_number + ' · ' + api.name(p.name)] = p.id; });
      var listId = BT.uid('emps');
      function row() {
        return h`<tr data-line><td style="min-width:220px">${BT.f.select({ label: '', options: opts, placeholder: 'الحساب…' })}</td>
          <td><input class="input num-in" data-debit inputmode="decimal" placeholder="0.000" aria-label="مدين"></td>
          <td><input class="input num-in" data-credit inputmode="decimal" placeholder="0.000" aria-label="دائن"></td>
          <td><input class="input" data-emp list="${listId}" autocomplete="off" placeholder="اختياري" aria-label="الموظف"></td>
          <td><button type="button" class="icon-btn sm" data-del-line aria-label="حذف السطر">${icon('x', 14)}</button></td></tr>`;
      }
      var dlg = BT.modal.open({
        title: 'قيد يدوي', subtitle: cfg && cfg.entry_approval === 'auto' ? 'يُعتمد فور حفظه (الاعتماد تلقائي في الإعدادات)' : 'يُحفظ مسودة يعتمدها من له صلاحية الاعتماد', icon: 'book-open', size: 'xl', form: true,
        body: h`<div class="form-grid">
            ${BT.f.input({ name: 'date', label: 'التاريخ', type: 'date', required: true, value: BT.config.today })}
            ${companySelect('الشركة')}
            ${BT.f.input({ name: 'description', label: 'البيان', required: true, full: true })}</div>
          <datalist id="${listId}">${Object.keys(emps).map(function (k) { return h`<option value="${k}"></option>`; })}</datalist>
          <div class="table-wrap mt-12"><table class="t compact" data-lines><thead><tr><th>الحساب</th><th class="num">مدين</th><th class="num">دائن</th><th>الموظف (اختياري)</th><th></th></tr></thead>
            <tbody>${row()}${row()}</tbody>
            <tfoot><tr><td><button type="button" class="btn btn-sm btn-ghost" data-add-line>${icon('plus', 14)} سطر</button></td><td class="num" data-sum-debit>0.000</td><td class="num" data-sum-credit>0.000</td><td colspan="2">الفرق <b class="num" data-diff>0.000</b></td></tr></tfoot></table></div>`,
        buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ القيد', cls: 'btn-primary', submit: true, disabled: true }],
        onSubmit: function (v, d) {
          var lines = read();
          if (!lines) return false;
          return api.post('/finance/entries/manual', { entry_date: v.date, description: v.description, company_id: v.company ? Number(v.company) : null, lines: lines.list })
            .then(function (e) { BT.toast(e.status === 'approved' ? 'حُفظ القيد #' + e.number + ' واعتُمد' : 'حُفظ القيد #' + e.number, { sub: e.status === 'approved' ? '' : 'مسودة بانتظار الاعتماد' }); if (done) done(); return true; })
            .catch(function (err) { api.fail(err); return Promise.reject(err); });
        }
      });
      var body = dlg.body, tbody = body.querySelector('[data-lines] tbody');
      function read() {
        var list = [], debit = 0, credit = 0, ok = true;
        BT.$$('tr[data-line]', tbody).forEach(function (tr) {
          var acc = tr.querySelector('select').value, d = num(tr.querySelector('[data-debit]').value), c = num(tr.querySelector('[data-credit]').value);
          var empText = tr.querySelector('[data-emp]').value.trim();
          if (!acc && !d && !c) return;
          if (!acc || isNaN(d) || isNaN(c) || (d > 0) === (c > 0) || d < 0 || c < 0) ok = false;
          if (empText && !emps[empText]) ok = false;
          debit += fils(d || 0); credit += fils(c || 0);
          list.push({ account_id: Number(acc), debit: (d || 0).toFixed(3), credit: (c || 0).toFixed(3), employee_id: empText ? emps[empText] : null });
        });
        return { list: list, debit: debit, credit: credit, ok: ok && list.length >= 2 };
      }
      function update() {
        var x = read();
        body.querySelector('[data-sum-debit]').textContent = fmt.money(x.debit / 1000);
        body.querySelector('[data-sum-credit]').textContent = fmt.money(x.credit / 1000);
        body.querySelector('[data-diff]').textContent = fmt.money((x.debit - x.credit) / 1000);
        var b = dlg.btn(1); if (b) b.disabled = !(x.ok && x.debit > 0 && x.debit === x.credit);
      }
      body.addEventListener('input', update);
      body.addEventListener('change', update);
      BT.on(body, 'click', '[data-add-line]', function () { tbody.insertAdjacentHTML('beforeend', String(row())); update(); });
      BT.on(body, 'click', '[data-del-line]', function (e, b) { if (BT.$$('tr[data-line]', tbody).length > 2) b.closest('tr').remove(); update(); });
    }, api.fail).catch(function () {});
  }

  /* ================= الأرصدة الافتتاحية ================= */
  function openingBalances(done) {
    Promise.all([api.get('/finance/accounts'), api.get('/finance/roles'), config(), api.get('/companies/options').then(function (c) { api.companies = c; })]).then(function (r) {
      var accounts = r[0].filter(function (a) { return a.active; });
      var equityId = (r[1].find(function (x) { return x.role === 'opening_equity'; }) || {}).account_id;
      var equity = r[0].find(function (a) { return a.id === equityId; });
      var ready = !!cfg.books_start_date;
      var dlg = BT.modal.open({
        title: 'الأرصدة الافتتاحية', icon: 'scale', size: 'lg', form: true,
        subtitle: ready ? 'بتاريخ ' + fmt.date(cfg.opening_date) + '، اليوم السابق لبداية الدفاتر' : '',
        body: h`${ready ? '' : h`<div class="banner warn mb-12">${icon('triangle-alert', 16)}<div>حدّد «تاريخ بداية الدفاتر في النظام» في الإعدادات ← المحاسبة أولاً.</div></div>`}
          <div class="form-grid">${companySelect('الشركة (اختياري)')}</div>
          <div class="hint">رصيد كل حساب في دفاتركم السابقة يوم ما قبل البداية. ما لا يتوازن يذهب سطراً واحداً إلى حساب الأرصدة الافتتاحية${equity ? ' (' + equity.code + ')' : ''}.</div>
          <div class="table-wrap mt-8" style="max-height:50vh"><table class="t compact" data-opening-lines><thead><tr><th>الحساب</th><th class="num">مدين</th><th class="num">دائن</th></tr></thead><tbody>
            ${accounts.map(function (a) { return h`<tr data-acc-line="${a.id}"><td><span class="num">${a.code}</span> ${api.name(a.name)}</td><td><input class="input num-in" data-debit inputmode="decimal" placeholder="0.000" aria-label="مدين ${a.code}"></td><td><input class="input num-in" data-credit inputmode="decimal" placeholder="0.000" aria-label="دائن ${a.code}"></td></tr>`; })}
          </tbody></table></div>
          <div class="banner info mt-12" data-equity>${icon('info', 16)}<div>الفرق إلى ${equity ? equity.code + ' ' + api.name(equity.name) : 'الأرصدة الافتتاحية'}: <b class="num" data-opening-diff>0.000</b></div></div>`,
        buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ الأرصدة', cls: 'btn-primary', submit: true, disabled: true }],
        onSubmit: function (v) {
          var x = read();
          return api.post('/finance/opening', { company_id: v.company ? Number(v.company) : null, lines: x.list }).then(function (res) {
            BT.toast('سُجّلت الأرصدة الافتتاحية #' + res.entry.number, { sub: Number(res.difference) ? 'الفرق ' + fmt.money(Math.abs(res.difference)) + ' إلى ' + (res.equity_account ? res.equity_account.code : '') : '' });
            if (done) done(); return true;
          }).catch(function (err) { api.fail(err); return Promise.reject(err); });
        }
      });
      var body = dlg.body;
      function read() {
        var list = [], debit = 0, credit = 0, ok = true;
        BT.$$('tr[data-acc-line]', body).forEach(function (tr) {
          var d = num(tr.querySelector('[data-debit]').value), c = num(tr.querySelector('[data-credit]').value);
          if (!d && !c) return;
          if (isNaN(d) || isNaN(c) || (d > 0) === (c > 0) || d < 0 || c < 0) ok = false;
          debit += fils(d || 0); credit += fils(c || 0);
          list.push({ account_id: Number(tr.getAttribute('data-acc-line')), debit: (d || 0).toFixed(3), credit: (c || 0).toFixed(3) });
        });
        return { list: list, diff: debit - credit, ok: ok && list.length > 0 };
      }
      function update() {
        var x = read();
        body.querySelector('[data-opening-diff]').textContent = fmt.money(Math.abs(x.diff) / 1000) + (x.diff > 0 ? ' دائن' : x.diff < 0 ? ' مدين' : '');
        var b = dlg.btn(1); if (b) b.disabled = !(ready && x.ok);
      }
      body.addEventListener('input', update);
    }, api.fail).catch(function () {});
  }

  /* ================= استيراد دفاتر النظام القديم ================= */
  function issueList(list, tone) {
    return h`<div class="banner ${tone} mt-12">${icon(tone === 'danger' ? 'circle-x' : 'triangle-alert', 16)}<div>${list.slice(0, 50).map(function (x) {
      return h`<div>${x.sheet}${x.row ? ' · صف ' + x.row : ''}: ${err(x.code, x.params)}</div>`;
    })}${list.length > 50 ? h`<div>… و${list.length - 50} غيرها</div>` : ''}</div></div>`;
  }
  function oldImport(done) {
    var file = null;
    var dlg = BT.modal.open({
      title: 'استيراد من نظام قديم', icon: 'file-up', size: 'lg',
      body: h`<p class="muted fs-sm">ملف Excel بورقتين: «أرصدة افتتاحية» (رصيد كل حساب يوم ما قبل بداية الدفاتر، والفرق إلى حساب الأرصدة الافتتاحية) و«قيود» (كل قيد قديم أسطره برقمه في النظام القديم). أي ورقة يمكن تركها فارغة. صف «مثال» يُتجاهل.</p>
        <div><button type="button" class="btn btn-outline btn-sm" data-old-template>${icon('download', 14)} تنزيل القالب</button></div>
        <div class="form-grid mt-12">${companySelect('الشركة (اختياري)')}</div>
        ${BT.f.upload({ name: 'file', label: 'ملف Excel (.xlsx)', accept: '.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', accept_label: 'xlsx · حتى 10MB' })}
        <div data-old-result></div>`,
      buttons: [{ label: 'إغلاق', cls: 'btn-ghost' }, { label: 'فحص', cls: 'btn-outline', icon: 'list-checks', close: false, onClick: function () { run(false); } },
        { label: 'استيراد', cls: 'btn-primary', icon: 'check', close: false, disabled: true, onClick: function () { run(true); } }]
    });
    var body = dlg.body, res = body.querySelector('[data-old-result]'), input = body.querySelector('input[type=file]');
    input.addEventListener('change', function () { file = input.files[0] || null; dlg.btn(2).disabled = true; BT.render(res, ''); });
    BT.on(body, 'click', '[data-old-template]', function () { A.downloadFile('/finance/import/template', {}, 'old-books-template.xlsx'); });
    function run(apply) {
      if (!file) { BT.toast('اختر الملف أولاً', { type: 'error' }); return; }
      var company = (body.querySelector('[name=company]') || {}).value;
      var i = apply ? 2 : 1;
      dlg.busy(i, true);
      api.uploadForm('/finance/import', file, { apply: apply, company_id: company || null }).then(function (r) {
        dlg.busy(i, false);
        var o = r.opening;
        BT.render(res, h`<div class="mt-12" data-old-summary>${BT.kv([
            ['الأرصدة الافتتاحية', h`<span class="num">${o.lines}</span> سطر · مدين ${fmt.money(o.debit)} · دائن ${fmt.money(o.credit)} · الفرق إلى الأرصدة الافتتاحية <b class="num">${fmt.money(o.difference)}</b>`],
            ['القيود', h`<span class="num">${r.entries}</span> قيد · <span class="num">${r.lines}</span> سطر`]
          ])}
          ${r.errors.length ? issueList(r.errors, 'danger') : r.applied ? h`<div class="banner success mt-12">${icon('circle-check', 16)}<div>استُورد ${r.numbers.length} قيد.</div></div>` : h`<div class="banner success mt-12">${icon('circle-check', 16)}<div>الملف سليم: اضغط «استيراد».</div></div>`}
          ${r.warnings.length ? issueList(r.warnings, 'warn') : ''}</div>`);
        dlg.btn(2).disabled = apply || r.errors.length > 0;
        if (r.applied) { BT.toast('تم الاستيراد', { sub: r.numbers.length + ' قيد' }); file = null; input.value = ''; if (done) done(); }
      }, function (e) {
        dlg.busy(i, false);
        dlg.btn(2).disabled = true;
        BT.render(res, h`<div class="banner danger mt-12">${icon('circle-x', 16)}<div>${api.message(e)}</div></div>`);
      });
    }
  }

  /* ================= دليل الحسابات ================= */
  /* ================= إقفال الشهور ================= */
  // where each point of the month's check is settled
  var PROBLEM_LINKS = {
    draft_entries: '#/finance?tab=entries', stale_entries: '#/finance?tab=entries', documents_not_entered: '#/finance?tab=entries',
    pending_expenses: '#/finance?tab=expenses&chip=pending', pending_fuel_claims: '#/cash?tab=fuel', pending_daily_reports: '#/daily',
    pending_deductions: '#/approvals', draft_payroll_runs: '#/payroll', treasury_days_open: '#/cash?tab=treasury'
  };
  function monthOf(d) { return d.slice(0, 7); }
  function prevMonth() { var d = new Date(BT.config.today.slice(0, 8) + '01T00:00:00Z'); d.setUTCDate(0); return d.toISOString().slice(0, 7); }
  function periodsPanel(el, month) {
    if (!api.me.all_companies) { BT.render(el, h`<div class="card">${BT.empty('lock', 'إقفال الشهور لمستخدم على كل الشركات', 'الدفاتر واحدة لكل الشركات')}</div>`); return; }
    var canClose = api.can('finance.close');
    BT.render(el, h`<div class="card"><div class="card-h"><div class="card-t">${icon('clipboard-check', 16)} فحص شهر وإقفاله</div>
        <div class="ms-auto nowrap"><input class="input" type="month" data-pick value="${month || prevMonth()}" aria-label="الشهر"> <button type="button" class="btn btn-sm btn-outline" data-check-pick>${icon('list-checks', 14)} فحص</button></div></div>
        <div data-check-box></div>
        <div class="hint mt-8">الشهر المقفول ما يتسجلش فيه قيد ولا حركة كاش بتاريخ فيه. يُقفل الشهر بعد ما يخلص، وبعد الشهور اللي قبله، ولما الفحص يطلع نظيف. آخر شهر مقفول بس هو اللي يتفتح تاني بسبب.</div></div>
      <div class="card mt-16"><div class="card-h"><div class="card-t">${icon('calendar', 16)} الشهور</div></div><div data-months></div></div>`);
    var box = el.querySelector('[data-check-box]'), monthsBox = el.querySelector('[data-months]');
    function problemText(p) {
      var params = Object.assign({}, p.params);
      if (params.branch && typeof params.branch === 'object') params.branch = api.name(params.branch);
      if (params.first) params.first = fmt.date(params.first);
      if (params.end) params.end = fmt.date(params.end);
      return api.t('period_problem', p.code, params);
    }
    function months() {
      A.load(monthsBox, api.get('/finance/periods'), function (rows) {
        return h`<div class="table-wrap"><table class="t compact" data-periods><thead><tr><th>الشهر</th><th>الحالة</th><th>أقفله</th><th>إعادة الفتح</th><th></th></tr></thead><tbody>
          ${rows.map(function (r) {
            return h`<tr data-month="${r.month}"><td class="num">${r.month}</td><td>${r.status === 'closed' ? BT.pill('مقفول', 'g', true) : BT.pill('مفتوح', 'n')}</td>
              <td>${r.closed_by ? h`${r.closed_by}<span class="sub">${fmt.dt(r.closed_at)}</span>` : '—'}</td>
              <td style="white-space:normal">${r.reopened_at ? h`${r.reopen_reason}<span class="sub">${r.reopened_by} · ${fmt.dt(r.reopened_at)}</span>` : '—'}</td>
              <td class="num nowrap"><button type="button" class="btn btn-sm btn-ghost" data-check="${r.month}">${icon('list-checks', 13)} فحص</button>${r.reopenable && canClose ? h` <button type="button" class="btn btn-sm btn-ghost" data-reopen-month="${r.month}">${icon('rotate-ccw', 13)} إعادة فتح</button>` : ''}</td></tr>`;
          })}</tbody></table></div>`;
      }).catch(function () {});
    }
    function check(m) {
      el.querySelector('[data-pick]').value = m;
      A.load(box, api.get('/finance/periods/' + m + '/check'), function (c) {
        var clean = !c.problems.length, open = c.status !== 'closed';
        return h`<div class="mt-12" data-check-result="${c.month}"><div class="between mb-8"><b>شهر ${c.month}</b>${open ? BT.pill('مفتوح', 'n') : BT.pill('مقفول', 'g', true)}</div>
          ${clean ? h`<div class="banner success">${icon('circle-check', 16)}<div>${open ? 'الفحص نظيف: الشهر جاهز للإقفال.' : 'الشهر مقفول.'}</div></div>`
            : h`<ul class="guide-list" data-problems>${c.problems.map(function (p) {
              var link = p.code === 'earlier_month_open' ? h` <button type="button" class="btn btn-sm btn-ghost" data-check="${p.params.month}">فحص ${p.params.month}</button>` : PROBLEM_LINKS[p.code] ? h` <a class="btn btn-sm btn-ghost" href="${PROBLEM_LINKS[p.code]}">افتح</a>` : '';
              return h`<li data-problem="${p.code}">${icon('circle-alert', 14, 't-danger')} ${problemText(p)}${link}</li>`;
            })}</ul>`}
          ${open && canClose ? h`<div class="mt-12"><button type="button" class="btn btn-primary" data-close-month="${c.month}"${clean ? '' : raw(' disabled')}>${icon('lock', 14)} إقفال الشهر</button></div>` : ''}</div>`;
      }).catch(function () {});
    }
    BT.on(el, 'click', '[data-check-pick]', function () { var m = el.querySelector('[data-pick]').value; if (m) check(m); });
    BT.on(el, 'click', '[data-check]', function (e, b) { check(b.getAttribute('data-check')); });
    BT.on(el, 'click', '[data-close-month]', function (e, b) {
      var m = b.getAttribute('data-close-month');
      A.confirmRun({ title: 'إقفال شهر ' + m, message: 'بعد الإقفال ما يتسجلش أي قيد ولا حركة كاش بتاريخ في الشهر ده.', confirmText: 'إقفال الشهر', tone: 'warn', icon: 'lock',
        run: function () { return api.post('/finance/periods/' + m + '/close', {}); }, done: 'تم إقفال الشهر', after: function () { months(); check(m); } });
    });
    BT.on(el, 'click', '[data-reopen-month]', function (e, b) {
      var m = b.getAttribute('data-reopen-month');
      A.confirmRun({ title: 'إعادة فتح شهر ' + m, message: 'الشهر يرجع مفتوح: تقدر تسجّل فيه، وبعدين افحصه واقفله تاني.', confirmText: 'إعادة فتح', tone: 'danger', icon: 'rotate-ccw', reason: { label: 'السبب', required: true },
        run: function (reason) { return api.post('/finance/periods/' + m + '/reopen', { reason: reason }); }, done: 'أُعيد فتح الشهر', after: function () { months(); check(m); } });
    });
    months();
    check(month || prevMonth());
  }

  function chartPanel(el) {
    var approve = api.can('finance.approve');
    A.load(el, Promise.all([api.get('/finance/accounts'), api.get('/finance/roles'), api.get('/finance/expense-types')]), function (r) {
      var accounts = r[0], roles = r[1], types = r[2];
      var byId = {}; accounts.forEach(function (a) { byId[a.id] = a; });
      var active = accounts.filter(function (a) { return a.active; });
      var mapped = {}; roles.forEach(function (x) { mapped[x.role] = x.account_id; });
      var groups = CLASSES.map(function (c) { return { c: c, rows: accounts.filter(function (a) { return a.code.charAt(0) === c; }) }; });
      var others = accounts.filter(function (a) { return CLASSES.indexOf(a.code.charAt(0)) < 0; });
      if (others.length) groups.push({ c: '', rows: others });
      return h`<div class="banner info mb-12">${icon('info', 16)}<div>رمز الحساب من أربعة أرقام: الأول الفئة والثاني المجموعة. يراجعه محاسبكم (زر Excel) ويعدّله هنا قبل أول اعتماد؛ القيود المعتمدة تبقى على حساباتها، والمسودات تُحذف وتُولَّد من جديد بعد أي تعديل.</div></div>
        <div class="grid" style="grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:16px">
          <div class="card"><div class="card-h"><div class="card-t">${icon('book-open', 17)} الحسابات</div><div><button type="button" class="btn btn-sm btn-outline" data-chart-export>${icon('file-spreadsheet', 14)} Excel</button>${approve ? h` <button type="button" class="btn btn-sm btn-soft" data-acc-new>${icon('plus', 14)} حساب</button>` : ''}</div></div>
            <div class="table-wrap"><table class="t compact"><thead><tr><th>الرمز</th><th>الاسم</th><th>النوع</th><th></th></tr></thead><tbody>
              ${groups.filter(function (g) { return g.rows.length; }).map(function (g) {
                return h`<tr class="group-row" data-class="${g.c}"><td colspan="4"><b>${g.c ? g.c + ' · ' + api.t('account_class', g.c) : 'حسابات أخرى'}</b></td></tr>${g.rows.map(function (a) { return h`<tr class="${approve ? 'clickable' : ''}" data-acc="${a.id}"><td class="num">${a.code}</td><td>${api.name(a.name)}${a.roles.length ? h`<span class="sub">${a.roles.map(function (x) { return api.t('finance_role', x); }).join('، ')}</span>` : ''}</td><td>${api.t('account_type', a.type)}</td><td>${a.active ? '' : BT.pill('موقوف', 'n')}</td></tr>`; })}`;
              })}
            </tbody></table></div></div>
          <div class="grid" style="gap:16px">
            <div class="card"><div class="card-h"><div class="card-t">${icon('git-branch', 17)} ربط الأدوار بالحسابات</div></div>
              <form data-roles class="form">${ROLES.map(function (role) {
                return BT.f.select({ name: role, label: api.t('finance_role', role), value: mapped[role], placeholder: false, disabled: !approve, options: active.map(function (a) { return { v: a.id, t: accountLabel(a) }; }) });
              })}${approve ? h`<div><button type="submit" class="btn btn-primary">حفظ الربط</button></div>` : ''}</form></div>
            <div class="card"><div class="card-h"><div class="card-t">${icon('receipt', 17)} أنواع المصروفات</div>${approve ? h`<button type="button" class="btn btn-sm btn-soft" data-type-new>${icon('plus', 14)} نوع</button>` : ''}</div>
              <div class="list">${types.map(function (t) { var a = byId[t.account_id]; return h`<button type="button" class="li" data-type="${t.id}" style="width:100%;text-align:start"${approve ? '' : raw(' disabled')}><div class="li-main"><div class="li-t">${api.name(t.name)}</div><div class="li-d">${a ? accountLabel(a) : '—'}</div></div>${t.active ? '' : BT.pill('موقوف', 'n')}</button>`; })}</div></div>
          </div></div>`;
    }).then(function (r) {
      if (!r) return;
      BT.on(el, 'click', '[data-chart-export]', function () { A.downloadFile('/finance/accounts/export', {}, 'chart-of-accounts.xlsx'); });
      if (!approve) return;
      var accounts = r[0], types = r[2];
      var reload = function () { chartPanel(el); };
      BT.on(el, 'click', '[data-acc-new]', function () { accountForm(null, reload); });
      BT.on(el, 'click', '[data-acc]', function (e, row) { accountForm(accounts.find(function (a) { return a.id === +row.getAttribute('data-acc'); }), reload); });
      BT.on(el, 'click', '[data-type-new]', function () { typeForm(null, accounts, reload); });
      BT.on(el, 'click', '[data-type]', function (e, b) { typeForm(types.find(function (t) { return t.id === +b.getAttribute('data-type'); }), accounts, reload); });
      el.querySelector('[data-roles]').addEventListener('submit', function (e) {
        e.preventDefault();
        var v = BT.form.values(e.target), body = {};
        ROLES.forEach(function (role) { if (v[role]) body[role] = Number(v[role]); });
        api.put('/finance/roles', { roles: body }).then(function () { BT.toast('حُفظ الربط', { sub: 'احذف المسودات وولّدها من جديد لتأخذ الربط الجديد' }); reload(); }, api.fail).catch(function () {});
      });
    }).catch(function () {});
  }

  function accountForm(a, done) {
    A.formModal({
      title: a ? 'الحساب ' + a.code : 'حساب جديد', icon: 'book-open', size: 'md',
      body: h`<div class="form-grid">
        ${BT.f.input({ name: 'code', label: 'الرمز', required: true, value: a ? a.code : '', pattern: '[0-9A-Za-z][0-9A-Za-z.\\-]{0,19}', msg: 'أرقام وحروف إنجليزية ونقطة وشرطة', hint: a && a.used ? 'عليه قيود: لا يتغير' : '' })}
        ${BT.f.select({ name: 'type', label: 'النوع', required: true, placeholder: false, value: a ? a.type : 'expense', options: A.options('account_type', ['asset', 'liability', 'equity', 'income', 'expense']) })}
        ${BT.f.input({ name: 'name_ar', label: 'الاسم بالعربية', required: true, value: a ? a.name.ar || '' : '' })}
        ${BT.f.input({ name: 'name_en', label: 'الاسم بالإنجليزية', required: true, value: a ? a.name.en || '' : '' })}
        ${a ? h`<label class="check full"><input type="checkbox" name="active"${a.active ? raw(' checked') : ''}> <span>نشط</span></label>` : ''}</div>`,
      submitText: 'حفظ', done: 'حُفظ الحساب',
      submit: function (v, dlg) {
        var name = Object.assign({}, a ? a.name : {}, { ar: v.name_ar, en: v.name_en });
        if (!a) return api.post('/finance/accounts', { code: v.code, type: v.type, name: name });
        var body = { version: a.version, name: name, active: dlg.form.querySelector('[name=active]').checked };
        if (v.code !== a.code) body.code = v.code;
        if (v.type !== a.type) body.type = v.type;
        return api.patch('/finance/accounts/' + a.id, body);
      },
      after: done
    });
  }

  function typeForm(t, accounts, done) {
    var options = accounts.filter(function (a) { return a.active; }).map(function (a) { return { v: a.id, t: accountLabel(a) }; });
    A.formModal({
      title: t ? api.name(t.name) : 'نوع مصروف جديد', icon: 'receipt', size: 'md',
      body: h`<div class="form-grid">
        ${t ? '' : BT.f.input({ name: 'code', label: 'الرمز', required: true, pattern: '[a-z][a-z0-9_]{1,30}', msg: 'حروف إنجليزية صغيرة وأرقام و _' })}
        ${BT.f.select({ name: 'account', label: 'الحساب', required: true, placeholder: false, value: t ? t.account_id : '', options: options })}
        ${BT.f.input({ name: 'name_ar', label: 'الاسم بالعربية', required: true, value: t ? t.name.ar || '' : '' })}
        ${BT.f.input({ name: 'name_en', label: 'الاسم بالإنجليزية', required: true, value: t ? t.name.en || '' : '' })}
        ${t ? h`<label class="check full"><input type="checkbox" name="active"${t.active ? raw(' checked') : ''}> <span>نشط</span></label>` : ''}</div>`,
      submitText: 'حفظ', done: 'حُفظ النوع',
      submit: function (v, dlg) {
        var name = Object.assign({}, t ? t.name : {}, { ar: v.name_ar, en: v.name_en });
        if (!t) return api.post('/finance/expense-types', { code: v.code, name: name, account_id: Number(v.account) });
        return api.patch('/finance/expense-types/' + t.id, { name: name, account_id: Number(v.account), active: dlg.form.querySelector('[name=active]').checked });
      },
      after: done
    });
  }

  /* ---------- مصروفات السيارة في ملفها ---------- */
  A.vehicleExpenses = function (el, vehicle) {
    A.load(el, api.get('/finance/expenses', { vehicle_id: vehicle.id, limit: 20 }), function (rows) {
      return rows.length ? h`<div class="list">${rows.map(function (e) {
        return h`<button type="button" class="li" data-expense="${e.id}" style="width:100%;text-align:start"><span class="li-ic o">${icon('receipt', 16)}</span><div class="li-main"><div class="li-t"><span class="num">#${e.number}</span> ${api.name(e.type.name)} · ${fmt.money(e.amount)}</div><div class="li-d">${fmt.date(e.expense_date)}${e.supplier ? ' · ' + e.supplier : ''}</div></div>${A.pill('expense_status', e.status)}</button>`;
      })}</div>` : BT.empty('receipt', 'لا توجد مصروفات', '');
    }).then(function () {
      if (!el._expWired) { el._expWired = true; BT.on(el, 'click', '[data-expense]', function (e, b) { expense(b.getAttribute('data-expense'), function () { A.vehicleExpenses(el, vehicle); }); }); }
    }).catch(function () {});
  };
})();
