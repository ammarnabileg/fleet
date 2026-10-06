/* =====================================================================
   BrilliantTech — center/portal.js  (بوابة مراكز الصيانة، مربوطة بالخادم)
   حساب المركز يرى فقط ما أُحيل لمركزه (الخادم يفرض ذلك في كل طلب):
   الاستلام بوقت الوصول والعداد وصوره، الفحص، عرض السعر، الإصلاح، الاكتمال
   بقراءة العداد النهائية، جاهزة للاستلام، والفواتير بملفها وبنودها.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, M = BT.mnt;
  var P = BT.P = { center: null, counts: {} };
  BT.pages = {};

  function view() { return document.getElementById('view'); }
  function setTitle(t, crumbs) {
    document.title = t + ' — بوابة مراكز الصيانة';
    BT.render(document.getElementById('tb-title'), h`<div class="crumbs">${crumbs ? h`${crumbs.map(function (c, i) { return h`${i ? icon('chevron-left', 12) : ''}${c[1] ? h`<a href="#/${c[1]}">${c[0]}</a>` : c[0]}`; })}` : h`${P.center ? P.center.name : ''} · ${fmt.dateLong(BT.config.today)}`}</div><h1>${t}</h1>`);
  }
  function head(t, s, a) { return h`<div class="page-head"><div><h2>${t}</h2>${s ? h`<p>${s}</p>` : ''}</div>${a ? h`<div class="page-actions">${a}</div>` : ''}</div>`; }
  function spinner() { return h`<div class="page-loading"><span class="spinner"></span>جاري التحميل…</div>`; }
  function errorBox(err) { return h`<div class="card"><div class="card-b">${BT.empty('wifi-off', 'تعذر تحميل البيانات', api.message(err), raw('<button type="button" class="btn btn-sm btn-secondary mt-8" data-action="reload">إعادة المحاولة</button>'))}</div></div>`; }
  BT.actions['reload'] = function () { P.router.refresh(); };
  function fileUrl(id) { return function (sha) { return api.url('/portal/requests/' + id + '/files/' + sha); }; }
  function upload(file) { return api.upload(file).then(function (f) { return f.sha256; }); }
  function uploadAll(files) { return Promise.all(Array.prototype.map.call(files || [], upload)); }
  function form(o) { // نافذة نموذج: submit يعيد Promise، والخطأ يبقيها مفتوحة
    return BT.modal.open({
      title: o.title, subtitle: o.subtitle, icon: o.icon, size: o.size, form: true, body: o.body,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: o.submitText || 'حفظ', cls: 'btn-primary', icon: o.submitIcon, submit: true }],
      onOpen: o.onOpen,
      onSubmit: function (v, dlg) {
        return Promise.resolve(o.submit(v, dlg)).then(function (res) {
          if (res === false) return false;
          BT.toast(o.done || 'تم الحفظ', o.doneSub ? { sub: o.doneSub(res) } : undefined);
          P.router.refresh(); refreshCounts();
          return true;
        }).catch(api.fail);
      }
    });
  }

  /* ---------- القائمة ---------- */
  var NAV = [
    { key: 'requests', icon: 'car', label: 'السيارات المحالة', count: 'active' },
    { key: 'accidents', icon: 'shield-alert', label: 'أضرار الحوادث', count: 'acc', perm: 'portal.damage' },
    { key: 'history', icon: 'history', label: 'السجل' },
    { key: 'invoices', icon: 'receipt-text', label: 'الفواتير', perm: 'portal.invoices' }
  ];
  function renderNav(active) {
    BT.render(document.getElementById('nav'), h`${NAV.filter(function (n) { return !n.perm || api.can(n.perm); }).map(function (it) {
      var c = it.count ? P.counts[it.count] : 0, hot = it.count === 'acc' ? P.counts.accFresh : P.counts.fresh;
      return h`<a class="nav-item${it.key === active ? ' active' : ''}" href="#/${it.key}">${icon(it.icon, 17)}<span>${it.label}</span>${c ? h`<span class="count${hot ? ' hot' : ''}">${c}</span>` : ''}</a>`;
    })}`);
  }
  function navKey(route) { var k = (route || '').split('/')[0]; return k === 'r' ? 'requests' : k === 'a' ? 'accidents' : k || 'requests'; }
  function refreshCounts() {
    return Promise.all([
      api.get('/portal/requests'),
      api.can('portal.damage') ? api.get('/portal/accidents') : Promise.resolve([])
    ]).then(function (res) {
      P.counts.active = res[0].length;
      P.counts.fresh = res[0].filter(function (r) { return r.is_new; }).length;
      P.counts.acc = res[1].length;
      P.counts.accFresh = res[1].filter(function (a) { return a.is_new; }).length;
      renderNav(navKey(P.router && P.router.current));
    }, function () {});
  }

  /* ---------- السيارات المحالة ---------- */
  BT.pages['requests'] = function (p, q) {
    setTitle('السيارات المحالة');
    var v = view(), stage = q.status || '';
    BT.render(v, h`${head('السيارات المحالة إلى مركزكم', 'حدّثوا الحالة أولاً بأول: الإدارة ترى كل تحديث فوراً، والمدة تُحسب تلقائياً من وقت الوصول')}<div data-body>${spinner()}</div>`);
    var body = v.querySelector('[data-body]');
    api.get('/portal/requests').then(function (rows) {
      if (!document.contains(body)) return;
      var stays = rows.filter(function (r) { return r.stay_seconds != null; });
      var avg = stays.length ? BT.sum(stays, function (r) { return r.stay_seconds; }) / stays.length : null;
      BT.render(body, h`<div class="kpis">
          ${BT.kpi({ label: 'لدى المركز', value: String(rows.length), sub: rows.filter(function (r) { return r.is_new; }).length + ' جديدة لم تُفتح', dot: 'b' })}
          ${BT.kpi({ label: 'بانتظار اعتماد العرض', value: String(rows.filter(function (r) { return r.status === 'quote_pending'; }).length), sub: 'لا يبدأ الإصلاح قبل الاعتماد', dot: 'o' })}
          ${BT.kpi({ label: 'جاهزة للاستلام', value: String(rows.filter(function (r) { return r.status === 'ready'; }).length), sub: 'أُبلغت الإدارة', dot: 'g' })}
          ${BT.kpi({ label: 'متوسط مدة البقاء', value: M.dur(avg), sub: 'للسيارات المستلمة', dot: 'p' })}
        </div>
        <div class="card" style="padding:10px 12px"><div class="flow">${M.AT_CENTER.map(function (s, i) {
          var n = rows.filter(function (r) { return r.status === s; }).length;
          return h`${i ? raw('<span class="arr">←</span>') : ''}<button type="button" class="st${stage === s ? ' active' : ''}" data-st="${s}">${api.t('maintenance_status', s)} <span class="n">${n}</span></button>`;
        })}</div></div>
        <div class="card"><div data-table></div></div>`);
      BT.table(body.querySelector('[data-table]'), {
        rows: function () { return rows.filter(function (r) { return !stage || r.status === stage; }); },
        search: { placeholder: 'اللوحة أو رقم الطلب…', text: function (r) { return r.vehicle.plate_number + ' ' + r.number + ' ' + r.description; } },
        columns: [
          { key: 'vehicle', label: 'السيارة', render: function (r) { return h`${M.vehicle(r.vehicle)}${r.is_new ? h` ${BT.pill('جديدة', 'b')}` : ''}`; } },
          { key: 'number', label: 'الطلب', render: function (r) { return h`<span class="num">#${r.number}</span><span class="sub">${M.kind(r.kind)}${r.emergency ? ' · طارئة' : ''}</span>`; } },
          { key: 'status', label: 'الحالة', render: function (r) { return M.status(r.status); } },
          { key: 'stay_seconds', label: 'المدة', num: true, render: function (r) { return r.stay_seconds != null ? M.dur(r.stay_seconds) : h`<span class="muted">محالة ${fmt.since(r.referred_at)}</span>`; } }
        ],
        rowClick: function (r) { P.router.go('r/' + r.id); },
        empty: { icon: 'car', title: stage ? 'لا توجد سيارات بهذه الحالة' : 'لا توجد سيارات محالة لمركزكم الآن' }
      });
      BT.on(body, 'click', '[data-st]', function (e, b) { var s = b.getAttribute('data-st'); P.router.go('requests' + (stage === s ? '' : '?status=' + s)); });
    }, function (err) { if (document.contains(body)) BT.render(body, errorBox(err)); });
  };

  /* ---------- أضرار الحوادث: التقدير المطلوب من المركز ---------- */
  function accUrl(id) { return function (sha) { return api.url('/portal/accidents/' + id + '/files/' + sha); }; }
  BT.pages['accidents'] = function (p, q) {
    setTitle('أضرار الحوادث');
    var hist = q.tab === 'history', v = view();
    BT.render(v, h`${head('حوادث محالة لتقدير الأضرار', 'قدّروا الأضرار بنداً بنداً؛ يعتمد مدير الصيانة التقدير قبل أي إجراء')}
      <div class="tabs mb-16"><a class="tab${hist ? '' : ' active'}" href="#/accidents">بانتظار التقدير أو الاعتماد</a><a class="tab${hist ? ' active' : ''}" href="#/accidents?tab=history">السجل</a></div>
      <div class="card"><div data-table>${spinner()}</div></div>`);
    api.get('/portal/accidents', { active: !hist }).then(function (rows) {
      var el = v.querySelector('[data-table]');
      if (!el) return;
      BT.table(el, {
        rows: rows,
        search: { placeholder: 'اللوحة أو رقم الحادث…', text: function (a) { return a.vehicle.plate_number + ' ' + a.number; } },
        columns: [
          { key: 'vehicle', label: 'السيارة', render: function (a) { return h`${M.vehicle(a.vehicle)}${a.is_new ? h` ${BT.pill('جديد', 'b')}` : ''}`; } },
          { key: 'number', label: 'الحادث', render: function (a) { return h`<span class="num">#${a.number}</span><span class="sub">${fmt.dt(a.occurred_at)}</span>`; } },
          { key: 'estimate_status', label: 'التقدير', render: function (a) { return BT.acc.estimate(a.estimate_status); } },
          { key: 'estimate_total', label: 'القيمة', num: true, render: function (a) { return a.estimate_total != null ? BT.amt(Number(a.estimate_total)) : '—'; } },
          { key: 'referred_at', label: 'الإحالة', render: function (a) { return fmt.since(a.referred_at); } }
        ],
        rowClick: function (a) { P.router.go('a/' + a.id); },
        empty: { icon: 'shield-alert', title: hist ? 'لا يوجد سجل بعد' : 'لا توجد حوادث بانتظار تقديركم' }
      });
    }, function (err) { var el = v.querySelector('[data-table]'); if (el) BT.render(el, errorBox(err)); });
  };

  BT.pages['a/:id'] = function (p) {
    setTitle('حادث', [['أضرار الحوادث', 'accidents'], ['الحادث']]);
    var v = view();
    BT.render(v, spinner());
    api.get('/portal/accidents/' + p.id).then(function (a) {
      if (!document.contains(v)) return;
      refreshCounts();
      setTitle('حادث #' + a.number + ' · ' + a.vehicle.plate_number, [['أضرار الحوادث', 'accidents'], ['#' + a.number]]);
      var canEstimate = ['none', 'rejected'].indexOf(a.estimate_status) > -1 && api.can('portal.damage');
      var banner = {
        none: ['info', 'info', 'افحصوا السيارة والصور ثم أرسلوا تقدير الأضرار بالبنود.'],
        pending: ['warn', 'clock', 'أُرسل التقدير: بانتظار اعتماد مدير الصيانة.'],
        approved: ['success', 'circle-check', 'اعتُمد التقدير. إن أُرسلت السيارة لكم للإصلاح ستظهر في «السيارات المحالة».'],
        rejected: ['danger', 'circle-x', 'رُفض التقدير: راجعوا السبب وأرسلوا تقديراً جديداً.']
      }[a.estimate_status];
      BT.render(v, h`${head(h`${M.vehicleLine(a.vehicle)} · حادث <span class="num">#${a.number}</span>`, h`${BT.acc.estimate(a.estimate_status)} · ${fmt.dt(a.occurred_at)}`,
          canEstimate ? h`<button type="button" class="btn btn-primary" data-est>${icon('file-plus', 15)}${a.estimate_status === 'rejected' ? 'تقدير جديد' : 'إرسال تقدير الأضرار'}</button>` : '')}
        <div class="banner ${banner[0]} mb-16">${icon(banner[1], 16)}<div>${banner[2]}${a.estimate_reason ? h`<br><b>سبب الرفض:</b> ${a.estimate_reason}` : ''}</div></div>
        <div class="grid-2 mb-16">
          <div class="card"><div class="card-h"><div class="card-t">الحادث</div></div>${BT.kv([
            ['السيارة', M.vehicleLine(a.vehicle)],
            ['الوقت', fmt.dt(a.occurred_at)],
            ['الوصف', h`<span style="white-space:normal">${a.description}</span>`],
            ['الإحالة', fmt.dt(a.referred_at)]
          ])}</div>
          <div class="card"><div class="card-h"><div class="card-t">الصور</div></div>${BT.acc.photos(a.photos, accUrl(a.id))}</div>
        </div>
        ${BT.acc.estimateCard(a, null)}`);
      var b = v.querySelector('[data-est]');
      if (b) b.onclick = function () { estimateForm(a); };
    }, function (err) { if (document.contains(v)) BT.render(v, errorBox(err)); });
  };

  function estimateForm(a) {
    var ed;
    form({
      title: 'تقدير أضرار الحادث', subtitle: a.vehicle.plate_number + ' · حادث #' + a.number, icon: 'file-plus', size: 'lg',
      body: h`${M.itemsHtml}<div class="form mt-16">${BT.f.textarea({ name: 'notes', label: 'ملاحظات (المدة المتوقعة للإصلاح مثلاً)', optional: true, rows: 2 })}
        ${BT.f.upload({ name: 'file', label: 'ملف التقدير', optional: true, accept: 'image/*,application/pdf' })}
        ${BT.f.upload({ name: 'ph', label: 'صور الأضرار من المركز', optional: true, multiple: true, accept: 'image/*', accept_label: 'صور فقط · حتى 12 صورة' })}</div>
        <div class="muted fs-sm mt-8">يعتمد مدير الصيانة التقدير قبل استخدامه؛ لا يمكن تعديله بعد الإرسال إلا إذا رُفض.</div>`,
      onOpen: function (dlg) { ed = M.itemsEditor(dlg.body); },
      submitText: 'إرسال التقدير', submitIcon: 'send', done: 'أُرسل التقدير', doneSub: function () { return 'بانتظار اعتماد مدير الصيانة'; },
      submit: function (f) {
        if (!ed.valid() || ed.total() <= 0) { BT.toast('أكمل البنود: الوصف والسعر لكل بند', { type: 'error' }); return false; }
        return Promise.all([f.file && f.file[0] ? upload(f.file[0]) : Promise.resolve(null), uploadAll(f.ph)]).then(function (up) {
          return api.post('/portal/accidents/' + a.id + '/estimate', { total: ed.total().toFixed(3), items: ed.read(), notes: f.notes || null, file_sha256: up[0], photos: up[1] });
        });
      }
    });
  }

  /* ---------- السجل ---------- */
  BT.pages['history'] = function () {
    setTitle('السجل');
    var v = view();
    BT.render(v, h`${head('السيارات التي غادرت المركز', 'المستلمة والمغلقة والملغاة بعد الإحالة')}<div class="card"><div data-table>${spinner()}</div></div>`);
    api.get('/portal/requests', { active: false }).then(function (rows) {
      var el = v.querySelector('[data-table]');
      if (!el) return;
      BT.table(el, {
        rows: rows,
        search: { placeholder: 'اللوحة أو رقم الطلب…', text: function (r) { return r.vehicle.plate_number + ' ' + r.number; } },
        columns: [
          { key: 'vehicle', label: 'السيارة', render: function (r) { return M.vehicle(r.vehicle); } },
          { key: 'number', label: 'الطلب', render: function (r) { return h`<span class="num">#${r.number}</span><span class="sub">${M.kind(r.kind)}</span>`; } },
          { key: 'status', label: 'الحالة', render: function (r) { return M.status(r.status); } },
          { key: 'stay_seconds', label: 'مدة البقاء', num: true, render: function (r) { return M.dur(r.stay_seconds); } },
          { key: 'picked_up_at', label: 'الاستلام', render: function (r) { return fmt.dt(r.picked_up_at); } }
        ],
        rowClick: function (r) { P.router.go('r/' + r.id); },
        empty: { icon: 'history', title: 'لا يوجد سجل بعد' }
      });
    }, function (err) { var el = v.querySelector('[data-table]'); if (el) BT.render(el, errorBox(err)); });
  };

  /* ---------- طلب واحد ---------- */
  BT.pages['r/:id'] = function (p) {
    setTitle('طلب صيانة', [['السيارات المحالة', 'requests'], ['الطلب']]);
    var v = view();
    BT.render(v, spinner());
    api.get('/portal/requests/' + p.id).then(function (r) {
      if (!document.contains(v)) return;
      setTitle('طلب #' + r.number + ' · ' + r.vehicle.plate_number, [['السيارات المحالة', 'requests'], ['#' + r.number]]);
      var acts = [], s = r.status;
      var hasInvoice = r.invoices.some(function (i) { return i.status !== 'rejected'; });
      if (s === 'referred') acts.push(['تسجيل الاستلام', 'log-in', 'btn-primary', 'receive']);
      if (s === 'received') acts.push(['بدء الفحص', 'search', 'btn-secondary', 'inspection']);
      if (['received', 'inspection'].indexOf(s) > -1 && api.can('portal.quotes')) acts.push(['إرسال عرض السعر', 'file-plus', 'btn-primary', 'quote']);
      if (['in_repair', 'waiting_parts'].indexOf(s) > -1 && api.can('portal.quotes')) acts.push(['عرض سعر معدّل', 'file-plus', 'btn-ghost', 'quote']);
      if (s === 'in_repair') acts.push(['بانتظار قطع', 'package', 'btn-secondary', 'waiting_parts']);
      if (s === 'waiting_parts') acts.push(['استئناف الإصلاح', 'wrench', 'btn-secondary', 'in_repair']);
      if (['in_repair', 'waiting_parts'].indexOf(s) > -1) acts.push(['اكتمل الإصلاح', 'circle-check', 'btn-primary', 'complete']);
      if (s === 'completed') acts.push(['جاهزة للاستلام', 'bell-ring', 'btn-primary', 'ready']);
      if (s === 'ready') acts.push(['تم الاستلام', 'log-out', 'btn-secondary', 'picked']);
      if (['completed', 'ready', 'picked_up'].indexOf(s) > -1 && !hasInvoice && api.can('portal.invoices')) acts.push(['إدخال الفاتورة', 'receipt-text', s === 'picked_up' ? 'btn-primary' : 'btn-outline', 'invoice']);
      BT.render(v, h`${head(h`${M.vehicleLine(r.vehicle)} · طلب <span class="num">#${r.number}</span>`, h`${M.status(r.status)} · ${M.kind(r.kind)}${r.emergency ? ' · طارئة' : ''}`, h`${acts.map(function (a) { return h`<button type="button" class="btn ${a[2]}" data-act="${a[3]}">${icon(a[1], 15)}${a[0]}</button>`; })}`)}
        ${M.detail(r, fileUrl(r.id))}`);
      BT.on(v, 'click', '[data-act]', function (e, b) { ACT[b.getAttribute('data-act')](r); });
    }, function (err) { if (document.contains(v)) BT.render(v, errorBox(err)); });
  };

  var ACT = {
    receive: function (r) {
      form({
        title: 'تسجيل استلام السيارة', subtitle: r.vehicle.plate_number + ' · طلب #' + r.number, icon: 'log-in', size: 'lg',
        body: h`<div class="form-grid">
          ${BT.f.input({ name: 'at', label: 'وقت الوصول', type: 'datetime-local', optional: true, hint: 'اتركه فارغاً إن وصلت الآن' })}
          ${BT.f.input({ name: 'km', label: 'قراءة العداد', required: true, num: true })}
          <div class="full">${BT.f.camera({ name: 'odo', label: 'صورة العداد', required: true, cta: 'صورة العداد', sub: 'إلزامية' })}</div>
          ${BT.f.upload({ name: 'ph', label: 'صور حالة السيارة', optional: true, multiple: true, full: true, accept: 'image/*', accept_label: 'صور فقط · حتى 12 صورة' })}
          ${BT.f.textarea({ name: 'cond', label: 'ملاحظات على حالة السيارة', optional: true, full: true, rows: 2 })}</div>
          <div class="banner info mt-12">${icon('info', 16)}<div>بالاستلام تنتهي عهدة السائق عند هذه القراءة ويتوقف تتبع موقعه، وتصبح السيارة «في الصيانة».</div></div>`,
        submitText: 'تسجيل الاستلام', submitIcon: 'check', done: 'تم تسجيل الاستلام', doneSub: function () { return 'بدأ احتساب مدة البقاء'; },
        submit: function (f, dlg) {
          var at = dlg.form.querySelector('[name=at]').value;
          return Promise.all([upload(f.odo[0]), uploadAll(f.ph)]).then(function (up) {
            return api.post('/portal/requests/' + r.id + '/receive', {
              received_at: fmt.kwIso(at), odometer_km: Math.round(f.km), odometer_photo: up[0], photos: up[1], condition_note: f.cond || null
            });
          });
        }
      });
    },
    inspection: function (r) { status(r, 'inspection', 'بدء الفحص'); },
    in_repair: function (r) { status(r, 'in_repair', 'استئناف الإصلاح'); },
    waiting_parts: function (r) { status(r, 'waiting_parts', 'بانتظار قطع'); },
    quote: function (r) {
      var ed;
      form({
        title: 'عرض السعر', subtitle: r.vehicle.plate_number + ' · ' + M.kind(r.kind), icon: 'file-plus', size: 'lg',
        body: h`${M.itemsHtml}<div class="form mt-16">${BT.f.textarea({ name: 'notes', label: 'ملاحظات (المدة المتوقعة مثلاً)', optional: true, rows: 2 })}
          ${BT.f.upload({ name: 'file', label: 'ملف العرض', optional: true, accept: 'image/*,application/pdf' })}</div>
          <div class="muted fs-sm mt-8">ضمن حد الاعتماد يُعتمد العرض فوراً ويبدأ الإصلاح؛ فوقه ينتظر اعتماد مدير الصيانة.</div>`,
        onOpen: function (dlg) { ed = M.itemsEditor(dlg.body); },
        submitText: 'إرسال العرض', submitIcon: 'send', done: 'أُرسل عرض السعر',
        doneSub: function (res) { return res.status === 'quote_pending' ? 'بانتظار اعتماد مدير الصيانة' : 'ضمن حد الاعتماد: ابدأ الإصلاح'; },
        submit: function (f) {
          if (!ed.valid() || ed.total() <= 0) { BT.toast('أكمل البنود: الوصف والسعر لكل بند', { type: 'error' }); return false; }
          return (f.file && f.file[0] ? upload(f.file[0]) : Promise.resolve(null)).then(function (sha) {
            return api.post('/portal/requests/' + r.id + '/quote', { amount: ed.total().toFixed(3), items: ed.read(), notes: f.notes || null, file_sha256: sha });
          });
        }
      });
    },
    complete: function (r) {
      form({
        title: 'اكتمل الإصلاح', subtitle: r.vehicle.plate_number + ' · طلب #' + r.number, icon: 'circle-check', size: 'lg',
        body: h`<div class="form-grid">${BT.f.textarea({ name: 'details', label: 'ما تم إصلاحه والقطع المستبدلة', required: true, full: true, rows: 3 })}
          ${BT.f.input({ name: 'km', label: 'قراءة العداد النهائية', required: true, num: true, hint: r.received_km != null ? 'عند الوصول: ' + fmt.km(r.received_km) : '' })}
          <div>${BT.f.camera({ name: 'odo', label: 'صورة العداد', required: true, cta: 'صورة العداد', sub: 'إلزامية' })}</div>
          ${BT.f.upload({ name: 'ph', label: 'صور بعد الإصلاح', optional: true, multiple: true, full: true, accept: 'image/*', accept_label: 'صور فقط' })}</div>`,
        submitText: 'حفظ', done: 'سُجّل اكتمال الإصلاح',
        submit: function (f) {
          return Promise.all([upload(f.odo[0]), uploadAll(f.ph)]).then(function (up) {
            return api.post('/portal/requests/' + r.id + '/complete', { repair_details: f.details, final_odometer_km: Math.round(f.km), final_odometer_photo: up[0], photos: up[1] });
          });
        }
      });
    },
    ready: function (r) {
      form({
        title: 'السيارة جاهزة للاستلام', subtitle: r.vehicle.plate_number, icon: 'bell-ring', size: 'sm',
        body: h`<p>تُبلَّغ الإدارة فوراً، ويرى السائق أن سيارته جاهزة في التطبيق.</p><div class="form mt-12">${BT.f.textarea({ name: 'note', label: 'ملاحظة (موعد الاستلام مثلاً)', optional: true, rows: 2 })}</div>`,
        submitText: 'جاهزة', done: 'أُبلغت الإدارة والسائق',
        submit: function (f) { return api.post('/portal/requests/' + r.id + '/ready', { note: f.note || null }); }
      });
    },
    picked: function (r) {
      BT.confirm({ title: 'تأكيد استلام الشركة للسيارة', message: 'سجّل هذا عند خروج السيارة من المركز فعلاً.', confirmText: 'تم الاستلام', icon: 'log-out' }).then(function (c) {
        if (!c.ok) return;
        api.post('/portal/requests/' + r.id + '/picked-up').then(function () { BT.toast('سُجّل خروج السيارة'); P.router.refresh(); refreshCounts(); }, function (err) { BT.toast(api.message(err), { type: 'error' }); });
      });
    },
    invoice: function (r) { invoiceForm(r); }
  };
  function status(r, s, label) {
    form({
      title: label, subtitle: r.vehicle.plate_number + ' · طلب #' + r.number, icon: 'refresh-cw', size: 'sm',
      body: h`<div class="form">${BT.f.textarea({ name: 'note', label: 'ملاحظة للإدارة', optional: true, rows: 2 })}</div>`,
      submitText: 'حفظ', done: 'تم تحديث الحالة',
      submit: function (f) { return api.post('/portal/requests/' + r.id + '/status', { status: s, note: f.note || null }); }
    });
  }
  function invoiceForm(r, choices) {
    var ed, approved = r ? r.quotes.filter(function (q) { return q.status === 'approved'; }).pop() : null;
    form({
      title: 'إدخال الفاتورة', subtitle: r ? r.vehicle.plate_number + ' · طلب #' + r.number + (approved ? ' · العرض المعتمد ' + fmt.money(approved.amount) + ' د.ك' : '') : 'للسيارات التي اكتمل إصلاحها', icon: 'receipt-text', size: 'lg',
      body: h`<div class="form-grid">
        ${r ? '' : BT.f.select({ name: 'req', label: 'الطلب', required: true, full: true, options: choices.map(function (c) { return { v: c.id, t: '#' + c.number + ' · ' + c.vehicle.plate_number + ' · ' + api.t('maintenance_status', c.status) }; }) })}
        ${BT.f.input({ name: 'number', label: 'رقم الفاتورة', required: true })}
        ${BT.f.date({ name: 'date', label: 'تاريخ الفاتورة', required: true, value: BT.config.today, max: BT.config.today })}
        ${BT.f.upload({ name: 'file', label: 'ملف الفاتورة (صورة أو PDF)', required: true, full: true, accept: 'image/*,application/pdf' })}</div>
        <div class="mt-16">${M.itemsHtml}</div><div data-diff></div>
        <div class="form mt-12">${BT.f.textarea({ name: 'notes', label: 'ملاحظات', optional: true, rows: 2 })}</div>`,
      onOpen: function (dlg) {
        ed = M.itemsEditor(dlg.body, function (t) {
          var box = dlg.body.querySelector('[data-diff]');
          if (box) BT.render(box, approved && Math.abs(t - Number(approved.amount)) > 0.0005 ? h`<div class="banner warn mt-8 fs-sm">${icon('triangle-alert', 15)}<div>الإجمالي يختلف عن العرض المعتمد (${fmt.money(approved.amount)} د.ك): سيظهر الفرق للإدارة.</div></div>` : '');
        });
      },
      submitText: 'إرسال للاعتماد المالي', submitIcon: 'send', done: 'أُرسلت الفاتورة للاعتماد المالي',
      submit: function (f) {
        if (!ed.valid() || ed.total() <= 0) { BT.toast('أكمل بنود الفاتورة', { type: 'error' }); return false; }
        return upload(f.file[0]).then(function (sha) {
          return api.post('/portal/invoices', { request_id: r ? r.id : f.req, number: f.number, invoice_date: f.date, total: ed.total().toFixed(3), items: ed.read(), file_sha256: sha, notes: f.notes || null });
        });
      }
    });
  }

  /* ---------- الفواتير ---------- */
  BT.pages['invoices'] = function () {
    setTitle('الفواتير');
    var v = view();
    BT.render(v, h`${head('فواتير المركز', 'تبقى الفاتورة «بانتظار الاعتماد» حتى يراجعها المسؤول المالي مقابل الملف المرفق', h`<button type="button" class="btn btn-primary" data-new>${icon('plus', 15)}إدخال فاتورة</button>`)}<div class="card"><div data-table>${spinner()}</div></div>`);
    api.get('/portal/invoices').then(function (rows) {
      var el = v.querySelector('[data-table]');
      if (!el) return;
      BT.table(el, {
        rows: rows,
        search: { placeholder: 'رقم الفاتورة أو اللوحة…', text: function (i) { return i.number + ' ' + (i.vehicle_plate || ''); } },
        columns: [
          { key: 'number', label: 'الفاتورة', render: function (i) { return h`<span class="num">${i.number}</span><span class="sub">${fmt.date(i.invoice_date)}</span>`; } },
          { key: 'vehicle_plate', label: 'السيارة / الطلب', render: function (i) { return i.request ? h`<span class="plate">${i.vehicle_plate}</span><span class="sub">#${i.request.number}</span>` : '—'; } },
          { key: 'total', label: 'الإجمالي', num: true, render: function (i) { return BT.amt(Number(i.total)); } },
          { key: 'status', label: 'الحالة', render: function (i) { return h`${M.invStatus(i)} ${M.flags(i.flags)}`; } },
          { key: 'file', label: '', sort: false, render: function (i) { return h`<a href="${api.url('/portal/invoices/' + i.id + '/file')}" target="_blank" rel="noopener">${icon('file-text', 14)} الملف</a>`; } }
        ],
        rowClick: function (i) { if (i.request) P.router.go('r/' + i.request.id); },
        empty: { icon: 'receipt-text', title: 'لا توجد فواتير بعد' }
      });
    }, function (err) { var el = v.querySelector('[data-table]'); if (el) BT.render(el, errorBox(err)); });
    v.querySelector('[data-new]').onclick = function () {
      Promise.all([api.get('/portal/requests'), api.get('/portal/requests', { active: false }), api.get('/portal/invoices')]).then(function (res) {
        var invoiced = {};
        res[2].forEach(function (i) { if (i.request && i.status !== 'rejected') invoiced[i.request.id] = true; });
        var choices = res[0].concat(res[1]).filter(function (r) { return ['completed', 'ready', 'picked_up'].indexOf(r.status) > -1 && !invoiced[r.id]; });
        if (!choices.length) { BT.toast('لا توجد طلبات مكتملة بلا فاتورة', { type: 'info' }); return; }
        invoiceForm(null, choices);
      }, api.fail);
    };
  };

  /* ---------- المستخدم ---------- */
  BT.actions['user-menu'] = function (arg, el) {
    var dark = BT.theme.get() === 'dark';
    BT.menu(el, [
      { head: api.me.full_name + ' · ' + api.me.username },
      { label: 'تغيير كلمة المرور', icon: 'key-round', onClick: function () { changePassword(false); } },
      { label: dark ? 'الوضع الفاتح' : 'الوضع الداكن', icon: dark ? 'sun' : 'moon', onClick: function () { BT.theme.toggle(); } },
      { sep: true },
      { label: 'تسجيل الخروج', icon: 'log-out', danger: true, onClick: logout }
    ], { focus: true });
  };
  BT.actions['toggle-nav'] = function () { document.getElementById('app').classList.toggle('nav-open'); };
  BT.actions['theme'] = function () { BT.theme.toggle(); };
  function logout() { api.post('/auth/logout').then(null, function () {}).then(function () { location.href = 'login.html'; }); }
  function changePassword(forced) {
    return BT.modal.open({
      title: forced ? 'غيّر كلمة المرور للمتابعة' : 'تغيير كلمة المرور', icon: 'key-round', size: 'sm', form: true, dismissible: !forced,
      subtitle: forced ? 'كلمة المرور الحالية مؤقتة، اختر كلمة مرور جديدة خاصة بك' : null,
      body: h`<div class="form">${BT.f.input({ name: 'old', label: 'كلمة المرور الحالية', type: 'password', required: true })}
        ${BT.f.input({ name: 'pw', label: 'كلمة المرور الجديدة', type: 'password', required: true })}
        ${BT.f.input({ name: 'pw2', label: 'تأكيد كلمة المرور', type: 'password', required: true, validate: 'samePw' })}</div>`,
      buttons: forced ? [{ label: 'تسجيل الخروج', cls: 'btn-ghost', onClick: function () { logout(); return false; } }, { label: 'حفظ', cls: 'btn-primary', submit: true }] : [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ', cls: 'btn-primary', submit: true }],
      onSubmit: function (v) {
        return api.post('/auth/password', { current_password: v.old, new_password: v.pw }).then(function () { api.me.must_change_password = false; BT.toast('تم تغيير كلمة المرور'); }).catch(api.fail);
      }
    }).promise;
  }
  BT.validators.samePw = function (v, el, f) { return v === f.querySelector('[name=pw]').value ? '' : 'كلمتا المرور غير متطابقتين'; };

  /* ---------- التشغيل ---------- */
  function boot() {
    BT.hydrate(document);
    BT.render(view(), spinner());
    api.get('/auth/me').then(function (me) {
      api.me = me; api.csrf = me.csrf_token;
      if (!api.isCenterAccount(me)) { location.replace('admin.html'); return null; } // حساب إدارة (ومنه مدير النظام) لا حساب مركز
      return Promise.all([
        api.loadCatalog(me.locale || 'ar').catch(function () { return api.loadCatalog('ar'); }),
        api.get('/portal/me').then(function (c) { P.center = c; })
      ]);
    }).then(function (ok) {
      if (!ok) return;
      document.querySelectorAll('[data-center-name]').forEach(function (e) { e.textContent = P.center.name; });
      document.querySelectorAll('[data-me-name]').forEach(function (e) { e.textContent = api.me.full_name; });
      document.querySelectorAll('[data-me-av]').forEach(function (e) { e.textContent = fmt.initials(api.me.full_name); });
      api.get('/branding', null, { noRedirect: true }).then(function (b) { document.querySelectorAll('[data-brand]').forEach(function (e) { e.textContent = 'محالة من ' + b.display_name; }); }, function () {});
      P.router = BT.router(BT.pages, {
        default: 'requests', view: view,
        onBefore: function (r) {
          BT.closeAll(); BT.closeMenu();
          var old = view(), fresh = old.cloneNode(false); old.replaceWith(fresh);
          document.getElementById('app').classList.remove('nav-open');
          renderNav(navKey(r.current));
          window.scrollTo(0, 0);
        }
      });
      document.querySelector('.sb-backdrop').addEventListener('click', function () { document.getElementById('app').classList.remove('nav-open'); });
      var start = function () { P.router.start(); refreshCounts(); setInterval(function () { if (!document.hidden) refreshCounts(); }, 60000); };
      if (api.me.must_change_password) changePassword(true).then(start); else start();
    }, function (err) {
      if (err instanceof api.ApiError && err.status === 401) return;
      BT.render(view(), errorBox(err));
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else setTimeout(boot, 0);
})();
