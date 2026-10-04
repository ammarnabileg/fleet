/* =====================================================================
   BrilliantTech — mnt.js  (الصيانة: ما تشترك فيه لوحة الإدارة وبوابة المراكز)
   تسميات الحالات، محرر البنود، الجدول الزمني، المدد، الصور، تفاصيل الطلب.
   الصفحة تمرّر fileUrl(sha) لأن رابط الملف يختلف: /maintenance/... للإدارة
   و /portal/... للمركز (كلٌّ يتحقق من صلاحيته ونطاقه).
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api;
  var M = BT.mnt = {};

  M.FLOW = ['referred', 'received', 'inspection', 'quote_pending', 'in_repair', 'waiting_parts', 'completed', 'ready', 'picked_up'];
  M.AT_CENTER = ['referred', 'received', 'inspection', 'quote_pending', 'in_repair', 'waiting_parts', 'completed', 'ready'];
  M.TONE = {
    requested: 'o', approved: 'b', rejected: 'r', referred: 'b', received: 'p', inspection: 'p', quote_pending: 'o',
    in_repair: 'p', waiting_parts: 'o', completed: 'g', ready: 'g', picked_up: 'n', closed: 'n', cancelled: 'n'
  };
  M.KINDS = ['periodic', 'mechanical', 'electrical', 'tyres', 'battery', 'ac', 'bodywork', 'other'];
  M.ITEM_KINDS = { part: 'قطعة', labour: 'أجور', other: 'أخرى' };
  M.INV_TONE = { pending: 'o', approved: 'g', rejected: 'r' };
  M.INV_STATUS = { pending: 'بانتظار الاعتماد', approved: 'معتمدة', rejected: 'مرفوضة' };
  M.FLAG = { duplicate_number: 'رقم مكرر لنفس المركز', differs_from_quote: 'تختلف عن العرض المعتمد' };

  M.NOTES = { ':emergency': 'صيانة طارئة: معتمدة فوراً وتُراجع لاحقاً', ':emergency_reviewed': 'روجعت الصيانة الطارئة', ':quote_approved': 'اعتُمد عرض السعر', ':quote_within_limit': 'عرض السعر ضمن حد الاعتماد: معتمد تلقائياً' };
  M.note = function (n) { return n && n.charAt(0) === ':' ? (M.NOTES[n] || n.slice(1)) : n; };
  M.status = function (s) { return BT.pill(api.t('maintenance_status', s), M.TONE[s] || 'n'); };
  M.kind = function (k) { return api.t('maintenance_kind', k); };
  M.kindOptions = function () { return M.KINDS.map(function (k) { return { v: k, t: M.kind(k) }; }); };
  M.dur = function (sec) {
    if (sec == null) return '—';
    var d = Math.floor(sec / 86400), hr = Math.floor(sec % 86400 / 3600), mi = Math.floor(sec % 3600 / 60);
    if (d) return d + ' يوم' + (hr ? ' و' + hr + ' س' : '');
    if (hr) return hr + ' س' + (mi ? ' و' + mi + ' د' : '');
    return Math.max(mi, 0) + ' د';
  };
  M.vehicle = function (v) {
    v = v || {};
    var desc = [v.make, v.model, v.year].filter(Boolean).join(' ');
    return h`<span class="plate">${v.plate_number || '—'}</span>${desc ? h`<span class="sub ltr">${desc}</span>` : ''}`;
  };
  M.vehicleLine = function (v) {
    v = v || {};
    var desc = [v.make, v.model, v.year].filter(Boolean).join(' ');
    return h`<span class="plate">${v.plate_number || '—'}</span>${desc ? h` <small class="muted ltr" style="font-size:.6em;font-weight:500">${desc}</small>` : ''}`;
  };
  M.invStatus = function (i) {
    return h`${BT.pill(M.INV_STATUS[i.status], M.INV_TONE[i.status])} ${i.payment_status === 'paid' ? BT.pill('مدفوعة', 'g') : i.status === 'approved' ? BT.pill('غير مدفوعة', 'n') : ''}`;
  };
  M.flags = function (flags) { return h`${(flags || []).map(function (f) { return BT.pill(M.FLAG[f] || f, 'o'); })}`; };

  /* ---------- الصور (محمية بالجلسة) وفتحها في العارض ---------- */
  var galleries = {};
  M.thumbs = function (items) { // [{src, caption}]
    if (!items.length) return raw('<div class="muted fs-sm">لا توجد صور</div>');
    var key = BT.uid('mth');
    galleries[key] = items;
    return h`<div class="thumbs">${items.map(function (it, i) { return h`<figure data-mthumbs="${key}" data-i="${i}"><img src="${it.src}" alt="${it.caption || ''}" loading="lazy"><figcaption>${it.caption || ''}</figcaption></figure>`; })}</div>`;
  };
  document.addEventListener('click', function (e) {
    var f = e.target.closest && e.target.closest('[data-mthumbs]');
    if (f) BT.lightbox(galleries[f.getAttribute('data-mthumbs')] || [], +f.getAttribute('data-i'));
  });

  /* ---------- البنود ---------- */
  M.itemsTable = function (items) {
    if (!items || !items.length) return '';
    return h`<div class="table-wrap"><table class="t"><thead><tr><th>البند</th><th>النوع</th><th class="num">الكمية</th><th class="num">السعر</th><th class="num">المبلغ</th></tr></thead><tbody>${items.map(function (it) {
      return h`<tr><td style="white-space:normal">${it.description}</td><td>${M.ITEM_KINDS[it.kind] || it.kind}</td><td class="num">${Number(it.quantity)}</td><td class="num">${fmt.money(it.unit_price)}</td><td class="num">${fmt.money(it.amount)}</td></tr>`;
    })}</tbody></table></div>`;
  };
  M.itemsHtml = h`<div class="label mb-8">البنود</div><div data-items class="col" style="gap:8px"></div>
    <button type="button" class="btn btn-soft btn-sm mt-8" data-items-add>${icon('plus', 14)} إضافة بند</button>
    <div class="highlight-box between mt-12"><b>الإجمالي</b><b><span data-items-total class="num">0.000</span> <small class="muted">د.ك</small></b></div>`;
  function num(v) { var n = Number(String(v || '').replace(/,/g, '')); return isFinite(n) ? n : 0; }
  /* محرر البنود داخل نافذة: يعيد read() بالشكل الذي يقبله الخادم، و total() */
  M.itemsEditor = function (root, onChange) {
    var box = root.querySelector('[data-items]'), totalEl = root.querySelector('[data-items-total]');
    function rows() { return BT.$$('.it-row', box); }
    function read() {
      return rows().map(function (r) {
        return { kind: r.querySelector('[data-k=kind]').value, description: r.querySelector('[data-k=d]').value.trim(), quantity: num(r.querySelector('[data-k=q]').value) || 1, unit_price: num(r.querySelector('[data-k=p]').value) };
      });
    }
    function total() { return BT.round3(BT.sum(read(), function (x) { return x.quantity * x.unit_price; })); }
    function update() { totalEl.textContent = fmt.kwd(total()); if (onChange) onChange(total()); }
    function draw(list) {
      BT.render(box, h`${list.map(function (x, i) {
        return h`<div class="it-row flex gap-8 items-center wrap">
          <select class="select" data-k="kind" style="width:110px" aria-label="النوع">${Object.keys(M.ITEM_KINDS).map(function (k) { return h`<option value="${k}"${k === x.kind ? raw(' selected') : ''}>${M.ITEM_KINDS[k]}</option>`; })}</select>
          <input class="input flex-1" data-k="d" placeholder="الوصف (القطعة أو العمل)" value="${x.description || ''}" aria-label="الوصف" style="min-width:160px">
          <input class="input num-in" data-k="q" inputmode="decimal" value="${x.quantity || 1}" aria-label="الكمية" style="width:70px">
          <div class="input-group" style="width:150px"><input class="input num-in" data-k="p" inputmode="decimal" placeholder="0.000" value="${x.unit_price || ''}" aria-label="سعر الوحدة"><span class="addon">د.ك</span></div>
          <button type="button" class="icon-btn sm" data-del="${i}" aria-label="حذف البند"${list.length < 2 ? raw(' disabled') : ''}>${icon('trash-2', 15)}</button></div>`;
      })}`);
      update();
    }
    root.querySelector('[data-items-add]').onclick = function () { var l = read(); l.push({ kind: 'part' }); draw(l); BT.$$('[data-k=d]', box).pop().focus(); };
    BT.on(box, 'click', '[data-del]', function (e, b) { var l = read(); l.splice(+b.getAttribute('data-del'), 1); draw(l); });
    box.addEventListener('input', update);
    box.addEventListener('change', update);
    draw([{ kind: 'part' }]);
    return {
      read: read,
      total: total,
      valid: function () { var l = read(); return l.length && l.every(function (x) { return x.description && x.unit_price >= 0; }); }
    };
  };

  /* ---------- الجدول الزمني والمدد ---------- */
  M.timeline = function (events) {
    return h`<div class="timeline">${events.map(function (e) {
      var tone = M.TONE[e.status] === 'r' ? 'r' : ['ready', 'completed', 'closed', 'approved'].indexOf(e.status) > -1 ? 'g' : 'b';
      var by = e.by === 'driver' ? 'السائق (من التطبيق)' : e.by;
      return h`<div class="tl-item"><span class="tl-ic ${tone}">${icon('circle-dot', 13)}</span><div><div class="tl-t">${api.t('maintenance_status', e.status)}</div><div class="tl-d">${fmt.dt(e.at)}${by ? ' · ' + by : ''}</div>${e.note ? h`<div class="tl-d" style="white-space:normal">${M.note(e.note)}</div>` : ''}</div></div>`;
    })}</div>`;
  };
  M.durations = function (list) {
    if (!list.length) return raw('<div class="muted fs-sm">تبدأ المدد من استلام المركز للسيارة</div>');
    return BT.kv(list.map(function (d) { return [api.t('maintenance_status', d.status), h`<span class="num">${M.dur(d.seconds)}</span>${d.ended_at ? '' : raw(' <small class="muted">(جارية)</small>')}`]; }));
  };

  /* ---------- مسار الحالات أعلى صفحة الطلب ---------- */
  M.flow = function (status) {
    var at = M.FLOW.indexOf(status);
    return h`<div class="flow">${M.FLOW.map(function (s, i) {
      var done = at > -1 && i < at;
      return h`${i ? raw('<span class="arr">←</span>') : ''}<span class="st${i === at ? ' active' : ''}"${done ? raw(' style="background:var(--success-soft);color:var(--success-text)"') : ''}>${done ? icon('check', 12) : ''}${api.t('maintenance_status', s)}</span>`;
    })}</div>`;
  };

  /* ---------- تفاصيل الطلب (الإدارة والمركز) ---------- */
  M.detail = function (r, fileUrl, opts) {
    opts = opts || {};
    var stage = { request: 'من الطلب', reception: 'عند الاستلام', repair: 'بعد الإصلاح' };
    var photos = r.photos.map(function (p) { return { src: fileUrl(p.sha256), caption: stage[p.stage] || p.stage }; });
    var info = [
      ['النوع', M.kind(r.kind)],
      ['الوصف', h`<span style="white-space:normal">${r.description}</span>`],
      r.odometer_km != null ? ['العداد عند الطلب', h`<span class="num">${fmt.km(r.odometer_km)}</span>`] : null,
      ['المصدر', r.source === 'driver' ? 'السائق من التطبيق' : 'الإدارة'],
      r.emergency ? ['طارئة', r.emergency_reviewed ? 'نعم · روجعت' : BT.pill('نعم · بانتظار المراجعة', 'o')] : null,
      opts.admin && r.driver ? ['السائق', api.name(r.driver.name)] : null,
      ['تاريخ الطلب', fmt.dt(r.created_at)]
    ].filter(Boolean);
    var center = [
      r.center ? ['المركز', r.center.name] : null,
      r.referred_at ? ['الإحالة', fmt.dt(r.referred_at)] : null,
      r.received_at ? ['الوصول', fmt.dt(r.received_at)] : null,
      r.received_km != null ? ['العداد عند الوصول', h`<span class="num">${fmt.km(r.received_km)}</span>`] : null,
      r.final_km != null ? ['العداد بعد الإصلاح', h`<span class="num">${fmt.km(r.final_km)}</span>`] : null,
      r.stay_seconds != null ? ['مدة البقاء في المركز', h`<b class="num">${M.dur(r.stay_seconds)}</b>`] : null
    ].filter(Boolean);
    return h`<div class="card mb-16" style="padding:10px 12px">${M.flow(r.status)}</div>
      ${r.status === 'quote_pending' ? h`<div class="banner warn mb-16">${icon('clock', 16)}<div>عرض السعر أعلى من حد الاعتماد: <b>لا يبدأ الإصلاح</b> قبل اعتماد مدير الصيانة.</div></div>` : ''}
      ${r.status === 'ready' ? h`<div class="banner success mb-16">${icon('bell-ring', 16)}<div>السيارة جاهزة للاستلام؛ أُبلغت الإدارة ويرى السائق ذلك في التطبيق.</div></div>` : ''}
      ${r.status === 'rejected' && r.decision_note ? h`<div class="banner danger mb-16">${icon('circle-x', 16)}<div>سبب الرفض: ${r.decision_note}</div></div>` : ''}
      ${r.status === 'cancelled' && r.cancel_reason ? h`<div class="banner mb-16">${icon('ban', 16)}<div>سبب الإلغاء: ${r.cancel_reason}</div></div>` : ''}
      <div class="grid-2 mb-16">
        <div class="card"><div class="card-h"><div class="card-t">الطلب</div></div>${BT.kv(info)}</div>
        <div class="card"><div class="card-h"><div class="card-t">في المركز</div></div>${center.length ? BT.kv(center) : raw('<div class="muted fs-sm">لم يُحل لمركز بعد</div>')}
          ${r.condition_note ? h`<div class="section-t mt-12">حالة السيارة عند الاستلام</div><div class="fs-sm" style="white-space:pre-wrap">${r.condition_note}</div>` : ''}
          ${r.repair_details ? h`<div class="section-t mt-12">ما تم إصلاحه</div><div class="fs-sm" style="white-space:pre-wrap">${r.repair_details}</div>` : ''}</div>
      </div>
      <div class="card mb-16"><div class="card-h"><div class="card-t">الصور</div></div>${M.thumbs(photos)}</div>
      ${r.quotes.length ? h`<div class="card mb-16"><div class="card-h"><div class="card-t">عروض السعر</div></div>${r.quotes.map(function (q) {
        return h`<div class="highlight-box mb-12"><div class="between mb-8"><b>${BT.amt(q.amount)}</b><span>${BT.pill(q.status === 'approved' ? (q.auto_approved ? 'معتمد تلقائياً (ضمن الحد)' : 'معتمد') : q.status === 'rejected' ? 'مرفوض' : 'بانتظار الاعتماد', q.status === 'approved' ? 'g' : q.status === 'rejected' ? 'r' : 'o')}</span></div>
          ${M.itemsTable(q.items)}${q.notes ? h`<div class="fs-sm mt-8">${q.notes}</div>` : ''}${q.reason ? h`<div class="fs-sm mt-8 t-danger">سبب الرفض: ${q.reason}</div>` : ''}
          <div class="muted fs-sm mt-8">${fmt.dt(q.created_at)}${q.decided_by ? ' · ' + q.decided_by : ''}${q.file_sha256 ? h` · <a href="${fileUrl(q.file_sha256)}" target="_blank" rel="noopener">ملف العرض</a>` : ''}</div>
          ${opts.quoteActions ? opts.quoteActions(q) : ''}</div>`;
      })}</div>` : ''}
      ${r.invoices.length ? h`<div class="card mb-16"><div class="card-h"><div class="card-t">الفواتير</div></div>${r.invoices.map(function (i) {
        return h`<div class="highlight-box mb-12"><div class="between mb-8"><b>فاتورة <span class="num">${i.number}</span> · ${BT.amt(i.total)}</b><span>${M.invStatus(i)}</span></div>
          ${M.flags(i.flags)}${M.itemsTable(i.items)}<div class="muted fs-sm mt-8">${fmt.date(i.invoice_date)} · <a href="${fileUrl(i.file_sha256)}" target="_blank" rel="noopener">ملف الفاتورة</a>${i.reason ? ' · سبب الرفض: ' + i.reason : ''}</div></div>`;
      })}</div>` : ''}
      <div class="grid-2">
        <div class="card"><div class="card-h"><div class="card-t">الجدول الزمني</div></div>${M.timeline(r.events)}</div>
        <div class="card"><div class="card-h"><div class="card-t">المدة في كل حالة</div></div>${M.durations(r.durations)}</div>
      </div>`;
  };
})();
