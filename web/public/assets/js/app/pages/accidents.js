/* =====================================================================
   app/pages/accidents.js — الحوادث: البلاغ (من التطبيق أو المكتب)، محضر الشرطة،
   الإحالة لمركز لتقدير الأضرار واعتماده، المسؤولية والخصم بالأقساط، الإصلاح
   وتكلفته الفعلية مقابل التقدير؛ وشاشة الخصومات التي يطبقها الراتب.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A, M = BT.mnt, C = BT.acc;

  function fileUrl(id) { return function (sha) { return api.url('/accidents/' + id + '/files/' + sha); }; }
  function upload(file) { return api.upload(file).then(function (f) { return f.sha256; }); }
  function uploadAll(files) { return Promise.all(Array.prototype.map.call(files || [], upload)); }
  function refreshAll() { A.router.refresh(); A.refreshCounts(); }
  var CHIPS = {
    reported: { stage: 'reported' },
    estimate: { stage: 'awaiting_estimate,estimate_pending,estimate_rejected' },
    outcome: { stage: 'awaiting_outcome' },
    police: { no_police_report: true },
    recorded: { stage: 'outcome_recorded' },
    closed: { status: 'closed,cancelled' }
  };

  /* ================= القائمة ================= */
  BT.pages['accidents'] = function (p, q) {
    A.setTitle('الحوادث');
    var v = A.view();
    BT.render(v, h`${A.head('الحوادث', 'السائق المسؤول من سجل التسليم وقت الحادث؛ لا تُسجّل المسؤولية دون محضر الشرطة، ولا يُخصم قبل اعتماد تقدير الأضرار',
        h`${api.can('deductions.view') ? A.btn('الخصومات', { icon: 'minus-circle', cls: 'btn-outline', action: 'acc-deductions' }) : ''}${api.can('accidents.create') ? A.btn('تسجيل حادث', { icon: 'plus', cls: 'btn-primary', action: 'acc-new' }) : ''}`)}
      <div class="card"><div data-t></div></div>`);
    BT.table(v.querySelector('[data-t]'), {
      fetch: function (s) { return api.get('/accidents', Object.assign({ limit: s.limit, offset: s.offset }, CHIPS[s.chip] || { status: 'open' })); },
      chips: { value: q.chip || '', all: 'المفتوحة', options: [
        { v: 'reported', t: 'بانتظار الإحالة' }, { v: 'estimate', t: 'التقدير' }, { v: 'outcome', t: 'بانتظار المسؤولية' },
        { v: 'police', t: 'بلا محضر شرطة' }, { v: 'recorded', t: 'المسؤولية محددة' }, { v: 'closed', t: 'المغلقة والملغاة' }
      ] },
      columns: [
        { key: 'number', label: 'الحادث', render: function (a) { return h`<span class="num">#${a.number}</span><span class="sub">${fmt.dt(a.occurred_at)}</span>`; } },
        { key: 'vehicle', label: 'السيارة', render: function (a) { return M.vehicle(a.vehicle); } },
        { key: 'driver', label: 'السائق المسؤول', render: function (a) { return a.driver ? A.person(a.driver) : raw('<span class="muted">لا أحد وقت الحادث</span>'); } },
        { key: 'stage', label: 'المرحلة', render: function (a) { return h`${C.stage(a.stage)}${a.status === 'open' && !a.has_police_report ? h` ${C.police(a)}` : ''}${a.injuries ? h` ${BT.pill('إصابات', 'r')}` : ''}`; } },
        { key: 'estimate_total', label: 'التقدير', num: true, render: function (a) { return a.estimate_total != null ? BT.amt(Number(a.estimate_total)) : '—'; } },
        { key: 'deduction_total', label: 'الخصم', num: true, render: function (a) { return a.deduction_total != null ? BT.amt(Number(a.deduction_total)) : (a.liability ? C.liability(a) : '—'); } }
      ],
      rowClick: function (a) { A.go('accidents/' + a.id); },
      empty: { icon: 'shield-alert', title: 'لا توجد حوادث هنا' }
    });
  };
  BT.actions['acc-new'] = function () { newAccident(); };
  BT.actions['acc-deductions'] = function () { A.go('deductions'); };

  /* كل السيارات ضمن النطاق، 200 في كل طلب */
  function allVehicles(offset, acc) {
    offset = offset || 0; acc = acc || [];
    return api.get('/vehicles', { limit: 200, offset: offset }).then(function (rows) {
      acc = acc.concat(rows);
      return rows.length === 200 && acc.length < 5000 ? allVehicles(offset + 200, acc) : acc;
    });
  }

  /* ---------- تسجيل حادث من المكتب ---------- */
  function newAccident(vehicle) {
    (vehicle ? Promise.resolve([vehicle]) : allVehicles()).then(function (vehicles) {
      A.formModal({
        title: 'تسجيل حادث', subtitle: 'يُحدد السائق المسؤول تلقائياً من سجل التسليم في وقت الحادث', icon: 'shield-alert', size: 'lg',
        body: h`<div class="form-grid">
          <div class="full">${A.picker({ name: 'vehicle', label: 'السيارة', required: true, items: vehicles.map(function (x) { return { id: x.id, label: A.vehicleLabel(x) }; }), value: vehicle && vehicle.id })}</div>
          ${BT.f.input({ name: 'at', label: 'وقت الحادث', type: 'datetime-local', optional: true, hint: 'اتركه فارغاً إن كان الآن' })}
          ${BT.f.input({ name: 'place', label: 'الموقع', optional: true })}
          ${BT.f.textarea({ name: 'desc', label: 'الوصف', required: true, full: true, rows: 3 })}
          ${BT.f.textarea({ name: 'other', label: 'الطرف الآخر (السيارة، السائق، التأمين)', optional: true, full: true, rows: 2 })}
          <div class="full">${BT.f.switch({ name: 'injuries', label: 'توجد إصابات' })}</div>
          ${BT.f.textarea({ name: 'inj', label: 'تفاصيل الإصابات', optional: true, full: true, rows: 2 })}
          ${BT.f.upload({ name: 'ph', label: 'صور حالة السيارة', optional: true, multiple: true, full: true, accept: 'image/*', accept_label: 'صور فقط · حتى 12 صورة' })}
          ${BT.f.upload({ name: 'police', label: 'محضر الشرطة', optional: true, accept: 'image/*,application/pdf', hint: 'يمكن إرفاقه لاحقاً' })}
          ${BT.f.input({ name: 'pno', label: 'رقم المحضر', optional: true })}</div>`,
        submitText: 'تسجيل الحادث', done: 'سُجّل الحادث',
        submit: function (f, dlg) {
          var vid = A.picked('vehicle', f.vehicle);
          var at = dlg.form.querySelector('[name=at]').value;
          var injuries = dlg.form.querySelector('[name=injuries]').checked;
          return Promise.all([uploadAll(f.ph), f.police && f.police[0] ? upload(f.police[0]) : Promise.resolve(null)]).then(function (up) {
            return api.post('/accidents', {
              vehicle_id: vid, occurred_at: at ? new Date(at).toISOString() : null, location_text: f.place || null, description: f.desc,
              other_party: f.other || null, injuries: injuries, injuries_note: f.inj || null, photos: up[0], police_report: up[1], police_report_no: f.pno || null
            });
          });
        },
        after: function (a) { A.go('accidents/' + a.id); A.refreshCounts(); }
      });
    }, api.fail).catch(function () {});
  }
  A.newAccident = newAccident;

  /* ================= حادث واحد ================= */
  BT.pages['accidents/:id'] = function (p) {
    A.setTitle('حادث', [['الحوادث', 'accidents'], ['حادث']]);
    var v = A.view();
    A.load(v, api.get('/accidents/' + p.id), function (a) {
      A._acc = a;
      A.setTitle('حادث #' + a.number, [['الحوادث', 'accidents'], ['#' + a.number]]);
      var open = a.status === 'open', acts = [];
      if (open && !a.liability && api.can('accidents.create')) acts.push(A.btn(a.has_police_report ? 'استبدال المحضر' : 'إرفاق محضر الشرطة', { icon: 'file-up', cls: a.has_police_report ? 'btn-ghost' : 'btn-outline', action: 'acc-police' }));
      if (open && ['none', 'rejected'].indexOf(a.estimate_status) > -1 && api.can('accidents.update')) acts.push(A.btn(a.center ? 'تغيير المركز' : 'إحالة لمركز', { icon: 'send', cls: a.center ? 'btn-outline' : 'btn-primary', action: 'acc-refer' }));
      if (open && a.estimate_status === 'approved' && !a.repair && api.can('accidents.update')) acts.push(A.btn('إرسال للإصلاح', { icon: 'wrench', cls: 'btn-outline', action: 'acc-repair' }));
      if (open && !a.liability && api.can('accidents.approve')) acts.push(A.btn('تحديد المسؤولية', { icon: 'scale', cls: a.stage === 'awaiting_outcome' ? 'btn-primary' : 'btn-outline', action: 'acc-outcome' }));
      if (open && a.liability && api.can('accidents.approve')) acts.push(A.btn('إغلاق الحادث', { icon: 'circle-check', cls: 'btn-primary', action: 'acc-close' }));
      if (open && !a.liability && !a.repair && api.can('accidents.update')) acts.push(A.btn('إلغاء', { icon: 'ban', cls: 'btn-ghost', action: 'acc-cancel' }));
      if (open && api.can('accidents.create')) acts.push(A.btn('إضافة صور', { icon: 'camera', cls: 'btn-ghost', action: 'acc-photos' }));
      return detail(a, acts);
    }).then(function () {
      BT.on(v, 'click', '[data-est-ok]', function () {
        A.confirmRun({ title: 'اعتماد تقدير الأضرار', message: 'بعد الاعتماد يمكن استخدام القيمة في الخصم وإرسال السيارة للإصلاح لدى المركز نفسه.', confirmText: 'اعتماد', run: function () { return api.post('/accidents/' + A._acc.id + '/estimate/approve'); }, done: 'اعتُمد التقدير', after: refreshAll });
      });
      BT.on(v, 'click', '[data-est-no]', function () {
        A.confirmRun({ title: 'رفض تقدير الأضرار', message: 'يعود للمركز ليقدّر من جديد، أو أحله لمركز آخر.', tone: 'danger', confirmText: 'رفض', reason: { label: 'السبب (يراه المركز)', required: true }, run: function (reason) { return api.post('/accidents/' + A._acc.id + '/estimate/reject', { reason: reason }); }, done: 'رُفض التقدير', after: refreshAll });
      });
    }).catch(function () {});
  };

  function detail(a, acts) {
    var url = fileUrl(a.id);
    var info = [
      ['الوقت', fmt.dt(a.occurred_at)],
      a.location_text ? ['الموقع', a.location_text] : null,
      a.lat != null ? ['الإحداثيات', h`<a class="ltr" href="https://www.openstreetmap.org/?mlat=${a.lat}&mlon=${a.lng}#map=17/${a.lat}/${a.lng}" target="_blank" rel="noopener">${a.lat.toFixed(5)}, ${a.lng.toFixed(5)}</a>`] : null,
      ['الوصف', h`<span style="white-space:normal">${a.description}</span>`],
      ['الإصابات', a.injuries ? h`${BT.pill('نعم', 'r')}${a.injuries_note ? h` <span style="white-space:normal">${a.injuries_note}</span>` : ''}` : 'لا'],
      a.other_party ? ['الطرف الآخر', h`<span style="white-space:normal">${a.other_party}</span>`] : null,
      ['المصدر', a.source === 'driver' ? 'السائق من التطبيق' : 'المكتب'],
      ['السائق المسؤول', a.driver ? A.person(a.driver) : raw('<span class="muted">لم تكن السيارة مسلّمة لأحد وقت الحادث</span>')]
    ].filter(Boolean);
    var police = a.has_police_report
      ? [['المحضر', h`<a href="${url(a.police_report_sha256)}" target="_blank" rel="noopener">${icon('file-text', 14)} فتح المحضر</a>`], a.police_report_no ? ['رقم المحضر', h`<span class="num">${a.police_report_no}</span>`] : null, ['أُرفق', fmt.dt(a.police_report_at)]].filter(Boolean)
      : null;
    var estActions = a.estimate_status === 'pending' && a.status === 'open' && api.can('accidents.update')
      ? h`<div class="flex gap-8 mt-12"><button type="button" class="btn btn-sm btn-primary" data-est-ok>${icon('check', 14)} اعتماد التقدير</button><button type="button" class="btn btn-sm btn-ghost" data-est-no>${icon('x', 14)} رفض</button></div>` : '';
    var outcome = a.liability ? [
      ['المسؤولية', C.liability(a)],
      a.outcome_note ? ['ملاحظة', h`<span style="white-space:normal">${a.outcome_note}</span>`] : null,
      ['القرار', (a.outcome_by || '') + ' · ' + fmt.dt(a.outcome_at)]
    ].filter(Boolean) : null;
    var d = a.deduction;
    var repair = a.repair;
    return h`${A.head(h`${M.vehicleLine(a.vehicle)} · حادث <span class="num">#${a.number}</span>`, h`${C.stage(a.stage)} ${a.status === 'open' ? C.police(a) : ''} · ${api.company(a.company_id)}`, acts)}
      ${a.status === 'open' && !a.has_police_report ? h`<div class="banner warn mb-16">${icon('file-warning', 16)}<div>الحادث <b>بانتظار محضر الشرطة</b>: لا يمكن تسجيل المسؤولية قبل إرفاقه.</div></div>` : ''}
      ${a.status === 'cancelled' ? h`<div class="banner mb-16">${icon('ban', 16)}<div>أُلغي: ${a.cancel_reason}</div></div>` : ''}
      <div class="grid-2 mb-16">
        <div class="card"><div class="card-h"><div class="card-t">الحادث</div></div>${BT.kv(info)}</div>
        <div class="card"><div class="card-h"><div class="card-t">محضر الشرطة والمركز</div></div>
          ${police ? BT.kv(police) : raw('<div class="muted fs-sm mb-12">لم يُرفق المحضر بعد</div>')}
          ${a.center ? h`<div class="section-t mt-12">المركز</div>${BT.kv([['المركز', a.center.name], ['الإحالة', fmt.dt(a.referred_at)], ['التقدير', C.estimate(a.estimate_status)]])}` : raw('<div class="muted fs-sm mt-12">لم يُحل لمركز لتقدير الأضرار بعد</div>')}</div>
      </div>
      <div class="card mb-16"><div class="card-h"><div class="card-t">الصور</div></div>${C.photos(a.photos, url)}</div>
      ${C.estimateCard(a, url, estActions)}
      ${outcome ? h`<div class="card mb-16"><div class="card-h"><div class="card-t">المسؤولية والخصم</div></div><div class="grid-2">
          <div>${BT.kv(outcome)}</div>
          <div>${d ? h`<div class="highlight-box mb-12 between"><b>الخصم ${d.status === 'cancelled' ? BT.pill('ملغى', 'n') : ''}</b><b>${BT.amt(d.total)} <small class="muted">على ${d.installments} ${d.installments === 1 ? 'قسط' : 'أقساط'}</small></b></div>${C.schedule(d)}${d.cancel_reason ? h`<div class="fs-sm mt-8 muted">سبب الإلغاء: ${d.cancel_reason}</div>` : ''}` : raw('<div class="muted fs-sm">لا خصم على السائق</div>')}</div>
        </div></div>` : ''}
      ${repair ? h`<div class="card mb-16"><div class="card-h"><div class="card-t">الإصلاح</div><a class="link-row" href="#/maintenance/${repair.id}">طلب الصيانة <span class="num">#${repair.number}</span> ${icon('arrow-left', 14)}</a></div>
        ${BT.kv([
          ['الحالة', M.status(repair.status)],
          ['التقدير المعتمد', BT.amt(a.estimate_total)],
          ['التكلفة الفعلية', repair.actual_cost != null ? BT.amt(repair.actual_cost) : raw('<span class="muted">' + (repair.invoices_pending ? 'فاتورة بانتظار الاعتماد' : 'لم تصل الفاتورة بعد') + '</span>')],
          a.cost_difference != null ? ['الفرق', h`<b class="${Number(a.cost_difference) > 0 ? 't-danger' : ''}">${BT.amt(Number(a.cost_difference), { signed: true })}</b>`] : null
        ].filter(Boolean))}</div>` : ''}
      <div class="card"><div class="card-h"><div class="card-t">الجدول الزمني</div></div>${C.timeline(a.events)}</div>`;
  }

  function acc() { return A._acc; }
  BT.actions['acc-police'] = function () {
    A.formModal({
      title: acc().has_police_report ? 'استبدال محضر الشرطة' : 'إرفاق محضر الشرطة', subtitle: 'حادث #' + acc().number, icon: 'file-up', size: 'sm',
      body: h`<div class="form">${BT.f.upload({ name: 'file', label: 'المحضر (صورة أو PDF)', required: true, accept: 'image/*,application/pdf' })}${BT.f.input({ name: 'no', label: 'رقم المحضر', optional: true })}</div>`,
      submitText: 'إرفاق', done: 'أُرفق المحضر',
      submit: function (f) { return upload(f.file[0]).then(function (sha) { return api.post('/accidents/' + acc().id + '/police-report', { file_sha256: sha, number: f.no || null }); }); },
      after: refreshAll
    });
  };
  BT.actions['acc-photos'] = function () {
    A.formModal({
      title: 'إضافة صور', subtitle: 'حادث #' + acc().number, icon: 'camera', size: 'sm',
      body: h`<div class="form">${BT.f.upload({ name: 'ph', label: 'صور', required: true, multiple: true, accept: 'image/*', accept_label: 'صور فقط · حتى 12 صورة' })}</div>`,
      submitText: 'إضافة', done: 'أُضيفت الصور',
      submit: function (f) { return uploadAll(f.ph).then(function (photos) { return api.post('/accidents/' + acc().id + '/photos', { photos: photos }); }); },
      after: refreshAll
    });
  };
  BT.actions['acc-refer'] = function () {
    api.get('/maintenance/centers', { active: true }).then(function (centers) {
      if (!centers.length) { BT.toast('أضف مركز صيانة أولاً من صفحة الصيانة', { type: 'warning' }); return; }
      A.formModal({
        title: 'إحالة لمركز لتقدير الأضرار', subtitle: acc().vehicle.plate_number + ' · حادث #' + acc().number, icon: 'send',
        body: h`<div class="form">${BT.f.select({ name: 'center', label: 'المركز', required: true, value: acc().center && acc().center.id, options: centers.map(function (c) { return { v: c.id, t: c.name + (c.specialty ? ' — ' + c.specialty : '') }; }) })}
          ${BT.f.textarea({ name: 'note', label: 'ملاحظة', optional: true, rows: 2 })}<div class="hint">يظهر الحادث بصوره فوراً في بوابة المركز ليُدخل قيمة الأضرار وبنودها.</div></div>`,
        submitText: 'إحالة', done: 'أُحيل الحادث للمركز',
        submit: function (f) { return api.post('/accidents/' + acc().id + '/refer', { center_id: f.center, note: f.note || null }); }, after: refreshAll
      });
    }, api.fail).catch(function () {});
  };
  BT.actions['acc-repair'] = function () {
    A.confirmRun({
      title: 'إرسال السيارة للإصلاح', message: 'يُنشأ طلب صيانة معتمد ومحال إلى ' + (acc().center ? acc().center.name : 'المركز') + '، وعرض سعره هو التقدير المعتمد (' + fmt.money(acc().estimate_total) + ' د.ك). يبدأ الإصلاح عند استلام المركز للسيارة.',
      confirmText: 'إرسال', run: function () { return api.post('/accidents/' + acc().id + '/repair'); }, done: 'أُرسلت السيارة للإصلاح', after: refreshAll
    });
  };
  BT.actions['acc-close'] = function () {
    A.formModal({ title: 'إغلاق الحادث', icon: 'circle-check', size: 'sm', body: h`<div class="form">${BT.f.textarea({ name: 'note', label: 'ملاحظة', optional: true, rows: 2 })}</div><div class="hint mt-8">إن كانت السيارة ما زالت «في حادث» (لم تدخل مركزاً) تعود لسائقها أو متاحة.</div>`,
      submitText: 'إغلاق', done: 'أُغلق الحادث', submit: function (f) { return api.post('/accidents/' + acc().id + '/close', { note: f.note || null }); }, after: refreshAll });
  };
  BT.actions['acc-cancel'] = function () {
    A.confirmRun({ title: 'إلغاء الحادث', message: 'للبلاغ المسجّل بالخطأ فقط. تعود السيارة لحالتها.', tone: 'danger', confirmText: 'إلغاء الحادث', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/accidents/' + acc().id + '/cancel', { reason: reason }); }, done: 'أُلغي الحادث', after: refreshAll });
  };

  /* ---------- المسؤولية والخصم ---------- */
  function nextMonth() { var p = BT.config.today.split('-'), y = +p[0], m = +p[1] + 1; if (m > 12) { m = 1; y++; } return y + '-' + (m < 10 ? '0' : '') + m; }
  BT.actions['acc-outcome'] = function () {
    var a = acc(), approved = a.estimate_status === 'approved', total = approved ? Number(a.estimate_total) : 0;
    if (!a.has_police_report) { BT.toast('أرفق محضر الشرطة أولاً: لا تُسجّل المسؤولية دونه', { type: 'error', timeout: 6000 }); return; }
    A.formModal({
      title: 'تحديد المسؤولية', subtitle: 'حادث #' + a.number + ' · وفق محضر الشرطة المرفق', icon: 'scale', size: 'lg',
      body: h`<div class="form-grid">
        <div class="full">${BT.f.select({ name: 'liability', label: 'المسؤولية', required: true, value: 'driver', options: A.options('accident_liability', ['none', 'driver', 'shared']) })}</div>
        <div data-charge class="full"><div class="form-grid">
          ${!approved ? h`<div class="full banner warn">${icon('triangle-alert', 16)}<div>تقدير الأضرار لم يُعتمد بعد: يمكن تسجيل «لا مسؤولية» فقط.</div></div>` : ''}
          ${!a.driver ? h`<div class="full banner warn">${icon('triangle-alert', 16)}<div>لا يوجد سائق مسؤول (لم تكن السيارة مسلّمة لأحد وقت الحادث).</div></div>` : ''}
          ${BT.f.input({ name: 'percent', label: 'نسبة مسؤولية السائق %', optional: true, num: true, value: '100', hint: 'مسؤولية السائق: 100% إلا إذا قررتم أقل' })}
          ${BT.f.input({ name: 'inst', label: 'عدد الأقساط', required: true, num: true, value: '1' })}
          ${BT.f.input({ name: 'start', label: 'شهر البدء', type: 'month', required: true, value: nextMonth() })}
          ${BT.f.input({ name: 'reason', label: 'السبب في كشف الراتب', optional: true, hint: 'افتراضياً: حادث #' + a.number })}
          <div class="full highlight-box" data-preview></div></div></div>
        ${BT.f.textarea({ name: 'note', label: 'ملاحظة القرار', optional: true, full: true, rows: 2 })}</div>`,
      onOpen: function (dlg) {
        var f = dlg.form, sel = f.querySelector('[name=liability]'), pct = f.querySelector('[name=percent]'), inst = f.querySelector('[name=inst]');
        function draw() {
          var l = sel.value, box = f.querySelector('[data-charge]');
          box.style.display = l === 'none' ? 'none' : '';
          box.querySelectorAll('input').forEach(function (i) { i.disabled = l === 'none'; });
          if (l === 'shared' && pct.value === '100') pct.value = '50';
          var p = Number(pct.value) || 0, n = Math.max(1, Math.round(Number(inst.value) || 1)), amount = BT.round3(total * p / 100);
          var each = Math.floor(amount / n * 1000) / 1000, last = BT.round3(amount - each * (n - 1));
          BT.render(f.querySelector('[data-preview]'), approved ? h`<div class="between"><span>التقدير المعتمد ${BT.amt(total)} × ${p}%</span><b>الخصم ${BT.amt(amount)}</b></div><div class="muted fs-sm mt-8">${n === 1 ? 'دفعة واحدة' : n + ' أقساط: ' + fmt.kwd(each) + (last !== each ? ' والأخير ' + fmt.kwd(last) : ' شهرياً')}</div>` : '');
        }
        [sel, pct, inst].forEach(function (el) { el.addEventListener('input', draw); el.addEventListener('change', draw); });
        draw();
      },
      submitText: 'تسجيل القرار', submitCls: 'btn-primary', done: 'سُجّلت المسؤولية',
      submit: function (f, dlg) {
        var l = dlg.form.querySelector('[name=liability]').value;
        var body = { liability: l, note: f.note || null };
        if (l !== 'none') {
          body.percent = f.percent === '' || f.percent == null ? null : String(f.percent);
          body.installments = Math.round(f.inst);
          body.start_month = f.start + '-01';
          body.reason = f.reason || null;
        }
        return api.post('/accidents/' + a.id + '/outcome', body);
      },
      after: refreshAll
    });
  };

  /* ================= الخصومات ================= */
  BT.pages['deductions'] = function (p, q) {
    A.setTitle('الخصومات', [['الحوادث', 'accidents'], ['الخصومات']]);
    var v = A.view();
    if (!api.can('deductions.view')) { BT.render(v, A.forbidden()); return; }
    BT.render(v, h`${A.head('الخصومات المعتمدة', 'ما يخصمه الراتب من كل موظف: الإجمالي على أقساط شهرية متساوية، والباقي على القسط الأخير. الشهر الذي يصل حد الخصم يُرحّل باقيه للشهر التالي.', api.can('deductions.manage') && A.manualDeduction ? A.btn('خصم جديد (سلفة، شريحة…)', { icon: 'plus', cls: 'btn-primary', id: 'ded-new' }) : '')}
      <div class="card"><div data-t></div></div>`);
    var add = v.querySelector('#ded-new');
    if (add) add.onclick = function () { A.manualDeduction(function () { t.refresh(); }); };
    var t = BT.table(v.querySelector('[data-t]'), {
      fetch: function (s) { return api.get('/deductions', { status: s.chip === 'cancelled' ? 'cancelled' : 'approved', month: s.chip === 'month' ? BT.config.today : null, limit: s.limit, offset: s.offset }); },
      chips: { value: q.chip || 'month', all: false, options: [{ v: 'month', t: 'هذا الشهر' }, { v: 'approved', t: 'كل المعتمدة' }, { v: 'cancelled', t: 'الملغاة' }] },
      columns: [
        { key: 'employee', label: 'الموظف', render: function (d) { return A.person(d.employee); } },
        { key: 'source_type', label: 'المصدر', render: function (d) { return h`${api.t('deduction_source', d.source_type)}<span class="sub">${d.reason}</span>`; } },
        { key: 'total', label: 'الإجمالي', num: true, render: function (d) { return BT.amt(Number(d.total)); } },
        { key: 'installments', label: 'الأقساط', render: function (d) { var m = d.start_month.split('-'); return h`<span class="num">${d.installments}</span><span class="sub">من ${fmt.month(+m[0], +m[1])}</span>`; } },
        { key: 'this', label: 'قسط هذا الشهر', num: true, render: function (d) { var cur = BT.config.today.slice(0, 7), x = d.schedule.filter(function (s) { return s.month.slice(0, 7) === cur; })[0]; return x ? BT.amt(Number(x.amount)) : '—'; } },
        { key: 'status', label: 'الحالة', render: function (d) { return BT.pill(api.t('deduction_status', d.status), d.status === 'approved' ? 'g' : 'n'); } }
      ],
      rowClick: function (d) { deductionView(d, function () { t.refresh(); }); },
      empty: { icon: 'minus-circle', title: 'لا توجد خصومات هنا' }
    });
  };
  function deductionView(d, done) {
    var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
    if (d.status === 'approved' && api.can('deductions.manage')) btns.push({ label: 'إلغاء الخصم', cls: 'btn-ghost', icon: 'ban', close: false, onClick: function (dlg) {
      A.confirmRun({ title: 'إلغاء الخصم', message: 'لا يُخصم أي قسط بعد الإلغاء. يبقى في السجل بسببه.', tone: 'danger', confirmText: 'إلغاء الخصم', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/deductions/' + d.id + '/cancel', { reason: reason }); }, done: 'أُلغي الخصم', after: function () { dlg.close(); done(); } });
    } });
    BT.drawer.open({
      title: h`خصم ${BT.amt(Number(d.total))}`, subtitle: api.name(d.employee.name) + ' · ' + api.t('deduction_source', d.source_type) + ' ' + d.reason, icon: 'minus-circle',
      body: h`${BT.kv([
        ['الموظف', A.person(d.employee)],
        ['المصدر', api.t('deduction_source', d.source_type) + ' · ' + d.reason],
        ['الاعتماد', (d.created_by || '') + ' · ' + fmt.dt(d.created_at)],
        d.cancelled_at ? ['الإلغاء', (d.cancelled_by || '') + ' · ' + fmt.dt(d.cancelled_at) + ' · ' + d.cancel_reason] : null
      ].filter(Boolean))}<div class="section-t mt-16">الأقساط</div>${C.schedule(d)}`,
      buttons: btns
    });
  }

  /* ---------- تبويب الحوادث في ملف السيارة ---------- */
  A.vehicleAccidents = function (el, vehicle) {
    A.load(el, api.get('/accidents', { vehicle_id: vehicle.id, limit: 20 }), function (rows) {
      return h`${rows.length ? h`<div class="list">${rows.map(function (a) {
        return h`<a class="li" href="#/accidents/${a.id}"><span class="li-ic r">${icon('shield-alert', 16)}</span><div class="li-main"><div class="li-t"><span class="num">#${a.number}</span> ${a.driver ? api.name(a.driver.name) : 'بلا سائق'}</div><div class="li-d">${fmt.dt(a.occurred_at)}${a.estimate_total != null ? ' · تقدير ' + fmt.money(a.estimate_total) : ''}</div></div>${C.stage(a.stage)}</a>`;
      })}</div>` : BT.empty('shield-check', 'لا توجد حوادث', '')}
        ${api.can('accidents.create') ? h`<div class="mt-12"><button type="button" class="btn btn-sm btn-soft" data-acc-new>${icon('plus', 14)} تسجيل حادث</button></div>` : ''}`;
    }).then(function () {
      var b = el.querySelector('[data-acc-new]');
      if (b) b.onclick = function () { newAccident(vehicle); };
    }).catch(function () {});
  };
})();
