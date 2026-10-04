/* =====================================================================
   app/pages/reports.js — التقارير: العمل اليومي وأرصدة الكاش، الصيانة (مدة
   البقاء والتكلفة حسب المركز والسيارة، والقطع)، والحوادث (حسب السائق والسيارة
   والنتيجة، المحضر، التقدير مقابل التكلفة الفعلية، الخصومات). تصدير CSV.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A, M = BT.mnt, C = BT.acc;

  BT.pages['reports'] = function (p, q) {
    A.setTitle('التقارير');
    var v = A.view(), tabs = [];
    if (api.can('reports.view') || api.can('cash.view')) tabs.push(['daily', 'العمل اليومي والكاش']);
    if (api.can('reports.view') && api.can('maintenance.view')) tabs.push(['maintenance', 'الصيانة']);
    if (api.can('reports.view') && api.can('accidents.view')) tabs.push(['accidents', 'الحوادث']);
    if (!tabs.length) { BT.render(v, A.forbidden()); return; }
    var tab = tabs.some(function (t) { return t[0] === q.tab; }) ? q.tab : tabs[0][0];
    BT.render(v, h`${A.head('التقارير', 'فلتر بالفترة، وتصدير CSV يفتح في Excel بالعربية', '')}
      ${tabs.length > 1 ? BT.tabs('rep', tabs, tab, 'tabs-line') : ''}
      ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="rep" class="${t[0] === tab ? 'active' : ''}"><div data-p="${t[0]}"></div></div>`; })}`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      ({ daily: dailyPanel, maintenance: maintenancePanel, accidents: accidentsPanel })[t](v.querySelector('[data-p="' + t + '"]'));
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/reports?tab=' + e.detail); });
    show(tab);
  };

  /* فورم الفترة: من/إلى + عرض + CSV */
  function rangeForm(days, csvLabel, extra) {
    var to = BT.config.today, from = BT.date.add(to, -days);
    return h`<form class="toolbar" data-range style="margin:0 0 12px">${BT.f.date({ name: 'from', label: 'من', value: from, required: true })}${BT.f.date({ name: 'to', label: 'إلى', value: to, required: true })}${extra || ''}<button type="submit" class="btn btn-primary" style="align-self:flex-end">${icon('chart-column', 15)} عرض</button>${api.can('reports.export') ? h`<button type="button" class="btn btn-outline" data-csv style="align-self:flex-end">${icon('download', 15)} ${csvLabel || 'CSV'}</button>` : ''}</form>`;
  }
  function wireRange(el, load, csv) {
    var form = el.querySelector('[data-range]');
    form.addEventListener('submit', function (e) { e.preventDefault(); var x = BT.form.values(form); load(x.from, x.to, x); });
    var b = el.querySelector('[data-csv]');
    if (b) b.onclick = function () { var x = BT.form.values(form); csv(x.from, x.to, x).catch(api.fail); };
    var x = BT.form.values(form);
    load(x.from, x.to, x);
  }

  /* ================= العمل اليومي والكاش ================= */
  function dailyPanel(el) {
    BT.render(el, h`${api.can('reports.view') ? h`<div class="card">${rangeForm(6)}<div class="hint mb-12">ملخص السائقين خلال فترة حتى 93 يوماً.</div><div data-sum></div></div>` : ''}
      ${api.can('cash.view') && api.can('reports.export') ? h`<div class="card mt-16"><div class="card-h"><div class="card-t">${icon('wallet', 16)} أرصدة الكاش لكل السائقين</div><button type="button" class="btn btn-sm btn-outline ms-auto" data-bal-csv>${icon('download', 14)} CSV</button></div><div class="hint">نفس أرقام صفحة الكاش، للتسليم إلى المحاسبة.</div></div>` : ''}`);
    var bc = el.querySelector('[data-bal-csv]');
    if (bc) bc.onclick = function () { A.downloadFile('/reports/cash-balances', { format: 'csv' }, 'cash-balances.csv').catch(api.fail); };
    if (!api.can('reports.view')) return;
    var sumEl = el.querySelector('[data-sum]');
    wireRange(el, function (f, t2) {
      A.load(sumEl, api.get('/reports/daily-summary', { date_from: f, date_to: t2 }), function (d) {
        setTimeout(function () {
          var t = sumEl.querySelector('[data-t]');
          if (t) BT.table(t, {
            rows: d.rows, pageSize: 25, sort: { key: 'orders', dir: 'desc' },
            search: { placeholder: 'السائق أو الرقم الوظيفي…', text: function (r) { return api.name(r.driver.name) + ' ' + r.employee_number; } },
            columns: [
              { key: 'driver', label: 'السائق', sort: function (r) { return api.name(r.driver.name); }, render: function (r) { return A.person(r.driver, r.employee_number); } },
              { key: 'days', label: 'أيام', num: true },
              { key: 'orders', label: 'الطلبات', num: true, render: function (r) { return fmt.int(r.orders); } },
              { key: 'reported_cash', label: 'الكاش المُبلّغ', num: true, sort: function (r) { return Number(r.reported_cash); }, render: function (r) { return fmt.money(r.reported_cash); } },
              { key: 'approved_cash', label: 'المعتمد', num: true, sort: function (r) { return Number(r.approved_cash); }, render: function (r) { return fmt.money(r.approved_cash); } },
              { key: 'waiting', label: 'بانتظار', num: true },
              { key: 'rejected', label: 'مرفوض', num: true }
            ],
            empty: { icon: 'chart-column', title: 'لا توجد تقارير في هذه الفترة' }
          });
        });
        var T = d.totals || {};
        return h`<div class="kpis">${BT.kpi({ label: 'الطلبات', value: fmt.int(T.orders), dot: 'o' })}${BT.kpi({ label: 'الكاش المُبلّغ', value: fmt.money(T.reported_cash), dot: 'b' })}${BT.kpi({ label: 'الكاش المعتمد', value: fmt.money(T.approved_cash), dot: 'g' })}${BT.kpi({ label: 'سائقون', value: fmt.int(d.rows.length), dot: 'p' })}</div><div data-t></div>`;
      }).catch(function () {});
    }, function (f, t2) {
      return A.downloadFile('/reports/daily-summary', { date_from: f, date_to: t2, format: 'csv' }, 'daily-summary-' + f + '-' + t2 + '.csv');
    });
  }

  /* ================= الصيانة ================= */
  function maintenancePanel(el) {
    var section = BT.f.select({ name: 'section', label: 'ملف CSV', value: 'centers', placeholder: false, options: [{ v: 'centers', t: 'حسب المركز' }, { v: 'vehicles', t: 'حسب السيارة' }, { v: 'parts', t: 'القطع' }] });
    BT.render(el, h`<div class="card">${rangeForm(89, 'CSV', section)}<div class="hint mb-12">مدة البقاء: السيارات المستلمة في الفترة (والباقية في المركز تُحسب حتى الآن). التكلفة: الفواتير المعتمدة بتاريخها في الفترة. حتى سنة.</div><div data-out></div></div>`);
    var out = el.querySelector('[data-out]');
    wireRange(el, function (f, t2) {
      A.load(out, api.get('/reports/maintenance', { date_from: f, date_to: t2 }), function (d) {
        var T = d.totals;
        setTimeout(function () {
          var c = out.querySelector('[data-centers]'), vv = out.querySelector('[data-vehicles]'), pp = out.querySelector('[data-parts]');
          if (c) BT.table(c, {
            rows: d.by_center, pageSize: 0, sort: { key: 'cost', dir: 'desc' },
            columns: [
              { key: 'center', label: 'المركز', sort: function (r) { return r.center.name; }, render: function (r) { return r.center.name; } },
              { key: 'received', label: 'استلم', num: true, render: function (r) { return h`${fmt.int(r.received)}${r.still_there ? h`<span class="sub">${r.still_there} ما زالت فيه</span>` : ''}`; } },
              { key: 'avg_stay_seconds', label: 'متوسط البقاء', num: true, render: function (r) { return M.dur(r.avg_stay_seconds); } },
              { key: 'max_stay_seconds', label: 'الأطول', num: true, render: function (r) { return M.dur(r.max_stay_seconds); } },
              { key: 'invoices', label: 'فواتير', num: true },
              { key: 'cost', label: 'التكلفة', num: true, sort: function (r) { return Number(r.cost); }, render: function (r) { return BT.amt(Number(r.cost)); } },
              { key: 'avg_cost', label: 'متوسط الفاتورة', num: true, sort: function (r) { return Number(r.avg_cost || 0); }, render: function (r) { return r.avg_cost != null ? fmt.money(r.avg_cost) : '—'; } }
            ],
            empty: { icon: 'wrench', title: 'لا توجد صيانة في هذه الفترة' }
          });
          if (vv) BT.table(vv, {
            rows: d.by_vehicle, pageSize: 10,
            search: { placeholder: 'اللوحة…', text: function (r) { return r.vehicle.plate_number + ' ' + (r.vehicle.make || ''); } },
            columns: [
              { key: 'vehicle', label: 'السيارة', sort: function (r) { return r.vehicle.plate_number; }, render: function (r) { return M.vehicle(r.vehicle); } },
              { key: 'times_received', label: 'مرات الدخول', num: true },
              { key: 'stay_seconds', label: 'أيام التوقف', num: true, render: function (r) { return M.dur(r.stay_seconds); } },
              { key: 'invoices', label: 'فواتير', num: true },
              { key: 'cost', label: 'التكلفة', num: true, sort: function (r) { return Number(r.cost); }, render: function (r) { return BT.amt(Number(r.cost)); } }
            ],
            empty: { icon: 'car', title: 'لا توجد سيارات' }
          });
          if (pp) BT.table(pp, {
            rows: d.parts, pageSize: 10,
            search: { placeholder: 'القطعة…', text: function (r) { return r.description; } },
            columns: [
              { key: 'description', label: 'القطعة', render: function (r) { return h`<span style="white-space:normal">${r.description}</span>`; } },
              { key: 'quantity', label: 'الكمية', num: true, sort: function (r) { return Number(r.quantity); }, render: function (r) { return String(Number(r.quantity)); } },
              { key: 'invoices', label: 'فواتير', num: true },
              { key: 'amount', label: 'المبلغ', num: true, sort: function (r) { return Number(r.amount); }, render: function (r) { return BT.amt(Number(r.amount)); } }
            ],
            empty: { icon: 'wrench', title: 'لا توجد قطع في فواتير معتمدة' }
          });
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
    }, function (f, t2, x) {
      return A.downloadFile('/reports/maintenance', { date_from: f, date_to: t2, format: 'csv', section: x.section }, 'maintenance-' + x.section + '-' + f + '-' + t2 + '.csv');
    });
  }

  /* ================= الحوادث ================= */
  function accidentsPanel(el) {
    BT.render(el, h`<div class="card">${rangeForm(89)}<div class="hint mb-12">الحوادث الواقعة في الفترة (عدا الملغاة)؛ وقائمة «بانتظار محضر الشرطة» تشمل كل المفتوحة أياً كان تاريخها. حتى سنة.</div><div data-out></div></div>`);
    var out = el.querySelector('[data-out]');
    wireRange(el, function (f, t2) {
      A.load(out, api.get('/reports/accidents', { date_from: f, date_to: t2 }), function (d) {
        var T = d.totals, O = d.by_outcome;
        function groupTable(node, key, label) {
          BT.table(node, {
            rows: d['by_' + key], pageSize: 10,
            columns: [
              { key: key, label: label, sort: false, render: function (r) { return r[key] ? (key === 'driver' ? A.person(r.driver) : M.vehicle(r.vehicle)) : raw('<span class="muted">' + (key === 'driver' ? 'بلا سائق' : '—') + '</span>'); } },
              { key: 'accidents', label: 'حوادث', num: true },
              { key: 'liable', label: 'مسؤولية السائق', num: true },
              { key: 'estimate', label: 'التقدير المعتمد', num: true, sort: function (r) { return Number(r.estimate); }, render: function (r) { return fmt.money(r.estimate); } },
              { key: key === 'driver' ? 'deduction' : 'actual_cost', label: key === 'driver' ? 'الخصومات' : 'التكلفة الفعلية', num: true, sort: function (r) { return Number(r[key === 'driver' ? 'deduction' : 'actual_cost']); }, render: function (r) { return fmt.money(r[key === 'driver' ? 'deduction' : 'actual_cost']); } }
            ],
            empty: { icon: 'shield-check', title: 'لا توجد حوادث' }
          });
        }
        setTimeout(function () {
          var a = out.querySelector('[data-acc]'), dr = out.querySelector('[data-drv]'), ve = out.querySelector('[data-veh]'), w = out.querySelector('[data-wait]');
          if (a) BT.table(a, {
            rows: d.accidents, pageSize: 10,
            columns: [
              { key: 'number', label: 'الحادث', render: function (r) { return h`<span class="num">#${r.number}</span><span class="sub">${fmt.dt(r.occurred_at)}</span>`; } },
              { key: 'vehicle', label: 'السيارة', sort: false, render: function (r) { return r.vehicle ? BT.plate(r.vehicle.plate_number) : '—'; } },
              { key: 'driver', label: 'السائق', sort: false, render: function (r) { return r.driver ? A.person(r.driver) : raw('<span class="muted">بلا سائق</span>'); } },
              { key: 'liability', label: 'المسؤولية', render: function (r) { return h`${C.liability(r)}${r.has_police_report ? '' : h` ${BT.pill('بلا محضر', 'o')}`}`; } },
              { key: 'estimate', label: 'التقدير', num: true, sort: function (r) { return Number(r.estimate || 0); }, render: function (r) { return r.estimate != null ? fmt.money(r.estimate) : '—'; } },
              { key: 'actual_cost', label: 'الفعلية', num: true, sort: function (r) { return Number(r.actual_cost || 0); }, render: function (r) { return r.actual_cost != null ? fmt.money(r.actual_cost) : '—'; } },
              { key: 'difference', label: 'الفرق', num: true, sort: function (r) { return Number(r.difference || 0); }, render: function (r) { return r.difference != null ? h`<b class="${Number(r.difference) > 0 ? 't-danger' : ''}">${fmt.signed(Number(r.difference))}</b>` : '—'; } },
              { key: 'deduction', label: 'الخصم', num: true, sort: function (r) { return Number(r.deduction || 0); }, render: function (r) { return r.deduction != null ? fmt.money(r.deduction) : '—'; } }
            ],
            rowClick: function (r) { A.go('accidents/' + r.id); },
            empty: { icon: 'shield-check', title: 'لا توجد حوادث في هذه الفترة' }
          });
          if (dr) groupTable(dr, 'driver', 'السائق');
          if (ve) groupTable(ve, 'vehicle', 'السيارة');
          if (w) BT.table(w, {
            rows: d.waiting_police_report, pageSize: 10,
            columns: [
              { key: 'number', label: 'الحادث', render: function (r) { return h`<span class="num">#${r.number}</span><span class="sub">${fmt.dt(r.occurred_at)}</span>`; } },
              { key: 'vehicle', label: 'السيارة', sort: false, render: function (r) { return r.vehicle ? BT.plate(r.vehicle.plate_number) : '—'; } },
              { key: 'driver', label: 'السائق', sort: false, render: function (r) { return r.driver ? A.person(r.driver) : raw('<span class="muted">بلا سائق</span>'); } },
              { key: 'days', label: 'منذ', num: true, render: function (r) { return r.days + ' يوم'; } }
            ],
            rowClick: function (r) { A.go('accidents/' + r.id); },
            empty: { icon: 'circle-check', title: 'كل الحوادث المفتوحة لها محضر' }
          });
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
    }, function (f, t2) {
      return A.downloadFile('/reports/accidents', { date_from: f, date_to: t2, format: 'csv' }, 'accidents-' + f + '-' + t2 + '.csv');
    });
  }
})();
