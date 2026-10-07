/* =====================================================================
   app/pages/reports.js — التقارير: العمل اليومي، الكيلومترات، الكاش وأعماره
   والخزينة، الصيانة، الحوادث، الرواتب. لكل تقرير فلاتر الفترة والشركة والفرع
   والسائق والسيارة (FR-RPT-08)، وتصدير Excel بلغة المستخدم و CSV، وطباعة
   تُحفظ PDF من نافذة الطباعة.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A, M = BT.mnt, C = BT.acc;

  var TABS = [
    ['daily', 'العمل اليومي', function () { return api.can('reports.view') || api.can('cash.view'); }],
    ['fleet', 'الأسطول', function () { return api.can('reports.view') && api.can('vehicles.view'); }],
    ['km', 'الكيلومترات', function () { return api.can('reports.view') && api.can('odometer.view'); }],
    ['cash', 'الكاش والخزينة', function () { return api.can('reports.view') && api.can('cash.view'); }],
    ['maintenance', 'الصيانة', function () { return api.can('reports.view') && api.can('maintenance.view'); }],
    ['accidents', 'الحوادث', function () { return api.can('reports.view') && api.can('accidents.view'); }],
    ['payroll', 'الرواتب', function () { return api.can('reports.view') && api.can('payroll.view'); }]
  ];

  BT.pages['reports'] = function (p, q) {
    A.setTitle('التقارير');
    var v = A.view(), tabs = TABS.filter(function (t) { return t[2](); }).map(function (t) { return [t[0], t[1]]; });
    if (!tabs.length) { BT.render(v, A.forbidden()); return; }
    var tab = tabs.some(function (t) { return t[0] === q.tab; }) ? q.tab : tabs[0][0];
    lists = null;
    BT.render(v, h`${A.head('التقارير', 'فلتر بالفترة والشركة والفرع والسائق والسيارة؛ تصدير Excel أو CSV، والطباعة تُحفظ PDF', '')}
      ${tabs.length > 1 ? BT.tabs('rep', tabs, tab, 'tabs-line') : ''}
      ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="rep" class="${t[0] === tab ? 'active' : ''}"><div data-p="${t[0]}"></div></div>`; })}`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      ({ daily: dailyPanel, fleet: fleetPanel, km: kmPanel, cash: cashPanel, maintenance: maintenancePanel, accidents: accidentsPanel, payroll: payrollPanel })[t](v.querySelector('[data-p="' + t + '"]'));
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/reports?tab=' + e.detail); });
    show(tab);
  };

  /* ---------- الفلاتر: القوائم تُحمّل مرة لكل فتح للصفحة ---------- */
  var lists = null, PICK = {};
  function loadLists() {
    if (lists) return lists;
    var none = Promise.resolve([]);
    lists = {
      drivers: api.can('employees.view') ? A.all('/employees', { is_driver: true }).catch(function () { return []; }) : none,
      employees: api.can('employees.view') ? A.all('/employees').catch(function () { return []; }) : none,
      vehicles: api.can('vehicles.view') ? A.all('/vehicles').catch(function () { return []; }) : none
    };
    return lists;
  }
  function personLabel(e) { return api.name(e.name) + ' — ' + e.employee_number; }
  function listFilter(name, label, kind) {
    return h`<div class="field"><label>${label}</label><input class="input" name="${name}" list="${BT.uid('fl')}" autocomplete="off" placeholder="الكل" data-list="${kind}"></div>`;
  }
  function fillLists(form) {
    BT.$$('[data-list]', form).forEach(function (input) {
      var kind = input.getAttribute('data-list'), dl = document.createElement('datalist');
      dl.id = input.getAttribute('list');
      input.parentNode.appendChild(dl);
      loadLists()[kind].then(function (rows) {
        PICK[kind] = {};
        rows.forEach(function (x) { PICK[kind][kind === 'vehicles' ? A.vehicleLabel(x) : personLabel(x)] = x.id; });
        BT.render(dl, h`${Object.keys(PICK[kind]).map(function (l) { return h`<option value="${l}"></option>`; })}`);
      });
    });
  }
  /* الفلاتر المختارة كمعاملات للخادم؛ null إن كُتب اسم ليس في القائمة */
  function picks(x) {
    var out = {};
    if (x.company_id) out.company_id = x.company_id;
    if (x.branch_id) out.branch_id = x.branch_id;
    var named = [['driver', 'drivers', 'driver_id', 'السائق'], ['employee', 'employees', 'driver_id', 'الموظف'], ['vehicle', 'vehicles', 'vehicle_id', 'السيارة']];
    for (var i = 0; i < named.length; i++) {
      var n = named[i], text = String(x[n[0]] || '').trim();
      if (!text) continue;
      var id = (PICK[n[1]] || {})[text];
      if (!id) { BT.toast('اختر ' + n[3] + ' من القائمة', { type: 'error' }); return null; }
      out[n[2]] = id;
    }
    return out;
  }
  function describe(form, x, months) {
    var parts = [(months ? 'من شهر ' : 'من ') + x.from + (months ? ' إلى شهر ' : ' إلى ') + x.to];
    BT.$$('select[name=company_id], select[name=branch_id]', form).forEach(function (s) { if (s.value) parts.push(s.options[s.selectedIndex].text); });
    ['driver', 'employee', 'vehicle'].forEach(function (n) { if (x[n]) parts.push(x[n]); });
    return parts.join(' · ');
  }
  function monthsBack(n) { var d = BT.config.today.split('-'), y = +d[0], m = +d[1] - n; while (m < 1) { m += 12; y--; } return y + '-' + (m < 10 ? '0' : '') + m; }

  /* شريط التقرير: الفترة، الفلاتر، الجدول المصدَّر، عرض، Excel، CSV، طباعة */
  function rangeForm(o) {
    var to = BT.config.today, f = o.filters || [];
    var companies = (api.companies || []).filter(function (c) { return c.is_active; }), branches = (api.branches || []).filter(function (b) { return b.is_active; });
    var period = o.months
      ? h`${BT.f.input({ name: 'from', label: 'من شهر', type: 'month', value: monthsBack(o.months - 1), required: true })}${BT.f.input({ name: 'to', label: 'إلى شهر', type: 'month', value: to.slice(0, 7), required: true })}`
      : h`${BT.f.date({ name: 'from', label: 'من', value: BT.date.add(to, -o.days), required: true })}${BT.f.date({ name: 'to', label: 'إلى', value: to, required: true })}`;
    return h`<form class="toolbar" data-range style="margin:0 0 12px">${period}
      ${f.indexOf('company') >= 0 && companies.length > 1 ? BT.f.select({ name: 'company_id', label: 'الشركة', value: '', placeholder: 'كل الشركات', options: companies.map(function (c) { return { v: c.id, t: api.name(c.name) }; }) }) : ''}
      ${f.indexOf('branch') >= 0 && branches.length > 1 ? BT.f.select({ name: 'branch_id', label: 'الفرع', value: '', placeholder: 'كل الفروع', options: branches.map(function (b) { return { v: b.id, t: api.name(b.name) }; }) }) : ''}
      ${f.indexOf('driver') >= 0 && api.can('employees.view') ? listFilter('driver', 'السائق', 'drivers') : ''}
      ${f.indexOf('employee') >= 0 && api.can('employees.view') ? listFilter('employee', 'الموظف', 'employees') : ''}
      ${f.indexOf('vehicle') >= 0 && api.can('vehicles.view') ? listFilter('vehicle', 'السيارة', 'vehicles') : ''}
      ${o.sections && o.sections.length > 1 && api.can('reports.export') ? BT.f.select({ name: 'section', label: 'الجدول المصدَّر', value: o.sections[0].v, placeholder: false, options: o.sections }) : ''}
      <button type="submit" class="btn btn-primary" style="align-self:flex-end">${icon('chart-column', 15)} عرض</button>
      ${api.can('reports.export') ? h`<button type="button" class="btn btn-outline" data-export="xlsx" style="align-self:flex-end">${icon('sheet', 15)} Excel</button><button type="button" class="btn btn-ghost" data-export="csv" style="align-self:flex-end">CSV</button>` : ''}
      <button type="button" class="btn btn-ghost" data-print style="align-self:flex-end">${icon('printer', 15)} طباعة / PDF</button></form>`;
  }
  /* o: {path, name, title, months, sections, load(query)}; الحمل يضع el._print = function () { return [أقسام] } */
  function wireRange(el, o) {
    var form = el.querySelector('[data-range]');
    fillLists(form);
    function read() {
      var x = BT.form.values(form), f = picks(x);
      if (!f) return null;
      var q = o.months ? { month_from: x.from + '-01', month_to: x.to + '-01' } : { date_from: x.from, date_to: x.to };
      return { x: x, q: Object.assign(q, f) };
    }
    form.addEventListener('submit', function (e) { e.preventDefault(); var r = read(); if (r) o.load(r.q); });
    BT.$$('[data-export]', form).forEach(function (b) {
      b.onclick = function () {
        var r = read(); if (!r) return;
        var ext = b.getAttribute('data-export'), section = r.x.section || (o.sections ? o.sections[0].v : null);
        var q = Object.assign({}, r.q, { format: ext }, section ? { section: section } : {});
        A.downloadFile(o.path, q, o.name + (section ? '-' + section : '') + '-' + r.x.from + '-' + r.x.to + '.' + ext);
      };
    });
    form.querySelector('[data-print]').onclick = function () {
      var r = read(); if (!r) return;
      if (!el._print) { BT.toast('اعرض التقرير أولاً', { type: 'error' }); return; }
      printReport(o.title, describe(form, r.x, o.months), el._print());
    };
    o.load(read().q);
  }

  /* الطباعة: كل الصفوف (لا الصفحة المعروضة فقط)، بعنوان التقرير وفلاتره ومن طبعه */
  function cell(c, r) { return c.print ? c.print(r) : c.render ? c.render(r) : (r[c.key] == null ? '—' : r[c.key]); }
  function printReport(title, meta, sections) {
    BT.print(h`<div class="print-report"><div class="pr-head"><h1>${title}</h1><div>${meta}</div><div class="muted">طُبع ${fmt.dt(new Date().toISOString())} · ${api.me ? api.me.full_name : ''}</div></div>
      ${sections.map(function (s) {
        return h`<h2>${s.title}</h2>${s.rows.length ? h`<table class="t"><thead><tr>${s.columns.map(function (c) { return h`<th class="${c.num ? 'num' : ''}">${c.label}</th>`; })}</tr></thead><tbody>${s.rows.map(function (r) { return h`<tr>${s.columns.map(function (c) { return h`<td class="${c.num ? 'num' : ''}">${cell(c, r)}</td>`; })}</tr>`; })}</tbody></table>` : h`<div class="muted">لا يوجد</div>`}`;
      })}</div>`);
  }
  function table(node, rows, columns, more) { if (node) BT.table(node, Object.assign({ rows: rows, columns: columns, pageSize: 10 }, more || {})); }
  function money(key, label) { return { key: key, label: label, num: true, sort: function (r) { return Number(r[key] || 0); }, render: function (r) { return r[key] == null ? '—' : fmt.money(r[key]); } }; }
  function km(key, label) { return { key: key, label: label, num: true, sort: function (r) { return Number(r[key] || 0); }, render: function (r) { return r[key] == null ? '—' : fmt.km(Number(r[key])); } }; }
  function driverCol(key, label) { return { key: key, label: label, sort: function (r) { return r[key] ? api.name(r[key].name) : ''; }, render: function (r) { return r[key] ? A.person(r[key]) : raw('<span class="muted">—</span>'); }, print: function (r) { return r[key] ? api.name(r[key].name) : '—'; } }; }
  function vehicleCol() { return { key: 'vehicle', label: 'السيارة', sort: function (r) { return r.vehicle ? r.vehicle.plate_number : ''; }, render: function (r) { return r.vehicle ? M.vehicle(r.vehicle) : '—'; }, print: function (r) { return r.vehicle ? r.vehicle.plate_number : '—'; } }; }

  /* ================= العمل اليومي ================= */
  function dailyPanel(el) {
    var sections = [{ v: 'drivers', t: 'حسب السائق' }, { v: 'days', t: 'حسب اليوم' }, { v: 'companies', t: 'حسب الشركة' }];
    BT.render(el, h`${api.can('reports.view') ? h`<div class="card">${rangeForm({ days: 6, filters: ['company', 'branch', 'driver'], sections: sections })}<div class="hint mb-12">التقارير المرسلة والمتأخرة (أُرسلت بعد يومها) والمرفوضة، والطلبات والكاش، حسب السائق واليوم والشركة. حتى 93 يوماً.</div><div data-sum></div></div>` : ''}
      ${api.can('cash.view') && api.can('reports.export') ? h`<div class="card mt-16"><div class="card-h"><div class="card-t">${icon('wallet', 16)} أرصدة الكاش لكل السائقين</div><div class="ms-auto flex gap-8"><button type="button" class="btn btn-sm btn-outline" data-bal="xlsx">${icon('sheet', 14)} Excel</button><button type="button" class="btn btn-sm btn-ghost" data-bal="csv">CSV</button></div></div><div class="hint">نفس أرقام صفحة الكاش، للتسليم إلى المحاسبة.</div></div>` : ''}`);
    BT.$$('[data-bal]', el).forEach(function (b) { b.onclick = function () { var ext = b.getAttribute('data-bal'); A.downloadFile('/reports/cash-balances', { format: ext }, 'cash-balances.' + ext); }; });
    if (!api.can('reports.view')) return;
    var sumEl = el.querySelector('[data-sum]');
    var cols = [
      driverCol('driver', 'السائق'),
      { key: 'days', label: 'أيام', num: true },
      { key: 'orders', label: 'الطلبات', num: true, render: function (r) { return fmt.int(r.orders); } },
      money('reported_cash', 'الكاش المُبلّغ'),
      money('approved_cash', 'المعتمد'),
      { key: 'waiting', label: 'بانتظار', num: true },
      { key: 'rejected', label: 'مرفوض', num: true },
      { key: 'late', label: 'متأخر', num: true, render: function (r) { return r.late ? h`<span class="t-warning fw-700">${fmt.int(r.late)}</span>` : '0'; }, print: function (r) { return r.late; } }
    ];
    var groupCols = function (first) {
      return [first,
        { key: 'sent', label: 'مرسلة', num: true },
        { key: 'late', label: 'متأخرة', num: true },
        { key: 'rejected', label: 'مرفوضة', num: true },
        { key: 'orders', label: 'الطلبات', num: true, render: function (r) { return fmt.int(r.orders); } },
        money('reported_cash', 'الكاش المُبلّغ'), money('approved_cash', 'المعتمد')];
    };
    var dayCols = groupCols({ key: 'day', label: 'اليوم', render: function (r) { return h`<span class="num">${fmt.date(r.day)}</span>`; }, print: function (r) { return fmt.date(r.day); } });
    var coCols = groupCols({ key: 'name', label: 'الشركة', render: function (r) { return api.name(r.name); }, print: function (r) { return api.name(r.name); } });
    wireRange(el, { path: '/reports/daily-summary', name: 'daily-summary', title: 'تقرير العمل اليومي', sections: sections, load: function (q) {
      A.load(sumEl, api.get('/reports/daily-summary', q), function (d) {
        el._print = function () { return [{ title: 'السائقون', columns: cols, rows: d.rows }, { title: 'حسب اليوم', columns: dayCols, rows: d.by_day }, { title: 'حسب الشركة', columns: coCols, rows: d.by_company }]; };
        setTimeout(function () {
          table(sumEl.querySelector('[data-t]'), d.rows, cols, {
            pageSize: 25, sort: { key: 'orders', dir: 'desc' },
            search: { placeholder: 'السائق أو الرقم الوظيفي…', text: function (r) { return api.name(r.driver.name) + ' ' + r.employee_number; } },
            empty: { icon: 'chart-column', title: 'لا توجد تقارير في هذه الفترة' }
          });
          table(sumEl.querySelector('[data-days]'), d.by_day, dayCols, { pageSize: 31, empty: { icon: 'calendar', title: 'لا توجد أيام' } });
          table(sumEl.querySelector('[data-cos]'), d.by_company, coCols, { empty: { icon: 'building-2', title: 'لا توجد تقارير' } });
        });
        var T = d.totals || {};
        return h`<div class="kpis">${BT.kpi({ label: 'الطلبات', value: fmt.int(T.orders), dot: 'o' })}${BT.kpi({ label: 'الكاش المُبلّغ', value: fmt.money(T.reported_cash), dot: 'b' })}${BT.kpi({ label: 'الكاش المعتمد', value: fmt.money(T.approved_cash), dot: 'g' })}${BT.kpi({ label: 'متأخرة / مرفوضة', value: h`${fmt.int(T.late)}<small> / ${fmt.int(T.rejected)}</small>`, sub: 'أُرسلت بعد يومها · رُفضت', dot: 'r', tone: T.late ? 'warning' : null })}</div>
          <div class="section-t mt-12">حسب السائق</div><div data-t></div>
          <div class="grid-2 mt-16"><div><div class="section-t">حسب اليوم</div><div data-days></div></div><div><div class="section-t">حسب الشركة</div><div data-cos></div></div></div>`;
      }).catch(function () {});
    } });
  }

  /* ================= الأسطول (FR-RPT-01) ================= */
  function fleetPanel(el) {
    var sections = [{ v: 'vehicles', t: 'حسب السيارة' }, { v: 'days', t: 'حسب اليوم' }];
    BT.render(el, h`<div class="card">${rangeForm({ days: 29, filters: ['company', 'branch', 'vehicle'], sections: sections })}
      <div class="hint mb-12">حالات السيارات الآن، والسيارات بلا سائق، وأيام كل سيارة في عهدة سائق خلال الفترة (أي جزء من يوم بتوقيت الكويت يُحسب يوماً)، ونسبة الاستخدام اليومي. السيارات الموقوفة لا تدخل النسبة. حتى 93 يوماً.</div><div data-out></div></div>`);
    var out = el.querySelector('[data-out]');
    var pct = function (v) { return v == null ? '—' : v + '%'; };
    var vcols = [
      vehicleCol(),
      { key: 'status', label: 'الحالة', render: function (r) { return A.pill('vehicle_status', r.status); }, print: function (r) { return api.t('vehicle_status', r.status); } },
      driverCol('driver', 'السائق الآن'),
      { key: 'days_held', label: 'أيام في العهدة', num: true },
      { key: 'use_percent', label: 'الاستخدام', num: true, sort: function (r) { return r.use_percent == null ? -1 : Number(r.use_percent); }, render: function (r) { return pct(r.use_percent); }, print: function (r) { return pct(r.use_percent); } }
    ];
    var dcols = [
      { key: 'day', label: 'اليوم', render: function (r) { return h`<span class="num">${fmt.date(r.day)}</span>`; }, print: function (r) { return fmt.date(r.day); } },
      { key: 'in_use', label: 'في العهدة', num: true },
      { key: 'vehicles', label: 'من السيارات', num: true },
      { key: 'rate', label: 'النسبة', num: true, sort: false, render: function (r) { return r.vehicles ? Math.round(r.in_use * 1000 / r.vehicles) / 10 + '%' : '—'; } }
    ];
    wireRange(el, { path: '/reports/fleet', name: 'fleet', title: 'تقرير الأسطول', sections: sections, load: function (q) {
      A.load(out, api.get('/reports/fleet', q), function (d) {
        var S = d.statuses, total = Object.keys(S).reduce(function (s, k) { return s + S[k]; }, 0);
        el._print = function () { return [{ title: 'حسب السيارة', columns: vcols, rows: d.by_vehicle }, { title: 'حسب اليوم', columns: dcols, rows: d.by_day }]; };
        setTimeout(function () {
          table(out.querySelector('[data-veh]'), d.by_vehicle, vcols, { sort: { key: 'use_percent', dir: 'asc' }, search: { placeholder: 'اللوحة…', text: function (r) { return r.vehicle.plate_number; } }, empty: { icon: 'car', title: 'لا توجد سيارات' } });
          table(out.querySelector('[data-days]'), d.by_day, dcols, { pageSize: 31, empty: { icon: 'calendar', title: 'لا توجد أيام' } });
        });
        return h`<div class="kpis" data-fleet-kpis>
            ${BT.kpi({ label: 'السيارات', value: fmt.int(total), sub: fmt.int(S.assigned) + ' في العهدة · ' + fmt.int(S.available) + ' متاحة · ' + fmt.int(S.maintenance) + ' صيانة · ' + fmt.int(S.accident) + ' حادث · ' + fmt.int(S.inactive) + ' موقوفة', dot: 'b' })}
            ${BT.kpi({ label: 'بلا سائق الآن', value: fmt.int(d.without_driver), sub: 'في الخدمة ولا عهدة لها', dot: 'o', tone: d.without_driver ? 'warning' : null })}
            ${BT.kpi({ label: 'نسبة الاستخدام اليومي', value: pct(d.use_percent), sub: 'أيام العهدة من أيام السيارات في الخدمة', dot: 'g' })}
          </div>
          <div class="section-t mt-12">حسب السيارة</div><div data-veh></div>
          <div class="section-t mt-16">حسب اليوم</div><div data-days></div>`;
      }).catch(function () {});
    } });
  }

  /* ================= الكيلومترات (FR-RPT-03) ================= */
  function kmPanel(el) {
    var sections = [{ v: 'vehicles', t: 'حسب السيارة' }, { v: 'drivers', t: 'حسب السائق' }, { v: 'pending', t: 'قراءات بانتظار المراجعة' }];
    BT.render(el, h`<div class="card">${rangeForm({ days: 6, filters: ['company', 'branch', 'driver', 'vehicle'], sections: sections })}
      <div class="hint mb-12">كل قراءتين متتاليتين للسيارة مسافة: <b>خارج العمل</b> بين نهاية يوم وبداية التالي، و<b>بلا سائق</b> بين الاستلام والتسليم التالي، و<b>في المركز</b> بعد استلام المركز. القراءات بانتظار المراجعة لا تُحسب حتى تُراجع. كيلومترات GPS خطوط مستقيمة بين نقاط الهاتف فتقل عن العداد قليلاً، وكثيراً إن انقطعت الإشارة. حتى 93 يوماً.</div><div data-out></div></div>`);
    var out = el.querySelector('[data-out]');
    var vcols = [
      vehicleCol(),
      km('km', 'المجموع'), km('on_duty', 'في العمل'), km('off_duty', 'خارج العمل'), km('unattended', 'بلا سائق'), km('center', 'في المركز'),
      km('gps', 'GPS'),
      { key: 'difference_percent', label: 'العداد عن GPS', num: true, sort: function (r) { return Number(r.difference_percent || 0); }, render: function (r) { return r.difference_percent == null ? '—' : h`<span class="${Math.abs(Number(r.difference_percent)) > 25 ? 't-danger fw-700' : ''}">${Number(r.difference_percent) > 0 ? '+' : ''}${r.difference_percent}%</span>`; }, print: function (r) { return r.difference_percent == null ? '—' : r.difference_percent + '%'; } }
    ];
    var dcols = [driverCol('driver', 'السائق'), { key: 'days', label: 'أيام عمل', num: true }, km('on_duty', 'في العمل'), km('off_duty', 'خارج العمل'), km('gps', 'GPS'), km('km_per_day', 'كم لكل يوم')];
    var pcols = [
      { key: 'recorded_at', label: 'الوقت', render: function (r) { return fmt.dt(r.recorded_at); } },
      vehicleCol(), driverCol('driver', 'السائق'),
      { key: 'kind', label: 'النوع', render: function (r) { return api.t('reading_kind', r.kind); } },
      km('value_km', 'القراءة'),
      { key: 'flags', label: 'السبب', sort: false, render: function (r) { return r.flags.map(function (f) { return api.t('odometer_flags', f); }).join('، '); } }
    ];
    wireRange(el, { path: '/reports/kilometers', name: 'kilometers', title: 'تقرير الكيلومترات', sections: sections, load: function (q) {
      A.load(out, api.get('/reports/kilometers', q), function (d) {
        var T = d.totals;
        el._print = function () { return [{ title: 'حسب السيارة', columns: vcols, rows: d.by_vehicle }, { title: 'حسب السائق', columns: dcols, rows: d.by_driver }, { title: 'قراءات بانتظار المراجعة (لم تُحسب)', columns: pcols, rows: d.pending }]; };
        setTimeout(function () {
          table(out.querySelector('[data-veh]'), d.by_vehicle, vcols, { search: { placeholder: 'اللوحة…', text: function (r) { return r.vehicle ? r.vehicle.plate_number : ''; } }, empty: { icon: 'gauge', title: 'لا توجد قراءات في هذه الفترة' } });
          table(out.querySelector('[data-drv]'), d.by_driver, dcols, { empty: { icon: 'users', title: 'لا يوجد سائقون' } });
          table(out.querySelector('[data-pend]'), d.pending, pcols, { rowClick: function () { A.go('odometer'); }, empty: { icon: 'circle-check', title: 'لا توجد قراءات بانتظار المراجعة' } });
        });
        return h`<div class="kpis">
            ${BT.kpi({ label: 'الكيلومترات', value: fmt.km(T.km), sub: 'في العمل ' + fmt.km(T.on_duty), dot: 'b' })}
            ${BT.kpi({ label: 'خارج العمل', value: fmt.km(T.off_duty), sub: 'بلا سائق ' + fmt.km(T.unattended) + ' · في المراكز ' + fmt.km(T.center), dot: 'o', tone: T.off_duty ? 'warning' : null })}
            ${BT.kpi({ label: 'مع السائقين: العداد / GPS', value: h`${fmt.km(T.with_driver)}<small> / ${fmt.km(Number(T.gps))}</small>`, dot: 'p' })}
            ${BT.kpi({ label: 'قراءات بانتظار المراجعة', value: fmt.int(d.pending_count), sub: 'لا تُحسب حتى تُراجع', dot: 'r', tone: d.pending_count ? 'warning' : null })}
          </div>
          <div class="section-t mt-12">حسب السيارة</div><div data-veh></div>
          <div class="grid-2 mt-16"><div><div class="section-t">حسب السائق</div><div data-drv></div></div><div><div class="section-t">قراءات بانتظار المراجعة</div><div data-pend></div></div></div>`;
      }).catch(function () {});
    } });
  }

  /* ================= الكاش والخزينة (FR-RPT-04) ================= */
  function cashPanel(el) {
    var treasury = api.can('treasury.view');
    var sections = [{ v: 'aging', t: 'الأرصدة وأعمارها' }, { v: 'collectors', t: 'التحصيل حسب المستلم' }].concat(treasury ? [{ v: 'treasury', t: 'الخزينة' }, { v: 'deposits', t: 'الإيداعات البنكية' }] : []);
    BT.render(el, h`<div class="card">${rangeForm({ days: 29, filters: ['company', 'branch', 'driver'], sections: sections })}
      <div class="hint mb-12">الأعمار لليوم أياً كانت الفترة: ما يسلّمه السائق يسدد أقدم كاش معه أولاً، فالباقي معه هو الأحدث. غير المعتمد لا يُعمَّر. التحصيل والخزينة والإيداعات للفترة؛ والخزينة لكل فرع ومشتركة بين شركاته فلا يطبق عليها فلتر الشركة.</div><div data-out></div></div>`);
    var out = el.querySelector('[data-out]');
    var acols = [
      driverCol('driver', 'السائق'), money('posted', 'معه (معتمد)'), money('pending', 'غير معتمد'),
      money('d0_1', 'حتى يوم'), money('d2_3', '2–3 أيام'), money('d4_7', '4–7 أيام'),
      { key: 'd8_plus', label: 'أكثر من 7 أيام', num: true, sort: function (r) { return Number(r.d8_plus); }, render: function (r) { return Number(r.d8_plus) ? h`<b class="t-danger">${fmt.money(r.d8_plus)}</b>` : fmt.money(r.d8_plus); }, print: function (r) { return fmt.money(r.d8_plus); } },
      { key: 'oldest_days', label: 'أقدم كاش', num: true, render: function (r) { return r.oldest_days == null ? '—' : r.oldest_days + ' يوم'; } }
    ];
    var ccols = [{ key: 'user', label: 'المستلم' }, { key: 'receipts', label: 'إيصالات', num: true }, money('amount', 'المبلغ'), { key: 'confirmed', label: 'أكدها السائق', num: true }, { key: 'reversed', label: 'معكوسة', num: true }];
    var tcols = [{ key: 'branch', label: 'الفرع', render: function (r) { return r.branch ? api.name(r.branch.name) : '—'; } }, money('opening', 'أول المدة'), money('received', 'دخل'), money('paid_out', 'خرج'), money('closing', 'آخر المدة')];
    var dcols = [{ key: 'business_date', label: 'التاريخ', render: function (r) { return fmt.date(r.business_date); } }, { key: 'branch', label: 'الفرع', render: function (r) { return r.branch ? api.name(r.branch.name) : '—'; } }, money('amount', 'المبلغ'), { key: 'reference', label: 'المرجع' }, { key: 'by', label: 'بواسطة' }, { key: 'reversed', label: '', sort: false, render: function (r) { return r.reversed ? BT.pill('معكوس', 'n') : ''; } }];
    wireRange(el, { path: '/reports/cash', name: 'cash', title: 'تقرير الكاش والخزينة', sections: sections, load: function (q) {
      A.load(out, api.get('/reports/cash', q), function (d) {
        var T = d.aging.totals, collected = d.collectors.reduce(function (s, r) { return s + Number(r.amount); }, 0);
        el._print = function () {
          return [{ title: 'أرصدة السائقين وأعمارها (اليوم)', columns: acols, rows: d.aging.rows }, { title: 'التحصيل حسب المستلم', columns: ccols, rows: d.collectors }]
            .concat(d.treasury ? [{ title: 'الخزينة', columns: tcols, rows: d.treasury }, { title: 'الإيداعات البنكية', columns: dcols, rows: d.deposits }] : []);
        };
        setTimeout(function () {
          table(out.querySelector('[data-aging]'), d.aging.rows, acols, { pageSize: 25, search: { placeholder: 'السائق…', text: function (r) { return r.driver ? api.name(r.driver.name) : ''; } }, empty: { icon: 'wallet', title: 'لا يحمل أحد كاشاً' } });
          table(out.querySelector('[data-coll]'), d.collectors, ccols, { pageSize: 0, empty: { icon: 'receipt', title: 'لا توجد إيصالات في هذه الفترة' } });
          if (d.treasury) {
            table(out.querySelector('[data-tr]'), d.treasury, tcols, { pageSize: 0, empty: { icon: 'landmark', title: 'لا حركة' } });
            table(out.querySelector('[data-dep]'), d.deposits, dcols, { empty: { icon: 'landmark', title: 'لا توجد إيداعات في هذه الفترة' } });
          }
        });
        return h`<div class="kpis">
            ${BT.kpi({ label: 'كاش مع السائقين (معتمد)', value: fmt.money(T.posted), sub: 'غير معتمد ' + fmt.money(T.pending), dot: 'b' })}
            ${BT.kpi({ label: 'معهم أكثر من 7 أيام', value: fmt.money(T.d8_plus), dot: 'r', tone: Number(T.d8_plus) ? 'danger' : null })}
            ${BT.kpi({ label: '4–7 أيام', value: fmt.money(T.d4_7), dot: 'o' })}
            ${BT.kpi({ label: 'حُصّل بإيصالات في الفترة', value: fmt.money(collected), dot: 'g' })}
          </div>
          <div class="section-t mt-12">أرصدة السائقين وأعمارها (اليوم ${fmt.date(d.as_of)})</div><div data-aging></div>
          <div class="grid-2 mt-16"><div><div class="section-t">التحصيل حسب المستلم</div><div data-coll></div></div>${d.treasury ? h`<div><div class="section-t">الخزينة</div><div data-tr></div></div>` : ''}</div>
          ${d.treasury ? h`<div class="section-t mt-16">الإيداعات البنكية</div><div data-dep></div>` : ''}`;
      }).catch(function () {});
    } });
  }

  /* ================= الصيانة ================= */
  function maintenancePanel(el) {
    var sections = [{ v: 'centers', t: 'حسب المركز' }, { v: 'vehicles', t: 'حسب السيارة' }, { v: 'parts', t: 'القطع' }];
    BT.render(el, h`<div class="card">${rangeForm({ days: 89, filters: ['company', 'branch', 'vehicle'], sections: sections })}<div class="hint mb-12">مدة البقاء: السيارات المستلمة في الفترة (والباقية في المركز تُحسب حتى الآن). التكلفة: الفواتير المعتمدة بتاريخها في الفترة. حتى سنة.</div><div data-out></div></div>`);
    var out = el.querySelector('[data-out]');
    var ccols = [
      { key: 'center', label: 'المركز', sort: function (r) { return r.center.name; }, render: function (r) { return r.center.name; } },
      { key: 'received', label: 'استلم', num: true, render: function (r) { return h`${fmt.int(r.received)}${r.still_there ? h`<span class="sub">${r.still_there} ما زالت فيه</span>` : ''}`; } },
      { key: 'avg_stay_seconds', label: 'متوسط البقاء', num: true, render: function (r) { return M.dur(r.avg_stay_seconds); } },
      { key: 'max_stay_seconds', label: 'الأطول', num: true, render: function (r) { return M.dur(r.max_stay_seconds); } },
      { key: 'invoices', label: 'فواتير', num: true },
      money('cost', 'التكلفة'), money('avg_cost', 'متوسط الفاتورة')
    ];
    var vcols = [vehicleCol(), { key: 'times_received', label: 'مرات الدخول', num: true }, { key: 'stay_seconds', label: 'أيام التوقف', num: true, render: function (r) { return M.dur(r.stay_seconds); } }, { key: 'invoices', label: 'فواتير', num: true }, money('cost', 'التكلفة')];
    var pcols = [
      { key: 'description', label: 'القطعة', render: function (r) { return h`<span style="white-space:normal">${r.description}</span>`; } },
      { key: 'quantity', label: 'الكمية', num: true, sort: function (r) { return Number(r.quantity); }, render: function (r) { return String(Number(r.quantity)); } },
      { key: 'invoices', label: 'فواتير', num: true }, money('amount', 'المبلغ')
    ];
    wireRange(el, { path: '/reports/maintenance', name: 'maintenance', title: 'تقرير الصيانة', sections: sections, load: function (q) {
      A.load(out, api.get('/reports/maintenance', q), function (d) {
        var T = d.totals;
        el._print = function () { return [{ title: 'حسب المركز', columns: ccols, rows: d.by_center }, { title: 'حسب السيارة', columns: vcols, rows: d.by_vehicle }, { title: 'القطع', columns: pcols, rows: d.parts }]; };
        setTimeout(function () {
          table(out.querySelector('[data-centers]'), d.by_center, ccols, { pageSize: 0, sort: { key: 'cost', dir: 'desc' }, empty: { icon: 'wrench', title: 'لا توجد صيانة في هذه الفترة' } });
          table(out.querySelector('[data-vehicles]'), d.by_vehicle, vcols, { search: { placeholder: 'اللوحة…', text: function (r) { return r.vehicle.plate_number + ' ' + (r.vehicle.make || ''); } }, empty: { icon: 'car', title: 'لا توجد سيارات' } });
          table(out.querySelector('[data-parts]'), d.parts, pcols, { search: { placeholder: 'القطعة…', text: function (r) { return r.description; } }, empty: { icon: 'wrench', title: 'لا توجد قطع في فواتير معتمدة' } });
        });
        return h`<div class="kpis">
            ${BT.kpi({ label: 'سيارات استلمتها المراكز', value: fmt.int(T.received), sub: T.still_there ? fmt.int(T.still_there) + ' ما زالت في المراكز' : '', dot: 'b' })}
            ${BT.kpi({ label: 'متوسط البقاء', value: M.dur(T.avg_stay_seconds), dot: 'p' })}
            ${BT.kpi({ label: 'التكلفة المعتمدة', value: fmt.money(T.cost), sub: fmt.int(T.invoices) + ' فاتورة', dot: 'o' })}
            ${BT.kpi({ label: 'قطع / أجور', value: h`${fmt.money(T.parts)}<small> / ${fmt.money(T.labour)}</small>`, dot: 'g' })}
          </div>
          <div class="section-t mt-12">حسب المركز</div><div data-centers></div>
          <div class="grid-2 mt-16"><div><div class="section-t">حسب السيارة (الأعلى تكلفة أولاً)</div><div data-vehicles></div></div><div><div class="section-t">القطع</div><div data-parts></div></div></div>`;
      }).catch(function () {});
    } });
  }

  /* ================= الحوادث ================= */
  function accidentsPanel(el) {
    BT.render(el, h`<div class="card">${rangeForm({ days: 89, filters: ['company', 'branch', 'driver', 'vehicle'] })}<div class="hint mb-12">الحوادث الواقعة في الفترة (عدا الملغاة)؛ وقائمة «بانتظار محضر الشرطة» تشمل كل المفتوحة أياً كان تاريخها. حتى سنة.</div><div data-out></div></div>`);
    var out = el.querySelector('[data-out]');
    var acols = [
      { key: 'number', label: 'الحادث', render: function (r) { return h`<span class="num">#${r.number}</span><span class="sub">${fmt.dt(r.occurred_at)}</span>`; }, print: function (r) { return '#' + r.number + ' · ' + fmt.dt(r.occurred_at); } },
      { key: 'vehicle', label: 'السيارة', sort: false, render: function (r) { return r.vehicle ? BT.plate(r.vehicle.plate_number) : '—'; }, print: function (r) { return r.vehicle ? r.vehicle.plate_number : '—'; } },
      { key: 'driver', label: 'السائق', sort: false, render: function (r) { return r.driver ? A.person(r.driver) : raw('<span class="muted">بلا سائق</span>'); }, print: function (r) { return r.driver ? api.name(r.driver.name) : 'بلا سائق'; } },
      { key: 'liability', label: 'المسؤولية', render: function (r) { return h`${C.liability(r)}${r.has_police_report ? '' : h` ${BT.pill('بلا محضر', 'o')}`}`; } },
      money('estimate', 'التقدير'), money('actual_cost', 'الفعلية'),
      { key: 'difference', label: 'الفرق', num: true, sort: function (r) { return Number(r.difference || 0); }, render: function (r) { return r.difference != null ? h`<b class="${Number(r.difference) > 0 ? 't-danger' : ''}">${fmt.signed(Number(r.difference))}</b>` : '—'; } },
      money('deduction', 'الخصم')
    ];
    var wcols = [acols[0], acols[1], acols[2], { key: 'days', label: 'منذ', num: true, render: function (r) { return r.days + ' يوم'; } }];
    function groupCols(key, label) {
      return [
        { key: key, label: label, sort: false, render: function (r) { return r[key] ? (key === 'driver' ? A.person(r.driver) : M.vehicle(r.vehicle)) : raw('<span class="muted">' + (key === 'driver' ? 'بلا سائق' : '—') + '</span>'); }, print: function (r) { return r[key] ? (key === 'driver' ? api.name(r.driver.name) : r.vehicle.plate_number) : '—'; } },
        { key: 'accidents', label: 'حوادث', num: true }, { key: 'liable', label: 'مسؤولية السائق', num: true },
        money('estimate', 'التقدير المعتمد'), key === 'driver' ? money('deduction', 'الخصومات') : money('actual_cost', 'التكلفة الفعلية')
      ];
    }
    wireRange(el, { path: '/reports/accidents', name: 'accidents', title: 'تقرير الحوادث', load: function (q) {
      A.load(out, api.get('/reports/accidents', q), function (d) {
        var T = d.totals, O = d.by_outcome;
        el._print = function () { return [{ title: 'الحوادث', columns: acols, rows: d.accidents }, { title: 'حسب السائق', columns: groupCols('driver', 'السائق'), rows: d.by_driver }, { title: 'حسب السيارة', columns: groupCols('vehicle', 'السيارة'), rows: d.by_vehicle }, { title: 'بانتظار محضر الشرطة', columns: wcols, rows: d.waiting_police_report }]; };
        setTimeout(function () {
          table(out.querySelector('[data-acc]'), d.accidents, acols, { rowClick: function (r) { A.go('accidents/' + r.id); }, empty: { icon: 'shield-check', title: 'لا توجد حوادث في هذه الفترة' } });
          table(out.querySelector('[data-drv]'), d.by_driver, groupCols('driver', 'السائق'), { empty: { icon: 'shield-check', title: 'لا توجد حوادث' } });
          table(out.querySelector('[data-veh]'), d.by_vehicle, groupCols('vehicle', 'السيارة'), { empty: { icon: 'shield-check', title: 'لا توجد حوادث' } });
          table(out.querySelector('[data-wait]'), d.waiting_police_report, wcols, { rowClick: function (r) { A.go('accidents/' + r.id); }, empty: { icon: 'circle-check', title: 'كل الحوادث المفتوحة لها محضر' } });
        });
        return h`<div class="kpis">
            ${BT.kpi({ label: 'حوادث', value: fmt.int(T.accidents), sub: T.injuries ? fmt.int(T.injuries) + ' بإصابات' : '', dot: 'r' })}
            ${BT.kpi({ label: 'التقدير المعتمد', value: fmt.money(T.estimate), sub: 'الفعلية ' + fmt.money(T.actual_cost), dot: 'o' })}
            ${BT.kpi({ label: 'الخصومات القائمة', value: fmt.money(T.deduction), dot: 'p' })}
            ${BT.kpi({ label: 'بانتظار محضر الشرطة', value: fmt.int(T.waiting_police_report), sub: 'كل المفتوحة', dot: 'o', tone: T.waiting_police_report ? 'warning' : null })}
          </div>
          <div class="flex gap-8 wrap mb-12">${BT.pill('بانتظار القرار ' + O.pending, 'o')}${BT.pill('لا مسؤولية ' + O.none, 'g')}${BT.pill('السائق مسؤول ' + O.driver, 'r')}${BT.pill('مشتركة ' + O.shared, 'o')}</div>
          <div class="section-t">الحوادث</div><div data-acc></div>
          <div class="grid-2 mt-16"><div><div class="section-t">حسب السائق</div><div data-drv></div></div><div><div class="section-t">حسب السيارة</div><div data-veh></div></div></div>
          <div class="section-t mt-16">بانتظار محضر الشرطة</div><div data-wait></div>`;
      }).catch(function () {});
    } });
  }

  /* ================= الرواتب (FR-RPT-07) ================= */
  function payrollPanel(el) {
    var sections = [{ v: 'runs', t: 'حسب الشهر والشركة' }, { v: 'carried', t: 'المبالغ المرحّلة' }];
    BT.render(el, h`<div class="card">${rangeForm({ months: 6, filters: ['company', 'branch', 'employee'], sections: sections })}
      <div class="hint mb-12">كشف كل شركة في كل شهر (المسودة قابلة للتغيير). ما لم يُخصم من قسط بسبب الحد الشهري يُرحَّل ويُستحق في الشهر التالي، فيُقرأ شهراً بشهر ولا يُجمع عبر الأشهر. حتى 24 شهراً.</div><div data-out></div></div>`);
    var out = el.querySelector('[data-out]');
    function monthLabel(s) { var p = s.split('-'); return fmt.month(+p[0], +p[1]); }
    function sources(r) { return Object.keys(r.by_source).map(function (s) { var x = r.by_source[s]; return api.t('deduction_source', s) + ' ' + fmt.money(x.deducted) + (Number(x.carried) ? ' (رُحّل ' + fmt.money(x.carried) + ')' : ''); }).join(' · '); }
    var rcols = [
      { key: 'month', label: 'الشهر', render: function (r) { return monthLabel(r.month); } },
      { key: 'company', label: 'الشركة', sort: false, render: function (r) { return r.company.name ? api.name(r.company.name) : '—'; } },
      { key: 'status', label: 'الحالة', render: function (r) { return BT.pill(api.t('run_status', r.status), r.status === 'draft' ? 'o' : 'g'); }, print: function (r) { return api.t('run_status', r.status); } },
      { key: 'lines', label: 'الموظفون', num: true },
      money('gross', 'المستحق'), money('deductions', 'الخصومات'), money('net', 'الصافي'),
      { key: 'installments_deducted', label: 'أقساط مخصومة', num: true, sort: function (r) { return Number(r.installments_deducted); }, render: function (r) { return h`${fmt.money(r.installments_deducted)}${Object.keys(r.by_source).length ? h`<span class="sub">${sources(r)}</span>` : ''}`; }, print: function (r) { return fmt.money(r.installments_deducted) + (Object.keys(r.by_source).length ? ' — ' + sources(r) : ''); } },
      { key: 'carried', label: 'مُرحّل', num: true, sort: function (r) { return Number(r.carried); }, render: function (r) { return Number(r.carried) ? h`<b class="t-warning">${fmt.money(r.carried)}</b>` : fmt.money(r.carried); }, print: function (r) { return fmt.money(r.carried); } }
    ];
    var ccols = [
      { key: 'month', label: 'الشهر', render: function (r) { return monthLabel(r.month); } },
      driverCol('employee', 'الموظف'),
      { key: 'source_type', label: 'المصدر', render: function (r) { return api.t('deduction_source', r.source_type); } },
      { key: 'reason', label: 'السبب', render: function (r) { return h`<span style="white-space:normal">${r.reason}</span>`; } },
      money('due', 'المستحق'), money('deducted', 'المخصوم'), money('carried', 'مُرحّل')
    ];
    wireRange(el, { path: '/reports/payroll', name: 'payroll', title: 'تقرير الرواتب', months: true, sections: sections, load: function (q) {
      A.load(out, api.get('/reports/payroll', q), function (d) {
        var T = d.totals, last = d.runs.length ? d.runs[d.runs.length - 1].month : null;
        var carriedLast = d.runs.filter(function (r) { return r.month === last; }).reduce(function (s, r) { return s + Number(r.carried); }, 0);
        el._print = function () { return [{ title: 'حسب الشهر والشركة', columns: rcols, rows: d.runs }, { title: 'المبالغ المرحّلة', columns: ccols, rows: d.carried }]; };
        setTimeout(function () {
          table(out.querySelector('[data-runs]'), d.runs, rcols, { pageSize: 25, rowClick: function (r) { A.go('payroll/run/' + r.id); }, empty: { icon: 'banknote', title: 'لا توجد كشوف رواتب في هذه الأشهر' } });
          table(out.querySelector('[data-carried]'), d.carried, ccols, { search: { placeholder: 'الموظف…', text: function (r) { return r.employee ? api.name(r.employee.name) : ''; } }, empty: { icon: 'circle-check', title: 'لم يُرحّل شيء' } });
        });
        return h`<div class="kpis">
            ${BT.kpi({ label: 'المستحق', value: fmt.money(T.gross), sub: fmt.int(T.lines) + ' سطر', dot: 'b' })}
            ${BT.kpi({ label: 'الخصومات', value: fmt.money(T.deductions), sub: 'منها أقساط ' + fmt.money(T.installments_deducted), dot: 'o' })}
            ${BT.kpi({ label: 'الصافي', value: fmt.money(T.net), dot: 'g' })}
            ${BT.kpi({ label: 'مُرحّل من آخر شهر', value: fmt.money(carriedLast), sub: last ? monthLabel(last) : '', dot: 'r', tone: carriedLast ? 'warning' : null })}
          </div>
          <div class="section-t mt-12">حسب الشهر والشركة</div><div data-runs></div>
          <div class="section-t mt-16">المبالغ المرحّلة</div><div data-carried></div>`;
      }).catch(function () {});
    } });
  }
})();
