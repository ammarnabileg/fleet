/* =====================================================================
   app/pages/maintenance.js — الصيانة: الطلبات والاعتماد والإحالة، عروض السعر،
   فواتير المراكز واعتمادها ودفعها، ومراكز الصيانة وحسابات بوابتها.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A, M = BT.mnt;

  var GROUPS = {
    pending: 'requested,quote_pending',
    approved: 'approved',
    at_center: 'referred,received,inspection,in_repair,waiting_parts,completed',
    ready: 'ready',
    done: 'picked_up,closed',
    stopped: 'rejected,cancelled'
  };
  function fileUrl(id) { return function (sha) { return api.url('/maintenance/requests/' + id + '/files/' + sha); }; }
  function upload(file) { return api.upload(file).then(function (f) { return f.sha256; }); }
  function uploadAll(files) { return Promise.all(Array.prototype.map.call(files || [], upload)); }
  function refreshAll() { A.refreshIfAt('maintenance'); A.refreshCounts(); }

  /* ================= الصفحة: الطلبات · الفواتير · المراكز ================= */
  BT.pages['maintenance'] = function (p, q) {
    A.setTitle('الصيانة');
    var v = A.view(), tabs = [];
    if (api.can('maintenance.view')) tabs.push(['requests', 'طلبات الصيانة']);
    if (api.can('invoices.view')) tabs.push(['invoices', 'الفواتير']);
    if (api.can('maintenance.view')) tabs.push(['centers', 'مراكز الصيانة']);
    var tab = tabs.some(function (t) { return t[0] === q.tab; }) ? q.tab : tabs[0][0];
    BT.render(v, h`${A.head('الصيانة ومراكزها', 'كل طلب يمر بالاعتماد ثم الإحالة لمركز يحدّث حالته من بوابته؛ مدة البقاء والفواتير تُتابع هنا', h`${api.can('maintenance.create') ? A.btn('طلب صيانة', { icon: 'plus', cls: 'btn-primary', action: 'mnt-new' }) : ''}${api.can('invoices.create') ? A.btn('فاتورة من مركز', { icon: 'receipt-text', cls: 'btn-outline', action: 'mnt-invoice' }) : ''}`)}
      ${tabs.length > 1 ? BT.tabs('mnt', tabs, tab, 'tabs-line') : ''}
      ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="mnt" class="${t[0] === tab ? 'active' : ''}"><div data-p="${t[0]}"></div></div>`; })}`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      var el = v.querySelector('[data-p="' + t + '"]');
      ({ requests: requestsPanel, invoices: invoicesPanel, centers: centersPanel })[t](el, q);
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); });
    show(tab);
  };
  BT.actions['mnt-new'] = function () { newRequest(); };
  BT.actions['mnt-invoice'] = function () { officeInvoice(); };

  function requestsPanel(el, q) {
    BT.render(el, h`<div class="card"><div data-t></div></div>`);
    BT.table(el.querySelector('[data-t]'), {
      fetch: function (s) { return api.get('/maintenance/requests', { status: GROUPS[s.chip] || null, active: s.chip ? null : true, limit: s.limit, offset: s.offset }); },
      chips: { value: q.status || 'pending', all: 'المفتوحة', options: [
        { v: 'pending', t: 'بانتظار القرار' }, { v: 'approved', t: 'معتمدة للإحالة' }, { v: 'at_center', t: 'في المركز' },
        { v: 'ready', t: 'جاهزة للاستلام' }, { v: 'done', t: 'المستلمة' }, { v: 'stopped', t: 'المرفوضة والملغاة' }
      ] },
      columns: [
        { key: 'number', label: 'الطلب', render: function (r) { return h`<span class="num">#${r.number}</span><span class="sub">${M.kind(r.kind)}${r.emergency ? ' · طارئة' : ''}</span>`; } },
        { key: 'vehicle', label: 'السيارة', render: function (r) { return M.vehicle(r.vehicle); } },
        { key: 'driver', label: 'السائق', render: function (r) { return r.driver ? A.person(r.driver) : raw('<span class="muted">—</span>'); } },
        { key: 'status', label: 'الحالة', render: function (r) { return h`${M.status(r.status)}${r.emergency && !r.emergency_reviewed ? h` ${BT.pill('تحتاج مراجعة', 'o')}` : ''}`; } },
        { key: 'center', label: 'المركز', render: function (r) { return r.center ? r.center.name : raw('<span class="muted">—</span>'); } },
        { key: 'stay', label: 'المدة', render: function (r) { return r.stay_seconds != null ? M.dur(r.stay_seconds) : h`<span class="muted">${fmt.since(r.created_at)}</span>`; } }
      ],
      rowClick: function (r) { A.go('maintenance/' + r.id); },
      empty: { icon: 'wrench', title: 'لا توجد طلبات هنا' }
    });
  }

  /* كل السيارات ضمن النطاق، 200 في كل طلب (حد الخادم للصفحة) */
  function allVehicles(offset, acc) {
    offset = offset || 0; acc = acc || [];
    return api.get('/vehicles', { limit: 200, offset: offset }).then(function (rows) {
      acc = acc.concat(rows);
      return rows.length === 200 && acc.length < 5000 ? allVehicles(offset + 200, acc) : acc;
    });
  }

  /* ---------- طلب جديد من الإدارة ---------- */
  function newRequest(vehicle) {
    var jobs = [vehicle ? Promise.resolve([vehicle]) : allVehicles()];
    Promise.all(jobs).then(function (res) {
      var vehicles = res[0];
      A.formModal({
        title: 'طلب صيانة', icon: 'wrench', size: 'lg',
        body: h`<div class="form-grid">
          <div class="full">${A.picker({ name: 'vehicle', label: 'السيارة', required: true, items: vehicles.map(function (x) { return { id: x.id, label: A.vehicleLabel(x) }; }), value: vehicle && vehicle.id })}</div>
          ${BT.f.select({ name: 'kind', label: 'النوع', required: true, options: M.kindOptions() })}
          ${BT.f.input({ name: 'km', label: 'قراءة العداد', optional: true, num: true })}
          ${BT.f.textarea({ name: 'desc', label: 'الوصف', required: true, full: true, rows: 3 })}
          ${BT.f.upload({ name: 'ph', label: 'صور', optional: true, multiple: true, full: true, accept: 'image/*', accept_label: 'صور فقط' })}
          <div class="full">${BT.f.switch({ name: 'emergency', label: 'صيانة طارئة: تُعتمد الآن وتُراجع لاحقاً' })}</div></div>`,
        submitText: 'إنشاء الطلب', done: 'أُنشئ طلب الصيانة',
        submit: function (f, dlg) {
          var vid = A.picked('vehicle', f.vehicle);
          var emergency = dlg.form.querySelector('[name=emergency]').checked;
          return uploadAll(f.ph).then(function (photos) {
            return api.post('/maintenance/requests', { vehicle_id: vid, kind: f.kind, description: f.desc, odometer_km: f.km === '' || f.km == null ? null : Math.round(f.km), emergency: emergency, photos: photos });
          });
        },
        after: function (r) { A.go('maintenance/' + r.id); A.refreshCounts(); }
      });
    }, api.fail).catch(function () {});
  }
  A.maintenanceRequest = newRequest;

  /* ================= طلب واحد ================= */
  BT.pages['maintenance/:id'] = function (p) {
    A.setTitle('طلب صيانة', [['الصيانة', 'maintenance'], ['طلب']]);
    var v = A.view();
    A.load(v, api.get('/maintenance/requests/' + p.id), function (r) {
      A.setTitle('طلب #' + r.number, [['الصيانة', 'maintenance'], ['#' + r.number]]);
      var acts = [], s = r.status;
      if (s === 'requested' && api.can('maintenance.approve')) { acts.push(A.btn('رفض', { icon: 'x', cls: 'btn-ghost', action: 'mnt-reject' })); acts.push(A.btn('اعتماد', { icon: 'check', cls: 'btn-primary', action: 'mnt-approve' })); }
      if ((s === 'approved' || s === 'referred') && api.can('maintenance.approve')) acts.push(A.btn(s === 'referred' ? 'تغيير المركز' : 'إحالة لمركز', { icon: 'send', cls: s === 'approved' ? 'btn-primary' : 'btn-outline', action: 'mnt-refer' }));
      if (r.emergency && !r.emergency_reviewed && api.can('maintenance.approve')) acts.push(A.btn('مراجعة الطارئة', { icon: 'shield-check', cls: 'btn-outline', action: 'mnt-review' }));
      if (['requested', 'approved', 'referred'].indexOf(s) > -1 && api.can('maintenance.create')) acts.push(A.btn('إلغاء', { icon: 'ban', cls: 'btn-ghost', action: 'mnt-cancel' }));
      if (s === 'ready' && api.can('maintenance.create')) acts.push(A.btn('تم استلام السيارة', { icon: 'log-out', cls: 'btn-primary', action: 'mnt-picked' }));
      A._mnt = r;
      return h`${A.head(h`${M.vehicleLine(r.vehicle)} · طلب <span class="num">#${r.number}</span>`, h`${M.status(r.status)} · ${M.kind(r.kind)} · ${api.company(r.company_id)}`, acts)}
        ${M.detail(r, fileUrl(r.id), {
          admin: true,
          quoteActions: function (qt) {
            if (qt.status !== 'pending' || !api.can('maintenance.approve')) return '';
            return h`<div class="flex gap-8 mt-8"><button type="button" class="btn btn-sm btn-primary" data-q-ok="${qt.id}">${icon('check', 14)} اعتماد العرض</button><button type="button" class="btn btn-sm btn-ghost" data-q-no="${qt.id}">${icon('x', 14)} رفض</button></div>`;
          }
        })}
        ${r.invoices.some(function (i) { return i.status === 'pending'; }) && api.can('invoices.approve') ? h`<div class="banner info mt-16">${icon('receipt-text', 16)}<div>فاتورة بانتظار الاعتماد: راجعها مقابل الملف في <a href="#/maintenance?tab=invoices">تبويب الفواتير</a>.</div></div>` : ''}`;
    }).then(function () {
      BT.on(v, 'click', '[data-q-ok]', function (e, b) {
        A.confirmRun({ title: 'اعتماد عرض السعر', message: 'يبدأ المركز الإصلاح بعد الاعتماد.', confirmText: 'اعتماد', run: function () { return api.post('/maintenance/quotes/' + b.getAttribute('data-q-ok') + '/approve'); }, done: 'اعتُمد العرض', after: refreshAll });
      });
      BT.on(v, 'click', '[data-q-no]', function (e, b) {
        A.confirmRun({ title: 'رفض عرض السعر', message: 'يعود الطلب للمركز ليرسل عرضاً جديداً.', tone: 'danger', confirmText: 'رفض', reason: { label: 'السبب (يراه المركز)', required: true }, run: function (reason) { return api.post('/maintenance/quotes/' + b.getAttribute('data-q-no') + '/reject', { reason: reason }); }, done: 'رُفض العرض', after: refreshAll });
      });
    }).catch(function () {});
  };
  function req() { return A._mnt; }
  BT.actions['mnt-approve'] = function () {
    A.formModal({ title: 'اعتماد طلب الصيانة', icon: 'check', size: 'sm', body: h`<div class="form">${BT.f.textarea({ name: 'note', label: 'ملاحظة', optional: true, rows: 2 })}</div>`, submitText: 'اعتماد', done: 'اعتُمد الطلب',
      submit: function (f) { return api.post('/maintenance/requests/' + req().id + '/approve', { note: f.note || null }); }, after: refreshAll });
  };
  BT.actions['mnt-reject'] = function () {
    A.confirmRun({ title: 'رفض طلب الصيانة', tone: 'danger', confirmText: 'رفض', reason: { label: 'السبب (يراه السائق)', required: true }, run: function (reason) { return api.post('/maintenance/requests/' + req().id + '/reject', { reason: reason }); }, done: 'رُفض الطلب', after: refreshAll });
  };
  BT.actions['mnt-cancel'] = function () {
    A.confirmRun({ title: 'إلغاء طلب الصيانة', tone: 'danger', confirmText: 'إلغاء الطلب', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/maintenance/requests/' + req().id + '/cancel', { reason: reason }); }, done: 'أُلغي الطلب', after: refreshAll });
  };
  BT.actions['mnt-review'] = function () {
    A.formModal({ title: 'مراجعة الصيانة الطارئة', icon: 'shield-check', size: 'sm', body: h`<div class="form">${BT.f.textarea({ name: 'note', label: 'ملاحظة المراجعة', optional: true, rows: 2 })}</div>`, submitText: 'تمت المراجعة', done: 'سُجّلت المراجعة',
      submit: function (f) { return api.post('/maintenance/requests/' + req().id + '/review-emergency', { note: f.note || null }); }, after: refreshAll });
  };
  BT.actions['mnt-picked'] = function () {
    A.confirmRun({ title: 'استلام السيارة من المركز', message: 'تعود السيارة «متاحة» للتسليم لسائق.', confirmText: 'تم الاستلام', run: function () { return api.post('/maintenance/requests/' + req().id + '/picked-up'); }, done: 'سُجّل الاستلام', after: refreshAll });
  };
  BT.actions['mnt-refer'] = function () {
    api.get('/maintenance/centers', { active: true }).then(function (centers) {
      if (!centers.length) { BT.toast('أضف مركز صيانة أولاً من تبويب المراكز', { type: 'warning' }); return; }
      A.formModal({
        title: 'إحالة لمركز صيانة', subtitle: req().vehicle.plate_number + ' · طلب #' + req().number, icon: 'send',
        body: h`<div class="form">${BT.f.select({ name: 'center', label: 'المركز', required: true, value: req().center && req().center.id, options: centers.map(function (c) { return { v: c.id, t: c.name + (c.specialty ? ' — ' + c.specialty : '') + (c.at_center ? ' · لديه ' + c.at_center : '') }; }) })}
          ${BT.f.textarea({ name: 'note', label: 'ملاحظة للمركز', optional: true, rows: 2 })}<div class="hint">يظهر الطلب فوراً في بوابة المركز.</div></div>`,
        submitText: 'إحالة', done: 'أُحيل الطلب للمركز',
        submit: function (f) { return api.post('/maintenance/requests/' + req().id + '/refer', { center_id: f.center, note: f.note || null }); }, after: refreshAll
      });
    }, api.fail).catch(function () {});
  };

  /* ================= الفواتير ================= */
  var INV_CHIPS = { pending: { status: 'pending' }, unpaid: { status: 'approved', payment_status: 'unpaid' }, paid: { payment_status: 'paid' }, rejected: { status: 'rejected' } };
  function invoicesPanel(el) {
    BT.render(el, h`<div class="card"><div data-t></div></div>`);
    var t = BT.table(el.querySelector('[data-t]'), {
      fetch: function (s) { return api.get('/maintenance/invoices', Object.assign({ limit: s.limit, offset: s.offset }, INV_CHIPS[s.chip] || {})); },
      chips: { value: 'pending', all: 'الكل', options: [{ v: 'pending', t: 'بانتظار الاعتماد' }, { v: 'unpaid', t: 'معتمدة غير مدفوعة' }, { v: 'paid', t: 'مدفوعة' }, { v: 'rejected', t: 'مرفوضة' }] },
      columns: [
        { key: 'number', label: 'الفاتورة', render: function (i) { return h`<span class="num">${i.number}</span><span class="sub">${fmt.date(i.invoice_date)}</span>`; } },
        { key: 'center', label: 'المركز', render: function (i) { return i.center.name; } },
        { key: 'request', label: 'السيارة / الطلب', render: function (i) { return i.request ? h`<a href="#/maintenance/${i.request.id}"><span class="plate">${i.vehicle_plate}</span> <span class="num">#${i.request.number}</span></a>` : h`<span class="muted">${api.company(i.company_id)}</span>`; } },
        { key: 'total', label: 'الإجمالي', num: true, render: function (i) { return h`${BT.amt(Number(i.total))}${i.quote_amount != null ? h`<span class="sub">العرض ${fmt.money(i.quote_amount)}</span>` : ''}`; } },
        { key: 'status', label: 'الحالة', render: function (i) { return h`${M.invStatus(i)} ${M.flags(i.flags)}`; } }
      ],
      rowClick: function (i) { invoiceView(i, function () { t.refresh(); A.refreshCounts(); }); },
      empty: { icon: 'receipt-text', title: 'لا توجد فواتير هنا' }
    });
  }
  function invoiceView(i, done) {
    var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
    if (i.status === 'pending' && api.can('invoices.approve')) {
      btns.push({ label: 'رفض', cls: 'btn-ghost', icon: 'x', close: false, onClick: function (dlg) {
        A.confirmRun({ title: 'رفض الفاتورة', tone: 'danger', confirmText: 'رفض', reason: { label: 'السبب (يراه المركز)', required: true }, run: function (reason) { return api.post('/maintenance/invoices/' + i.id + '/reject', { reason: reason }); }, done: 'رُفضت الفاتورة', after: function () { dlg.close(); done(); } });
      } });
      btns.push({ label: 'اعتماد', cls: 'btn-primary', icon: 'check', close: false, onClick: function (dlg) {
        A.confirmRun({ title: 'اعتماد الفاتورة', message: 'راجعت البيانات المدخلة مقابل الملف المرفق؟', confirmText: 'اعتماد', run: function () { return api.post('/maintenance/invoices/' + i.id + '/approve'); }, done: 'اعتُمدت الفاتورة', after: function () { dlg.close(); done(); } });
      } });
    }
    if (i.status === 'approved' && i.payment_status === 'unpaid' && api.can('finance.create')) {
      btns.push({ label: 'تسجيل الدفع', cls: 'btn-primary', icon: 'banknote', close: false, onClick: function (dlg) {
        A.formModal({ title: 'تسجيل دفع الفاتورة', icon: 'banknote', size: 'sm', body: h`<div class="form">${BT.f.input({ name: 'ref', label: 'مرجع الدفع (تحويل أو شيك)', optional: true })}</div>`, submitText: 'تم الدفع', done: 'سُجّل الدفع',
          submit: function (f) { return api.post('/maintenance/invoices/' + i.id + '/paid', { payment_ref: f.ref || null }); }, after: function () { dlg.close(); done(); } });
      } });
    }
    BT.drawer.open({
      title: h`فاتورة <span class="num">${i.number}</span> · ${i.center.name}`, subtitle: fmt.date(i.invoice_date) + (i.vehicle_plate ? ' · ' + i.vehicle_plate : ''), icon: 'receipt-text', size: 'lg',
      body: h`<div class="mb-12">${M.invStatus(i)} ${M.flags(i.flags)}</div>
        ${i.flags.indexOf('differs_from_quote') > -1 ? h`<div class="banner warn mb-12">${icon('triangle-alert', 16)}<div>الإجمالي ${fmt.money(i.total)} يختلف عن العرض المعتمد ${fmt.money(i.quote_amount)} د.ك.</div></div>` : ''}
        ${i.flags.indexOf('duplicate_number') > -1 ? h`<div class="banner warn mb-12">${icon('copy', 16)}<div>رقم الفاتورة مسجّل من قبل لنفس المركز: تأكد أنها ليست مكررة.</div></div>` : ''}
        ${BT.kv([['الإجمالي', BT.amt(Number(i.total)), 'total'], ['الشركة', api.company(i.company_id)], ['أدخلها', i.created_by || '—'], i.decided_by ? ['قرار', i.decided_by + ' · ' + fmt.dt(i.decided_at)] : null, i.reason ? ['السبب', i.reason] : null, i.paid_at ? ['الدفع', fmt.dt(i.paid_at) + (i.payment_ref ? ' · ' + i.payment_ref : '')] : null].filter(Boolean))}
        <div class="section-t mt-16">البنود</div>${M.itemsTable(i.items)}
        <div class="mt-16"><a class="btn btn-outline" href="${api.url('/maintenance/invoices/' + i.id + '/file')}" target="_blank" rel="noopener">${icon('file-text', 15)} فتح ملف الفاتورة</a></div>`,
      buttons: btns
    });
  }

  /* ---------- فاتورة يدخلها المحاسب لمركز (بلا طلب في النظام) ---------- */
  function officeInvoice() {
    api.get('/maintenance/centers').then(function (centers) {
      if (!centers.length) { BT.toast('أضف مركز صيانة أولاً', { type: 'warning' }); return; }
      var ed;
      A.formModal({
        title: 'فاتورة من مركز صيانة', subtitle: 'لفواتير المراكز غير المرتبطة بطلب في النظام؛ فواتير الطلبات يدخلها المركز من بوابته', icon: 'receipt-text', size: 'lg',
        body: h`<div class="form-grid">${BT.f.select({ name: 'center', label: 'المركز', required: true, options: centers.map(function (c) { return { v: c.id, t: c.name }; }) })}
          ${BT.f.select({ name: 'company', label: 'الشركة', required: true, options: api.companyOptions() })}
          ${BT.f.input({ name: 'number', label: 'رقم الفاتورة', required: true })}${BT.f.date({ name: 'date', label: 'التاريخ', required: true, value: BT.config.today, max: BT.config.today })}
          ${BT.f.upload({ name: 'file', label: 'ملف الفاتورة', required: true, full: true })}</div><div class="mt-16">${M.itemsHtml}</div>
          <div class="form mt-12">${BT.f.textarea({ name: 'notes', label: 'ملاحظات', optional: true, rows: 2 })}</div>`,
        onOpen: function (dlg) { ed = M.itemsEditor(dlg.body); },
        submitText: 'حفظ', done: 'سُجّلت الفاتورة بانتظار الاعتماد',
        submit: function (f) {
          if (!ed.valid() || ed.total() <= 0) { BT.toast('أكمل بنود الفاتورة', { type: 'error' }); return false; }
          return upload(f.file[0]).then(function (sha) {
            return api.post('/maintenance/invoices', { center_id: f.center, company_id: Number(f.company), number: f.number, invoice_date: f.date, total: ed.total().toFixed(3), items: ed.read(), file_sha256: sha, notes: f.notes || null });
          });
        },
        after: function () { A.go('maintenance?tab=invoices'); A.refreshCounts(); }
      });
    }, api.fail).catch(function () {});
  }

  /* ================= المراكز وحسابات البوابة ================= */
  function centersPanel(el) {
    A.load(el, api.get('/maintenance/centers'), function (rows) {
      setTimeout(function () {
        var t = el.querySelector('[data-t]');
        if (!t) return;
        BT.table(t, {
          rows: rows,
          search: { placeholder: 'اسم المركز…', text: function (c) { return c.name + ' ' + (c.specialty || ''); } },
          columns: [
            { key: 'name', label: 'المركز', render: function (c) { return h`<b>${c.name}</b><span class="sub">${c.specialty || ''}</span>`; } },
            { key: 'phone', label: 'التواصل', render: function (c) { return h`${c.contact_name || ''}<span class="sub ltr">${c.phone || ''}</span>`; } },
            { key: 'at_center', label: 'سيارات لديه', num: true },
            { key: 'users', label: 'حسابات البوابة', num: true },
            { key: 'is_active', label: 'الحالة', render: function (c) { return c.is_active ? BT.pill('نشط', 'g') : BT.pill('موقوف', 'n'); } }
          ],
          rowClick: function (c) { centerView(c); },
          tools: api.can('maintenance_centers.manage') ? A.btn('إضافة مركز', { icon: 'plus', cls: 'btn-primary', action: 'mnt-center-new' }) : '',
          empty: { icon: 'store', title: 'لا توجد مراكز صيانة', text: 'أضف المراكز التي تتعامل معها، ثم أنشئ لكل مركز حساباً لبوابته' }
        });
      });
      return h`<div class="card"><div data-t></div></div>`;
    }).catch(function () {});
  }
  BT.actions['mnt-center-new'] = function () { centerForm(null); };
  function centerForm(c) {
    A.formModal({
      title: c ? 'تعديل مركز صيانة' : 'إضافة مركز صيانة', icon: 'store',
      body: h`<div class="form-grid">${BT.f.input({ name: 'name', label: 'الاسم', required: true, value: c && c.name })}${BT.f.input({ name: 'specialty', label: 'التخصص', optional: true, value: c && c.specialty, placeholder: 'ميكانيكا، كهرباء، سمكرة…' })}
        ${BT.f.input({ name: 'contact_name', label: 'جهة الاتصال', optional: true, value: c && c.contact_name })}${BT.f.input({ name: 'phone', label: 'الهاتف', optional: true, value: c && c.phone })}
        ${BT.f.input({ name: 'email', label: 'البريد', optional: true, value: c && c.email })}${BT.f.input({ name: 'address', label: 'العنوان', optional: true, value: c && c.address })}
        ${BT.f.textarea({ name: 'notes', label: 'ملاحظات', optional: true, full: true, rows: 2, value: c && c.notes })}
        ${c ? h`<div class="full">${BT.f.switch({ name: 'is_active', label: 'نشط (الموقوف لا يستقبل إحالات وتتوقف حساباته)', checked: c.is_active })}</div>` : ''}</div>`,
      submitText: 'حفظ', done: 'تم الحفظ',
      submit: function (f, dlg) {
        var body = { name: f.name, specialty: f.specialty || null, contact_name: f.contact_name || null, phone: f.phone || null, email: f.email || null, address: f.address || null, notes: f.notes || null };
        if (!c) return api.post('/maintenance/centers', body);
        body.version = c.version; body.is_active = dlg.form.querySelector('[name=is_active]').checked;
        return api.put('/maintenance/centers/' + c.id, body);
      },
      after: function () { BT.closeAll(); A.go('maintenance?tab=centers'); A.router.refresh(); }
    });
  }
  function centerView(c) {
    var manage = api.can('maintenance_centers.manage');
    var d = BT.drawer.open({
      title: c.name, subtitle: c.specialty || '', icon: 'store', size: 'lg',
      body: h`${BT.kv([['جهة الاتصال', c.contact_name || '—'], ['الهاتف', c.phone ? h`<span class="ltr">${c.phone}</span>` : '—'], ['البريد', c.email || '—'], ['العنوان', c.address || '—'], ['سيارات لديه الآن', String(c.at_center)], ['الحالة', c.is_active ? 'نشط' : 'موقوف']])}
        ${c.notes ? h`<div class="fs-sm mt-12" style="white-space:pre-wrap">${c.notes}</div>` : ''}
        <div class="between mt-16 mb-8"><div class="section-t" style="margin:0">حسابات البوابة</div>${manage ? h`<button type="button" class="btn btn-sm btn-soft" data-user-add>${icon('user-plus', 14)} إضافة حساب</button>` : ''}</div>
        <div data-users>${A.spinner()}</div>
        <div class="hint mt-8">حساب المركز يرى فقط السيارات المحالة لمركزه، ويدخل من صفحة الدخول نفسها.</div>`,
      buttons: [{ label: 'إغلاق', cls: 'btn-ghost' }].concat(manage ? [{ label: 'تعديل', cls: 'btn-outline', icon: 'pencil', close: false, onClick: function () { centerForm(c); } }] : [])
    });
    function loadUsers() {
      var box = d.el.querySelector('[data-users]');
      if (!api.can('maintenance_centers.view')) { BT.render(box, raw('<div class="muted fs-sm">يحتاج صلاحية عرض المراكز</div>')); return; }
      api.get('/maintenance/centers/' + c.id + '/users').then(function (users) { drawUsers(users); }, function (err) { BT.render(box, BT.empty('wifi-off', api.message(err))); });
    }
    function drawUsers(users) {
      var box = d.el.querySelector('[data-users]');
      BT.render(box, users.length ? h`<div class="list">${users.map(function (u) {
        return h`<div class="li"><span class="li-ic ${u.is_active ? 'g' : ''}">${icon('user-round', 16)}</span><div class="li-main"><div class="li-t">${u.full_name} <span class="muted fs-sm ltr">${u.username}</span></div><div class="li-d">${u.last_login_at ? 'آخر دخول ' + fmt.since(u.last_login_at) : 'لم يدخل بعد'}</div></div>${u.is_active ? '' : BT.pill('موقوف', 'n')}${manage ? h`<button type="button" class="btn btn-sm btn-ghost" data-user-toggle="${u.id}" data-on="${u.is_active ? '0' : '1'}">${u.is_active ? 'إيقاف' : 'تفعيل'}</button>` : ''}</div>`;
      })}</div>` : BT.empty('users', 'لا توجد حسابات', 'أنشئ حساباً ليستلم المركز السيارات ويحدّث حالتها'));
    }
    loadUsers();
    BT.on(d.el, 'click', '[data-user-toggle]', function (e, b) {
      b.disabled = true;
      api.put('/maintenance/centers/' + c.id + '/users/' + b.getAttribute('data-user-toggle'), { is_active: b.getAttribute('data-on') === '1' }).then(drawUsers, function (err) { b.disabled = false; BT.toast(api.message(err), { type: 'error' }); });
    });
    BT.on(d.el, 'click', '[data-user-add]', function () {
      A.formModal({
        title: 'حساب بوابة لـ ' + c.name, icon: 'user-plus', size: 'sm',
        body: h`<div class="form">${BT.f.input({ name: 'full_name', label: 'الاسم', required: true })}${BT.f.input({ name: 'username', label: 'اسم المستخدم', required: true })}
          ${BT.f.input({ name: 'phone', label: 'الجوال', optional: true })}${BT.f.input({ name: 'password', label: 'كلمة مرور مؤقتة', type: 'password', required: true, hint: 'يُطلب تغييرها عند أول دخول' })}</div>`,
        submitText: 'إنشاء الحساب', done: 'أُنشئ الحساب',
        submit: function (f) { return api.post('/maintenance/centers/' + c.id + '/users', { full_name: f.full_name, username: f.username, phone: f.phone || null, password: f.password }); },
        after: drawUsers
      });
    });
  }

  /* ---------- تبويب الصيانة في ملف السيارة ---------- */
  A.vehicleMaintenance = function (el, vehicle) {
    A.load(el, api.get('/maintenance/requests', { vehicle_id: vehicle.id, limit: 20 }), function (rows) {
      return h`${rows.length ? h`<div class="list">${rows.map(function (r) {
        return h`<a class="li" href="#/maintenance/${r.id}"><span class="li-ic">${icon('wrench', 16)}</span><div class="li-main"><div class="li-t"><span class="num">#${r.number}</span> ${M.kind(r.kind)}${r.center ? ' · ' + r.center.name : ''}</div><div class="li-d">${fmt.dt(r.created_at)}${r.stay_seconds != null ? ' · بقيت ' + M.dur(r.stay_seconds) : ''}</div></div>${M.status(r.status)}</a>`;
      })}</div>` : BT.empty('wrench', 'لا توجد طلبات صيانة', '')}
        ${api.can('maintenance.create') ? h`<div class="mt-12"><button type="button" class="btn btn-sm btn-soft" data-mnt-new>${icon('plus', 14)} طلب صيانة</button></div>` : ''}`;
    }).then(function () {
      var b = el.querySelector('[data-mnt-new]');
      if (b) b.onclick = function () { newRequest(vehicle); };
    }).catch(function () {});
  };
})();
