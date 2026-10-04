/* =====================================================================
   صفحات التشغيل: العمل اليومي · الكاش والخزينة
   بوب أب: مراجعة التقرير (xl) · لقطة الشاشة (lightbox) · اعتماد/طلب تعديل/رفض ·
   تعديل الأرقام · تذكير المتأخرين · اعتماد جماعي · تسجيل تحصيل · الإيصال (طباعة) ·
   دفتر السائق (drawer) · تسوية · إيداع بنكي · إلغاء إيصال
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, D = BT.data, A = BT.A;
  var cfg = BT.config;
  var ORDER = { 'انحراف عن المتوسط': 0, 'بانتظار المراجعة': 1, 'مطلوب تعديل': 2, 'متأخر: لم يُرسل': 3, 'مرفوض': 4, 'معتمد': 5 };
  function dev(r) { return r.cash != null && r.avgC ? (r.cash - r.avgC) / r.avgC * 100 : null; }

  /* =================================================================
     العمل اليومي  #/daily
     ================================================================= */
  BT.pages['daily'] = function (p, q) {
    A.setTitle('العمل اليومي');
    var st = D.reportStats();
    BT.render(A.view(), h`
      ${A.head('ملخص واحد لكل يوم، ودليله بجانبه', 'لا ربط مع شركات التوصيل: السائق يرفع لقطة شاشة من تطبيقها مع إجمالي يومه',
        h`<input class="input" type="date" value="${cfg.today}" max="${cfg.today}" style="width:170px" id="dw-date" aria-label="التاريخ">${A.btn('تذكير المتأخرين', { icon: 'bell-ring', cls: 'btn-outline', action: 'remind-late' })}${A.btn('تصدير', { icon: 'download', cls: 'btn-outline', action: 'export', arg: 'تقارير اليوم' })}`)}
      <div class="kpis cols-5">
        ${BT.kpi({ label: 'بدؤوا يومهم', value: fmt.int(st.started), sub: 'من ' + D.vehicles.filter(function (v) { return v.status === 'مسلّمة'; }).length + ' سيارة مسلّمة', dot: 'b' })}
        ${BT.kpi({ label: 'أرسلوا التقرير', value: fmt.int(st.sent), sub: fmt.int(st.orders) + ' طلباً', dot: 'p' })}
        ${BT.kpi({ label: 'معتمد', value: fmt.int(st.approved), dot: 'g', action: 'dw-chip', arg: 'معتمد' })}
        ${BT.kpi({ label: 'قيد المراجعة', value: fmt.int(st.review), sub: 'بانتظار · انحراف · تعديل · مرفوض', dot: 'o', tone: 'warning', action: 'dw-chip', arg: 'review' })}
        ${BT.kpi({ label: 'متأخر: لم يُرسل', value: fmt.int(st.late), sub: 'بدأ يومه ولم يرسل', dot: 'n', action: 'dw-chip', arg: 'متأخر: لم يُرسل' })}
      </div>
      <div class="card" id="dw-card"><div id="dw-table"></div></div>`);
    var t = BT.table(document.getElementById('dw-table'), {
      rows: function () { return D.reports.slice().sort(function (a, b) { return ORDER[a.status] - ORDER[b.status] || (b.cash || 0) - (a.cash || 0); }); },
      search: { placeholder: 'ابحث بسائق أو لوحة…', text: function (r) { return r.driver + ' ' + r.plate; } },
      chips: { key: 'status', value: q.status || 'review', options: [{ v: 'review', t: 'قيد المراجعة' }, { v: 'انحراف عن المتوسط', t: 'انحراف' }, { v: 'معتمد', t: 'معتمد' }, { v: 'متأخر: لم يُرسل', t: 'متأخر' }],
        match: function (r, v) { return v === 'review' ? r.orders != null && r.status !== 'معتمد' : r.status === v; } },
      columns: [
        { key: 'driver', label: 'السائق', render: function (r) { return BT.person(r.driver, r.plate); } },
        { key: 'orders', label: 'الطلبات', num: true, render: function (r) { return r.orders == null ? '—' : String(r.orders); } },
        { key: 'cash', label: 'الكاش (د.ك)', num: true, render: function (r) { return r.cash == null ? '—' : fmt.kwd(r.cash); } },
        { key: 'dev', label: 'عن متوسطه', sort: function (r) { var d = dev(r); return d == null ? -999 : Math.abs(d); }, render: function (r) { var d = dev(r); return d == null ? '—' : Math.abs(d) > 40 ? BT.pill(fmt.pct(d), 'r') : h`<span class="num muted">${fmt.pct(d)}</span>`; } },
        { key: 'km', label: 'كم (عداد / GPS)', sort: function (r) { return r.end ? r.end - r.start : 0; }, render: function (r) { return r.end ? h`<span class="num">${r.end - r.start} / ${r.gps}</span>` : '—'; } },
        { key: 'status', label: 'الحالة', render: function (r) { return BT.pill(r.status === 'انحراف عن المتوسط' ? 'انحراف ' + fmt.pct(dev(r)) : r.status, D.reportTone[r.status]); } },
        { key: 'sent', label: 'وقت الإرسال', render: function (r) { return r.sent ? h`<span class="num">${r.sent}</span>` : h`<span class="muted fs-sm">بدأ ${r.started || ''}</span>`; } }
      ],
      rowClick: function (r) { A.reviewReport(r); },
      rowClass: function (r) { return r.status === 'انحراف عن المتوسط' ? 'row-danger' : r.status === 'بانتظار المراجعة' ? 'row-warn' : ''; },
      selectable: true,
      bulk: [
        { label: 'اعتماد المحدد', icon: 'check', cls: 'btn-primary', run: function (rows, done) {
          var ok = rows.filter(function (r) { return r.status === 'بانتظار المراجعة'; });
          var skip = rows.length - ok.length;
          BT.confirm({ title: 'اعتماد ' + ok.length + ' تقريراً', message: 'سيُضاف كاش هذه التقارير إلى أرصدة السائقين كرصيد معتمد.' + (skip ? ' سيتم تخطي ' + skip + ' تقرير (انحراف أو متأخر أو معتمد مسبقاً) — هذه تحتاج مراجعة فردية.' : ''), confirmText: 'اعتماد', tone: 'success' })
            .then(function (res) { if (!res.ok) return; ok.forEach(function (r) { r.status = 'معتمد'; }); done(); BT.toast('تم اعتماد ' + ok.length + ' تقريراً'); A.router.refresh(); });
        } },
        { label: 'تصدير', icon: 'download', run: function (rows, done) { A.exportToast(rows.length + ' تقريراً'); done(); } }
      ]
    });
    BT.actions['dw-chip'] = function (s) { t.setChip(s); };
    document.getElementById('dw-date').addEventListener('change', function (e) {
      if (e.target.value !== cfg.today) BT.toast('البيانات التجريبية متاحة ليوم ' + fmt.iso(cfg.today) + ' فقط', { type: 'info', sub: 'في النظام الفعلي تُحمَّل تقارير اليوم المحدد' });
    });
  };

  BT.actions['remind-late'] = function () {
    var n = D.reports.filter(function (r) { return r.status === 'متأخر: لم يُرسل'; }).length;
    BT.confirm({ title: 'تذكير المتأخرين', message: 'سيصل إشعار فوري إلى ' + n + ' سائقاً بدؤوا يومهم ولم يرسلوا التقرير اليومي.', confirmText: 'إرسال التذكير', icon: 'bell-ring' })
      .then(function (r) { if (r.ok) BT.toast('أُرسل التذكير إلى ' + n + ' سائقاً'); });
  };

  /* ---------- لقطة الشاشة (mock) ---------- */
  A.shot = function (r, lg) {
    return h`<button type="button" class="shot${lg ? ' lg' : ''}" data-shot aria-label="تكبير لقطة الشاشة"><div class="shot-in">
      <div class="s-top"><span>${r.sent || '23:00'}</span><span>▮▮▮</span></div>
      <div style="font-weight:700;margin-top:8px">ملخص اليوم</div><div style="color:#8A93A6;font-size:.85em">${fmt.dateLong(r.date)}</div>
      <div class="s-box"><small>الطلبات المكتملة</small><b>${r.orders}</b></div>
      <div class="s-box"><small>النقد المحصّل (د.ك)</small><b>${fmt.kwd(r.cash)}</b></div>
      <div style="margin-top:8px"><div class="s-row"><span style="color:#8A93A6">أول طلب</span><span class="num">${r.first}</span></div><div class="s-row"><span style="color:#8A93A6">آخر طلب</span><span class="num">${r.last}</span></div></div>
      </div><div class="shot-cap">لقطة شاشة مرفوعة</div></button>`;
  };

  /* ---------- مراجعة التقرير ---------- */
  A.reviewReport = function (r) {
    var e = D.byName[r.driver];
    if (r.orders == null) {
      BT.modal.open({
        title: 'تقرير لم يُرسل', subtitle: r.driver + ' · ' + r.plate, icon: 'clock', iconTone: 'warn', size: 'sm',
        body: h`<div class="confirm-msg">بدأ السائق يومه الساعة <b class="num">${r.started}</b> بعداد <b class="num">${fmt.km(r.start)}</b>، ولم يرسل التقرير اليومي حتى الآن.</div>`,
        buttons: [{ label: 'إغلاق', cls: 'btn-ghost' }, { label: 'إرسال تذكير', cls: 'btn-primary', icon: 'bell-ring', onClick: function () { BT.toast('أُرسل تذكير إلى ' + r.driver); } }]
      });
      return;
    }
    var d = dev(r), done = r.status === 'معتمد';
    var dlg = BT.modal.open({
      title: h`مراجعة التقرير — <bdi>${r.driver}</bdi>`, subtitle: fmt.iso(r.date) + ' · سيارة ' + r.plate + ' · أُرسل ' + r.sent, icon: 'clipboard-list', size: 'xl',
      body: h`${r.status === 'انحراف عن المتوسط' ? h`<div class="banner danger mb-12">${icon('trending-up', 16)}<div>الكاش أعلى من متوسط السائق بنسبة <b class="num">${fmt.pct(d)}</b>. قارن الرقم بلقطة الشاشة قبل الاعتماد.</div></div>` : ''}
        ${r.status === 'مطلوب تعديل' ? h`<div class="banner note mb-12" style="border-inline-start-color:var(--purple)">${icon('message-square', 16)}<div>طُلب من السائق تعديل التقرير: «لقطة الشاشة لا تطابق عدد الطلبات». بانتظار إعادة الإرسال.</div></div>` : ''}
        <div class="grid" style="grid-template-columns:minmax(0,1fr) auto;gap:20px">
          <div class="col" style="gap:12px">
            <div class="kpis" style="grid-template-columns:repeat(2,minmax(0,1fr))">
              ${BT.kpi({ label: 'عدد الطلبات', value: String(r.orders), sub: 'متوسطه ' + r.avgO + ' في آخر 30 يوماً', dot: 'b' })}
              ${BT.kpi({ label: 'الكاش (د.ك)', value: fmt.kwd(r.cash), sub: 'متوسطه ' + fmt.kwd(r.avgC) + (Math.abs(d) > 40 ? ' · خارج المعتاد' : ' · ضمن المعتاد'), dot: 'o', tone: Math.abs(d) > 40 ? 'danger' : '' })}
            </div>
            <div class="grid-2" style="gap:12px">
              <button type="button" class="odo" data-odo-end>${raw(String(A.odoPhoto(r.end, 'من الكاميرا · ' + r.sent)).replace(/^<div class="odo">|<\/div>$/g, ''))}</button>
              ${BT.kpi({ label: 'عداد نهاية اليوم', value: fmt.km(r.end), sub: 'بداية اليوم ' + fmt.km(r.start) + ' · ' + (r.end - r.start) + ' كم (GPS ' + r.gps + ' كم)', dot: 'g' })}
            </div>
            <div class="card" style="padding:12px 14px"><div class="section-t">آخر 4 أيام للسائق <span class="muted fw-500 fs-xs">· من دفتر الكاش</span></div>
              ${BT.chart.table(['اليوم', 'الطلبات (تقريبي)', 'الكاش (د.ك)'], A.driverDays(e, r))}</div>
            ${done ? '' : h`<div class="field"><label for="rv-note">ملاحظة المراجع <span class="opt">(إلزامية عند الرفض أو طلب التعديل)</span></label><textarea class="textarea" id="rv-note" rows="2" placeholder="مثال: عدد الطلبات في لقطة الشاشة 23 وليس 25"></textarea><div class="err-msg"></div></div>`}
          </div>
          <div>${A.shot(r)}</div>
        </div>`,
      footNote: done ? 'اعتُمد التقرير — أي تعديل الآن يتم كتسوية في دفتر السائق' : 'الرفض وطلب التعديل بسبب إلزامي، ويظهر للسائق في التطبيق',
      buttons: done ? [{ label: 'تسوية في دفتر السائق', cls: 'btn-outline', icon: 'scale', onClick: function () { setTimeout(function () { A.adjust(e); }, 240); } }, { label: 'إغلاق', cls: 'btn-primary' }] : [
        { label: 'رفض', cls: 'btn-danger', close: false, onClick: function () { act('مرفوض'); } },
        { label: 'طلب تعديل', cls: 'btn-outline', close: false, onClick: function () { act('مطلوب تعديل'); } },
        { label: 'تعديل الأرقام', cls: 'btn-ghost', icon: 'pencil', close: false, onClick: function () { A.editNumbers(r, dlg); } },
        { label: 'اعتماد', cls: 'btn-success', icon: 'check', close: false, onClick: function () { act('معتمد'); } }
      ]
    });
    function act(status) {
      var note = dlg.el.querySelector('#rv-note'), f = note.closest('.field');
      if (status !== 'معتمد' && !note.value.trim()) { f.classList.add('invalid'); f.querySelector('.err-msg').textContent = 'اكتب السبب — يظهر للسائق'; note.focus(); return; }
      r.status = status; dlg.close();
      BT.toast(status === 'معتمد' ? 'تم اعتماد تقرير ' + r.driver : status === 'مرفوض' ? 'تم رفض التقرير' : 'أُرسل طلب التعديل إلى ' + r.driver, { sub: status === 'معتمد' ? 'أُضيف ' + fmt.kwd(r.cash) + ' د.ك لرصيد السائق كرصيد معتمد' : note.value.trim(), type: status === 'مرفوض' ? 'warning' : 'success' });
      A.router.refresh();
    }
    BT.on(dlg.el, 'click', '[data-shot]', function () { BT.lightbox({ html: A.shot(r, true), caption: 'لقطة شاشة تطبيق شركة التوصيل — ' + r.driver, sub: 'مرفوعة من تطبيق السائق · ' + fmt.iso(r.date) + ' ' + r.sent }); });
    BT.on(dlg.el, 'click', '[data-odo-end]', function () { A.showOdo([{ value: r.start, caption: 'عداد بداية اليوم', sub: 'المكتوب ' + fmt.km(r.start) }, { value: r.end, caption: 'عداد نهاية اليوم', sub: 'المكتوب ' + fmt.km(r.end) }], 1); });
  };
  // آخر 4 أيام من دفتر الكاش (اليوم الذي ليس له «كاش يومي» = لم يعمل، مثلاً السيارة كانت مع سائق آخر)
  A.driverDays = function (e, r) {
    var L = D.ledger(e), perOrder = r.cash / r.orders;
    return [0, -1, -2, -3].map(function (k) {
      var day = BT.date.add(r.date, k);
      if (!k) return [fmt.dm(day) + ' (اليوم)', String(r.orders), fmt.kwd(r.cash)];
      var x = L.find(function (l) { return l.date === day && /^كاش يومي/.test(l.text); });
      return x ? [fmt.dm(day), '≈ ' + Math.round(x.amount / perOrder), fmt.kwd(x.amount)] : [fmt.dm(day), raw('<span class="muted">لا يوجد تقرير</span>'), '—'];
    });
  };
  A.editNumbers = function (r, parent) {
    BT.modal.open({
      title: 'تعديل أرقام التقرير', subtitle: r.driver, icon: 'pencil', size: 'sm', form: true,
      body: h`<div class="form">${BT.f.input({ name: 'orders', label: 'عدد الطلبات', num: true, required: true, value: r.orders, min: 0 })}
        ${BT.f.money({ name: 'cash', label: 'الكاش', required: true, value: fmt.kwd(r.cash) })}
        ${BT.f.textarea({ name: 'reason', label: 'سبب التعديل', required: true, placeholder: 'يُسجَّل في سجل التدقيق ويظهر للسائق' })}
        <div class="banner info fs-sm">${icon('info', 15)}<div>تُحفظ القيمة الأصلية التي أرسلها السائق، ويظهر التعديل كتسوية في دفتره.</div></div></div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ واعتماد', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) {
        var diff = BT.round3(f.cash - r.cash);
        r.orders = f.orders; r.cash = f.cash; r.status = 'معتمد';
        if (parent) parent.close();
        BT.toast('تم التعديل والاعتماد', { sub: diff ? 'تسوية ' + fmt.signed(diff) + ' د.ك في دفتر ' + r.driver : '' });
        A.router.refresh();
      }
    });
  };

  /* =================================================================
     الكاش والخزينة  #/cash?tab=balances|receipts|treasury
     ================================================================= */
  BT.pages['cash'] = function (p, q) {
    A.setTitle('الكاش والخزينة');
    var tab = q.tab || 'balances';
    var drivers = D.employees.filter(function (e) { return e.role === 'سائق' && (e.balance > 0 || e.vehicleId); });
    var total = BT.sum(drivers, function (e) { return e.balance; }), over = drivers.filter(function (e) { return e.balance > cfg.cashAlert; }).length;
    var todayRc = D.receipts.filter(function (r) { return r.date === cfg.today; });
    BT.render(A.view(), h`
      ${A.head('رصيد كل سائق واضح في أي لحظة', 'لا تحصيل على كل طلب: كاش التقرير اليومي يُضاف لرصيد السائق، والمحاسب يحصّل أي مبلغ في أي وقت',
        h`${A.btn('إيداع بنكي', { icon: 'landmark', cls: 'btn-outline', action: 'deposit' })}${A.btn('تسجيل تحصيل', { icon: 'hand-coins', cls: 'btn-primary', action: 'collect' })}`)}
      <div class="kpis">
        ${BT.kpi({ label: 'الكاش لدى السائقين', value: fmt.kwd(total), sub: over + ' سائقاً فوق حد التنبيه', dot: 'o' })}
        ${BT.kpi({ label: 'تحصيلات اليوم', value: fmt.kwd(BT.sum(todayRc, function (r) { return r.amount; })), sub: todayRc.length + ' إيصالاً', dot: 'g', tone: 'success' })}
        ${BT.kpi({ label: 'رصيد الخزينة', value: fmt.kwd(D.treasury.balance), sub: 'بعد إيداع ' + fmt.kwd(D.treasury.depositedToday), dot: 'b' })}
        ${BT.kpi({ label: 'حد التنبيه', value: fmt.kwd(cfg.cashAlert), sub: 'تنبيه فقط · لا يمنع السائق من العمل', dot: 'p' })}
      </div>
      ${BT.tabs('cash', [['balances', 'أرصدة السائقين'], ['receipts', 'الإيصالات', todayRc.length], ['treasury', 'الخزينة']], tab, 'tabs-line')}
      <div data-panel="balances" data-group="cash" class="${tab === 'balances' ? 'active' : ''}"><div class="card"><div id="bal-table"></div></div></div>
      <div data-panel="receipts" data-group="cash" class="${tab === 'receipts' ? 'active' : ''}"><div class="card"><div id="rc-table"></div></div></div>
      <div data-panel="treasury" data-group="cash" class="${tab === 'treasury' ? 'active' : ''}"><div class="grid" style="grid-template-columns:minmax(0,340px) minmax(0,1fr)">
        <div class="card"><div class="card-h"><div class="card-t">الخزينة اليوم</div><span class="card-meta">${fmt.dateLong(cfg.today)}</span></div>
          ${BT.kv([['رصيد أمس', BT.amt(D.treasury.yesterday)], ['تحصيلات اليوم', h`<span class="t-success">${BT.amt(D.treasury.collectedToday, { signed: true })}</span>`], ['إيداع بنكي', h`<span class="t-danger">${BT.amt(-D.treasury.depositedToday, { signed: true })}</span>`], ['الرصيد', BT.amt(D.treasury.balance), 'total']])}
          <div class="card-f">${A.btn('إيداع بنكي', { icon: 'landmark', cls: 'btn-primary btn-block', action: 'deposit' })}</div></div>
        <div class="card"><div class="card-h"><div class="card-t">الإيداعات البنكية</div></div>
          <div class="table-wrap"><table class="t"><thead><tr><th>الرقم</th><th>التاريخ</th><th>البنك</th><th>المرجع</th><th class="num">المبلغ</th><th>بواسطة</th><th></th></tr></thead><tbody>
          ${D.treasury.deposits.map(function (x) { return h`<tr><td class="num">${x.id}</td><td class="num">${fmt.date(x.date)}</td><td>${x.bank}</td><td class="num">${x.ref}</td><td class="num">${fmt.kwd(x.amount)}</td><td>${x.by}</td><td class="actions"><button type="button" class="btn btn-sm btn-ghost" data-dep="${x.id}">${icon('image', 14)} الإيصال</button></td></tr>`; })}
          </tbody></table></div></div></div></div>`);

    BT.table(document.getElementById('bal-table'), {
      rows: function () { return drivers; },
      sort: { key: 'balance', dir: 'desc' },
      search: { placeholder: 'ابحث بسائق…', text: function (e) { return e.name + ' ' + (e.vehicleId || ''); } },
      chips: { key: 'over', options: [{ v: 'over', t: 'فوق حد التنبيه' }, { v: 'today', t: 'لديه كاش اليوم غير معتمد' }], match: function (e, v) { return v === 'over' ? e.balance > cfg.cashAlert : !!(e.today && e.today.cash != null && e.today.status !== 'معتمد'); } },
      columns: [
        { key: 'name', label: 'السائق', render: function (e) { return BT.person(e.name, e.vehicleId || 'بلا سيارة'); } },
        { key: 'balance', label: 'الرصيد (د.ك)', num: true, render: function (e) { return e.balance > cfg.cashAlert ? h`<b class="t-warning">${fmt.kwd(e.balance)}</b>` : fmt.kwd(e.balance); } },
        { key: 'meter', label: 'من حد التنبيه', sort: function (e) { return e.balance; }, render: function (e) { var pc = Math.min(100, e.balance / cfg.cashAlert * 100); return h`<div class="meter ${pc >= 100 ? 'danger' : pc >= 85 ? 'warn' : ''}" style="width:110px" title="${Math.round(pc)}%"><i style="width:${pc.toFixed(0)}%"></i></div>`; } },
        { key: 'today', label: 'غير معتمد اليوم', num: true, sort: function (e) { return e.today && e.today.status !== 'معتمد' ? e.today.cash || 0 : 0; }, render: function (e) { return e.today && e.today.cash != null && e.today.status !== 'معتمد' ? fmt.kwd(e.today.cash) : '—'; } },
        { key: 'st', label: '', sort: false, render: function (e) { return e.balance > cfg.cashAlert ? BT.pill('فوق حد التنبيه', 'o') : ''; } },
        { key: '_a', label: '', sort: false, cls: 'actions', render: function (e) { return h`<button type="button" class="btn btn-sm btn-soft" data-collect="${e.id}">${icon('hand-coins', 14)} تحصيل</button>`; } }
      ],
      rowClick: function (e) { A.ledger(e); },
      rowMenu: function (e) { return [{ label: 'دفتر السائق', icon: 'book-open', onClick: function () { A.ledger(e); } }, { label: 'تسجيل تحصيل', icon: 'hand-coins', onClick: function () { A.collect(e); } }, { label: 'تسوية', icon: 'scale', onClick: function () { A.adjust(e); } }]; }
    });
    BT.table(document.getElementById('rc-table'), {
      rows: function () { return D.receipts; },
      search: { placeholder: 'رقم الإيصال أو السائق…', text: function (r) { return r.no + ' ' + r.driver; } },
      chips: { key: 'status', options: [{ v: 'مؤكد', t: 'مؤكد' }, { v: 'بانتظار تأكيد السائق', t: 'بانتظار تأكيد السائق' }, { v: 'ملغى', t: 'ملغى' }] },
      columns: [
        { key: 'no', label: 'رقم الإيصال', render: function (r) { return h`<b class="num">${r.no}</b>`; } },
        { key: 'date', label: 'التاريخ والوقت', render: function (r) { return h`<span class="num">${fmt.date(r.date)} ${r.time}</span>`; } },
        { key: 'driver', label: 'السائق', render: function (r) { return BT.person(r.driver); } },
        { key: 'amount', label: 'المبلغ (د.ك)', num: true, render: function (r) { return fmt.kwd(r.amount); } },
        { key: 'by', label: 'المحاسب', render: function (r) { return h`<bdi>${r.by}</bdi>`; } },
        { key: 'status', label: 'الحالة', render: function (r) { return BT.pill(r.status, r.status === 'مؤكد' ? 'g' : r.status === 'ملغى' ? 'r' : 'b'); } }
      ],
      rowClick: function (r) { A.receipt(r); },
      rowMenu: function (r) { return [{ label: 'عرض وطباعة', icon: 'printer', onClick: function () { A.receipt(r); } }, { sep: true }, { label: 'إلغاء الإيصال', icon: 'ban', danger: true, onClick: function () { A.cancelReceipt(r); } }]; }
    });
    BT.on(A.view(), 'click', '[data-collect]', function (ev, b) { A.collect(D.employees.find(function (e) { return e.id === b.getAttribute('data-collect'); })); });
    BT.on(A.view(), 'click', '[data-dep]', function (ev, b) { var x = D.treasury.deposits.find(function (d) { return d.id === b.getAttribute('data-dep'); }); A.docPreview('إيصال إيداع ' + x.ref, [['البنك', x.bank], ['رقم الحساب', '9615990019'], ['المبلغ', fmt.kwd(x.amount) + ' د.ك'], ['التاريخ', fmt.date(x.date)], ['المرجع', x.ref]]); });
  };

  /* ---------- دفتر السائق ---------- */
  A.ledger = function (e) {
    var L = D.ledger(e);
    var month = D.receipts.filter(function (r) { return r.empId === e.id && r.status !== 'ملغى'; });
    BT.drawer.open({
      title: h`دفتر كاش السائق — <bdi>${e.name}</bdi>`, subtitle: (e.vehicleId || 'بلا سيارة') + ' · ' + fmt.month(2026, 11), icon: 'book-open', size: 'lg',
      body: h`<div class="kpis mb-16">
          ${BT.kpi({ label: 'الرصيد الحالي', value: fmt.kwd(e.balance), sub: e.balance > cfg.cashAlert ? 'فوق حد التنبيه · تنبيه فقط' : 'ضمن الحد', dot: e.balance > cfg.cashAlert ? 'o' : 'g', tone: e.balance > cfg.cashAlert ? 'warning' : '' })}
          ${BT.kpi({ label: 'تحصيلات الشهر', value: fmt.kwd(BT.sum(month, function (r) { return r.amount; })), sub: month.length + (month.length === 2 ? ' إيصالان' : ' إيصال'), dot: 'g' })}
          ${BT.kpi({ label: 'غير معتمد', value: e.today && e.today.cash != null && e.today.status !== 'معتمد' ? fmt.kwd(e.today.cash) : '0.000', sub: 'من تقرير اليوم', dot: 'p' })}
          ${BT.kpi({ label: 'حد التنبيه', value: fmt.kwd(cfg.cashAlert), sub: 'لا يمنع السائق من العمل', dot: 'b' })}
        </div>
        <div class="table-wrap"><table class="t"><thead><tr><th>التاريخ</th><th>الحركة</th><th class="num">المبلغ</th><th class="num">الرصيد</th><th></th></tr></thead><tbody>
        ${L.map(function (x) {
          return h`<tr><td class="num">${fmt.dm(x.date)}</td><td>${x.text}</td><td class="num ${x.amount > 0 ? 't-success' : x.amount < 0 ? 't-danger' : ''}">${x.amount == null ? '' : fmt.signed(x.amount)}</td><td class="num"><b>${fmt.kwd(x.balance)}</b></td><td>${x.balance > cfg.cashAlert && x.amount > 0 ? BT.pill('فوق حد التنبيه', 'o') : x.note ? BT.pill(x.note, x.note === 'مؤكد' ? 'g' : x.note === 'بسبب مسجّل' ? 'n' : 'b') : ''}</td></tr>`;
        })}</tbody></table></div>
        <div class="banner info mt-16 fs-sm">${icon('info', 15)}<div>كل حركة تظهر للسائق في التطبيق. الإيصال يبقى «بانتظار تأكيد السائق» حتى يؤكد استلامه من هاتفه.</div></div>`,
      buttons: [{ label: 'تسوية', cls: 'btn-outline', icon: 'scale', onClick: function () { setTimeout(function () { A.adjust(e); }, 240); } }, { label: 'كشف PDF', cls: 'btn-ghost', icon: 'file-text', close: false, onClick: function () { A.exportToast('دفتر ' + e.name, 'PDF'); } }, { label: 'تسجيل تحصيل', cls: 'btn-primary', icon: 'hand-coins', onClick: function () { setTimeout(function () { A.collect(e); }, 240); } }]
    });
  };

  /* ---------- تسجيل تحصيل + الإيصال ---------- */
  BT.actions['collect'] = function () { A.collect(null); };
  A.collect = function (e) {
    var drivers = D.employees.filter(function (x) { return x.role === 'سائق' && x.balance > 0; }).sort(function (a, b) { return b.balance - a.balance; });
    var d = BT.modal.open({
      title: 'تسجيل تحصيل', icon: 'hand-coins', form: true,
      body: h`<div class="form">
        ${BT.f.select({ name: 'emp', label: 'السائق', required: true, value: e && e.id, options: drivers.map(function (x) { return { v: x.id, t: x.name + ' — الرصيد ' + fmt.kwd(x.balance) }; }) })}
        <div id="col-bal"></div>
        ${BT.f.money({ name: 'amount', label: 'المبلغ المستلم', required: true, min: 0.25, validate: 'collectMax', autofocus: !!e })}
        ${BT.f.input({ name: 'no', label: 'رقم الإيصال', value: String(D.nextReceipt), readonly: true, hint: 'يُرقّم تلقائياً ولا يتكرر' })}
        ${BT.f.textarea({ name: 'notes', label: 'ملاحظات', optional: true, rows: 2 })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'تحصيل وإصدار إيصال', cls: 'btn-primary', icon: 'receipt', submit: true }],
      onSubmit: function (f) {
        var emp = D.employees.find(function (x) { return x.id === f.emp; });
        var r = { id: D.nextReceipt, no: D.nextReceipt++, date: cfg.today, time: cfg.now, empId: emp.id, driver: emp.name, amount: BT.round3(f.amount), by: D.currentUser.name, status: 'بانتظار تأكيد السائق' };
        D.receipts.unshift(r); emp.balance = BT.round3(emp.balance - r.amount);
        D.treasury.collectedToday = BT.round3(D.treasury.collectedToday + r.amount); D.treasury.balance = BT.round3(D.treasury.balance + r.amount);
        setTimeout(function () { A.receipt(r, true); }, 240);
        if (/^cash|^dashboard/.test(A.router.current)) A.router.refresh();
      }
    });
    function showBal() {
      var emp = D.employees.find(function (x) { return x.id === d.el.querySelector('[name=emp]').value; });
      d.el.querySelector('[name=amount]').dataset.max = emp ? emp.balance : '';
      BT.render(d.el.querySelector('#col-bal'), emp ? h`<div class="highlight-box between"><span class="muted">الرصيد الحالي</span><b>${BT.amt(emp.balance)}</b></div>` : '');
    }
    d.el.querySelector('[name=emp]').addEventListener('change', showBal); showBal();
  };
  BT.validators.collectMax = function (v, el) { var m = +el.dataset.max, n = Number(v.replace(/,/g, '')); return m && n > m ? 'أكبر من رصيد السائق (' + fmt.kwd(m) + ')' : ''; };

  A.receiptHtml = function (r) {
    return h`<div class="receipt"><div class="r-head"><div><div style="font-weight:700;font-size:15px">${BT.config.client}</div><div style="color:#6B7385;font-size:11.5px">إيصال استلام نقدية</div></div><div style="text-align:left"><div style="color:#6B7385;font-size:11px">رقم</div><b class="num" style="font-size:18px">${r.no}</b></div></div>
      <div class="r-amt"><div style="color:#6B7385;font-size:12px">المبلغ المستلم</div><b class="num">${fmt.kwd(r.amount)}</b> <span style="color:#6B7385">د.ك</span></div>
      <div class="r-row"><span>من السائق</span><b><bdi>${r.driver}</bdi></b></div><div class="r-row"><span>التاريخ والوقت</span><span class="num">${fmt.date(r.date)} ${r.time}</span></div>
      <div class="r-row"><span>المحاسب</span><span><bdi>${r.by}</bdi></span></div><div class="r-row"><span>الحالة</span><span>${r.status}</span></div>
      <div class="r-sign"><div>توقيع المحاسب</div><div>توقيع السائق</div></div></div>`;
  };
  A.receipt = function (r, fresh) {
    BT.modal.open({
      title: fresh ? 'تم إصدار الإيصال' : 'إيصال ' + r.no, subtitle: fresh ? 'أُرسل للسائق ليؤكد الاستلام من التطبيق' : '', icon: fresh ? 'circle-check' : 'receipt', iconTone: fresh ? 'success' : '', size: 'sm',
      body: A.receiptHtml(r),
      buttons: [{ label: 'طباعة', cls: 'btn-outline', icon: 'printer', close: false, onClick: function () { BT.print(A.receiptHtml(r)); } }, { label: 'تم', cls: 'btn-primary' }]
    });
  };
  A.cancelReceipt = function (r) {
    BT.confirm({ title: 'إلغاء الإيصال ' + r.no, message: 'سيُعاد المبلغ ' + fmt.kwd(r.amount) + ' د.ك إلى رصيد ' + r.driver + '. الإيصال لا يُحذف ويبقى في السجل بحالة «ملغى».', confirmText: 'إلغاء الإيصال', cancelText: 'تراجع', tone: 'danger', reason: { label: 'سبب الإلغاء' }, typed: String(r.no) })
      .then(function (res) { if (!res.ok) return; r.status = 'ملغى'; var e = D.employees.find(function (x) { return x.id === r.empId; }); if (e) e.balance = BT.round3(e.balance + r.amount); BT.toast('تم إلغاء الإيصال ' + r.no, { type: 'warning', sub: res.reason }); A.router.refresh(); });
  };

  /* ---------- تسوية ---------- */
  A.adjust = function (e) {
    BT.modal.open({
      title: 'تسوية في دفتر السائق', subtitle: e.name + ' · الرصيد ' + fmt.kwd(e.balance), icon: 'scale', size: 'sm', form: true,
      body: h`<div class="form">${BT.f.radios({ name: 'dir', label: 'النوع', required: true, value: '-', options: [{ v: '-', t: 'خصم من الرصيد', d: 'مثال: خطأ في التقرير' }, { v: '+', t: 'إضافة للرصيد', d: 'مثال: كاش لم يُسجّل' }] })}
        ${BT.f.money({ name: 'amount', label: 'المبلغ', required: true, min: 0.25 })}
        ${BT.f.textarea({ name: 'reason', label: 'السبب', required: true })}
        <div class="banner info fs-sm">${icon('shield-check', 15)}<div>التسوية تحتاج اعتماد المحاسب الأول قبل أن تؤثر على الرصيد.</div></div></div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'إرسال للاعتماد', cls: 'btn-primary', submit: true }],
      onSubmit: function (f) { D.approvals.push({ id: 'AP-' + (D.approvals.length + 1), type: 'تسوية كاش', title: 'تسوية ' + (f.dir === '-' ? '−' : '+') + fmt.kwd(f.amount) + ' — ' + e.name, meta: f.reason, amount: f.amount, age: 'الآن', tone: 'n', link: 'cash' }); A.renderNav(A.router.current.split('/')[0]); BT.toast('أُرسلت التسوية للاعتماد', { sub: e.name + ' · ' + (f.dir === '-' ? '−' : '+') + fmt.kwd(f.amount) }); }
    });
  };

  /* ---------- إيداع بنكي ---------- */
  BT.actions['deposit'] = function () {
    BT.modal.open({
      title: 'إيداع بنكي', subtitle: 'رصيد الخزينة الآن ' + fmt.kwd(D.treasury.balance) + ' د.ك', icon: 'landmark', form: true,
      body: h`<div class="form-grid">
        ${BT.f.money({ name: 'amount', label: 'المبلغ', required: true, min: 1, max: D.treasury.balance, full: true })}
        ${BT.f.select({ name: 'bank', label: 'البنك', required: true, value: 'البنك التجاري الكويتي', options: ['البنك التجاري الكويتي', 'بنك الكويت الوطني', 'بيت التمويل الكويتي'] })}
        ${BT.f.date({ name: 'date', label: 'تاريخ الإيداع', required: true, value: cfg.today })}
        ${BT.f.input({ name: 'ref', label: 'رقم المرجع', required: true, placeholder: 'CBK-…', full: true })}
        ${BT.f.upload({ name: 'slip', label: 'صورة إيصال الإيداع', required: true, full: true, accept: 'image/*,application/pdf' })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'تسجيل الإيداع', cls: 'btn-primary', submit: true, icon: 'check' }],
      onSubmit: function (f) {
        D.treasury.deposits.unshift({ id: 'DP-' + (1189 + D.treasury.deposits.length - 3), date: f.date, amount: f.amount, bank: f.bank, ref: f.ref, by: D.currentUser.name });
        D.treasury.depositedToday = BT.round3(D.treasury.depositedToday + f.amount); D.treasury.balance = BT.round3(D.treasury.balance - f.amount);
        BT.toast('تم تسجيل إيداع ' + fmt.kwd(f.amount) + ' د.ك', { sub: f.bank + ' · ' + f.ref });
        if (A.router.current === 'cash') A.go('cash?tab=treasury');
      }
    });
  };
})();
