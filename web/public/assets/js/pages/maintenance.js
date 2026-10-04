/* =====================================================================
   صفحات: الصيانة · الحوادث · ملف الحادث
   بوب أب: طلب صيانة جديد · تفاصيل طلب الصيانة (drawer) · اعتماد عرض السعر ·
   مراجعة الفاتورة · رسالة للمركز · استلام السيارة من المركز (confirm) ·
   تسجيل حادث · إرفاق تقرير الشرطة · إحالة لمركز · اعتماد التقدير ·
   تحديد المسؤولية وخطة الخصم بالأقساط · صور الحادث (lightbox)
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, D = BT.data, A = BT.A;
  var cfg = BT.config;

  /* =================================================================
     الصيانة  #/maintenance
     ================================================================= */
  BT.pages['maintenance'] = function (p, q) {
    A.setTitle('الصيانة');
    var open = D.jobs.filter(function (j) { return j.stage !== 'تم الاستلام'; });
    var cs = D.centerStats(), visits = BT.sum(cs, function (c) { return c.visits; });
    var avg = BT.sum(cs, function (c) { return c.avgDays * c.visits; }) / visits;
    var stage = q.stage || '';
    BT.render(A.view(), h`
      ${A.head('الصيانة', 'مركز الصيانة يحدّث الحالة من بوابته، والإدارة تتابع وتعتمد',
        h`<a class="btn btn-outline" href="portal.html">${icon('store', 15)} بوابة المراكز</a>${A.btn('طلب صيانة', { icon: 'plus', cls: 'btn-primary', action: 'maint-new' })}`)}
      <div class="kpis">
        ${BT.kpi({ label: 'سيارات في الصيانة', value: String(open.length), sub: 'لدى ' + D.centers.length + ' مراكز', dot: 'b' })}
        ${BT.kpi({ label: 'بانتظار اعتماد العرض', value: String(open.filter(function (j) { return j.stage === 'بانتظار اعتماد العرض'; }).length), sub: 'فوق حد الاعتماد ' + fmt.kwd(cfg.approvalLimit), dot: 'o', tone: 'warning', action: 'mt-stage', arg: 'بانتظار اعتماد العرض' })}
        ${BT.kpi({ label: 'جاهزة للاستلام', value: String(open.filter(function (j) { return j.stage === 'جاهزة للاستلام'; }).length), sub: 'أُشعر السائق', dot: 'g', action: 'mt-stage', arg: 'جاهزة للاستلام' })}
        ${BT.kpi({ label: 'متوسط مدة البقاء', value: avg.toFixed(1) + ' يوم', sub: 'نوفمبر · ' + visits + ' زيارة', dot: 'p' })}
      </div>
      <div class="card" style="padding:10px 12px"><div class="flow" id="mt-flow"></div></div>
      <div class="card"><div id="mt-table"></div></div>`);
    function flow() {
      BT.render(document.getElementById('mt-flow'), h`<button type="button" class="st${stage === '' ? ' active' : ''}" data-st="">الكل <span class="n">${D.jobs.length}</span></button>${D.stages.map(function (s, i) {
        var n = D.jobs.filter(function (j) { return j.stage === s; }).length;
        return h`<span class="arr">${i ? '←' : '·'}</span><button type="button" class="st${stage === s ? ' active' : ''}" data-st="${s}">${s} <span class="n">${n}</span></button>`;
      })}`);
    }
    var t = BT.table(document.getElementById('mt-table'), {
      rows: function () { return D.jobs.filter(function (j) { return !stage || j.stage === stage; }).sort(function (a, b) { return (a.stage === 'تم الاستلام') - (b.stage === 'تم الاستلام') || b.opened.localeCompare(a.opened); }); },
      search: { placeholder: 'ابحث بلوحة أو رقم طلب…', text: function (j) { return j.id + ' ' + j.plate + ' ' + j.desc + ' ' + D.centerName(j.center); } },
      chips: { key: 'center', options: D.centers.map(function (c) { return { v: c.id, t: c.short }; }) },
      columns: [
        { key: 'id', label: 'الطلب', render: function (j) { return h`<b class="num">${j.id}</b><span class="sub">${fmt.date(j.opened)}</span>`; } },
        { key: 'plate', label: 'السيارة', render: function (j) { return j.vehicle ? A.veh(j.vehicle) : BT.plate(j.plate); } },
        { key: 'center', label: 'المركز', render: function (j) { return D.centerName(j.center); } },
        { key: 'type', label: 'النوع', render: function (j) { return h`${BT.pill(j.type, j.type === 'حادث' ? 'r' : j.type === 'دورية' ? 'n' : 'b')}<span class="sub" style="white-space:normal;max-width:220px">${j.desc}</span>`; } },
        { key: 'stage', label: 'الحالة', render: function (j) { return BT.pill(j.stage, D.stageTone[j.stage]); } },
        { key: 'days', label: 'المدة', num: true, render: function (j) { return j.days === 0 ? 'اليوم' : j.days + ' يوم'; } },
        { key: 'cost', label: 'المبلغ (د.ك)', num: true, render: function (j) { return j.invoice ? h`${fmt.kwd(j.invoice.total)}<span class="sub">فاتورة ${j.invoice.no}</span>` : j.estimate ? h`${fmt.kwd(j.estimate.total)}<span class="sub">عرض ${j.estimate.status === 'معتمد' ? 'معتمد' : 'معلّق'}</span>` : '—'; } }
      ],
      rowClick: function (j) { A.jobDrawer(j); },
      rowClass: function (j) { return j.stage === 'بانتظار اعتماد العرض' ? 'row-warn' : ''; }
    });
    flow();
    BT.on(A.view(), 'click', '[data-st]', function (e, b) { stage = b.getAttribute('data-st'); flow(); t.refresh(); });
    BT.actions['mt-stage'] = function (s) { stage = s; flow(); t.refresh(); };
  };

  /* ---------- تفاصيل طلب الصيانة ---------- */
  A.jobDrawer = function (j) {
    var si = D.stages.indexOf(j.stage), est = j.estimate, inv = j.invoice;
    var d = BT.drawer.open({
      title: h`طلب ${j.id} — <span class="plate">${j.plate}</span>`, subtitle: D.centerName(j.center) + ' · ' + j.type, icon: 'wrench', size: 'lg',
      body: h`<div class="flex items-center gap-8 mb-16" style="flex-wrap:wrap">${BT.pill(j.stage, D.stageTone[j.stage], true)}<span class="muted fs-sm">منذ ${j.days === 0 ? 'اليوم' : j.days + ' يوم'} · ${j.source}</span></div>
        <div class="flow mb-16">${D.stages.map(function (s, i) { return h`${i ? raw('<span class="arr">←</span>') : ''}<span class="st${i === si ? ' active' : ''}" style="${i < si ? 'background:var(--success-soft);color:var(--success-text)' : ''}">${i < si ? icon('check', 12) : ''}${s}</span>`; })}</div>
        <div class="grid-2">
          <div><div class="section-t">التفاصيل</div>${BT.kv([['السيارة', j.vehicle ? h`<span class="plate">${j.plate}</span> <span class="muted ltr">${j.vehicle.make} ${j.vehicle.model}</span>` : j.plate], ['الوصف', j.desc], ['تاريخ الطلب', fmt.date(j.opened)], ['المصدر', j.accident ? h`<a href="#/accidents/${j.accident}">${j.source}</a>` : j.source], ['المركز', D.centerName(j.center)]])}</div>
          <div><div class="section-t">عرض السعر</div>${est ? h`${est.items ? h`<div class="kv">${est.items.map(function (it) { return h`<div><span>${it[0]}</span><span class="num">${fmt.kwd(it[1])}</span></div>`; })}</div>` : ''}${BT.kv([['الإجمالي', BT.amt(est.total), 'total'], ['الحالة', BT.pill(est.status, est.status === 'معتمد' ? 'g' : 'o')]])}${est.status !== 'معتمد' && est.total > cfg.approvalLimit ? h`<div class="banner warn mt-8 fs-sm">${icon('shield-alert', 15)}<div>فوق حد الاعتماد (${fmt.kwd(cfg.approvalLimit)}) — لا يبدأ الإصلاح قبل الاعتماد.</div></div>` : ''}` : h`<div class="muted fs-sm">لم يُرسل المركز عرض سعر بعد.</div>`}</div>
        </div>
        ${inv ? h`<div class="section-t mt-16">الفاتورة ${inv.no}</div><div class="highlight-box">${BT.kv([inv.parts != null ? ['القطع', BT.amt(inv.parts)] : null, inv.labour != null ? ['الأجور', BT.amt(inv.labour)] : null, ['الإجمالي', BT.amt(inv.total), 'total'], est ? ['العرض المعتمد', BT.amt(est.total)] : null].filter(Boolean))}
          <div class="flex gap-8 items-center mt-8">${est && inv.total !== est.total ? BT.pill('فرق ' + fmt.signed(inv.total - est.total) + ' عن العرض', 'o') : ''}${BT.pill(inv.status, inv.status === 'مدفوعة' ? 'g' : 'o')}</div>
          <button type="button" class="doc-link mt-12" data-inv-file><span class="dl-ic">${icon('file-text', 18)}</span><span class="flex-1"><b>ملف الفاتورة</b><small>invoice_${inv.no}.pdf</small></span></button></div>` : ''}`,
      buttons: [
        { label: 'رسالة للمركز', cls: 'btn-ghost', icon: 'message-square', close: false, onClick: function () { A.msgCenter(j); } },
        j.stage === 'جاهزة للاستلام' ? { label: 'تم استلام السيارة', cls: 'btn-success', icon: 'check', close: false, onClick: function () { A.pickup(j, d); } } : null,
        est && est.status !== 'معتمد' ? { label: 'مراجعة العرض', cls: 'btn-primary', icon: 'badge-check', close: false, onClick: function () { A.approveEstimate(j, d); } } : null,
        inv && inv.status === 'بانتظار الاعتماد المالي' ? { label: 'مراجعة الفاتورة', cls: 'btn-primary', icon: 'receipt-text', close: false, onClick: function () { A.reviewInvoice(j, d); } } : null,
        { label: 'إغلاق', cls: 'btn-secondary' }
      ].filter(Boolean)
    });
    BT.on(d.el, 'click', '[data-inv-file]', function () { A.docPreview('فاتورة ' + inv.no + ' — ' + D.centerName(j.center), [['السيارة', j.plate], ['القطع', inv.parts != null ? fmt.kwd(inv.parts) : '—'], ['الأجور', inv.labour != null ? fmt.kwd(inv.labour) : '—'], ['الإجمالي', fmt.kwd(inv.total) + ' د.ك']]); });
  };
  A.msgCenter = function (j) {
    BT.modal.open({
      title: 'رسالة إلى ' + D.centerName(j.center), subtitle: 'تظهر في بوابة المركز على الطلب ' + j.id, icon: 'message-square', size: 'sm', form: true,
      body: h`<div class="form">${BT.f.textarea({ name: 'msg', label: 'الرسالة', required: true, rows: 4, placeholder: 'مثال: متى الموعد المتوقع لوصول القطعة؟' })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إرسال', cls: 'btn-primary', icon: 'send', submit: true }],
      onSubmit: function () { BT.toast('أُرسلت الرسالة إلى ' + D.centerName(j.center)); }
    });
  };
  A.pickup = function (j, parent) {
    BT.confirm({ title: 'استلام السيارة من المركز', message: 'تأكيد استلام ' + j.plate + ' من ' + D.centerName(j.center) + '. ستصبح السيارة «بلا سائق» وجاهزة للتسليم، ويتوقف احتساب مدة البقاء.', confirmText: 'تأكيد الاستلام', tone: 'success' })
      .then(function (r) { if (!r.ok) return; j.stage = 'تم الاستلام'; if (j.vehicle) j.vehicle.status = 'بلا سائق'; parent.close(); BT.toast('تم استلام ' + j.plate); A.router.refresh(); });
  };
  A.approveEstimate = function (j, parent) {
    var est = j.estimate;
    BT.modal.open({
      title: 'اعتماد عرض السعر', subtitle: j.id + ' · ' + j.plate + ' · ' + D.centerName(j.center), icon: 'badge-check', form: true,
      body: h`${est.items ? BT.chart.table(['البند', 'المبلغ (د.ك)'], est.items.map(function (it) { return [it[0], fmt.kwd(it[1])]; }).concat([['الإجمالي', fmt.kwd(est.total)]])) : BT.kv([['الإجمالي', BT.amt(est.total)]])}
        <div class="banner warn mt-12 fs-sm">${icon('shield-alert', 15)}<div>العرض أعلى من حد الاعتماد (${fmt.kwd(cfg.approvalLimit)} د.ك). آخر صيانة لهذه السيارة: قبل 4 أشهر (${fmt.kwd(64)} د.ك).</div></div>
        <div class="form mt-16">${BT.f.radios({ name: 'd', label: 'القرار', required: true, options: [{ v: 'ok', t: 'اعتماد', d: 'يبدأ الإصلاح' }, { v: 'change', t: 'طلب تعديل', d: 'يعدّل المركز العرض' }, { v: 'no', t: 'رفض', d: 'تُسحب السيارة' }] })}
        ${BT.f.textarea({ name: 'c', label: 'ملاحظة', optional: true, rows: 2 })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ القرار', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) {
        if (f.d !== 'ok' && !f.c) { BT.toast('اكتب ملاحظة للمركز', { type: 'error' }); return false; }
        if (f.d === 'ok') { est.status = 'معتمد'; j.stage = 'قيد الإصلاح'; D.approvals = D.approvals.filter(function (a) { return a.ref !== j.id; }); }
        if (parent) parent.close();
        BT.toast(f.d === 'ok' ? 'تم اعتماد العرض — بدأ الإصلاح' : f.d === 'change' ? 'أُرسل طلب التعديل للمركز' : 'تم رفض العرض', { type: f.d === 'no' ? 'warning' : 'success' });
        A.router.refresh();
      }
    });
  };
  A.reviewInvoice = function (j, parent) {
    var inv = j.invoice, est = j.estimate, diff = inv.total - (est ? est.total : inv.total);
    BT.modal.open({
      title: 'مراجعة الفاتورة ' + inv.no, subtitle: j.plate + ' · ' + D.centerName(j.center), icon: 'receipt-text', form: true,
      body: h`<div class="grid-2"><div class="highlight-box"><div class="label-sm">العرض المعتمد</div><div class="fs-xl fw-700 num">${fmt.kwd(est ? est.total : 0)}</div></div><div class="highlight-box"><div class="label-sm">الفاتورة</div><div class="fs-xl fw-700 num">${fmt.kwd(inv.total)}</div></div></div>
        ${diff ? h`<div class="banner warn mt-12">${icon('triangle-alert', 16)}<div>الفاتورة أعلى من العرض المعتمد بـ <b class="num">${fmt.kwd(diff)}</b> د.ك. اطلب التبرير أو اعتمد الفرق.</div></div>` : ''}
        <div class="mt-12">${BT.kv([['القطع', BT.amt(inv.parts)], ['الأجور', BT.amt(inv.labour)]])}</div>
        <div class="form mt-16">${BT.f.radios({ name: 'd', label: 'القرار', required: true, options: [{ v: 'ok', t: 'اعتماد مالي', d: 'تُحال للمالية للصرف' }, { v: 'back', t: 'إرجاع للمركز', d: 'مع السبب' }] })}${BT.f.textarea({ name: 'c', label: 'ملاحظة', optional: true, rows: 2 })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ القرار', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) {
        if (f.d === 'back' && !f.c) { BT.toast('اكتب سبب الإرجاع', { type: 'error' }); return false; }
        inv.status = f.d === 'ok' ? 'معتمدة' : 'مرتجعة للمركز';
        if (f.d === 'ok') D.approvals = D.approvals.filter(function (a) { return a.id !== 'AP-2'; });
        if (parent) parent.close();
        BT.toast(f.d === 'ok' ? 'تم الاعتماد المالي للفاتورة ' + inv.no : 'أُرجعت الفاتورة للمركز'); A.router.refresh();
      }
    });
  };

  BT.actions['maint-new'] = function (plate) {
    BT.modal.open({
      title: 'طلب صيانة', subtitle: 'يُحال إلى بوابة المركز المختار', icon: 'wrench', size: 'lg', form: true,
      body: h`<div class="form-grid">
        ${BT.f.select({ name: 'plate', label: 'السيارة', required: true, value: plate, options: D.vehicles.filter(function (v) { return v.status !== 'في الصيانة' || v.plate === plate; }).map(function (v) { return { v: v.plate, t: v.plate + ' — ' + v.make + ' ' + v.model }; }) })}
        ${BT.f.select({ name: 'center', label: 'مركز الصيانة', required: true, options: D.centers.map(function (c) { return { v: c.id, t: c.name + ' · ' + c.area }; }) })}
        <div class="full">${BT.f.radios({ name: 'type', label: 'نوع الصيانة', required: true, value: 'عطل', options: [{ v: 'دورية', t: 'دورية', d: 'زيت، فلاتر، إطارات' }, { v: 'عطل', t: 'عطل', d: 'بلاغ سائق أو ملاحظة' }, { v: 'حادث', t: 'حادث', d: 'مرتبط بملف حادث' }] })}</div>
        ${BT.f.textarea({ name: 'desc', label: 'وصف المشكلة', required: true, full: true, rows: 3 })}
        ${BT.f.input({ name: 'odo', label: 'قراءة العداد', num: true, optional: true })}
        ${BT.f.select({ name: 'prio', label: 'الأولوية', value: 'عادية', placeholder: false, options: ['عادية', 'عاجلة'] })}
        ${BT.f.upload({ name: 'photos', label: 'صور', optional: true, multiple: true, full: true, accept: 'image/*' })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إحالة للمركز', cls: 'btn-primary', icon: 'send', submit: true }],
      onSubmit: function (f) {
        var v = D.byPlate[f.plate], e = D.driverOf(v);
        D.jobs.unshift({ id: 'M-' + (2700 + D.jobs.length), plate: f.plate, vehicle: v, center: f.center, stage: 'مستلمة', days: 0, type: f.type, source: 'لوحة الإدارة', desc: f.desc, opened: cfg.today, cost: 0 });
        v.status = 'في الصيانة';
        if (e) { e.vehicleId = null; v.driverId = null; }
        BT.toast('أُحيلت ' + f.plate + ' إلى ' + D.centerName(f.center), { sub: e ? 'تم فك ارتباط السيارة بالسائق ' + e.name : '' });
        A.router.refresh();
      }
    });
  };

  /* =================================================================
     الحوادث  #/accidents
     ================================================================= */
  BT.pages['accidents'] = function () {
    A.setTitle('الحوادث');
    var open = D.accidents.filter(function (a) { return a.status.indexOf('مغلق') < 0; });
    var ded = D.deductions.filter(function (d) { return /حادث/.test(d.reason); });
    BT.render(A.view(), h`
      ${A.head('تقرير الشرطة يحدد المسؤولية، والمركز يقدّر التلفيات', 'ملف واحد لكل حادث: الصور والتقرير والتقدير والخصم', A.btn('تسجيل حادث', { icon: 'plus', cls: 'btn-primary', action: 'accident-new' }))}
      <div class="kpis">
        ${BT.kpi({ label: 'حوادث الشهر', value: String(D.accidents.length), sub: fmt.month(2026, 11), dot: 'b' })}
        ${BT.kpi({ label: 'ملفات مفتوحة', value: String(open.length), dot: 'o', tone: 'warning' })}
        ${BT.kpi({ label: 'بانتظار تقرير الشرطة', value: String(D.accidents.filter(function (a) { return !a.police; }).length), sub: 'لا تُسجَّل نتيجة دون تقرير', dot: 'r' })}
        ${BT.kpi({ label: 'خصومات حوادث معتمدة', value: fmt.kwd(BT.sum(ded, function (d) { return d.total; })), sub: ded.length + ' خطط أقساط', dot: 'p' })}
      </div>
      <div class="card"><div id="ac-table"></div></div>`);
    BT.table(document.getElementById('ac-table'), {
      rows: function () { return D.accidents; },
      search: { placeholder: 'رقم الحادث أو اللوحة أو السائق…', text: function (a) { return a.id + ' ' + a.plate + ' ' + a.driver + ' ' + a.location; } },
      chips: { key: 'open', options: [{ v: 'open', t: 'مفتوحة' }, { v: 'closed', t: 'مغلقة' }], match: function (a, v) { return (a.status.indexOf('مغلق') < 0) === (v === 'open'); } },
      columns: [
        { key: 'id', label: 'الحادث', render: function (a) { return h`<b class="num">${a.id}</b><span class="sub"><span class="num">${fmt.date(a.date)} ${a.time}</span></span>`; } },
        { key: 'plate', label: 'السيارة', render: function (a) { return A.veh(D.byPlate[a.plate]); } },
        { key: 'driver', label: 'السائق', render: function (a) { return BT.person(a.driver, 'من سجل التسليم'); } },
        { key: 'location', label: 'الموقع' },
        { key: 'status', label: 'الحالة', render: function (a) { return BT.pill(a.status, a.statusTone); } },
        { key: 'estimate', label: 'التقدير (د.ك)', num: true, render: function (a) { return a.estimate ? fmt.kwd(a.estimate) : '—'; } },
        { key: 'liability', label: 'المسؤولية', render: function (a) { return a.liability || '—'; } }
      ],
      rowClick: function (a) { A.go('accidents/' + a.id); }
    });
  };

  /* ---------- ملف الحادث  #/accidents/A-0142 ---------- */
  BT.pages['accidents/:id'] = function (p) {
    var a = D.accidents.find(function (x) { return x.id === p.id; });
    if (!a) { BT.render(A.view(), BT.empty('triangle-alert', 'الحادث غير موجود', '')); return; }
    A.setTitle('ملف الحادث ' + a.id, [['الحوادث', 'accidents'], [a.id]]);
    var v = D.byPlate[a.plate];
    var tl = a.timeline || [
      ['بلاغ السائق من التطبيق', fmt.dm(a.date) + ' · ' + a.time + ' · الموقع: ' + a.location, 'g'],
      a.police ? ['تقرير الشرطة مرفق', 'رقم ' + a.police.no + ' · PDF', 'g'] : ['تقرير الشرطة', 'بانتظار الإرفاق', 'pending'],
      a.center ? ['إحالة لـ' + D.centerName(a.center) + ' لتقدير التلفيات', a.estimate ? fmt.kwd(a.estimate) + ' د.ك' : 'بانتظار التقدير', a.estimate ? 'g' : 'o'] : ['تقدير التلفيات', 'بعد إرفاق التقرير', 'pending'],
      [a.liability ? 'النتيجة: ' + a.liability : 'تحديد المسؤولية وفق تقرير الشرطة', a.liability ? 'وفق تقرير الشرطة' : '', a.liability ? 'g' : 'pending']
    ];
    var next = !a.police ? A.btn('إرفاق تقرير الشرطة', { icon: 'file-up', cls: 'btn-primary', action: 'acc-police', arg: a.id })
      : !a.center ? A.btn('إحالة لمركز صيانة', { icon: 'send', cls: 'btn-primary', action: 'acc-center', arg: a.id })
      : !a.estimate ? A.btn('إدخال/اعتماد التقدير', { icon: 'badge-check', cls: 'btn-primary', action: 'acc-estimate', arg: a.id })
      : !a.liability ? A.btn('تحديد المسؤولية', { icon: 'scale', cls: 'btn-primary', action: 'acc-liability', arg: a.id }) : '';
    BT.render(A.view(), h`
      <div class="page-head"><div><div class="flex items-center gap-8" style="flex-wrap:wrap"><h2>ملف الحادث <span class="num">${a.id}</span></h2>${BT.pill(a.status, a.statusTone, true)}</div><p><span class="num">${fmt.date(a.date)} · ${a.time}</span> · ${a.location}</p></div>
        <div class="page-actions">${A.btn('طباعة الملف', { icon: 'printer', cls: 'btn-outline', action: 'export', arg: 'ملف الحادث ' + a.id })}${next}</div></div>
      <div class="grid" style="grid-template-columns:minmax(0,1.4fr) minmax(0,1fr)">
        <div class="card col" style="gap:14px"><div class="card-h" style="margin:0"><div class="card-t">صور حالة السيارة</div><span class="card-meta">من الكاميرا مباشرة</span></div>
          <div class="ph-grid cols-4">${['أمام', 'خلف', 'يمين', 'يسار'].map(function (s, i) { return h`<button type="button" class="ph" data-ph="${i}" style="min-height:100px">${icon('car', 26)}<span>${s}</span></button>`; })}</div>
          ${a.police ? h`<button type="button" class="doc-link" data-police>${raw('<span class="dl-ic">' + icon('file-text', 18) + '</span>')}<span class="flex-1"><b>تقرير قسم الشرطة · رقم <span class="num">${a.police.no}</span></b><small>${a.police.file}</small></span>${icon('eye', 16)}</button>`
            : h`<div class="banner danger">${icon('file-warning', 16)}<div><b>تقرير الشرطة غير مرفق.</b> لا تُسجَّل نتيجة ولا خصم دون تقرير مرفق.</div><button type="button" class="btn btn-sm btn-danger-solid banner-act" data-action="acc-police" data-arg="${a.id}">إرفاق</button></div>`}
          ${BT.kv([['السيارة', v ? h`<span class="plate">${v.plate}</span> · <span class="ltr">${v.make} ${v.model}</span>` : a.plate], ['السائق (من سجل التسليم)', h`<bdi>${a.driver}</bdi>`], ['الطرف الآخر', a.other], ['الإصابات', a.injuries], ['مركز التقدير', a.center ? D.centerName(a.center) : '—'], ['التلفيات المقدّرة', a.estimate ? BT.amt(a.estimate) : '—']])}
        </div>
        <div class="card"><div class="card-h"><div class="card-t">مسار الحادث</div></div>
          <div class="timeline">${tl.map(function (s) { return h`<div class="tl-item"><span class="tl-ic ${s[2]}">${s[2] === 'pending' ? '' : icon(s[2] === 'o' ? 'clock' : 'check', 13)}</span><div><div class="tl-t${s[2] === 'pending' ? ' muted' : ''}">${s[0]}</div><div class="tl-d">${s[1]}</div></div></div>`; })}</div>
          ${a.installments ? h`<div class="highlight-box mt-12"><div class="section-t" style="margin-top:0">خطة الخصم</div>${BT.kv([['الإجمالي', BT.amt(a.liability === 'السائق' ? a.estimate : a.estimate / 2)], ['الأقساط', a.installments + ' × ' + fmt.kwd((a.liability === 'السائق' ? a.estimate : a.estimate / 2) / a.installments)], ['تظهر في', 'كشف الراتب وتطبيق السائق']])}</div>` : ''}
        </div>
      </div>`);
    BT.on(A.view(), 'click', '[data-ph]', function (e, b) { BT.lightbox(['أمام', 'خلف', 'يمين', 'يسار'].map(function (s) { return { html: h`<div class="ph" style="width:min(680px,86vw);height:420px">${icon('car', 72)}<span>${s}</span></div>`, caption: 'صورة ' + s + ' — ' + a.id, sub: 'من الكاميرا · ' + fmt.iso(a.date) + ' ' + a.time }; }), +b.getAttribute('data-ph')); });
    BT.on(A.view(), 'click', '[data-police]', function () { A.docPreview('تقرير قسم الشرطة — ' + a.police.no, [['رقم التقرير', a.police.no], ['التاريخ', fmt.date(a.date)], ['الموقع', a.location], ['الطرف الآخر', a.other], ['النتيجة', a.liability || 'قيد الدراسة']]); });
  };
  function acc(id) { return D.accidents.find(function (x) { return x.id === id; }); }
  BT.actions['acc-police'] = function (id) {
    var a = acc(id);
    BT.modal.open({
      title: 'إرفاق تقرير الشرطة', subtitle: a.id, icon: 'file-up', form: true,
      body: h`<div class="form">${BT.f.input({ name: 'no', label: 'رقم التقرير', required: true, placeholder: '2026/0000' })}${BT.f.upload({ name: 'file', label: 'ملف التقرير', required: true })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إرفاق', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) { a.police = { no: f.no, file: f.file[0].name }; a.status = 'بانتظار الإحالة'; a.statusTone = 'o'; BT.toast('تم إرفاق تقرير الشرطة'); A.router.refresh(); }
    });
  };
  BT.actions['acc-center'] = function (id) {
    var a = acc(id);
    BT.modal.open({
      title: 'إحالة لتقدير التلفيات', subtitle: a.id + ' · ' + a.plate, icon: 'send', size: 'sm', form: true,
      body: h`<div class="form">${BT.f.select({ name: 'c', label: 'مركز الصيانة', required: true, options: D.centers.map(function (c) { return { v: c.id, t: c.name }; }) })}<div class="banner info fs-sm">${icon('info', 15)}<div>تصل للمركز الصور وتقرير الشرطة في بوابته، ويُدخل تقدير التلفيات.</div></div></div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إحالة', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) { a.center = f.c; a.status = 'بانتظار تقدير التلفيات'; a.statusTone = 'o'; BT.toast('أُحيل الحادث إلى ' + D.centerName(f.c)); A.router.refresh(); }
    });
  };
  BT.actions['acc-estimate'] = function (id) {
    var a = acc(id);
    BT.modal.open({
      title: 'اعتماد تقدير التلفيات', subtitle: a.id + ' · ' + D.centerName(a.center), icon: 'badge-check', size: 'sm', form: true,
      body: h`<div class="banner info mb-12 fs-sm">${icon('clock', 15)}<div>المركز لم يُدخل التقدير بعد. في هذا القالب يمكنك إدخاله نيابةً عنه للتجربة.</div></div><div class="form">${BT.f.money({ name: 'amt', label: 'مبلغ التقدير', required: true, min: 1 })}${BT.f.textarea({ name: 'c', label: 'ملاحظة', optional: true, rows: 2 })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'اعتماد', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) { a.estimate = f.amt; a.status = 'بانتظار تحديد المسؤولية'; a.statusTone = 'b'; BT.toast('تم اعتماد التقدير ' + fmt.kwd(f.amt) + ' د.ك'); A.router.refresh(); }
    });
  };
  BT.actions['acc-liability'] = function (id) {
    var a = acc(id), emp = D.byName[a.driver];
    var maxPct = cfg.maxDeductionPct, maxAmt = emp ? emp.basic * maxPct / 100 : 0;
    var d = BT.modal.open({
      title: 'تحديد المسؤولية', subtitle: a.id + ' · التقدير ' + fmt.kwd(a.estimate) + ' د.ك', icon: 'scale', size: 'lg', form: true,
      body: h`<div class="form">${BT.f.radios({ name: 'who', label: 'المسؤولية وفق تقرير الشرطة', required: true, options: [{ v: 'السائق', t: 'السائق', d: 'خصم كامل التقدير' }, { v: 'مشتركة 50%', t: 'مشتركة', d: 'خصم 50%' }, { v: 'الطرف الآخر', t: 'الطرف الآخر', d: 'لا خصم · مطالبة التأمين' }] })}
        <div id="ded-wrap" class="hidden"><div class="form-grid">${BT.f.select({ name: 'n', label: 'عدد الأقساط', value: '3', placeholder: false, options: ['1', '2', '3', '4', '5', '6'] })}${BT.f.select({ name: 'start', label: 'بداية الخصم', value: 'نوفمبر 2026', placeholder: false, options: ['نوفمبر 2026', 'ديسمبر 2026', 'يناير 2027'] })}</div><div id="ded-prev" class="mt-12"></div></div>
        ${BT.f.textarea({ name: 'c', label: 'ملاحظة', optional: true, rows: 2 })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'اعتماد وإغلاق الملف', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) {
        var total = f.who === 'السائق' ? a.estimate : f.who === 'مشتركة 50%' ? a.estimate / 2 : 0;
        a.liability = f.who; a.status = total ? 'مغلق — خصم معتمد' : 'مغلق — على الطرف الآخر'; a.statusTone = total ? 'g' : 'n'; a.installments = total ? +f.n : null;
        if (total && emp) D.deductions.push({ id: 'DD-' + (300 + D.deductions.length), empId: emp.id, driver: emp.name, reason: 'حادث ' + a.id, total: total, count: +f.n, paid: 0, per: BT.round3(total / f.n), start: f.start, status: 'معتمد' });
        BT.toast('أُغلق ملف الحادث', { sub: total ? 'خصم ' + fmt.kwd(total) + ' على ' + f.n + ' أقساط من راتب ' + a.driver : 'لا خصم على السائق' }); A.router.refresh();
      }
    });
    function prev() {
      var who = (d.el.querySelector('[name=who]:checked') || {}).value, n = +d.el.querySelector('[name=n]').value;
      var total = who === 'السائق' ? a.estimate : who === 'مشتركة 50%' ? a.estimate / 2 : 0, per = total / n;
      d.el.querySelector('#ded-wrap').classList.toggle('hidden', !total);
      if (!total) return;
      BT.render(d.el.querySelector('#ded-prev'), h`${BT.chart.table(['القسط', 'الشهر', 'المبلغ (د.ك)'], Array.from({ length: n }, function (x, i) { return [String(i + 1), ['نوفمبر', 'ديسمبر', 'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو'][i + ['نوفمبر 2026', 'ديسمبر 2026', 'يناير 2027'].indexOf(d.el.querySelector('[name=start]').value)], fmt.kwd(per)]; }))}
        ${per > maxAmt ? h`<div class="banner warn mt-8 fs-sm">${icon('triangle-alert', 15)}<div>القسط ${fmt.kwd(per)} أعلى من الحد الأقصى للخصم (${maxPct}% من الراتب = ${fmt.kwd(maxAmt)}). الزيادة تُرحّل تلقائياً للشهر التالي.</div></div>` : ''}`);
    }
    BT.on(d.el, 'change', '[name=who],[name=n],[name=start]', prev);
  };

  BT.actions['accident-new'] = function () {
    var d = BT.modal.open({
      title: 'تسجيل حادث', subtitle: 'السائق يُحدَّد تلقائياً من سجل التسليم', icon: 'triangle-alert', iconTone: 'danger', size: 'lg', form: true,
      body: h`<div class="form-grid">
        ${BT.f.select({ name: 'plate', label: 'السيارة', required: true, options: D.vehicles.filter(function (v) { return v.status === 'مسلّمة'; }).map(function (v) { return { v: v.plate, t: v.plate + ' — ' + v.make + ' ' + v.model }; }) })}
        <div class="field"><label>السائق وقت الحادث</label><div class="input" id="acc-drv" style="display:flex;align-items:center;background:var(--surface-sunken)"><span class="muted">اختر السيارة</span></div></div>
        ${BT.f.date({ name: 'date', label: 'التاريخ', required: true, value: cfg.today })}
        ${BT.f.input({ name: 'time', label: 'الوقت', type: 'time', required: true })}
        ${BT.f.input({ name: 'loc', label: 'الموقع', required: true, placeholder: 'المنطقة / الشارع' })}
        ${BT.f.select({ name: 'other', label: 'الطرف الآخر', required: true, options: ['مركبة خاصة', 'مركبة نقل', 'لا يوجد', 'أخرى'] })}
        ${BT.f.select({ name: 'inj', label: 'الإصابات', required: true, value: 'لا يوجد', options: ['لا يوجد', 'إصابة طفيفة', 'إصابة تحتاج علاج'] })}
        ${BT.f.input({ name: 'pno', label: 'رقم تقرير الشرطة', optional: true })}
        ${BT.f.upload({ name: 'police', label: 'تقرير الشرطة', optional: true, hint: 'يمكن إرفاقه لاحقاً — لا تُسجَّل نتيجة دون تقرير' })}
        ${BT.f.upload({ name: 'photos', label: 'صور السيارة (أمام، خلف، يمين، يسار)', required: true, multiple: true, accept: 'image/*' })}
        ${BT.f.textarea({ name: 'desc', label: 'وصف الحادث', required: true, full: true, rows: 3 })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'تسجيل الحادث', cls: 'btn-danger-solid', submit: true }],
      onSubmit: function (f) {
        var v = D.byPlate[f.plate], e = D.driverOf(v), id = 'A-0' + (145 + D.accidents.length - 5);
        D.accidents.unshift({ id: id, plate: f.plate, driver: e ? e.name : '—', date: f.date, time: f.time, location: f.loc, other: f.other, injuries: f.inj, status: f.police.length ? 'بانتظار الإحالة' : 'بانتظار تقرير الشرطة', statusTone: f.police.length ? 'o' : 'r', police: f.police.length ? { no: f.pno || '—', file: f.police[0].name } : null, center: null, estimate: null, liability: null });
        BT.toast('تم تسجيل الحادث ' + id); A.go('accidents/' + id);
      }
    });
    function drv() { var v = D.byPlate[d.el.querySelector('[name=plate]').value], e = D.driverOf(v); BT.render(d.el.querySelector('#acc-drv'), e ? h`<bdi>${e.name}</bdi>&nbsp;<span class="muted fs-sm">· ${e.id}</span>` : h`<span class="muted">اختر السيارة</span>`); }
    d.el.querySelector('[name=plate]').addEventListener('change', drv);
  };
})();
