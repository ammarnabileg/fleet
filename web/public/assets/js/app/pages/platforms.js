/* =====================================================================
   app/pages/platforms.js — الشركات المتعاقد معها: طلبات وكيتا (أساسيتان)
   وأي شركة أخرى. لكل شركة صفحة بتبويبات: نظرة عامة، أنظمة الدفع (مصمم
   القواعد)، السواقين ومعرّفاتهم، حقول التقرير، استيراد الشهر. وطلبات
   السائقين من التطبيق «أنت شغال مع أنهي شركة؟» يعتمدها المكتب أو يرفضها.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;
  var REQ_TONE = { pending: 'o', approved: 'g', rejected: 'r', cancelled: 'n' };
  var REQ_STATUS = { pending: 'بانتظار الموافقة', approved: 'وُوفق', rejected: 'رُفض', cancelled: 'ألغاه السائق' };
  function requestCounts() { return api.can('payroll.view') ? api.get('/payroll/platform-requests/counts').then(null, function () { return { pending: 0, by_platform: {} }; }) : Promise.resolve({ pending: 0, by_platform: {} }); }

  /* ================= الصفحة: الشركات، كل أنظمة الدفع، طلبات السائقين ================= */
  BT.pages['platforms'] = function (p, q) {
    A.setTitle('الشركات المتعاقد معها');
    var v = A.view();
    var tabs = [['list', 'الشركات']];
    if (api.can('payroll.view')) tabs.push(['schemes', 'أنظمة الدفع'], ['requests', 'طلبات السائقين' + (A.counts.platform_requests ? ' (' + A.counts.platform_requests + ')' : '')]);
    var tab = tabs.some(function (t) { return t[0] === q.tab; }) ? q.tab : 'list';
    BT.render(v, h`${A.head('الشركات المتعاقد معها', 'منصات التوصيل التي يعمل معها السائقون: أنظمة الدفع، السائقون ومعرّفاتهم، حقول التقرير، واستيراد الشهر')}
      ${BT.tabs('plat', tabs, tab, 'tabs-line')}
      ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="plat" class="${t[0] === tab ? 'active' : ''}"><div data-p="${t[0]}"></div></div>`; })}`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      var el = v.querySelector('[data-p="' + t + '"]');
      if (t === 'list') platformsPanel(el);
      else if (t === 'schemes') A.schemesPanel(el, q);
      else requestsPanel(el, null);
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/platforms' + (e.detail === 'list' ? '' : '?tab=' + e.detail)); });
    show(tab);
  };

  /* ================= صفحة الشركة ================= */
  BT.pages['platforms/:id'] = function (p, q) {
    var id = +p.id, v = A.view();
    A.setTitle('الشركات المتعاقد معها');
    A.load(v, A.platforms(true), function (list) {
      var plat = list.find(function (x) { return x.id === id; });
      if (!plat) return h`<div class="card"><div class="card-b">${BT.empty('building-2', 'الشركة غير موجودة', '')}</div></div>`;
      A.setTitle(api.name(plat.name), [['الشركات المتعاقد معها', 'platforms'], [api.name(plat.name)]]);
      var tabs = [['overview', 'نظرة عامة']];
      if (api.can('payroll.view')) tabs.push(['schemes', 'أنظمة الدفع'], ['drivers', 'السواقين ومعرّفاتهم'], ['ids', 'معرّفات الشهر']);
      tabs.push(['fields', 'حقول التقرير']);
      if (api.can('payroll.view')) tabs.push(['import', 'استيراد الشهر']);
      var tab = tabs.some(function (t) { return t[0] === q.tab; }) ? q.tab : 'overview';
      setTimeout(function () {
        var drawn = {};
        function show(t) {
          if (drawn[t]) return; drawn[t] = true;
          var el = v.querySelector('[data-p="' + t + '"]');
          ({ overview: overviewPanel, schemes: function (e) { A.schemesPanel(e, q, id); }, drivers: driversPanel, ids: idsPanel, fields: fieldsPanel, import: function (e) { A.monthPanel(e, q, id); } })[t](el, plat);
        }
        v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/platforms/' + id + (e.detail === 'overview' ? '' : '?tab=' + e.detail)); });
        show(tab);
      });
      return h`${A.head(h`${api.name(plat.name)} ${plat.is_core ? BT.pill('أساسية', 'b') : ''}${plat.is_active ? '' : BT.pill('موقوفة', 'n')}`, h`<span class="ltr">${plat.code}</span>`, A.btn('كل الشركات', { icon: 'arrow-right', cls: 'btn-ghost', action: 'go-platforms' }))}
        ${BT.tabs('pl1', tabs, tab, 'tabs-line')}
        ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="pl1" class="${t[0] === tab ? 'active' : ''}"><div data-p="${t[0]}"></div></div>`; })}`;
    }).catch(function () {});
  };
  BT.actions['go-platforms'] = function () { A.go('platforms'); };

  function overviewPanel(el, plat) {
    var canEdit = api.can('settings.update');
    var load = api.can('payroll.view') ? api.get('/payroll/platforms/' + plat.id + '/overview') : Promise.resolve(null);
    A.load(el, load, function (o) {
      A.delegate(el, 'click', '#pl-edit', function () { platformForm(plat, null, function () { A.router.refresh(); }); });
      setTimeout(function () { var box = el.querySelector('[data-req-box]'); if (box) requestsPanel(box, plat.id, true); });
      var stat = function (label, value, tone, link) { return h`<div class="card"><div class="card-b"><div class="muted fs-sm">${label}</div><div class="fs-xl num${tone ? ' t-' + tone : ''}">${link ? h`<a href="${link}">${fmt.int(value)}</a>` : fmt.int(value)}</div></div></div>`; };
      return h`${o ? h`<div class="grid mb-16" data-overview style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px">
          ${stat('السائقون عليها', o.drivers, null, '#/platforms/' + plat.id + '?tab=drivers')}
          ${stat('لهم معرّف في المنصة', o.with_driver_id, 'success')}
          ${stat('بلا معرّف', o.missing_driver_id, o.missing_driver_id ? 'warning' : null, '#/platforms/' + plat.id + '?tab=drivers')}
          ${stat('أنظمة الدفع النشطة', o.schemes, null, '#/platforms/' + plat.id + '?tab=schemes')}
          ${stat('طلبات سائقين تنتظر', o.pending_requests, o.pending_requests ? 'warning' : null)}
        </div>` : ''}
        <div data-req-box></div>
        <div class="card"><div class="card-h"><div class="card-t">إعدادات الشركة</div>${canEdit ? h`<button type="button" class="btn btn-sm btn-ghost ms-auto" id="pl-edit">${icon('pencil', 14)} تعديل</button>` : ''}</div>
          <div class="card-b">${BT.kv([
            ['التقرير اليومي', (plat.daily_fields || []).length ? plat.daily_fields.map(function (f) { return api.t('daily_field', f); }).join('، ') : 'لقطة الشاشة فقط'],
            ['كشف الشهر من السائق', plat.driver_fields.length ? plat.driver_fields.map(function (f) { return api.t('driver_field', f); }).join('، ') : 'لا يُطلب'],
            ['أعمدة كشف الراتب', plat.columns.length ? plat.columns.length + ' عموداً' : 'كل الأعمدة (لا نموذج)']
          ])}</div></div>`;
    }).catch(function () {});
  }

  /* السواقين ومعرّفاتهم: المعرّف يُعدّل في مكانه، ومن بلا معرّف في تبويب وحده */
  function driversPanel(el, plat) {
    var canEdit = api.can('employees.update');
    BT.render(el, h`<div class="card"><div class="banner note fs-sm mb-12">${icon('info', 15)}<div>معرّف السائق في ${api.name(plat.name)} هو ما يطابق به استيراد الشهر صفوف الملف. اكتبه واضغط حفظ (Enter). لإضافة سائقين للشركة: الموظفون ← حدّدهم ← «تعيين منصة»، أو اعتمد طلباتهم من التطبيق.</div></div><div data-t></div></div>`);
    var t = BT.table(el.querySelector('[data-t]'), {
      key: 'plat-drivers-' + plat.id,
      fetch: function (s) { return api.get('/payroll/platforms/' + plat.id + '/drivers', { missing: s.chip === 'missing' ? 'true' : null }).then(function (rows) { var q = (s.q || '').toLowerCase(); return (q ? rows.filter(function (r) { return (api.name(r.name) + ' ' + r.employee_number + ' ' + (r.platform_driver_id || '')).toLowerCase().indexOf(q) >= 0; }) : rows).slice(s.offset, s.offset + s.limit); }); },
      search: { placeholder: 'ابحث بالاسم أو الرقم أو المعرّف' },
      chips: { value: q0(), all: false, options: [{ v: 'all', t: 'الكل' }, { v: 'missing', t: 'بلا معرّف' }] },
      columns: [
        { key: 'name', label: 'السائق', render: function (r) { return h`${A.person(r, r.employee_number)}`; } },
        { key: 'platform_driver_id', label: 'المعرّف في المنصة', render: function (r) {
          return canEdit ? h`<form class="flex gap-4 items-center" data-pdid="${r.id}" novalidate><input class="input ltr" name="pdid" value="${r.platform_driver_id || ''}" maxlength="60" placeholder="—" aria-label="المعرّف في المنصة" style="max-width:180px"><button type="submit" class="btn btn-sm btn-outline">حفظ</button></form>` : (r.platform_driver_id ? h`<span class="ltr">${r.platform_driver_id}</span>` : h`<span class="muted">—</span>`);
        } },
        { key: 'scheme', label: 'نظام الدفع هذا الشهر', render: function (r) { return r.scheme ? api.name(r.scheme.name) : h`<span class="muted">—</span>`; } },
        { key: 'missing', label: '', render: function (r) { return r.platform_driver_id ? '' : BT.pill('بلا معرّف', 'o'); } }
      ],
      empty: { icon: 'users', title: 'لا سائقين هنا', text: 'لا سائقين على هذه الشركة، أو كلهم لهم معرّف' }
    });
    function q0() { return /[?&]missing=1/.test(location.hash) ? 'missing' : 'all'; }
    A.delegate(el, 'submit', 'form[data-pdid]', function (e, f) {
      e.preventDefault();
      var input = f.querySelector('[name=pdid]'), btn = f.querySelector('button');
      btn.disabled = true;
      api.put('/payroll/platforms/' + plat.id + '/drivers/' + f.getAttribute('data-pdid'), { platform_driver_id: input.value.trim() || null }).then(function (r) {
        BT.toast(r.platform_driver_id ? 'حُفظ المعرّف ' + r.platform_driver_id : 'أُزيل المعرّف');
        btn.disabled = false; input.value = r.platform_driver_id || '';
        f.setAttribute('data-saved', r.platform_driver_id || '');
      }, function (err) { btn.disabled = false; api.fail(err); });
    });
    return t;
  }

  /* المعرّف لا يلزم موظفاً: كل شهر يبدأ بمعرّفات الشهر الذي قبله، ويُغيَّر ما انتقل لموظف آخر فقط، وملف الشهر يُقرأ بمعرّفات شهره */
  function idsPanel(el, plat) {
    var canEdit = api.can('employees.update');
    var month = BT.config.today.slice(0, 7);
    BT.render(el, h`<div class="card"><div class="banner note fs-sm mb-12">${icon('info', 15)}<div>كل شهر يبدأ بمعرّفات الشهر الذي قبله. لو اشتغل موظف على معرّف موظف آخر هذا الشهر اكتب المعرّف عنده واحفظ: ينتقل له من هذا الشهر، ومرتب المعرّف عن الشهر يكون له. الشهور السابقة لا تتغير، وملف الشركة يُقرأ بمعرّفات شهره.</div></div>
      <div class="flex gap-8 items-center mb-12"><label class="label" for="ids-month">الشهر</label><input type="month" class="input" id="ids-month" value="${month}" style="max-width:180px"></div><div data-t></div></div>`);
    var box = el.querySelector('[data-t]');
    function draw() {
      BT.table(box, {
        key: 'plat-ids-' + plat.id,
        fetch: function (s) { return api.get('/payroll/platforms/' + plat.id + '/rider-ids', { month: month + '-01' }).then(function (rows) { var q = (s.q || '').toLowerCase(); rows = s.chip === 'changed' ? rows.filter(function (r) { return r.changed; }) : rows; return (q ? rows.filter(function (r) { return (api.name(r.name) + ' ' + r.employee_number + ' ' + (r.rider_id || '') + ' ' + (r.previous || '')).toLowerCase().indexOf(q) >= 0; }) : rows).slice(s.offset, s.offset + s.limit); }); },
        search: { placeholder: 'ابحث بالاسم أو الرقم أو المعرّف' },
        chips: { value: 'all', all: false, options: [{ v: 'all', t: 'الكل' }, { v: 'changed', t: 'تغيّر عن الشهر السابق' }] },
        columns: [
          { key: 'name', label: 'السائق', render: function (r) { return h`${A.person(r, r.employee_number)}`; } },
          { key: 'previous', label: 'الشهر السابق', render: function (r) { return r.previous ? h`<span class="ltr">${r.previous}</span>` : h`<span class="muted">—</span>`; } },
          { key: 'rider_id', label: 'معرّف هذا الشهر', render: function (r) {
            return canEdit ? h`<form class="flex gap-4 items-center" data-rid="${r.id}" novalidate><input class="input ltr" name="rid" value="${r.rider_id || ''}" maxlength="60" placeholder="—" aria-label="معرّف هذا الشهر" style="max-width:180px"><button type="submit" class="btn btn-sm btn-outline">حفظ</button></form>` : (r.rider_id ? h`<span class="ltr">${r.rider_id}</span>` : h`<span class="muted">—</span>`);
          } },
          { key: 'changed', label: '', render: function (r) { return r.changed ? BT.pill('تغيّر', 'b') : ''; } }
        ],
        empty: { icon: 'users', title: 'لا سائقين هنا', text: 'لا سائقين على هذه الشركة في هذا الشهر' }
      });
    }
    draw();
    el.querySelector('#ids-month').addEventListener('change', function (e) { if (e.target.value) { month = e.target.value; draw(); } });
    A.delegate(el, 'submit', 'form[data-rid]', function (e, f) {
      e.preventDefault();
      var input = f.querySelector('[name=rid]'), btn = f.querySelector('button'), value = input.value.trim();
      btn.disabled = true;
      api.put('/payroll/platforms/' + plat.id + '/rider-ids/' + f.getAttribute('data-rid'), { month: month + '-01', rider_id: value || null }).then(function () {
        BT.toast(value ? 'المعرّف ' + value + ' له من هذا الشهر' : 'أُزيل معرّفه لهذا الشهر');
        draw();
      }, function (err) { btn.disabled = false; api.fail(err); });
    });
  }

  function fieldsPanel(el, plat) {
    var canEdit = api.can('settings.update');
    A.load(el, api.get('/payroll/platforms/' + plat.id + '/fields'), function (f) {
      A.delegate(el, 'click', '#pl-fields', function () { A.platformFields(plat, function () { fieldsPanel(el, plat); }); });
      var row = function (x) { return h`<tr><td>${api.name(x.label)}</td><td class="ltr fs-sm">${x.key}</td><td>${x.builtin ? BT.pill('مدمج', 'n') : api.t('rule_choice', x.type, null, x.type)}</td><td>${x.required ? 'مطلوب' : ''}</td></tr>`; };
      var table = function (rows) { return rows.length ? h`<div class="table-wrap"><table class="t compact"><thead><tr><th>الحقل</th><th>المفتاح</th><th>النوع</th><th></th></tr></thead><tbody>${rows.map(row)}</tbody></table></div>` : h`<div class="muted fs-sm">لا حقول</div>`; };
      return h`<div class="card"><div class="card-h"><div class="card-t">حقول التقرير</div>${canEdit ? h`<button type="button" class="btn btn-sm btn-primary ms-auto" id="pl-fields">${icon('list-checks', 14)} تعديل الحقول</button>` : ''}</div>
        <div class="card-b"><div class="section-t">التقرير اليومي في تطبيق السائق</div>${table(f.daily)}
          <div class="section-t mt-12">بيانات الشهر (مراجعة الشهر واستيراده)</div>${table(f.monthly)}</div></div>`;
    }).catch(function () {});
  }

  /* ================= طلبات السائقين: «أنت شغال مع أنهي شركة؟» ================= */
  function requestsPanel(el, platformId, pendingOnly) {
    var canDecide = api.can('employees.update');
    if (pendingOnly) { // a platform's overview: what waits for it, nothing when nothing waits
      api.get('/payroll/platform-requests', { status: 'pending', platform_id: platformId }).then(function (rows) {
        if (!document.contains(el)) return;
        BT.render(el, rows.length ? h`<div class="card mb-16" data-pending="platform_requests"><div class="card-h"><b>طلبات سائقين للعمل مع هذه الشركة</b></div><div class="card-b">${rows.map(function (r) { return reqRow(r, canDecide); })}</div></div>` : '');
      }, function () { BT.render(el, ''); });
      A.delegate(el, 'click', '[data-req-act]', function (e, b) { act(b, function () { requestsPanel(el, platformId, true); }); });
      return;
    }
    BT.render(el, h`<div class="card"><div class="banner note fs-sm mb-12">${icon('info', 15)}<div>السائق بلا شركة يختار من التطبيق أول مرة «أنت شغال مع أنهي شركة؟». حتى الموافقة يرى حقول تقرير الشركة التي اختارها، والرواتب لا تحسبه عليها. الموافقة تضع شركته ومعرّفه فيها.</div></div><div data-t></div></div>`);
    var t = BT.table(el.querySelector('[data-t]'), {
      fetch: function (s) { return api.get('/payroll/platform-requests', { status: s.chip === 'all' ? null : s.chip, platform_id: platformId, limit: s.limit, offset: s.offset }); },
      chips: { value: 'pending', all: false, options: [{ v: 'pending', t: 'بانتظار الموافقة' }, { v: 'approved', t: 'وُوفق' }, { v: 'rejected', t: 'رُفض' }, { v: 'all', t: 'الكل' }] },
      columns: [
        { key: 'employee', label: 'السائق', render: function (r) { return A.person(r.employee); } },
        { key: 'platform', label: 'الشركة', render: function (r) { return r.platform ? api.name(r.platform.name) : '—'; } },
        { key: 'status', label: 'الحالة', render: function (r) { return h`${BT.pill(REQ_STATUS[r.status], REQ_TONE[r.status])}${r.admin_note ? h`<span class="sub">${r.admin_note}</span>` : ''}${r.platform_driver_id ? h`<span class="sub ltr">${r.platform_driver_id}</span>` : ''}`; } },
        { key: 'created_at', label: 'الطلب', render: function (r) { return h`<span class="num">${fmt.dt(r.created_at)}</span>${r.driver_note ? h`<span class="sub">${r.driver_note}</span>` : ''}`; } },
        { key: 'act', label: '', render: function (r) { return r.status === 'pending' && canDecide ? h`<span class="nowrap">${actBtns(r)}</span>` : ''; } }
      ],
      empty: { icon: 'building-2', title: 'لا طلبات هنا', text: '' }
    });
    A.delegate(el, 'click', '[data-req-act]', function (e, b) { e.stopPropagation(); act(b, function () { t.refresh(); }); });
    function act(b, after) { decide(b.getAttribute('data-req-act'), JSON.parse(b.getAttribute('data-req')), after); }
    return t;
  }
  function actBtns(r) {
    var data = JSON.stringify({ id: r.id, version: r.version, platform: r.platform, employee: r.employee });
    return h`<button type="button" class="btn btn-sm btn-primary" data-req-act="approve" data-req="${data}">موافقة</button> <button type="button" class="btn btn-sm btn-outline" data-req-act="reject" data-req="${data}">رفض</button>`;
  }
  function reqRow(r, canDecide) {
    return h`<div class="between mb-12" data-pending-id="${r.id}"><div class="flex-1">${A.person(r.employee)}<span class="sub">${r.driver_note || ''} · ${fmt.dt(r.created_at)}</span></div><div class="nowrap">${canDecide ? actBtns(r) : ''}</div></div>`;
  }
  function decide(kind, r, after) {
    var done = function () { A.refreshCounts(); if (after) after(); };
    if (kind === 'reject') {
      A.confirmRun({ title: 'رفض طلب ' + api.name(r.employee.name), message: 'يرى السائق السبب في التطبيق ويختار من جديد.', tone: 'danger', confirmText: 'رفض', reason: { label: 'السبب', required: true },
        run: function (reason) { return api.post('/payroll/platform-requests/' + r.id + '/reject', { version: r.version, note: reason }); }, done: 'رُفض الطلب', after: done });
      return;
    }
    A.platforms().then(function (plats) {
      A.formModal({
        title: 'موافقة: ' + api.name(r.employee.name), subtitle: 'اختار ' + api.name(r.platform.name), icon: 'building-2', size: 'sm', submitText: 'موافقة', done: 'وُوفق الطلب: الشركة والمعرّف محفوظان',
        body: h`<div class="form">${BT.f.select({ name: 'platform_id', label: 'الشركة', value: String(r.platform.id), placeholder: false, options: plats.filter(function (p) { return p.is_active; }).map(function (p) { return { v: String(p.id), t: api.name(p.name) }; }) })}
          ${BT.f.input({ name: 'platform_driver_id', label: 'معرّفه في المنصة', optional: true, hint: 'يمكن إضافته لاحقاً من «السواقين ومعرّفاتهم»' })}</div>`,
        submit: function (v) { return api.post('/payroll/platform-requests/' + r.id + '/approve', { version: r.version, platform_id: +v.platform_id, platform_driver_id: v.platform_driver_id || null }); },
        after: done
      });
    }, api.fail);
  }
  A.platformRequestView = function (id, after) { // the alert's «مراجعة»: the queue where it waits
    A.go('platforms?tab=requests');
    if (after) after();
  };

  /* ================= الشركات: القائمة ================= */
  var RULE_HINT = 'لكل شركة صفحتها: السائقون ومعرّفاتهم، أنظمة الدفع (مصمم القواعد)، حقول التقرير، واستيراد الشهر. طلبات وكيتا أساسيتان لا تُحذفان؛ وأي شركة أخرى تُضاف يدوياً.';
  function platformsPanel(el) {
    var canEdit = api.can('settings.update');
    A.load(el, Promise.all([A.platforms(true), requestCounts()]), function (r) {
      var list = r[0], waiting = r[1].by_platform || {};
      A.delegate(el, 'click', '[data-del]', function (e, x) {
        var p = list.find(function (y) { return y.id === +x.getAttribute('data-del'); });
        A.confirmRun({ title: 'حذف ' + api.name(p.name), message: 'تُحذف الشركة نهائياً. شركة عليها سائقون أو أنظمة أو بيانات شهر لا تُحذف: أوقفها من «تعديل».', confirmText: 'حذف', tone: 'danger',
          run: function () { return api.del('/payroll/platforms/' + p.id); }, done: 'حُذفت الشركة', after: function () { A.platforms(true); A.refreshNavPlatforms(); platformsPanel(el); } });
      });
      A.delegate(el, 'click', '[data-edit]', function (e, x) { var p = list.find(function (y) { return y.id === +x.getAttribute('data-edit'); }); platformForm(p, null, function () { platformsPanel(el); }); });
      A.delegate(el, 'click', '[data-fields]', function (e, x) { var p = list.find(function (y) { return y.id === +x.getAttribute('data-fields'); }); A.platformFields(p, function () { platformsPanel(el); }); });
      setTimeout(function () {
        var b = el.querySelector('#plat-template'); if (b) b.onclick = function () { fromTemplate(function () { platformsPanel(el); }); };
        var n = el.querySelector('#plat-new'); if (n) n.onclick = function () { platformForm(null, null, function () { platformsPanel(el); }); };
      });
      return h`<div class="flex gap-8 items-center mb-12"><div class="muted fs-sm">${RULE_HINT}</div><span class="spacer"></span>${canEdit ? h`${A.btn('من نموذج Excel', { icon: 'file-spreadsheet', cls: 'btn-outline', id: 'plat-template' })}${A.btn('منصة جديدة', { icon: 'plus', cls: 'btn-primary', id: 'plat-new' })}` : ''}</div>
        ${list.length ? h`<div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(360px,1fr))">${list.map(function (p) {
          return h`<div class="card" data-platform-card="${p.code}"><div class="card-h"><div class="card-t"><a href="#/platforms/${p.id}">${api.name(p.name)}</a></div><span class="muted fs-sm ltr">${p.code}</span>${p.is_core ? BT.pill('أساسية', 'b') : ''}${p.is_active ? '' : BT.pill('موقوفة', 'n')}${waiting[p.id] ? BT.pill(waiting[p.id] + ' طلب سائق', 'o') : ''}<span class="ms-auto nowrap"><a class="btn btn-sm btn-outline" href="#/platforms/${p.id}">${icon('arrow-left', 14)} فتح</a>${canEdit ? h`<button type="button" class="btn btn-sm btn-ghost" data-fields="${p.id}">${icon('list-checks', 14)} حقول المنصة</button><button type="button" class="btn btn-sm btn-ghost" data-edit="${p.id}">${icon('pencil', 14)} تعديل</button>${p.is_core ? '' : h`<button type="button" class="btn btn-sm btn-ghost" data-del="${p.id}" title="حذف">${icon('trash-2', 14)}</button>`}` : ''}</span></div>
            <div class="card-b">${BT.kv([
              ['السائقون', fmt.int(p.drivers)],
              ['التقرير اليومي', (p.daily_fields || []).length ? p.daily_fields.map(function (f) { return api.t('daily_field', f); }).join('، ') : 'لقطة الشاشة فقط'],
              ['كشف الشهر من السائق', p.driver_fields.length ? p.driver_fields.map(function (f) { return api.t('driver_field', f); }).join('، ') + ' مع لقطات الشاشة' : 'لا يُطلب: الشهر من التقارير اليومية المعتمدة'],
              ['طريقة الحساب', h`<a href="#/platforms/${p.id}?tab=schemes">أنظمة الدفع ← مصمم القواعد</a>`],
              ['أعمدة الكشف', p.columns.length ? p.columns.length + ' عموداً: ' + p.columns.slice(0, 4).map(function (c) { return c.header; }).join('، ') + '…' : 'كل الأعمدة (لا نموذج)']
            ])}</div></div>`;
        })}</div>` : h`<div class="card"><div class="card-b">${BT.empty('banknote', 'لا توجد منصات بعد', 'أضف منصة جديدة واختر ما يرسله السائق في تقريره اليومي، أو ارفع نموذج كشف الرواتب الذي تستخدمونه (Excel): كل ورقة فيه تصبح منصة بأعمدتها وترتيبها.')}</div></div>`}`;
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
  // ما يرسله السائق كل يوم: منصة تحتسب اليوم صالحاً أو لا، وأخرى بالطلبات والكاش
  var DAILY = [
    ['valid_day', 'اليوم صالح', 'هل احتسبت المنصة يومه صالحاً (نعم أو لا)'],
    ['orders', 'عدد الطلبات', 'طلبات اليوم كما في تطبيق المنصة'],
    ['cash', 'الكاش', 'المبلغ الذي حصّله نقداً'],
  ];
  function platformForm(p, sheet, done) {
    var editing = !!p;
    // بلا نموذج Excel: منصة فارغة، وكشف الراتب بكل الأعمدة
    p = p || { code: '', name: { ar: sheet ? sheet.suggested_name : '', en: '' }, driver_fields: sheet ? sheet.driver_fields : [], daily_fields: ['orders', 'cash'], pay_basic: false, per_order: '0.000', per_hour: '0.000', per_valid_day: '0.000', invalid_days: sheet ? sheet.invalid_days : 'none', invalid_day_amount: null, day_divisor: 30, columns: sheet ? sheet.columns : [] };
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
        <div class="section-t mt-12">التقرير اليومي في تطبيق السائق: ما يُسأل عنه مع لقطة شاشة يومه من تطبيق المنصة</div>
        <div class="flex gap-12 wrap" data-daily>${DAILY.map(function (f) { return BT.f.check({ name: 'dy_' + f[0], label: h`<b>${f[1]}</b> <span class="muted fs-sm">${f[2]}</span>`, checked: (p.daily_fields || []).indexOf(f[0]) >= 0 }); })}</div>
        <div class="hint">مثلاً: منصة تحتسب اليوم صالحاً أو لا ← «اليوم صالح» وحده؛ منصة بالطلبات والدفع نقداً ← «عدد الطلبات» و«الكاش». لا شيء محدداً: لقطة الشاشة فقط. الطلبات والأيام الصالحة في الشهر تُجمع من التقارير اليومية المعتمدة؛ وتقرير لم يُراجع يوقف رواتب صاحبه حتى يُراجع.</div>
        <div class="section-t mt-12">ما يرسله السائق كل شهر مع لقطات الشاشة (اتركه فارغاً إن كان الشهر من التقارير اليومية)</div>
        <div class="flex gap-12 wrap">${['valid_days', 'orders', 'hours'].map(function (f) { return BT.f.check({ name: 'df_' + f, label: api.t('driver_field', f), checked: p.driver_fields.indexOf(f) >= 0 }); })}</div>
        <div class="section-t mt-12">طريقة الحساب</div>
        <div class="banner note fs-sm mb-8">${icon('info', 15)}<div>لا تُضبط هنا: تُصمم أنظمة دفع المنصة من «أنظمة الدفع ← مصمم القواعد» (من قالب أو قاعدة قاعدة)، وحقولها الخاصة من «حقول المنصة».</div></div>
        <div class="section-t mt-12">أعمدة كشف الراتب (بترتيب نموذجكم)</div>
        ${unknown ? h`<div class="banner warn fs-sm mb-8">${icon('triangle-alert', 15)}<div>${unknown} عمود لم يُعرف معناه: اختر له المعنى أو اتركه «عمود فارغ».</div></div>` : ''}
        ${cols.length ? h`<div class="table-wrap"><table class="t compact"><thead><tr><th class="num">#</th><th>العنوان في الكشف</th><th>ما يحتويه</th></tr></thead><tbody data-cols>${columnRows(cols)}</tbody></table></div>` : h`<div class="hint">بلا نموذج: كشف الراتب بكل الأعمدة. لترتيب أعمدة نموذجكم أنشئ المنصة «من نموذج Excel».</div>`}`,
      submit: function (v, dlg) {
        var panel = dlg && dlg.panel ? dlg.panel : document;
        var columns = cols.map(function (c, i) { return { header: (panel.querySelector('[data-col-h="' + i + '"]') || {}).value || c.header, code: (panel.querySelector('[data-col-c="' + i + '"]') || {}).value || c.code }; });
        var body = {
          name: Object.assign({}, p.name, { ar: v.name_ar, en: v.name_en }),
          driver_fields: ['valid_days', 'orders', 'hours'].filter(function (f) { return v['df_' + f]; }),
          daily_fields: ['orders', 'cash', 'valid_day'].filter(function (f) { return v['dy_' + f]; }),
          columns: columns
        };
        if (editing) return api.patch('/payroll/platforms/' + p.id, Object.assign(body, { version: p.version, is_active: !!v.is_active }));
        return api.post('/payroll/platforms', Object.assign(body, { code: v.code }));
      },
      after: function () { A.platforms(true); A.refreshNavPlatforms(); done(); }
    });
  }


  A.platformForm = platformForm;
})();
