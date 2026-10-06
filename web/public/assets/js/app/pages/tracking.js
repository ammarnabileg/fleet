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
        return h`<button type="button" class="li${state.selected === r.vehicle.id ? ' active' : ''}" data-veh="${r.vehicle.id}" style="width:100%;text-align:start"><span class="sdot ${t}" style="margin-top:6px"></span><div class="li-main"><div class="li-t"><span class="plate">${r.vehicle.plate_number}</span> <bdi>${api.name(r.driver && r.driver.name)}</bdi></div><div class="li-d">${r.position ? (t === 'r' ? 'آخر موقع ' : '') + fmt.since(r.position.recorded_at) + (r.position.speed_kmh != null ? ' · ' + Math.round(r.position.speed_kmh) + ' كم/س' : '') : 'لم يصل أي موقع خلال العهدة'}</div></div></button>`;
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
        r.signal_lost = false;
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
        BT.render(sum, h`<span class="plate">${r.vehicle.plate_number}</span> · <b class="num">${fmt.int(r.points.length)}</b> نقطة · <b class="num">${r.distance_km}</b> كم${r.drivers.length ? h` · ${r.drivers.map(function (d) { return api.name(d.name); }).join('، ')}` : ''}${r.truncated ? h` ${BT.pill('مقتطع: قلّل الفترة', 'o')}` : ''}`);
        if (!map) return;
        ends.splice(0).forEach(function (m) { m.remove(); });
        var ll = r.points.map(function (x) { return [x.lat, x.lng]; });
        map.line(ll);
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

  /* ================= التنبيهات ================= */
  BT.pages['alerts'] = function (p, q) {
    A.setTitle('التنبيهات');
    var v = A.view();
    BT.render(v, h`${A.head('التنبيهات', 'تظهر لك تنبيهات الصلاحيات التي تملكها فقط، ضمن شركاتك. «تم الاطلاع» يسجّل اسمك ووقتك في سجل التدقيق', '')}<div class="card"><div id="alerts-table"></div></div>`);
    var cursors = [null], open = true;
    var t = BT.table(document.getElementById('alerts-table'), {
      fetch: function (s) {
        var page = Math.round(s.offset / (s.limit - 1));
        if (open !== (s.chip !== 'closed')) { open = s.chip !== 'closed'; cursors = [null]; page = 0; }
        if (page === 0) cursors = [null];
        return api.get('/alerts', { open: open, limit: s.limit, before: cursors[page] }).then(function (rows) {
          if (rows.length >= s.limit) cursors[page + 1] = rows[s.limit - 2].created_at;
          return rows;
        });
      },
      chips: { value: 'open', all: false, options: [{ v: 'open', t: 'المفتوحة' }, { v: 'closed', t: 'كل التنبيهات' }] },
      columns: [
        { key: 'severity', label: 'الخطورة', render: function (a) { return A.pill('severity', a.severity); } },
        { key: 'message', label: 'التنبيه', render: function (a) { return h`<span style="white-space:normal">${a.message}</span>`; } },
        { key: 'created_at', label: 'الوقت', render: function (a) { return h`${fmt.dt(a.created_at)}<span class="sub">${fmt.since(a.created_at)}</span>`; } },
        { key: 'company', label: 'الشركة', render: function (a) { return a.company_id ? api.company(a.company_id) : '—'; } },
        { key: 'ack', label: '', render: function (a) { return a.acknowledged_at ? h`<span class="muted fs-sm">${icon('check', 13)} ${fmt.dt(a.acknowledged_at)}</span>` : h`<button type="button" class="btn btn-sm btn-soft" data-ack="${a.id}">${icon('check', 13)} تم الاطلاع</button>`; } }
      ],
      empty: { icon: 'circle-check', title: 'لا توجد تنبيهات' }
    });
    BT.on(v, 'click', '[data-ack]', function (e, b) {
      b.disabled = true;
      api.post('/alerts/' + b.getAttribute('data-ack') + '/ack').then(function () { BT.toast('تم تسجيل الاطلاع'); t.refresh(); A.refreshCounts(); }, function (err) { b.disabled = false; BT.toast(api.message(err), { type: 'error' }); });
    });
  };
})();
