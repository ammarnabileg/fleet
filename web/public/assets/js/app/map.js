/* =====================================================================
   app/map.js — الخريطة (MapLibre GL، تُحمّل عند فتح صفحة فيها خريطة)
   الخريطة الأساسية من خادمنا: ملف واحد للكويت (Protomaps PMTiles من بيانات OpenStreetMap) في BT.config.mapPmtiles،
   يقرأ المتصفح منه ما يلزم فقط بطلبات HTTP Range. لا رسوم ولا حدود استخدام، ولا يرى طرف ثالث مواقع السيارات
   ولا ما يشاهده المشرف. إن لم يوجد الملف على الخادم: بلاطات BT.config.mapFallbackTiles مع ملاحظة ظاهرة على الخريطة.
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
          sources: { raster: { type: 'raster', tiles: [BT.config.mapFallbackTiles], tileSize: 256, maxzoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>' } },
          layers: [{ id: 'raster', type: 'raster', source: 'raster' }]
        }
      };
    });
  }

  /* يفتح خريطة في العنصر. النتيجة null إن غادر المستخدم الصفحة قبل اكتمال التحميل. */
  BT.map = function (el) {
    return libs().then(function (lib) {
      return baseStyle(lib).then(function (base) {
        if (!document.contains(el)) return null;
        var ml = lib.ml;
        var map = new ml.Map({
          container: el, style: base.style, center: lngLat(BT.config.mapCenter), zoom: BT.config.mapZoom, maxZoom: 18,
          attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false, touchPitch: false
        });
        map.touchZoomRotate.disableRotation();
        map.keyboard.disableRotation();
        map.addControl(new ml.NavigationControl({ showCompass: false }), 'top-left');
        if (base.fallback) {
          var note = document.createElement('div');
          note.className = 'map-note';
          note.textContent = 'خريطة احتياطية: ملف الخريطة غير موجود على الخادم';
          el.appendChild(note);
        }
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
        var mk = new ml.Marker({ element: el, anchor: 'center' }).setLngLat(lngLat(pos)).addTo(map);
        return {
          move: function (p) { mk.setLngLat(lngLat(p)); },
          html: function (x) { if (x !== last) el.innerHTML = last = x; },
          popup: function (x) {
            if (popup) popup.setHTML(x);
            else mk.setPopup(popup = new ml.Popup({ offset: 18, maxWidth: '300px' }).setHTML(x));
          },
          open: function () { if (popup && !popup.isOpen()) mk.togglePopup(); },
          pos: function () { var c = mk.getLngLat(); return [c.lat, c.lng]; },
          remove: function () { mk.remove(); }
        };
      },
      fit: function (points, maxZoom) {
        if (!points.length) return;
        var b = new ml.LngLatBounds(lngLat(points[0]), lngLat(points[0]));
        points.forEach(function (p) { b.extend(lngLat(p)); });
        map.fitBounds(b, { padding: 40, maxZoom: maxZoom || 15, duration: 0 });
      },
      view: function (p, zoom) { map.easeTo({ center: lngLat(p), zoom: zoom }); },
      zoom: function () { return map.getZoom(); },
      /* خط المسار (يحلّ محل السابق) */
      line: function (points) {
        return loaded.then(function () {
          var data = { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: points.map(lngLat) } };
          if (map.getSource('route')) { map.getSource('route').setData(data); return; }
          map.addSource('route', { type: 'geojson', data: data });
          var layout = { 'line-join': 'round', 'line-cap': 'round' };
          map.addLayer({ id: 'route-casing', type: 'line', source: 'route', layout: layout, paint: { 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.9 } });
          map.addLayer({ id: 'route', type: 'line', source: 'route', layout: layout, paint: { 'line-color': '#0A6CFF', 'line-width': 4, 'line-opacity': 0.9 } });
        });
      }
    };
  }

  BT.map.carHtml = function (tone, selected) {
    return String(h`<div class="veh-mark ${tone}${selected ? ' sel' : ''}">${BT.icon('car', 15)}</div>`);
  };
})();
