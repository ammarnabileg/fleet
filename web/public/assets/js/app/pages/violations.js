/* =====================================================================
   app/pages/violations.js — مخالفات العمل (#/violations)  (BRD FR-VIO-01..05، BR-09/10/13، UAT-05)
   من المكتب (طلب، شكوى، غياب…) أو من تنبيه يحوّله المشرف، أو يفتحها النظام (تزييف الموقع،
   انقطاع الإشارة المتكرر). مراجعة ← معتمدة أو مستبعدة ← اعتراض السائق في المهلة ← قرار نهائي.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;
  var SOURCES = ['attendance', 'cash', 'orders', 'complaints', 'accidents', 'tracking'];
  A.tone.violation_status = { pending: 'o', approved: 'b', excluded: 'n', objected: 'o', upheld: 'r', overturned: 'g' };
  // التنبيهات التي تتحول لمخالفة (BR-13: السرعة وانقطاع التتبع تنبيهات حتى يقرر المشرف)
  A.violationFromAlert = { speeding: 'speeding', signal_lost: 'signal_loss', gps_off: 'signal_loss', location_permission_off: 'signal_loss', tracking_stopped: 'signal_loss', daily_report_missing: 'report_late', cash_balance_high: 'cash_deposit_late' };

  function fileUrl(v, sha) { return api.url('/violations/' + v.id + '/files/' + sha); }
  function amount(v) { return v.amount == null ? raw('<span class="muted">—</span>') : Number(v.amount) ? BT.amt(Number(v.amount)) : raw('<span class="muted fs-sm">إنذار</span>'); }
  function status(v) {
    var pill = A.pill('violation_status', v.status);
    if (v.status === 'approved') return h`${pill}<span class="sub">${v.final ? 'نهائية' : 'الاعتراض حتى ' + fmt.dt(v.objection_deadline)}</span>`;
    return pill;
  }

  BT.pages['violations'] = function (p, q) {
    A.setTitle('مخالفات العمل');
    var v = A.view(), tab = ['types', 'causes'].indexOf(q.tab) >= 0 ? q.tab : 'list';
    var tabs = [['list', 'المخالفات'], ['types', 'الأنواع'], ['causes', 'أسباب الاستبعاد']];
    BT.render(v, h`${A.head('مخالفات العمل', 'كل مخالفة تُراجع قبل أن تُحسب، وللسائق أن يعترض من التطبيق خلال المهلة. ما سببه خارج مسؤولية السائق (من قائمة أسباب الاستبعاد) يُستبعد وحده.',
        api.can('violations.manage') ? A.btn('تسجيل مخالفة', { icon: 'plus', cls: 'btn-primary', action: 'violation-new' }) : '')}
      ${BT.tabs('violations', tabs, tab, 'tabs-line')}
      ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="violations" class="${t[0] === tab ? 'active' : ''}"><div id="violations-${t[0]}"></div></div>`; })}`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      ({ list: listPanel, types: typesPanel, causes: causesPanel })[t](document.getElementById('violations-' + t), q);
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); });
    show(tab);
  };

  /* ---------- المخالفات ---------- */
  function listPanel(el, q) {
    var t = BT.table(el, {
      fetch: function (s) {
        var st = { review: 'pending', objections: 'objected', approved: 'approved', final: 'upheld,overturned', excluded: 'excluded' }[s.chip];
        return api.get('/violations', { status: st, limit: s.limit, offset: s.offset });
      },
      chips: { value: q.chip || 'review', all: 'الكل', options: [{ v: 'review', t: 'للمراجعة' }, { v: 'objections', t: 'اعتراضات' }, { v: 'approved', t: 'معتمدة' }, { v: 'final', t: 'قرار نهائي' }, { v: 'excluded', t: 'مستبعدة' }] },
      columns: [
        { key: 'number', label: 'المخالفة', render: function (x) { return h`<span class="num">#${x.number}</span><span class="sub">${fmt.dt(x.occurred_at)}</span>`; } },
        { key: 'driver', label: 'السائق', render: function (x) { return x.driver ? A.person(x.driver) : '—'; } },
        { key: 'type', label: 'النوع', render: function (x) { return h`${api.name(x.type.name)}<span class="sub">${api.t('violation_source', x.type.source)}${x.reference ? ' · ' + x.reference : ''}</span>`; } },
        { key: 'origin', label: 'المصدر', render: function (x) { return x.origin === 'system' ? BT.pill('النظام', 'n') : x.origin === 'alert' ? BT.pill('من تنبيه', 'n') : raw('<span class="muted fs-sm">المكتب</span>'); } },
        { key: 'amount', label: 'الغرامة', num: true, render: amount },
        { key: 'status', label: 'الحالة', render: status }
      ],
      rowClick: function (x) { view(x.id, function () { t.refresh(); A.refreshCounts(); }); },
      empty: { icon: 'shield-alert', title: 'لا توجد مخالفات هنا' }
    });
    A._violationsTable = t;
  }

  function view(id, done) {
    api.get('/violations/' + id).then(function (x) {
      var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
      function after(dlg) { return function () { dlg.close(); if (done) done(); }; }
      if (x.status === 'pending' && api.can('violations.approve')) {
        btns.push({ label: 'استبعاد', cls: 'btn-ghost', icon: 'x', close: false, onClick: function (dlg) {
          A.confirmRun({ title: 'استبعاد المخالفة', confirmText: 'استبعاد', message: 'لا تُحسب على السائق ولا يراها.', reason: { label: 'سبب الاستبعاد', required: true },
            run: function (r) { return api.post('/violations/' + x.id + '/exclude', { note: r }); }, done: 'استُبعدت المخالفة', after: after(dlg) });
        } });
        btns.push({ label: 'اعتماد', cls: 'btn-primary', icon: 'check', close: false, onClick: function (dlg) {
          A.formModal({
            title: 'اعتماد المخالفة #' + x.number, icon: 'shield-alert', size: 'sm', done: 'اعتُمدت المخالفة وأُبلغ السائق',
            body: h`<div class="form">${BT.f.money({ name: 'amount', label: 'الغرامة (صفر = إنذار)', required: true, value: x.amount != null ? x.amount : '0.000' })}
              ${BT.f.textarea({ name: 'note', label: 'ملاحظة', optional: true, rows: 2 })}
              <div class="hint">يُبلَّغ السائق ويمكنه الاعتراض من التطبيق خلال المهلة. الغرامة تُخصم من راتبه بعد أن تصبح نهائية.</div></div>`,
            submit: function (f) { return api.post('/violations/' + x.id + '/approve', { amount: String(f.amount), note: f.note || null }); },
            after: after(dlg)
          });
        } });
      }
      if (x.status === 'objected' && api.can('violations.approve')) {
        [[false, 'قبول الاعتراض', 'تُلغى المخالفة ولا يُخصم شيء.', 'قُبل الاعتراض'], [true, 'رفض الاعتراض', 'المخالفة نهائية وتُخصم غرامتها.', 'رُفض الاعتراض']].forEach(function (d) {
          btns.push({ label: d[1], cls: d[0] ? 'btn-primary' : 'btn-ghost', close: false, onClick: function (dlg) {
            A.confirmRun({ title: d[1], tone: d[0] ? 'danger' : 'success', confirmText: d[1], message: d[2], reason: { label: 'سبب القرار', required: true },
              run: function (r) { return api.post('/violations/' + x.id + '/decide', { uphold: d[0], note: r }); }, done: d[3], after: after(dlg) });
          } });
        });
      }
      var photos = [].concat(x.evidence_sha256 ? [{ src: fileUrl(x, x.evidence_sha256), caption: 'الدليل' }] : [], x.objection_sha256 ? [{ src: fileUrl(x, x.objection_sha256), caption: 'مرفق الاعتراض' }] : []);
      BT.drawer.open({
        title: h`مخالفة <span class="num">#${x.number}</span> · ${api.name(x.type.name)}`, subtitle: (x.driver ? api.name(x.driver.name) + ' · ' : '') + fmt.dt(x.occurred_at), icon: 'shield-alert', size: 'lg',
        body: h`${x.status === 'objected' ? h`<div class="banner warn mb-12" data-objection>${icon('triangle-alert', 16)}<div><b>اعتراض السائق:</b> ${x.objection}</div></div>` : ''}
          ${photos.length ? h`<div class="mb-12">${A.thumbs(photos)}</div>` : ''}
          ${BT.kv([
            ['الحالة', status(x)],
            ['السائق', x.driver ? A.person(x.driver) : '—'],
            ['النوع', h`${api.name(x.type.name)} · ${api.t('violation_source', x.type.source)}`],
            x.vehicle_plate ? ['السيارة', h`<span class="plate">${x.vehicle_plate}</span>`] : null,
            ['الوصف', x.description],
            x.reference ? ['المرجع', x.reference] : null,
            x.cause ? ['سبب خارج مسؤوليته', api.name(x.cause.name)] : null,
            ['التسجيل', (x.origin === 'system' ? 'النظام' : x.origin === 'alert' ? 'من تنبيه' : 'المكتب') + (x.created_by ? ' · ' + x.created_by : '') + ' · ' + fmt.dt(x.created_at)],
            ['الغرامة', amount(x)],
            x.reviewed_at ? ['المراجعة', (x.reviewed_by || 'تلقائياً') + ' · ' + fmt.dt(x.reviewed_at) + (x.review_note ? ' · ' + x.review_note : '')] : null,
            x.objected_at && x.status !== 'objected' ? ['الاعتراض', x.objection + ' · ' + fmt.dt(x.objected_at)] : null,
            x.final_at ? ['القرار النهائي', (x.final_by || '') + ' · ' + fmt.dt(x.final_at) + ' · ' + x.final_note] : null,
            x.deduction ? ['الخصم', h`${BT.amt(Number(x.deduction.total))} · ${A.pill('deduction_status', x.deduction.status)}`] : null
          ].filter(Boolean))}`,
        buttons: btns
      });
    }, api.fail);
  }

  /* ---------- تسجيل مخالفة (من المكتب أو من تنبيه) ---------- */
  function driverOf(alert) {
    if (!alert) return Promise.resolve(null);
    if (alert.entity_type === 'employee') return Promise.resolve(alert.entity_id);
    if (alert.entity_type === 'custody') return api.get('/custodies/' + alert.entity_id).then(function (c) { return c.driver ? c.driver.id : null; });
    return Promise.resolve(null);
  }
  BT.actions['violation-new'] = function () { A.newViolation({}); };
  A.newViolation = function (pre) { // pre.alert: an alert turned into a violation (its driver and type proposed)
    Promise.all([A.all('/employees', { is_driver: true }), api.get('/violations/types'), api.get('/violations/causes'), driverOf(pre.alert)]).then(function (r) {
      var drivers = r[0], types = r[1].filter(function (t) { return t.active; }), causes = r[2].filter(function (c) { return c.active; });
      var label = function (e) { return api.name(e.name) + ' — ' + e.employee_number; };
      var chosen = drivers.find(function (e) { return e.id === r[3]; });
      var typeCode = pre.alert ? A.violationFromAlert[pre.alert.kind] : null;
      var type = types.find(function (t) { return t.code === typeCode; });
      A.formModal({
        title: pre.alert ? 'تحويل التنبيه لمخالفة' : 'تسجيل مخالفة', subtitle: pre.alert ? pre.alert.message : 'تُراجع قبل أن تُحسب على السائق', icon: 'shield-alert', size: 'lg', done: false,
        body: h`<div class="form-grid">
          <div class="full">${A.picker({ name: 'drv', label: 'السائق', required: true, items: drivers.map(function (e) { return { id: e.id, label: label(e) }; }), value: chosen ? chosen.id : '' })}</div>
          ${BT.f.select({ name: 'type', label: 'نوع المخالفة', required: true, value: type ? String(type.id) : '', options: SOURCES.flatMap(function (s) { return types.filter(function (t) { return t.source === s; }).map(function (t) { return { v: String(t.id), t: api.t('violation_source', s) + ' — ' + api.name(t.name) }; }); }) })}
          ${BT.f.input({ name: 'at', label: 'وقت المخالفة (بتوقيت الكويت)', type: 'datetime-local', required: true, value: fmt.kwInput(pre.alert ? pre.alert.created_at : null) })}
          ${BT.f.input({ name: 'reference', label: 'المرجع (رقم الطلب أو الشكوى)', optional: true })}
          ${BT.f.select({ name: 'cause', label: 'سبب خارج مسؤولية السائق', optional: true, placeholder: 'لا يوجد', options: causes.map(function (c) { return { v: String(c.id), t: api.name(c.name) }; }), hint: 'إن وُجد تُستبعد المخالفة فوراً ولا تُحسب عليه' })}
          <div class="full">${BT.f.textarea({ name: 'description', label: 'الوصف', required: true, rows: 2, value: pre.alert ? pre.alert.message : '' })}</div>
          <div class="full">${BT.f.upload({ name: 'evidence', label: 'دليل (صورة أو PDF)', optional: true, accept: 'image/*,application/pdf' })}</div></div>`,
        submitText: 'تسجيل',
        submit: function (f) {
          var up = f.evidence && f.evidence[0] ? api.upload(f.evidence[0]) : Promise.resolve(null);
          return up.then(function (file) {
            return api.post('/violations', {
              employee_id: A.picked('drv', f.drv), type_id: Number(f.type), occurred_at: fmt.kwIso(f.at), reference: f.reference || null,
              cause_id: f.cause ? Number(f.cause) : null, description: f.description, evidence_sha256: file ? file.sha256 : null, alert_id: pre.alert ? pre.alert.id : null
            });
          });
        },
        after: function (x) {
          BT.toast(x.status === 'excluded' ? 'سُجّلت واستُبعدت: السبب خارج مسؤولية السائق' : 'سُجّلت المخالفة وتنتظر المراجعة');
          if (A._violationsTable) A._violationsTable.refresh();
          if (pre.after) pre.after();
          A.refreshCounts();
        }
      });
    }, api.fail);
  };

  /* ---------- الأنواع وأسباب الاستبعاد (قوائم العميل) ---------- */
  function listEditor(el, o) {
    var rows = [];
    BT.on(el, 'click', '[data-edit]', function (e, b) { form(rows.find(function (x) { return String(x.id) === b.getAttribute('data-edit'); })); });
    BT.on(el, 'click', '[data-add]', function () { form(null); });
    function draw() {
      A.load(el, api.get(o.path), function (list) {
        var edit = api.can('violations.approve');
        rows = list;
        return h`<div class="card"><div class="card-h"><div><div class="card-t">${o.title}</div><div class="card-meta">${o.meta}</div></div>${edit ? h`<button type="button" class="btn btn-sm btn-primary ms-auto" data-add>${icon('plus', 14)} إضافة</button>` : ''}</div>
          ${BT.chart.table(o.columns, rows.map(function (x) { return o.row(x).concat([x.active ? BT.pill('فعال', 'g') : BT.pill('موقوف', 'n'), edit ? h`<button type="button" class="btn btn-sm btn-ghost" data-edit="${x.id}">${icon('pencil', 13)} تعديل</button>` : '']); }))}</div>`;
      }).catch(function () {});
    }
    function form(x) {
      A.formModal({
        title: x ? 'تعديل ' + api.name(x.name) : 'إضافة', icon: 'shield-alert', size: 'sm', done: 'تم الحفظ',
        body: h`<div class="form">${x ? '' : BT.f.input({ name: 'code', label: 'الرمز (حروف إنجليزية صغيرة)', required: true })}
          ${BT.f.input({ name: 'ar', label: 'الاسم بالعربية', required: true, value: x && x.name.ar })}${BT.f.input({ name: 'en', label: 'الاسم بالإنجليزية', required: true, value: x && x.name.en })}
          ${o.fields ? o.fields(x) : ''}${x ? BT.f.check({ name: 'active', label: 'فعال', checked: x.active }) : ''}</div>`,
        submit: function (f, dlg) {
          var body = Object.assign({ name: { ar: f.ar, en: f.en } }, o.body ? o.body(f, x) : {});
          if (x) return api.put(o.path + '/' + x.id, Object.assign(body, { active: dlg.form.querySelector('[name=active]').checked, version: x.version }));
          return api.post(o.path, Object.assign(body, { code: f.code }));
        },
        after: draw
      });
    }
    draw();
  }
  function typesPanel(el) {
    listEditor(el, {
      path: '/violations/types', title: 'أنواع المخالفات', meta: 'كل نوع تحت مصدر من المصادر الستة، وغرامته المعتادة (تُعدَّل عند الاعتماد). النوع الموقوف لا يُسجَّل ولا يفتحه النظام.',
      columns: ['النوع', 'المصدر', 'الغرامة المعتادة', 'الحالة', ''],
      row: function (t) { return [api.name(t.name), api.t('violation_source', t.source), t.amount == null ? '—' : fmt.kwd(Number(t.amount))]; },
      fields: function (t) {
        return h`${t ? '' : BT.f.select({ name: 'source', label: 'المصدر', required: true, options: SOURCES.map(function (s) { return { v: s, t: api.t('violation_source', s) }; }) })}${BT.f.money({ name: 'amount', label: 'الغرامة المعتادة', optional: true, value: t && t.amount })}`;
      },
      body: function (f, t) { return Object.assign({ amount: f.amount === '' || f.amount == null ? null : String(f.amount) }, t ? {} : { source: f.source }); }
    });
  }
  function causesPanel(el) {
    listEditor(el, {
      path: '/violations/causes', title: 'أسباب خارج مسؤولية السائق', meta: 'المخالفة المسجلة بسبب فعال منها تُستبعد فوراً (BR-10). أوقف السبب ليعود للمراجعة العادية.',
      columns: ['السبب', 'الحالة', ''],
      row: function (c) { return [api.name(c.name)]; }
    });
  }
})();
