/* =====================================================================
   صفحات الأسطول: التتبع الحي · السيارات · ملف السيارة · تسليم السيارات · العداد
   بوب أب: بطاقة السيارة (drawer) · سجل المسار (modal xl) · إرسال تنبيه للسائق ·
   إضافة/تعديل سيارة · استيراد Excel · تسليم سيارة · استلام سيارة · من كان يقود؟ ·
   صورة العداد (lightbox) · مراجعة قراءة عداد · رفع مستند · إيقاف سيارة (confirm)
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, D = BT.data, A = BT.A;
  var cfg = BT.config;

  /* ---------- أدوات مشتركة ---------- */
  A.odoPhoto = function (value, meta, lg) {
    return h`<div class="odo${lg ? ' lg' : ''}"><span class="digits">${String(value).padStart(6, '0')}</span><span class="meta">${icon('camera', 11)} ${meta || 'من الكاميرا'}</span></div>`;
  };
  A.showOdo = function (items, i) { // [{value, caption, sub}]
    BT.lightbox(items.map(function (x) { return { html: A.odoPhoto(x.value, x.meta || 'صورة من الكاميرا · ' + (x.time || ''), true), caption: x.caption, sub: x.sub }; }), i || 0);
  };
  A.sigPill = function (v) { var s = D.vehicleSignal(v); return s ? BT.pill(s, D.signalTone[s]) : BT.pill('—', 'n'); };
  function lastSeen(v) { return v.lastSec == null ? '—' : fmt.ago(v.lastSec); }

  /* =================================================================
     التتبع الحي  #/tracking?signal=انقطاع
     ================================================================= */
  var FIXED_PINS = ['18/23456', '12/40077', '30/66024', '27/30211', '41/88415', '33/19552', '16/51190', '25/72318'];
  BT.pages['tracking'] = function (p, q) {
    A.setTitle('التتبع الحي');
    var list = D.vehicles.filter(function (v) { return v.status === 'مسلّمة'; });
    var counts = {}; list.forEach(function (v) { var s = D.vehicleSignal(v); counts[s] = (counts[s] || 0) + 1; });
    var filter = q.signal || '', term = '', selected = null;
    BT.render(A.view(), h`
      ${A.head('موقع كل سيارة على مدار اليوم', list.length + ' سيارة مسلّمة · مصدر الموقع: هاتف السائق · تحديث كل ' + cfg.gpsIntervalSec + ' ثانية',
        h`<span class="tag"><span class="sdot g pulse"></span> مباشر · آخر تحديث ${BT.config.now}</span>${A.btn('سجل المسار', { icon: 'route', cls: 'btn-outline', action: 'route-pick' })}`)}
      <div class="toolbar" style="margin:0">
        <div class="search-box">${icon('search', 16)}<input class="input" id="trk-q" type="search" placeholder="ابحث بلوحة أو سائق…" aria-label="بحث"></div>
        <div class="chips" id="trk-chips"></div>
        <div class="map-legend ms-auto"><span><span class="sdot g"></span>يرسل</span><span><span class="sdot o"></span>متأخر</span><span><span class="sdot r"></span>انقطاع</span><span><span class="sdot p"></span>خارج يوم العمل</span></div>
      </div>
      <div class="grid" style="grid-template-columns:minmax(0,340px) minmax(0,1fr);align-items:start" id="trk-grid">
        <div class="card flush" style="display:flex;flex-direction:column;max-height:calc(100vh - 250px);min-height:420px">
          <div class="card-h"><div class="card-t">السيارات</div><span class="card-meta" id="trk-count"></span></div>
          <div id="trk-list" style="overflow-y:auto;padding:0 10px 10px"></div>
        </div>
        <div class="card" style="padding:10px"><div id="trk-map"></div></div>
      </div>
      <div class="banner note">${icon('info', 16)}<div>الهاتف يتتبع السائق وليس السيارة. إذا استُخدمت السيارة دون الهاتف تظهر المسافة في <a href="#/odometer"><b>سلسلة العداد</b></a>. انقطاع الإشارة أكثر من ${cfg.signalLossMin} دقائق يرسل تنبيهاً للمشرف.</div></div>`);

    function visible() {
      var t = BT.norm(term);
      return list.filter(function (v) {
        if (filter && D.vehicleSignal(v) !== filter) return false;
        if (!t) return true;
        var e = D.driverOf(v);
        return BT.norm(v.plate + ' ' + (e ? e.name : '')).indexOf(t) > -1;
      }).sort(function (a, b) { var o = { 'انقطاع': 0, 'متأخر': 1, 'خارج يوم العمل': 2, 'يرسل': 3 }; return o[D.vehicleSignal(a)] - o[D.vehicleSignal(b)]; });
    }
    function drawChips() {
      BT.render(document.getElementById('trk-chips'), h`${[['', 'الكل', list.length], ['انقطاع', 'انقطاع', counts['انقطاع']], ['متأخر', 'متأخر', counts['متأخر']], ['خارج يوم العمل', 'خارج يوم العمل', counts['خارج يوم العمل']], ['يرسل', 'يرسل', counts['يرسل']]].map(function (c) {
        return h`<button type="button" class="chip${filter === c[0] ? ' active' : ''}" data-f="${c[0]}">${c[0] ? h`<span class="sdot ${D.signalTone[c[0]]}"></span>` : ''}${c[1]} <span class="n">${c[2] || 0}</span></button>`;
      })}`);
    }
    function draw() {
      var vs = visible();
      document.getElementById('trk-count').textContent = vs.length + ' سيارة';
      BT.render(document.getElementById('trk-list'), vs.length ? h`${vs.slice(0, 120).map(function (v) {
        var e = D.driverOf(v);
        return h`<button type="button" class="li${selected === v.plate ? ' selected' : ''}" data-v="${v.plate}" style="${selected === v.plate ? 'background:var(--primary-softer);border-radius:8px' : ''}"><div class="li-main"><div class="li-t"><span class="plate">${v.plate}</span> <span class="muted fs-sm">· <bdi>${e ? e.name : ''}</bdi></span></div><div class="li-d">${lastSeen(v)}${v.speed ? ' · ' + v.speed + ' كم/س' : ''}</div></div>${A.sigPill(v)}</button>`;
      })}${vs.length > 120 ? h`<div class="muted fs-sm center" style="padding:10px">يظهر أول 120 — استخدم البحث للباقي</div>` : ''}` : BT.empty('map-pin-off', 'لا توجد سيارات', 'غيّر الفلتر أو كلمة البحث'));
      var pins = [], dots = '';
      vs.forEach(function (v) {
        if (!v.pos) return;
        var s = D.vehicleSignal(v), tone = D.signalTone[s];
        if (FIXED_PINS.indexOf(v.plate) > -1 || s === 'انقطاع' || v.plate === selected) pins.push({ id: v.plate, x: v.pos[0], y: v.pos[1], label: v.plate.split('/')[1], tone: tone, aria: v.plate + ' ' + s });
        else { var pos = BT.mapPos(v.pos[0], v.pos[1]); dots += String(h`<button type="button" class="mdot ${tone}" data-pin="${v.plate}" style="left:${pos.left};top:${pos.top}" aria-label="${v.plate}" data-tip="${v.plate}"></button>`); }
      });
      var mapEl = document.getElementById('trk-map');
      BT.render(mapEl, BT.kuwaitMap({ pins: pins }));
      mapEl.querySelector('.map-inner').insertAdjacentHTML('beforeend', dots);
      BT.$$('.pin', mapEl).forEach(function (p) { if (p.getAttribute('data-pin') === selected) p.classList.add('active'); });
    }
    drawChips(); draw();
    document.getElementById('trk-q').addEventListener('input', BT.debounce(function (e) { term = e.target.value; draw(); }, 150));
    BT.on(A.view(), 'click', '[data-f]', function (e, b) { filter = b.getAttribute('data-f'); drawChips(); draw(); });
    BT.on(A.view(), 'click', '[data-v],[data-pin]', function (e, b) {
      selected = b.getAttribute('data-v') || b.getAttribute('data-pin');
      draw(); A.vehicleQuick(D.byPlate[selected]);
    });
  };

  /* ---------- بطاقة السيارة السريعة (drawer) ---------- */
  A.vehicleQuick = function (v) {
    var e = D.driverOf(v), r = e && e.today, s = D.vehicleSignal(v);
    BT.drawer.open({
      title: h`<span class="plate">${v.plate}</span> · ${v.make} ${v.model}`, subtitle: 'آخر إشارة ' + lastSeen(v), icon: 'car',
      body: h`<div class="flex items-center gap-12 mb-16">${e ? BT.person(e.name, 'السائق الحالي · ' + e.id, 'lg') : ''}<span class="ms-auto">${A.sigPill(v)}</span></div>
        ${s === 'انقطاع' ? h`<div class="banner danger mb-12">${icon('wifi-off', 16)}<div>لا توجد إشارة من هاتف السائق منذ ${Math.round(v.lastSec / 60)} دقيقة. آخر موقع معروف معروض على الخريطة.</div></div>` : ''}
        ${v.outOfDay ? h`<div class="banner note mb-12" style="border-inline-start-color:var(--purple)">${icon('moon', 16)}<div>السائق أرسل تقريره اليومي والسيارة ما زالت تتحرك (<span class="num">${v.speed}</span> كم/س). تظهر هذه الحركة لأصحاب الصلاحية فقط.</div></div>` : ''}
        <div class="kpis cols-3 mb-16">
          ${BT.kpi({ label: 'السرعة', value: v.speed == null ? '—' : v.speed + ' كم/س', dot: 'b', ltr: true })}
          ${BT.kpi({ label: 'كم اليوم (GPS)', value: r && r.gps ? String(r.gps) : '—', dot: 'g' })}
          ${BT.kpi({ label: 'العداد', value: fmt.km(v.odo), dot: 'p' })}
        </div>
        ${BT.kv([['حالة اليوم', r ? (r.orders != null ? BT.pill('أرسل التقرير ' + r.sent, 'g') : BT.pill('بدأ اليوم ' + (r.started || ''), 'b')) : BT.pill('لم يبدأ اليوم', 'n')], ['الجوال', e ? h`<a class="num" href="tel:+965${e.phone}">${e.phone}</a>` : '—'], ['الفرع', v.branch], ['الإحداثيات (توضيحية)', h`<span class="num">${v.pos ? v.pos.join(', ') : '—'}</span>`]])}
        <div class="mt-16">${BT.kuwaitMap({ pins: [{ id: v.plate, x: v.pos[0], y: v.pos[1], label: v.plate.split('/')[1], tone: D.signalTone[s] }], tools: false, zone: false })}</div>`,
      buttons: [
        { label: 'تنبيه السائق', cls: 'btn-ghost', icon: 'bell-ring', close: false, onClick: function () { A.notifyDriver(e); } },
        { label: 'ملف السيارة', cls: 'btn-outline', icon: 'file-text', onClick: function () { A.go('vehicles/' + A.slug(v.plate)); } },
        { label: 'عرض المسار', cls: 'btn-primary', icon: 'route', close: false, onClick: function () { A.route(v); } }
      ]
    });
  };

  A.notifyDriver = function (e) {
    if (!e) return;
    BT.modal.open({
      title: 'إرسال تنبيه للسائق', subtitle: e.name, icon: 'bell-ring', size: 'sm', form: true,
      body: h`<div class="form">${BT.f.select({ name: 'tpl', label: 'نوع التنبيه', options: ['افتح تطبيق السائق — الإشارة منقطعة', 'أرسل تقريرك اليومي', 'راجع المشرف', 'رسالة مخصصة'], value: 'افتح تطبيق السائق — الإشارة منقطعة', placeholder: false })}
        ${BT.f.textarea({ name: 'msg', label: 'نص الرسالة', optional: true, placeholder: 'يظهر للسائق كإشعار في التطبيق' })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إرسال', icon: 'send', cls: 'btn-primary', submit: true }],
      onSubmit: function () { BT.toast('أُرسل الإشعار إلى ' + e.name, { sub: 'إشعار فوري في تطبيق السائق' }); }
    });
  };

  /* ---------- سجل المسار (modal xl) ---------- */
  BT.actions['route-pick'] = function () {
    BT.modal.open({
      title: 'سجل المسار', icon: 'route', size: 'sm', form: true,
      body: h`<div class="form">${BT.f.select({ name: 'plate', label: 'السيارة', required: true, options: D.vehicles.filter(function (v) { return v.status === 'مسلّمة'; }).map(function (v) { return { v: v.plate, t: v.plate + ' — ' + (D.driverOf(v) || {}).name }; }) })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'عرض المسار', cls: 'btn-primary', submit: true }],
      onSubmit: function (v) { setTimeout(function () { A.route(D.byPlate[v.plate]); }, 240); }
    });
  };
  A.route = function (v) {
    var day = 'اليوم';
    var d = BT.modal.open({
      title: h`سجل المسار — <span class="plate">${v.plate}</span>`, subtitle: (D.driverOf(v) || {}).name, icon: 'route', size: 'xl',
      body: h`<div class="between mb-12">${BT.tabs('route-day', [['اليوم', 'اليوم'], ['أمس', 'أمس'], ['فترة', 'فترة']], 'اليوم')}
        <div class="flex gap-8 items-center hidden" id="rt-range"><input class="input" type="date" value="${BT.date.add(cfg.today, -7)}" style="width:160px" aria-label="من"><span class="muted">إلى</span><input class="input" type="date" value="${cfg.today}" style="width:160px" aria-label="إلى"><button type="button" class="btn btn-soft" id="rt-apply">عرض</button></div></div>
        <div id="rt-body"></div>`,
      buttons: [{ label: 'تصدير GPX', cls: 'btn-outline', icon: 'download', close: false, onClick: function () { A.exportToast('مسار ' + v.plate, 'GPX'); } }, { label: 'إغلاق', cls: 'btn-primary' }]
    });
    function draw() {
      var r = D.route(v.plate, day);
      BT.render(d.el.querySelector('#rt-body'), h`<div class="grid" style="grid-template-columns:minmax(0,1fr) 260px">
        <div>${BT.kuwaitMap({ route: r.points, stops: r.stops, zone: false })}</div>
        <div class="col" style="gap:12px">
          ${BT.kpi({ label: 'المسافة (GPS)', value: r.km + ' كم', dot: 'b' })}
          ${BT.kv([['البداية', h`<span class="num">${r.start}</span>`], ['النهاية', h`<span class="num">${r.end}</span>`], ['التوقفات', String(r.stopsCount)], ['أعلى سرعة', h`<span class="num">${r.maxSpeed}</span> كم/س`]])}
          <div class="map-legend"><span><span class="sdot g"></span>بداية</span><span><span class="sdot r"></span>نهاية</span><span><span class="sdot o"></span>توقف</span></div>
          <div class="banner info fs-sm">${icon('info', 15)}<div>المسار من هاتف السائق. الفجوات تعني انقطاع الإشارة.</div></div>
        </div></div>`);
    }
    d.el.querySelector('[data-tabs="route-day"]').addEventListener('bt:tab', function (e) { day = e.detail; d.el.querySelector('#rt-range').classList.toggle('hidden', day !== 'فترة'); draw(); });
    d.el.querySelector('#rt-apply').onclick = function () { BT.toast('تم تحديث المسار للفترة المحددة', { type: 'info' }); draw(); };
    draw();
  };

  /* =================================================================
     السيارات  #/vehicles
     ================================================================= */
  BT.pages['vehicles'] = function (p, q) {
    A.setTitle('السيارات');
    var c = function (s) { return D.vehicles.filter(function (v) { return v.status === s; }).length; };
    BT.render(A.view(), h`
      ${A.head('السيارات', D.vehicles.length + ' سيارة في الأسطول',
        h`${A.btn('استيراد من Excel', { icon: 'file-spreadsheet', cls: 'btn-outline', action: 'vehicles-import' })}${A.btn('تصدير', { icon: 'download', cls: 'btn-outline', action: 'export', arg: 'قائمة السيارات' })}${A.btn('إضافة سيارة', { icon: 'plus', cls: 'btn-primary', action: 'add-vehicle' })}`)}
      <div class="kpis">
        ${BT.kpi({ label: 'كل السيارات', value: fmt.int(D.vehicles.length), sub: 'في كل الفروع', dot: 'b', action: 'veh-chip', arg: '' })}
        ${BT.kpi({ label: 'مسلّمة', value: fmt.int(c('مسلّمة')), sub: 'مع سائق الآن', dot: 'g', action: 'veh-chip', arg: 'مسلّمة' })}
        ${BT.kpi({ label: 'في الصيانة', value: fmt.int(c('في الصيانة')), sub: 'لدى مراكز الصيانة', dot: 'b', action: 'veh-chip', arg: 'في الصيانة' })}
        ${BT.kpi({ label: 'بلا سائق', value: fmt.int(c('بلا سائق')), sub: 'جاهزة للتسليم', dot: 'o', action: 'veh-chip', arg: 'بلا سائق' })}
      </div>
      <div class="card"><div id="veh-table"></div></div>`);
    var t = BT.table(document.getElementById('veh-table'), {
      rows: function () { return D.vehicles; },
      search: { placeholder: 'ابحث بلوحة أو موديل أو سائق…', text: function (v) { var e = D.driverOf(v); return v.plate + ' ' + v.make + ' ' + v.model + ' ' + (e ? e.name : ''); } },
      chips: { key: 'status', options: ['مسلّمة', 'في الصيانة', 'بلا سائق', 'موقوفة'].map(function (s) { return { v: s, t: s }; }), value: q.status || '' },
      columns: [
        { key: 'plate', label: 'السيارة', render: function (v) { return A.veh(v); } },
        { key: 'driver', label: 'السائق', sort: function (v) { var e = D.driverOf(v); return e ? e.name : 'ي'; }, render: function (v) { var e = D.driverOf(v); return e ? BT.person(e.name) : raw('<span class="muted">—</span>'); } },
        { key: 'status', label: 'الحالة', render: function (v) { return BT.pill(v.status, D.vehStatusTone[v.status]); } },
        { key: 'odo', label: 'العداد (كم)', num: true, render: function (v) { return fmt.km(v.odo); } },
        { key: 'nextServiceKm', label: 'الصيانة القادمة', sort: function (v) { return v.nextServiceKm - v.odo; }, render: function (v) { var left = v.nextServiceKm - v.odo; return h`<span class="num">${fmt.km(left)}</span> كم${left < 1000 ? raw(' ' + BT.pill('قريبة', 'o')) : ''}`; } },
        { key: 'regExp', label: 'الاستمارة', render: function (v) { var n = BT.date.daysLeft(v.regExp); return n <= 30 ? BT.pill(fmt.daysLabel(n), n <= 15 ? 'r' : 'o') : fmt.date(v.regExp); } },
        { key: 'branch', label: 'الفرع' }
      ],
      rowClick: function (v) { A.go('vehicles/' + A.slug(v.plate)); },
      rowMenu: A.vehicleMenu,
      selectable: true,
      bulk: [{ label: 'تصدير المحدد', icon: 'download', run: function (rows, done) { A.exportToast(rows.length + ' سيارة'); done(); } }, { label: 'نقل لفرع', icon: 'building-2', run: function (rows, done) { A.moveBranch(rows, done); } }],
      pageSize: 10
    });
    BT.actions['veh-chip'] = function (s) { t.setChip(s || ''); };
  };
  A.vehicleMenu = function (v) {
    var e = D.driverOf(v);
    return [
      { label: 'عرض الملف', icon: 'file-text', onClick: function () { A.go('vehicles/' + A.slug(v.plate)); } },
      { label: 'تعديل البيانات', icon: 'pencil', onClick: function () { A.vehicleForm(v); } },
      e ? { label: 'استلام السيارة من السائق', icon: 'key-round', onClick: function () { A.returnCar(v); } } : { label: 'تسليم لسائق', icon: 'key-round', onClick: function () { A.handover(v.plate); } },
      { label: 'إحالة للصيانة', icon: 'wrench', onClick: function () { BT.actions['maint-new'](v.plate); } },
      { label: 'من كان يقود؟', icon: 'search', onClick: function () { A.whoDrove(v.plate); } },
      { sep: true },
      { label: 'إيقاف السيارة', icon: 'ban', danger: true, onClick: function () { A.stopVehicle(v); } }
    ];
  };
  A.moveBranch = function (rows, done) {
    BT.modal.open({
      title: 'نقل ' + rows.length + ' سيارة لفرع آخر', icon: 'building-2', size: 'sm', form: true,
      body: h`<div class="form">${BT.f.select({ name: 'branch', label: 'الفرع', required: true, options: D.company.branches })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'نقل', cls: 'btn-primary', submit: true }],
      onSubmit: function (v) { rows.forEach(function (r) { r.branch = v.branch; }); done(); BT.toast('تم نقل ' + rows.length + ' سيارة إلى ' + v.branch); }
    });
  };
  A.stopVehicle = function (v) {
    BT.confirm({ title: 'إيقاف السيارة ' + v.plate, message: 'السيارة الموقوفة لا يمكن تسليمها لسائق حتى تُعاد للخدمة. إذا كانت مسلّمة الآن سيُطلب استلامها أولاً.', confirmText: 'إيقاف السيارة', tone: 'danger', reason: { label: 'سبب الإيقاف', placeholder: 'مثال: انتهاء الاستمارة، بيع السيارة…' } })
      .then(function (r) { if (!r.ok) return; if (D.driverOf(v)) { BT.toast('استلم السيارة من السائق أولاً', { type: 'warning' }); return; } v.status = 'موقوفة'; BT.toast('تم إيقاف السيارة ' + v.plate, { sub: r.reason }); A.router.refresh(); });
  };

  /* ---------- إضافة/تعديل سيارة ---------- */
  BT.actions['add-vehicle'] = function () { A.vehicleForm(null); };
  A.vehicleForm = function (v) {
    var edit = !!v; v = v || {};
    var makes = ['Toyota', 'Nissan', 'Suzuki', 'Hyundai', 'Kia', 'Mitsubishi', 'Chevrolet'];
    BT.modal.open({
      title: edit ? 'تعديل بيانات السيارة' : 'إضافة سيارة', subtitle: edit ? v.plate : 'الحقول المعلّمة بـ * مطلوبة', icon: edit ? 'pencil' : 'car', size: 'lg', form: true,
      body: h`<div class="form-grid">
        ${BT.f.input({ name: 'plate', label: 'رقم اللوحة', required: true, value: v.plate, placeholder: '18/23456', validate: 'plate', readonly: edit, hint: edit ? 'لا يمكن تعديل اللوحة بعد الإضافة' : 'الصيغة: رقم/رقم' })}
        ${BT.f.select({ name: 'branch', label: 'الفرع', required: true, options: D.company.branches, value: v.branch })}
        ${BT.f.select({ name: 'make', label: 'الشركة المصنّعة', required: true, options: makes, value: v.make })}
        ${BT.f.input({ name: 'model', label: 'الموديل', required: true, value: v.model, placeholder: 'Yaris' })}
        ${BT.f.select({ name: 'year', label: 'سنة الصنع', required: true, options: ['2025', '2024', '2023', '2022', '2021', '2020'], value: v.year })}
        ${BT.f.select({ name: 'color', label: 'اللون', options: ['أبيض', 'فضي', 'رمادي', 'أسود', 'أحمر', 'أزرق'], value: v.color })}
        ${BT.f.input({ name: 'chassis', label: 'رقم الشاصي', value: v.chassis, optional: true, placeholder: 'JT…' })}
        ${BT.f.input({ name: 'odo', label: 'قراءة العداد الحالية (كم)', required: true, num: true, min: 0, value: v.odo, readonly: edit, hint: edit ? 'تتغير فقط من قراءات السائق أو المراجعة' : '' })}
        ${BT.f.date({ name: 'regExp', label: 'انتهاء الاستمارة', required: true, value: v.regExp })}
        ${BT.f.date({ name: 'insuranceExp', label: 'انتهاء التأمين', required: true, value: v.insuranceExp })}
        ${BT.f.input({ name: 'nextServiceKm', label: 'الصيانة القادمة عند (كم)', num: true, value: v.nextServiceKm, optional: true })}
        ${BT.f.upload({ name: 'docs', label: 'صورة الاستمارة والتأمين', optional: true, multiple: true })}
        ${BT.f.textarea({ name: 'notes', label: 'ملاحظات', optional: true, full: true, rows: 2 })}
      </div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: edit ? 'حفظ التعديلات' : 'إضافة السيارة', cls: 'btn-primary', submit: true, icon: 'check' }],
      onSubmit: function (f) {
        if (!edit && D.byPlate[f.plate]) { BT.toast('اللوحة ' + f.plate + ' مسجلة مسبقاً', { type: 'error' }); return false; }
        return new Promise(function (res) { setTimeout(function () {
          if (edit) Object.assign(v, { branch: f.branch, make: f.make, model: f.model, year: +f.year, color: f.color, chassis: f.chassis, regExp: f.regExp, insuranceExp: f.insuranceExp, nextServiceKm: f.nextServiceKm || v.nextServiceKm });
          else { var nv = { id: f.plate, plate: f.plate, make: f.make, model: f.model, year: +f.year, color: f.color, chassis: f.chassis, branch: f.branch, odo: f.odo, regExp: f.regExp, insuranceExp: f.insuranceExp, nextServiceKm: f.nextServiceKm || (Math.floor(f.odo / 5000) + 1) * 5000, status: 'بلا سائق' }; D.vehicles.unshift(nv); D.byPlate[nv.plate] = nv; }
          BT.toast(edit ? 'تم حفظ التعديلات' : 'تمت إضافة السيارة ' + f.plate, { sub: edit ? '' : 'الحالة: بلا سائق — جاهزة للتسليم' });
          A.router.refresh(); res(true);
        }, 500); });
      }
    });
  };

  /* ---------- استيراد من Excel ---------- */
  BT.actions['vehicles-import'] = function () {
    var d = BT.modal.open({
      title: 'استيراد السيارات من Excel', icon: 'file-spreadsheet', size: 'lg',
      body: h`<div class="stepper"><div class="step active"><span class="sn">1</span>تحميل القالب</div><div class="step-line"></div><div class="step" id="st2"><span class="sn">2</span>رفع الملف</div><div class="step-line"></div><div class="step" id="st3"><span class="sn">3</span>المراجعة والاستيراد</div></div>
        <div class="banner info mb-12">${icon('info', 16)}<div>استخدم قالب البيانات نفسه (ورقة «السيارات»). الأعمدة: اللوحة، الشركة، الموديل، السنة، اللون، الفرع، العداد، انتهاء الاستمارة، انتهاء التأمين.</div><button type="button" class="btn btn-sm btn-outline banner-act" data-action="soon" data-arg="تحميل قالب Excel">${icon('download', 14)} القالب</button></div>
        <label class="dropzone" style="min-height:150px">${icon('file-spreadsheet', 26)}<span><b>اختر ملف Excel</b> أو اسحبه هنا</span><span class="hint">xlsx · حتى 5MB · حتى 1,000 صف</span><input type="file" accept=".xlsx,.xls,.csv" id="imp-file"></label>
        <div id="imp-result" class="mt-12"></div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'استيراد', cls: 'btn-primary', icon: 'upload', disabled: true, onClick: function () { BT.toast('تم استيراد 12 سيارة', { sub: 'تم تجاهل صف واحد به خطأ — تم تنزيل تقرير الأخطاء' }); } }]
    });
    d.el.querySelector('#imp-file').addEventListener('change', function (e) {
      if (!e.target.files.length) return;
      d.el.querySelector('#st2').classList.add('done'); d.el.querySelector('#st3').classList.add('active');
      BT.render(d.el.querySelector('#imp-result'), h`<div class="file-item"><span class="fi-ic">${icon('file-spreadsheet', 16)}</span><span class="fi-name">${e.target.files[0].name}</span><span class="fi-size">${fmt.bytes(e.target.files[0].size)}</span></div>
        <div class="kpis cols-3 mt-12">${BT.kpi({ label: 'صفوف صالحة', value: '12', dot: 'g', tone: 'success' })}${BT.kpi({ label: 'أخطاء', value: '1', dot: 'r', tone: 'danger' })}${BT.kpi({ label: 'مكررة (موجودة)', value: '0', dot: 'n' })}</div>
        <div class="banner danger mt-12">${icon('circle-x', 16)}<div>صف 9: اللوحة «18-4401» بصيغة غير صحيحة (المطلوب 18/4401). سيتم تجاهل هذا الصف.</div></div>`);
      d.btn(1).disabled = false;
    });
  };

  /* =================================================================
     ملف السيارة  #/vehicles/18-23456
     ================================================================= */
  BT.pages['vehicles/:plate'] = function (p) {
    var v = D.byPlate[A.unslug(p.plate)];
    if (!v) { A.setTitle('غير موجود'); BT.render(A.view(), BT.empty('car', 'السيارة غير موجودة', 'تأكد من رقم اللوحة', A.btn('كل السيارات', { cls: 'btn-primary', action: 'go', arg: 'vehicles' }))); return; }
    A.setTitle('ملف السيارة', [['السيارات', 'vehicles'], [v.plate]]);
    var e = D.driverOf(v), chain = D.odoChain(v.plate);
    var gaps = chain.filter(function (c) { return c.gap; }), gapSum = BT.sum(gaps, function (c) { return c.gap; }), bigGaps = gaps.filter(function (c) { return c.gap > cfg.odoGapKm; }).length;
    var yRep = e && e.today;
    var logs = D.assignments.filter(function (a) { return a.plate === v.plate; });
    var jobs = D.jobs.filter(function (j) { return j.plate === v.plate; });
    BT.render(A.view(), h`
      <div class="page-head"><div><div class="flex items-center gap-8" style="flex-wrap:wrap">${BT.pill(v.status, D.vehStatusTone[v.status], true)}<h2 class="ltr">${v.make} ${v.model} ${v.year} — ${v.plate}</h2></div>
        <p>${e ? h`السائق الحالي <bdi>${e.name}</bdi> · ` : ''}التأمين حتى ${fmt.date(v.insuranceExp)} · الاستمارة حتى ${fmt.date(v.regExp)}</p></div>
        <div class="page-actions">${A.btn('تعديل', { icon: 'pencil', cls: 'btn-outline', action: 'veh-edit', arg: v.plate })}
        ${e ? A.btn('استلام من السائق', { icon: 'key-round', cls: 'btn-outline', action: 'veh-return', arg: v.plate }) : A.btn('تسليم لسائق', { icon: 'key-round', cls: 'btn-outline', action: 'handover-new', arg: v.plate })}
        ${A.btn('إحالة للصيانة', { icon: 'wrench', cls: 'btn-primary', action: 'maint-new', arg: v.plate })}
        <button type="button" class="icon-btn" data-action="veh-more" data-arg="${v.plate}" aria-label="المزيد">${icon('ellipsis-vertical', 18)}</button></div></div>
      ${BT.tabs('veh', [['overview', 'نظرة عامة'], ['handover', 'التسليم', logs.length], ['maint', 'الصيانة', jobs.length], ['route', 'المسار'], ['docs', 'المستندات']], 'overview', 'tabs-line')}
      <div data-panel="overview" data-group="veh" class="active col">
        <div class="kpis">
          ${BT.kpi({ label: 'كم آخر 5 أيام', value: fmt.km(BT.sum(chain, function (c) { return c.end - c.start; })), sub: 'من صور العداد', dot: 'b' })}
          ${BT.kpi({ label: 'كم خارج العمل', value: String(gapSum), sub: bigGaps ? (bigGaps === 1 ? 'تنبيه واحد' : bigGaps + ' تنبيهات') + ' فوق ' + cfg.odoGapKm + ' كم' : 'لا تنبيهات', dot: 'o' })}
          ${BT.kpi({ label: 'فرق العداد وGPS اليوم', value: yRep && yRep.gps ? ((chain[0].end - chain[0].start) - yRep.gps) + ' كم' : '—', sub: yRep && yRep.gps ? 'العداد ' + (chain[0].end - chain[0].start) + ' · GPS ' + yRep.gps : 'لا يوجد تقرير اليوم', dot: 'g' })}
          ${BT.kpi({ label: 'الصيانة القادمة', value: fmt.km(v.nextServiceKm - v.odo) + ' كم', sub: 'تغيير زيت عند ' + fmt.km(v.nextServiceKm), dot: 'p' })}
        </div>
        <div class="grid" style="grid-template-columns:minmax(0,1.5fr) minmax(0,1fr)">
          <div class="card"><div class="card-h"><div><div class="card-t">سلسلة العداد</div><div class="card-meta">رقم يكتبه السائق وصورة من الكاميرا</div></div>${A.btn('من كان يقود؟', { icon: 'search', cls: 'btn-sm btn-soft', action: 'who-drove', arg: v.plate })}</div>
            <div class="table-wrap"><table class="t compact"><thead><tr><th>اليوم</th><th>السائق</th><th class="num">البداية</th><th class="num">النهاية</th><th class="num">كم اليوم</th><th>خارج العمل قبله</th><th>الصورة</th></tr></thead><tbody>
            ${chain.map(function (c, i) { return h`<tr><td class="num">${fmt.dm(c.day)}</td><td><bdi>${c.driver}</bdi></td><td class="num">${fmt.km(c.start)}</td><td class="num">${fmt.km(c.end)}</td><td class="num">${c.end - c.start}</td><td>${c.gap == null ? '—' : BT.pill(c.gap + ' كم', c.gap > cfg.odoGapKm ? 'o' : 'g')}</td><td><button type="button" class="icon-btn sm" data-odo="${i}" aria-label="عرض الصور" data-tip="عرض الصورتين">${icon('camera', 15)}</button></td></tr>`; })}
            </tbody></table></div>
            ${chain.filter(function (c) { return c.gapNote; }).map(function (c) { return h`<div class="banner warn mt-12 fs-sm">${icon('triangle-alert', 15)}<div><b>${c.gap} كم</b> ${c.gapNote}: تنبيه باسم الاثنين. <a href="#/odometer">مراجعة</a></div></div>`; })}
          </div>
          <div class="col">
            <div class="card"><div class="card-h"><div class="card-t">سجل التسليم</div>${logs.length ? h`<span class="card-meta">آخر ${logs.length}</span>` : ''}</div>
              ${logs.length ? h`<div class="table-wrap"><table class="t compact"><thead><tr><th>السائق</th><th>من</th><th>إلى</th><th class="num">العداد</th></tr></thead><tbody>${logs.map(function (a) { return h`<tr><td><bdi>${a.driver}</bdi></td><td class="num">${fmt.dm(a.from.split(' ')[0])} ${a.from.split(' ')[1]}</td><td>${a.to ? h`<span class="num">${fmt.dm(a.to.split(' ')[0])} ${a.to.split(' ')[1]}</span>` : BT.pill('حالياً', 'g')}</td><td class="num">${fmt.km(a.odoFrom)}${a.odoTo ? ' ← ' + fmt.km(a.odoTo) : ''}</td></tr>`; })}</tbody></table></div>` : BT.empty('key-round', 'لا يوجد سجل', '')}</div>
            <div class="card"><div class="card-h"><div class="card-t">البيانات</div></div>${BT.kv([['الشاصي', h`<span class="num fs-sm">${v.chassis || '—'}</span>`], ['اللون', v.color], ['الفرع', v.branch], ['العداد الحالي', h`<span class="num">${fmt.km(v.odo)}</span> كم`]])}</div>
          </div>
        </div>
      </div>
      <div data-panel="handover" data-group="veh" class="col"><div class="card">${logs.length ? h`<div class="table-wrap"><table class="t"><thead><tr><th>رقم السجل</th><th>السائق</th><th>من</th><th>إلى</th><th class="num">عداد الاستلام</th><th class="num">عداد الإرجاع</th><th class="num">المسافة</th></tr></thead><tbody>${logs.map(function (a) { return h`<tr><td class="num">${a.id}</td><td>${BT.person(a.driver)}</td><td class="num">${fmt.date(a.from.split(' ')[0])} ${a.from.split(' ')[1]}</td><td>${a.to ? h`<span class="num">${fmt.date(a.to.split(' ')[0])} ${a.to.split(' ')[1]}</span>` : BT.pill('حالياً', 'g')}</td><td class="num">${fmt.km(a.odoFrom)}</td><td class="num">${a.odoTo ? fmt.km(a.odoTo) : '—'}</td><td class="num">${a.odoTo ? fmt.km(a.odoTo - a.odoFrom) + ' كم' : '—'}</td></tr>`; })}</tbody></table></div>` : BT.empty('key-round', 'لا يوجد سجل تسليم لهذه السيارة', '')}</div></div>
      <div data-panel="maint" data-group="veh" class="col"><div class="card">${jobs.length ? h`<div class="table-wrap"><table class="t"><thead><tr><th>الطلب</th><th>المركز</th><th>النوع</th><th>الحالة</th><th class="num">المدة</th><th class="num">التكلفة</th></tr></thead><tbody>${jobs.map(function (j) { return h`<tr class="clickable" data-job="${j.id}"><td class="num">${j.id}</td><td>${D.centerName(j.center)}</td><td>${j.type} · <span class="muted">${j.desc}</span></td><td>${BT.pill(j.stage, D.stageTone[j.stage])}</td><td class="num">${j.days} يوم</td><td class="num">${j.cost ? fmt.kwd(j.cost) : '—'}</td></tr>`; })}</tbody></table></div>` : BT.empty('wrench', 'لا توجد زيارات صيانة', 'آخر 12 شهراً', A.btn('طلب صيانة', { cls: 'btn-primary', icon: 'plus', action: 'maint-new', arg: v.plate }))}</div></div>
      <div data-panel="route" data-group="veh" class="col"><div class="card">${v.pos ? h`<div class="between mb-12"><div class="card-t">آخر موقع · ${lastSeen(v)}</div>${A.btn('عرض سجل المسار', { icon: 'route', cls: 'btn-primary', action: 'veh-route', arg: v.plate })}</div>${BT.kuwaitMap({ pins: [{ id: v.plate, x: v.pos[0], y: v.pos[1], label: v.plate.split('/')[1], tone: D.signalTone[D.vehicleSignal(v)] }] })}` : BT.empty('map-pin-off', 'لا يوجد موقع', 'السيارة غير مسلّمة لسائق — التتبع من هاتف السائق فقط')}</div></div>
      <div data-panel="docs" data-group="veh" class="col"><div class="card"><div class="card-h"><div class="card-t">المستندات</div>${A.btn('رفع مستند', { icon: 'upload', cls: 'btn-sm btn-primary', action: 'doc-upload', arg: v.plate })}</div>
        <div class="grid-3">${[['الاستمارة', v.regExp, 'registration.pdf'], ['التأمين', v.insuranceExp, 'insurance.pdf'], ['صور السيارة عند الاستلام', null, '4 صور']].map(function (d) {
          var n = d[1] ? BT.date.daysLeft(d[1]) : null;
          return h`<button type="button" class="doc-link" data-doc="${d[0]}"><span class="dl-ic">${icon(d[1] ? 'file-text' : 'images', 18)}</span><span class="flex-1"><b>${d[0]}</b><small>${d[2]}</small></span>${n != null ? BT.pill(n <= 30 ? fmt.daysLabel(n) : 'حتى ' + fmt.date(d[1]), n <= 30 ? 'o' : 'n') : ''}</button>`;
        })}</div></div></div>`);
    BT.on(A.view(), 'click', '[data-odo]', function (ev, b) {
      var c = chain[+b.getAttribute('data-odo')];
      A.showOdo([{ value: c.start, time: '07:4' + b.getAttribute('data-odo'), caption: 'بداية يوم ' + fmt.date(c.day) + ' — ' + c.driver, sub: 'القراءة المكتوبة: ' + fmt.km(c.start) }, { value: c.end, time: '23:0' + b.getAttribute('data-odo'), caption: 'نهاية يوم ' + fmt.date(c.day) + ' — ' + c.driver, sub: 'القراءة المكتوبة: ' + fmt.km(c.end) }]);
    });
    BT.on(A.view(), 'click', '[data-job]', function (ev, tr) { A.jobDrawer(D.jobs.find(function (j) { return j.id === tr.getAttribute('data-job'); })); });
    BT.on(A.view(), 'click', '[data-doc]', function (ev, b) {
      var t = b.getAttribute('data-doc');
      if (t.indexOf('صور') === 0) BT.lightbox(['أمام', 'خلف', 'يمين', 'يسار'].map(function (s) { return { html: h`<div class="ph" style="width:min(640px,86vw);height:400px">${icon('car', 64)}<span>${s}</span></div>`, caption: 'صورة ' + s + ' — ' + v.plate, sub: 'عند الاستلام · من الكاميرا' }; }));
      else A.docPreview(t + ' — ' + v.plate, [['رقم اللوحة', v.plate], ['الموديل', v.make + ' ' + v.model + ' ' + v.year], ['تاريخ الانتهاء', fmt.date(t === 'الاستمارة' ? v.regExp : v.insuranceExp)], ['الشاصي', v.chassis]]);
    });
  };
  A.docPreview = function (title, rows) {
    BT.lightbox({ html: h`<div class="lb-doc"><h3>${title}</h3>${BT.kv(rows)}<p class="muted fs-sm mt-24 center">معاينة توضيحية — الملف الأصلي يُعرض هنا (PDF أو صورة)</p></div>`, caption: title });
  };
  BT.actions['go'] = function (path) { A.go(path); };
  BT.actions['veh-edit'] = function (p) { A.vehicleForm(D.byPlate[p]); };
  BT.actions['veh-return'] = function (p) { A.returnCar(D.byPlate[p]); };
  BT.actions['veh-route'] = function (p) { A.route(D.byPlate[p]); };
  BT.actions['veh-more'] = function (p, el) { BT.menu(el, A.vehicleMenu(D.byPlate[p]).slice(3), { align: 'start' }); };
  BT.actions['doc-upload'] = function (p) {
    BT.modal.open({
      title: 'رفع مستند', subtitle: p, icon: 'upload', form: true,
      body: h`<div class="form">${BT.f.select({ name: 'type', label: 'نوع المستند', required: true, options: ['الاستمارة', 'التأمين', 'صور السيارة', 'أخرى'] })}${BT.f.date({ name: 'exp', label: 'تاريخ الانتهاء', optional: true })}${BT.f.upload({ name: 'file', label: 'الملف', required: true })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'رفع', cls: 'btn-primary', submit: true, icon: 'upload' }],
      onSubmit: function (f) { BT.toast('تم رفع ' + f.type, { sub: f.file[0].name }); }
    });
  };

  /* =================================================================
     تسليم السيارات  #/handover
     ================================================================= */
  BT.pages['handover'] = function () {
    A.setTitle('تسليم السيارات');
    var free = D.vehicles.filter(function (v) { return v.status === 'بلا سائق'; }).length;
    var noCar = D.employees.filter(function (e) { return e.role === 'سائق' && e.status === 'على رأس العمل' && !e.vehicleId; }).length;
    var today = D.assignments.filter(function (a) { return a.from.indexOf(cfg.today) === 0; }).length;
    BT.render(A.view(), h`
      ${A.head('من كان يقود السيارة في أي لحظة', 'كل تسليم واستلام بعداد وصورة، وسجل لا يُحذف',
        h`${A.btn('من كان يقود؟', { icon: 'search', cls: 'btn-outline', action: 'who-drove' })}${A.btn('استلام سيارة', { icon: 'log-in', cls: 'btn-outline', action: 'return-pick' })}${A.btn('تسليم سيارة', { icon: 'key-round', cls: 'btn-primary', action: 'handover-new' })}`)}
      <div class="kpis">
        ${BT.kpi({ label: 'مسلّمة الآن', value: fmt.int(D.vehicles.filter(function (v) { return v.status === 'مسلّمة'; }).length), dot: 'g', href: '#/vehicles?status=مسلّمة' })}
        ${BT.kpi({ label: 'سيارات بلا سائق', value: String(free), sub: 'جاهزة للتسليم', dot: 'o', href: '#/vehicles?status=بلا سائق' })}
        ${BT.kpi({ label: 'سائقون بلا سيارة', value: String(noCar), sub: 'على رأس العمل', dot: 'b' })}
        ${BT.kpi({ label: 'تسليمات اليوم', value: String(today), dot: 'p' })}
      </div>
      <div class="card"><div class="card-h"><div class="card-t">سجل التسليم</div><span class="card-meta">الأحدث أولاً</span></div><div id="ho-table"></div></div>`);
    BT.table(document.getElementById('ho-table'), {
      rows: function () { return D.assignments.slice().sort(function (a, b) { return b.from.localeCompare(a.from); }); },
      search: { placeholder: 'ابحث بلوحة أو سائق…', text: function (a) { return a.plate + ' ' + a.driver; } },
      chips: { key: 'state', options: [{ v: 'current', t: 'حالية' }, { v: 'closed', t: 'منتهية' }], match: function (a, v) { return v === 'current' ? !a.to : !!a.to; } },
      columns: [
        { key: 'id', label: 'السجل', render: function (a) { return h`<span class="num">${a.id}</span>`; } },
        { key: 'plate', label: 'السيارة', render: function (a) { return A.veh(D.byPlate[a.plate]); } },
        { key: 'driver', label: 'السائق', render: function (a) { return BT.person(a.driver); } },
        { key: 'from', label: 'الاستلام', render: function (a) { return h`<span class="num">${fmt.date(a.from.split(' ')[0])} ${a.from.split(' ')[1]}</span>`; } },
        { key: 'to', label: 'الإرجاع', render: function (a) { return a.to ? h`<span class="num">${fmt.date(a.to.split(' ')[0])} ${a.to.split(' ')[1]}</span>` : BT.pill('حالياً', 'g'); } },
        { key: 'odoFrom', label: 'العداد', num: true, render: function (a) { return fmt.km(a.odoFrom) + (a.odoTo ? ' ← ' + fmt.km(a.odoTo) : ''); } }
      ],
      rowMenu: function (a) { return [{ label: 'ملف السيارة', icon: 'car', onClick: function () { A.go('vehicles/' + A.slug(a.plate)); } }, { label: 'صور العداد', icon: 'camera', onClick: function () { A.showOdo([{ value: a.odoFrom, caption: 'عند الاستلام — ' + a.driver, time: a.from.split(' ')[1] }].concat(a.odoTo ? [{ value: a.odoTo, caption: 'عند الإرجاع — ' + a.driver, time: a.to.split(' ')[1] }] : [])); } }].concat(a.to ? [] : [{ label: 'استلام السيارة', icon: 'log-in', onClick: function () { A.returnCar(D.byPlate[a.plate]); } }]); }
    });
  };

  BT.actions['handover-new'] = function (plate) { A.handover(plate); };
  A.handover = function (plate) {
    var cars = D.vehicles.filter(function (v) { return v.status === 'بلا سائق' || v.plate === plate; });
    var drivers = D.employees.filter(function (e) { return e.role === 'سائق' && e.status === 'على رأس العمل' && !e.vehicleId; });
    var d = BT.modal.open({
      title: 'تسليم سيارة لسائق', icon: 'key-round', size: 'lg', form: true,
      body: h`<div class="form-grid">
        ${BT.f.select({ name: 'plate', label: 'السيارة', required: true, value: plate, options: cars.map(function (v) { return { v: v.plate, t: v.plate + ' — ' + v.make + ' ' + v.model }; }), hint: 'السيارات بلا سائق فقط' })}
        ${BT.f.select({ name: 'driver', label: 'السائق', required: true, options: drivers.map(function (e) { return { v: e.id, t: e.name + ' · ' + e.id }; }), hint: 'السائقون على رأس العمل بلا سيارة' })}
        ${BT.f.input({ name: 'at', label: 'وقت التسليم', type: 'datetime-local', required: true, value: cfg.today + 'T' + cfg.now })}
        ${BT.f.input({ name: 'odo', label: 'قراءة العداد عند التسليم', required: true, num: true, validate: 'odoMin', hint: 'اختر السيارة لعرض آخر قراءة' })}
        <div class="full hidden" id="ho-gap"></div>
        ${BT.f.camera({ name: 'photo', label: 'صورة العداد', required: true, msg: 'صورة العداد مطلوبة', full: true })}
        <div class="field full"><label>قائمة الاستلام</label><div class="grid-2" style="gap:8px">
          ${BT.f.check({ name: 'chk', value: 'reg', label: 'الاستمارة داخل السيارة', checked: true })}${BT.f.check({ name: 'chk', value: 'spare', label: 'الإطار الاحتياطي والرافعة', checked: true })}
          ${BT.f.check({ name: 'chk', value: 'bag', label: 'حقيبة التوصيل', checked: true })}${BT.f.check({ name: 'chk', value: 'nodmg', label: 'لا توجد أضرار ظاهرة' })}</div></div>
        ${BT.f.textarea({ name: 'notes', label: 'ملاحظات', optional: true, full: true, rows: 2 })}
      </div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'تأكيد التسليم', cls: 'btn-primary', icon: 'check', submit: true }],
      footNote: 'يُرسل إشعار للسائق ليؤكد الاستلام من التطبيق',
      onSubmit: function (f) {
        var v = D.byPlate[f.plate], e = D.employees.find(function (x) { return x.id === f.driver; });
        v.status = 'مسلّمة'; v.driverId = e.id; e.vehicleId = v.plate; v.odo = f.odo; v.signal = 'يرسل'; v.lastSec = 5; v.speed = 0; v.pos = v.pos || [226, 262];
        D.assignments.unshift({ id: 'A-' + (9100 + D.assignments.length), plate: v.plate, driver: e.name, from: f.at.replace('T', ' '), to: null, odoFrom: f.odo, odoTo: null });
        BT.toast('تم تسليم ' + v.plate + ' إلى ' + e.name, { sub: 'بانتظار تأكيد السائق من التطبيق' });
        A.router.refresh();
      }
    });
    function refreshHint() {
      var sel = d.el.querySelector('[name=plate]').value, v = D.byPlate[sel], odo = d.el.querySelector('[name=odo]');
      var hint = odo.closest('.field').querySelector('.hint');
      if (v) hint.textContent = 'آخر قراءة مسجلة: ' + fmt.km(v.odo);
      odo.dataset.last = v ? v.odo : '';
      var val = Number(String(odo.value).replace(/,/g, '')), gap = d.el.querySelector('#ho-gap');
      var diff = v && odo.value ? val - v.odo : 0;
      gap.classList.toggle('hidden', !(diff > cfg.odoGapKm));
      if (diff > cfg.odoGapKm) BT.render(gap, h`<div class="banner warn">${icon('triangle-alert', 16)}<div>فرق <b class="num">${diff}</b> كم عن آخر قراءة — سيُسجَّل تنبيه «كم خارج العمل» ويظهر في مراجعة العداد.</div></div>`);
    }
    d.el.querySelector('[name=plate]').addEventListener('change', refreshHint);
    d.el.querySelector('[name=odo]').addEventListener('input', refreshHint);
    refreshHint();
  };
  BT.validators.odoMin = function (v, el) { var last = +el.dataset.last; return last && Number(v.replace(/,/g, '')) < last ? 'القراءة أقل من آخر قراءة (' + fmt.km(last) + ')' : ''; };

  BT.actions['return-pick'] = function () {
    BT.modal.open({
      title: 'استلام سيارة من سائق', icon: 'log-in', size: 'sm', form: true,
      body: h`<div class="form">${BT.f.select({ name: 'plate', label: 'السيارة', required: true, options: D.vehicles.filter(function (v) { return v.status === 'مسلّمة'; }).map(function (v) { return { v: v.plate, t: v.plate + ' — ' + (D.driverOf(v) || {}).name }; }) })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'متابعة', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) { setTimeout(function () { A.returnCar(D.byPlate[f.plate]); }, 240); }
    });
  };
  A.returnCar = function (v) {
    var e = D.driverOf(v);
    BT.modal.open({
      title: 'استلام السيارة ' + v.plate, subtitle: 'من ' + (e ? e.name : ''), icon: 'log-in', size: 'lg', form: true,
      body: h`<div class="form-grid">
        ${BT.f.input({ name: 'at', label: 'وقت الاستلام', type: 'datetime-local', required: true, value: cfg.today + 'T' + cfg.now })}
        <div class="field"><label>قراءة العداد عند الاستلام<span class="req">*</span></label><input class="input num-in" name="odo" data-type="number" inputmode="decimal" required data-last="${v.odo}" data-validate="odoMin"><div class="hint">آخر قراءة: ${fmt.km(v.odo)}</div><div class="err-msg"></div></div>
        ${BT.f.camera({ name: 'photo', label: 'صورة العداد', required: true, full: true })}
        ${BT.f.radios({ name: 'cond', label: 'حالة السيارة', required: true, full: true, value: 'سليمة', options: [{ v: 'سليمة', t: 'سليمة', d: 'لا ملاحظات' }, { v: 'أضرار بسيطة', t: 'أضرار بسيطة', d: 'تُوثّق بالصور' }, { v: 'تحتاج صيانة', t: 'تحتاج صيانة', d: 'يُنشأ طلب صيانة' }] })}
        ${BT.f.textarea({ name: 'notes', label: 'ملاحظات', optional: true, full: true, rows: 2 })}
      </div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'تأكيد الاستلام', cls: 'btn-primary', icon: 'check', submit: true }],
      onSubmit: function (f) {
        var a = D.assignments.find(function (x) { return x.plate === v.plate && !x.to; });
        if (a) { a.to = f.at.replace('T', ' '); a.odoTo = f.odo; }
        if (e) e.vehicleId = null;
        v.driverId = null; v.status = f.cond === 'تحتاج صيانة' ? 'في الصيانة' : 'بلا سائق'; v.odo = f.odo; v.signal = null;
        BT.toast('تم استلام ' + v.plate, { sub: f.cond === 'تحتاج صيانة' ? 'أُنشئ طلب صيانة — اختر المركز من صفحة الصيانة' : 'السيارة جاهزة للتسليم' });
        A.router.refresh();
      }
    });
  };

  /* ---------- من كان يقود؟ ---------- */
  BT.actions['who-drove'] = function (plate) { A.whoDrove(plate); };
  A.whoDrove = function (plate) {
    var d = BT.modal.open({
      title: 'من كان يقود؟', subtitle: 'حدد السيارة والتاريخ والوقت (مثلاً لمخالفة مرورية)', icon: 'search', form: true,
      body: h`<div class="form-grid">
        <div class="full">${BT.f.select({ name: 'plate', label: 'السيارة', required: true, value: plate || '18/23456', options: D.vehicles.map(function (v) { return { v: v.plate, t: v.plate + ' — ' + v.make + ' ' + v.model }; }) })}</div>
        ${BT.f.date({ name: 'date', label: 'التاريخ', required: true, value: BT.date.add(cfg.today, -2) })}
        ${BT.f.input({ name: 'time', label: 'الوقت', type: 'time', required: true, value: '18:30' })}
        <div class="full" id="who-res"></div></div>`,
      buttons: [{ label: 'إغلاق', cls: 'btn-ghost' }, { label: 'بحث', cls: 'btn-primary', icon: 'search', submit: true }],
      onSubmit: function (f) {
        var at = f.date + ' ' + f.time;
        var a = D.assignments.find(function (x) { return x.plate === f.plate && x.from <= at && (!x.to || x.to > at); });
        var v = D.byPlate[f.plate], cur = D.driverOf(v);
        BT.render(d.el.querySelector('#who-res'), a ? h`<div class="highlight-box"><div class="flex items-center gap-12">${BT.avatar(a.driver, 'lg')}<div class="flex-1"><div class="muted fs-sm">كان يقود السيارة ${f.plate} في ${fmt.date(f.date)} الساعة ${f.time}</div><h3><bdi>${a.driver}</bdi></h3></div>${BT.pill('من سجل التسليم', 'b')}</div>
          <div class="mt-12">${BT.kv([['فترة التسليم', h`<span class="num">${fmt.date(a.from.split(' ')[0])} ${a.from.split(' ')[1]}</span> ← ${a.to ? h`<span class="num">${fmt.date(a.to.split(' ')[0])} ${a.to.split(' ')[1]}</span>` : 'حالياً'}`], ['العداد', h`<span class="num">${fmt.km(a.odoFrom)}${a.odoTo ? ' ← ' + fmt.km(a.odoTo) : ''}</span>`], ['رقم السجل', h`<span class="num">${a.id}</span>`]])}</div>
          <div class="btn-group mt-12"><button type="button" class="btn btn-sm btn-outline" data-action="soon" data-arg="إضافة مخالفة وخصمها من السائق">${icon('receipt', 14)} تسجيل مخالفة على السائق</button><button type="button" class="btn btn-sm btn-ghost" data-action="export" data-arg="إفادة من كان يقود">${icon('printer', 14)} طباعة إفادة</button></div></div>`
          : h`<div class="banner warn">${icon('circle-help', 16)}<div>لا يوجد سجل تسليم لهذه السيارة في هذا الوقت.${cur ? h` السائق الحالي: <b><bdi>${cur.name}</bdi></b> (السجل التجريبي لا يغطي التواريخ القديمة).` : ''}</div></div>`);
        return false; // تبقى النافذة مفتوحة لعرض النتيجة
      }
    });
  };

  /* =================================================================
     العداد  #/odometer
     ================================================================= */
  BT.pages['odometer'] = function () {
    A.setTitle('العداد');
    var st = D.reportStats(), pend = D.odoReviews.filter(function (x) { return x.status === 'بانتظار المراجعة'; }).length;
    BT.render(A.view(), h`
      ${A.head('كل قراءة عداد لها صورة، وكل يوم له سائق', 'السائق يكتب القراءة ويرفع صورة العداد من الكاميرا مباشرة، والنظام يربط الأيام في سلسلة لا تنقطع')}
      <div class="kpis">
        ${BT.kpi({ label: 'قراءات اليوم', value: fmt.int(st.started + st.sent), sub: st.started + ' بداية يوم · ' + st.sent + ' نهاية يوم', dot: 'b' })}
        ${BT.kpi({ label: 'بانتظار المراجعة', value: String(pend), sub: 'قراءات عليها ملاحظة', dot: 'o', tone: pend ? 'warning' : '' })}
        ${BT.kpi({ label: 'حد «كم خارج العمل»', value: cfg.odoGapKm + ' كم', sub: 'الفرق بين يومين قبل التنبيه', dot: 'p', ltr: false })}
        ${BT.kpi({ label: 'متوسط الفرق مع GPS', value: '3.1 كم', sub: 'آخر 7 أيام', dot: 'g', ltr: false })}
      </div>
      <div class="banner note">${icon('camera', 16)}<div><b>الكاميرا فقط:</b> صورة العداد تُلتقط من الكاميرا داخل التطبيق ولا يُسمح بالرفع من المعرض. النظام لا يقرأ الصورة آلياً — المراجع يقارن الرقم المكتوب بالصورة عند وجود ملاحظة.</div></div>
      <div class="card"><div class="card-h"><div class="card-t">قراءات عليها ملاحظة</div></div><div id="odo-table"></div></div>`);
    BT.table(document.getElementById('odo-table'), {
      rows: function () { return D.odoReviews; }, pageSize: 0,
      chips: { key: 'status', options: ['بانتظار المراجعة', 'تم القبول', 'تم التصحيح', 'مرفوضة'].map(function (s) { return { v: s, t: s }; }), value: 'بانتظار المراجعة' },
      columns: [
        { key: 'plate', label: 'السيارة', render: function (x) { return A.veh(D.byPlate[x.plate]); } },
        { key: 'driver', label: 'السائق', render: function (x) { return BT.person(x.driver); } },
        { key: 'date', label: 'اليوم', render: function (x) { return h`<span class="num">${fmt.date(x.date)}</span>`; } },
        { key: 'kind', label: 'الملاحظة', render: function (x) { return h`${BT.pill(x.kind, x.kind === 'أقل من السابقة' ? 'r' : 'o')}<span class="sub" style="white-space:normal;max-width:320px">${x.detail}</span>`; } },
        { key: 'status', label: 'الحالة', render: function (x) { return BT.pill(x.status, x.status === 'بانتظار المراجعة' ? 'o' : x.status === 'مرفوضة' ? 'r' : 'g'); } },
        { key: '_a', label: '', sort: false, cls: 'actions', render: function (x) { return h`<button type="button" class="btn btn-sm ${x.status === 'بانتظار المراجعة' ? 'btn-primary' : 'btn-ghost'}" data-review="${x.id}">${x.status === 'بانتظار المراجعة' ? 'مراجعة' : 'التفاصيل'}</button>`; } }
      ],
      empty: { icon: 'circle-check', title: 'لا توجد قراءات بانتظار المراجعة', text: '' }
    });
    BT.on(A.view(), 'click', '[data-review]', function (e, b) { A.odoReview(D.odoReviews.find(function (x) { return x.id === b.getAttribute('data-review'); })); });
  };
  A.odoReview = function (x) {
    var done = x.status !== 'بانتظار المراجعة';
    var d = BT.modal.open({
      title: 'مراجعة قراءة العداد', subtitle: x.plate + ' · ' + x.driver + ' · ' + fmt.iso(x.date), icon: 'gauge', iconTone: 'warn', size: 'lg', form: !done,
      body: h`<div class="banner warn mb-16">${icon('triangle-alert', 16)}<div><b>${x.kind}:</b> ${x.detail}</div></div>
        <div class="grid-2 mb-16">
          <div><div class="label mb-8">القراءة السابقة</div><button type="button" class="odo" data-zoom="0" style="width:100%"><span class="digits">${String(x.prev).padStart(6, '0')}</span><span class="meta">${icon('camera', 11)} من الكاميرا</span></button><div class="muted fs-sm mt-4">المكتوب: <span class="num">${fmt.km(x.prev)}</span></div></div>
          <div><div class="label mb-8">القراءة محل المراجعة</div><button type="button" class="odo" data-zoom="1" style="width:100%"><span class="digits">${String(x.photo || x.typed).padStart(6, '0')}</span><span class="meta">${icon('camera', 11)} من الكاميرا</span></button><div class="muted fs-sm mt-4">المكتوب: <b class="num">${fmt.km(x.typed)}</b>${x.photo && x.photo !== x.typed ? h` · <span class="t-danger">الصورة تُظهر ${fmt.km(x.photo)}</span>` : ''}</div></div>
        </div>
        ${done ? h`<div class="section-t">القرار</div>${BT.kv([['الحالة', BT.pill(x.status, x.status === 'مرفوضة' ? 'r' : 'g')], ['بواسطة', x.by], ['السبب', x.reason]])}` : h`<div class="form">
          ${BT.f.radios({ name: 'decision', label: 'القرار', required: true, options: [{ v: 'قبول', t: 'قبول القراءة', d: 'الفرق مبرر' }, { v: 'تصحيح', t: 'تصحيح القراءة', d: 'حسب الصورة' }, { v: 'رفض', t: 'رفض وإعادة التصوير', d: 'يُشعَر السائق' }] })}
          <div class="hidden" id="fix-wrap">${BT.f.input({ name: 'fixed', label: 'القراءة الصحيحة', num: true, value: x.photo || '' })}</div>
          ${BT.f.textarea({ name: 'reason', label: 'السبب', required: true, placeholder: 'يظهر في سجل التدقيق' })}
          ${x.kind === 'فرق بين يومين' ? BT.f.check({ name: 'deduct', label: 'تسجيل الكيلومترات الزائدة على السائقَين للمتابعة' }) : ''}</div>`}`,
      buttons: done ? [{ label: 'إغلاق', cls: 'btn-primary' }] : [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ القرار', cls: 'btn-primary', submit: true, icon: 'check' }],
      onSubmit: function (f) {
        if (f.decision === 'تصحيح' && !f.fixed) { BT.toast('أدخل القراءة الصحيحة', { type: 'error' }); return false; }
        x.status = f.decision === 'قبول' ? 'تم القبول' : f.decision === 'تصحيح' ? 'تم التصحيح' : 'مرفوضة'; x.by = D.currentUser.name; x.reason = f.reason;
        BT.toast('تم حفظ القرار: ' + x.status, { sub: f.decision === 'رفض' ? 'أُرسل إشعار للسائق لإعادة التصوير' : '' });
        A.router.refresh(); A.renderNav('odometer');
      }
    });
    BT.on(d.el, 'change', '[name=decision]', function (e, r) { var w = d.el.querySelector('#fix-wrap'); if (w) w.classList.toggle('hidden', r.value !== 'تصحيح'); });
    BT.on(d.el, 'click', '[data-zoom]', function (e, b) { A.showOdo([{ value: x.prev, caption: 'القراءة السابقة', sub: 'المكتوب ' + fmt.km(x.prev) }, { value: x.photo || x.typed, caption: 'القراءة محل المراجعة', sub: 'المكتوب ' + fmt.km(x.typed) }], +b.getAttribute('data-zoom')); });
  };
})();
