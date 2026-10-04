/* =====================================================================
   app/pages/fines.js — المخالفات المرورية: التسجيل بوقت المخالفة (والنظام يحدد
   السائق من سجل العهدة)، ثم القرار: خصم من السائق بأقساط، أو على الشركة، أو
   إلغاء؛ ودفع المخالفة للمرور يُسجّل مستقلاً.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A, M = BT.mnt;

  var TONE = { open: 'o', charged: 'r', company: 'b', cancelled: 'n' };
  var CHIPS = {
    open: { status: 'open' }, no_driver: { no_driver: true }, charged: { status: 'charged' }, company: { status: 'company' },
    unpaid: { unpaid: true }, cancelled: { status: 'cancelled' }
  };
  function upload(file) { return api.upload(file).then(function (f) { return f.sha256; }); }
  function status(f) {
    return h`${BT.pill(api.t('fine_status', f.status), TONE[f.status])}${f.status !== 'cancelled' && !f.paid_at ? h` ${BT.pill('غير مدفوعة للمرور', 'n')}` : ''}`;
  }
  function nextMonth() { var p = BT.config.today.split('-'), y = +p[0], m = +p[1] + 1; if (m > 12) { m = 1; y++; } return y + '-' + (m < 10 ? '0' : '') + m; }

  BT.pages['fines'] = function (p, q) {
    A.setTitle('المخالفات المرورية');
    var v = A.view();
    BT.render(v, h`${A.head('المخالفات المرورية', 'سجّل المخالفة بوقتها كما في المخالفة: النظام يحدد السائق الذي كانت معه السيارة من سجل العهدة',
        api.can('fines.manage') ? A.btn('تسجيل مخالفة', { icon: 'plus', cls: 'btn-primary', action: 'fine-new' }) : '')}
      <div class="card"><div data-t></div></div>`);
    var t = BT.table(v.querySelector('[data-t]'), {
      fetch: function (s) { return api.get('/fines', Object.assign({ limit: s.limit, offset: s.offset }, CHIPS[s.chip] || {})); },
      chips: { value: q.chip || 'open', all: 'الكل', options: [
        { v: 'open', t: 'بانتظار القرار' }, { v: 'no_driver', t: 'بلا سائق' }, { v: 'charged', t: 'مخصومة' }, { v: 'company', t: 'على الشركة' },
        { v: 'unpaid', t: 'غير مدفوعة للمرور' }, { v: 'cancelled', t: 'ملغاة' }
      ] },
      columns: [
        { key: 'number', label: 'المخالفة', render: function (f) { return h`<span class="num">#${f.number}</span><span class="sub">${fmt.dt(f.occurred_at)}</span>`; } },
        { key: 'vehicle', label: 'السيارة', render: function (f) { return M.vehicle(f.vehicle); } },
        { key: 'driver', label: 'السائق وقت المخالفة', render: function (f) { return f.driver ? A.person(f.driver) : raw('<span class="t-danger">لا أحد</span>'); } },
        { key: 'violation', label: 'المخالفة', render: function (f) { return h`<span style="white-space:normal">${f.violation}</span>${f.reference_no ? h`<span class="sub num">${f.reference_no}</span>` : ''}`; } },
        { key: 'amount', label: 'المبلغ', num: true, render: function (f) { return BT.amt(Number(f.amount)); } },
        { key: 'status', label: 'الحالة', render: status }
      ],
      rowClick: function (f) { view(f.id, function () { t.refresh(); A.refreshCounts(); }); },
      empty: { icon: 'file-warning', title: 'لا توجد مخالفات هنا' }
    });
    A._finesTable = t;
  };
  BT.actions['fine-new'] = function () { newFine(null, function () { if (A._finesTable) A._finesTable.refresh(); }); };

  function allVehicles(offset, acc) {
    offset = offset || 0; acc = acc || [];
    return api.get('/vehicles', { limit: 200, offset: offset }).then(function (rows) {
      acc = acc.concat(rows);
      return rows.length === 200 && acc.length < 5000 ? allVehicles(offset + 200, acc) : acc;
    });
  }

  function newFine(vehicle, done) {
    (vehicle ? Promise.resolve([vehicle]) : allVehicles()).then(function (vehicles) {
      A.formModal({
        title: 'تسجيل مخالفة مرورية', subtitle: 'الوقت كما في المخالفة: منه يُحدد السائق', icon: 'file-warning', size: 'lg',
        body: h`<div class="form-grid">
          <div class="full">${A.picker({ name: 'vehicle', label: 'السيارة', required: true, items: vehicles.map(function (x) { return { id: x.id, label: A.vehicleLabel(x) }; }), value: vehicle && vehicle.id })}</div>
          ${BT.f.input({ name: 'at', label: 'تاريخ ووقت المخالفة', type: 'datetime-local', required: true })}
          ${BT.f.money({ name: 'amount', label: 'المبلغ', required: true })}
          ${BT.f.input({ name: 'violation', label: 'المخالفة', required: true, full: true, placeholder: 'تجاوز السرعة 120 في 80' })}
          ${BT.f.input({ name: 'ref', label: 'رقم المخالفة', optional: true, hint: 'يُسجّل مرة واحدة فقط' })}
          ${BT.f.input({ name: 'place', label: 'الموقع', optional: true })}
          ${BT.f.upload({ name: 'file', label: 'صورة أو ملف المخالفة', optional: true, full: true, accept: 'image/*,application/pdf' })}
          ${BT.f.textarea({ name: 'notes', label: 'ملاحظات', optional: true, full: true, rows: 2 })}</div>`,
        submitText: 'تسجيل', done: false,
        submit: function (f, dlg) {
          var at = dlg.form.querySelector('[name=at]').value;
          return (f.file && f.file[0] ? upload(f.file[0]) : Promise.resolve(null)).then(function (sha) {
            return api.post('/fines', {
              vehicle_id: A.picked('vehicle', f.vehicle), occurred_at: new Date(at).toISOString(), violation: f.violation,
              amount: String(f.amount), reference_no: f.ref || null, location_text: f.place || null, file_sha256: sha, notes: f.notes || null
            });
          });
        },
        after: function (fine) {
          BT.toast('سُجّلت المخالفة', { sub: fine.driver ? 'السائق وقت المخالفة: ' + api.name(fine.driver.name) : 'لم تكن السيارة مسلّمة لأحد في ذلك الوقت', type: fine.driver ? undefined : 'warning', timeout: 7000 });
          if (done) done();
          view(fine.id, done);
          A.refreshCounts();
        }
      });
    }, api.fail).catch(function () {});
  }
  A.newFine = newFine;

  function view(id, done) {
    api.get('/fines/' + id).then(function (f) {
      var d = f.deduction, btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
      function act(fn) { return function (dlg) { fn(f, function () { dlg.close(); if (done) done(); view(id, done); }); }; }
      if (f.status !== 'cancelled' && api.can('fines.manage') && !(d && d.status === 'approved')) btns.push({ label: 'إلغاء', cls: 'btn-ghost', icon: 'ban', close: false, onClick: act(cancel) });
      if (f.status !== 'cancelled' && !f.paid_at && api.can('finance.create')) btns.push({ label: 'دُفعت للمرور', cls: 'btn-outline', icon: 'banknote', close: false, onClick: act(paid) });
      if (f.can_decide && api.can('fines.manage')) btns.push({ label: 'على الشركة', cls: 'btn-outline', icon: 'building-2', close: false, onClick: act(company) });
      if (f.can_decide && f.driver && api.can('deductions.manage')) btns.push({ label: 'خصم من السائق', cls: 'btn-primary', icon: 'minus-circle', close: false, onClick: act(charge) });
      BT.drawer.open({
        title: h`مخالفة <span class="num">#${f.number}</span> · ${BT.amt(Number(f.amount))}`, subtitle: f.vehicle.plate_number + ' · ' + fmt.dt(f.occurred_at), icon: 'file-warning', size: 'lg',
        body: h`${!f.driver && f.status === 'open' ? h`<div class="banner warn mb-12">${icon('triangle-alert', 16)}<div>لم تكن السيارة مسلّمة لأي سائق في ذلك الوقت: لا يمكن الخصم. راجع «من كان يقود؟» في ملف السيارة، أو اجعلها على الشركة.</div></div>` : ''}
          ${BT.kv([
            ['الحالة', status(f)],
            ['السيارة', M.vehicleLine(f.vehicle)],
            ['السائق وقت المخالفة', f.driver ? A.person(f.driver) : raw('<span class="muted">لا أحد</span>')],
            ['الوقت', fmt.dt(f.occurred_at)],
            ['المخالفة', h`<span style="white-space:normal">${f.violation}</span>`],
            f.reference_no ? ['رقم المخالفة', h`<span class="num">${f.reference_no}</span>`] : null,
            f.location_text ? ['الموقع', f.location_text] : null,
            ['المبلغ', BT.amt(Number(f.amount))],
            f.has_file ? ['الملف', h`<a href="${api.url('/fines/' + f.id + '/file')}" target="_blank" rel="noopener">${icon('file-text', 14)} فتح</a>`] : null,
            f.notes ? ['ملاحظات', h`<span style="white-space:normal">${f.notes}</span>`] : null,
            f.decided_at ? ['القرار', (f.decided_by || '') + ' · ' + fmt.dt(f.decided_at) + (f.decision_note ? ' · ' + f.decision_note : '')] : null,
            f.paid_at ? ['الدفع للمرور', (f.paid_by || '') + ' · ' + fmt.dt(f.paid_at) + (f.payment_ref ? ' · ' + f.payment_ref : '')] : null,
            f.cancel_reason ? ['سبب الإلغاء', f.cancel_reason] : null,
            ['التسجيل', (f.created_by || '') + ' · ' + fmt.dt(f.created_at)]
          ].filter(Boolean))}
          ${d ? h`<div class="section-t mt-16">الخصم ${d.status === 'cancelled' ? BT.pill('ملغى: يمكن البت من جديد', 'n') : ''}</div>${BT.acc.schedule(d)}` : ''}`,
        buttons: btns
      });
    }, api.fail);
  }
  A.fine = view;

  function charge(f, done) {
    A.formModal({
      title: 'خصم المخالفة من السائق', subtitle: api.name(f.driver.name) + ' · ' + fmt.money(f.amount) + ' د.ك', icon: 'minus-circle', size: 'sm',
      body: h`<div class="form">${BT.f.input({ name: 'inst', label: 'عدد الأقساط', required: true, num: true, value: '1' })}
        ${BT.f.input({ name: 'start', label: 'شهر البدء', type: 'month', required: true, value: nextMonth() })}
        ${BT.f.input({ name: 'reason', label: 'السبب في كشف الراتب', optional: true, hint: 'افتراضياً: #' + f.number + ' ' + f.violation })}</div>
        <div class="hint mt-8">يُنشأ خصم معتمد يراه السائق في التطبيق، ويطبقه الراتب بحد الخصم الشهري.</div>`,
      submitText: 'اعتماد الخصم', done: 'اعتُمد الخصم',
      submit: function (v) { return api.post('/fines/' + f.id + '/charge', { installments: Math.round(v.inst), start_month: v.start + '-01', reason: v.reason || null }); },
      after: done
    });
  }
  function company(f, done) {
    A.confirmRun({ title: 'المخالفة على الشركة', message: 'لا يُخصم شيء من السائق.', confirmText: 'على الشركة', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/fines/' + f.id + '/company', { reason: reason }); }, done: 'سُجّل القرار', after: done });
  }
  function cancel(f, done) {
    A.confirmRun({ title: 'إلغاء المخالفة', message: 'لإدخال خاطئ فقط. يصبح رقم المخالفة متاحاً للتسجيل من جديد.', tone: 'danger', confirmText: 'إلغاء المخالفة', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/fines/' + f.id + '/cancel', { reason: reason }); }, done: 'أُلغيت المخالفة', after: done });
  }
  function paid(f, done) {
    A.formModal({ title: 'دفع المخالفة للمرور', icon: 'banknote', size: 'sm', body: h`<div class="form">${BT.f.input({ name: 'ref', label: 'مرجع الدفع', optional: true })}</div>`, submitText: 'تم الدفع', done: 'سُجّل الدفع',
      submit: function (v) { return api.post('/fines/' + f.id + '/paid', { payment_ref: v.ref || null }); }, after: done });
  }

  /* ---------- المخالفات في ملف السيارة ---------- */
  A.vehicleFines = function (el, vehicle) {
    A.load(el, api.get('/fines', { vehicle_id: vehicle.id, limit: 20 }), function (rows) {
      return h`${rows.length ? h`<div class="list">${rows.map(function (f) {
        return h`<button type="button" class="li" data-fine="${f.id}" style="width:100%;text-align:start"><span class="li-ic o">${icon('file-warning', 16)}</span><div class="li-main"><div class="li-t"><span class="num">#${f.number}</span> ${f.violation} · ${fmt.money(f.amount)}</div><div class="li-d">${fmt.dt(f.occurred_at)} · ${f.driver ? api.name(f.driver.name) : 'بلا سائق'}</div></div>${BT.pill(api.t('fine_status', f.status), TONE[f.status])}</button>`;
      })}</div>` : BT.empty('circle-check', 'لا توجد مخالفات', '')}
        ${api.can('fines.manage') ? h`<div class="mt-12"><button type="button" class="btn btn-sm btn-soft" data-fine-new>${icon('plus', 14)} تسجيل مخالفة</button></div>` : ''}`;
    }).then(function () {
      var refresh = function () { A.vehicleFines(el, vehicle); };
      if (!el._finesWired) { el._finesWired = true; BT.on(el, 'click', '[data-fine]', function (e, b) { view(b.getAttribute('data-fine'), refresh); }); }
      var b = el.querySelector('[data-fine-new]');
      if (b) b.onclick = function () { newFine(vehicle, refresh); };
    }).catch(function () {});
  };
})();
