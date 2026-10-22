/* =====================================================================
   app/pages/maintenance.js — الصيانة: الطلبات (من السائق أو المكتب للمركز مباشرة)،
   فواتير المراكز واعتمادها ودفعها، ومراكز الصيانة وحسابات بوابتها. الطلبات القديمة
   تكمل اعتمادها وإحالتها وعروض سعرها من هنا.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A, M = BT.mnt;

  var GROUPS = {
    pending: 'requested,approved,quote_pending', // طلبات قديمة أو سيارة في حادث: بانتظار المكتب
    at_center: 'referred,received,inspection,in_repair,waiting_parts,completed',
    ready: 'ready',
    done: 'picked_up,closed',
    stopped: 'rejected,cancelled'
  };
  function fileUrl(id) { return function (sha) { return api.url('/maintenance/requests/' + id + '/files/' + sha); }; }
  function upload(file) { return api.upload(file).then(function (f) { return f.sha256; }); }
  function uploadAll(files) { return Promise.all(Array.prototype.map.call(files || [], upload)); }
  function refreshAll() { A.refreshIfAt('maintenance'); A.refreshCounts(); }

  /* ================= الصفحة: الطلبات · الفواتير · المراكز ================= */
  BT.pages['maintenance'] = function (p, q) {
    A.setTitle('الصيانة');
    var v = A.view(), tabs = [];
    if (api.can('maintenance.view')) tabs.push(['requests', 'طلبات الصيانة']);
    if (api.can('maintenance.view')) tabs.push(['schedules', 'الصيانة الدورية']);
    if (api.can('invoices.view')) tabs.push(['invoices', 'الفواتير']);
    if (api.can('maintenance.view')) tabs.push(['centers', 'مراكز الصيانة']);
    var tab = tabs.some(function (t) { return t[0] === q.tab; }) ? q.tab : tabs[0][0];
    BT.render(v, h`${A.head('الصيانة ومراكزها', 'الطلب يذهب من السائق أو المكتب للمركز المختار مباشرة؛ المركز يستلم السيارة ثم يجهزها بفاتورته، والسائق يؤكد الاستلام من تطبيقه. الفواتير تُعتمد هنا', h`${api.can('maintenance.create') ? A.btn('طلب صيانة', { icon: 'plus', cls: 'btn-primary', action: 'mnt-new' }) : ''}${api.can('invoices.create') ? A.btn('فاتورة من مركز', { icon: 'receipt-text', cls: 'btn-outline', action: 'mnt-invoice' }) : ''}`)}
      ${tabs.length > 1 ? BT.tabs('mnt', tabs, tab, 'tabs-line') : ''}
      ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="mnt" class="${t[0] === tab ? 'active' : ''}"><div data-p="${t[0]}"></div></div>`; })}`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      var el = v.querySelector('[data-p="' + t + '"]');
      ({ requests: requestsPanel, schedules: schedulesPanel, invoices: invoicesPanel, centers: centersPanel })[t](el, q);
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); });
    show(tab);
  };
  BT.actions['mnt-new'] = function () { newRequest(); };
  BT.actions['mnt-invoice'] = function () { officeInvoice(); };

  function requestsPanel(el, q) {
    BT.render(el, h`<div class="card"><div data-t></div></div>`);
    BT.table(el.querySelector('[data-t]'), {
      fetch: function (s) { return api.get('/maintenance/requests', { status: GROUPS[s.chip] || null, active: s.chip && s.chip !== 'late' ? null : true, late: s.chip === 'late' || null, limit: s.limit, offset: s.offset }); },
      chips: { value: q.status || '', all: 'المفتوحة', options: [
        { v: 'at_center', t: 'في المركز' }, { v: 'late', t: 'المتأخرة' }, { v: 'ready', t: 'جاهزة للاستلام' }, { v: 'done', t: 'المستلمة' },
        { v: 'pending', t: 'بانتظار المكتب' }, { v: 'stopped', t: 'المرفوضة والملغاة' }
      ] },
      columns: [
        { key: 'number', label: 'الطلب', render: function (r) { return h`<span class="num">#${r.number}</span><span class="sub">${M.kind(r.kind)}${r.emergency ? ' · طارئة' : ''}</span>`; } },
        { key: 'vehicle', label: 'السيارة', render: function (r) { return M.vehicle(r.vehicle); } },
        { key: 'driver', label: 'السائق', render: function (r) { return r.driver ? A.person(r.driver) : raw('<span class="muted">—</span>'); } },
        { key: 'status', label: 'الحالة', render: function (r) { return h`${M.status(r.status)}${r.emergency && !r.emergency_reviewed ? h` ${BT.pill('تحتاج مراجعة', 'o')}` : ''}`; } },
        { key: 'center', label: 'المركز', render: function (r) { return r.center ? r.center.name : raw('<span class="muted">—</span>'); } },
        { key: 'follow', label: 'المتابعة', render: function (r) { return h`${r.priority !== 'normal' ? M.priority(r.priority) : ''}${r.expected_ready_on ? h`<span class="sub">متوقع ${fmt.date(r.expected_ready_on)}</span>` : ''}${M.late(r)}${r.assignee ? h`<span class="sub">${r.assignee.name}</span>` : ''}`; } },
        { key: 'stay', label: 'المدة', render: function (r) { return r.stay_seconds != null ? M.dur(r.stay_seconds) : h`<span class="muted">${fmt.since(r.created_at)}</span>`; } }
      ],
      rowClick: function (r) { A.go('maintenance/' + r.id); },
      empty: { icon: 'wrench', title: 'لا توجد طلبات هنا' }
    });
  }

  /* كل السيارات ضمن النطاق، 200 في كل طلب (حد الخادم للصفحة) */
  function allVehicles(offset, acc) {
    offset = offset || 0; acc = acc || [];
    return api.get('/vehicles', { limit: 200, offset: offset }).then(function (rows) {
      acc = acc.concat(rows);
      return rows.length === 200 && acc.length < 5000 ? allVehicles(offset + 200, acc) : acc;
    });
  }

  /* ---------- طلب جديد من الإدارة (أو تنفيذاً لصيانة دورية: schedule) ---------- */
  function newRequest(vehicle, schedule) {
    var jobs = [vehicle ? Promise.resolve([vehicle]) : allVehicles(), api.get('/maintenance/centers', { active: true })];
    Promise.all(jobs).then(function (res) {
      var vehicles = res[0], centers = res[1];
      if (!centers.length) { BT.toast('أضف مركز صيانة أولاً من تبويب المراكز', { type: 'warning' }); return; }
      A.formModal({
        title: 'طلب صيانة', subtitle: schedule ? 'تنفيذ الصيانة الدورية «' + schedule.title + '»: تُسجَّل منفّذة عند استلام السيارة' : '', icon: 'wrench', size: 'lg',
        body: h`<div class="form-grid">
          <div class="full">${A.picker({ name: 'vehicle', label: 'السيارة', required: true, items: vehicles.map(function (x) { return { id: x.id, label: A.vehicleLabel(x) }; }), value: vehicle && vehicle.id })}</div>
          <div class="full">${BT.f.select({ name: 'center', label: 'مركز الصيانة', required: true, options: centers.map(function (c) { return { v: c.id, t: c.name + (c.specialty ? ' — ' + c.specialty : '') + (c.at_center ? ' · لديه ' + c.at_center : '') }; }) })}</div>
          ${BT.f.select({ name: 'kind', label: 'النوع', required: true, options: M.kindOptions(), value: schedule && schedule.kind })}
          ${BT.f.input({ name: 'km', label: 'قراءة العداد', optional: true, num: true })}
          ${BT.f.select({ name: 'priority', label: 'الأولوية', placeholder: false, options: A.options('maintenance_priority', ['low', 'normal', 'high', 'urgent']), value: 'normal' })}
          ${BT.f.input({ name: 'expected', label: 'موعد الإنجاز المتوقع', type: 'date', optional: true, min: BT.config.today, hint: 'بعده يُنبَّه عن التأخير ثم يُصعَّد' })}
          ${BT.f.textarea({ name: 'desc', label: 'الوصف', required: true, full: true, rows: 3, value: schedule ? schedule.title : '' })}
          ${BT.f.upload({ name: 'ph', label: 'صور', optional: true, multiple: true, full: true, accept: 'image/*', accept_label: 'صور فقط' })}</div>
          <div class="hint mt-8">يظهر الطلب فوراً في بوابة المركز؛ تبقى السيارة في عهدة سائقها أثناء الصيانة ويؤكد استلامها من تطبيقه.</div>`,
        submitText: 'إرسال للمركز', done: 'أُرسل الطلب للمركز',
        submit: function (f) {
          var vid = A.picked('vehicle', f.vehicle);
          return uploadAll(f.ph).then(function (photos) {
            return api.post('/maintenance/requests', { vehicle_id: vid, center_id: f.center, kind: f.kind, description: f.desc, odometer_km: f.km === '' || f.km == null ? null : Math.round(f.km), photos: photos,
              priority: f.priority || null, expected_ready_on: f.expected || null, schedule_id: schedule ? schedule.id : null });
          });
        },
        after: function (r) { A.go('maintenance/' + r.id); A.refreshCounts(); }
      });
    }, api.fail).catch(function () {});
  }
  A.maintenanceRequest = newRequest;

  /* ================= طلب واحد ================= */
  BT.pages['maintenance/:id'] = function (p) {
    A.setTitle('طلب صيانة', [['الصيانة', 'maintenance'], ['طلب']]);
    var v = A.view();
    A.load(v, api.get('/maintenance/requests/' + p.id), function (r) {
      A.setTitle('طلب #' + r.number, [['الصيانة', 'maintenance'], ['#' + r.number]]);
      var acts = [], s = r.status;
      if (s === 'requested' && api.can('maintenance.approve')) { acts.push(A.btn('رفض', { icon: 'x', cls: 'btn-ghost', action: 'mnt-reject' })); acts.push(A.btn('اعتماد', { icon: 'check', cls: 'btn-primary', action: 'mnt-approve' })); }
      if ((s === 'approved' || s === 'referred') && api.can('maintenance.approve')) acts.push(A.btn(s === 'referred' ? 'تغيير المركز' : 'إحالة لمركز', { icon: 'send', cls: s === 'approved' ? 'btn-primary' : 'btn-outline', action: 'mnt-refer' }));
      if (r.emergency && !r.emergency_reviewed && api.can('maintenance.approve')) acts.push(A.btn('مراجعة الطارئة', { icon: 'shield-check', cls: 'btn-outline', action: 'mnt-review' }));
      if (['requested', 'approved', 'referred'].indexOf(s) > -1 && api.can('maintenance.create')) acts.push(A.btn('إلغاء', { icon: 'ban', cls: 'btn-ghost', action: 'mnt-cancel' }));
      if (s === 'ready' && !r.driver_collects && api.can('maintenance.create')) acts.push(A.btn('تم استلام السيارة', { icon: 'log-out', cls: 'btn-primary', action: 'mnt-picked' })); // وإلا يؤكده السائق من تطبيقه
      var spare = openReplacement(r);
      if (spare && api.can('custody.assign')) acts.push(A.btn('إرجاع السيارة البديلة', { icon: 'undo-2', cls: 'btn-outline', action: 'mnt-spare-back' }));
      else if (REPAIRING.indexOf(s) > -1 && r.driver_collects && api.can('custody.assign')) acts.push(A.btn('سيارة بديلة', { icon: 'car', cls: 'btn-outline', action: 'mnt-spare' }));
      if (FINISHED.indexOf(s) < 0 && api.can('maintenance.create')) acts.push(A.btn('المتابعة', { icon: 'calendar', cls: 'btn-outline', action: 'mnt-plan' }));
      A._mnt = r;
      return h`${A.head(h`${M.vehicleLine(r.vehicle)} · طلب <span class="num">#${r.number}</span>`, h`${M.status(r.status)} · ${M.kind(r.kind)} · ${api.company(r.company_id)}`, acts)}
        ${M.detail(r, fileUrl(r.id), {
          admin: true,
          quoteActions: function (qt) {
            if (qt.status !== 'pending' || !api.can('maintenance.approve')) return '';
            return h`<div class="flex gap-8 mt-8"><button type="button" class="btn btn-sm btn-primary" data-q-ok="${qt.id}">${icon('check', 14)} اعتماد العرض</button><button type="button" class="btn btn-sm btn-ghost" data-q-no="${qt.id}">${icon('x', 14)} رفض</button></div>`;
          }
        })}
        ${r.invoices.some(function (i) { return i.status === 'pending'; }) && api.can('invoices.approve') ? h`<div class="banner info mt-16">${icon('receipt-text', 16)}<div>فاتورة بانتظار الاعتماد: راجعها مقابل الملف في <a href="#/maintenance?tab=invoices">تبويب الفواتير</a>.</div></div>` : ''}
        ${links(r)}`;
    }).then(function () {
      BT.on(v, 'click', '[data-q-ok]', function (e, b) {
        A.confirmRun({ title: 'اعتماد عرض السعر', message: 'يبدأ المركز الإصلاح بعد الاعتماد.', confirmText: 'اعتماد', run: function () { return api.post('/maintenance/quotes/' + b.getAttribute('data-q-ok') + '/approve'); }, done: 'اعتُمد العرض', after: refreshAll });
      });
      BT.on(v, 'click', '[data-custody-open]', function (e, b) { if (A.custody) A.custody(b.getAttribute('data-custody-open')); });
      BT.on(v, 'click', '[data-q-no]', function (e, b) {
        A.confirmRun({ title: 'رفض عرض السعر', message: 'يعود الطلب للمركز ليرسل عرضاً جديداً.', tone: 'danger', confirmText: 'رفض', reason: { label: 'السبب (يراه المركز)', required: true }, run: function (reason) { return api.post('/maintenance/quotes/' + b.getAttribute('data-q-no') + '/reject', { reason: reason }); }, done: 'رُفض العرض', after: refreshAll });
      });
    }).catch(function () {});
  };
  function req() { return A._mnt; }
  var REPAIRING = ['received', 'inspection', 'quote_pending', 'in_repair', 'waiting_parts', 'completed'];
  var FINISHED = ['rejected', 'picked_up', 'closed', 'cancelled'];
  function openReplacement(r) { return (r.replacements || []).filter(function (c) { return !c.ended_at; })[0] || null; }

  /* الارتباطات في الاتجاهين: السيارة، العهدة التي بقيت فيها أثناء الصيانة، السيارات البديلة، الفواتير، الاستلام */
  function custodyLine(c, label) {
    var open = !c.ended_at;
    return h`<button type="button" class="li" data-custody-open="${c.id}" style="width:100%;text-align:start"><span class="li-ic ${open ? 'g' : ''}">${icon(c.kind === 'replacement' ? 'car' : 'key-round', 16)}</span><div class="li-main"><div class="li-t">${label} · <span class="plate">${c.vehicle.plate_number || '—'}</span> · ${c.driver ? api.name(c.driver.name) : '—'}</div><div class="li-d">${fmt.dt(c.started_at)} ← ${c.ended_at ? fmt.dt(c.ended_at) : 'مستمرة'}</div></div>${open ? BT.pill('مفتوحة', 'g') : ''}</button>`;
  }
  function links(r) {
    var rows = [];
    rows.push(h`<a class="li" href="#/vehicles/${r.vehicle.id}"><span class="li-ic">${icon('car', 16)}</span><div class="li-main"><div class="li-t">السيارة <span class="plate">${r.vehicle.plate_number}</span></div><div class="li-d">ملف السيارة: العهد والقراءات والصيانة الدورية</div></div></a>`);
    if (r.custody) rows.push(custodyLine(r.custody, 'العهدة أثناء الصيانة'));
    (r.replacements || []).forEach(function (c) { rows.push(custodyLine(c, 'سيارة بديلة')); });
    r.invoices.forEach(function (i) { rows.push(h`<a class="li" href="#/maintenance?tab=invoices"><span class="li-ic">${icon('receipt-text', 16)}</span><div class="li-main"><div class="li-t">فاتورة <span class="num">${i.number}</span> · ${BT.amt(Number(i.total))}</div><div class="li-d">${fmt.date(i.invoice_date)}</div></div>${M.invStatus(i)}</a>`); });
    if (r.pickup) rows.push(h`<div class="li"><span class="li-ic g">${icon('log-out', 16)}</span><div class="li-main"><div class="li-t">الاستلام من المركز${r.pickup.km != null ? h` · <span class="num">${fmt.km(r.pickup.km)}</span> كم` : ''}</div><div class="li-d">${fmt.dt(r.pickup.at)} · ${r.pickup.by === 'driver' ? 'السائق من تطبيقه' : r.pickup.by || '—'}</div></div></div>`);
    return h`<div class="card mt-16" data-mnt-links><div class="card-h"><div class="card-t">${icon('link', 16)} الارتباطات</div></div><div class="list">${rows}</div>
      ${openReplacement(r) ? h`<div class="hint mt-8">تنتهي عهدة السيارة البديلة حين يستلم السائق سيارته من تطبيقه (يسجّل قراءتها وصورتها في نفس الخطوة)، أو بإرجاعها من هنا.</div>` : ''}</div>`;
  }

  BT.actions['mnt-plan'] = function () {
    var r = req();
    var users = api.get('/maintenance/assignees').catch(function () { return []; });
    users.then(function (list) {
      A.formModal({
        title: 'متابعة الطلب', subtitle: r.vehicle.plate_number + ' · طلب #' + r.number, icon: 'calendar', size: 'sm',
        body: h`<div class="form">${BT.f.select({ name: 'priority', label: 'الأولوية', placeholder: false, options: A.options('maintenance_priority', ['low', 'normal', 'high', 'urgent']), value: r.priority })}
          ${BT.f.select({ name: 'assignee', label: 'المسؤول عن المتابعة', placeholder: 'بدون', options: list.map(function (u) { return { v: u.id, t: u.name }; }), value: r.assignee ? r.assignee.id : '' })}
          ${BT.f.input({ name: 'expected', label: 'موعد الإنجاز المتوقع', type: 'date', optional: true, value: r.expected_ready_on || '', hint: 'بعده يظهر الطلب «متأخراً» ويُنبَّه عنه، ثم يُصعَّد للمعتمدين بعد المهلة في الإعدادات (فوراً للعاجل)' })}</div>`,
        submitText: 'حفظ', done: 'حُفظت المتابعة',
        submit: function (f) { return api.put('/maintenance/requests/' + r.id + '/plan', { version: r.version, priority: f.priority, assignee_id: f.assignee || null, expected_ready_on: f.expected || null }); },
        after: refreshAll
      });
    });
  };
  /* سيارة بديلة: عهدة من نوع «بديلة» للسائق نفسه، وسيارته تبقى في عهدته في المركز */
  BT.actions['mnt-spare'] = function () {
    var r = req();
    A.all('/vehicles', { status: 'available' }).then(function (vehicles) {
      vehicles = vehicles.filter(function (x) { return x.status === 'available' && x.id !== r.vehicle.id; });
      if (!vehicles.length) { BT.toast('لا توجد سيارة متاحة الآن', { type: 'warning' }); return; }
      A.formModal({
        title: 'سيارة بديلة للسائق', subtitle: (r.driver ? api.name(r.driver.name) + ' · ' : '') + 'سيارته ' + r.vehicle.plate_number + ' في المركز', icon: 'car', size: 'lg',
        body: h`<div class="form-grid"><div class="full">${A.picker({ name: 'spare', label: 'السيارة البديلة', required: true, items: vehicles.map(function (x) { return { id: x.id, label: A.vehicleLabel(x) }; }), hint: 'السيارات المتاحة فقط' })}</div>
          ${BT.f.input({ name: 'km', label: 'قراءة العداد (كم)', required: true, num: true, min: 0 })}${BT.f.input({ name: 'at', label: 'وقت التسليم', type: 'datetime-local', optional: true, hint: 'اتركه للتسليم الآن' })}
          <div class="full">${BT.f.camera({ name: 'odo', label: 'صورة العداد', required: true, cta: 'صورة العداد', sub: 'إلزامية' })}</div></div>
          <div class="banner info fs-sm mt-12">${icon('info', 15)}<div>تبقى سيارته في عهدته أثناء الصيانة، ويعمل بالبديلة حتى يستلم سيارته: عندها تنتهي عهدة البديلة في نفس الخطوة بقراءتها وصورتها من تطبيقه. لا يحمل السائق إلا بديلة واحدة، ولا تُسلَّم البديلة لغيره قبل إرجاعها.</div></div>`,
        submitText: 'تسليم البديلة', done: 'سُلّمت السيارة البديلة',
        submit: function (f) {
          return api.upload(f.odo[0]).then(function (up) {
            return api.post('/maintenance/requests/' + r.id + '/replacement', { vehicle_id: A.picked('spare', f.spare), odometer_km: Math.round(f.km), photo_sha256: up.sha256, started_at: fmt.kwIso(f.at) });
          });
        },
        after: refreshAll
      });
    }, api.fail).catch(function () {});
  };
  BT.actions['mnt-spare-back'] = function () {
    var r = req(), spare = openReplacement(r);
    A.formModal({
      title: 'إرجاع السيارة البديلة', subtitle: spare.vehicle.plate_number, icon: 'undo-2',
      body: h`<div class="form-grid">${BT.f.input({ name: 'km', label: 'قراءة العداد (كم)', required: true, num: true, min: 0 })}${BT.f.input({ name: 'at', label: 'وقت الإرجاع', type: 'datetime-local', optional: true, hint: 'اتركه للإرجاع الآن' })}
        <div class="full">${BT.f.camera({ name: 'odo', label: 'صورة العداد', required: true, cta: 'صورة العداد', sub: 'إلزامية' })}</div></div>`,
      submitText: 'إرجاع', done: 'أُرجعت السيارة البديلة',
      submit: function (f) {
        return api.upload(f.odo[0]).then(function (up) {
          return api.post('/maintenance/requests/' + r.id + '/replacement/return', { odometer_km: Math.round(f.km), photo_sha256: up.sha256, ended_at: fmt.kwIso(f.at) });
        });
      },
      after: refreshAll
    });
  };
  BT.actions['mnt-approve'] = function () {
    A.formModal({ title: 'اعتماد طلب الصيانة', icon: 'check', size: 'sm', body: h`<div class="form">${BT.f.textarea({ name: 'note', label: 'ملاحظة', optional: true, rows: 2 })}</div>`, submitText: 'اعتماد', done: 'اعتُمد الطلب',
      submit: function (f) { return api.post('/maintenance/requests/' + req().id + '/approve', { note: f.note || null }); }, after: refreshAll });
  };
  BT.actions['mnt-reject'] = function () {
    A.confirmRun({ title: 'رفض طلب الصيانة', tone: 'danger', confirmText: 'رفض', reason: { label: 'السبب (يراه السائق)', required: true }, run: function (reason) { return api.post('/maintenance/requests/' + req().id + '/reject', { reason: reason }); }, done: 'رُفض الطلب', after: refreshAll });
  };
  BT.actions['mnt-cancel'] = function () {
    A.confirmRun({ title: 'إلغاء طلب الصيانة', tone: 'danger', confirmText: 'إلغاء الطلب', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/maintenance/requests/' + req().id + '/cancel', { reason: reason }); }, done: 'أُلغي الطلب', after: refreshAll });
  };
  BT.actions['mnt-review'] = function () {
    A.formModal({ title: 'مراجعة الصيانة الطارئة', icon: 'shield-check', size: 'sm', body: h`<div class="form">${BT.f.textarea({ name: 'note', label: 'ملاحظة المراجعة', optional: true, rows: 2 })}</div>`, submitText: 'تمت المراجعة', done: 'سُجّلت المراجعة',
      submit: function (f) { return api.post('/maintenance/requests/' + req().id + '/review-emergency', { note: f.note || null }); }, after: refreshAll });
  };
  BT.actions['mnt-picked'] = function () {
    // يظهر فقط حين لا يحمل السيارة سائق (أرجعها المكتب أثناء الصيانة مثلاً): وإلا يؤكد السائق الاستلام من تطبيقه
    A.confirmRun({ title: 'استلام السيارة من المركز', message: 'لا يحمل السيارة سائق الآن: تعود «متاحة» للتسليم لسائق.', confirmText: 'تم الاستلام', run: function () { return api.post('/maintenance/requests/' + req().id + '/picked-up'); }, done: 'سُجّل الاستلام', after: refreshAll });
  };
  BT.actions['mnt-refer'] = function () {
    api.get('/maintenance/centers', { active: true }).then(function (centers) {
      if (!centers.length) { BT.toast('أضف مركز صيانة أولاً من تبويب المراكز', { type: 'warning' }); return; }
      A.formModal({
        title: req().status === 'referred' ? 'تغيير المركز' : 'إحالة لمركز صيانة', subtitle: req().vehicle.plate_number + ' · طلب #' + req().number, icon: 'send',
        body: h`<div class="form">${BT.f.select({ name: 'center', label: 'المركز', required: true, value: req().center && req().center.id, options: centers.map(function (c) { return { v: c.id, t: c.name + (c.specialty ? ' — ' + c.specialty : '') + (c.at_center ? ' · لديه ' + c.at_center : '') }; }) })}
          ${BT.f.textarea({ name: 'note', label: 'ملاحظة للمركز', optional: true, rows: 2 })}<div class="hint">يظهر الطلب فوراً في بوابة المركز.</div></div>`,
        submitText: 'إحالة', done: 'أُحيل الطلب للمركز',
        submit: function (f) { return api.post('/maintenance/requests/' + req().id + '/refer', { center_id: f.center, note: f.note || null }); }, after: refreshAll
      });
    }, api.fail).catch(function () {});
  };

  /* ================= الصيانة الدورية: بالتاريخ و/أو بالكيلومترات ================= */
  var SCH_TONE = { overdue: 'r', due: 'o', unknown: 'n', ok: 'g', inactive: 'n' };
  function schState(x) { return h`<span data-sch-state="${x.state}">${BT.pill(api.t('schedule_state', x.state), SCH_TONE[x.state] || 'n')}</span>`; }
  function schEvery(x) {
    return [x.every_days ? 'كل ' + fmt.int(x.every_days) + ' يوم' : null, x.every_km ? 'كل ' + fmt.km(x.every_km) + ' كم' : null].filter(Boolean).join(' أو ');
  }
  function schDue(x) {
    var parts = [];
    if (x.due_on) parts.push(h`<span class="num">${fmt.date(x.due_on)}</span> <small class="muted">${x.days_left < 0 ? 'متأخرة ' + fmt.int(-x.days_left) + ' يوم' : 'بعد ' + fmt.int(x.days_left) + ' يوم'}</small>`);
    if (x.due_km != null) parts.push(h`<span class="num">${fmt.km(x.due_km)}</span> كم${x.km_left != null ? h` <small class="muted">${x.km_left <= 0 ? 'تجاوزها بـ ' + fmt.km(-x.km_left) + ' كم' : 'باقي ' + fmt.km(x.km_left) + ' كم'}</small>` : ''}`);
    else if (x.km_state) parts.push(h`<small class="muted" data-km-unknown>${api.t('schedule_state', x.km_state)}: الكيلومترات لا تُحسب</small>`);
    return h`${parts.map(function (p, i) { return h`${i ? raw('<br>') : ''}${p}`; })}`;
  }
  function schReading(x) {
    if (x.current_km == null) return raw('<span class="muted">لا توجد قراءة</span>');
    return h`<span class="num">${fmt.km(x.current_km)}</span> كم<span class="sub">${fmt.dt(x.current_km_at)}${x.reading_stale ? ' · قراءة قديمة' : ''}</span>`;
  }
  var SCH_COLS = [
    { key: 'vehicle', label: 'السيارة', render: function (x) { return M.vehicle(x.vehicle); } },
    { key: 'title', label: 'الصيانة', render: function (x) { return h`<b>${x.title}</b><span class="sub">${M.kind(x.kind)} · ${schEvery(x)}</span>`; } },
    { key: 'last', label: 'آخر مرة', render: function (x) { return h`<span class="num">${fmt.date(x.last_done_on)}</span>${x.last_done_km != null ? h`<span class="sub num">${fmt.km(x.last_done_km)} كم</span>` : ''}`; } },
    { key: 'due', label: 'تستحق', render: schDue },
    { key: 'reading', label: 'العداد الآن', render: schReading },
    { key: 'state', label: 'الحالة', render: function (x) { return h`${schState(x)}${x.open_request ? h`<span class="sub"><a href="#/maintenance/${x.open_request.id}">طلب #${x.open_request.number}</a> جارٍ</span>` : ''}`; } }
  ];
  function schedulesPanel(el) {
    A.load(el, api.get('/maintenance/schedules'), function (rows) {
      setTimeout(function () {
        var box = el.querySelector('[data-t]');
        if (!box) return;
        BT.table(box, {
          rows: rows,
          search: { placeholder: 'اللوحة أو اسم الصيانة…', text: function (x) { return (x.vehicle.plate_number || '') + ' ' + x.title; } },
          chips: { value: rows.some(function (x) { return x.state === 'overdue' || x.state === 'due'; }) ? 'attention' : '', all: 'الكل', match: function (x, c) { return c === 'attention' ? x.state === 'overdue' || x.state === 'due' : x.state === c; },
            options: [{ v: 'attention', t: 'تحتاج إجراء' }, { v: 'overdue', t: api.t('schedule_state', 'overdue') }, { v: 'due', t: api.t('schedule_state', 'due') }, { v: 'unknown', t: api.t('schedule_state', 'unknown') }] },
          columns: SCH_COLS,
          rowClick: function (x) { scheduleView(x, function () { schedulesPanel(el); }); },
          tools: api.can('maintenance.create') ? h`<button type="button" class="btn btn-primary" data-sch-new>${icon('plus', 15)} صيانة دورية</button>` : '',
          empty: { icon: 'calendar', title: 'لا توجد صيانة دورية هنا', text: 'أضف لكل سيارة ما يتكرر: تغيير الزيت كل 5,000 كم، الفحص كل 6 أشهر…' }
        });
        var add = el.querySelector('[data-sch-new]');
        if (add) add.onclick = function () { scheduleForm(null, null, function () { schedulesPanel(el); }); };
      });
      return h`<div class="hint mb-12">تستحق الصيانة بعد عدد الأيام أو الكيلومترات من آخر مرة نُفذت، أيهما أسبق. الكيلومترات من آخر قراءة عداد مصوّرة للسيارة؛ إن لم توجد قراءة لا تُحسب ولا تُخمَّن. ساعات المحرك غير متاحة: النظام لا يستقبل بياناتها. تُنبَّه الإدارة يومياً بما يستحق قريباً أو تأخر، والطلب المنفّذ لها يسجّلها منفّذة عند استلام السيارة.</div><div class="card"><div data-t></div></div>`;
    }).catch(function () {});
  }
  function scheduleView(x, done) {
    var manage = api.can('maintenance.create');
    var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
    if (manage && x.active) {
      btns.push({ label: 'تعديل', cls: 'btn-outline', icon: 'pencil', close: false, onClick: function (dlg) { scheduleForm(x, null, function () { dlg.close(); done(); }); } });
      btns.push({ label: 'نُفذت', cls: 'btn-outline', icon: 'check', close: false, onClick: function (dlg) { scheduleDone(x, function () { dlg.close(); done(); }); } });
      if (!x.open_request) btns.push({ label: 'طلب صيانة لها', cls: 'btn-primary', icon: 'wrench', close: true, onClick: function () { newRequest(Object.assign({ id: x.vehicle.id }, x.vehicle, { plate_number: x.vehicle.plate_number }), x); } });
    }
    BT.drawer.open({
      title: x.title, subtitle: (x.vehicle.plate_number || '') + ' · ' + schEvery(x), icon: 'calendar', size: 'lg',
      body: h`<div class="mb-12">${schState(x)}</div>${BT.kv([
        ['السيارة', h`<a href="#/vehicles/${x.vehicle.id}" class="plate">${x.vehicle.plate_number}</a>`],
        ['النوع', M.kind(x.kind)], ['التكرار', schEvery(x)],
        ['آخر مرة', h`<span class="num">${fmt.date(x.last_done_on)}</span>${x.last_done_km != null ? h` · <span class="num">${fmt.km(x.last_done_km)}</span> كم` : ''}`],
        ['تستحق', schDue(x)], ['العداد الآن', schReading(x)],
        x.open_request ? ['طلب جارٍ', h`<a href="#/maintenance/${x.open_request.id}">طلب #${x.open_request.number}</a> · ${M.status(x.open_request.status)}`] : null,
        x.notes ? ['ملاحظات', x.notes] : null
      ].filter(Boolean))}`,
      buttons: btns
    });
  }
  function scheduleForm(x, vehicle, done) {
    var jobs = x || vehicle ? Promise.resolve(null) : allVehicles();
    jobs.then(function (vehicles) {
      A.formModal({
        title: x ? 'تعديل الصيانة الدورية' : 'صيانة دورية', subtitle: x ? x.vehicle.plate_number : vehicle ? vehicle.plate_number : '', icon: 'calendar',
        body: h`<div class="form-grid">
          ${vehicles ? h`<div class="full">${A.picker({ name: 'vehicle', label: 'السيارة', required: true, items: vehicles.map(function (v) { return { id: v.id, label: A.vehicleLabel(v) }; }) })}</div>` : ''}
          ${BT.f.input({ name: 'title', label: 'الاسم', required: true, value: x ? x.title : '', placeholder: 'تغيير الزيت، فحص دوري…' })}
          ${BT.f.select({ name: 'kind', label: 'النوع', placeholder: false, options: M.kindOptions(), value: x ? x.kind : 'periodic' })}
          ${BT.f.input({ name: 'days', label: 'كل (يوم)', optional: true, num: true, min: 1, value: x && x.every_days })}
          ${BT.f.input({ name: 'km', label: 'كل (كم)', optional: true, num: true, min: 100, value: x && x.every_km })}
          ${x ? '' : h`${BT.f.input({ name: 'last_on', label: 'آخر مرة نُفذت', type: 'date', optional: true, max: BT.config.today, hint: 'اتركه: من اليوم' })}${BT.f.input({ name: 'last_km', label: 'العداد آخر مرة (كم)', optional: true, num: true, min: 0, hint: 'اتركه: آخر قراءة للسيارة' })}`}
          ${BT.f.textarea({ name: 'notes', label: 'ملاحظات', optional: true, full: true, rows: 2, value: x ? x.notes : '' })}
          ${x ? h`<div class="full">${BT.f.switch({ name: 'active', label: 'نشطة (الموقوفة لا تُتابع ولا تُنبَّه)', checked: x.active })}</div>` : ''}</div>
          <div class="hint mt-8">حدد الأيام أو الكيلومترات أو الاثنين: تستحق بأيهما أسبق.</div>`,
        submitText: 'حفظ', done: 'تم الحفظ',
        submit: function (f, dlg) {
          var num = function (v) { return v === '' || v == null ? null : Math.round(v); };
          if (num(f.days) == null && num(f.km) == null) return Promise.reject(new Error('حدد كل كم يوماً أو كل كم كيلومتراً'));
          if (x) return api.put('/maintenance/schedules/' + x.id, { version: x.version, title: f.title, kind: f.kind, every_days: num(f.days), every_km: num(f.km), notes: f.notes || null, active: dlg.form.querySelector('[name=active]').checked });
          var vid = vehicle ? vehicle.id : A.picked('vehicle', f.vehicle);
          return api.post('/maintenance/schedules', { vehicle_id: vid, title: f.title, kind: f.kind, every_days: num(f.days), every_km: num(f.km), last_done_on: f.last_on || null, last_done_km: num(f.last_km), notes: f.notes || null });
        },
        after: done
      });
    }, api.fail).catch(function () {});
  }
  function scheduleDone(x, done) {
    A.formModal({
      title: 'تسجيل تنفيذ الصيانة', subtitle: x.title + ' · ' + x.vehicle.plate_number, icon: 'check', size: 'sm',
      body: h`<div class="form">${BT.f.input({ name: 'on', label: 'تاريخ التنفيذ', type: 'date', required: true, value: BT.config.today, max: BT.config.today })}
        ${BT.f.input({ name: 'km', label: 'العداد عند التنفيذ (كم)', optional: true, num: true, min: 0, value: x.current_km })}
        ${BT.f.textarea({ name: 'note', label: 'أين نُفذت (ورشة أخرى…)', optional: true, rows: 2 })}
        <div class="hint">للتنفيذ خارج طلبات النظام؛ الطلب المرتبط بها يسجّلها تلقائياً عند الاستلام.</div></div>`,
      submitText: 'تسجيل', done: 'سُجّل التنفيذ',
      submit: function (f) { return api.post('/maintenance/schedules/' + x.id + '/done', { done_on: f.on, done_km: f.km === '' || f.km == null ? null : Math.round(f.km), note: f.note || null }); },
      after: done
    });
  }

  /* الطلبات المرتبطة بعهدة: طلبات سيارتها أثناءها، والطلب الذي أعطاها كسيارة بديلة (من درج العهدة) */
  A.custodyMaintenance = function (el, custody) {
    if (!el || !api.can('maintenance.view')) return;
    api.get('/maintenance/requests', { custody_id: custody.id, limit: 20 }).then(function (rows) {
      if (!document.contains(el)) return;
      BT.render(el, rows.length ? h`<div class="section-t mt-16">الصيانة خلال العهدة</div><div class="list" data-custody-mnt>${rows.map(function (r) {
        return h`<a class="li" href="#/maintenance/${r.id}"><span class="li-ic">${icon('wrench', 16)}</span><div class="li-main"><div class="li-t"><span class="num">#${r.number}</span> ${M.kind(r.kind)}${r.center ? ' · ' + r.center.name : ''}${custody.kind === 'replacement' ? ' · بديلة عن ' + (r.vehicle.plate_number || '') : ''}</div><div class="li-d">${fmt.dt(r.received_at || r.created_at)}${r.stay_seconds != null ? ' · بقيت ' + M.dur(r.stay_seconds) : ''}</div></div>${M.status(r.status)}</a>`;
      })}</div>` : '');
    }, function () {});
  };

  /* ================= الفواتير ================= */
  var INV_CHIPS = { pending: { status: 'pending' }, unpaid: { status: 'approved', payment_status: 'unpaid' }, paid: { payment_status: 'paid' }, rejected: { status: 'rejected' } };
  function invoicesPanel(el) {
    // المحاسبة الدورية مع مركز: فواتيره وحده (المعتمدة غير المدفوعة هي مستحقاته)
    var center = '';
    BT.render(el, h`<div class="card">${api.can('maintenance.view') ? h`<div class="toolbar" style="margin:0 0 8px"><select class="input" data-inv-center style="max-width:280px" aria-label="المركز"><option value="">كل المراكز</option></select></div>` : ''}<div data-t></div></div>`);
    var sel = el.querySelector('[data-inv-center]');
    if (sel) {
      api.get('/maintenance/centers').then(function (cs) {
        cs.forEach(function (c) { var o = document.createElement('option'); o.value = c.id; o.textContent = c.name; sel.appendChild(o); });
      }, function () { sel.remove(); });
      sel.addEventListener('change', function () { center = sel.value; t.refresh(); });
    }
    var t = BT.table(el.querySelector('[data-t]'), {
      fetch: function (s) { return api.get('/maintenance/invoices', Object.assign({ limit: s.limit, offset: s.offset, center_id: center }, INV_CHIPS[s.chip] || {})); },
      chips: { value: 'pending', all: 'الكل', options: [{ v: 'pending', t: 'بانتظار الاعتماد' }, { v: 'unpaid', t: 'معتمدة غير مدفوعة' }, { v: 'paid', t: 'مدفوعة' }, { v: 'rejected', t: 'مرفوضة' }] },
      columns: [
        { key: 'number', label: 'الفاتورة', render: function (i) { return h`<span class="num">${i.number}</span><span class="sub">${fmt.date(i.invoice_date)}</span>`; } },
        { key: 'center', label: 'المركز', render: function (i) { return i.center.name; } },
        { key: 'request', label: 'السيارة / الطلب', render: function (i) { return i.request ? h`<a href="#/maintenance/${i.request.id}"><span class="plate">${i.vehicle_plate}</span> <span class="num">#${i.request.number}</span></a>` : h`<span class="muted">${api.company(i.company_id)}</span>`; } },
        { key: 'total', label: 'الإجمالي', num: true, render: function (i) { return h`${BT.amt(Number(i.total))}${i.quote_amount != null ? h`<span class="sub">العرض ${fmt.money(i.quote_amount)}</span>` : ''}`; } },
        { key: 'status', label: 'الحالة', render: function (i) { return h`${M.invStatus(i)} ${M.flags(i.flags)}`; } }
      ],
      rowClick: function (i) { invoiceView(i, function () { t.refresh(); A.refreshCounts(); }); },
      empty: { icon: 'receipt-text', title: 'لا توجد فواتير هنا' }
    });
  }
  function invoiceView(i, done) {
    var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
    if (i.status === 'pending' && api.can('invoices.approve')) {
      btns.push({ label: 'رفض', cls: 'btn-ghost', icon: 'x', close: false, onClick: function (dlg) {
        A.confirmRun({ title: 'رفض الفاتورة', tone: 'danger', confirmText: 'رفض', reason: { label: 'السبب (يراه المركز)', required: true }, run: function (reason) { return api.post('/maintenance/invoices/' + i.id + '/reject', { reason: reason }); }, done: 'رُفضت الفاتورة', after: function () { dlg.close(); done(); } });
      } });
      btns.push({ label: 'اعتماد', cls: 'btn-primary', icon: 'check', close: false, onClick: function (dlg) {
        A.confirmRun({ title: 'اعتماد الفاتورة', message: 'راجعت البيانات المدخلة مقابل الملف المرفق؟', confirmText: 'اعتماد', run: function () { return api.post('/maintenance/invoices/' + i.id + '/approve'); }, done: 'اعتُمدت الفاتورة', after: function () { dlg.close(); done(); } });
      } });
    }
    if (i.status === 'approved' && i.payment_status === 'unpaid' && api.can('finance.create')) {
      btns.push({ label: 'تسجيل الدفع', cls: 'btn-primary', icon: 'banknote', close: false, onClick: function (dlg) {
        A.formModal({ title: 'تسجيل دفع الفاتورة', icon: 'banknote', size: 'sm', body: h`<div class="form">${BT.f.input({ name: 'ref', label: 'مرجع الدفع (تحويل أو شيك)', optional: true })}</div>`, submitText: 'تم الدفع', done: 'سُجّل الدفع',
          submit: function (f) { return api.post('/maintenance/invoices/' + i.id + '/paid', { payment_ref: f.ref || null }); }, after: function () { dlg.close(); done(); } });
      } });
    }
    BT.drawer.open({
      title: h`فاتورة <span class="num">${i.number}</span> · ${i.center.name}`, subtitle: fmt.date(i.invoice_date) + (i.vehicle_plate ? ' · ' + i.vehicle_plate : ''), icon: 'receipt-text', size: 'lg',
      body: h`<div class="mb-12">${M.invStatus(i)} ${M.flags(i.flags)}</div>
        ${i.flags.indexOf('differs_from_quote') > -1 ? h`<div class="banner warn mb-12">${icon('triangle-alert', 16)}<div>الإجمالي ${fmt.money(i.total)} يختلف عن العرض المعتمد ${fmt.money(i.quote_amount)} د.ك.</div></div>` : ''}
        ${i.flags.indexOf('duplicate_number') > -1 ? h`<div class="banner warn mb-12">${icon('copy', 16)}<div>رقم الفاتورة مسجّل من قبل لنفس المركز: تأكد أنها ليست مكررة.</div></div>` : ''}
        ${BT.kv([['الإجمالي', BT.amt(Number(i.total)), 'total'], ['الشركة', api.company(i.company_id)], ['أدخلها', i.created_by || '—'], i.decided_by ? ['قرار', i.decided_by + ' · ' + fmt.dt(i.decided_at)] : null, i.reason ? ['السبب', i.reason] : null, i.paid_at ? ['الدفع', fmt.dt(i.paid_at) + (i.payment_ref ? ' · ' + i.payment_ref : '')] : null].filter(Boolean))}
        <div class="section-t mt-16">البنود</div>${M.itemsTable(i.items)}
        <div class="mt-16"><a class="btn btn-outline" href="${api.url('/maintenance/invoices/' + i.id + '/file')}" target="_blank" rel="noopener">${icon('file-text', 15)} فتح ملف الفاتورة</a></div>`,
      buttons: btns
    });
  }

  /* ---------- فاتورة يدخلها المحاسب لمركز (بلا طلب في النظام) ---------- */
  function officeInvoice() {
    api.get('/maintenance/centers').then(function (centers) {
      if (!centers.length) { BT.toast('أضف مركز صيانة أولاً', { type: 'warning' }); return; }
      var ed;
      A.formModal({
        title: 'فاتورة من مركز صيانة', subtitle: 'لفواتير المراكز غير المرتبطة بطلب في النظام؛ فواتير الطلبات يدخلها المركز من بوابته', icon: 'receipt-text', size: 'lg',
        body: h`<div class="form-grid">${BT.f.select({ name: 'center', label: 'المركز', required: true, options: centers.map(function (c) { return { v: c.id, t: c.name }; }) })}
          ${BT.f.select({ name: 'company', label: 'الشركة', required: true, options: api.companyOptions() })}
          ${BT.f.input({ name: 'number', label: 'رقم الفاتورة', required: true })}${BT.f.date({ name: 'date', label: 'التاريخ', required: true, value: BT.config.today, max: BT.config.today })}
          ${BT.f.upload({ name: 'file', label: 'ملف الفاتورة', required: true, full: true })}</div><div class="mt-16">${M.itemsHtml}</div>
          <div class="form mt-12">${BT.f.textarea({ name: 'notes', label: 'ملاحظات', optional: true, rows: 2 })}</div>`,
        onOpen: function (dlg) { ed = M.itemsEditor(dlg.body); },
        submitText: 'حفظ', done: 'سُجّلت الفاتورة بانتظار الاعتماد',
        submit: function (f) {
          if (!ed.valid() || ed.total() <= 0) { BT.toast('أكمل بنود الفاتورة', { type: 'error' }); return false; }
          return upload(f.file[0]).then(function (sha) {
            return api.post('/maintenance/invoices', { center_id: f.center, company_id: Number(f.company), number: f.number, invoice_date: f.date, total: ed.total().toFixed(3), items: ed.read(), file_sha256: sha, notes: f.notes || null });
          });
        },
        after: function () { A.go('maintenance?tab=invoices'); A.refreshCounts(); }
      });
    }, api.fail).catch(function () {});
  }

  /* ================= المراكز وحسابات البوابة ================= */
  function centersPanel(el) {
    A.load(el, api.get('/maintenance/centers'), function (rows) {
      setTimeout(function () {
        var t = el.querySelector('[data-t]');
        if (!t) return;
        BT.table(t, {
          rows: rows,
          search: { placeholder: 'اسم المركز…', text: function (c) { return c.name + ' ' + (c.specialty || ''); } },
          columns: [
            { key: 'name', label: 'المركز', render: function (c) { return h`<b>${c.name}</b><span class="sub">${c.specialty || ''}</span>`; } },
            { key: 'phone', label: 'التواصل', render: function (c) { return h`${c.contact_name || ''}<span class="sub ltr">${c.phone || ''}</span>`; } },
            { key: 'at_center', label: 'سيارات لديه', num: true },
            { key: 'users', label: 'حسابات البوابة', num: true },
            { key: 'is_active', label: 'الحالة', render: function (c) { return c.is_active ? BT.pill('نشط', 'g') : BT.pill('موقوف', 'n'); } }
          ],
          rowClick: function (c) { centerView(c); },
          tools: api.can('maintenance_centers.manage') ? A.btn('إضافة مركز', { icon: 'plus', cls: 'btn-primary', action: 'mnt-center-new' }) : '',
          empty: { icon: 'store', title: 'لا توجد مراكز صيانة', text: 'أضف المراكز التي تتعامل معها، ثم أنشئ لكل مركز حساباً لبوابته' }
        });
      });
      return h`<div class="card"><div data-t></div></div>`;
    }).catch(function () {});
  }
  BT.actions['mnt-center-new'] = function () { centerForm(null); };
  function centerForm(c) {
    A.formModal({
      title: c ? 'تعديل مركز صيانة' : 'إضافة مركز صيانة', icon: 'store',
      body: h`<div class="form-grid">${BT.f.input({ name: 'name', label: 'الاسم', required: true, value: c && c.name })}${BT.f.input({ name: 'specialty', label: 'التخصص', optional: true, value: c && c.specialty, placeholder: 'ميكانيكا، كهرباء، سمكرة…' })}
        ${BT.f.input({ name: 'contact_name', label: 'جهة الاتصال', optional: true, value: c && c.contact_name })}${BT.f.input({ name: 'phone', label: 'الهاتف', optional: true, value: c && c.phone })}
        ${BT.f.input({ name: 'email', label: 'البريد', optional: true, value: c && c.email })}${BT.f.input({ name: 'address', label: 'العنوان', optional: true, value: c && c.address })}
        ${BT.f.textarea({ name: 'notes', label: 'ملاحظات', optional: true, full: true, rows: 2, value: c && c.notes })}
        ${c ? h`<div class="full">${BT.f.switch({ name: 'is_active', label: 'نشط (الموقوف لا يستقبل إحالات وتتوقف حساباته)', checked: c.is_active })}</div>` : ''}</div>`,
      submitText: 'حفظ', done: 'تم الحفظ',
      submit: function (f, dlg) {
        var body = { name: f.name, specialty: f.specialty || null, contact_name: f.contact_name || null, phone: f.phone || null, email: f.email || null, address: f.address || null, notes: f.notes || null };
        if (!c) return api.post('/maintenance/centers', body);
        body.version = c.version; body.is_active = dlg.form.querySelector('[name=is_active]').checked;
        return api.put('/maintenance/centers/' + c.id, body);
      },
      after: function () { BT.closeAll(); A.go('maintenance?tab=centers'); A.router.refresh(); }
    });
  }
  function centerView(c) {
    var manage = api.can('maintenance_centers.manage');
    var d = BT.drawer.open({
      title: c.name, subtitle: c.specialty || '', icon: 'store', size: 'lg',
      body: h`${BT.kv([['جهة الاتصال', c.contact_name || '—'], ['الهاتف', c.phone ? h`<span class="ltr">${c.phone}</span>` : '—'], ['البريد', c.email || '—'], ['العنوان', c.address || '—'], ['سيارات لديه الآن', String(c.at_center)], ['الحالة', c.is_active ? 'نشط' : 'موقوف']])}
        ${c.notes ? h`<div class="fs-sm mt-12" style="white-space:pre-wrap">${c.notes}</div>` : ''}
        <div class="between mt-16 mb-8"><div class="section-t" style="margin:0">حسابات البوابة</div>${manage ? h`<div class="flex gap-8"><button type="button" class="btn btn-sm btn-ghost" data-user-link>${icon('link', 14)} ربط حساب موجود</button><button type="button" class="btn btn-sm btn-soft" data-user-add>${icon('user-plus', 14)} إضافة حساب</button></div>` : ''}</div>
        <div data-users>${A.spinner()}</div>
        <div class="hint mt-8">حساب المركز يرى فقط السيارات المحالة لمركزه، ويدخل من صفحة الدخول نفسها.</div>`,
      buttons: [{ label: 'إغلاق', cls: 'btn-ghost' }].concat(manage ? [{ label: 'تعديل', cls: 'btn-outline', icon: 'pencil', close: false, onClick: function () { centerForm(c); } }] : [])
    });
    function loadUsers() {
      var box = d.el.querySelector('[data-users]');
      if (!api.can('maintenance_centers.view')) { BT.render(box, raw('<div class="muted fs-sm">يحتاج صلاحية عرض المراكز</div>')); return; }
      api.get('/maintenance/centers/' + c.id + '/users').then(function (users) { drawUsers(users); }, function (err) { BT.render(box, BT.empty('wifi-off', api.message(err))); });
    }
    function drawUsers(users) {
      var box = d.el.querySelector('[data-users]');
      BT.render(box, users.length ? h`<div class="list">${users.map(function (u) {
        return h`<div class="li"><span class="li-ic ${u.is_active ? 'g' : ''}">${icon('user-round', 16)}</span><div class="li-main"><div class="li-t">${u.full_name} <span class="muted fs-sm ltr">${u.username}</span></div><div class="li-d">${u.last_login_at ? 'آخر دخول ' + fmt.since(u.last_login_at) : 'لم يدخل بعد'}</div></div>${u.is_active ? '' : BT.pill('موقوف', 'n')}${manage ? h`<button type="button" class="btn btn-sm btn-ghost" data-user-toggle="${u.id}" data-on="${u.is_active ? '0' : '1'}">${u.is_active ? 'إيقاف' : 'تفعيل'}</button>` : ''}</div>`;
      })}</div>` : BT.empty('users', 'لا توجد حسابات', 'أنشئ حساباً ليستلم المركز السيارات ويحدّث حالتها'));
    }
    loadUsers();
    BT.on(d.el, 'click', '[data-user-toggle]', function (e, b) {
      b.disabled = true;
      api.put('/maintenance/centers/' + c.id + '/users/' + b.getAttribute('data-user-toggle'), { is_active: b.getAttribute('data-on') === '1' }).then(drawUsers, function (err) { b.disabled = false; BT.toast(api.message(err), { type: 'error' }); });
    });
    BT.on(d.el, 'click', '[data-user-link]', function () {
      A.formModal({
        title: 'ربط حساب موجود بـ ' + c.name, icon: 'link', size: 'sm',
        body: h`<div class="form">${BT.f.input({ name: 'username', label: 'اسم المستخدم', required: true })}<div class="hint">لحساب بوابة اتعمل من صفحة المستخدمين ومش مربوط بمركز. حسابات الإدارة ما تتربطش.</div></div>`,
        submitText: 'ربط الحساب', done: 'اتربط الحساب بالمركز',
        submit: function (f) { return api.post('/maintenance/centers/' + c.id + '/users/link', { username: f.username }); },
        after: drawUsers
      });
    });
    BT.on(d.el, 'click', '[data-user-add]', function () {
      A.formModal({
        title: 'حساب بوابة لـ ' + c.name, icon: 'user-plus', size: 'sm',
        body: h`<div class="form">${BT.f.input({ name: 'full_name', label: 'الاسم', required: true })}${BT.f.input({ name: 'username', label: 'اسم المستخدم', required: true })}
          ${BT.f.input({ name: 'phone', label: 'الجوال', optional: true })}${BT.f.input({ name: 'password', label: 'كلمة مرور مؤقتة', type: 'password', required: true, hint: 'يُطلب تغييرها عند أول دخول' })}</div>`,
        submitText: 'إنشاء الحساب', done: 'أُنشئ الحساب',
        submit: function (f) { return api.post('/maintenance/centers/' + c.id + '/users', { full_name: f.full_name, username: f.username, phone: f.phone || null, password: f.password }); },
        after: drawUsers
      });
    });
  }

  /* ---------- تبويب الصيانة في ملف السيارة ---------- */
  A.vehicleMaintenance = function (el, vehicle) {
    A.load(el, Promise.all([api.get('/maintenance/requests', { vehicle_id: vehicle.id, limit: 20 }), api.get('/maintenance/schedules', { vehicle_id: vehicle.id })]), function (res) {
      var rows = res[0], schedules = res[1];
      return h`<div class="section-t">الصيانة الدورية</div>${schedules.length ? h`<div class="list mb-12" data-veh-schedules>${schedules.map(function (x) {
        return h`<button type="button" class="li" data-sch="${x.id}" style="width:100%;text-align:start"><span class="li-ic">${icon('calendar', 16)}</span><div class="li-main"><div class="li-t">${x.title} <small class="muted">${schEvery(x)}</small></div><div class="li-d">${schDue(x)}</div></div>${schState(x)}</button>`;
      })}</div>` : raw('<div class="muted fs-sm mb-12">لا توجد صيانة دورية لهذه السيارة</div>')}
        <div class="section-t">الطلبات</div>${rows.length ? h`<div class="list">${rows.map(function (r) {
        return h`<a class="li" href="#/maintenance/${r.id}"><span class="li-ic">${icon('wrench', 16)}</span><div class="li-main"><div class="li-t"><span class="num">#${r.number}</span> ${M.kind(r.kind)}${r.center ? ' · ' + r.center.name : ''}</div><div class="li-d">${fmt.dt(r.created_at)}${r.stay_seconds != null ? ' · بقيت ' + M.dur(r.stay_seconds) : ''}</div></div>${M.status(r.status)}</a>`;
      })}</div>` : BT.empty('wrench', 'لا توجد طلبات صيانة', '')}
        ${api.can('maintenance.create') ? h`<div class="mt-12 flex gap-8"><button type="button" class="btn btn-sm btn-soft" data-mnt-new>${icon('plus', 14)} طلب صيانة</button><button type="button" class="btn btn-sm btn-ghost" data-sch-new>${icon('calendar', 14)} صيانة دورية</button></div>` : ''}`;
    }).then(function (res) {
      var again = function () { A.vehicleMaintenance(el, vehicle); };
      var b = el.querySelector('[data-mnt-new]');
      if (b) b.onclick = function () { newRequest(vehicle); };
      var sn = el.querySelector('[data-sch-new]');
      if (sn) sn.onclick = function () { scheduleForm(null, vehicle, again); };
      A.delegate(el, 'click', '[data-sch]', function (e, btn) {
        var x = res[1].find(function (y) { return y.id === btn.getAttribute('data-sch'); });
        if (x) scheduleView(x, again);
      });
    }).catch(function () {});
  };
})();
