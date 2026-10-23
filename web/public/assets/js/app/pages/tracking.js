/* =====================================================================
   app/pages/tracking.js — التتبع الحي (خريطة + بث مباشر SSE)، مسار سيارة، التنبيهات
   الخريطة من app/map.js (MapLibre + ملف الكويت على خادمنا).
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  function mapFailed(el) { BT.render(el, BT.empty('map', 'تعذر تحميل الخريطة', 'حدّث الصفحة. إن تكرر: المتصفح لا يدعم WebGL أو ملفات الخريطة غير منشورة على الخادم')); }

  BT.pages['tracking'] = function (p, q) {
    if (q.route) return routeView(q.route, q);
    A.setTitle('التتبع الحي');
    var v = A.view();
    BT.render(v, h`${A.head('أين كل سيارة الآن', 'المواقع تصل مباشرة من هواتف السائقين خلال العهدة. «انقطاع» = لم يصل موقع خلال المدة المحددة في الإعدادات', h`<span class="pill n" data-live-state>${icon('radio', 13)} جاري الاتصال…</span>`)}
      <div class="grid" style="grid-template-columns:minmax(0,320px) minmax(0,1fr)">
        <div class="card" style="padding:12px"><div class="search-box mb-8">${icon('search', 16)}<input class="input" type="search" data-q placeholder="اللوحة أو اسم السائق…"></div>
          <div class="chips mb-8" data-chips></div><div class="side-list list" data-list>${A.spinner()}</div></div>
        <div class="live-map" data-map dir="ltr"></div>
      </div>`);
    var state = { rows: [], filter: '', q: '', selected: null, markers: {} };
    var listEl = v.querySelector('[data-list]'), chipsEl = v.querySelector('[data-chips]'), liveEl = v.querySelector('[data-live-state]');
    var map;
    function tone(r) { return !r.position ? 'n' : r.signal_lost ? 'r' : 'g'; }
    function visible() {
      var nq = BT.norm(state.q);
      return state.rows.filter(function (r) {
        if (state.filter === 'g' && tone(r) !== 'g') return false;
        if (state.filter === 'r' && tone(r) === 'g') return false;
        return !nq || BT.norm(r.vehicle.plate_number + ' ' + api.name(r.driver && r.driver.name)).indexOf(nq) > -1;
      });
    }
    function drawList() {
      var n = { all: state.rows.length, g: state.rows.filter(function (r) { return tone(r) === 'g'; }).length };
      BT.render(chipsEl, h`${[['', 'الكل', n.all], ['g', 'يرسل', n.g], ['r', 'انقطاع / بلا موقع', n.all - n.g]].map(function (c) { return h`<button type="button" class="chip${state.filter === c[0] ? ' active' : ''}" data-chip="${c[0]}">${c[1]} <span class="n">${c[2]}</span></button>`; })}`);
      var rows = visible();
      BT.render(listEl, rows.length ? h`${rows.map(function (r) {
        var t = tone(r);
        return h`<button type="button" class="li${state.selected === r.vehicle.id ? ' active' : ''}" data-veh="${r.vehicle.id}" style="width:100%;text-align:start"><span class="sdot ${t}" style="margin-top:6px"></span><div class="li-main"><div class="li-t"><span class="plate">${r.vehicle.plate_number}</span> <bdi>${api.name(r.driver && r.driver.name)}</bdi></div><div class="li-d">${r.position_hidden ? 'خارج يوم العمل: الموقع لا يظهر لصلاحيتك' : r.position ? (t === 'r' ? 'آخر موقع ' : '') + fmt.since(r.position.recorded_at) + (r.position.speed_kmh != null ? ' · ' + Math.round(r.position.speed_kmh) + ' كم/س' : '') + (r.on_duty === false ? ' · خارج يوم العمل' : '') : 'لم يصل أي موقع خلال العهدة'}</div></div></button>`;
      })}` : BT.empty('map', 'لا توجد سيارات', state.rows.length ? 'غيّر البحث أو التصفية' : 'لا توجد عهد مفتوحة الآن'));
    }
    function popup(r) {
      return String(h`<div dir="rtl" style="min-width:180px;font-family:inherit"><b class="plate">${r.vehicle.plate_number}</b><div class="mt-4"><bdi>${api.name(r.driver && r.driver.name)}</bdi></div><div class="muted fs-sm mt-4">${r.position ? fmt.dt(r.position.recorded_at) + (r.position.speed_kmh != null ? ' · ' + Math.round(r.position.speed_kmh) + ' كم/س' : '') : ''}</div><div class="mt-8 flex gap-8">${api.can('vehicles.view') ? h`<a href="#/vehicles/${r.vehicle.id}">ملف السيارة</a>` : ''}${api.can('tracking.history') ? h`<a href="#/tracking?route=${r.vehicle.id}">المسار</a>` : ''}</div></div>`);
    }
    function drawMarkers(fit) {
      if (!map) return; // الخريطة لم تُحمّل (أو تعذرت): القائمة تعمل وحدها
      var bounds = [];
      state.rows.forEach(function (r) {
        var m = state.markers[r.vehicle.id];
        if (!r.position) { if (m) { m.remove(); delete state.markers[r.vehicle.id]; } return; }
        var ll = [r.position.lat, r.position.lng], html = BT.map.carHtml(tone(r), state.selected === r.vehicle.id);
        bounds.push(ll);
        if (!m) m = state.markers[r.vehicle.id] = map.marker(ll, html, { title: r.vehicle.plate_number, onClick: function () { select(r.vehicle.id, false); } });
        else { m.move(ll); m.html(html); }
        m.popup(popup(r));
      });
      if (fit) map.fit(bounds, 13);
    }
    function select(id, pan) {
      state.selected = id;
      var r = state.rows.find(function (x) { return x.vehicle.id === id; });
      drawList(); drawMarkers(false);
      var m = state.markers[id];
      // من القائمة: تحريك الخريطة وفتح النافذة. من العلامة نفسها: الخريطة تفتحها
      if (m && pan) { map.view(m.pos(), Math.max(map.zoom(), 13)); m.open(); }
      if (r && !r.position) BT.toast('لا يوجد موقع لهذه السيارة خلال العهدة', { type: 'info' });
    }
    function refresh(fit) {
      return api.get('/tracking/live').then(function (rows) { state.rows = rows; drawList(); drawMarkers(fit); }, function (err) { BT.render(listEl, A.errorBox(err)); });
    }
    var mapEl = v.querySelector('[data-map]');
    BT.map(mapEl).then(function (m) {
      if (!m) return;
      map = m;
      refresh(true);
      // البث المباشر: موقع جديد ← تحريك العلامة فوراً
      var es = new EventSource(api.url('/tracking/live/stream'));
      es.onopen = function () { liveEl.className = 'pill g'; liveEl.innerHTML = String(h`${icon('radio', 13)} مباشر`); };
      es.onerror = function () { liveEl.className = 'pill o'; liveEl.innerHTML = String(h`${icon('wifi-off', 13)} إعادة الاتصال…`); };
      es.addEventListener('position', function (e) {
        var m = JSON.parse(e.data), r = state.rows.find(function (x) { return x.vehicle.id === m.vehicle.id; });
        if (!r) { refresh(false); return; }
        r.position = { lat: m.lat, lng: m.lng, speed_kmh: m.speed_kmh, heading: m.heading, recorded_at: m.recorded_at };
        r.signal_lost = false; r.on_duty = m.on_duty; r.position_hidden = false;
        drawMarkers(false); drawList();
      });
      var timer = setInterval(function () { if (!document.hidden) refresh(false); }, 60000); // حالة الانقطاع من الخادم
      A.onLeave(function () { es.close(); clearInterval(timer); });
    }, function (err) { if (window.console) console.error(err); mapFailed(mapEl); refresh(false); });
    BT.on(v, 'click', '[data-veh]', function (e, b) { select(b.getAttribute('data-veh'), true); });
    BT.on(chipsEl, 'click', '[data-chip]', function (e, b) { state.filter = b.getAttribute('data-chip'); drawList(); });
    v.querySelector('[data-q]').addEventListener('input', BT.debounce(function (e) { state.q = e.target.value; drawList(); }, 150));
  };

  /* ---------- مسار سيارة خلال فترة (حتى 24 ساعة) ---------- */
  function routeView(vehicleId, q) {
    A.setTitle('مسار سيارة', [['التتبع الحي', 'tracking'], ['المسار']]);
    var v = A.view();
    var end = q.end || fmt.kwInput(), start = q.start || fmt.kwInput(new Date(Date.now() - 8 * 3600 * 1000).toISOString());
    BT.render(v, h`${A.head('مسار السيارة', 'النقاط كما وصلت من هاتف السائق خلال العهدة', '')}
      <div class="card mb-16"><form class="toolbar" data-range style="margin:0">${BT.f.input({ name: 'start', label: 'من', type: 'datetime-local', value: start, required: true })}${BT.f.input({ name: 'end', label: 'إلى', type: 'datetime-local', value: end, required: true })}<button type="submit" class="btn btn-primary" style="align-self:flex-end">${icon('route', 15)} عرض</button><div data-sum class="ms-auto"></div></form></div>
      <div class="live-map" data-map dir="ltr"></div>`);
    var map, ends = [];
    function load(s, e) {
      var sum = v.querySelector('[data-sum]');
      BT.render(sum, A.spinner(''));
      api.get('/tracking/route', { vehicle_id: vehicleId, start: fmt.kwIso(s), end: fmt.kwIso(e) }).then(function (r) {
        A.setTitle('مسار ' + r.vehicle.plate_number, [['التتبع الحي', 'tracking'], [r.vehicle.plate_number]]);
        // FR-TRK-09: the driver's own time (before his day started, after it ended) in orange, or hidden without the permission
        var off = r.points.filter(function (x) { return !x.on_duty; }).length;
        BT.render(sum, h`<span class="plate">${r.vehicle.plate_number}</span> · <b class="num">${fmt.int(r.points.length)}</b> نقطة · <b class="num">${r.distance_km}</b> كم${r.drivers.length ? h` · ${r.drivers.map(function (d) { return api.name(d.name); }).join('، ')}` : ''}${r.truncated ? h` ${BT.pill('مقتطع: قلّل الفترة', 'o')}` : ''}
          ${off ? h` <span data-off-duty>${BT.pill('خارج يوم العمل: ' + r.off_duty_km + ' كم (' + fmt.int(off) + ' نقطة)', 'o')}</span>` : ''}${r.hidden_off_duty ? h` <span data-off-hidden>${BT.pill(fmt.int(r.hidden_off_duty) + ' نقطة خارج يوم العمل لا تظهر لصلاحيتك', 'n')}</span>` : ''}`);
        if (!map) return;
        ends.splice(0).forEach(function (m) { m.remove(); });
        var ll = r.points.map(function (x) { return [x.lat, x.lng]; });
        map.line(ll, r.points.map(function (x) { return !x.on_duty; }));
        if (!ll.length) { BT.toast('لا توجد نقاط في هذه الفترة', { type: 'info' }); return; }
        ends.push(map.marker(ll[0], '<div class="route-end start"></div>', { title: 'البداية ' + fmt.dt(r.points[0].t) }));
        ends.push(map.marker(ll[ll.length - 1], '<div class="route-end end"></div>', { title: 'النهاية ' + fmt.dt(r.points[r.points.length - 1].t) }));
        map.fit(ll, 15);
      }, function (err) { BT.render(sum, h`<span class="t-danger fs-sm">${api.message(err)}</span>`); });
    }
    var mapEl = v.querySelector('[data-map]');
    BT.map(mapEl).then(function (m) {
      if (!m) return;
      map = m;
      load(start, end);
    }, function (err) { if (window.console) console.error(err); mapFailed(mapEl); load(start, end); });
    v.querySelector('[data-range]').addEventListener('submit', function (e) { e.preventDefault(); var x = BT.form.values(e.target); load(x.start, x.end); });
  }

  /* ================= التنبيهات =================
     نص التنبيه = ما حدث وقت إنشائه (لا يتغير)، والحالة الآن تُحسب على الشاشة من الأوقات: كم بقي على انتهاء المستند
     اليوم، منذ متى انقطعت الإشارة، من اطّلع ومن أُسند إليه ومتى عولج. «تم الاطلاع» لا يغلق التنبيه: يبقى مفتوحاً حتى
     يزول سببه (يُغلق تلقائياً) أو يُسجَّل ما فُعل به. */
  var SEV_ICON = { critical: 'siren', warning: 'triangle-alert', info: 'info' };
  var STATUS_PILL = { 'new': ['جديد', 'b'], seen: ['اطُّلع عليه', 'o'], resolved: ['عولج', 'g'] };
  A.alertKind = function (k) { return api.t('alert_kind', k); };
  A.alertStatusPill = function (a) {
    if (a.status === 'resolved') return BT.pill(a.resolution === 'auto' ? 'أُغلق تلقائياً' : 'عولج', 'g');
    var p = STATUS_PILL[a.status] || ['—', 'n'];
    return h`${BT.pill(p[0], p[1])}${a.escalated_at ? h` ${BT.pill('مُصعّد', 'r')}` : ''}`;
  };
  function secs(iso) { return Math.max(0, Math.round((Date.now() - new Date(iso)) / 1000)); }
  /* ما هو صحيح الآن، بجانب ما قاله التنبيه وقت إنشائه */
  // brief: only what the text does not already say (the dashboard's list shows the time beside it)
  A.alertNow = function (a, brief) {
    var p = a.params || {};
    if (a.status === 'resolved') {
      return a.resolution === 'auto'
        ? h`زال السبب فأُغلق تلقائياً ${fmt.agoEl(a.resolved_at)}`
        : h`عالجه ${a.resolved_by ? a.resolved_by.name : '—'} ${fmt.agoEl(a.resolved_at)}${a.resolution_note ? h`: «${a.resolution_note}»` : ''}`;
    }
    if ((a.kind === 'document_expiring' || a.kind === 'document_expired') && p.date) {
      var n = BT.date.daysLeft(p.date);
      return h`الآن: ${BT.pill(fmt.daysLabel(n), n < 0 ? 'r' : n <= 15 ? 'o' : 'b')}`;
    }
    if (a.kind === 'signal_lost' && p.minutes != null) { // still open: no point has come since (a point closes it)
      var since = new Date(new Date(a.created_at).getTime() - p.minutes * 60000).toISOString();
      return h`لا موقع حتى الآن منذ ${fmt.time(since)} (${fmt.span(secs(since))})`;
    }
    if (a.updated_at) return h`آخر تحديث لأرقامه ${fmt.agoEl(a.updated_at)}`;
    return brief ? '' : h`مفتوح منذ ${fmt.span(secs(a.created_at))}`;
  };
  function who(a) {
    var bits = [];
    if (a.assigned_to) bits.push(h`${icon('user-round', 12)} ${a.assigned_to.name}`);
    if (a.acknowledged_by && a.status !== 'new') bits.push(h`${icon('eye', 12)} ${a.acknowledged_by.name}`);
    return bits.length ? h`<span class="sub">${bits.map(function (b, i) { return h`${i ? ' · ' : ''}${b}`; })}</span>` : '';
  }

  BT.pages['alerts'] = function (p, q) {
    A.setTitle('التنبيهات');
    var v = A.view();
    var f = { severity: q.severity || '', kind: q.kind || '', sort: 'severity', since: '', until: '' };
    var kinds = Object.keys(api.cat.alert_kind || {}).sort(function (x, y) { return A.alertKind(x).localeCompare(A.alertKind(y), 'ar'); });
    BT.render(v, h`${A.head('التنبيهات', 'تظهر لك تنبيهات صلاحياتك وشركاتك فقط. «تم الاطلاع» يسجّل أنك رأيته ويبقى مفتوحاً حتى يُعالج أو يزول سببه؛ كل إجراء يُحفظ في سجل التنبيه وسجل التدقيق. الأوقات بتوقيت الكويت', '')}
      <div class="kpis alerts-kpis" data-alert-counts></div>
      <div class="card"><div id="alerts-table"></div></div>`);
    var countsEl = v.querySelector('[data-alert-counts]');
    function counts() {
      api.get('/alerts/summary').then(function (s) {
        if (!document.contains(countsEl)) return;
        BT.render(countsEl, h`${BT.kpi({ label: 'مفتوحة', value: fmt.int(s.open), sub: fmt.int(s.critical) + ' حرجة · ' + fmt.int(s.warning) + ' تحذير · ' + fmt.int(s.info) + ' معلومة', dot: 'o', action: 'alerts-chip', arg: 'open' })}
          ${BT.kpi({ label: 'لم يطّلع عليها أحد', value: fmt.int(s['new']), sub: 'تظهر في الجرس', dot: 'b', tone: s['new'] ? 'warning' : null, action: 'alerts-chip', arg: 'new' })}
          ${BT.kpi({ label: 'مسندة إليك', value: fmt.int(s.mine), sub: 'مفتوحة وأنت المسؤول عنها', dot: 'p', action: 'alerts-chip', arg: 'mine' })}
          ${BT.kpi({ label: 'حرجة مفتوحة', value: fmt.int(s.critical), sub: 'الأخطر أولاً في القائمة', dot: 'r', tone: s.critical ? 'danger' : null, action: 'alerts-severity', arg: 'critical' })}`);
      }, function () {});
    }
    var sel = function (key, label, all, options) { return h`<select class="select" data-f="${key}" aria-label="${label}"><option value="">${all}</option>${options.map(function (o) { return h`<option value="${o[0]}"${String(o[0]) === f[key] ? raw(' selected') : ''}>${o[1]}</option>`; })}</select>`; };
    var t = BT.table(document.getElementById('alerts-table'), {
      key: 'alerts',
      fetch: function (s) {
        var query = { status: s.chip === 'mine' ? 'open' : s.chip, assigned: s.chip === 'mine' ? 'me' : null, q: s.q, severity: f.severity, kind: f.kind, sort: f.sort, offset: s.offset, limit: s.limit };
        if (f.since) query.since = f.since + 'T00:00:00+03:00';
        if (f.until) query.until = BT.date.add(f.until, 1) + 'T00:00:00+03:00';
        return api.get('/alerts', query);
      },
      search: { placeholder: 'اسم، لوحة، رقم، أو كلمة من نص التنبيه…' },
      chips: { value: q.status || 'open', all: false, options: [{ v: 'open', t: 'المفتوحة' }, { v: 'new', t: 'لم يُطّلع عليها' }, { v: 'mine', t: 'المسندة إليّ' }, { v: 'resolved', t: 'عولجت' }, { v: 'all', t: 'الكل' }] },
      tools: h`${sel('severity', 'الخطورة', 'كل الدرجات', [['critical', 'حرج'], ['warning', 'تحذير'], ['info', 'معلومة']])}
        ${sel('kind', 'النوع', 'كل الأنواع', kinds.map(function (k) { return [k, A.alertKind(k)]; }))}
        <select class="select" data-f="sort" aria-label="الترتيب"><option value="severity">الأخطر أولاً</option><option value="newest">الأحدث أولاً</option></select>
        <label class="t-date"><span>من</span><input class="input" type="date" data-f="since" aria-label="من تاريخ"></label>
        <label class="t-date"><span>إلى</span><input class="input" type="date" data-f="until" aria-label="إلى تاريخ"></label>`,
      openLabel: 'التفاصيل',
      columns: [
        { key: 'severity', label: 'الخطورة', fixed: true, render: function (a) { return A.pill('severity', a.severity); } },
        { key: 'message', label: 'التنبيه (وقت حدوثه)', fixed: true, render: function (a) { return h`<span class="alert-msg">${a.message}</span><span class="sub">${A.alertKind(a.kind)}</span>`; } },
        { key: 'created_at', label: 'وقت الحدث', render: function (a) { return h`<span class="num" title="${fmt.dtKw(a.created_at)}">${fmt.dt(a.created_at)}</span><span class="sub">${fmt.agoEl(a.created_at)}</span>`; } },
        { key: 'now', label: 'الحالة الآن', render: function (a) { return h`<div class="alert-now">${A.alertStatusPill(a)}<span class="sub">${A.alertNow(a)}</span>${who(a)}</div>`; } },
        { key: 'company', label: 'الشركة', render: function (a) { return a.company_id ? api.company(a.company_id) : '—'; } },
        { key: 'record', label: 'السجل', render: function (a) { return h`${A.alertButton(a, a.status === 'resolved')}${a.status === 'new' ? h` <button type="button" class="btn btn-sm btn-soft" data-ack="${a.id}">${icon('eye', 13)} تم الاطلاع</button>` : ''}`; } }
      ],
      rowClass: function (a) { return a.status === 'new' ? 'alert-new' : ''; },
      rowClick: function (a) { A.alertDrawer(a.id); },
      empty: { icon: 'circle-check', title: 'لا توجد تنبيهات هنا' }
    });
    A._alertsTable = { refresh: function () { t.refresh(); counts(); } }; // redrawn in place after a decision or a new alert
    counts();
    var tableEl = document.getElementById('alerts-table');
    BT.on(tableEl, 'change', '[data-f]', function (e, s) { f[s.getAttribute('data-f')] = s.value; t.refresh(); });
    BT.on(v, 'click', '[data-ack]', function (e, b) {
      b.disabled = true;
      api.post('/alerts/' + b.getAttribute('data-ack') + '/ack').then(function () { BT.toast('تم تسجيل الاطلاع، ويبقى مفتوحاً حتى يُعالج'); A._alertsTable.refresh(); A.refreshCounts(); }, function (err) { b.disabled = false; BT.toast(api.message(err), { type: 'error' }); });
    });
    BT.actions['alerts-chip'] = function (c) { t.setChip(c); };
    BT.actions['alerts-severity'] = function (s) { var x = tableEl.querySelector('[data-f=severity]'); x.value = s; f.severity = s; t.setChip('open'); };
  };

  /* تفاصيل التنبيه: ما قاله وقت إنشائه، الحالة الآن، من أُسند إليه، وسجل ما فُعل به؛ والإجراءات */
  A.alertDrawer = function (id) {
    var dlg = BT.drawer.open({ title: 'تنبيه', icon: 'bell', size: 'lg', body: A.spinner(), buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }] });
    var a = null; // the alert as last loaded; the buttons act on it (one listener, the body redrawn under it)
    function after() { A.refreshCounts(); if (A._alertsTable) A._alertsTable.refresh(); load(); }
    BT.on(dlg.body, 'click', '[data-x]', function (e, b) {
      var x = b.getAttribute('data-x');
      if (!a) return;
      if (x === 'ack') { b.disabled = true; api.post('/alerts/' + a.id + '/ack').then(function () { BT.toast('تم تسجيل الاطلاع'); after(); }, function (err) { b.disabled = false; BT.toast(api.message(err), { type: 'error' }); }); }
      if (x === 'resolve') A.confirmRun({ title: 'تمت المعالجة', message: 'يُغلق التنبيه ويُحفظ ما فعلته باسمك ووقتك في سجله وسجل التدقيق.', confirmText: 'إغلاق التنبيه', tone: 'success', reason: { label: 'ماذا فُعل؟', placeholder: 'مثال: اتصلنا بالسائق وأعاد تشغيل الـ GPS' }, run: function (note) { return api.post('/alerts/' + a.id + '/resolve', { note: note }); }, done: 'أُغلق التنبيه', after: after });
      if (x === 'assign' || x === 'escalate') pickHandler(a, x === 'escalate', after);
    });
    function load() {
      api.get('/alerts/' + id).then(function (loaded) {
        a = loaded;
        var open = a.status !== 'resolved';
        var log = [{ at: a.created_at, icon: SEV_ICON[a.severity], t: 'أُنشئ التنبيه', d: a.message }];
        if (a.updated_at) log.push({ at: a.updated_at, icon: 'refresh-cw', t: 'تحدّثت أرقامه', d: 'النص أعلاه بأحدث الأرقام' });
        a.events.forEach(function (e) {
          var t = { acknowledged: 'تم الاطلاع', assigned: 'أُسند إلى ' + (e.user ? e.user.name : '—'), unassigned: 'أُلغي الإسناد', escalated: 'صُعّد إلى ' + (e.user ? e.user.name : '—'), resolved: 'عولج وأُغلق' }[e.action] || e.action;
          log.push({ at: e.at, icon: { acknowledged: 'eye', assigned: 'user-round', unassigned: 'user-round', escalated: 'trending-up', resolved: 'circle-check' }[e.action] || 'history', t: t, by: e.by, d: e.note });
        });
        if (a.resolution === 'auto') log.push({ at: a.resolved_at, icon: 'circle-check', t: 'زال السبب فأُغلق تلقائياً' });
        log.sort(function (x, y) { return new Date(x.at) - new Date(y.at); });
        var target = A.alertTarget(a);
        dlg.setBody(h`<div class="alert-detail" data-alert="${a.id}">
          <div class="banner ${{ critical: 'danger', warning: 'warn', info: 'info' }[a.severity]} mb-12">${icon(SEV_ICON[a.severity], 16)}<div><b>${a.message}</b><div class="fs-sm mt-4">النص كما كان وقت إنشاء التنبيه${a.updated_at ? ' (بأرقام آخر تحديث)' : ''}</div></div></div>
          ${BT.kv([
            ['النوع', A.alertKind(a.kind)],
            ['الخطورة', A.pill('severity', a.severity)],
            ['وقت الحدث', h`<span class="num">${fmt.dtKw(a.created_at)}</span> · ${fmt.agoEl(a.created_at)}`],
            ['الحالة الآن', h`${A.alertStatusPill(a)} <span class="fs-sm">${A.alertNow(a)}</span>`],
            ['المسؤول عن المعالجة', a.assigned_to ? h`${a.assigned_to.name} <span class="muted fs-sm">منذ ${fmt.time(a.assigned_at)}</span>` : h`<span class="muted">لم يُسند لأحد</span>`],
            a.escalated_at ? ['التصعيد', h`${a.escalated_by ? a.escalated_by.name : '—'} · <span class="num">${fmt.dtKw(a.escalated_at)}</span>`] : null,
            ['الشركة', a.company_id ? api.company(a.company_id) : 'كل الشركات']
          ].filter(Boolean))}
          <div class="flex gap-8 mt-12" style="flex-wrap:wrap">
            ${target ? A.alertButton(a, !open) : ''}
            ${open && a.status === 'new' ? h`<button type="button" class="btn btn-sm btn-outline" data-x="ack">${icon('eye', 14)} تم الاطلاع</button>` : ''}
            ${open ? h`<button type="button" class="btn btn-sm btn-outline" data-x="assign">${icon('user-round', 14)} ${a.assigned_to ? 'تغيير المسؤول' : 'إسناد'}</button>
              <button type="button" class="btn btn-sm btn-outline" data-x="escalate">${icon('trending-up', 14)} تصعيد</button>
              <button type="button" class="btn btn-sm btn-primary" data-x="resolve">${icon('circle-check', 14)} تمت المعالجة</button>` : ''}
          </div>
          <div class="section-t mt-16">سجل الإجراءات</div>
          <div class="timeline" data-alert-log>${log.map(function (x) { return h`<div class="tl-item"><span class="tl-ic">${icon(x.icon, 13)}</span><div class="flex-1"><div class="tl-t">${x.t}${x.by ? h` <span class="muted fs-sm">— ${x.by.name}</span>` : ''}</div><div class="tl-d num">${fmt.dtKw(x.at)}</div>${x.d ? h`<div class="tl-d">${x.d}</div>` : ''}</div></div>`; })}</div>
        </div>`);
      }, function (err) { dlg.setBody(A.errorBox(err)); });
    }
    load();
  };
  function pickHandler(a, escalate, after) {
    api.get('/alerts/' + a.id + '/handlers').then(function (users) {
      var options = users.filter(function (u) { return !escalate || u.id !== api.me.public_id; }).map(function (u) { return { v: u.id, t: u.name }; });
      if (!escalate) options.unshift({ v: '', t: 'لا أحد' });
      A.formModal({
        title: escalate ? 'تصعيد التنبيه' : 'إسناد التنبيه', subtitle: a.message, icon: escalate ? 'trending-up' : 'user-round', size: 'sm',
        body: h`<div class="form">${BT.f.select({ name: 'user', label: escalate ? 'إلى' : 'المسؤول عن المعالجة', required: escalate, value: a.assigned_to ? a.assigned_to.id : '', options: options, placeholder: false, hint: 'تظهر فقط أسماء من يرى هذا التنبيه بصلاحياته وشركاته' })}
          ${BT.f.textarea({ name: 'note', label: escalate ? 'سبب التصعيد' : 'ملاحظة', required: escalate, optional: !escalate, rows: 2 })}</div>`,
        submitText: escalate ? 'تصعيد' : 'حفظ',
        submit: function (v) {
          return escalate ? api.post('/alerts/' + a.id + '/escalate', { user_id: v.user, note: v.note })
            : api.post('/alerts/' + a.id + '/assign', { user_id: v.user || null, note: v.note || null });
        },
        done: escalate ? 'صُعّد التنبيه' : 'حُفظ الإسناد',
        after: after
      });
    }, function (err) { BT.toast(api.message(err), { type: 'error' }); });
  }
})();
