/* =====================================================================
   app/pages/tracking.js — التتبع الحي (خريطة + بث مباشر SSE، تجميع ومتابعة وملء الشاشة)، مسار سيارة (التوقفات وفجوات
   GPS وتشغيل المسار)، التنبيهات
   الخريطة من app/map.js (MapLibre + ملف الكويت على خادمنا).
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  function mapFailed(el) { BT.render(el, BT.empty('map', 'تعذر تحميل الخريطة', 'حدّث الصفحة. إن تكرر: المتصفح لا يدعم WebGL أو ملفات الخريطة غير منشورة على الخادم')); }

  var GLIDE_MS = 1200, FOCUS_ZOOM = 16; // انزلاق العلامة للموقع الجديد، والتقريب عند اختيار سيارة
  var CLUSTER_FROM = 25, CLUSTER_PX = 56, CLUSTER_UNTIL_ZOOM = 15; // من 25 سيارة ظاهرة: المتقاربة على الشاشة مجموعة واحدة

  /* حالة السيارة كما تُعرض: لا يظهر موقع قديم كأنه حالي، عمره بجانبه دائماً */
  function vehicleState(r) {
    var p = r.position, age = p ? (Date.now() - new Date(p.recorded_at)) / 1000 : null;
    var lostAfter = (r.signal_loss_minutes || 10) * 60, off = r.on_duty === false ? ' · خارج يوم العمل' : '';
    var speed = p && p.speed_kmh != null ? ' · ' + Math.round(p.speed_kmh) + ' كم/س' : '';
    if (r.position_hidden) return { tone: 'n', stale: true, text: 'خارج يوم العمل: الموقع لا يظهر لصلاحيتك' };
    if (r.in_maintenance) return { tone: 'n', stale: true, text: 'في مركز الصيانة: لا يُتتبَّع' + (p ? ' · آخر موقع ' + fmt.since(p.recorded_at) : '') };
    if (!p) return r.signal_lost ? { tone: 'r', stale: true, text: 'لم يصل أي موقع منذ بداية العهدة' + off } : { tone: 'n', stale: true, text: 'بانتظار أول موقع من الهاتف' + off };
    if (r.signal_lost || age > lostAfter) return { tone: 'r', stale: true, text: 'انقطاع · آخر موقع معروف ' + fmt.since(p.recorded_at) + ' (' + fmt.time(p.recorded_at) + ')' + off };
    return { tone: 'g', stale: false, text: 'يرسل · آخر موقع ' + fmt.since(p.recorded_at) + speed + off };
  }

  BT.pages['tracking'] = function (p, q) {
    if (q.route) return routeView(q.route, q);
    A.setTitle('التتبع الحي');
    var v = A.view();
    var pane = BT.store.get('tracking-pane', 'map');
    BT.render(v, h`${A.head('أين كل سيارة الآن', 'المواقع تصل مباشرة من هواتف السائقين خلال العهدة. بجانب كل سيارة عمر آخر موقع وصل منها؛ «انقطاع» = لم يصل موقع خلال المدة المحددة في الإعدادات، والعلامة الباهتة آخر موقع معروف لا الموقع الحالي', h`<span class="pill n" data-live-state>${icon('radio', 13)} جاري الاتصال بالبث…</span>`)}
      <div class="tabs trk-switch mb-12" role="group" aria-label="طريقة العرض"><button type="button" data-pane-btn="list">${icon('list', 14)} القائمة</button><button type="button" data-pane-btn="map">${icon('map', 14)} الخريطة</button></div>
      <div class="trk" data-trk>
        <div class="card trk-side"><div class="search-box mb-8">${icon('search', 16)}<input class="input" type="search" data-q placeholder="اللوحة أو اسم السائق…" aria-label="بحث باللوحة أو اسم السائق"></div>
          <div class="chips mb-8" data-chips></div><div class="side-list list" data-list>${A.spinner()}</div></div>
        <div class="trk-main" data-map-wrap><div class="live-map" data-map dir="ltr"></div></div>
      </div>`);
    var state = { rows: [], byId: {}, rowEls: {}, filter: '', q: '', selected: null, follow: false, markers: {}, clusters: {}, stream: 'connecting', lastEvent: null, fitted: false };
    function index() { state.byId = {}; state.rows.forEach(function (r) { state.byId[r.vehicle.id] = r; }); }
    var listEl = v.querySelector('[data-list]'), chipsEl = v.querySelector('[data-chips]'), liveEl = v.querySelector('[data-live-state]');
    var trk = v.querySelector('[data-trk]'), mapEl = v.querySelector('[data-map]');
    var map, tools;

    function setPane(x) {
      pane = x;
      trk.setAttribute('data-pane', x);
      BT.$$('[data-pane-btn]', v).forEach(function (b) { var on = b.getAttribute('data-pane-btn') === x; b.classList.toggle('active', on); b.setAttribute('aria-pressed', on ? 'true' : 'false'); });
      BT.store.set('tracking-pane', x);
      if (x === 'map' && map) map.resize();
    }
    setPane(pane);
    function narrow() { return getComputedStyle(v.querySelector('.trk-switch')).display !== 'none'; }

    function tone(r) { return vehicleState(r).tone; }
    function visible() { return state.rows.filter(matches); }
    function drawChips() {
      var n = { all: state.rows.length, g: state.rows.filter(function (r) { return tone(r) === 'g'; }).length };
      BT.render(chipsEl, h`${[['', 'الكل', n.all], ['g', 'يرسل الآن', n.g], ['r', 'انقطاع / بلا موقع', n.all - n.g]].map(function (c) { return h`<button type="button" class="chip${state.filter === c[0] ? ' active' : ''}" aria-pressed="${state.filter === c[0] ? 'true' : 'false'}" data-chip="${c[0]}">${c[1]} <span class="n">${c[2]}</span></button>`; })}`);
    }
    function drawList() {
      drawChips();
      var rows = visible();
      BT.render(listEl, rows.length ? h`${rows.map(function (r) {
        var st = vehicleState(r);
        return h`<button type="button" class="li${state.selected === r.vehicle.id ? ' active' : ''}" aria-pressed="${state.selected === r.vehicle.id ? 'true' : 'false'}" data-veh="${r.vehicle.id}" style="width:100%;text-align:start"><span class="sdot ${st.tone}" style="margin-top:6px"></span><div class="li-main"><div class="li-t"><span class="plate">${r.vehicle.plate_number}</span> <bdi>${api.name(r.driver && r.driver.name)}</bdi></div><div class="li-d" data-veh-state>${st.text}</div></div></button>`;
      })}` : BT.empty('map', 'لا توجد سيارات', state.rows.length ? 'غيّر البحث أو التصفية' : 'لا توجد عهد مفتوحة الآن'));
      state.rowEls = {};
      BT.$$('[data-veh]', listEl).forEach(function (b) { state.rowEls[b.getAttribute('data-veh')] = b; });
      drawTools();
    }
    /* السيارات التي وصل منها موقع: لون صفها ونص حالتها في مكانهما، بلا إعادة بناء القائمة؛ إلا إن خرجت سيارة من
       التصفية أو دخلتها (يرسل الآن / انقطاع)، فالقائمة كلها */
    function updateRows(ids) {
      drawChips();
      var rebuild = ids.some(function (id) { var r = state.byId[id]; return r && !!state.rowEls[id] !== matches(r); });
      if (rebuild) { drawList(); return; }
      ids.forEach(function (id) {
        var r = state.byId[id], b = state.rowEls[id];
        if (!r || !b) return;
        var st = vehicleState(r), dot = b.querySelector('.sdot'), txt = b.querySelector('[data-veh-state]');
        if (dot) dot.className = 'sdot ' + st.tone;
        if (txt && txt.textContent !== st.text) txt.textContent = st.text;
      });
      drawTools();
    }
    function popup(r) {
      var st = vehicleState(r);
      return String(h`<div dir="rtl" style="min-width:190px;font-family:inherit"><b class="plate">${r.vehicle.plate_number}</b><div class="mt-4"><bdi>${api.name(r.driver && r.driver.name)}</bdi></div><div class="fs-sm mt-4 ${st.tone === 'g' ? '' : 't-danger'}">${st.text}</div><div class="muted fs-sm mt-4">آخر موقع وصل: ${r.position ? fmt.dt(r.position.recorded_at) : '—'}</div><div class="mt-8 flex gap-8">${api.can('vehicles.view') ? h`<a href="#/vehicles/${r.vehicle.id}">ملف السيارة</a>` : ''}${api.can('tracking.history') ? h`<a href="#/tracking?route=${r.vehicle.id}">المسار</a>` : ''}</div></div>`);
    }
    function drawMarkers() {
      if (!map) return; // الخريطة لم تُحمّل (أو تعذرت): القائمة تعمل وحدها
      var shown = {};
      visible().forEach(function (r) { shown[r.vehicle.id] = true; });
      state.rows.forEach(function (r) { drawMarker(r, !!shown[r.vehicle.id]); });
      Object.keys(state.markers).forEach(function (id) { if (!state.byId[id]) { state.markers[id].remove(); delete state.markers[id]; } });
      cluster();
    }
    /* علامة سيارة واحدة: الموقع الواصل من البث يحرّك علامته وحدها، لا كل العلامات */
    function drawMarker(r, shown) {
      var m = state.markers[r.vehicle.id];
      if (!r.position) { if (m) { m.remove(); delete state.markers[r.vehicle.id]; } return; }
      var st = vehicleState(r), ll = [r.position.lat, r.position.lng], moving = r.position.speed_kmh != null && r.position.speed_kmh >= 3, html = BT.map.carHtml(st.tone, state.selected === r.vehicle.id, st.stale, moving ? r.position.heading : null);
      if (!m) m = state.markers[r.vehicle.id] = map.marker(ll, html, { onClick: function () { select(r.vehicle.id, true); } });
      else { m.move(ll, GLIDE_MS); m.html(html); }
      m.title(r.vehicle.plate_number + ' — ' + st.text);
      m.el.setAttribute('data-veh-mark', r.vehicle.id);
      m.shown = shown;
      m.popup(function () { return popup(r); }); // تُبنى عند فتحها فقط
    }
    function matches(r) {
      if (state.filter === 'g' && tone(r) !== 'g') return false;
      if (state.filter === 'r' && tone(r) === 'g') return false;
      var nq = BT.norm(state.q);
      return !nq || BT.norm(r.vehicle.plate_number + ' ' + api.name(r.driver && r.driver.name)).indexOf(nq) > -1;
    }
    /* تجميع العلامات المتقاربة على الشاشة عند كثرتها؛ السيارة المحددة تبقى وحدها دائماً */
    function cluster() {
      if (!map) return;
      var ids = Object.keys(state.markers).filter(function (id) { return state.markers[id].shown; });
      var groups = {}, keep = {};
      if (ids.length >= CLUSTER_FROM && map.zoom() < CLUSTER_UNTIL_ZOOM) {
        ids.forEach(function (id) {
          if (id === state.selected) return;
          var px = map.project(state.markers[id].pos()), key = Math.floor(px.x / CLUSTER_PX) + ':' + Math.floor(px.y / CLUSTER_PX);
          (groups[key] = groups[key] || []).push(id);
        });
      }
      var inCluster = {};
      Object.keys(groups).forEach(function (k) {
        var g = groups[k];
        if (g.length < 2) return;
        g.sort();
        var sig = g.join(','), pts = g.map(function (id) { return state.markers[id].pos(); });
        var center = [BT.sum(pts, function (x) { return x[0]; }) / pts.length, BT.sum(pts, function (x) { return x[1]; }) / pts.length];
        var lost = g.filter(function (id) { var r = state.byId[id]; return r && vehicleState(r).tone !== 'g'; }).length;
        var c = state.clusters[sig];
        if (!c) c = state.clusters[sig] = map.marker(center, BT.map.clusterHtml(g.length, lost), { onClick: function () { map.fitBounds(pts.slice(), 16); } });
        else { c.move(center); c.html(BT.map.clusterHtml(g.length, lost)); }
        c.title(g.length + ' سيارات متقاربة' + (lost ? '، منها ' + lost + ' بلا موقع حالي' : '') + ' — اضغط للتكبير');
        keep[sig] = true;
        g.forEach(function (id) { inCluster[id] = true; });
      });
      Object.keys(state.clusters).forEach(function (sig) { if (!keep[sig]) { state.clusters[sig].remove(); delete state.clusters[sig]; } });
      Object.keys(state.markers).forEach(function (id) { var m = state.markers[id]; m.show(m.shown && !inCluster[id]); });
    }
    function positioned() { return visible().filter(function (r) { return r.position; }).map(function (r) { return [r.position.lat, r.position.lng]; }); }
    function selectedRow() { return state.byId[state.selected]; }
    function drawTools() {
      if (!tools) return;
      var r = selectedRow(), n = positioned().length;
      var fit = tools.querySelector('[data-fit]'), follow = tools.querySelector('[data-follow]');
      fit.disabled = !n;
      fit.title = n ? 'إظهار كل السيارات الظاهرة في القائمة (' + n + ')' : 'لا توجد مواقع لإظهارها';
      follow.disabled = !(r && r.position);
      follow.classList.toggle('active', state.follow);
      follow.setAttribute('aria-pressed', state.follow ? 'true' : 'false');
      follow.title = !r ? 'اختر سيارة من القائمة أو الخريطة أولاً' : !r.position ? 'لا يوجد موقع لهذه السيارة' : state.follow ? 'إيقاف متابعة ' + r.vehicle.plate_number : 'إبقاء ' + r.vehicle.plate_number + ' في وسط الخريطة مع كل موقع جديد';
    }
    function select(id, pan) {
      state.selected = id;
      var r = selectedRow();
      drawList(); drawMarkers();
      var m = state.markers[id];
      if (pan && narrow()) setPane('map');
      // من القائمة أو العلامة: الخريطة تطير إليها وتقرّب وتتابعها مع كل موقع جديد (سحب الخريطة يوقف المتابعة)
      if (m && pan) { state.follow = !!(r && r.position); map.fly(m.pos(), Math.max(map.zoom(), FOCUS_ZOOM)); m.open(); drawTools(); }
      if (r && !r.position) BT.toast('لا يوجد موقع لهذه السيارة خلال العهدة', { type: 'info' });
    }
    function drawLive() {
      var s = state.stream, last = state.lastEvent ? ' · آخر موقع وصل ' + fmt.time(state.lastEvent) : '';
      var view = {
        connecting: ['n', 'radio', 'جاري الاتصال بالبث…', ''],
        live: ['g', 'radio', 'مباشر' + last, 'البث المباشر متصل: كل موقع جديد يظهر فوراً'],
        reconnecting: ['o', 'wifi-off', 'البث منقطع: إعادة الاتصال…', 'المواقع المعروضة قد تكون قديمة؛ عمر كل موقع مكتوب بجانبه، وتُحدَّث القائمة كل دقيقة'],
        closed: ['r', 'wifi-off', 'البث متوقف: تحديث كل دقيقة', 'تعذر الاتصال بالبث المباشر؛ حدّث الصفحة. عمر كل موقع مكتوب بجانبه']
      }[s];
      liveEl.className = 'pill ' + view[0];
      liveEl.title = view[3];
      liveEl.setAttribute('data-stream', s);
      BT.render(liveEl, h`${icon(view[1], 13)} ${view[2]}`);
    }
    function refresh() {
      return api.get('/tracking/live').then(function (rows) {
        state.rows = rows; index(); drawList(); drawMarkers();
        if (map && !state.fitted) { state.fitted = true; map.fit(positioned(), 13); }
      }, function (err) { BT.render(listEl, A.errorBox(err)); });
    }
    function stream() {
      var es = new EventSource(api.url('/tracking/live/stream'));
      es.onopen = function () { state.stream = 'live'; drawLive(); };
      es.onerror = function () { state.stream = es.readyState === 2 ? 'closed' : 'reconnecting'; drawLive(); };
      // موقع جديد ← تحريك العلامة فوراً (وتوسيط الخريطة عليها إن كانت متابَعة)
      // مئات السيارات ترسل معاً: كل موقع يُسجَّل فوراً، والرسم مجمّع (العلامات التي تغيّرت كل ربع ثانية، والقائمة
      // والتجميع كل ثانيتين) بدل إعادة رسم كل العلامات والقائمة مع كل موقع، وهو ما كان يجمّد الصفحة
      var dirty = {}, listed = {}, flushT = null, listT = null, unknownT = null;
      function flush() {
        flushT = null;
        var ids = Object.keys(dirty); dirty = {};
        ids.forEach(function (id) { listed[id] = true; var r = state.byId[id]; if (map && r) drawMarker(r, matches(r)); });
        if (!listT) listT = setTimeout(function () { listT = null; var l = Object.keys(listed); listed = {}; updateRows(l); cluster(); }, 2000);
      }
      es.addEventListener('position', function (e) {
        var m = JSON.parse(e.data), r = state.byId[m.vehicle.id];
        state.lastEvent = new Date().toISOString();
        if (!r) { if (!unknownT) unknownT = setTimeout(function () { unknownT = null; refresh(); }, 10000); return; } // سيارة سُلّمت بعد فتح الصفحة: مرة كل 10 ثوانٍ
        r.position = { lat: m.lat, lng: m.lng, speed_kmh: m.speed_kmh, heading: m.heading, recorded_at: m.recorded_at };
        r.signal_lost = false; r.on_duty = m.on_duty; r.position_hidden = false; // الحداثة من وقت الموقع نفسه (vehicleState)
        dirty[r.vehicle.id] = true;
        if (!flushT) flushT = setTimeout(function () { drawLive(); flush(); }, 250);
        if (map && state.follow && r.vehicle.id === state.selected) map.view([m.lat, m.lng], map.zoom(), GLIDE_MS);
      });
      var poll = setInterval(function () { if (!document.hidden) refresh(); }, 30000); // الانقطاع والسيارات الجديدة من الخادم
      var tick = setInterval(function () { if (!document.hidden) { drawList(); drawMarkers(); } }, 15000); // عمر كل موقع يتقدم
      A.onLeave(function () { es.close(); clearInterval(poll); clearInterval(tick); clearTimeout(flushT); clearTimeout(listT); clearTimeout(unknownT); });
    }
    function mapTools() {
      tools = document.createElement('div');
      tools.className = 'maplibregl-ctrl maplibregl-ctrl-group trk-tools';
      tools.innerHTML = String(h`<button type="button" data-fit aria-label="احتواء كل السيارات الظاهرة">${icon('maximize', 15)}<span>الكل</span></button><button type="button" data-follow aria-label="متابعة السيارة المحددة" aria-pressed="false">${icon('focus', 15)}<span>متابعة</span></button>`);
      tools.querySelector('[data-fit]').onclick = function () { state.follow = false; map.fitBounds(positioned(), 15); drawTools(); };
      tools.querySelector('[data-follow]').onclick = function () {
        var r = selectedRow();
        state.follow = !state.follow && !!(r && r.position);
        if (state.follow) map.view([r.position.lat, r.position.lng], Math.max(map.zoom(), 14));
        drawTools();
      };
      map.control(tools, 'top-right');
      map.on('dragstart', function () { if (state.follow) { state.follow = false; drawTools(); } }); // المستخدم حرّك الخريطة بنفسه
      map.on('moveend', cluster);
    }
    drawLive();
    BT.map(mapEl, { fullscreen: v.querySelector('[data-map-wrap]') }).then(function (m) {
      if (!m) return;
      map = m;
      mapTools();
      refresh();
      stream();
    }, function (err) { if (window.console) console.error(err); mapFailed(mapEl); refresh(); stream(); });
    BT.on(v, 'click', '[data-veh]', function (e, b) { select(b.getAttribute('data-veh'), true); });
    BT.on(v, 'click', '[data-pane-btn]', function (e, b) { setPane(b.getAttribute('data-pane-btn')); });
    BT.on(chipsEl, 'click', '[data-chip]', function (e, b) { state.filter = b.getAttribute('data-chip'); drawList(); drawMarkers(); });
    v.querySelector('[data-q]').addEventListener('input', BT.debounce(function (e) { state.q = e.target.value; drawList(); drawMarkers(); }, 150));
  };

  /* ---------- مسار سيارة خلال فترة (حتى 48 ساعة): التوقفات وفجوات GPS وتشغيل المسار ---------- */
  var SPEEDS = [10, 30, 60, 120, 300];

  function routeView(vehicleId, q) {
    A.setTitle('مسار سيارة', [['التتبع الحي', 'tracking'], ['المسار']]);
    var v = A.view();
    var end = q.end || fmt.kwInput(), start = q.start || fmt.kwInput(new Date(Date.now() - 8 * 3600 * 1000).toISOString());
    BT.render(v, h`${A.head('مسار السيارة', 'النقاط كما وصلت من هاتف السائق خلال العهدة. الخط المتقطع الرمادي فجوة: لم يصل موقع خلالها، فهو ليس الطريق الذي سلكته السيارة', '')}
      <div class="card mb-16"><form class="toolbar" data-range style="margin:0">${BT.f.input({ name: 'start', label: 'من', type: 'datetime-local', value: start, required: true })}${BT.f.input({ name: 'end', label: 'إلى', type: 'datetime-local', value: end, required: true })}<button type="submit" class="btn btn-primary" style="align-self:flex-end">${icon('route', 15)} عرض</button><div data-sum class="ms-auto"></div></form></div>
      <div class="card mb-12 route-play" data-play hidden>
        <button type="button" class="btn btn-sm btn-primary" data-play-btn aria-label="تشغيل المسار">${icon('play', 14)} تشغيل</button>
        <label class="route-slider"><span class="sr-only">موضع التشغيل</span><input type="range" min="0" max="0" value="0" step="1" data-play-pos aria-label="موضع التشغيل على المسار"></label>
        <label class="fs-sm muted">السرعة <select class="select" data-play-speed aria-label="سرعة التشغيل">${SPEEDS.map(function (x) { return h`<option value="${x}"${x === 60 ? ' selected' : ''}>×${x}</option>`; })}</select></label>
        <div class="fs-sm route-now" data-play-now aria-live="off"></div>
      </div>
      <div class="live-map" data-map dir="ltr"></div>
      <div class="card mt-16" data-events hidden></div>`);
    var map, ends = [], extras = [], play = null;
    function stopPlay() { if (play && play.timer) { clearInterval(play.timer); play.timer = null; } drawPlayBtn(); }
    function drawPlayBtn() {
      var b = v.querySelector('[data-play-btn]'), on = !!(play && play.timer);
      BT.render(b, h`${icon(on ? 'pause' : 'play', 14)} ${on ? 'إيقاف' : 'تشغيل'}`);
      b.setAttribute('aria-label', on ? 'إيقاف التشغيل' : 'تشغيل المسار');
    }
    A.onLeave(stopPlay);

    /* موضع السيارة في لحظة من المسار: بين نقطتين متتاليتين بالتناسب مع الوقت؛ داخل فجوة: آخر نقطة قبلها */
    function at(r, ms) {
      var pts = r.points, times = play.times, lo = 0, hi = pts.length - 1;
      while (lo < hi) { var mid = (lo + hi + 1) >> 1; if (times[mid] <= ms) lo = mid; else hi = mid - 1; }
      var a = pts[lo], b = pts[lo + 1];
      if (!b) return { ll: [a.lat, a.lng], p: a, gap: false };
      if (b.break_before) return { ll: [a.lat, a.lng], p: a, gap: b.break_before };
      var f = (ms - times[lo]) / Math.max(1, times[lo + 1] - times[lo]);
      return { ll: [a.lat + (b.lat - a.lat) * f, a.lng + (b.lng - a.lng) * f], p: f < 0.5 ? a : b, gap: false };
    }
    function stopAt(r, ms) { return r.stops.find(function (s) { return new Date(s.from) <= ms && ms <= new Date(s.to); }); }
    function showAt(r, offset) {
      var ms = play.times[0] + offset * 1000, x = at(r, ms), stop = stopAt(r, ms);
      play.offset = offset;
      v.querySelector('[data-play-pos]').value = String(Math.round(offset));
      if (map) { if (!play.marker) play.marker = map.marker(x.ll, BT.map.carHtml('g', true), { title: r.vehicle.plate_number }); else play.marker.move(x.ll); }
      var what = x.gap === 'signal' ? BT.pill('فجوة GPS: لم يصل موقع', 'o') : x.gap === 'hidden' ? BT.pill('خارج يوم العمل (مخفي)', 'n') : stop ? BT.pill('متوقف ' + stop.minutes + ' د', 'n') : x.p.speed_kmh != null ? h`<b class="num">${Math.round(x.p.speed_kmh)}</b> كم/س` : '';
      BT.render(v.querySelector('[data-play-now]'), h`<b>${fmt.dt(new Date(ms).toISOString())}</b> ${what}`);
    }
    function setupPlay(r) {
      stopPlay();
      if (play && play.marker) play.marker.remove();
      var box = v.querySelector('[data-play]');
      box.hidden = r.points.length < 2;
      if (box.hidden) { play = null; return; }
      var times = r.points.map(function (x) { return new Date(x.t).getTime(); });
      play = { r: r, times: times, offset: 0, total: (times[times.length - 1] - times[0]) / 1000, timer: null, marker: null };
      var pos = v.querySelector('[data-play-pos]');
      pos.max = String(Math.round(play.total));
      showAt(r, 0);
    }
    v.querySelector('[data-play-btn]').onclick = function () {
      if (!play) return;
      if (play.timer) { stopPlay(); return; }
      if (play.offset >= play.total) play.offset = 0;
      play.timer = setInterval(function () {
        var speed = +v.querySelector('[data-play-speed]').value;
        var next = Math.min(play.total, play.offset + 0.25 * speed);
        showAt(play.r, next);
        if (map && play.marker) { var c = play.marker.pos(); map.view(c, map.zoom()); }
        if (next >= play.total) stopPlay();
      }, 250);
      drawPlayBtn();
    };
    v.querySelector('[data-play-pos]').addEventListener('input', function (e) { if (play) showAt(play.r, +e.target.value); });

    function drawEvents(r) {
      var box = v.querySelector('[data-events]');
      var items = r.stops.map(function (s) { return { t: s.from, kind: 'stop', s: s }; }).concat(r.gaps.map(function (g) { return { t: g.from, kind: 'gap', g: g }; }));
      items.sort(function (a, b) { return new Date(a.t) - new Date(b.t); });
      box.hidden = !r.points.length;
      BT.render(box, h`<div class="card-h"><div class="card-t">${icon('list', 16)} التوقفات وفجوات GPS</div><span class="ms-auto muted fs-sm">توقف = بقيت ضمن 150 م لمدة 5 دقائق أو أكثر · فجوة = لم يصل موقع أكثر من ${r.gap_minutes} دقيقة</span></div>
        ${items.length ? h`<div class="list">${items.map(function (it, i) {
          if (it.kind === 'stop') return h`<button type="button" class="li" style="width:100%;text-align:start" data-event="${i}"><span class="sdot n" style="margin-top:6px"></span><div class="li-main"><div class="li-t">توقف <b class="num">${it.s.minutes}</b> دقيقة</div><div class="li-d">${fmt.time(it.s.from)} – ${fmt.time(it.s.to)} · ${fmt.dt(it.s.from)}</div></div></button>`;
          return h`<button type="button" class="li" style="width:100%;text-align:start" data-event="${i}"><span class="sdot o" style="margin-top:6px"></span><div class="li-main"><div class="li-t">فجوة GPS <b class="num">${it.g.minutes}</b> دقيقة</div><div class="li-d">${fmt.time(it.g.from)} – ${fmt.time(it.g.to)} · ${it.g.km} كم بخط مستقيم بين طرفيها (المسار الفعلي غير معروف)</div></div></button>`;
        })}</div>` : h`<div class="card-b muted fs-sm">لا توقفات ولا فجوات في هذه الفترة</div>`}`);
      box.onclick = function (e) {
        var b = e.target.closest('[data-event]');
        if (!b || !map) return;
        var it = items[+b.getAttribute('data-event')];
        if (it.kind === 'stop') map.view([it.s.lat, it.s.lng], Math.max(map.zoom(), 16));
        else {
          var k = r.points.findIndex(function (x) { return x.t === it.g.to; });
          if (k > 0) map.fitBounds([[r.points[k - 1].lat, r.points[k - 1].lng], [r.points[k].lat, r.points[k].lng]], 16);
        }
        if (play) showAt(r, (new Date(it.kind === 'stop' ? it.s.from : it.g.from) - play.times[0]) / 1000);
        map.raw.getContainer().scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      };
    }
    function load(s, e) {
      var sum = v.querySelector('[data-sum]');
      BT.render(sum, A.spinner(''));
      api.get('/tracking/route', { vehicle_id: vehicleId, start: fmt.kwIso(s), end: fmt.kwIso(e) }).then(function (r) {
        A.setTitle('مسار ' + r.vehicle.plate_number, [['التتبع الحي', 'tracking'], [r.vehicle.plate_number]]);
        // FR-TRK-09: the driver's own time (before his day started, after it ended) in orange, or hidden without the permission
        var off = r.points.filter(function (x) { return !x.on_duty; }).length;
        BT.render(sum, h`<span class="plate">${r.vehicle.plate_number}</span> · <b class="num">${fmt.int(r.points.length)}</b> نقطة · <b class="num">${r.distance_km}</b> كم${r.drivers.length ? h` · ${r.drivers.map(function (d) { return api.name(d.name); }).join('، ')}` : ''}${r.truncated ? h` ${BT.pill('مقتطع: قلّل الفترة', 'o')}` : ''}
          ${r.stops.length ? h` · <span data-stops><b class="num">${r.stops.length}</b> توقف</span>` : ''}${r.gaps.length ? h` <span data-gaps>${BT.pill(r.gaps.length + ' فجوة GPS', 'o')}</span>` : ''}
          ${off ? h` <span data-off-duty>${BT.pill('خارج يوم العمل: ' + r.off_duty_km + ' كم (' + fmt.int(off) + ' نقطة)', 'o')}</span>` : ''}${r.hidden_off_duty ? h` <span data-off-hidden>${BT.pill(fmt.int(r.hidden_off_duty) + ' نقطة خارج يوم العمل لا تظهر لصلاحيتك', 'n')}</span>` : ''}`);
        drawEvents(r);
        setupPlay(r);
        if (!map) return;
        ends.splice(0).forEach(function (m) { m.remove(); });
        extras.splice(0).forEach(function (m) { m.remove(); });
        var ll = r.points.map(function (x) { return [x.lat, x.lng]; });
        map.line(ll, r.points.map(function (x) { return !x.on_duty; }), r.points.map(function (x) { return !!x.break_before; }));
        if (!ll.length) { BT.toast('لا توجد نقاط في هذه الفترة', { type: 'info' }); return; }
        r.stops.forEach(function (st) { extras.push(map.marker([st.lat, st.lng], '<div class="route-stop">P</div>', { title: 'توقف ' + st.minutes + ' دقيقة: ' + fmt.time(st.from) + ' – ' + fmt.time(st.to) })); });
        ends.push(map.marker(ll[0], '<div class="route-end start"></div>', { title: 'البداية ' + fmt.dt(r.points[0].t) }));
        ends.push(map.marker(ll[ll.length - 1], '<div class="route-end end"></div>', { title: 'النهاية ' + fmt.dt(r.points[r.points.length - 1].t) }));
        if (play && play.marker) { play.marker.remove(); play.marker = null; showAt(r, 0); }
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
