/* =====================================================================
   صفحات: المالية · التقارير · الاعتمادات · الإعدادات والصلاحيات · سجل التدقيق
   بوب أب: إضافة مصروف · تصدير تقرير (Excel/PDF) · فترة مخصصة · قرار اعتماد ·
   إضافة مستخدم · صلاحيات الدور · تعديل مسار اعتماد · طلب خدمة إضافية ·
   تفاصيل حدث التدقيق (قبل/بعد)
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, D = BT.data, A = BT.A;
  var cfg = BT.config;

  /* =================================================================
     المالية  #/finance
     ================================================================= */
  BT.pages['finance'] = function (p, q) {
    A.setTitle('المالية');
    var tab = q.tab || 'expenses';
    var inv = D.jobs.filter(function (j) { return j.invoice; });
    BT.render(A.view(), h`
      ${A.head('المالية', 'المصروفات وفواتير مراكز الصيانة — التسجيل والاعتماد فقط، والدفع يتم خارج النظام بالتحويل البنكي أو الشيك',
        h`${A.btn('تصدير القيود', { icon: 'download', cls: 'btn-outline', action: 'export', arg: 'القيود المحاسبية' })}${A.btn('تسجيل مصروف', { icon: 'plus', cls: 'btn-primary', action: 'expense-new' })}`)}
      <div class="kpis">
        ${BT.kpi({ label: 'مصروفات الشهر', value: fmt.kwd(BT.sum(D.expenses, function (x) { return x.amount; })), sub: D.expenses.length + ' حركة', dot: 'b' })}
        ${BT.kpi({ label: 'فواتير بانتظار الاعتماد', value: String(inv.filter(function (j) { return j.invoice.status === 'بانتظار الاعتماد المالي'; }).length), dot: 'o', tone: 'warning' })}
        ${BT.kpi({ label: 'فواتير المراكز (نوفمبر)', value: fmt.kwd(BT.sum(inv, function (j) { return j.invoice.total; })), sub: inv.length + ' فاتورة', dot: 'p' })}
        ${BT.kpi({ label: 'رصيد الخزينة', value: fmt.kwd(D.treasury.balance), dot: 'g', href: '#/cash?tab=treasury' })}
      </div>
      ${BT.tabs('fin', [['expenses', 'المصروفات'], ['invoices', 'فواتير المراكز', inv.length]], tab, 'tabs-line')}
      <div data-panel="expenses" data-group="fin" class="${tab === 'expenses' ? 'active' : ''}"><div class="card"><div id="ex-table"></div></div></div>
      <div data-panel="invoices" data-group="fin" class="${tab === 'invoices' ? 'active' : ''}"><div class="card"><div id="inv-table"></div></div></div>`);
    BT.table(document.getElementById('ex-table'), {
      rows: function () { return D.expenses; },
      chips: { key: 'cat', options: ['صيانة', 'رسوم حكومية', 'مخالفات', 'تأمين', 'إيجارات', 'أخرى'].map(function (c) { return { v: c, t: c }; }) },
      columns: [
        { key: 'id', label: 'الرقم', render: function (x) { return h`<span class="num">${x.id}</span>`; } },
        { key: 'date', label: 'التاريخ', render: function (x) { return h`<span class="num">${fmt.date(x.date)}</span>`; } },
        { key: 'cat', label: 'البند', render: function (x) { return h`<span class="tag">${x.cat}</span>`; } },
        { key: 'desc', label: 'الوصف' },
        { key: 'amount', label: 'المبلغ (د.ك)', num: true, render: function (x) { return fmt.kwd(x.amount); } },
        { key: 'status', label: 'الحالة', render: function (x) { return BT.pill(x.status, x.status === 'بانتظار الاعتماد' ? 'o' : x.status === 'مدفوع' ? 'g' : 'b'); } }
      ],
      rowMenu: function (x) { return (x.status === 'بانتظار الاعتماد' ? [{ label: 'اعتماد', icon: 'check', onClick: function () { x.status = 'معتمد'; BT.toast('تم اعتماد ' + x.id); A.router.refresh(); } }] : []).concat([{ label: 'تسجيل كمدفوع', icon: 'banknote', onClick: function () { A.markPaid(x); } }, { label: 'المرفق', icon: 'paperclip', onClick: function () { A.docPreview(x.id + ' — ' + x.desc, [['البند', x.cat], ['المبلغ', fmt.kwd(x.amount) + ' د.ك'], ['التاريخ', fmt.date(x.date)]]); } }]); }
    });
    BT.table(document.getElementById('inv-table'), {
      rows: function () { return inv; },
      chips: { key: 'st', options: [{ v: 'بانتظار الاعتماد المالي', t: 'بانتظار الاعتماد' }, { v: 'مدفوعة', t: 'مدفوعة' }], match: function (j, v) { return j.invoice.status === v; } },
      columns: [
        { key: 'no', label: 'الفاتورة', sort: function (j) { return j.invoice.no; }, render: function (j) { return h`<b class="num">${j.invoice.no}</b>`; } },
        { key: 'center', label: 'المركز', render: function (j) { return D.centerName(j.center); } },
        { key: 'plate', label: 'السيارة', render: function (j) { return BT.plate(j.plate); } },
        { key: 'id', label: 'الطلب', render: function (j) { return h`<span class="num">${j.id}</span>`; } },
        { key: 'total', label: 'المبلغ (د.ك)', num: true, sort: function (j) { return j.invoice.total; }, render: function (j) { return fmt.kwd(j.invoice.total); } },
        { key: 'status', label: 'الحالة', sort: function (j) { return j.invoice.status; }, render: function (j) { return BT.pill(j.invoice.status, j.invoice.status === 'مدفوعة' ? 'g' : 'o'); } }
      ],
      rowClick: function (j) { A.jobDrawer(j); }
    });
  };
  A.markPaid = function (x) {
    BT.modal.open({
      title: 'تسجيل كمدفوع', subtitle: x.id + ' · ' + fmt.kwd(x.amount) + ' د.ك', icon: 'banknote', size: 'sm', form: true,
      body: h`<div class="form">${BT.f.select({ name: 'm', label: 'طريقة الدفع', required: true, options: ['تحويل بنكي', 'شيك', 'نقداً من الخزينة'] })}${BT.f.input({ name: 'ref', label: 'المرجع / رقم الشيك', required: true })}${BT.f.date({ name: 'd', label: 'التاريخ', required: true, value: cfg.today })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) { x.status = 'مدفوع'; BT.toast('سُجّل ' + x.id + ' كمدفوع', { sub: f.m + ' · ' + f.ref }); A.router.refresh(); }
    });
  };
  BT.actions['expense-new'] = function () {
    BT.modal.open({
      title: 'تسجيل مصروف', icon: 'receipt-text', form: true,
      body: h`<div class="form-grid">${BT.f.date({ name: 'date', label: 'التاريخ', required: true, value: cfg.today })}${BT.f.select({ name: 'cat', label: 'البند', required: true, options: ['صيانة', 'رسوم حكومية', 'مخالفات', 'تأمين', 'إيجارات', 'وقود', 'أخرى'] })}
        ${BT.f.input({ name: 'desc', label: 'الوصف', required: true, full: true })}${BT.f.money({ name: 'amount', label: 'المبلغ', required: true, min: 0.25 })}${BT.f.select({ name: 'car', label: 'مرتبط بسيارة', optional: true, options: D.vehicles.slice(0, 60).map(function (v) { return v.plate; }) })}
        ${BT.f.upload({ name: 'att', label: 'الفاتورة / الإيصال', required: true, full: true })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ وإرسال للاعتماد', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) { D.expenses.unshift({ id: 'EX-' + (4411 + D.expenses.length - 6), date: f.date, cat: f.cat, desc: f.desc, amount: f.amount, status: 'بانتظار الاعتماد' }); BT.toast('تم تسجيل المصروف'); if (A.router.current === 'finance') A.router.refresh(); }
    });
  };

  /* =================================================================
     التقارير  #/reports?cat=maint
     ================================================================= */
  var CATS = [['fleet', 'الأسطول'], ['daily', 'العمل اليومي'], ['km', 'الكيلومترات'], ['cash', 'الكاش'], ['maint', 'الصيانة'], ['acc', 'الحوادث'], ['pay', 'الرواتب']];
  BT.pages['reports'] = function (p, q) {
    A.setTitle('التقارير');
    var cat = q.cat || 'maint', period = 'هذا الشهر';
    BT.render(A.view(), h`
      ${A.head('أرقام تستطيع أن تبني عليها قراراً', 'كل تقرير بفلاتر التاريخ والفرع والسائق والسيارة', h`${A.btn('Excel', { icon: 'file-spreadsheet', cls: 'btn-outline', action: 'export', arg: 'report' })}${A.btn('PDF', { icon: 'file-text', cls: 'btn-outline', action: 'export-pdf' })}`)}
      <div class="toolbar" style="margin:0">
        <button type="button" class="chip active" id="rp-period" aria-haspopup="menu">${icon('calendar', 14)} <span>${period}</span> ${icon('chevron-down', 14)}</button>
        <select class="select" style="width:auto;height:32px;border-radius:16px" aria-label="الفرع"><option>كل الفروع</option>${D.company.branches.map(function (b) { return h`<option>فرع ${b}</option>`; })}</select>
        <div class="search-box" style="max-width:220px">${icon('search', 16)}<input class="input" style="height:32px" placeholder="سائق أو سيارة…" aria-label="سائق أو سيارة"></div>
      </div>
      ${BT.tabs('rep', CATS, cat)}
      <div id="rp-body" class="col"></div>`);
    function draw() { BT.render(document.getElementById('rp-body'), REPORTS[cat]()); if (cat === 'daily') BT.chart.bars(document.getElementById('rp-chart'), { name: 'الطلبات', labels: D.history.days.map(BT.date.dayName), sublabels: D.history.days.map(fmt.dm), values: D.history.orders, unitLabel: 'طلب', height: 220 }); }
    A.view().querySelector('[data-tabs="rep"]').addEventListener('bt:tab', function (e) { cat = e.detail; draw(); });
    document.getElementById('rp-period').addEventListener('click', function (e) {
      var b = e.currentTarget;
      BT.menu(b, ['اليوم', 'أمس', 'آخر 7 أيام', 'هذا الشهر', 'الشهر الماضي'].map(function (x) { return { label: x, checked: x === period, onClick: function () { period = x; b.querySelector('span').textContent = x; BT.toast('الفترة: ' + x, { type: 'info', sub: 'البيانات التجريبية ثابتة — في النظام الفعلي تتغير الأرقام' }); } }; }).concat([{ sep: true }, { label: 'فترة مخصصة…', icon: 'calendar-range', onClick: function () { A.customRange(function (t) { period = t; b.querySelector('span').textContent = t; }); } }]), { align: 'start' });
    });
    draw();
  };
  A.customRange = function (cb) {
    BT.modal.open({
      title: 'فترة مخصصة', icon: 'calendar-range', size: 'sm', form: true,
      body: h`<div class="form-grid">${BT.f.date({ name: 'from', label: 'من', required: true, value: '2026-11-01' })}${BT.f.date({ name: 'to', label: 'إلى', required: true, value: cfg.today, validate: 'afterFrom' })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'تطبيق', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) { cb(fmt.iso(f.from) + ' ← ' + fmt.iso(f.to)); }
    });
  };
  BT.validators.afterFrom = function (v, el, form) { return v < form.querySelector('[name=from]').value ? 'تاريخ النهاية قبل البداية' : ''; };

  var REPORTS = {
    fleet: function () {
      var byModel = {}; D.vehicles.forEach(function (v) { var k = v.make + ' ' + v.model; byModel[k] = byModel[k] || { n: 0, a: 0, m: 0, i: 0 }; byModel[k].n++; if (v.status === 'مسلّمة') byModel[k].a++; else if (v.status === 'في الصيانة') byModel[k].m++; else byModel[k].i++; });
      var a = D.vehicles.filter(function (v) { return v.status === 'مسلّمة'; }).length;
      return h`<div class="kpis">${BT.kpi({ label: 'السيارات', value: fmt.int(D.vehicles.length), dot: 'b' })}${BT.kpi({ label: 'نسبة الاستخدام', value: (a / D.vehicles.length * 100).toFixed(1) + '%', sub: a + ' مسلّمة', dot: 'g' })}${BT.kpi({ label: 'بلا سائق', value: String(D.vehicles.filter(function (v) { return v.status === 'بلا سائق'; }).length), dot: 'o' })}${BT.kpi({ label: 'في الصيانة', value: String(D.vehicles.filter(function (v) { return v.status === 'في الصيانة'; }).length), dot: 'p' })}</div>
        <div class="card"><div class="card-h"><div class="card-t">حسب الموديل</div></div>${BT.chart.table(['الموديل', 'العدد', 'مسلّمة', 'في الصيانة', 'بلا سائق'], Object.keys(byModel).sort(function (x, y) { return byModel[y].n - byModel[x].n; }).map(function (k) { var r = byModel[k]; return [raw('<span class="ltr">' + BT.esc(k) + '</span>'), String(r.n), String(r.a), String(r.m), String(r.i)]; }))}</div>`;
    },
    daily: function () {
      var st = D.reportStats();
      var top = D.reports.filter(function (r) { return r.orders != null; }).sort(function (x, y) { return y.orders - x.orders; }).slice(0, 8);
      return h`<div class="kpis">${BT.kpi({ label: 'تقارير مرسلة', value: fmt.int(st.sent), dot: 'b' })}${BT.kpi({ label: 'في الوقت', value: (st.sent / st.started * 100).toFixed(1) + '%', sub: 'من الذين بدؤوا يومهم', dot: 'g' })}${BT.kpi({ label: 'متأخرة', value: String(st.late), dot: 'o' })}${BT.kpi({ label: 'الطلبات', value: fmt.int(st.orders), dot: 'p' })}</div>
        <div class="grid-2"><div class="card"><div class="card-h"><div class="card-t">الطلبات — آخر 7 أيام</div></div><div id="rp-chart"></div></div>
        <div class="card"><div class="card-h"><div class="card-t">الأعلى طلبات اليوم</div></div>${BT.chart.table(['السائق', 'الطلبات', 'الكاش (د.ك)'], top.map(function (r) { return [raw('<bdi>' + BT.esc(r.driver) + '</bdi>'), String(r.orders), fmt.kwd(r.cash)]; }))}</div></div>`;
    },
    km: function () {
      var rs = D.reports.filter(function (r) { return r.end; });
      var km = BT.sum(rs, function (r) { return r.end - r.start; }), gps = BT.sum(rs, function (r) { return r.gps; });
      var top = rs.slice().sort(function (x, y) { return (y.end - y.start - y.gps) - (x.end - x.start - x.gps); }).slice(0, 8);
      return h`<div class="kpis">${BT.kpi({ label: 'كم اليوم (العداد)', value: fmt.km(km), dot: 'b' })}${BT.kpi({ label: 'كم اليوم (GPS)', value: fmt.km(gps), dot: 'g' })}${BT.kpi({ label: 'متوسط للسائق', value: (km / rs.length).toFixed(0) + ' كم', dot: 'p' })}${BT.kpi({ label: 'متوسط الفرق', value: ((km - gps) / rs.length).toFixed(1) + ' كم', sub: 'العداد − GPS', dot: 'o' })}</div>
        <div class="card"><div class="card-h"><div class="card-t">أكبر فرق بين العداد وGPS اليوم</div><span class="card-meta">الفرق الكبير يعني استخدام السيارة دون الهاتف</span></div>${BT.chart.table(['السائق', 'السيارة', 'العداد (كم)', 'GPS (كم)', 'الفرق'], top.map(function (r) { return [raw('<bdi>' + BT.esc(r.driver) + '</bdi>'), raw('<span class="plate">' + BT.esc(r.plate) + '</span>'), String(r.end - r.start), String(r.gps), String(r.end - r.start - r.gps)]; }))}</div>`;
    },
    cash: function () {
      var ds = D.employees.filter(function (e) { return e.role === 'سائق'; });
      var b = [['0 – 20', 0, 20], ['20 – 50', 20, 50], ['50 – 80', 50, 80], ['فوق 80', 80, 1e9]].map(function (x) { var g = ds.filter(function (e) { return e.balance > x[1] && e.balance <= x[2]; }); return { label: x[0] + ' د.ك', n: g.length, s: BT.sum(g, function (e) { return e.balance; }) }; });
      return h`<div class="kpis">${BT.kpi({ label: 'الأرصدة لدى السائقين', value: fmt.kwd(BT.sum(ds, function (e) { return e.balance; })), dot: 'o' })}${BT.kpi({ label: 'فوق حد التنبيه', value: String(b[3].n), dot: 'r' })}${BT.kpi({ label: 'تحصيلات اليوم', value: fmt.kwd(D.treasury.collectedToday), dot: 'g' })}${BT.kpi({ label: 'رصيد الخزينة', value: fmt.kwd(D.treasury.balance), dot: 'b' })}</div>
        <div class="grid-2"><div class="card"><div class="card-h"><div class="card-t">عدد السائقين حسب الرصيد</div></div>${BT.chart.hbars({ rows: b.map(function (x) { return { label: x.label, value: x.n }; }), unit: 'سائق' })}</div>
        <div class="card"><div class="card-h"><div class="card-t">مجموع الأرصدة حسب الشريحة</div></div>${BT.chart.table(['الشريحة', 'السائقون', 'المجموع (د.ك)'], b.map(function (x) { return [x.label, String(x.n), fmt.kwd(x.s)]; }))}</div></div>`;
    },
    maint: function () {
      var cs = D.centerStats(), v = BT.sum(cs, function (c) { return c.visits; }), cost = BT.sum(cs, function (c) { return c.cost; });
      var avg = BT.sum(cs, function (c) { return c.avgDays * c.visits; }) / v;
      return h`<div class="kpis">${BT.kpi({ label: 'زيارات الصيانة', value: String(v), sub: fmt.month(2026, 11), dot: 'b' })}${BT.kpi({ label: 'متوسط مدة البقاء', value: avg.toFixed(1) + ' يوم', sub: 'كل المراكز', dot: 'p' })}${BT.kpi({ label: 'تكلفة الصيانة', value: fmt.kwd(cost), sub: 'د.ك · شاملة العروض المعتمدة', dot: 'o' })}${BT.kpi({ label: 'عروض فوق حد الاعتماد', value: String(D.overLimitApproved()), sub: 'اعتُمدت قبل الإصلاح', dot: 'g' })}</div>
        <div class="card"><div class="card-h"><div class="card-t">حسب مركز الصيانة</div><span class="card-meta">كل الفروع · ${fmt.month(2026, 11)}</span></div>
          <div class="table-wrap"><table class="t"><thead><tr><th>المركز</th><th class="num">الزيارات</th><th class="num">متوسط البقاء (يوم)</th><th class="num">التكلفة (د.ك)</th></tr></thead><tbody>${cs.map(function (c) { return h`<tr><td>${c.center.name}</td><td class="num">${c.visits}</td><td class="num">${c.avgDays.toFixed(1)}</td><td class="num">${fmt.kwd(c.cost)}</td></tr>`; })}</tbody><tfoot><tr><td>الإجمالي</td><td class="num">${v}</td><td class="num">${avg.toFixed(1)}</td><td class="num">${fmt.kwd(cost)}</td></tr></tfoot></table></div></div>
        <div class="card"><div class="card-h"><div class="card-t">متوسط مدة البقاء حسب المركز</div></div>${BT.chart.hbars({ rows: cs.map(function (c) { return { label: c.center.name, value: +c.avgDays.toFixed(1) }; }), max: 4, unit: 'يوم' })}</div>`;
    },
    acc: function () {
      var by = {}; D.accidents.forEach(function (a) { var k = a.liability || 'قيد الدراسة'; by[k] = (by[k] || 0) + 1; });
      return h`<div class="kpis">${BT.kpi({ label: 'الحوادث', value: String(D.accidents.length), dot: 'r' })}${BT.kpi({ label: 'التلفيات المقدّرة', value: fmt.kwd(BT.sum(D.accidents, function (a) { return a.estimate || 0; })), dot: 'o' })}${BT.kpi({ label: 'خصومات على السائقين', value: fmt.kwd(BT.sum(D.deductions.filter(function (d) { return /حادث/.test(d.reason); }), function (d) { return d.total; })), dot: 'p' })}${BT.kpi({ label: 'بانتظار تقرير الشرطة', value: String(D.accidents.filter(function (a) { return !a.police; }).length), dot: 'b' })}</div>
        <div class="card"><div class="card-h"><div class="card-t">حسب المسؤولية</div></div>${BT.chart.hbars({ rows: Object.keys(by).map(function (k) { return { label: k, value: by[k] }; }), unit: 'حادث' })}</div>`;
    },
    pay: function () {
      var rows = D.payroll.rows, by = {};
      rows.forEach(function (r) { by[r.role] = by[r.role] || { n: 0, s: 0 }; by[r.role].n++; by[r.role].s += r.net; });
      return h`<div class="kpis">${BT.kpi({ label: 'الموظفون', value: fmt.int(rows.length), dot: 'b' })}${BT.kpi({ label: 'صافي الرواتب', value: fmt.kwd(BT.sum(rows, function (r) { return r.net; })), dot: 'g' })}${BT.kpi({ label: 'الخصومات', value: fmt.kwd(BT.sum(rows, function (r) { return r.deductions; })), dot: 'r' })}${BT.kpi({ label: 'الحوافز', value: fmt.kwd(BT.sum(rows, function (r) { return r.incentives; })), dot: 'p' })}</div>
        <div class="card"><div class="card-h"><div class="card-t">حسب الوظيفة</div><span class="card-meta">${D.payroll.month}</span></div>${BT.chart.table(['الوظيفة', 'العدد', 'الصافي (د.ك)'], Object.keys(by).map(function (k) { return [k, String(by[k].n), fmt.kwd(by[k].s)]; }))}</div>`;
    }
  };

  /* ---------- تصدير ---------- */
  BT.actions['export'] = function (name) { A.exportDialog(name && name !== 'report' ? name : 'التقرير', 'xlsx'); };
  BT.actions['export-pdf'] = function () { A.exportDialog('التقرير', 'pdf'); };
  A.exportDialog = function (name, fmtDefault) {
    BT.modal.open({
      title: 'تصدير ' + name, icon: 'download', form: true,
      body: h`<div class="form">${BT.f.radios({ name: 'f', label: 'الصيغة', required: true, value: fmtDefault || 'xlsx', options: [{ v: 'xlsx', t: 'Excel', d: 'للتحليل والتعديل' }, { v: 'pdf', t: 'PDF', d: 'للطباعة والمشاركة' }, { v: 'csv', t: 'CSV', d: 'للأنظمة الأخرى' }] })}
        ${BT.f.select({ name: 'p', label: 'الفترة', value: 'اليوم', placeholder: false, options: ['اليوم', 'آخر 7 أيام', 'هذا الشهر', 'الشهر الماضي'] })}
        ${BT.f.switch({ name: 'charts', label: 'إرفاق الرسوم البيانية (PDF فقط)', checked: true })}${BT.f.switch({ name: 'filters', label: 'تطبيق الفلاتر الحالية', checked: true })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'تصدير', cls: 'btn-primary', icon: 'download', submit: true }],
      onSubmit: function (f) { return new Promise(function (res) { setTimeout(function () { res(true); BT.toast('تم تجهيز ' + name, { sub: f.p + ' · ' + f.f.toUpperCase(), action: { label: 'تحميل', fn: function () { A.soon('تحميل الملف'); } } }); }, 700); }); }
    });
  };

  /* =================================================================
     الاعتمادات  #/approvals
     ================================================================= */
  BT.pages['approvals'] = function () {
    A.setTitle('الاعتمادات');
    BT.render(A.view(), h`
      ${A.head('كل ما ينتظر قرارك في مكان واحد', 'المسارات قابلة للضبط من الإعدادات', h`<a class="btn btn-outline" href="#/settings?tab=flows">${icon('git-branch', 15)} مسارات الاعتماد</a>`)}
      <div class="card flush">${D.approvals.length ? h`<div class="list" style="padding:6px 12px">${D.approvals.map(function (x) {
        return h`<div class="li" style="padding:14px 4px"><span class="li-ic ${x.tone}">${icon({ 'عرض سعر صيانة': 'wrench', 'فاتورة': 'receipt-text', 'كشف رواتب': 'receipt', 'تقارير يومية': 'clipboard-list', 'خصم': 'minus-circle', 'مراجعة عداد': 'gauge', 'تسوية كاش': 'scale' }[x.type] || 'badge-check', 17)}</span>
          <div class="li-main"><div class="li-t">${x.title}</div><div class="li-d">${x.type} · ${x.meta} · ${x.age}</div></div>
          ${x.amount != null ? h`<b class="hide-sm">${BT.amt(x.amount)}</b>` : ''}<button type="button" class="btn btn-sm btn-primary" data-ap="${x.id}">مراجعة</button></div>`;
      })}</div>` : BT.empty('circle-check', 'لا شيء بانتظارك', 'كل الاعتمادات مكتملة')}</div>`);
    BT.on(A.view(), 'click', '[data-ap]', function (e, b) {
      var x = D.approvals.find(function (a) { return a.id === b.getAttribute('data-ap'); });
      var job = x.ref && D.jobs.find(function (j) { return j.id === x.ref; });
      if (x.id === 'AP-1' && job) return A.approveEstimate(job);
      if (x.id === 'AP-2' && job) return A.reviewInvoice(job);
      if (x.link === 'payroll' && x.type === 'كشف رواتب') return A.go('payroll');
      if (x.link === 'daily' || x.link === 'odometer') return A.go(x.link);
      A.decide(x);
    });
  };
  A.decide = function (x) {
    BT.modal.open({
      title: 'قرار: ' + x.type, subtitle: x.title, icon: 'badge-check', form: true,
      body: h`${BT.kv([['النوع', x.type], ['التفاصيل', x.meta], x.amount != null ? ['المبلغ', BT.amt(x.amount)] : null, ['مقدّم منذ', x.age]].filter(Boolean))}
        <div class="form mt-16">${BT.f.radios({ name: 'd', label: 'القرار', required: true, options: [{ v: 'ok', t: 'اعتماد' }, { v: 'no', t: 'رفض' }] })}${BT.f.textarea({ name: 'c', label: 'ملاحظة', optional: true, rows: 2 })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ القرار', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) {
        if (f.d === 'no' && !f.c) { BT.toast('سبب الرفض مطلوب', { type: 'error' }); return false; }
        D.approvals = D.approvals.filter(function (a) { return a !== x; });
        var dd = D.deductions.find(function (d) { return x.type === 'خصم' && x.title.indexOf(d.driver) > -1 && d.status === 'بانتظار الاعتماد'; }); if (dd) dd.status = f.d === 'ok' ? 'معتمد' : 'مرفوض';
        BT.toast(f.d === 'ok' ? 'تم الاعتماد' : 'تم الرفض', { sub: x.title }); A.router.refresh();
      }
    });
  };

  /* =================================================================
     الإعدادات والصلاحيات  #/settings?tab=
     ================================================================= */
  BT.pages['settings'] = function (p, q) {
    A.setTitle('الإعدادات والصلاحيات');
    var tab = q.tab || 'rules';
    var TABS = [['company', 'الشركة'], ['users', 'المستخدمون', D.users.length], ['roles', 'الأدوار والصلاحيات'], ['rules', 'قواعد التشغيل'], ['flows', 'مسارات الاعتماد'], ['notify', 'الإشعارات'], ['addons', 'الخدمات الإضافية']];
    BT.render(A.view(), h`${A.head('الإعدادات والصلاحيات', 'التغييرات تُسجَّل في سجل التدقيق باسمك')}
      ${BT.tabs('set', TABS, tab, 'tabs-line')}
      <div data-panel="company" data-group="set" class="${tab === 'company' ? 'active' : ''}"><form class="card form" id="f-company" novalidate>
        <div class="form-grid">${BT.f.input({ name: 'name', label: 'اسم الشركة', required: true, value: D.company.name })}${BT.f.input({ name: 'legal', label: 'الاسم القانوني', value: D.company.legal })}${BT.f.input({ name: 'cr', label: 'رقم السجل التجاري', optional: true })}${BT.f.input({ name: 'lic', label: 'رقم الترخيص', optional: true })}${BT.f.input({ name: 'addr', label: 'العنوان', optional: true, full: true })}${BT.f.upload({ name: 'logo', label: 'الشعار', optional: true, accept: 'image/*', accept_label: 'PNG أو SVG · مربع' })}
          <div class="field"><label>الفروع</label><div class="flex gap-6" style="flex-wrap:wrap">${D.company.branches.map(function (b) { return h`<span class="tag">${icon('building-2', 13)} ${b}</span>`; })}<button type="button" class="btn btn-xs btn-soft" data-action="branch-new">${icon('plus', 12)} فرع</button></div></div></div>
        <div class="card-f"><button type="submit" class="btn btn-primary">${icon('check', 15)} حفظ</button></div></form></div>
      <div data-panel="users" data-group="set" class="${tab === 'users' ? 'active' : ''}"><div class="card"><div id="usr-table"></div></div></div>
      <div data-panel="roles" data-group="set" class="${tab === 'roles' ? 'active' : ''}"><div class="card"><div class="card-h"><div class="flex items-center gap-8"><label class="label" for="role-sel">الدور</label><select class="select" id="role-sel" style="width:220px">${D.roles.map(function (r) { return h`<option>${r}</option>`; })}</select></div><button type="button" class="btn btn-primary" id="perm-save">${icon('check', 15)} حفظ الصلاحيات</button></div><div id="perm-box"></div></div></div>
      <div data-panel="rules" data-group="set" class="${tab === 'rules' ? 'active' : ''}"><form class="card" id="f-rules" novalidate>
        <div class="card-h"><div><div class="card-t">قواعد التشغيل</div><div class="card-meta">القيم الحالية مطبقة على كل الشاشات</div></div></div>
        <div class="form-grid">
          ${BT.f.money({ name: 'cashAlert', label: 'حد تنبيه رصيد السائق', required: true, value: fmt.kwd(cfg.cashAlert), hint: 'تنبيه للمحاسب والمشرف فقط — لا يوقف السائق' })}
          ${BT.f.input({ name: 'signalLossMin', label: 'انقطاع الإشارة قبل التنبيه', required: true, num: true, min: 3, max: 60, value: cfg.signalLossMin, addon: 'دقيقة' })}
          ${BT.f.input({ name: 'odoGapKm', label: 'فرق العداد بين يومين قبل التنبيه', required: true, num: true, min: 0, value: cfg.odoGapKm, addon: 'كم' })}
          ${BT.f.input({ name: 'gpsIntervalSec', label: 'تحديث الموقع كل', required: true, num: true, min: 10, max: 120, value: cfg.gpsIntervalSec, addon: 'ثانية', hint: 'أقل = استهلاك بطارية أعلى لهاتف السائق' })}
          ${BT.f.money({ name: 'approvalLimit', label: 'حد اعتماد عروض الصيانة', required: true, value: fmt.kwd(cfg.approvalLimit) })}
          ${BT.f.input({ name: 'maxDeductionPct', label: 'الحد الأقصى للخصم من الراتب', required: true, num: true, min: 0, max: 100, value: cfg.maxDeductionPct, addon: '%', hint: 'يُضبط وفق رأي المستشار القانوني وقانون العمل الكويتي' })}
          ${BT.f.input({ name: 'deadline', label: 'آخر موعد للتقرير اليومي', type: 'time', value: '23:59' })}
          <div class="field"><label>متطلبات التقرير اليومي</label><div class="col" style="gap:8px">${BT.f.switch({ name: 'reqShot', label: 'لقطة شاشة تطبيق التوصيل إلزامية', checked: true })}${BT.f.switch({ name: 'reqOdo', label: 'صورة عداد نهاية اليوم إلزامية', checked: true })}</div></div>
        </div><div class="card-f"><button type="submit" class="btn btn-primary">${icon('check', 15)} حفظ القواعد</button><span class="muted fs-sm">آخر تعديل: سامي الأنصاري · اليوم 09:02</span></div></form></div>
      <div data-panel="flows" data-group="set" class="${tab === 'flows' ? 'active' : ''}"><div class="card flush"><div class="list" style="padding:6px 12px">${FLOWS.map(function (f, i) {
        return h`<div class="li" style="padding:14px 4px"><span class="li-ic b">${icon('git-branch', 16)}</span><div class="li-main"><div class="li-t">${f.name}</div><div class="li-d">${f.steps.map(function (s) { return s[0] + (s[1] ? ' (فوق ' + s[1] + ')' : ''); }).join(' ← ')}</div></div><button type="button" class="btn btn-sm btn-outline" data-flow="${i}">${icon('pencil', 13)} تعديل</button></div>`;
      })}</div></div></div>
      <div data-panel="notify" data-group="set" class="${tab === 'notify' ? 'active' : ''}"><div class="card"><div class="card-h"><div><div class="card-t">قنوات الإشعارات</div><div class="card-meta">البريد الإلكتروني خدمة إضافية مدفوعة — تُفعَّل عند الطلب</div></div></div>
        <div class="table-wrap"><table class="t perm"><thead><tr><th>الحدث</th><th>داخل النظام</th><th>إشعار التطبيق</th><th>البريد الإلكتروني</th></tr></thead><tbody>${['انقطاع إشارة', 'تقرير متأخر', 'رصيد فوق حد التنبيه', 'عرض سعر بانتظار الاعتماد', 'حادث جديد', 'مستند ينتهي خلال 30 يوماً', 'فرق عداد بين يومين'].map(function (ev) {
          return h`<tr><td>${ev}</td><td><label class="check"><input type="checkbox" checked aria-label="داخل النظام"></label></td><td><label class="check"><input type="checkbox" ${ev === 'مستند ينتهي خلال 30 يوماً' ? '' : raw('checked')} aria-label="إشعار التطبيق"></label></td><td><span data-tip="خدمة إضافية مدفوعة"><label class="check"><input type="checkbox" disabled aria-label="البريد"></label></span></td></tr>`;
        })}</tbody></table></div><div class="card-f"><button type="button" class="btn btn-primary" data-action="notify-save">${icon('check', 15)} حفظ</button><button type="button" class="btn btn-ghost" data-action="addon" data-arg="email">${icon('mail', 15)} طلب تفعيل البريد</button></div></div></div>
      <div data-panel="addons" data-group="set" class="${tab === 'addons' ? 'active' : ''}"><div class="grid-3">${ADDONS.map(function (a) {
        return h`<div class="card col" style="gap:10px"><span class="icon-tile lg">${icon(a.icon, 22)}</span><h3>${a.name}</h3><p class="fs-sm text-2" style="line-height:1.7">${a.desc}</p><div class="highlight-box fs-sm"><b>${a.price}</b></div><div class="mt-8">${BT.pill(a.state, a.state === 'غير مفعّل' ? 'n' : 'g')}</div><button type="button" class="btn btn-outline mt-8" data-action="addon" data-arg="${a.key}">${icon('send', 14)} طلب الخدمة</button></div>`;
      })}</div></div>`);

    document.getElementById('f-company').addEventListener('submit', function (e) { e.preventDefault(); if (BT.form.validate(e.target)) BT.toast('تم حفظ بيانات الشركة'); });
    document.getElementById('f-rules').addEventListener('submit', function (e) {
      e.preventDefault(); if (!BT.form.validate(e.target)) return;
      var v = BT.form.values(e.target), changed = [];
      ['cashAlert', 'signalLossMin', 'odoGapKm', 'gpsIntervalSec', 'approvalLimit', 'maxDeductionPct'].forEach(function (k) { if (v[k] !== cfg[k]) { changed.push(k); cfg[k] = v[k]; } });
      BT.toast(changed.length ? 'تم حفظ ' + changed.length + ' تغيير' : 'لا توجد تغييرات', { type: changed.length ? 'success' : 'info', sub: changed.length ? 'مسجّل في سجل التدقيق' : '' });
    });
    BT.form.live(document.getElementById('f-rules'));
    BT.table(document.getElementById('usr-table'), {
      rows: function () { return D.users; },
      search: { placeholder: 'ابحث بالاسم…', text: function (u) { return u.name + ' ' + u.role; } },
      tools: A.btn('إضافة مستخدم', { icon: 'user-plus', cls: 'btn-primary', action: 'user-new' }),
      columns: [
        { key: 'name', label: 'المستخدم', render: function (u) { return BT.person(u.name, u.id); } },
        { key: 'role', label: 'الدور', render: function (u) { return h`<span class="tag">${u.role}</span>`; } },
        { key: 'phone', label: 'الجوال', render: function (u) { return h`<span class="num">${u.phone}</span>`; } },
        { key: 'twoFA', label: 'التحقق بخطوتين', render: function (u) { return u.twoFA ? BT.pill('مفعّل', 'g') : BT.pill('غير مفعّل', 'o'); } },
        { key: 'last', label: 'آخر دخول' },
        { key: 'active', label: 'الحالة', render: function (u) { return u.active ? BT.pill('نشط', 'g', true) : BT.pill('معطّل', 'n', true); } }
      ],
      rowMenu: function (u) { return [{ label: 'تغيير الدور', icon: 'shield', onClick: function () { A.userForm(u); } }, { label: 'إعادة تعيين كلمة المرور', icon: 'key-round', onClick: function () { BT.toast('أُرسل رابط إعادة التعيين إلى ' + u.phone); } }, { sep: true }, { label: u.active ? 'تعطيل الحساب' : 'تفعيل الحساب', icon: u.active ? 'ban' : 'check', danger: u.active, onClick: function () { BT.confirm({ title: (u.active ? 'تعطيل ' : 'تفعيل ') + u.name, message: u.active ? 'لن يتمكن من الدخول، وتُنهى جلساته الحالية فوراً.' : 'سيتمكن من الدخول بدوره الحالي.', tone: u.active ? 'danger' : 'success', confirmText: u.active ? 'تعطيل' : 'تفعيل' }).then(function (r) { if (r.ok) { u.active = !u.active; BT.toast('تم'); A.go('settings?tab=users'); } }); } }]; }
    });
    function perms() {
      var role = document.getElementById('role-sel').value, m = D.perms(role);
      BT.render(document.getElementById('perm-box'), h`<div class="table-wrap"><table class="t perm compact"><thead><tr><th>الوحدة</th>${D.permActions.map(function (a) { return h`<th>${a}</th>`; })}</tr></thead><tbody>${D.permModules.map(function (mod, i) {
        return h`<tr><td>${mod}</td>${D.permActions.map(function (a, j) { return h`<td><label class="check"><input type="checkbox" aria-label="${mod} — ${a}"${m[i][j] ? raw(' checked') : ''}${role === 'مدير النظام' ? raw(' disabled') : ''}></label></td>`; })}</tr>`;
      })}</tbody></table></div>${role === 'مدير النظام' ? h`<div class="banner info mt-12 fs-sm">${icon('lock', 15)}<div>صلاحيات مدير النظام كاملة ولا يمكن تعديلها.</div></div>` : ''}`);
    }
    document.getElementById('role-sel').addEventListener('change', perms); perms();
    document.getElementById('perm-save').onclick = function () { BT.toast('تم حفظ صلاحيات ' + document.getElementById('role-sel').value, { sub: 'تُطبّق عند الدخول التالي للمستخدمين' }); };
    BT.on(A.view(), 'click', '[data-flow]', function (e, b) { A.flowEdit(FLOWS[+b.getAttribute('data-flow')]); });
  };
  var FLOWS = [
    { name: 'عروض أسعار الصيانة', steps: [['مدير الصيانة', '100.000'], ['المالية', '300.000']] },
    { name: 'فواتير مراكز الصيانة', steps: [['مدير الصيانة', ''], ['المالية', '']] },
    { name: 'الخصومات من الراتب', steps: [['الموارد البشرية', ''], ['مدير العمليات', '']] },
    { name: 'تسويات الكاش', steps: [['المحاسب الأول', '']] },
    { name: 'كشف الرواتب الشهري', steps: [['المالية', ''], ['مدير العمليات', '']] },
    { name: 'التقارير اليومية', steps: [['مشرف تشغيل', '']] }
  ];
  A.flowEdit = function (f) {
    var d = BT.modal.open({
      title: 'مسار اعتماد: ' + f.name, icon: 'git-branch', size: 'lg', form: true,
      body: h`<div id="fl-steps" class="col" style="gap:10px"></div><button type="button" class="btn btn-soft btn-sm mt-12" id="fl-add">${icon('plus', 14)} إضافة مستوى</button>
        <div class="banner info mt-16 fs-sm">${icon('info', 15)}<div>المستويات تُنفَّذ بالترتيب. المبلغ اختياري: المستوى يُطلب فقط عندما يتجاوز المبلغ هذا الحد.</div></div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ المسار', cls: 'btn-primary', submit: true }],
      onSubmit: function () {
        f.steps = BT.$$('.fl-row', d.el).map(function (r) { return [r.querySelector('select').value, r.querySelector('input').value]; });
        BT.toast('تم حفظ مسار ' + f.name); A.go('settings?tab=flows');
      }
    });
    var steps = f.steps.slice();
    function draw() {
      BT.render(d.el.querySelector('#fl-steps'), h`${steps.map(function (s, i) {
        return h`<div class="fl-row flex items-center gap-10"><span class="step active"><span class="sn">${i + 1}</span></span>
          <select class="select" required aria-label="المعتمد">${D.roles.filter(function (r) { return r !== 'سائق' && r !== 'مركز صيانة'; }).concat(['المحاسب الأول']).map(function (r) { return h`<option${r === s[0] ? raw(' selected') : ''}>${r}</option>`; })}</select>
          <div class="input-group" style="width:230px"><input class="input num-in" placeholder="كل المبالغ" value="${s[1]}" aria-label="فوق مبلغ"><span class="addon">فوق د.ك</span></div>
          <button type="button" class="icon-btn sm" data-del="${i}" aria-label="حذف المستوى"${steps.length < 2 ? raw(' disabled') : ''}>${icon('trash-2', 15)}</button></div>`;
      })}`);
    }
    d.el.querySelector('#fl-add').onclick = function () { steps = BT.$$('.fl-row', d.el).map(function (r) { return [r.querySelector('select').value, r.querySelector('input').value]; }); steps.push(['مدير العمليات', '']); draw(); };
    BT.on(d.el, 'click', '[data-del]', function (e, b) { steps = BT.$$('.fl-row', d.el).map(function (r) { return [r.querySelector('select').value, r.querySelector('input').value]; }); steps.splice(+b.getAttribute('data-del'), 1); draw(); });
    draw();
  };
  BT.actions['notify-save'] = function () { BT.toast('تم حفظ إعدادات الإشعارات'); };
  BT.actions['branch-new'] = function () {
    BT.modal.open({ title: 'إضافة فرع', icon: 'building-2', size: 'sm', form: true, body: h`<div class="form">${BT.f.input({ name: 'n', label: 'اسم الفرع', required: true })}</div>`, buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إضافة', cls: 'btn-primary', submit: true }], onSubmit: function (f) { D.company.branches.push(f.n); BT.toast('تمت إضافة فرع ' + f.n); A.go('settings?tab=company'); } });
  };
  BT.actions['user-new'] = function () { A.userForm(null); };
  A.userForm = function (u) {
    BT.modal.open({
      title: u ? 'تعديل المستخدم' : 'إضافة مستخدم', subtitle: u ? u.name : 'يصله رابط تفعيل على الجوال', icon: 'user-plus', form: true,
      body: h`<div class="form-grid">${BT.f.input({ name: 'name', label: 'الاسم', required: true, value: u && u.name, full: true })}${BT.f.input({ name: 'phone', label: 'الجوال', required: true, value: u && u.phone, validate: 'kwPhone', maxlength: 8 })}
        ${BT.f.select({ name: 'role', label: 'الدور', required: true, value: u && u.role, options: D.roles.filter(function (r) { return r !== 'سائق'; }) })}
        ${BT.f.select({ name: 'scope', label: 'نطاق الفروع', value: 'كل الفروع', placeholder: false, options: ['كل الفروع'].concat(D.company.branches) })}
        <div class="field full">${BT.f.switch({ name: 'twoFA', label: 'التحقق بخطوتين (OTP) إلزامي', checked: true })}</div></div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: u ? 'حفظ' : 'إضافة', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) {
        if (u) Object.assign(u, { name: f.name, phone: f.phone, role: f.role, twoFA: f.twoFA });
        else D.users.unshift({ id: 'U-' + (40 + D.users.length), name: f.name, phone: f.phone, role: f.role, twoFA: f.twoFA, last: '—', active: true });
        BT.toast(u ? 'تم حفظ المستخدم' : 'تمت إضافة ' + f.name, { sub: u ? '' : 'أُرسل رابط التفعيل إلى ' + f.phone }); A.go('settings?tab=users');
      }
    });
  };
  var ADDONS = [
    { key: 'email', icon: 'mail', name: 'خدمة البريد الإلكتروني', desc: 'إرسال التنبيهات والتقارير الدورية وإشعارات الاعتماد بالبريد الإلكتروني.', price: 'خدمة إضافية مدفوعة — السعر حسب الطلب', state: 'غير مفعّل' },
    { key: 'iphone', icon: 'smartphone', name: 'تطبيق السائق على iPhone', desc: 'نسخة iOS من تطبيق السائق منشورة على App Store بنفس خصائص نسخة أندرويد.', price: '250 د.ك سنوياً + 100 دولار رسوم App Store سنوياً', state: 'غير مفعّل' },
    { key: 'custom', icon: 'puzzle', name: 'تطوير إضافي', desc: 'تقارير أو شاشات أو تكاملات خارج نطاق الاشتراك الحالي.', price: 'بعرض سعر منفصل لكل طلب', state: 'غير مفعّل' }
  ];
  BT.actions['addon'] = function (key) {
    var a = ADDONS.find(function (x) { return x.key === key; });
    BT.modal.open({
      title: 'طلب: ' + a.name, icon: a.icon, form: true,
      body: h`<div class="highlight-box mb-12"><b>${a.price}</b></div><div class="form">${BT.f.textarea({ name: 'n', label: 'تفاصيل الطلب', optional: true, rows: 3 })}${BT.f.check({ name: 'ok', label: 'أوافق على أن الخدمة مدفوعة وفق عرض السعر', required: true })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إرسال الطلب لـ BrilliantTech', cls: 'btn-primary', icon: 'send', submit: true }],
      onSubmit: function () { BT.toast('أُرسل طلب ' + a.name, { sub: 'يتواصل معك فريق BrilliantTech بعرض السعر' }); }
    });
  };

  /* =================================================================
     سجل التدقيق  #/audit
     ================================================================= */
  BT.pages['audit'] = function () {
    A.setTitle('سجل التدقيق');
    BT.render(A.view(), h`${A.head('من فعل ماذا ومتى ومن أي جهاز', 'السجل لا يُعدَّل ولا يُحذف · يُحفظ على خوادم BrilliantTech', A.btn('تصدير', { icon: 'download', cls: 'btn-outline', action: 'export', arg: 'سجل التدقيق' }))}
      <div class="card"><div id="au-table"></div></div>`);
    BT.table(document.getElementById('au-table'), {
      rows: function () { return D.audit; },
      search: { placeholder: 'ابحث في السجل…' },
      chips: { key: 'user', options: [{ v: 'sys', t: 'النظام' }, { v: 'users', t: 'المستخدمون' }], match: function (a, v) { return (a.user === 'النظام') === (v === 'sys'); } },
      columns: [
        { key: 'time', label: 'الوقت', render: function (a) { return h`<span class="num">${fmt.dm(a.date)} ${a.time}</span>`; } },
        { key: 'user', label: 'المستخدم', render: function (a) { return a.user === 'النظام' ? h`<span class="tag">${icon('cpu', 12)} النظام</span>` : BT.person(a.user); } },
        { key: 'action', label: 'الإجراء', render: function (a) { return h`<b>${a.action}</b>`; } },
        { key: 'detail', label: 'التفاصيل', render: function (a) { return h`<span style="white-space:normal">${a.detail}</span>`; } },
        { key: 'device', label: 'الجهاز', render: function (a) { return h`<span class="muted fs-sm">${a.device}</span>`; } }
      ],
      rowClick: function (a) {
        var diff = /^(تعديل|تغيير)/.test(a.action) ? a.detail.split('←') : [];
        BT.drawer.open({
          title: a.action, subtitle: a.id + ' · ' + fmt.iso(a.date) + ' ' + a.time, icon: 'shield-check',
          body: h`${BT.kv([['المستخدم', a.user], ['الإجراء', a.action], ['الجهاز', a.device], ['رقم الحدث', h`<span class="num">${a.id}</span>`]])}
            <div class="section-t mt-16">التفاصيل</div>${diff.length === 2 ? h`<div class="highlight-box">${a.detail.split(':')[0]}<div class="mt-8"><span class="diff-old">${diff[0].split(':').pop().trim()}</span> ← <span class="diff-new">${diff[1].trim()}</span></div></div>` : h`<div class="highlight-box">${a.detail}</div>`}
            <div class="banner note mt-16 fs-sm">${icon('lock', 15)}<div>أحداث السجل للقراءة فقط.</div></div>`,
          buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }]
        });
      }
    });
  };
})();
