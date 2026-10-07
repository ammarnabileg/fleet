/* =====================================================================
   app/pages/fuel.js — الوقود (#/fuel)  (BRD FR-FUL-01..05، UAT-03)
   التعبئات من التطبيق أو من فاتورة: السليمة تُعتمد وحدها، والمخالفة تنتظر المحاسب
   بسبب. الاستهلاك مقابل مرجع الطراز، والأسعار الرسمية بتاريخ سريانها.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;
  var TYPES = ['premium_91', 'super_95', 'ultra_98', 'diesel'];
  A.tone.fuel_status = { pending: 'o', approved: 'g', rejected: 'r' };

  function litres(v) { return h`<span class="num">${Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 })}</span> لتر`; }
  function flags(f) { return f.flags.length ? h`${f.flags.map(function (x) { return BT.pill(api.t('fuel_flag', x), 'o'); })}` : raw('<span class="muted fs-sm">سليمة</span>'); }
  function fileUrl(f, sha) { return api.url('/fuel/fills/' + f.id + '/files/' + sha); }

  BT.pages['fuel'] = function (p, q) {
    A.setTitle('الوقود');
    var v = A.view(), tab = ['consumption', 'prices', 'models'].indexOf(q.tab) >= 0 ? q.tab : 'fills';
    var tabs = [['fills', 'التعبئات'], ['consumption', 'الاستهلاك'], ['prices', 'الأسعار الرسمية'], ['models', 'مراجع الطرازات']];
    BT.render(v, h`${A.head('الوقود', 'كل تعبئة تُفحص: السعة، والسعر الرسمي، ونوع الوقود، والعداد. السليمة تُعتمد وتُسجَّل مصروفاً، والمخالفة تنتظر قرار المحاسب بسببه.',
        api.can('fuel.manage') ? A.btn('تعبئة من فاتورة', { icon: 'plus', cls: 'btn-primary', action: 'fuel-new' }) : '')}
      ${BT.tabs('fuel', tabs, tab, 'tabs-line')}
      ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="fuel" class="${t[0] === tab ? 'active' : ''}"><div id="fuel-${t[0]}"></div></div>`; })}`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      ({ fills: fillsPanel, consumption: consumptionPanel, prices: pricesPanel, models: modelsPanel })[t](document.getElementById('fuel-' + t), q);
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); });
    show(tab);
  };

  /* ---------- التعبئات ---------- */
  function fillsPanel(el, q) {
    var t = BT.table(el, {
      fetch: function (s) {
        var chip = { pending: { status: 'pending' }, approved: { status: 'approved' }, rejected: { status: 'rejected' }, flagged: { flagged: true } }[s.chip] || {};
        return api.get('/fuel/fills', Object.assign({ limit: s.limit, offset: s.offset }, chip));
      },
      chips: { value: q.chip || 'pending', all: 'الكل', options: [{ v: 'pending', t: 'بانتظار المراجعة' }, { v: 'approved', t: 'معتمدة' }, { v: 'rejected', t: 'مرفوضة' }, { v: 'flagged', t: 'فيها ملاحظة' }] },
      columns: [
        { key: 'number', label: 'التعبئة', render: function (f) { return h`<span class="num">#${f.number}</span><span class="sub">${fmt.dt(f.filled_at)}</span>`; } },
        { key: 'vehicle', label: 'السيارة', render: function (f) { return h`<span class="plate">${f.vehicle.plate_number}</span><span class="sub">${[f.vehicle.make, f.vehicle.model].filter(Boolean).join(' ')}</span>`; } },
        { key: 'driver', label: 'السائق', render: function (f) { return f.driver ? A.person(f.driver) : raw('<span class="muted">—</span>'); } },
        { key: 'litres', label: 'الكمية', num: true, render: function (f) { return h`${litres(f.litres)}<span class="sub">${api.t('fuel_type', f.fuel_type)}</span>`; } },
        { key: 'amount', label: 'المبلغ', num: true, render: function (f) { return h`${BT.amt(Number(f.amount))}${f.expected_amount ? h`<span class="sub">بالسعر الرسمي ${fmt.kwd(Number(f.expected_amount))}</span>` : ''}`; } },
        { key: 'flags', label: 'الفحص', render: flags },
        { key: 'status', label: 'الحالة', render: function (f) { return A.pill('fuel_status', f.status); } }
      ],
      rowClick: function (f) { view(f.id, function () { t.refresh(); A.refreshCounts(); }); },
      empty: { icon: 'fuel', title: 'لا توجد تعبئات هنا' }
    });
    A._fuelTable = t;
  }

  function view(id, done) {
    api.get('/fuel/fills/' + id).then(function (f) {
      var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
      function decide(approve) {
        return function (dlg) {
          A.confirmRun({
            title: approve ? 'اعتماد التعبئة' : 'رفض التعبئة', tone: approve ? 'success' : 'danger', confirmText: approve ? 'اعتماد' : 'رفض',
            message: approve ? (f.flags.length ? 'التعبئة فيها ملاحظة: الاعتماد بسبب يُسجَّل معها، وتُسجَّل مصروف وقود.' : 'تُسجَّل مصروف وقود.') : 'يُبلَّغ السائق بالرفض وسببه.',
            reason: { label: approve ? 'سبب الاعتماد' : 'سبب الرفض', required: true },
            run: function (reason) { return api.post('/fuel/fills/' + f.id + '/' + (approve ? 'approve' : 'reject'), { note: reason }); },
            done: approve ? 'اعتُمدت التعبئة' : 'رُفضت التعبئة', after: function () { dlg.close(); if (done) done(); }
          });
        };
      }
      if (f.status === 'pending' && api.can('fuel.approve')) {
        btns.push({ label: 'رفض', cls: 'btn-ghost', icon: 'x', close: false, onClick: decide(false) });
        btns.push({ label: 'اعتماد بسبب', cls: 'btn-primary', icon: 'check', close: false, onClick: decide(true) });
      }
      var photos = [{ src: fileUrl(f, f.invoice_sha256), caption: 'الفاتورة' }].concat(f.odometer_sha256 ? [{ src: fileUrl(f, f.odometer_sha256), caption: 'العداد ' + fmt.km(f.odometer_km) }] : []);
      BT.drawer.open({
        title: h`تعبئة <span class="num">#${f.number}</span> · ${BT.amt(Number(f.amount))}`, subtitle: f.vehicle.plate_number + ' · ' + fmt.dt(f.filled_at), icon: 'fuel', size: 'lg',
        body: h`${f.flags.length && f.status === 'pending' ? h`<div class="banner warn mb-12" data-fuel-flags>${icon('triangle-alert', 16)}<div>لم تُعتمد وحدها: ${f.flags.map(function (x) { return api.t('fuel_flag', x); }).join('، ')}</div></div>` : ''}
          <div class="mb-12">${A.thumbs(photos)}</div>
          ${BT.kv([
            ['الحالة', A.pill('fuel_status', f.status)],
            ['السائق', f.driver ? A.person(f.driver) : raw('<span class="muted">لم تكن السيارة مع أحد</span>')],
            ['الكمية', h`${litres(f.litres)} · ${api.t('fuel_type', f.fuel_type)}`],
            ['المبلغ', h`${BT.amt(Number(f.amount))}${f.price ? h` <span class="muted fs-sm">· السعر الرسمي ${fmt.kwd(Number(f.price))} للتر = ${fmt.kwd(Number(f.expected_amount))}</span>` : raw(' <span class="muted fs-sm">· لا سعر رسمي لذلك اليوم</span>')}`],
            ['العداد', h`<span class="num">${fmt.km(f.odometer_km)}</span> كم`],
            f.litres_per_100km ? ['الاستهلاك', h`<span class="num">${f.litres_per_100km}</span> لتر/100 كم على <span class="num">${fmt.int(f.km_since)}</span> كم منذ التعبئة السابقة`] : null,
            f.station ? ['المحطة', f.station] : null,
            ['المصدر', f.source === 'app' ? 'تطبيق السائق' : 'المكتب' + (f.created_by ? ' · ' + f.created_by : '')],
            f.decided_at ? ['القرار', (f.decided_by || 'الفحص الآلي') + ' · ' + fmt.dt(f.decided_at) + (f.decision_note ? ' · ' + f.decision_note : '')] : null
          ].filter(Boolean))}`,
        buttons: btns
      });
    }, api.fail);
  }

  /* ---------- تعبئة من فاتورة (المكتب) ---------- */
  function allVehicles(offset, acc) {
    offset = offset || 0; acc = acc || [];
    return api.get('/vehicles', { limit: 200, offset: offset }).then(function (rows) {
      acc = acc.concat(rows);
      return rows.length === 200 && acc.length < 5000 ? allVehicles(offset + 200, acc) : acc;
    });
  }
  BT.actions['fuel-new'] = function () {
    allVehicles().then(function (vehicles) {
      A.formModal({
        title: 'تعبئة من فاتورة', subtitle: 'الوقت كما في الفاتورة: منه يُحدد السائق', icon: 'fuel', size: 'lg', done: false,
        body: h`<div class="form-grid">
          <div class="full">${A.picker({ name: 'vehicle', label: 'السيارة', required: true, items: vehicles.map(function (x) { return { id: x.id, label: A.vehicleLabel(x) }; }) })}</div>
          ${BT.f.input({ name: 'at', label: 'تاريخ ووقت التعبئة (بتوقيت الكويت)', type: 'datetime-local', required: true })}
          ${BT.f.select({ name: 'fuel_type', label: 'نوع الوقود', required: true, placeholder: false, options: TYPES.map(function (k) { return { v: k, t: api.t('fuel_type', k) }; }), value: 'super_95' })}
          ${BT.f.input({ name: 'litres', label: 'اللترات', required: true, num: true })}
          ${BT.f.money({ name: 'amount', label: 'المبلغ', required: true })}
          ${BT.f.input({ name: 'km', label: 'قراءة العداد', required: true, num: true })}
          ${BT.f.input({ name: 'station', label: 'المحطة', optional: true })}
          ${BT.f.upload({ name: 'invoice', label: 'صورة الفاتورة', required: true, accept: 'image/*' })}
          ${BT.f.upload({ name: 'odo', label: 'صورة العداد', optional: true, accept: 'image/*' })}</div>`,
        submitText: 'تسجيل',
        submit: function (f, dlg) {
          var at = dlg.form.querySelector('[name=at]').value;
          return Promise.all([api.upload(f.invoice[0]), f.odo && f.odo[0] ? api.upload(f.odo[0]) : Promise.resolve(null)]).then(function (up) {
            return api.post('/fuel/fills', {
              vehicle_id: A.picked('vehicle', f.vehicle), filled_at: fmt.kwIso(at), fuel_type: f.fuel_type, litres: String(f.litres), amount: String(f.amount),
              odometer_km: Math.round(Number(f.km)), station: f.station || null, invoice_sha256: up[0].sha256, odometer_sha256: up[1] ? up[1].sha256 : null
            });
          });
        },
        after: function (fill) {
          BT.toast(fill.status === 'approved' ? 'سُجّلت التعبئة واعتُمدت' : 'سُجّلت التعبئة وتنتظر المراجعة', { type: fill.status === 'approved' ? undefined : 'warning', sub: fill.flags.map(function (x) { return api.t('fuel_flag', x); }).join('، ') });
          if (A._fuelTable) A._fuelTable.refresh();
          A.refreshCounts();
          view(fill.id, function () { if (A._fuelTable) A._fuelTable.refresh(); });
        }
      });
    }, api.fail);
  };

  /* ---------- الاستهلاك (FR-FUL-04) ---------- */
  function consumptionPanel(el) {
    var to = BT.date.today(), from = BT.date.add(to, -29);
    A.load(el, api.get('/fuel/consumption', { date_from: from, date_to: to }), function (rows) {
      setTimeout(function () {
        BT.table(el.querySelector('[data-cons]'), {
          rows: rows, pageSize: 25,
          search: { placeholder: 'اللوحة…', text: function (r) { return r.vehicle.plate_number; } },
          columns: [
            { key: 'vehicle', label: 'السيارة', sort: function (r) { return r.vehicle.plate_number; }, render: function (r) { return h`<span class="plate">${r.vehicle.plate_number}</span><span class="sub">${[r.vehicle.make, r.vehicle.model].filter(Boolean).join(' ')}</span>`; } },
            { key: 'fills', label: 'تعبئات', num: true },
            { key: 'litres', label: 'اللترات', num: true, sort: function (r) { return Number(r.litres); }, render: function (r) { return litres(r.litres); } },
            { key: 'amount', label: 'المبلغ', num: true, sort: function (r) { return Number(r.amount); }, render: function (r) { return BT.amt(Number(r.amount)); } },
            { key: 'km', label: 'كم', num: true, render: function (r) { return fmt.int(r.km); } },
            { key: 'rate', label: 'لتر/100 كم', num: true, sort: function (r) { return Number(r.litres_per_100km || 0); }, render: function (r) { return r.litres_per_100km == null ? '—' : h`<b class="num">${r.litres_per_100km}</b>${r.reference ? h`<span class="sub">المرجع ${r.reference}</span>` : ''}`; } },
            { key: 'over', label: '', sort: function (r) { return Number(r.over_percent || -1000); }, render: function (r) { return r.over_percent == null ? '' : BT.pill((Number(r.over_percent) > 0 ? '+' : '') + r.over_percent + '%', r.over ? 'r' : Number(r.over_percent) > 0 ? 'o' : 'g'); } }
          ],
          empty: { icon: 'fuel', title: 'لا تعبئات معتمدة في آخر 30 يوماً' }
        });
      });
      return h`<div class="card"><div class="card-h"><div><div class="card-t">آخر 30 يوماً</div><div class="card-meta">اللترات بعد أول تعبئة على المسافة بين أول تعبئة وآخرها (كل تعبئة تملأ الخزان)، مقابل مرجع الطراز</div></div></div><div data-cons></div></div>`;
    }).catch(function () {});
  }

  /* ---------- الأسعار الرسمية (FR-FUL-05) ---------- */
  function pricesPanel(el) {
    function draw() {
      A.load(el, api.get('/fuel/prices'), function (d) {
        var manage = api.can('fuel.manage');
        setTimeout(function () {
          var b = el.querySelector('[data-price-add]');
          if (b) b.onclick = function () {
            A.formModal({
              title: 'سعر رسمي جديد', icon: 'fuel', size: 'sm', done: 'حُفظ السعر',
              body: h`<div class="form">${BT.f.select({ name: 'fuel_type', label: 'الوقود', required: true, placeholder: false, options: TYPES.map(function (k) { return { v: k, t: api.t('fuel_type', k) }; }) })}
                ${BT.f.money({ name: 'price', label: 'السعر للتر', required: true })}
                ${BT.f.input({ name: 'from', label: 'يسري من', type: 'date', required: true, value: BT.date.today() })}</div>`,
              submit: function (v) { return api.post('/fuel/prices', { fuel_type: v.fuel_type, price: String(v.price), effective_from: v.from }); },
              after: draw
            });
          };
        });
        return h`<div class="kpis">${TYPES.map(function (k) { return BT.kpi({ label: api.t('fuel_type', k), value: d.current[k] ? fmt.kwd(Number(d.current[k])) : '—', sub: d.current[k] ? BT.config.currency + ' للتر' : 'لم يُحدد', dot: d.current[k] ? 'g' : 'o' }); })}</div>
          <div class="card mt-16"><div class="card-h"><div class="card-t">السجل</div>${manage ? h`<button type="button" class="btn btn-sm btn-primary ms-auto" data-price-add>${icon('plus', 14)} سعر جديد</button>` : ''}</div>
          ${d.history.length ? BT.chart.table(['الوقود', 'السعر', 'يسري من', 'بواسطة'], d.history.map(function (x) { return [api.t('fuel_type', x.fuel_type), fmt.kwd(Number(x.price)), fmt.date(x.effective_from), x.created_by || '—']; })) : BT.empty('fuel', 'لم تُسجَّل أسعار بعد', 'بدون سعر رسمي تنتظر كل تعبئة المراجعة')}</div>`;
      }).catch(function () {});
    }
    draw();
  }

  /* ---------- مراجع الطرازات (FR-FUL-02، FR-FUL-04) ---------- */
  function modelsPanel(el) {
    function form(m) {
      A.formModal({
        title: m ? 'تعديل مرجع ' + m.make + ' ' + m.model : 'مرجع طراز جديد', icon: 'car', done: 'حُفظ المرجع',
        body: h`<div class="form-grid">${BT.f.input({ name: 'make', label: 'الصانع', required: true, value: m && m.make, hint: 'كما في ملف السيارة' })}${BT.f.input({ name: 'model', label: 'الطراز', required: true, value: m && m.model })}
          ${BT.f.input({ name: 'tank', label: 'سعة الخزان (لتر)', required: true, num: true, value: m && m.tank_litres })}${BT.f.input({ name: 'rate', label: 'المرجع (لتر/100 كم)', required: true, num: true, value: m && m.litres_per_100km })}
          <div class="full"><label class="fs-sm">الوقود المسموح</label><div class="flex gap-8 mt-4" style="flex-wrap:wrap">${TYPES.map(function (k) { return BT.f.check({ name: 'types', value: k, label: api.t('fuel_type', k), checked: m ? m.fuel_types.indexOf(k) >= 0 : k === 'super_95' }); })}</div></div></div>`,
        submit: function (v, dlg) {
          var types = BT.$$('[name=types]:checked', dlg.form).map(function (x) { return x.value; });
          var body = { make: v.make, model: v.model, tank_litres: String(v.tank), litres_per_100km: String(v.rate), fuel_types: types };
          return m ? api.put('/fuel/models/' + m.id, Object.assign(body, { version: m.version })) : api.post('/fuel/models', body);
        },
        after: draw
      });
    }
    function draw() {
      A.load(el, api.get('/fuel/models'), function (rows) {
        var manage = api.can('fuel.manage');
        setTimeout(function () {
          BT.table(el.querySelector('[data-models]'), {
            rows: rows, pageSize: 25,
            columns: [
              { key: 'model', label: 'الطراز', render: function (m) { return m.make + ' ' + m.model; } },
              { key: 'tank', label: 'الخزان', num: true, render: function (m) { return litres(m.tank_litres); } },
              { key: 'types', label: 'الوقود', render: function (m) { return m.fuel_types.map(function (k) { return api.t('fuel_type', k); }).join('، '); } },
              { key: 'rate', label: 'لتر/100 كم', num: true, render: function (m) { return h`<span class="num">${m.litres_per_100km}</span>`; } }
            ],
            rowClick: manage ? form : null,
            empty: { icon: 'car', title: 'لا مراجع بعد', text: 'بدون مرجع لطراز السيارة تنتظر تعبئاتها المراجعة' }
          });
          var b = el.querySelector('[data-model-add]');
          if (b) b.onclick = function () { form(null); };
        });
        return h`<div class="card"><div class="card-h"><div><div class="card-t">مراجع الطرازات</div><div class="card-meta">الصانع والطراز كما في ملف السيارة؛ منها السعة والوقود المسموح ومرجع الاستهلاك</div></div>${manage ? h`<button type="button" class="btn btn-sm btn-primary ms-auto" data-model-add>${icon('plus', 14)} مرجع جديد</button>` : ''}</div><div data-models></div></div>`;
      }).catch(function () {});
    }
    draw();
  }
})();
