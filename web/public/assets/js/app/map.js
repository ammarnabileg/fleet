/* =====================================================================
   app/map.js — الخريطة (MapLibre GL، تُحمّل عند فتح صفحة فيها خريطة)
   الخريطة الأساسية من خادمنا: ملف واحد للكويت (Protomaps PMTiles من بيانات OpenStreetMap) في BT.config.mapPmtiles،
   يقرأ المتصفح منه ما يلزم فقط بطلبات HTTP Range. لا رسوم ولا حدود استخدام، ولا يرى طرف ثالث مواقع السيارات
   ولا ما يشاهده المشرف. الملف تنزّله وتحدّثه خدمة maps في docker-compose (deploy/maps). إن لم يوجد على الخادم:
   بلاطات BT.config.mapFallbackTiles مع ملاحظة ظاهرة على الخريطة تقول السبب (maps/status.json من الخدمة نفسها).
   الإحداثيات في هذه الواجهة [lat, lng] كما في بقية النظام (MapLibre نفسه يستخدم [lng, lat]).
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, A = BT.A, h = BT.h;
  var V = 'assets/vendor/maps/';
  var ATTRIBUTION = '<a href="https://protomaps.com" target="_blank" rel="noopener">Protomaps</a> © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>';
  var loading = null;

  function abs(path) { return new URL(path, document.baseURI).href; }
  function lngLat(p) { return [p[1], p[0]]; }

  /* المكتبات مرة واحدة للصفحة كلها */
  function libs() {
    if (!loading) {
      A.loadCss(V + 'maplibre/maplibre-gl.css');
      loading = Promise.all([import(abs(V + 'maplibre/maplibre-gl.mjs')), A.loadScript(V + 'pmtiles.js'), A.loadScript(V + 'basemaps.js')]).then(function (r) {
        var ml = r[0], protocol = new window.pmtiles.Protocol();
        ml.addProtocol('pmtiles', protocol.tile);
        // تشكيل الحروف العربية واتجاه الأسماء من اليمين (يُحمّل عند أول اسم عربي)
        ml.setRTLTextPlugin(abs(V + 'mapbox-gl-rtl-text.js'), true).catch(function () { /* الأسماء العربية تظهر مفككة فقط */ });
        return { ml: ml, protocol: protocol };
      });
      loading.catch(function () { loading = null; }); // يُعاد المحاولة عند فتح الصفحة مرة أخرى
    }
    return loading;
  }

  /* نمط الخريطة: الملف المحلي إن وُجد، وإلا البلاطات الاحتياطية */
  function baseStyle(lib) {
    var url = abs(BT.config.mapPmtiles || 'maps/kuwait.pmtiles'), file = new window.pmtiles.PMTiles(url);
    lib.protocol.add(file);
    return file.getHeader().then(function () {
      return {
        style: {
          version: 8,
          glyphs: abs(V + 'fonts/') + '{fontstack}/{range}.pbf', // الرموز بعد URL(): وإلا حوّل الأقواس إلى %7B
          sprite: abs(V + 'sprites/light'),
          sources: { protomaps: { type: 'vector', url: 'pmtiles://' + url, attribution: ATTRIBUTION } },
          layers: window.basemaps.layers('protomaps', window.basemaps.namedFlavor('light'), { lang: 'ar' })
        }
      };
    }, function (err) {
      if (!BT.config.mapFallbackTiles) throw err;
      if (window.console) console.warn('map file missing, using the fallback tiles:', url, err);
      return {
        fallback: true,
        style: {
          version: 8,
          glyphs: abs(V + 'fonts/') + '{fontstack}/{range}.pbf', // عدد السيارات في المجموعات
          sources: { raster: { type: 'raster', tiles: [BT.config.mapFallbackTiles], tileSize: 256, maxzoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>' } },
          layers: [{ id: 'raster', type: 'raster', source: 'raster' }]
        }
      };
    });
  }

  /* لماذا الخريطة احتياطية: ما كتبته خدمة الخرائط في status.json بجانب الملف (تنزيل جارٍ، فشل وسببه، موعد المحاولة التالية) */
  function fallbackNote(el) {
    var note = document.createElement('div');
    note.className = 'map-note';
    note.setAttribute('role', 'status');
    note.setAttribute('data-map-fallback', '');
    note.textContent = 'خريطة احتياطية: ملف خريطة الكويت غير موجود على الخادم';
    el.appendChild(note);
    var url = abs(BT.config.mapPmtiles || 'maps/kuwait.pmtiles').replace(/[^/]*$/, 'status.json');
    fetch(url, { cache: 'no-store', credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (st) {
      var fmt = BT.fmt;
      if (!st || !st.state) {
        note.textContent = 'خريطة احتياطية: ملف خريطة الكويت غير موجود، وخدمة الخرائط (maps) لا تعمل على الخادم';
      } else if (st.state === 'updating') {
        note.textContent = 'خريطة احتياطية: يجري الآن تنزيل خريطة الكويت على الخادم (دقائق)، ثم تظهر عند فتح الصفحة مرة أخرى';
      } else if (st.state === 'failed') {
        note.textContent = 'خريطة احتياطية: تعذّر تنزيل خريطة الكويت (آخر محاولة ' + fmt.dt(st.checked_at) + ')، والمحاولة التالية تلقائياً ' + fmt.dt(st.next_try_at);
        if (st.error) note.title = st.error;
      }
      note.setAttribute('data-state', st && st.state || 'none');
    }, function () { /* تبقى الرسالة العامة */ });
  }

  var LOCALE = {
    'NavigationControl.ZoomIn': 'تكبير', 'NavigationControl.ZoomOut': 'تصغير',
    'FullscreenControl.Enter': 'ملء الشاشة', 'FullscreenControl.Exit': 'الخروج من ملء الشاشة',
    'AttributionControl.ToggleAttribution': 'مصدر الخريطة', 'Popup.Close': 'إغلاق', 'Marker.Title': 'علامة'
  };

  /* يفتح خريطة في العنصر. النتيجة null إن غادر المستخدم الصفحة قبل اكتمال التحميل.
     opts.fullscreen: العنصر الذي يملأ الشاشة (الخريطة نفسها افتراضياً) */
  BT.map = function (el, opts) {
    opts = opts || {};
    return libs().then(function (lib) {
      return baseStyle(lib).then(function (base) {
        if (!document.contains(el)) return null;
        var ml = lib.ml;
        var map = new ml.Map({
          container: el, style: base.style, center: lngLat(BT.config.mapCenter), zoom: BT.config.mapZoom, maxZoom: 18,
          attributionControl: { compact: true }, fadeDuration: 0, dragRotate: false, pitchWithRotate: false, touchPitch: false, locale: LOCALE
        });
        map.touchZoomRotate.disableRotation();
        map.keyboard.disableRotation();
        map.addControl(new ml.NavigationControl({ showCompass: false }), 'top-left');
        map.addControl(new ml.FullscreenControl({ container: opts.fullscreen || el }), 'top-left');
        if (base.fallback) fallbackNote(el);
        A.onLeave(function () { map.remove(); });
        return wrap(ml, map);
      });
    });
  };

  function wrap(ml, map) {
    var loaded = new Promise(function (ok) { if (map.loaded()) ok(); else map.once('load', ok); });
    return {
      raw: map,
      /* علامة HTML: html من قوالبنا (BT.h)، والنافذة المنبثقة تُنشأ مرة وتُحدَّث محتوياتها (تبقى مفتوحة مع البث الحي) */
      marker: function (pos, html, opts) {
        opts = opts || {};
        var el = document.createElement('div'), popup = null, last = html;
        el.innerHTML = html;
        if (opts.title) el.title = opts.title;
        // بعد انتهاء النقرة: لو أعاد onClick رسم العلامة أثناءها لما فتحت الخريطة النافذة المنبثقة
        if (opts.onClick) el.addEventListener('click', function () { setTimeout(opts.onClick, 0); });
        var mk = new ml.Marker({ element: el, anchor: 'center' }).setLngLat(lngLat(pos)).addTo(map), anim = 0;
        return {
          el: el,
          /* ms: انزلاق من الموضع الحالي للجديد بدل القفز (البث المباشر)؛ قفزة كبيرة (أكثر من 3 كم) تُنقل فوراً */
          move: function (p, ms) {
            cancelAnimationFrame(anim);
            var to = lngLat(p), from = mk.getLngLat();
            if (!ms || from.distanceTo(new ml.LngLat(to[0], to[1])) > 3000 || document.hidden) { mk.setLngLat(to); return; }
            var t0 = performance.now();
            (function step(now) {
              var k = Math.min(1, (now - t0) / ms), e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
              mk.setLngLat([from.lng + (to[0] - from.lng) * e, from.lat + (to[1] - from.lat) * e]);
              if (k < 1) anim = requestAnimationFrame(step);
            })(t0);
          },
          html: function (x) { if (x !== last) el.innerHTML = last = x; },
          title: function (x) { el.title = x; },
          /* مخفية: داخل مجموعة، أو خارج التصفية */
          show: function (on) { el.style.display = on ? '' : 'none'; if (!on && popup && popup.isOpen()) popup.remove(); },
          /* x: the HTML, or a function that builds it, called only when the popup opens (and on updates while it is
             open): hundreds of live markers do not rebuild hundreds of closed popups on every position */
          popup: function (x) {
            var build = typeof x === 'function' ? x : function () { return x; };
            if (!popup) {
              mk.setPopup(popup = new ml.Popup({ offset: 18, maxWidth: '300px' }));
              popup.on('open', function () { popup.setHTML(popup._build()); });
            }
            popup._build = build;
            if (popup.isOpen()) popup.setHTML(build());
          },
          open: function () { if (popup && !popup.isOpen()) mk.togglePopup(); },
          pos: function () { var c = mk.getLngLat(); return [c.lat, c.lng]; },
          remove: function () { mk.remove(); }
        };
      },
      /* كل السيارات طبقة واحدة ترسمها بطاقة الرسوميات (WebGL)، والخريطة نفسها تجمع المتقاربة: لا عنصر HTML لكل سيارة
         ولا حركة لكل واحدة. مئات العلامات HTML فوق الخريطة كانت تأخذ نواة معالج كاملة وذاكرة تزيد، فيتوقف المتصفح.
         set(list): [{id, pos:[lat,lng], tone, stale, heading}] كلها؛ يُرسم مرة كل ثانيتين على الأكثر (كل رسم يعيد
         رسم الخريطة كلها، ومواقع السيارات تصل كل 30 ثانية)، وبلا تلاشٍ للرموز (fadeDuration: 0) فلا يستمر الرسم بعد كل تحديث.
         opts.onClick(id) عند الضغط على سيارة؛ popup(id) يفتح نافذتها (opts.popup(id) يبنيها) */
      cars: function (opts) {
        var byId = {}, selected = null, pending = null, popup = null, popupId = null, ready = false;
        function feature(c) {
          return { type: 'Feature', geometry: { type: 'Point', coordinates: lngLat(c.pos) },
            properties: { id: c.id, tone: c.tone, stale: c.stale ? 1 : 0, heading: c.heading == null || c.stale ? -1 : Math.round(c.heading), sel: c.id === selected ? 1 : 0, lost: c.tone === 'g' ? 0 : 1 } };
        }
        function data() { return { type: 'FeatureCollection', features: Object.keys(byId).map(function (id) { return feature(byId[id]); }) }; }
        function flush() {
          pending = null;
          var src = ready && map.getStyle() && map.getSource('cars');
          if (!src) return; // not drawn yet, or the page was left
          src.setData(data());
          if (popup && popupId && byId[popupId]) { popup.setLngLat(lngLat(byId[popupId].pos)); popup.setHTML(opts.popup(popupId)); }
        }
        function later() { if (!pending) pending = setTimeout(flush, 2000); }
        loaded.then(function () {
          return Promise.all(['g', 'o', 'r', 'n'].map(function (t) { return carImage(map, t); }).concat([arrowImage(map)]));
        }).then(function () {
          if (!map.getStyle()) return; // left the page
          map.addSource('cars', { type: 'geojson', data: data(), cluster: true, clusterRadius: 48, clusterMaxZoom: 14, clusterProperties: { lost: ['+', ['get', 'lost']] } });
          var single = ['!', ['has', 'point_count']], many = ['has', 'point_count'];
          map.addLayer({ id: 'cars-cluster', type: 'circle', source: 'cars', filter: many, paint: { 'circle-color': '#1D4ED8', 'circle-radius': ['step', ['get', 'point_count'], 17, 10, 20, 50, 24, 200, 28], 'circle-stroke-width': 3, 'circle-stroke-color': '#ffffff' } });
          map.addLayer({ id: 'cars-cluster-n', type: 'symbol', source: 'cars', filter: many, layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Noto Sans Medium'], 'text-size': 13, 'text-allow-overlap': true }, paint: { 'text-color': '#ffffff' } });
          map.addLayer({ id: 'cars-cluster-lost', type: 'circle', source: 'cars', filter: ['all', many, ['>', ['get', 'lost'], 0]], paint: { 'circle-color': '#B91C1C', 'circle-radius': 9, 'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff', 'circle-translate': [15, -15] } });
          map.addLayer({ id: 'cars-cluster-lost-n', type: 'symbol', source: 'cars', filter: ['all', many, ['>', ['get', 'lost'], 0]], layout: { 'text-field': ['to-string', ['get', 'lost']], 'text-font': ['Noto Sans Medium'], 'text-size': 10, 'text-allow-overlap': true, 'text-offset': [1.5, -1.5] }, paint: { 'text-color': '#ffffff' } });
          map.addLayer({ id: 'cars-sel', type: 'circle', source: 'cars', filter: ['all', single, ['==', ['get', 'sel'], 1]], paint: { 'circle-radius': 22, 'circle-color': 'rgba(10,108,255,.18)', 'circle-stroke-width': 3, 'circle-stroke-color': '#0A6CFF' } });
          map.addLayer({ id: 'cars-dir', type: 'symbol', source: 'cars', filter: ['all', single, ['>=', ['get', 'heading'], 0]], layout: { 'icon-image': 'veh-arrow', 'icon-rotate': ['get', 'heading'], 'icon-rotation-alignment': 'map', 'icon-allow-overlap': true, 'icon-ignore-placement': true } });
          map.addLayer({ id: 'cars', type: 'symbol', source: 'cars', filter: single, layout: { 'icon-image': ['concat', 'veh-', ['get', 'tone']], 'icon-allow-overlap': true, 'icon-ignore-placement': true, 'symbol-sort-key': ['get', 'sel'] }, paint: { 'icon-opacity': ['case', ['==', ['get', 'stale'], 1], 0.6, 1] } });
          map.on('click', 'cars', function (e) { var id = e.features[0].properties.id; setTimeout(function () { opts.onClick(id); }, 0); });
          map.on('click', 'cars-cluster', function (e) {
            var f = e.features[0];
            map.getSource('cars').getClusterExpansionZoom(f.properties.cluster_id).then(function (z) { map.easeTo({ center: f.geometry.coordinates, zoom: Math.min(z, 16) }); });
          });
          ['cars', 'cars-cluster'].forEach(function (l) {
            map.on('mouseenter', l, function () { map.getCanvas().style.cursor = 'pointer'; });
            map.on('mouseleave', l, function () { map.getCanvas().style.cursor = ''; });
          });
          ready = true;
          map.once('remove', function () { ready = false; clearTimeout(pending); pending = null; });
          flush();
        });
        return {
          set: function (list) { byId = {}; list.forEach(function (c) { byId[c.id] = c; }); later(); },
          put: function (c) { if (c.pos) byId[c.id] = c; else delete byId[c.id]; later(); },
          select: function (id) { selected = id; later(); },
          pos: function (id) { return byId[id] ? byId[id].pos : null; },
          has: function (id) { return !!byId[id]; },
          count: function () { return Object.keys(byId).length; },
          /* where a car is on the page, in pixels (the tests click it there) */
          point: function (id) { var c = byId[id]; if (!c) return null; var p = map.project(lngLat(c.pos)), r = map.getCanvas().getBoundingClientRect(); return { x: r.left + p.x, y: r.top + p.y }; },
          popup: function (id) {
            if (!byId[id]) return;
            if (!popup) { popup = new ml.Popup({ offset: 18, maxWidth: '300px' }); popup.on('close', function () { popupId = null; }); }
            popupId = id;
            popup.setLngLat(lngLat(byId[id].pos)).setHTML(opts.popup(id)).addTo(map);
          }
        };
      },
      fit: function (points, maxZoom) {
        if (!points.length) return;
        var b = new ml.LngLatBounds(lngLat(points[0]), lngLat(points[0]));
        points.forEach(function (p) { b.extend(lngLat(p)); });
        map.fitBounds(b, { padding: 40, maxZoom: maxZoom || 15, duration: 0 });
      },
      fitBounds: function (points, maxZoom) {
        if (!points.length) return;
        var b = new ml.LngLatBounds(lngLat(points[0]), lngLat(points[0]));
        points.forEach(function (p) { b.extend(lngLat(p)); });
        map.fitBounds(b, { padding: 60, maxZoom: maxZoom || 15 });
      },
      view: function (p, zoom, ms) { map.easeTo({ center: lngLat(p), zoom: zoom, duration: ms == null ? 800 : ms, easing: function (t) { return t * (2 - t); } }); },
      fly: function (p, zoom) { map.flyTo({ center: lngLat(p), zoom: zoom, speed: 1.4, curve: 1.3, essential: true }); },
      zoom: function () { return map.getZoom(); },
      /* موضع النقطة على الشاشة بالبكسل (لتجميع العلامات المتقاربة) */
      project: function (p) { return map.project(lngLat(p)); },
      on: function (ev, fn) { map.on(ev, fn); },
      resize: function () { map.resize(); },
      /* أداة فوق الخريطة (أزرار الصفحة) */
      control: function (node, where) { map.addControl({ onAdd: function () { return node; }, onRemove: function () { node.remove(); } }, where || 'top-right'); },
      /* خط المسار (يحلّ محل السابق). off[i]: النقطة خارج يوم العمل (FR-TRK-09)؛ ما بين نقطتين خارجه يُرسم برتقالياً.
         breaks[i]: انقطاع قبل النقطة i (فجوة GPS أو نقاط مخفية): يُرسم متقطعاً رمادياً لأنه ليس طريق السيارة */
      line: function (points, off, breaks) {
        return loaded.then(function () {
          var features = [];
          for (var i = 1; i < points.length; i++) {
            var kind = breaks && breaks[i] ? 'gap' : off && off[i - 1] && off[i] ? 'off' : 'on', last = features[features.length - 1];
            if (last && last.properties.kind === kind && kind !== 'gap') last.geometry.coordinates.push(lngLat(points[i]));
            else features.push({ type: 'Feature', properties: { kind: kind }, geometry: { type: 'LineString', coordinates: [lngLat(points[i - 1]), lngLat(points[i])] } });
          }
          var data = { type: 'FeatureCollection', features: features };
          if (map.getSource('route')) { map.getSource('route').setData(data); return; }
          map.addSource('route', { type: 'geojson', data: data });
          var layout = { 'line-join': 'round', 'line-cap': 'round' }, driven = ['!=', ['get', 'kind'], 'gap'];
          map.addLayer({ id: 'route-casing', type: 'line', source: 'route', filter: driven, layout: layout, paint: { 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.9 } });
          map.addLayer({ id: 'route', type: 'line', source: 'route', filter: driven, layout: layout, paint: { 'line-color': ['case', ['==', ['get', 'kind'], 'off'], '#F59E0B', '#0A6CFF'], 'line-width': 4, 'line-opacity': 0.9 } });
          map.addLayer({ id: 'route-gap', type: 'line', source: 'route', filter: ['==', ['get', 'kind'], 'gap'], paint: { 'line-color': '#64748B', 'line-width': 3, 'line-dasharray': [1.5, 2], 'line-opacity': 0.9 } });
        });
      }
    };
  }

  /* صور علامات السيارات للطبقة: دائرة بلون الحالة وإطار أبيض وسيارة، وسهم الاتجاه */
  var TONE = { g: '#1F9D45', o: '#E08A00', r: '#E5352B', n: '#5F6879' };
  var CAR = '<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/>';
  function addSvg(map, name, svg, size) {
    return new Promise(function (ok) {
      if (map.hasImage(name)) { ok(); return; }
      var img = new Image(size * 2, size * 2);
      img.onload = function () { if (map.getStyle() && !map.hasImage(name)) map.addImage(name, img, { pixelRatio: 2 }); ok(); };
      img.onerror = function () { ok(); };
      img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    });
  }
  function carImage(map, tone) {
    return addSvg(map, 'veh-' + tone, '<svg xmlns="http://www.w3.org/2000/svg" width="68" height="68" viewBox="0 0 34 34"><circle cx="17" cy="17" r="14" fill="' + TONE[tone] + '" stroke="#fff" stroke-width="2.5"/><g transform="translate(9.5 9.5) scale(.62)" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' + CAR + '</g></svg>', 34);
  }
  function arrowImage(map) { // the arrow on the circle's edge, pointing up: rotated with the heading
    return addSvg(map, 'veh-arrow', '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 48 48"><path d="M24 2 L30 11 L18 11 Z" fill="#0A6CFF" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>', 48);
  }

  /* stale: موقع قديم (آخر موقع معروف، لا الموقع الحالي) يُرسم باهتاً بإطار متقطع */
  /* heading: اتجاه الحركة بالدرجات (سهم حول العلامة)، يظهر فقط والسيارة ماشية */
  BT.map.carHtml = function (tone, selected, stale, heading) {
    var arrow = heading != null && !stale ? h`<span class="veh-dir" style="transform:rotate(${Math.round(heading)}deg)"></span>` : '';
    return String(h`<div class="veh-mark ${tone}${selected ? ' sel' : ''}${stale ? ' stale' : ''}">${arrow}${BT.icon('car', 15)}</div>`);
  };
})();
