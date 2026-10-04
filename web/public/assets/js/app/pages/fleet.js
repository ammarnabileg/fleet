/* =====================================================================
   app/pages/fleet.js — السيارات، العُهد والتسليم، العداد
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;
  var STATUSES = ['available', 'assigned', 'maintenance', 'accident', 'inactive'];
  var POSITIONS = ['front', 'back', 'left', 'right', 'interior'];

  /* الكويت UTC+3 طوال السنة (بلا توقيت صيفي) */
  A.kwIso = function (local) { return local ? local + (local.length === 16 ? ':00' : '') + '+03:00' : null; };
  A.kwInput = function (iso) { var d = new Date(new Date(iso || Date.now()).getTime() + 3 * 3600 * 1000); return d.toISOString().slice(0, 16); };

  /* حقل اختيار بالبحث (datalist): يعيد المعرّف من النص المختار */
  A._pick = {};
  A.picker = function (o) { // {name, label, required, items:[{id, label}], value}
    var id = BT.uid('dl');
    A._pick[o.name] = o.items;
    var current = o.value ? (o.items.find(function (x) { return x.id === o.value; }) || {}).label : '';
    return h`<div class="field${o.full ? ' full' : ''}"><label for="f-${o.name}">${o.label}${o.required ? raw('<span class="req">*</span>') : ''}</label><input class="input" id="f-${o.name}" name="${o.name}" list="${id}" autocomplete="off"${o.required ? raw(' required') : ''} value="${current || ''}" placeholder="${o.placeholder || 'اكتب للبحث…'}" data-validate="picked" data-pick="${o.name}"><datalist id="${id}">${o.items.map(function (x) { return h`<option value="${x.label}"></option>`; })}</datalist>${o.hint ? h`<div class="hint">${o.hint}</div>` : ''}<div class="err-msg"></div></div>`;
  };
  A.picked = function (name, text) { var x = (A._pick[name] || []).find(function (i) { return i.label === text; }); return x ? x.id : null; };
  BT.validators.picked = function (v, el) { return A.picked(el.getAttribute('data-pick'), v) ? '' : 'اختر من القائمة'; };

  function photoFields(prefix, positions) {
    return h`<div class="cam-grid" style="grid-template-columns:repeat(${positions.length},minmax(0,1fr))">${positions.map(function (p) { return BT.f.camera({ name: prefix + p, cta: api.t('photo_position', p), sub: 'اختياري' }); })}</div>`;
  }
  function uploadPhotos(v, prefix, positions) {
    return Promise.all(positions.filter(function (p) { return v[prefix + p] && v[prefix + p][0]; }).map(function (p) {
      return api.upload(v[prefix + p][0]).then(function (f) { return { position: p, sha256: f.sha256 }; });
    }));
  }
  A.vehicleLabel = function (v) { return v.plate_number + (v.make ? ' — ' + v.make + ' ' + (v.model || '') : ''); };

  /* ================= السيارات ================= */
  BT.pages['vehicles'] = function (p, q) {
    A.setTitle('السيارات');
    var v = A.view(), filters = { company: '' };
    BT.render(v, h`${A.head('سجل السيارات', 'الحالة والعهدة الحالية وآخر قراءة عداد لكل سيارة', api.can('vehicles.create') ? A.btn('إضافة سيارة', { icon: 'plus', cls: 'btn-primary', action: 'vehicle-new' }) : '')}<div class="card"><div id="veh-table"></div></div>`);
    var el = document.getElementById('veh-table');
    var t = BT.table(el, {
      fetch: function (s) { return api.get('/vehicles', { q: s.q, status: s.chip, company_id: filters.company, limit: s.limit, offset: s.offset }); },
      search: { placeholder: 'رقم اللوحة أو الماركة أو رقم الشاصي…' },
      chips: { value: q.status || '', options: A.options('vehicle_status', STATUSES) },
      tools: api.companies.length > 1 ? h`<select class="select" data-f="company" aria-label="الشركة"><option value="">كل الشركات</option>${api.companyOptions().map(function (c) { return h`<option value="${c.v}">${c.t}</option>`; })}</select>` : null,
      columns: [
        { key: 'plate', label: 'اللوحة', render: function (x) { return h`<span class="plate">${x.plate_number}</span><span class="sub ltr">${[x.make, x.model, x.year].filter(Boolean).join(' ')}</span>`; } },
        { key: 'company', label: 'الشركة / الفرع', render: function (x) { return h`${api.company(x.company_id)}<span class="sub">${api.branch(x.branch_id)}</span>`; } },
        { key: 'status', label: 'الحالة', render: function (x) { return A.pill('vehicle_status', x.status); } },
        { key: 'driver', label: 'في عهدة', render: function (x) { return x.custody ? A.person(x.custody.driver, 'منذ ' + fmt.dt(x.custody.started_at)) : raw('<span class="muted">—</span>'); } },
        { key: 'km', label: 'العداد', num: true, render: function (x) { return x.last_odometer_km != null ? h`<span class="num">${fmt.km(x.last_odometer_km)}</span>` : '—'; } }
      ],
      rowClick: function (x) { A.go('vehicles/' + x.id); },
      empty: { icon: 'car', title: 'لا توجد سيارات مطابقة' }
    });
    A.refreshVehicles = t.refresh;
    BT.on(el, 'change', '[data-f]', function (e, s) { filters.company = s.value; t.refresh(); });
  };

  BT.actions['vehicle-new'] = function () { A.vehicleForm(null, function (x) { A.go('vehicles/' + x.id); }); };
  A.vehicleForm = function (x, after) {
    var editing = !!x;
    x = x || { company_id: (api.companyOptions()[0] || {}).v, branch_id: api.defaultBranch(), status: 'available' };
    A.formModal({
      title: editing ? 'تعديل السيارة' : 'إضافة سيارة', subtitle: editing ? x.plate_number : null, icon: editing ? 'pencil' : 'car', size: 'lg', done: editing ? 'تم حفظ التعديلات' : 'تمت إضافة السيارة',
      body: h`<div class="form-grid">
        ${BT.f.input({ name: 'plate_number', label: 'رقم اللوحة', required: true, value: x.plate_number, placeholder: '18/23456' })}
        ${BT.f.input({ name: 'vin', label: 'رقم الشاصي (VIN)', optional: true, value: x.vin, maxlength: 17 })}
        ${BT.f.input({ name: 'make', label: 'الماركة', optional: true, value: x.make })}${BT.f.input({ name: 'model', label: 'الموديل', optional: true, value: x.model })}
        ${BT.f.input({ name: 'year', label: 'سنة الصنع', optional: true, value: x.year, num: true, min: 1990, max: 2100 })}${BT.f.input({ name: 'color', label: 'اللون', optional: true, value: x.color })}
        ${BT.f.select({ name: 'company_id', label: 'الشركة المالكة', required: true, value: x.company_id, options: api.companyOptions(), placeholder: false })}
        ${BT.f.select({ name: 'branch_id', label: 'الفرع', required: true, value: x.branch_id, options: api.branchOptions(), placeholder: false })}
        ${editing ? BT.f.select({ name: 'status', label: 'الحالة', required: true, value: x.status, placeholder: false, options: A.options('vehicle_status', STATUSES.filter(function (s) { return s !== 'assigned' || x.status === 'assigned'; })), hint: '«في العهدة» تُضبط تلقائياً بالتسليم والاستلام' }) : BT.f.input({ name: 'last_odometer_km', label: 'العداد الحالي (كم)', optional: true, num: true, min: 0 })}
      </div>`,
      submit: function (v) {
        var body = { plate_number: v.plate_number.trim(), vin: v.vin || null, make: v.make || null, model: v.model || null, year: v.year === '' ? null : v.year, color: v.color || null, company_id: +v.company_id, branch_id: +v.branch_id };
        if (!editing) { body.last_odometer_km = v.last_odometer_km === '' ? null : v.last_odometer_km; return api.post('/vehicles', body); }
        var changes = { version: x.version };
        Object.keys(body).forEach(function (k) { if (body[k] !== (x[k] == null ? null : x[k])) changes[k] = body[k]; });
        if (v.status !== x.status) changes.status = v.status;
        return api.patch('/vehicles/' + x.id, changes);
      },
      after: after
    });
  };

  /* ---------- ملف السيارة ---------- */
  BT.pages['vehicles/:id'] = function (p) {
    A.setTitle('ملف سيارة', [['السيارات', 'vehicles'], ['ملف سيارة']]);
    var v = A.view(), id = p.id;
    var jobs = [api.get('/vehicles/' + id)];
    jobs.push(api.can('custody.view') ? api.get('/custodies', { vehicle_id: id, limit: 20 }) : Promise.resolve(null));
    jobs.push(api.can('odometer.view') ? api.get('/odometer/readings', { vehicle_id: id, limit: 20 }) : Promise.resolve(null));
    jobs.push(api.can('documents.view') ? Promise.all([api.get('/documents', { owner_type: 'vehicle', owner_id: id }), A.docTypes()]).then(function (x) { return x[0]; }) : Promise.resolve(null));
    A.load(v, Promise.all(jobs), function (r) {
      var x = r[0], custodies = r[1], readings = r[2], docs = r[3];
      A.setTitle(x.plate_number, [['السيارات', 'vehicles'], [x.plate_number]]);
      var actions = [];
      if (api.can('custody.view')) actions.push(A.btn('من كان يقود؟', { icon: 'search', cls: 'btn-outline', id: 'who-drove' }));
      if (api.can('tracking.history')) actions.push(h`<a class="btn btn-outline" href="#/tracking?route=${x.id}">${icon('route', 15)}المسار</a>`);
      if (api.can('vehicles.update')) actions.push(A.btn('تعديل', { icon: 'pencil', cls: 'btn-outline', id: 'veh-edit' }));
      if (api.can('custody.assign')) actions.push(x.custody ? A.btn('استلام السيارة', { icon: 'log-in', cls: 'btn-primary', id: 'veh-return' }) : A.btn('تسليم لسائق', { icon: 'key-round', cls: 'btn-primary', id: 'veh-handover' }));
      setTimeout(function () { wire(x); });
      return h`${A.head(h`<span class="plate" style="font-size:20px">${x.plate_number}</span>`, [x.make, x.model, x.year, x.color].filter(Boolean).join(' · ') || 'بدون بيانات الطراز', actions)}
        <div class="grid" style="grid-template-columns:minmax(0,1fr) minmax(0,1.4fr)">
          <div class="card"><div class="card-h"><div class="card-t">البيانات</div>${A.pill('vehicle_status', x.status)}</div>${BT.kv([['الشركة', api.company(x.company_id)], ['الفرع', api.branch(x.branch_id)], ['رقم الشاصي', x.vin ? h`<span class="num ltr">${x.vin}</span>` : '—'], ['آخر قراءة عداد', x.last_odometer_km != null ? h`<span class="num">${fmt.km(x.last_odometer_km)}</span> كم` : '—'], ['العهدة الحالية', x.custody ? h`${A.person(x.custody.driver)} <span class="muted fs-sm">منذ ${fmt.dt(x.custody.started_at)}</span>` : raw('<span class="muted">لا يوجد</span>')]])}</div>
          <div class="card"><div class="card-h"><div class="card-t">${icon('key-round', 16)} سجل العُهد</div></div>${custodies == null ? raw('<div class="muted fs-sm">يحتاج صلاحية العهد</div>') : custodies.length ? h`<div class="list">${custodies.map(function (c) { return h`<button type="button" class="li" data-custody="${c.id}" style="width:100%;text-align:start"><span class="li-ic ${c.ended_at ? '' : 'g'}">${icon(c.ended_at ? 'history' : 'key-round', 16)}</span><div class="li-main"><div class="li-t">${A.person(c.driver)}</div><div class="li-d">${fmt.dt(c.started_at)} ← ${c.ended_at ? fmt.dt(c.ended_at) : 'مستمرة'}</div></div>${c.kind === 'emergency' ? A.pill('custody_kind', 'emergency') : ''}${c.needs_review ? BT.pill('تحتاج مراجعة', 'o') : ''}</button>`; })}</div>` : BT.empty('key-round', 'لم تُسلَّم بعد', '')}</div>
        </div>
        ${readings ? h`<div class="card mt-16"><div class="card-h"><div class="card-t">${icon('gauge', 16)} قراءات العداد</div><a class="link-row" href="#/odometer">صفحة العداد ${icon('arrow-left', 14)}</a></div><div id="veh-readings"></div></div>` : ''}
        ${api.can('maintenance.view') ? h`<div class="card mt-16"><div class="card-h"><div class="card-t">${icon('wrench', 16)} الصيانة</div><a class="link-row" href="#/maintenance">صفحة الصيانة ${icon('arrow-left', 14)}</a></div><div id="veh-mnt"></div></div>` : ''}
        ${api.can('accidents.view') ? h`<div class="card mt-16"><div class="card-h"><div class="card-t">${icon('shield-alert', 16)} الحوادث</div><a class="link-row" href="#/accidents">صفحة الحوادث ${icon('arrow-left', 14)}</a></div><div id="veh-acc"></div></div>` : ''}
        ${docs ? h`<div class="card mt-16"><div class="card-h"><div class="card-t">${icon('file-badge', 16)} مستندات السيارة</div></div><div id="veh-docs">${vehDocs(docs)}</div></div>` : ''}`;
      function wire(x) {
        if (document.getElementById('veh-mnt') && A.vehicleMaintenance) A.vehicleMaintenance(document.getElementById('veh-mnt'), x);
        if (document.getElementById('veh-acc') && A.vehicleAccidents) A.vehicleAccidents(document.getElementById('veh-acc'), x);
        if (readings && document.getElementById('veh-readings')) BT.table(document.getElementById('veh-readings'), { rows: readings, pageSize: 0, columns: readingColumns(false), rowClick: function (rd) { A.reading(rd); } });
        var on = function (sel, fn) { var b = document.getElementById(sel); if (b) b.onclick = fn; };
        on('veh-edit', function () { A.vehicleForm(x, function () { A.router.refresh(); }); });
        on('veh-handover', function () { A.handover({ vehicle: x }, function () { A.router.refresh(); }); });
        on('veh-return', function () { A.returnVehicle(x.custody.id, x, function () { A.router.refresh(); }); });
        on('who-drove', function () { A.whoDrove(x); });
        BT.on(v, 'click', '[data-custody]', function (e, b) { A.custody(b.getAttribute('data-custody')); });
        BT.on(v, 'click', '[data-doc-add]', function () { A.addDocument('vehicle', x.id, function () { A.router.refresh(); }); });
      }
    }).catch(function () {});
  };
  function vehDocs(docs) {
    return h`${docs.length ? h`<div class="list">${docs.map(function (d) { var n = d.expiry_date ? BT.date.daysLeft(d.expiry_date) : null; return h`<div class="li"><span class="li-ic">${icon('file-badge', 16)}</span><div class="li-main"><div class="li-t">${A.docTypeName(d.type_code)} ${d.number ? h`<span class="num muted fs-sm">${d.number}</span>` : ''}</div><div class="li-d">${d.expiry_date ? h`ينتهي <span class="num">${fmt.date(d.expiry_date)}</span>` : 'بلا تاريخ انتهاء'}</div></div>${d.has_file ? h`<a class="btn btn-sm btn-ghost" href="${api.url('/documents/' + d.id + '/file')}" target="_blank" rel="noopener">${icon('eye', 14)} عرض</a>` : ''}${n != null && n <= 30 ? BT.pill(fmt.daysLabel(n), n < 0 ? 'r' : 'o') : ''}</div>`; })}</div>` : BT.empty('file-badge', 'لا توجد مستندات', '')}
      ${api.can('documents.manage') ? h`<div class="mt-12"><button type="button" class="btn btn-sm btn-soft" data-doc-add>${icon('file-plus', 14)} إضافة أو تجديد مستند</button></div>` : ''}`;
  }

  A.whoDrove = function (x) {
    var d = BT.modal.open({
      title: 'من كان يقود؟', subtitle: x.plate_number, icon: 'search', size: 'sm', form: true,
      body: h`<div class="form">${BT.f.input({ name: 'at', label: 'الوقت (بتوقيت الكويت)', type: 'datetime-local', required: true, value: A.kwInput() })}<div data-out></div><div class="hint">للمخالفات والحوادث والتلفيات: يُحدد السائق المسؤول من سجل العهد.</div></div>`,
      buttons: [{ label: 'إغلاق', cls: 'btn-ghost' }, { label: 'بحث', cls: 'btn-primary', submit: true }],
      onSubmit: function (v) {
        var out = d.el.querySelector('[data-out]');
        return api.get('/vehicles/' + x.id + '/custody-at', { at: A.kwIso(v.at) }).then(function (c) {
          BT.render(out, h`<div class="banner success mt-8">${icon('user-round-check', 16)}<div>${A.person(c.driver)}<div class="fs-sm mt-4">العهدة من ${fmt.dt(c.started_at)} إلى ${c.ended_at ? fmt.dt(c.ended_at) : 'الآن'}</div></div></div>`);
          return false;
        }, function (err) { BT.render(out, h`<div class="banner warn mt-8">${icon('info', 16)}<div>${api.message(err)}</div></div>`); return false; });
      }
    });
  };

  /* ================= العُهد ================= */
  BT.pages['custody'] = function (p, q) {
    A.setTitle('العُهد والتسليم');
    var v = A.view();
    BT.render(v, h`${A.head('من يحمل كل سيارة الآن', 'التسليم والاستلام بقراءة العداد وصورته وصور الحالة، والعهد الطارئة تنتظر المراجعة', api.can('custody.assign') ? A.btn('تسليم سيارة لسائق', { icon: 'key-round', cls: 'btn-primary', action: 'handover-new' }) : '')}<div class="card"><div id="cus-table"></div></div>`);
    var t = BT.table(document.getElementById('cus-table'), {
      fetch: function (s) { return api.get('/custodies', { open: s.chip === 'open' || null, needs_review: s.chip === 'review' || null, limit: s.limit, offset: s.offset }); },
      chips: { value: q.view || 'open', all: 'السجل كاملاً', options: [{ v: 'open', t: 'المفتوحة' }, { v: 'review', t: 'تحتاج مراجعة' }] },
      columns: [
        { key: 'vehicle', label: 'السيارة', render: function (c) { return A.plate(c.vehicle.plate_number, c.vehicle.id); } },
        { key: 'driver', label: 'السائق', render: function (c) { return A.person(c.driver); } },
        { key: 'started_at', label: 'من', render: function (c) { return fmt.dt(c.started_at); } },
        { key: 'ended_at', label: 'إلى', render: function (c) { return c.ended_at ? fmt.dt(c.ended_at) : BT.pill('مستمرة', 'g'); } },
        { key: 'kind', label: 'النوع', render: function (c) { return h`${A.pill('custody_kind', c.kind)}${c.needs_review ? h` ${BT.pill('تحتاج مراجعة', 'o')}` : ''}`; } }
      ],
      rowClick: function (c) { A.custody(c.id); },
      empty: { icon: 'key-round', title: 'لا توجد عهد' }
    });
    A.refreshCustody = t.refresh;
    if (q['new'] && api.can('custody.assign')) A.handover({}, t.refresh);
  };
  BT.actions['handover-new'] = function () { A.handover({}, function () { if (A.refreshCustody) A.refreshCustody(); }); };

  A.custody = function (id) {
    var dlg = BT.drawer.open({ title: 'العهدة', icon: 'key-round', size: 'lg', body: A.spinner(), buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }] });
    api.get('/custodies/' + id).then(function (c) {
      dlg.panel.querySelector('.modal-h h3').textContent = 'عهدة ' + (c.vehicle.plate_number || '');
      var photo = function (ph) { return { src: api.url('/custodies/' + id + '/photos/' + ph.sha256), caption: (ph.stage === 'handover' ? 'التسليم · ' : 'الاستلام · ') + api.t('photo_position', ph.position) }; };
      var stages = ['handover', 'return'].map(function (s) { return c.photos.filter(function (x) { return x.stage === s; }); });
      dlg.setBody(h`${c.needs_review ? h`<div class="banner warn fs-sm mb-12">${icon('triangle-alert', 15)}<div>عهدة طارئة تنتظر المراجعة${c.reason ? ': ' + c.reason : ''}</div></div>` : ''}
        ${BT.kv([['السيارة', A.plate(c.vehicle.plate_number, c.vehicle.id)], ['السائق', A.person(c.driver)], ['من', fmt.dt(c.started_at)], ['إلى', c.ended_at ? fmt.dt(c.ended_at) : BT.pill('مستمرة', 'g')], ['النوع', A.pill('custody_kind', c.kind)], c.reason ? ['السبب', c.reason] : null].filter(Boolean))}
        <div class="section-t mt-16">قراءات العداد خلال العهدة</div>
        ${c.readings.length ? h`<div class="list">${c.readings.map(function (rd) { return h`<button type="button" class="li" data-reading="${rd.id}" style="width:100%;text-align:start"><span class="li-ic ${rd.flags.length ? 'o' : ''}">${icon('gauge', 16)}</span><div class="li-main"><div class="li-t"><span class="num">${fmt.km(rd.effective_km)}</span> كم · ${api.t('reading_kind', rd.kind)}</div><div class="li-d">${fmt.dt(rd.recorded_at)}${rd.flags.length ? ' · ' + rd.flags.map(function (f) { return api.t('odometer_flags', f); }).join('، ') : ''}</div></div></button>`; })}</div>` : raw('<div class="muted fs-sm">لا توجد قراءات</div>')}
        <div class="section-t mt-16">صور الحالة عند التسليم</div>${A.thumbs(stages[0].map(photo))}
        ${c.ended_at ? h`<div class="section-t mt-16">صور الحالة عند الاستلام</div>${A.thumbs(stages[1].map(photo))}` : ''}`);
      BT.on(dlg.body, 'click', '[data-reading]', function (e, b) { var rd = c.readings.find(function (x) { return x.id === b.getAttribute('data-reading'); }); A.reading(rd); });
      var btns = [];
      if (c.needs_review && api.can('custody.emergency')) btns.push(h`<button type="button" class="btn btn-outline" data-x="review">${icon('badge-check', 15)}تمت المراجعة</button>`);
      if (!c.ended_at && api.can('custody.assign')) btns.push(h`<button type="button" class="btn btn-primary" data-x="return">${icon('log-in', 15)}استلام السيارة</button>`);
      if (!btns.length) return;
      var foot = dlg.panel.querySelector('.modal-f');
      BT.render(foot, h`<span class="spacer"></span>${btns}<button type="button" class="btn btn-secondary" data-close>إغلاق</button>`);
      var done = function () { dlg.close(); if (A.refreshCustody) A.refreshCustody(); if (A.router.current === 'vehicles/:id') A.router.refresh(); };
      BT.on(foot, 'click', '[data-x]', function (e, b) {
        if (b.getAttribute('data-x') === 'return') A.returnVehicle(id, { plate_number: c.vehicle.plate_number }, done);
        else A.confirmRun({ title: 'مراجعة العهدة الطارئة', message: 'اكتب ما تحققت منه (المستندات، حالة السيارة، سبب الطوارئ).', confirmText: 'تمت المراجعة', tone: 'success', reason: { label: 'ملاحظة المراجعة', required: true }, run: function (note) { return api.post('/custodies/' + id + '/review', { note: note }); }, done: 'تمت المراجعة', after: done });
      });
    }, function (err) { dlg.setBody(A.errorBox(err)); });
  };

  /* تسليم سيارة: صورة العداد إلزامية، وصور الحالة تحفظ وضع السيارة لحظة التسليم */
  A.handover = function (pre, after) {
    var wait = BT.modal.open({ title: 'تسليم سيارة لسائق', icon: 'key-round', size: 'sm', body: A.spinner() });
    var jobs = [pre.vehicle ? Promise.resolve([pre.vehicle]) : api.get('/vehicles', { status: 'available', limit: 200 }), api.get('/employees', { is_driver: true, status_code: 'active', limit: 200 }), api.get('/custodies', { open: true, limit: 200 })];
    Promise.all(jobs).then(function (r) {
      wait.close();
      var vehicles = r[0], holding = {};
      r[2].forEach(function (c) { if (c.driver) holding[c.driver.id] = c.vehicle.plate_number; });
      // من معه سيارة يظهر آخر القائمة مع لوحتها: التسليم له يُرفض ما لم تُستلم الأولى
      var drivers = r[1].slice().sort(function (a, b) { return (holding[a.id] ? 1 : 0) - (holding[b.id] ? 1 : 0); });
      var emergency = api.can('custody.emergency');
      A.formModal({
        title: 'تسليم سيارة لسائق', icon: 'key-round', size: 'lg', submitText: 'تسليم', done: 'تم التسليم وبدأت العهدة',
        body: h`<div class="form-grid">
          ${A.picker({ name: 'vehicle', label: 'السيارة', required: true, items: vehicles.map(function (x) { return { id: x.id, label: A.vehicleLabel(x), km: x.last_odometer_km }; }), value: pre.vehicle && pre.vehicle.id, hint: pre.vehicle ? '' : 'السيارات المتاحة فقط' })}
          ${A.picker({ name: 'driver', label: 'السائق', required: true, items: drivers.map(function (e) { return { id: e.id, label: api.name(e.name) + ' — ' + e.employee_number + (holding[e.id] ? ' · معه ' + holding[e.id] : '') }; }), hint: 'السائقون على رأس العمل؛ من معه سيارة يجب استلامها منه أولاً' })}
          ${BT.f.input({ name: 'odometer_km', label: 'قراءة العداد (كم)', required: true, num: true, min: 0, value: pre.vehicle ? pre.vehicle.last_odometer_km : '' })}
          ${BT.f.input({ name: 'started_at', label: 'وقت التسليم', type: 'datetime-local', optional: true, hint: 'اتركه للتسليم الآن. يقبل حتى 7 أيام للخلف' })}
          ${emergency ? BT.f.radios({ name: 'kind', label: 'نوع التسليم', value: 'normal', options: [{ v: 'normal', t: 'عادي' }, { v: 'emergency', t: 'طارئ', d: 'يتجاوز الفحوصات ويحتاج سبباً ومراجعة' }], full: true }) : ''}
          <div class="full hidden" data-reason>${BT.f.textarea({ name: 'reason', label: 'سبب التسليم الطارئ', rows: 2 })}</div>
          <div class="full">${BT.f.camera({ name: 'odo_photo', label: 'صورة العداد', required: true, cta: 'صورة العداد', sub: 'إلزامية' })}</div>
          <div class="full"><div class="label mb-8">صور الحالة</div>${photoFields('ph_', POSITIONS)}</div>
        </div>`,
        onOpen: function (dd) {
          var veh = dd.el.querySelector('[name=vehicle]'), km = dd.el.querySelector('[name=odometer_km]');
          veh.addEventListener('change', function () { var x = (A._pick.vehicle || []).find(function (i) { return i.label === veh.value; }); if (x && x.km != null && !km.value) km.value = x.km; });
          BT.on(dd.el, 'change', '[name=kind]', function (e, r) { dd.el.querySelector('[data-reason]').classList.toggle('hidden', r.value !== 'emergency'); });
        },
        submit: function (v) {
          return Promise.all([api.upload(v.odo_photo[0]), uploadPhotos(v, 'ph_', POSITIONS)]).then(function (up) {
            return api.post('/custodies', { vehicle_id: A.picked('vehicle', v.vehicle), driver_id: A.picked('driver', v.driver), odometer_km: v.odometer_km, photo_sha256: up[0].sha256, photos: up[1], started_at: A.kwIso(v.started_at), kind: v.kind || 'normal', reason: v.reason || null });
          });
        },
        after: after
      });
    }, function (err) { wait.setBody(A.errorBox(err)); });
  };

  A.returnVehicle = function (custodyId, x, after) {
    A.formModal({
      title: 'استلام السيارة', subtitle: x.plate_number, icon: 'log-in', size: 'lg', submitText: 'استلام', done: 'تم الاستلام وانتهت العهدة',
      body: h`<div class="form-grid">${BT.f.input({ name: 'odometer_km', label: 'قراءة العداد (كم)', required: true, num: true, min: 0 })}${BT.f.input({ name: 'ended_at', label: 'وقت الاستلام', type: 'datetime-local', optional: true, hint: 'اتركه للاستلام الآن' })}
        <div class="full">${BT.f.camera({ name: 'odo_photo', label: 'صورة العداد', required: true, cta: 'صورة العداد', sub: 'إلزامية' })}</div>
        <div class="full"><div class="label mb-8">صور الحالة</div>${photoFields('ph_', POSITIONS)}</div></div>`,
      submit: function (v) {
        return Promise.all([api.upload(v.odo_photo[0]), uploadPhotos(v, 'ph_', POSITIONS)]).then(function (up) {
          return api.post('/custodies/' + custodyId + '/return', { odometer_km: v.odometer_km, photo_sha256: up[0].sha256, photos: up[1], ended_at: A.kwIso(v.ended_at) });
        });
      },
      after: after
    });
  };

  /* ================= العداد ================= */
  function readingColumns(withVehicle) {
    return [
      withVehicle ? { key: 'vehicle', label: 'السيارة', render: function (rd) { return rd.vehicle_plate ? BT.plate(rd.vehicle_plate) : '—'; } } : null,
      { key: 'driver', label: 'السائق', render: function (rd) { return A.person(rd.driver); } },
      { key: 'kind', label: 'النوع', render: function (rd) { return api.t('reading_kind', rd.kind); } },
      { key: 'km', label: 'القراءة', num: true, render: function (rd) { return h`<span class="num">${fmt.km(rd.effective_km)}</span>${rd.corrected_km != null ? h`<span class="sub">مصححة من ${fmt.km(rd.value_km)}</span>` : ''}`; } },
      { key: 'flags', label: 'الملاحظات', render: function (rd) { return rd.flags.length ? rd.flags.map(function (f) { return BT.pill(api.t('odometer_flags', f), f === 'photo_reused' ? 'r' : 'o'); }) : raw('<span class="muted">—</span>'); } },
      { key: 'recorded_at', label: 'الوقت', render: function (rd) { return fmt.dt(rd.recorded_at); } },
      { key: 'review', label: 'المراجعة', render: function (rd) { return rd.review_status === 'pending' ? BT.pill('بانتظار المراجعة', 'o') : rd.review_status === 'reviewed' ? BT.pill('روجعت', 'g') : raw('<span class="muted">سليمة</span>'); } }
    ].filter(Boolean);
  }
  BT.pages['odometer'] = function (p, q) {
    A.setTitle('العداد');
    var v = A.view();
    BT.render(v, h`${A.head('قراءات العداد', 'كل قراءة بصورة من الكاميرا وموقع. القراءات المخالفة (أقل من السابقة، فوق الحد اليومي، مسافة خارج العهدة، صورة مكررة) تنتظر قرار المراجع', '')}<div class="card"><div id="odo-table"></div></div>`);
    var t = BT.table(document.getElementById('odo-table'), {
      fetch: function (s) { return api.get('/odometer/readings', { review_status: s.chip, limit: s.limit, offset: s.offset }); },
      chips: { value: q.status || 'pending', options: [{ v: 'pending', t: 'بانتظار المراجعة' }, { v: 'reviewed', t: 'روجعت' }, { v: 'ok', t: 'سليمة' }] },
      columns: readingColumns(true),
      rowClick: function (rd) { A.reading(rd, t.refresh); },
      empty: { icon: 'circle-check', title: 'لا توجد قراءات هنا' }
    });
  };

  A.reading = function (rd, after) {
    var canReview = rd.review_status === 'pending' && api.can('odometer.review');
    var mapLink = rd.lat != null ? h`<a href="https://www.openstreetmap.org/?mlat=${rd.lat}&mlon=${rd.lng}#map=17/${rd.lat}/${rd.lng}" target="_blank" rel="noopener">${icon('map', 14)} على الخريطة</a>` : '—';
    var body = h`<div class="grid" style="grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px">
      <div>${A.thumbs([{ src: api.url('/odometer/readings/' + rd.id + '/photo'), caption: 'صورة العداد · ' + fmt.dt(rd.recorded_at) }])}</div>
      <div>${BT.kv([['السيارة', rd.vehicle_plate ? BT.plate(rd.vehicle_plate) : '—'], ['السائق', A.person(rd.driver)], ['النوع', api.t('reading_kind', rd.kind)], ['المُدخل', h`<span class="num">${fmt.km(rd.value_km)}</span> كم`], rd.corrected_km != null ? ['المصحح', h`<span class="num">${fmt.km(rd.corrected_km)}</span> كم`] : null, ['يوم العمل', h`<span class="num">${fmt.date(rd.business_date)}</span>`], ['المصدر', rd.source === 'device' ? 'تطبيق السائق' : 'المكتب (تسليم أو استلام)'], ['الموقع', mapLink]].filter(Boolean))}</div></div>
      ${rd.flags.length ? h`<div class="banner warn fs-sm mt-12">${icon('triangle-alert', 15)}<div>${rd.flags.map(function (f) { return api.t('odometer_flags', f); }).join(' · ')}</div></div>` : ''}
      ${rd.review_status === 'reviewed' ? h`<div class="banner info fs-sm mt-12">${icon('badge-check', 15)}<div>روجعت ${rd.reviewed_at ? fmt.dt(rd.reviewed_at) : ''}${rd.review_reason ? ': ' + rd.review_reason : ''}</div></div>` : ''}
      ${canReview ? h`<div class="form mt-16">${BT.f.input({ name: 'corrected_km', label: 'القراءة الصحيحة (اختياري)', num: true, min: 0, hint: 'اتركها فارغة إن كانت القراءة صحيحة رغم الملاحظة' })}${BT.f.textarea({ name: 'reason', label: 'سبب القرار', required: true, rows: 2, placeholder: 'مثال: الصورة توضح 45210 والسائق أخطأ في الإدخال' })}</div>` : ''}`;
    if (!canReview) return BT.drawer.open({ title: 'قراءة عداد', icon: 'gauge', size: 'lg', body: body, buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }] });
    return BT.drawer.open({
      title: 'مراجعة قراءة عداد', icon: 'gauge', size: 'lg', form: true, body: body,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ القرار', cls: 'btn-primary', submit: true }],
      onSubmit: function (v) {
        return api.post('/odometer/readings/' + rd.id + '/review', { corrected_km: v.corrected_km === '' ? null : v.corrected_km, reason: v.reason }).then(function () {
          BT.toast('تم حفظ المراجعة'); A.refreshCounts(); if (after) after();
        }).catch(api.fail);
      }
    });
  };
})();
