/* =====================================================================
   BrilliantTech UI — portal.js  (بوابة مراكز الصيانة)
   المركز يرى السيارات المحالة إليه فقط، ويحدّث الحالة، ويرسل عرض السعر
   والفاتورة وتقدير تلفيات الحوادث.
   بوب أب: تفاصيل الطلب (drawer) · تحديث الحالة · بيانات الاستلام (صور) ·
   عرض السعر (بنود ديناميكية) · الفاتورة · تقدير تلفيات حادث · إضافة مستخدم ·
   جاهزة للاستلام (confirm) · معاينة الفاتورة
   للتجربة: قائمة المستخدم ← «عرض كمركز آخر» (مركز الغانم لديه حادث بانتظار التقدير)
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, D = BT.data;
  var cfg = BT.config;
  var P = BT.P = {};
  var CID = BT.store.get('portal-center', 'C1');
  var C = D.centers.find(function (c) { return c.id === CID; }) || D.centers[0];
  var USER = D.users.find(function (u) { return u.center === C.id; }) || { name: C.short };
  var STAGES = D.stages;
  var NEXT = { // الانتقالات المسموحة من كل حالة
    'مستلمة': ['فحص'], 'فحص': ['بانتظار اعتماد العرض', 'قيد الإصلاح'], 'بانتظار اعتماد العرض': [],
    'قيد الإصلاح': ['بانتظار قطع', 'مكتملة'], 'بانتظار قطع': ['قيد الإصلاح'], 'مكتملة': ['جاهزة للاستلام'], 'جاهزة للاستلام': [], 'تم الاستلام': []
  };
  function jobs() { return D.jobs.filter(function (j) { return j.center === C.id; }); }
  function open() { return jobs().filter(function (j) { return j.stage !== 'تم الاستلام'; }); }
  function view() { return document.getElementById('view'); }
  function btn(label, o) { o = o || {}; return h`<button type="button" class="btn ${o.cls || 'btn-secondary'}"${o.action ? h` data-action="${o.action}"` : ''}${o.arg != null ? h` data-arg="${o.arg}"` : ''}>${o.icon ? icon(o.icon, 15) : ''}${label}</button>`; }
  function setTitle(t) { document.title = t + ' — بوابة مراكز الصيانة'; BT.render(document.getElementById('tb-title'), h`<div class="crumbs">${C.name} · ${fmt.dateLong(cfg.today)}</div><h1>${t}</h1>`); }
  function head(t, s, a) { return h`<div class="page-head"><div><h2>${t}</h2>${s ? h`<p>${s}</p>` : ''}</div>${a ? h`<div class="page-actions">${a}</div>` : ''}</div>`; }
  function veh(j) { var v = j.vehicle; return h`<span class="plate">${j.plate}</span>${v ? h`<span class="sub ltr">${v.make} ${v.model} ${v.year}</span>` : ''}`; }
  function note(j) { return j.invoice ? 'فاتورة ' + j.invoice.no : j.estimate && j.estimate.status !== 'معتمد' ? 'عرض ' + fmt.kwd(j.estimate.total) : j.accident ? 'حادث ' + j.accident : '—'; }
  function doc(title, rows) { BT.lightbox({ html: h`<div class="lb-doc"><h3>${title}</h3>${BT.kv(rows)}<p class="muted fs-sm mt-24 center">معاينة توضيحية — الملف الأصلي يُعرض هنا</p></div>`, caption: title }); }
  var NAV = [
    { key: 'jobs', icon: 'car', label: 'السيارات المحالة', count: function () { return open().length; } },
    { key: 'accidents', icon: 'triangle-alert', label: 'الحوادث المحالة', count: function () { return D.accidents.filter(function (a) { return a.center === C.id && !a.estimate; }).length; } },
    { key: 'invoices', icon: 'file-text', label: 'الفواتير' },
    { key: 'users', icon: 'users', label: 'المستخدمون' }
  ];
  function renderNav(active) {
    BT.render(document.getElementById('nav'), h`${NAV.map(function (it) { var c = it.count ? it.count() : 0; return h`<a class="nav-item${it.key === active ? ' active' : ''}" href="#/${it.key}">${icon(it.icon, 17)}<span>${it.label}</span>${c ? h`<span class="count">${c}</span>` : ''}</a>`; })}`);
  }

  /* ---------------- السيارات المحالة ---------------- */
  BT.pages = {};
  BT.pages['jobs'] = function (p, q) {
    setTitle('السيارات المحالة');
    var o = open(), stage = q.stage || '';
    var avg = o.length ? BT.sum(o, function (j) { return j.days; }) / o.length : 0;
    BT.render(view(), h`${head('الورشة تحدّث الحالة، والإدارة تتابع', 'تظهر هنا فقط السيارات المحالة إلى ' + C.name, btn('تسجيل استلام سيارة', { icon: 'log-in', cls: 'btn-primary', action: 'p-receive' }))}
      <div class="kpis">
        ${BT.kpi({ label: 'سيارات لدى المركز', value: String(o.length), sub: 'محالة من ' + cfg.client, dot: 'b' })}
        ${BT.kpi({ label: 'بانتظار اعتماد العرض', value: String(o.filter(function (j) { return j.stage === 'بانتظار اعتماد العرض'; }).length), sub: 'فوق حد الاعتماد', dot: 'o' })}
        ${BT.kpi({ label: 'جاهزة للاستلام', value: String(o.filter(function (j) { return j.stage === 'جاهزة للاستلام'; }).length), sub: 'أُشعر السائق', dot: 'g' })}
        ${BT.kpi({ label: 'متوسط مدة البقاء', value: avg.toFixed(1) + ' يوم', sub: 'تُحسب تلقائياً', dot: 'p' })}
      </div>
      <div class="card" style="padding:10px 12px"><div class="flow" id="p-flow"></div></div>
      <div class="card"><div id="p-table"></div></div>`);
    function flow() { BT.render(document.getElementById('p-flow'), h`${STAGES.map(function (s, i) { var n = jobs().filter(function (j) { return j.stage === s; }).length; return h`${i ? raw('<span class="arr">←</span>') : ''}<button type="button" class="st${stage === s ? ' active' : ''}" data-st="${s}">${s} <span class="n">${n}</span></button>`; })}`); }
    var t = BT.table(document.getElementById('p-table'), {
      rows: function () { return jobs().filter(function (j) { return stage ? j.stage === stage : j.stage !== 'تم الاستلام'; }).sort(function (a, b) { return a.days - b.days; }); },
      search: { placeholder: 'ابحث باللوحة أو رقم الطلب…', text: function (j) { return j.plate + ' ' + j.id + ' ' + j.desc; } },
      columns: [
        { key: 'plate', label: 'السيارة', render: veh },
        { key: 'id', label: 'الطلب', render: function (j) { return h`<span class="num">${j.id}</span><span class="sub">${j.desc}</span>`; } },
        { key: 'stage', label: 'الحالة', render: function (j) { return BT.pill(j.stage, D.stageTone[j.stage]); } },
        { key: 'days', label: 'المدة', num: true, render: function (j) { return j.days === 0 ? 'اليوم' : j.days === 1 ? 'يوم' : j.days === 2 ? 'يومان' : j.days + ' أيام'; } },
        { key: 'note', label: 'ملاحظة', sort: false, render: note }
      ],
      rowClick: function (j) { P.job(j); },
      empty: { icon: 'car', title: 'لا توجد سيارات بهذه الحالة' }
    });
    flow();
    BT.on(view(), 'click', '[data-st]', function (e, b) { var s = b.getAttribute('data-st'); stage = stage === s ? '' : s; flow(); t.refresh(); });
  };

  /* ---------- تفاصيل الطلب ---------- */
  P.job = function (j) {
    var si = STAGES.indexOf(j.stage), est = j.estimate, inv = j.invoice, next = NEXT[j.stage] || [];
    var d = BT.drawer.open({
      title: h`<span class="plate">${j.plate}</span> — ${j.vehicle ? j.vehicle.make + ' ' + j.vehicle.model : ''}`, subtitle: 'طلب ' + j.id + ' · ' + j.type + ' · منذ ' + (j.days === 0 ? 'اليوم' : j.days + ' يوم'), icon: 'wrench', size: 'lg',
      body: h`<div class="flow mb-16">${STAGES.map(function (s, i) { return h`${i ? raw('<span class="arr">←</span>') : ''}<span class="st${i === si ? ' active' : ''}" style="${i < si ? 'background:var(--success-soft);color:var(--success-text)' : ''}">${i < si ? icon('check', 12) : ''}${s}</span>`; })}</div>
        ${j.stage === 'بانتظار اعتماد العرض' ? h`<div class="banner warn mb-12">${icon('clock', 16)}<div>العرض أعلى من حد الاعتماد — <b>لا تبدأ الإصلاح</b> قبل اعتماد ${cfg.client}. يصلك إشعار عند القرار.</div></div>` : ''}
        ${j.stage === 'جاهزة للاستلام' ? h`<div class="banner success mb-12">${icon('bell-ring', 16)}<div>أُشعر السائق بأن السيارة جاهزة. يُسجَّل الاستلام من ${cfg.client} عند وصوله.</div></div>` : ''}
        <div class="grid-2">
          <div><div class="section-t">الطلب</div>${BT.kv([['الوصف', j.desc], ['النوع', j.type], ['المصدر', j.source], ['تاريخ الإحالة', fmt.date(j.opened)], ['الأولوية', 'عادية']])}</div>
          <div><div class="section-t">الاستلام</div>${BT.kv([['وصلت', fmt.date(j.opened) + ' · 09:30'], ['العداد', h`<span class="num">${fmt.km(j.vehicle ? j.vehicle.odo : 0)}</span>`], ['الصور', h`<button type="button" class="btn btn-link fs-sm" data-photos>4 صور ${icon('images', 14)}</button>`]])}</div>
        </div>
        <div class="section-t mt-16">عرض السعر</div>
        ${est ? h`<div class="highlight-box">${est.items ? h`<div class="kv">${est.items.map(function (it) { return h`<div><span>${it[0]}</span><span class="num">${fmt.kwd(it[1])}</span></div>`; })}</div>` : ''}${BT.kv([['الإجمالي', BT.amt(est.total), 'total'], ['الحالة', BT.pill(est.status, est.status === 'معتمد' ? 'g' : 'o')]])}</div>` : h`<div class="muted fs-sm">لم يُرسل عرض سعر بعد. ${j.stage === 'فحص' || j.stage === 'مستلمة' ? 'أرسله بعد الفحص.' : ''}</div>`}
        ${inv ? h`<div class="section-t mt-16">الفاتورة ${inv.no}</div><div class="highlight-box">${BT.kv([inv.parts != null ? ['القطع', BT.amt(inv.parts)] : null, inv.labour != null ? ['الأجور', BT.amt(inv.labour)] : null, ['الإجمالي', BT.amt(inv.total), 'total'], est ? ['العرض المعتمد', BT.amt(est.total)] : null].filter(Boolean))}<div class="flex gap-8 mt-8">${est && inv.total !== est.total ? BT.pill('فرق ' + fmt.signed(inv.total - est.total) + ' عن العرض', 'o') : ''}${BT.pill(inv.status, inv.status === 'مدفوعة' ? 'g' : 'o')}</div></div>` : ''}`,
      buttons: [
        { label: 'إغلاق', cls: 'btn-ghost' },
        (j.stage === 'فحص' || j.stage === 'بانتظار اعتماد العرض') ? { label: est ? 'تعديل العرض' : 'إرسال عرض السعر', cls: j.stage === 'فحص' ? 'btn-primary' : 'btn-outline', icon: 'file-plus', close: false, onClick: function () { P.estimate(j, d); } } : null,
        (j.stage === 'مكتملة' && !inv) ? { label: 'إدخال الفاتورة', cls: 'btn-primary', icon: 'receipt-text', close: false, onClick: function () { P.invoice(j, d); } } : null,
        next.filter(function (s) { return s !== 'بانتظار اعتماد العرض'; }).length ? { label: 'تحديث الحالة', cls: j.stage === 'فحص' ? 'btn-outline' : 'btn-primary', icon: 'refresh-cw', close: false, onClick: function () { P.stage(j, d); } } : null
      ].filter(Boolean)
    });
    BT.on(d.el, 'click', '[data-photos]', function () { BT.lightbox(['أمام', 'خلف', 'يمين', 'يسار'].map(function (s) { return { html: h`<div class="ph" style="width:min(640px,86vw);height:400px">${icon('car', 64)}<span>${s}</span></div>`, caption: 'عند الاستلام — ' + s, sub: j.plate }; })); });
  };
  P.stage = function (j, parent) {
    var next = (NEXT[j.stage] || []).filter(function (s) { return s !== 'بانتظار اعتماد العرض'; });
    var d = BT.modal.open({
      title: 'تحديث الحالة', subtitle: j.plate + ' · الحالة الحالية: ' + j.stage, icon: 'refresh-cw', form: true,
      body: h`<div class="form">${BT.f.radios({ name: 's', label: 'الحالة الجديدة', required: true, value: next[0], options: next.map(function (s) { return { v: s, t: s, d: s === 'بانتظار قطع' ? 'تتوقف السيارة حتى وصول القطعة' : s === 'مكتملة' ? 'انتهى الإصلاح' : s === 'جاهزة للاستلام' ? 'يُشعَر السائق' : '' }; }) })}
        <div id="st-parts" class="hidden">${BT.f.date({ name: 'eta', label: 'الموعد المتوقع لوصول القطعة', value: BT.date.add(cfg.today, 3) })}</div>
        ${BT.f.textarea({ name: 'n', label: 'ملاحظة للإدارة', optional: true, rows: 2 })}${BT.f.upload({ name: 'ph', label: 'صور', optional: true, multiple: true, accept: 'image/*' })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) {
        if (f.s === 'قيد الإصلاح' && j.estimate && j.estimate.status !== 'معتمد') { BT.toast('لا يمكن بدء الإصلاح قبل اعتماد العرض', { type: 'error' }); return false; }
        if (f.s === 'قيد الإصلاح' && !j.estimate) { BT.toast('أرسل عرض السعر أولاً', { type: 'warning' }); return false; }
        j.stage = f.s; if (parent) parent.close();
        BT.toast('تم تحديث الحالة: ' + f.s, { sub: f.s === 'جاهزة للاستلام' ? 'أُرسل إشعار للسائق وللإدارة' : 'تظهر للإدارة فوراً' }); P.router.refresh();
      }
    });
    BT.on(d.el, 'change', '[name=s]', function (e, r) { d.el.querySelector('#st-parts').classList.toggle('hidden', r.value !== 'بانتظار قطع'); });
    var c = d.el.querySelector('[name=s]:checked'); if (c) d.el.querySelector('#st-parts').classList.toggle('hidden', c.value !== 'بانتظار قطع');
  };

  /* ---------- محرر البنود (عرض السعر / التقدير) ---------- */
  function itemsEditor(d, items) {
    var box = d.el.querySelector('#items');
    function read() { return BT.$$('.it-row', box).map(function (r) { return [r.querySelector('[data-k=t]').value, Number((r.querySelector('[data-k=a]').value || '0').replace(/,/g, ''))]; }); }
    function total() { var t = BT.sum(read(), function (x) { return x[1] || 0; }); d.el.querySelector('#items-total').textContent = fmt.kwd(t); var w = d.el.querySelector('#items-warn'); if (w) w.classList.toggle('hidden', t <= cfg.approvalLimit); return t; }
    function draw(list) {
      BT.render(box, h`${list.map(function (x, i) { return h`<div class="it-row flex gap-8 items-center"><input class="input" data-k="t" placeholder="البند (قطعة أو عمل)" value="${x[0]}" aria-label="البند" required><div class="input-group" style="width:170px;flex-shrink:0"><input class="input num-in" data-k="a" inputmode="decimal" placeholder="0.000" value="${x[1] ? fmt.kwd(x[1]) : ''}" aria-label="المبلغ"><span class="addon">د.ك</span></div><button type="button" class="icon-btn sm" data-del="${i}" aria-label="حذف البند"${list.length < 2 ? raw(' disabled') : ''}>${icon('trash-2', 15)}</button></div>`; })}`);
      total();
    }
    d.el.querySelector('#items-add').onclick = function () { var l = read(); l.push(['', 0]); draw(l); BT.$$('[data-k=t]', box).pop().focus(); };
    BT.on(box, 'click', '[data-del]', function (e, b) { var l = read(); l.splice(+b.getAttribute('data-del'), 1); draw(l); });
    box.addEventListener('input', total);
    draw(items && items.length ? items : [['', 0]]);
    return { read: read, total: total };
  }
  var itemsHtml = h`<div class="label mb-8">البنود</div><div id="items" class="col" style="gap:8px"></div>
    <button type="button" class="btn btn-soft btn-sm mt-8" id="items-add">${icon('plus', 14)} إضافة بند</button>
    <div class="highlight-box between mt-12"><b>الإجمالي</b><b><span id="items-total" class="num">0.000</span> <small class="muted">د.ك</small></b></div>`;

  P.estimate = function (j, parent) {
    var d = BT.modal.open({
      title: 'عرض السعر', subtitle: j.plate + ' · ' + j.desc, icon: 'file-plus', size: 'lg', form: true,
      body: h`${itemsHtml}<div id="items-warn" class="banner warn mt-12 hidden">${icon('shield-alert', 16)}<div>الإجمالي أعلى من حد الاعتماد (${fmt.kwd(cfg.approvalLimit)} د.ك): يُرسل للإدارة ولا يبدأ الإصلاح قبل الاعتماد.</div></div>
        <div class="form mt-16">${BT.f.select({ name: 'days', label: 'المدة المتوقعة للإصلاح', value: '2', placeholder: false, options: ['1', '2', '3', '4', '5', '7', '10'].map(function (x) { return { v: x, t: x + (x === '1' ? ' يوم' : ' أيام') }; }) })}${BT.f.textarea({ name: 'n', label: 'ملاحظات', optional: true, rows: 2 })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إرسال العرض', cls: 'btn-primary', icon: 'send', submit: true }],
      onSubmit: function () {
        var items = ed.read().filter(function (x) { return x[0] && x[1] > 0; }), t = BT.round3(BT.sum(items, function (x) { return x[1]; }));
        if (!items.length) { BT.toast('أضف بنداً واحداً على الأقل بمبلغ', { type: 'error' }); return false; }
        var needs = t > cfg.approvalLimit;
        j.estimate = { total: t, items: items, status: needs ? 'بانتظار الاعتماد' : 'معتمد' }; j.cost = t; j.stage = needs ? 'بانتظار اعتماد العرض' : 'قيد الإصلاح';
        if (parent) parent.close();
        BT.toast(needs ? 'أُرسل العرض للاعتماد' : 'العرض ضمن حد الاعتماد — اعتُمد تلقائياً', { sub: fmt.kwd(t) + ' د.ك', type: needs ? 'info' : 'success' }); P.router.refresh();
      }
    });
    var ed = itemsEditor(d, j.estimate && j.estimate.items);
  };
  P.invoice = function (j, parent) {
    var est = j.estimate;
    var d = BT.modal.open({
      title: 'إدخال الفاتورة', subtitle: j.plate + ' · العرض المعتمد ' + (est ? fmt.kwd(est.total) : '—') + ' د.ك', icon: 'receipt-text', form: true,
      body: h`<div class="form-grid">${BT.f.input({ name: 'no', label: 'رقم الفاتورة', required: true })}${BT.f.date({ name: 'date', label: 'التاريخ', required: true, value: cfg.today })}
        ${BT.f.money({ name: 'parts', label: 'القطع', required: true, min: 0 })}${BT.f.money({ name: 'labour', label: 'الأجور', required: true, min: 0 })}
        <div class="full" id="inv-sum"></div>
        <div class="full hidden" id="inv-why">${BT.f.textarea({ name: 'why', label: 'سبب تجاوز العرض المعتمد', rows: 2 })}</div>
        ${BT.f.upload({ name: 'pdf', label: 'ملف الفاتورة (PDF)', required: true, full: true, accept: 'application/pdf,image/*' })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إرسال للاعتماد المالي', cls: 'btn-primary', icon: 'send', submit: true }],
      onSubmit: function (f) {
        var t = BT.round3(f.parts + f.labour);
        if (est && t > est.total && !f.why) { BT.toast('اكتب سبب تجاوز العرض المعتمد', { type: 'error' }); return false; }
        j.invoice = { no: f.no, parts: f.parts, labour: f.labour, total: t, status: 'بانتظار الاعتماد المالي' }; j.cost = t;
        if (parent) parent.close(); BT.toast('أُرسلت الفاتورة ' + f.no + ' للاعتماد المالي'); P.router.refresh();
      }
    });
    function sum() {
      var g = function (n) { return Number((d.el.querySelector('[name=' + n + ']').value || '0').replace(/,/g, '')) || 0; };
      var t = g('parts') + g('labour'), diff = est ? t - est.total : 0;
      BT.render(d.el.querySelector('#inv-sum'), h`<div class="highlight-box between"><span>الإجمالي</span><b>${BT.amt(t)}</b></div>${diff > 0 ? h`<div class="banner warn mt-8 fs-sm">${icon('triangle-alert', 15)}<div>أعلى من العرض المعتمد بـ <b class="num">${fmt.kwd(diff)}</b> د.ك — سيظهر الفرق للإدارة.</div></div>` : ''}`);
      d.el.querySelector('#inv-why').classList.toggle('hidden', !(diff > 0));
    }
    BT.on(d.el, 'input', '[name=parts],[name=labour]', sum); sum();
  };
  BT.actions['p-receive'] = function () {
    var list = jobs().filter(function (j) { return j.stage === 'مستلمة'; });
    BT.modal.open({
      title: 'تسجيل استلام سيارة', subtitle: 'وقت الوصول والعداد وحالة السيارة والصور', icon: 'log-in', size: 'lg', form: true,
      body: h`<div class="form-grid">${BT.f.select({ name: 'j', label: 'السيارة المحالة', required: true, options: list.map(function (j) { return { v: j.id, t: j.plate + ' — ' + j.desc }; }), hint: list.length ? '' : 'لا توجد سيارات بانتظار الاستلام' })}
        ${BT.f.input({ name: 'at', label: 'وقت الوصول', type: 'datetime-local', required: true, value: cfg.today + 'T09:30' })}
        ${BT.f.input({ name: 'odo', label: 'قراءة العداد', required: true, num: true })}
        ${BT.f.select({ name: 'fuel', label: 'مستوى الوقود', value: 'نصف', placeholder: false, options: ['فارغ', 'ربع', 'نصف', 'ثلاثة أرباع', 'ممتلئ'] })}
        <div class="field full"><label>صور السيارة<span class="req">*</span></label><div class="cam-grid" style="grid-template-columns:repeat(4,minmax(0,1fr))">${['أمام', 'خلف', 'يمين', 'يسار'].map(function (s) { return h`<label class="cam-tile"><span class="cam-ic">${icon('camera', 18)}</span><span>${s}</span><input type="file" accept="image/*" capture="environment" name="ph-${s}" required data-msg="التقط الصور الأربع"></label>`; })}</div><div class="err-msg"></div></div>
        ${BT.f.textarea({ name: 'n', label: 'ملاحظات على حالة السيارة', optional: true, full: true, rows: 2 })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'تسجيل الاستلام', cls: 'btn-primary', icon: 'check', submit: true }],
      onSubmit: function (f) { BT.toast('تم تسجيل الاستلام', { sub: 'بدأ احتساب مدة البقاء · ظهر للإدارة' }); }
    });
  };

  /* ---------------- الحوادث المحالة ---------------- */
  BT.pages['accidents'] = function () {
    setTitle('الحوادث المحالة');
    var list = D.accidents.filter(function (a) { return a.center === C.id; });
    BT.render(view(), h`${head('تقدير تلفيات الحوادث', 'تصلك صور السيارة وتقرير الشرطة، وتُدخل التقدير ليعتمده مدير الصيانة')}
      ${list.length ? h`<div class="grid-2">${list.map(function (a) {
        return h`<div class="card col" style="gap:12px"><div class="between"><div><div class="card-t">حادث <span class="num">${a.id}</span></div><div class="card-meta"><span class="plate">${a.plate}</span> · ${fmt.date(a.date)}</div></div>${BT.pill(a.estimate ? 'أُرسل التقدير' : 'بانتظار تقديرك', a.estimate ? 'g' : 'o', true)}</div>
          <div class="ph-grid cols-4">${['أمام', 'خلف', 'يمين', 'يسار'].map(function (s, i) { return h`<button type="button" class="ph" data-aph="${a.id}|${i}" style="min-height:70px">${icon('car', 20)}<span>${s}</span></button>`; })}</div>
          ${a.police ? h`<button type="button" class="doc-link" data-apol="${a.id}"><span class="dl-ic">${icon('file-text', 18)}</span><span class="flex-1"><b>تقرير الشرطة</b><small>${a.police.file}</small></span></button>` : ''}
          ${a.estimate ? BT.kv([['التقدير المرسل', BT.amt(a.estimate)]]) : h`<button type="button" class="btn btn-primary" data-aest="${a.id}">${icon('calculator', 15)} إدخال تقدير التلفيات</button>`}</div>`;
      })}</div>` : h`<div class="card">${BT.empty('shield-check', 'لا توجد حوادث محالة', 'تظهر هنا الحوادث التي تحيلها الإدارة لتقدير التلفيات')}</div>`}`);
    function acc(id) { return D.accidents.find(function (x) { return x.id === id; }); }
    BT.on(view(), 'click', '[data-aph]', function (e, b) { var x = b.getAttribute('data-aph').split('|'); BT.lightbox(['أمام', 'خلف', 'يمين', 'يسار'].map(function (s) { return { html: h`<div class="ph" style="width:min(640px,86vw);height:400px">${icon('car', 64)}<span>${s}</span></div>`, caption: 'حادث ' + x[0] + ' — ' + s }; }), +x[1]); });
    BT.on(view(), 'click', '[data-apol]', function (e, b) { var a = acc(b.getAttribute('data-apol')); doc('تقرير قسم الشرطة — ' + a.police.no, [['رقم التقرير', a.police.no], ['التاريخ', fmt.date(a.date)], ['الموقع', a.location], ['السيارة', a.plate]]); });
    BT.on(view(), 'click', '[data-aest]', function (e, b) { P.accEstimate(acc(b.getAttribute('data-aest'))); });
  };
  P.accEstimate = function (a) {
    var d = BT.modal.open({
      title: 'تقدير تلفيات الحادث ' + a.id, subtitle: a.plate + ' · ' + a.location, icon: 'calculator', size: 'lg', form: true,
      body: h`${itemsHtml}<div class="form mt-16">${BT.f.textarea({ name: 'n', label: 'وصف التلفيات', required: true, rows: 3 })}${BT.f.upload({ name: 'ph', label: 'صور إضافية من الفحص', optional: true, multiple: true, accept: 'image/*' })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إرسال التقدير', cls: 'btn-primary', icon: 'send', submit: true }],
      onSubmit: function () {
        var items = ed.read().filter(function (x) { return x[0] && x[1] > 0; }); if (!items.length) { BT.toast('أضف بنود التقدير', { type: 'error' }); return false; }
        a.estimate = BT.round3(BT.sum(items, function (x) { return x[1]; })); a.status = 'بانتظار اعتماد التقدير'; a.statusTone = 'b';
        BT.toast('أُرسل التقدير ' + fmt.kwd(a.estimate) + ' د.ك', { sub: 'بانتظار اعتماد مدير الصيانة في ' + cfg.client }); P.router.refresh();
      }
    });
    var ed = itemsEditor(d, [['', 0]]);
  };

  /* ---------------- الفواتير ---------------- */
  BT.pages['invoices'] = function () {
    setTitle('الفواتير');
    var list = jobs().filter(function (j) { return j.invoice; });
    var waiting = jobs().filter(function (j) { return j.stage === 'مكتملة' && !j.invoice; });
    BT.render(view(), h`${head('الفواتير', 'تُقارن بنود الفاتورة بالعرض المعتمد قبل الاعتماد المالي', waiting.length ? btn('فاتورة جديدة', { icon: 'plus', cls: 'btn-primary', action: 'p-inv-new' }) : '')}
      <div class="kpis cols-3">${BT.kpi({ label: 'فواتير الشهر', value: String(list.length), dot: 'b' })}${BT.kpi({ label: 'بانتظار الاعتماد المالي', value: String(list.filter(function (j) { return j.invoice.status === 'بانتظار الاعتماد المالي'; }).length), dot: 'o' })}${BT.kpi({ label: 'إجمالي الفواتير', value: fmt.kwd(BT.sum(list, function (j) { return j.invoice.total; })), sub: 'د.ك', dot: 'g' })}</div>
      <div class="card"><div id="inv-table"></div></div>`);
    BT.table(document.getElementById('inv-table'), {
      rows: function () { return list; },
      columns: [
        { key: 'no', label: 'الفاتورة', sort: function (j) { return j.invoice.no; }, render: function (j) { return h`<b class="num">${j.invoice.no}</b>`; } },
        { key: 'plate', label: 'السيارة', render: veh },
        { key: 'desc', label: 'العمل' },
        { key: 'total', label: 'المبلغ (د.ك)', num: true, sort: function (j) { return j.invoice.total; }, render: function (j) { return fmt.kwd(j.invoice.total); } },
        { key: 'st', label: 'الحالة', sort: function (j) { return j.invoice.status; }, render: function (j) { return BT.pill(j.invoice.status, j.invoice.status === 'مدفوعة' ? 'g' : 'o'); } }
      ],
      rowClick: function (j) { doc('فاتورة ' + j.invoice.no + ' — ' + C.name, [['السيارة', j.plate], ['العمل', j.desc], ['القطع', j.invoice.parts != null ? fmt.kwd(j.invoice.parts) : '—'], ['الأجور', j.invoice.labour != null ? fmt.kwd(j.invoice.labour) : '—'], ['الإجمالي', fmt.kwd(j.invoice.total) + ' د.ك'], ['الحالة', j.invoice.status]]); }
    });
  };
  BT.actions['p-inv-new'] = function () {
    var w = jobs().filter(function (j) { return j.stage === 'مكتملة' && !j.invoice; });
    if (w.length === 1) return P.invoice(w[0]);
    BT.modal.open({ title: 'اختر الطلب', icon: 'receipt-text', size: 'sm', form: true, body: h`<div class="form">${BT.f.select({ name: 'j', label: 'الطلب المكتمل', required: true, options: w.map(function (j) { return { v: j.id, t: j.plate + ' — ' + j.desc }; }) })}</div>`, buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'متابعة', cls: 'btn-primary', submit: true }], onSubmit: function (f) { setTimeout(function () { P.invoice(D.jobs.find(function (j) { return j.id === f.j; })); }, 240); } });
  };

  /* ---------------- المستخدمون ---------------- */
  BT.pages['users'] = function () {
    setTitle('المستخدمون');
    var list = D.users.filter(function (u) { return u.center === C.id; });
    BT.render(view(), h`${head('مستخدمو المركز', 'كل مستخدم يدخل برمز تحقق على جواله', btn('إضافة مستخدم', { icon: 'user-plus', cls: 'btn-primary', action: 'p-user-new' }))}
      <div class="card"><div class="table-wrap"><table class="t"><thead><tr><th>المستخدم</th><th>الجوال</th><th>التحقق بخطوتين</th><th>آخر دخول</th><th>الحالة</th></tr></thead><tbody>${list.map(function (u) { return h`<tr><td>${BT.person(u.name, u.id)}</td><td class="num">${u.phone}</td><td>${u.twoFA ? BT.pill('مفعّل', 'g') : BT.pill('غير مفعّل', 'o')}</td><td>${u.last}</td><td>${BT.pill('نشط', 'g', true)}</td></tr>`; })}</tbody></table></div></div>`);
  };
  BT.actions['p-user-new'] = function () {
    BT.modal.open({
      title: 'إضافة مستخدم للمركز', icon: 'user-plus', form: true,
      body: h`<div class="form">${BT.f.input({ name: 'name', label: 'الاسم', required: true })}${BT.f.input({ name: 'phone', label: 'الجوال', required: true, validate: 'kwPhone', maxlength: 8 })}${BT.f.radios({ name: 'role', label: 'الدور', required: true, value: 'استقبال', options: [{ v: 'استقبال', t: 'استقبال', d: 'الاستلام والحالات' }, { v: 'محاسبة', t: 'محاسبة', d: 'العروض والفواتير' }, { v: 'فني', t: 'فني', d: 'تحديث الحالة فقط' }] })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إضافة', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) { D.users.push({ id: 'U-' + (50 + D.users.length), name: C.short + ' — ' + f.name, role: 'مركز صيانة', phone: f.phone, last: '—', twoFA: true, active: true, center: C.id }); BT.toast('تمت إضافة ' + f.name, { sub: 'يصله رابط الدخول على ' + f.phone }); P.router.refresh(); }
    });
  };

  /* ---------------- القائمة والتشغيل ---------------- */
  BT.actions['p-user-menu'] = function (a, el) {
    BT.menu(el, [{ head: USER.name }, { label: BT.theme.get() === 'dark' ? 'الوضع الفاتح' : 'الوضع الداكن', icon: 'moon', onClick: BT.theme.toggle }, { sep: true }, { head: 'عرض كمركز آخر (تجريبي)' }].concat(D.centers.map(function (c) { return { label: c.name, icon: 'store', checked: c.id === C.id, onClick: function () { BT.store.set('portal-center', c.id); location.reload(); } }; })).concat([{ sep: true }, { label: 'لوحة الإدارة', icon: 'house', onClick: function () { location.href = 'demo-admin.html'; } }, { label: 'تسجيل الخروج', icon: 'log-out', danger: true, onClick: function () { location.href = 'demo.html'; } }]), { focus: true });
  };
  BT.actions['theme'] = function () { BT.theme.toggle(); };
  BT.actions['toggle-nav'] = function () { document.getElementById('app').classList.toggle('nav-open'); };
  function boot() {
    document.getElementById('center-name').textContent = C.name;
    document.getElementById('foot-user').textContent = USER.name;
    var ini = C.short === 'مركز الملا' ? 'ML' : C.short === 'مركز الغانم' ? 'GH' : 'FH';
    document.getElementById('foot-av').textContent = ini; document.getElementById('top-av').textContent = ini;
    if (BT.store.get('frame', false)) document.body.classList.add('frame');
    P.router = BT.router(BT.pages, {
      default: 'jobs', view: view,
      onBefore: function (r) { BT.closeAll(); BT.closeMenu(); var o = view(), f = o.cloneNode(false); o.replaceWith(f); document.getElementById('app').classList.remove('nav-open'); renderNav(r.current); }
    });
    document.querySelector('.sb-backdrop').addEventListener('click', function () { document.getElementById('app').classList.remove('nav-open'); });
    BT.hydrate(document);
    P.router.start();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else setTimeout(boot, 0);
})();
