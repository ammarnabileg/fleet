/* =====================================================================
   BrilliantTech UI — charts.js
   BT.chart.bars  : أعمدة لسلسلة واحدة (محور واحد، tooltip عند المرور/التركيز)
   BT.chart.hbars : أشرطة أفقية مع القيمة عند الطرف
   BT.chart.table : نفس البيانات كجدول (بديل مقروء للرسم)
   BT.kuwaitMap   : خريطة توضيحية (SVG) مع دبابيس ومسار
   ملاحظة: الخريطة رسم توضيحي فقط. في النظام الفعلي استبدلها بـ Google Maps أو Mapbox.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw;

  function niceMax(v) {
    if (v <= 0) return 1;
    var p = Math.pow(10, Math.floor(Math.log10(v)));
    var steps = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
    for (var i = 0; i < steps.length; i++) if (steps[i] * p >= v) return steps[i] * p;
    return 10 * p;
  }

  BT.chart = {};

  /* BT.chart.bars(el, {labels, sublabels, values, format(v), unitLabel, height, name})
     الأحدث على اليسار (اتجاه القراءة العربي: الزمن يتقدم من اليمين لليسار). */
  BT.chart.bars = function (el, o) {
    var fmt = o.format || BT.fmt.int;
    var H = o.height || 210, axisW = 52, padTop = 22, xBand = 34;
    el.classList.add('chart');
    function draw() {
      var W = Math.max(260, el.clientWidth);
      var plotW = W - axisW, plotH = H - padTop - xBand;
      var max = niceMax(Math.max.apply(null, o.values) * (o.headroom || 1.08));
      var n = o.values.length, band = plotW / n, bw = Math.min(24, band * .56);
      var y = function (v) { return padTop + plotH - (v / max) * plotH; };
      var svg = '';
      for (var t = 0; t <= 4; t++) {
        var v = max * t / 4, yy = Math.round(y(v)) + .5;
        svg += '<line class="grid-l" x1="0" x2="' + plotW + '" y1="' + yy + '" y2="' + yy + '"/>';
        svg += '<text class="axis-t" x="' + (W - 4) + '" y="' + (yy + 4) + '" text-anchor="end" direction="ltr">' + BT.esc(o.tickFormat ? o.tickFormat(v) : BT.fmt.int(v)) + '</text>';
      }
      var last = n - 1;
      o.values.forEach(function (val, i) {
        var cx = plotW - band * (i + .5); // i=0 (الأقدم) على اليمين
        var top = y(val), x = cx - bw / 2, base = padTop + plotH, r = Math.min(4, (base - top) / 2);
        var path = 'M' + x + ',' + base + ' V' + (top + r) + ' Q' + x + ',' + top + ' ' + (x + r) + ',' + top + ' H' + (x + bw - r) + ' Q' + (x + bw) + ',' + top + ' ' + (x + bw) + ',' + (top + r) + ' V' + base + ' Z';
        var aria = (o.labels[i] + (o.sublabels ? ' ' + o.sublabels[i] : '') + ': ' + fmt(val) + ' ' + (o.unitLabel || ''));
        svg += '<rect class="hit" x="' + (cx - band / 2) + '" y="' + padTop + '" width="' + band + '" height="' + (plotH + xBand) + '" tabindex="0" role="img" aria-label="' + BT.esc(aria) + '" data-i="' + i + '"/>';
        svg += '<path class="bar" d="' + path + '"/>';
        svg += '<text class="axis-t" x="' + cx + '" y="' + (base + 16) + '" text-anchor="middle">' + BT.esc(o.labels[i]) + '</text>';
        if (o.sublabels) svg += '<text class="axis-t" x="' + cx + '" y="' + (base + 29) + '" text-anchor="middle" style="font-size:10px">' + BT.esc(o.sublabels[i]) + '</text>';
        if (i === last) svg += '<text class="val-t" x="' + cx + '" y="' + (top - 7) + '" text-anchor="middle" direction="ltr">' + BT.esc(fmt(val)) + '</text>';
      });
      el.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" height="' + H + '" role="group" aria-label="' + BT.esc(o.name || '') + '">' + svg + '</svg><div class="chart-tip" role="tooltip"></div>';
      var tip = el.querySelector('.chart-tip');
      var show = function (rect) {
        var i = +rect.getAttribute('data-i');
        tip.innerHTML = String(h`<b>${fmt(o.values[i])}</b><span><i></i>${o.unitLabel || ''} · ${o.labels[i]}${o.sublabels ? ' ' + o.sublabels[i] : ''}</span>`);
        var cx = plotW - band * (i + .5), top = y(o.values[i]);
        var scale = el.clientWidth / W;
        tip.style.left = (cx * scale) + 'px'; tip.style.top = (top * scale) + 'px';
        tip.classList.add('show');
      };
      BT.$$('.hit', el).forEach(function (r) {
        r.addEventListener('pointerenter', function () { show(r); });
        r.addEventListener('focus', function () { show(r); });
        r.addEventListener('pointerleave', function () { tip.classList.remove('show'); });
        r.addEventListener('blur', function () { tip.classList.remove('show'); });
      });
    }
    draw();
    // one size watcher per element: the chart drawn before this one (another tab's numbers) stops redrawing itself
    if (el._chartSize) el._chartSize.disconnect();
    if (window.ResizeObserver) {
      var ro = el._chartSize = new ResizeObserver(BT.debounce(function () { if (el._chartSize !== ro) return; if (document.contains(el)) draw(); else ro.disconnect(); }, 120));
      ro.observe(el);
    }
    return { redraw: draw };
  };

  /* BT.chart.hbars({rows:[{label, value}], max, format, unit}) → HTML */
  BT.chart.hbars = function (o) {
    var fmt = o.format || function (v) { return String(v); };
    var max = o.max || niceMax(Math.max.apply(null, o.rows.map(function (r) { return r.value; })));
    return h`<div class="hbars">${o.rows.map(function (r) {
      return h`<div class="hbar" data-tip="${r.label}: ${fmt(r.value)} ${o.unit || ''}" tabindex="0"><span class="truncate">${r.label}</span><div class="track"><div class="fill" style="width:${(r.value / max * 100).toFixed(1)}%"></div></div><span class="v">${fmt(r.value)}${o.unit ? raw(' <small class="muted">' + BT.esc(o.unit) + '</small>') : ''}</span></div>`;
    })}</div>`;
  };

  /* BT.chart.table(headers, rows) — عرض جدولي لنفس بيانات الرسم */
  BT.chart.table = function (headers, rows) {
    return h`<div class="table-wrap"><table class="t compact"><thead><tr>${headers.map(function (x, i) { return h`<th class="${i ? 'num' : ''}">${x}</th>`; })}</tr></thead><tbody>${rows.map(function (r) { return h`<tr>${r.map(function (c, i) { return h`<td class="${i ? 'num' : ''}">${c}</td>`; })}</tr>`; })}</tbody></table></div>`;
  };

  /* =================================================================
     Kuwait map (illustrative) — BT.kuwaitMap({pins, route, zone, height})
     pins : [{id, x, y, label, tone:'g'|'o'|'r'|'p'|'b'}]  (إحداثيات نظام الخريطة)
     route: [[x,y], ...]  مسار السيارة
     ================================================================= */
  var VX = -100, VW = 520, VH = 440;
  BT.mapPos = function (x, y) { return { left: ((x - VX) / VW * 100).toFixed(2) + '%', top: (y / VH * 100).toFixed(2) + '%' }; };
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-map-zoom]');
    if (!b) return;
    var inner = b.closest('.map').querySelector('.map-inner');
    var z = +(inner.dataset.z || 1), m = b.getAttribute('data-map-zoom');
    z = m === 'in' ? Math.min(2.5, z + .5) : m === 'out' ? Math.max(1, z - .5) : 1;
    inner.dataset.z = z; inner.style.transform = 'scale(' + z + ')';
  });
  BT.kuwaitMap = function (o) {
    o = o || {};
    var coast = 'M-70,0 C-60,30 -34,62 0,70 C40,74 70,92 110,104 C150,114 200,108 240,112 C275,116 300,124 312,142 C322,160 314,200 318,240 C322,280 312,330 318,380 C321,410 316,430 312,440 H430 V0 Z';
    var landClip = 'M-100,0 L-70,0 C-60,30 -34,62 0,70 C40,74 70,92 110,104 C150,114 200,108 240,112 C275,116 300,124 312,142 C322,160 314,200 318,240 C322,280 312,330 318,380 C321,410 316,430 312,440 L-100,440 Z';
    var cid = BT.uid('land');
    var s = '<svg class="map-bg" viewBox="' + VX + ' 0 ' + VW + ' ' + VH + '" preserveAspectRatio="xMidYMid meet" aria-hidden="true">';
    s += '<rect x="' + VX + '" y="0" width="' + VW + '" height="' + VH + '" style="fill:var(--map-land)"/>';
    s += '<defs><clipPath id="' + cid + '"><path d="' + landClip + '"/></clipPath></defs>';
    s += '<path d="' + coast + '" style="fill:var(--map-water)"/>';
    s += '<g clip-path="url(#' + cid + ')" fill="none" style="stroke:var(--map-ring)" stroke-width="7">' + [55, 95, 135, 175, 215, 255].map(function (r) { return '<circle cx="300" cy="118" r="' + r + '"/>'; }).join('') + '</g>';
    s += '<g fill="none" style="stroke:var(--map-road)" stroke-width="3" clip-path="url(#' + cid + ')"><path d="M300,118 L270,440"/><path d="M300,118 L-40,380"/><path d="M-100,60 L300,150"/><path d="M310,150 C300,260 300,330 300,440"/><path d="M-100,250 L200,230"/></g>';
    if (o.zone !== false) s += '<path d="M150,150 C200,135 280,140 300,170 C312,230 300,330 290,405 C230,420 170,395 150,330 C135,270 130,190 150,150 Z" fill="rgba(10,132,255,.06)" stroke="#0A84FF" stroke-width="1.6" stroke-dasharray="6 5"/>';
    [[70, 136, 'الجهراء'], [262, 136, 'العاصمة'], [292, 196, 'حولي'], [196, 205, 'الفروانية'], [284, 272, 'مبارك الكبير'], [286, 360, 'المهبولة'], [222, 430, 'الأحمدي'], [-40, 300, 'الصليبية']].forEach(function (l) {
      s += '<text x="' + l[0] + '" y="' + l[1] + '" font-size="10.5" text-anchor="middle" style="fill:var(--map-label);font-family:var(--font)">' + l[2] + '</text>';
    });
    s += '<text x="170" y="42" font-size="11" text-anchor="middle" style="fill:var(--map-water-label);font-family:var(--font)">جون الكويت</text>';
    s += '<text x="372" y="260" font-size="11" text-anchor="middle" style="fill:var(--map-water-label);font-family:var(--font)" transform="rotate(90 372 260)">الخليج العربي</text>';
    if (o.zone !== false) s += '<text x="150" y="385" font-size="10.5" style="fill:#0A6CFF;font-family:var(--font)">منطقة التشغيل</text>';
    if (o.route && o.route.length) {
      s += '<polyline points="' + o.route.map(function (p) { return p[0] + ',' + p[1]; }).join(' ') + '" fill="none" stroke="#0A84FF" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>';
      (o.stops || []).forEach(function (p) { s += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="4.5" fill="#FF9F0A" stroke="#fff" stroke-width="2"/>'; });
      var a = o.route[0], b = o.route[o.route.length - 1];
      s += '<circle cx="' + a[0] + '" cy="' + a[1] + '" r="6" fill="#28A745" stroke="#fff" stroke-width="2"/><circle cx="' + b[0] + '" cy="' + b[1] + '" r="6" fill="#FF3B30" stroke="#fff" stroke-width="2"/>';
    }
    s += '</svg>';
    var pins = (o.pins || []).map(function (p) {
      var pos = BT.mapPos(p.x, p.y);
      return h`<button type="button" class="pin" data-pin="${p.id}" style="left:${pos.left};top:${pos.top}" aria-label="${p.aria || p.label}"><span class="sdot ${p.tone || 'g'}"></span>${p.label}</button>`;
    });
    return h`<div class="map" style="aspect-ratio:${VW}/${VH}"><div class="map-inner">${raw(s)}${pins}</div>${o.tools !== false ? h`<div class="map-tools"><button type="button" data-tip="تكبير" data-map-zoom="in" aria-label="تكبير">${BT.icon('plus', 16)}</button><button type="button" data-tip="تصغير" data-map-zoom="out" aria-label="تصغير">${BT.icon('minus', 16)}</button><button type="button" data-tip="ملء الشاشة" data-map-zoom="fit" aria-label="ملء الشاشة">${BT.icon('maximize', 15)}</button></div>` : ''}<div class="map-note">خريطة توضيحية</div></div>`;
  };
})();
