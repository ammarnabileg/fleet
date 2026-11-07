/* =====================================================================
   app/pages/report-center.js — مركز التقارير: كل التقارير في مكان واحد،
   مجمّعة (الأسطول والتشغيل، الكاش، الرواتب، الصيانة والحوادث، الموظفون
   والإجازات، المالية)، لكل تقرير فلاتره، ويُفتح ويُطبع باسم الشركة المختارة
   (هيدر الورقة بشعارها واسمها وسجلها التجاري) أو باسم المجموعة.
   معاينة، طباعة A4 (تُحفظ PDF من نافذة الطباعة)، و Excel.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  function tab(key) { var t = (A.reportTabs || []).find(function (x) { return x[0] === key; }); return !!t && t[2](); }
  var GROUPS = [
    { key: 'fleet', title: 'الأسطول والتشغيل', icon: 'car', items: [
      { key: 'daily', title: 'العمل اليومي', sub: 'التقارير والطلبات والكاش حسب السائق واليوم والشركة', can: function () { return tab('daily'); } },
      { key: 'fleet', title: 'الأسطول', sub: 'السيارات وأيام العمل والتوقف', can: function () { return tab('fleet'); } },
      { key: 'km', title: 'الكيلومترات', sub: 'حسب السيارة والسائق', can: function () { return tab('km'); } }
    ] },
    { key: 'cash', title: 'الكاش والخزينة', icon: 'wallet', items: [
      { key: 'cash', title: 'الكاش وأعماره والخزينة', sub: 'أعمار الأرصدة، الإيصالات حسب المحصّل، الخزينة والإيداعات', can: function () { return tab('cash'); } }
    ] },
    { key: 'payroll', title: 'الرواتب', icon: 'banknote', items: [
      { key: 'payroll', title: 'الرواتب', sub: 'حسب الشهر والشركة، والمبالغ المرحّلة', can: function () { return tab('payroll'); } }
    ] },
    { key: 'maintenance', title: 'الصيانة والحوادث', icon: 'wrench', items: [
      { key: 'maintenance', title: 'الصيانة', sub: 'حسب المركز والسيارة والقطع', can: function () { return tab('maintenance'); } },
      { key: 'accidents', title: 'الحوادث', sub: 'حسب السائق والسيارة ومحاضر الشرطة', can: function () { return tab('accidents'); } }
    ] },
    { key: 'hr', title: 'الموظفون والإجازات', icon: 'users', items: [
      { key: 'leaves', title: 'الإجازات والغياب', sub: 'الإجازات في فترة، بحالتها وأيامها', can: function () { return api.can('reports.view') && api.can('leaves.view'); } }
    ] },
    { key: 'finance', title: 'المالية', icon: 'landmark', items: [
      { key: 'entries', title: 'القيود اليومية', sub: 'القيود في فترة؛ المسودات تُطبع بعلامة مائية إن ضُبطت', can: function () { return api.can('reports.view') && api.can('finance.view'); } }
    ] }
  ];
  function title(key) { var t = null; GROUPS.forEach(function (g) { g.items.forEach(function (i) { if (i.key === key) t = i.title; }); }); return t; }

  BT.pages['report-center'] = function (p, q) {
    A.setTitle('مركز التقارير');
    var v = A.view();
    var groups = GROUPS.map(function (g) { return Object.assign({}, g, { items: g.items.filter(function (i) { return i.can(); }) }); }).filter(function (g) { return g.items.length; });
    if (!api.can('reports.view') || !groups.length) { BT.render(v, A.forbidden()); return; }
    var companies = (api.companies || []).filter(function (c) { return c.is_active; });
    BT.render(v, h`${A.head('مركز التقارير', 'اختر التقرير وفلاتره والشركة التي يُطبع باسمها: معاينة، طباعة A4 أو PDF، و Excel', '')}
      <div class="rc-grid">
        <div class="card rc-list" data-rc-list>${groups.map(function (g) {
          return h`<div class="rc-group"><div class="section-t">${icon(g.icon, 15)} ${g.title}</div>${g.items.map(function (i) {
            return h`<button type="button" class="rc-item" data-rc="${i.key}"><b>${i.title}</b><span class="sub">${i.sub}</span></button>`;
          })}</div>`;
        })}</div>
        <div class="rc-main">
          <div class="card mb-12 rc-company"><div class="field"><label for="rc-company">يُطبع باسم</label>
            <select class="select" id="rc-company" data-rc-company><option value="">المجموعة (أو شركة فلتر التقرير)</option>${companies.map(function (c) { return h`<option value="${c.id}">${api.name(c.name)}</option>`; })}</select>
            <div class="hint">هيدر الورقة (الشعار والاسم والسجل التجاري) وقالبها من «قوالب الطباعة» لهذه الشركة.</div></div></div>
          <div data-rc-body><div class="card">${BT.empty('printer', 'اختر تقريراً', 'من القائمة')}</div></div>
        </div>
      </div>`);
    var body = v.querySelector('[data-rc-body]'), sel = v.querySelector('[data-rc-company]');
    function open(key) {
      BT.$$('[data-rc]', v).forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-rc') === key); b.setAttribute('aria-pressed', b.getAttribute('data-rc') === key ? 'true' : 'false'); });
      BT.render(body, h`<div class="card" data-rc-open="${key}"><div class="card-h"><div class="card-t">${title(key)}</div></div><div data-rc-panel></div></div>`);
      var el = body.querySelector('[data-rc-panel]');
      el._printCompany = function () { return sel.value || null; };
      var panels = A.reportPanels ? A.reportPanels() : {};
      if (panels[key]) panels[key](el);
      else ({ leaves: leavesPanel, entries: entriesPanel })[key](el);
      history.replaceState(null, '', '#/report-center?report=' + key);
    }
    BT.on(v, 'click', '[data-rc]', function (e, b) { open(b.getAttribute('data-rc')); });
    var first = groups.some(function (g) { return g.items.some(function (i) { return i.key === q.report; }); }) ? q.report : null;
    if (first) open(first);
  };

  /* ---------- تقرير بفترة: نموذج، جدول على الشاشة، ومعاينة وطباعة كل الصفوف ---------- */
  function rangeReport(el, o) {
    var to = BT.config.today;
    BT.render(el, h`<form class="toolbar" data-range style="margin:0 0 12px">${BT.f.date({ name: 'from', label: 'من', value: BT.date.add(to, -30), required: true })}${BT.f.date({ name: 'to', label: 'إلى', value: to, required: true })}
      <button type="submit" class="btn btn-primary" style="align-self:flex-end">${icon('chart-column', 15)} عرض</button>
      ${o.excel ? h`<button type="button" class="btn btn-outline" data-excel style="align-self:flex-end">${icon('sheet', 15)} Excel</button>` : ''}
      <button type="button" class="btn btn-ghost" data-preview style="align-self:flex-end">${icon('eye', 15)} معاينة</button>
      <button type="button" class="btn btn-ghost" data-print style="align-self:flex-end">${icon('printer', 15)} طباعة / PDF</button></form><div data-out></div>`);
    var form = el.querySelector('form'), out = el.querySelector('[data-out]'), rows = null, period = null;
    function load() {
      var x = BT.form.values(form);
      period = x;
      BT.render(out, A.spinner());
      o.fetch(x.from, x.to).then(function (r) { rows = r; BT.table(out, { rows: r, columns: o.columns, pageSize: 10, empty: { icon: 'file', title: 'لا يوجد', text: 'في هذه الفترة' } }); }, function (err) { BT.render(out, A.errorBox(err)); });
    }
    function doc() {
      if (!rows) { BT.toast('اعرض التقرير أولاً', { type: 'error' }); return null; }
      var cell = function (c, r) { return c.print ? c.print(r) : c.render ? c.render(r) : (r[c.key] == null ? '—' : r[c.key]); };
      return { title: o.title, meta: 'من ' + period.from + ' إلى ' + period.to, companyId: el._printCompany ? Number(el._printCompany()) || null : null,
        draft: o.draft ? o.draft(rows) : false, body: BT.printTable(o.columns, rows, cell) };
    }
    form.addEventListener('submit', function (e) { e.preventDefault(); load(); });
    form.querySelector('[data-print]').onclick = function () { var d = doc(); if (d) BT.printDoc(d); };
    form.querySelector('[data-preview]').onclick = function () { var d = doc(); if (d) BT.printPreview(d); };
    var xl = form.querySelector('[data-excel]');
    if (xl) xl.onclick = function () { var x = BT.form.values(form); o.excel(x.from, x.to); };
    load();
  }

  function leavesPanel(el) {
    rangeReport(el, {
      title: 'تقرير الإجازات والغياب',
      fetch: function (from, to) { return api.get('/leaves', { date_from: from, date_to: to, limit: 500 }); },
      columns: [
        { key: 'employee', label: 'الموظف', render: function (r) { return r.employee ? api.name(r.employee.name) : '—'; } },
        { key: 'kind', label: 'النوع', render: function (r) { return r.kind_name ? api.name(r.kind_name) : api.t('leave_kind', r.kind); } },
        { key: 'date_from', label: 'من', render: function (r) { return fmt.date(r.date_from); } },
        { key: 'date_to', label: 'إلى', render: function (r) { return fmt.date(r.date_to); } },
        { key: 'days', label: 'الأيام', num: true },
        { key: 'unpaid_days', label: 'بدون راتب', num: true },
        { key: 'status', label: 'الحالة', render: function (r) { return api.t('leave_status', r.status); } }
      ]
    });
  }

  function entriesPanel(el) {
    rangeReport(el, {
      title: 'تقرير القيود اليومية',
      fetch: function (from, to) { return api.get('/finance/entries', { date_from: from, date_to: to, limit: 500 }); },
      draft: function (rows) { return rows.some(function (r) { return r.status === 'draft'; }); },
      excel: api.can('finance.export') ? function (from, to) { A.downloadFile('/finance/entries/export', { date_from: from, date_to: to, format: 'xlsx' }, 'entries-' + from + '-' + to + '.xlsx'); } : null,
      columns: [
        { key: 'number', label: 'رقم القيد', num: true },
        { key: 'entry_date', label: 'التاريخ', render: function (r) { return fmt.date(r.entry_date); } },
        { key: 'description', label: 'البيان' },
        { key: 'source_ref', label: 'المرجع' },
        { key: 'amount', label: 'المبلغ', num: true, render: function (r) { return fmt.money(r.amount); } },
        { key: 'status', label: 'الحالة', render: function (r) { return api.t('entry_status', r.status); } }
      ]
    });
  }
})();
