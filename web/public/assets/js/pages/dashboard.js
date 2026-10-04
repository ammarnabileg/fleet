/* =====================================================================
   صفحة: لوحة التحكم  (#/dashboard)
   بوب أب: تفاصيل التنبيه (drawer) · إغلاق التنبيه بسبب (confirm)
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, D = BT.data, A = BT.A;

  BT.pages['dashboard'] = function () {
    A.setTitle('لوحة التحكم');
    var st = D.reportStats();
    var active = D.vehicles.filter(function (v) { return v.status === 'مسلّمة'; }).length;
    var maint = D.vehicles.filter(function (v) { return v.status === 'في الصيانة'; }).length;
    var idle = D.vehicles.filter(function (v) { return v.status === 'بلا سائق'; }).length;
    var cash = BT.sum(D.employees, function (e) { return e.balance; });
    var over = D.employees.filter(function (e) { return e.balance > BT.config.cashAlert; }).length;
    var lost = D.vehicles.filter(function (v) { return v.signal === 'انقطاع'; }).length;
    var todayRc = D.receipts.filter(function (r) { return r.date === BT.config.today; });
    var hour = +BT.config.now.split(':')[0];

    BT.render(A.view(), h`
      ${A.head((hour < 12 ? 'صباح الخير' : 'مساء الخير') + '، ' + D.currentUser.name.split(' ')[0], 'ملخص تشغيل ' + BT.config.client + ' اليوم ' + fmt.dateLong(BT.config.today) + ' · آخر تحديث ' + BT.config.now,
        h`${A.btn('تحديث', { icon: 'refresh-cw', cls: 'btn-outline', action: 'dash-refresh' })}${A.btn('تصدير ملخص اليوم', { icon: 'download', cls: 'btn-primary', action: 'export', arg: 'ملخص اليوم' })}`)}
      <div class="kpis">
        ${BT.kpi({ label: 'السيارات النشطة', value: h`${active}<small> / ${D.vehicles.length}</small>`, sub: maint + ' في الصيانة · ' + idle + ' بلا سائق', dot: 'g', href: '#/vehicles' })}
        ${BT.kpi({ label: 'بدؤوا يومهم اليوم', value: h`${st.started}<small> / ${active}</small>`, sub: 'سائقاً لديهم سيارة مسلّمة', dot: 'b', href: '#/daily' })}
        ${BT.kpi({ label: 'تقارير اليوم', value: fmt.int(st.sent), sub: st.approved + ' معتمد · ' + st.review + ' قيد المراجعة · ' + st.late + ' متأخر', dot: 'p', href: '#/daily' })}
        ${BT.kpi({ label: 'طلبات اليوم', value: fmt.int(st.orders), sub: 'من التقارير المرسلة', dot: 'o', href: '#/reports' })}
      </div>
      <div class="kpis">
        ${BT.kpi({ label: 'الكاش لدى السائقين', value: fmt.kwd(cash), sub: over + ' سائقاً فوق حد التنبيه', dot: 'o', href: '#/cash' })}
        ${BT.kpi({ label: 'تحصيلات اليوم', value: fmt.kwd(BT.sum(todayRc, function (r) { return r.amount; })), sub: todayRc.length + ' إيصالاً', dot: 'g', tone: 'success', href: '#/cash?tab=receipts' })}
        ${BT.kpi({ label: 'رصيد الخزينة', value: fmt.kwd(D.treasury.balance), sub: 'بعد إيداع ' + fmt.kwd(D.treasury.depositedToday), dot: 'b', href: '#/cash?tab=treasury' })}
        ${BT.kpi({ label: 'انقطاع إشارة', value: String(lost), sub: 'الآن، خلال فترة التسليم', dot: 'r', tone: 'danger', href: '#/tracking?signal=انقطاع' })}
      </div>
      <div class="grid" style="grid-template-columns:minmax(0,1.35fr) minmax(0,1fr)">
        <div class="card">
          <div class="card-h"><div><div class="card-t" id="chart-title">الطلبات — آخر 7 أيام</div><div class="card-meta">مجموع كل التقارير المرسلة في اليوم</div></div>
            <div class="flex gap-8 items-center">${BT.tabs('dash-metric', [['orders', 'الطلبات'], ['cash', 'الكاش المُبلّغ']], 'orders')}
            <button type="button" class="icon-btn sm sq" data-action="dash-table" data-tip="عرض كجدول" aria-label="عرض كجدول">${icon('table-2', 16)}</button></div></div>
          <div id="dash-chart"></div>
        </div>
        <div class="card">
          <div class="card-h"><div class="card-t">تنبيهات مفتوحة</div><span class="card-meta">حسب الخطورة</span></div>
          <div class="list">${D.alerts.map(function (a) {
            return h`<button type="button" class="li" data-action="alert-open" data-arg="${a.id}"><span class="li-ic ${a.tone}">${icon(a.tone === 'r' ? 'wifi-off' : a.tone === 'o' ? 'triangle-alert' : 'info', 16)}</span><div class="li-main"><div class="li-t">${a.text}</div><div class="li-d">اليوم ${a.at}</div></div>${BT.pill(a.level, a.tone)}</button>`;
          })}</div>
        </div>
      </div>
      <div class="grid-3">
        <div class="card"><div class="card-h"><div class="card-t">${icon('badge-check', 17)} بانتظار اعتمادك</div><a class="link-row" href="#/approvals">الكل ${icon('arrow-left', 14)}</a></div>
          <div class="list">${D.approvals.slice(0, 4).map(function (x) {
            return h`<a class="li" href="#/approvals"><div class="li-main"><div class="li-t">${x.title}</div><div class="li-d">${x.type} · ${x.age}</div></div>${x.amount != null ? BT.amt(x.amount) : BT.pill('مراجعة', x.tone)}</a>`;
          })}</div></div>
        <div class="card"><div class="card-h"><div class="card-t">${icon('file-clock', 17)} مستندات تنتهي خلال 30 يوماً</div><span class="card-meta">${D.docsExpiring(30).length + D.vehDocsExpiring(30).length} مستنداً</span></div>
          <div class="list">${D.vehDocsExpiring(30).slice(0, 1).map(function (d) { return h`<a class="li" href="#/vehicles/${A.slug(d.v.plate)}"><span class="li-ic b">${icon('car', 16)}</span><div class="li-main"><div class="li-t">${d.type} ${BT.plate(d.v.plate)}</div><div class="li-d">${fmt.date(d.exp)}</div></div>${BT.pill(fmt.daysLabel(d.days), d.days <= 15 ? 'o' : 'b')}</a>`; })}
          ${D.docsExpiring(30).slice(0, 3).map(function (d) { return h`<button type="button" class="li" data-action="employee-open" data-arg="${d.emp.id}"><span class="li-ic">${icon('file-badge', 16)}</span><div class="li-main"><div class="li-t">${d.type} — <bdi>${d.emp.name}</bdi></div><div class="li-d">${fmt.date(d.exp)}</div></div>${BT.pill(fmt.daysLabel(d.days), d.days <= 15 ? 'o' : 'b')}</button>`; })}</div></div>
        <div class="card"><div class="card-h"><div class="card-t">${icon('wrench', 17)} الصيانة الآن</div><a class="link-row" href="#/maintenance">التفاصيل ${icon('arrow-left', 14)}</a></div>
          ${BT.kv(D.stages.slice(0, 7).map(function (s) { var n = D.jobs.filter(function (j) { return j.stage === s; }).length; return [h`<span class="flex items-center gap-8"><span class="sdot ${D.stageTone[s]}"></span>${s}</span>`, h`<b class="num">${n}</b>`]; }))}
        </div>
      </div>`);

    var metric = 'orders';
    var chartEl = document.getElementById('dash-chart');
    var draw = function () {
      var H = D.history;
      BT.chart.bars(chartEl, {
        name: metric === 'orders' ? 'الطلبات آخر 7 أيام' : 'الكاش المبلّغ آخر 7 أيام',
        labels: H.days.map(BT.date.dayName), sublabels: H.days.map(fmt.dm),
        values: metric === 'orders' ? H.orders : H.cash,
        format: metric === 'orders' ? fmt.int : fmt.kwd, unitLabel: metric === 'orders' ? 'طلب' : 'د.ك',
        tickFormat: metric === 'orders' ? fmt.int : function (v) { return fmt.int(v); }, height: 230
      });
      document.getElementById('chart-title').textContent = metric === 'orders' ? 'الطلبات — آخر 7 أيام' : 'الكاش المُبلّغ (د.ك) — آخر 7 أيام';
    };
    draw();
    A.view().querySelector('[data-tabs="dash-metric"]').addEventListener('bt:tab', function (e) { metric = e.detail; draw(); });
    BT.actions['dash-table'] = function () {
      var H = D.history;
      BT.modal.open({
        title: 'آخر 7 أيام — عرض جدولي', icon: 'table-2',
        body: BT.chart.table(['اليوم', 'الطلبات', 'الكاش المُبلّغ (د.ك)'], H.days.map(function (d, i) { return [BT.date.dayName(d) + ' ' + fmt.dm(d), fmt.int(H.orders[i]), fmt.kwd(H.cash[i])]; })),
        buttons: [{ label: 'تصدير Excel', cls: 'btn-outline', icon: 'file-spreadsheet', onClick: function () { A.exportToast('آخر 7 أيام'); } }, { label: 'إغلاق', cls: 'btn-primary' }]
      });
    };
  };

  BT.actions['dash-refresh'] = function (a, el) {
    el.classList.add('is-loading');
    setTimeout(function () { el.classList.remove('is-loading'); BT.toast('تم تحديث البيانات', { sub: 'آخر تحديث ' + BT.config.now }); }, 700);
  };

  /* ---------- تفاصيل التنبيه ---------- */
  BT.actions['alert-open'] = function (id) {
    var a = D.alerts.find(function (x) { return x.id === id; });
    var d = BT.drawer.open({
      title: 'تفاصيل التنبيه', subtitle: a.id + ' · اليوم ' + a.at, icon: a.tone === 'r' ? 'wifi-off' : 'triangle-alert', iconTone: a.tone === 'r' ? 'danger' : a.tone === 'o' ? 'warn' : '',
      body: h`<div class="banner ${a.tone === 'r' ? 'danger' : a.tone === 'o' ? 'warn' : 'info'}">${icon('bell-ring', 16)}<div><b>${a.level}</b> — ${a.text}</div></div>
        <div class="section-t mt-16">التفاصيل</div>
        ${BT.kv([['النوع', a.link === 'tracking' ? 'انقطاع إشارة الهاتف' : a.link === 'odometer' ? 'فرق عداد بين يومين' : a.link === 'cash' ? 'رصيد فوق حد التنبيه' : a.link === 'approvals' ? 'اعتماد معلّق' : 'انتهاء مستند'], ['وقت التنبيه', 'اليوم ' + a.at], ['أُرسل إلى', 'المشرف المناوب · مدير العمليات'], ['الحالة', BT.pill('مفتوح', 'o')]])}
        <div class="section-t mt-16">ما المطلوب؟</div>
        <div class="fs-sm text-2" style="line-height:1.8">${a.link === 'tracking' ? 'تواصل مع السائق للتأكد أن الهاتف يعمل وأن تطبيق السائق مفتوح. إذا استُخدمت السيارة دون الهاتف ستظهر المسافة في سلسلة العداد.' : a.link === 'odometer' ? 'راجع صورتي العداد عند الإرجاع والاستلام، وسجّل القرار مع السبب. التنبيه يظهر باسم المسلِّم والمستلِم.' : a.link === 'cash' ? 'سجّل تحصيلاً من السائق. حد التنبيه لا يوقف السائق عن العمل.' : 'افتح السجل واتخذ الإجراء المناسب.'}</div>
        <div class="section-t mt-16">السجل</div>
        <div class="timeline">
          <div class="tl-item"><span class="tl-ic o">${icon('bell', 13)}</span><div><div class="tl-t">أُنشئ التنبيه تلقائياً</div><div class="tl-d">اليوم ${a.at}</div></div></div>
          <div class="tl-item"><span class="tl-ic pending"></span><div><div class="tl-t muted">بانتظار إجراء</div></div></div>
        </div>`,
      buttons: [
        { label: 'إغلاق التنبيه', cls: 'btn-ghost', icon: 'circle-check', close: false, onClick: function () {
          BT.confirm({ title: 'إغلاق التنبيه', message: 'سيُسجَّل اسمك ووقت الإغلاق والسبب في سجل التدقيق.', confirmText: 'إغلاق التنبيه', tone: 'success', reason: { label: 'سبب الإغلاق', placeholder: 'مثال: تواصلت مع السائق، الهاتف كان بدون شحن' } })
            .then(function (r) { if (r.ok) { D.alerts = D.alerts.filter(function (x) { return x.id !== id; }); d.close(); BT.toast('تم إغلاق التنبيه', { sub: r.reason }); if (A.router.current === 'dashboard') A.router.refresh(); } });
        } },
        { label: 'إسناد', cls: 'btn-outline', icon: 'user-round-check', close: false, onClick: function (api) {
          BT.menu(api.btn(1), [{ head: 'إسناد إلى' }, { label: 'فهد الرشيدي', icon: 'user-round', onClick: function () { BT.toast('تم إسناد التنبيه إلى فهد الرشيدي'); } }, { label: 'يوسف الكندري', icon: 'user-round', onClick: function () { BT.toast('تم إسناد التنبيه إلى يوسف الكندري'); } }]);
        } },
        { label: 'فتح السجل', cls: 'btn-primary', icon: 'arrow-left', onClick: function () { A.go(a.link); } }
      ]
    });
  };
})();
