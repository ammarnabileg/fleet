/* =====================================================================
   app/pages/home.js — لوحة التحكم (#/dashboard)
   كل رقم من /api/v1/dashboard، وكل قسم يظهر حسب صلاحيات المستخدم.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  BT.pages['dashboard'] = function () {
    A.setTitle('لوحة التحكم');
    var v = A.view();
    var hour = +new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kuwait', hour: '2-digit', hourCycle: 'h23' }).format(new Date());
    var jobs = [api.get('/dashboard'), api.get('/alerts', { limit: 8 })];
    jobs.push(api.can('documents.view') ? Promise.all([api.get('/documents/expiring', { within_days: 30 }), A.docTypes()]).then(function (x) { return x[0]; }) : Promise.resolve(null));
    A.load(v, Promise.all(jobs), function (r) {
      var d = r[0], alerts = r[1], docs = r[2];
      var veh = d.vehicles, drv = d.drivers, rep = d.daily_reports, cash = d.cash;
      var total = veh ? Object.keys(veh).reduce(function (s, k) { return s + veh[k]; }, 0) : 0;
      var rows = [];
      var row1 = [];
      if (veh) row1.push(BT.kpi({ label: 'سيارات في العهدة', value: h`${fmt.int(veh.assigned)}<small> / ${fmt.int(total)}</small>`, sub: fmt.int(veh.available) + ' متاحة · ' + fmt.int(veh.maintenance) + ' في الصيانة', dot: 'g', href: '#/vehicles' }));
      if (drv) row1.push(BT.kpi({ label: 'سائقون في العهدة الآن', value: fmt.int(drv.on_duty), sub: drv.signal_lost != null ? fmt.int(drv.signal_lost) + ' انقطعت إشارتهم' : '', dot: 'b', href: api.can('tracking.live') ? '#/tracking' : '#/custody' }));
      if (drv && drv.signal_lost != null) row1.push(BT.kpi({ label: 'انقطاع إشارة', value: fmt.int(drv.signal_lost), sub: 'خلال العهدة، الآن', dot: 'r', tone: drv.signal_lost ? 'danger' : null, href: '#/tracking' }));
      if (rep) row1.push(BT.kpi({ label: 'تقارير اليوم', value: h`${fmt.int(rep.today_sent)}${rep.drivers_on_duty != null ? h`<small> / ${fmt.int(rep.drivers_on_duty)}</small>` : ''}`, sub: fmt.int(rep.waiting_review) + ' بانتظار المراجعة' + (rep.overdue ? ' · ' + fmt.int(rep.overdue) + ' متأخرة' : ''), dot: 'p', href: '#/daily' }));
      if (row1.length) rows.push(h`<div class="kpis">${row1}</div>`);
      var row2 = [];
      if (rep) row2.push(BT.kpi({ label: 'طلبات اليوم', value: fmt.int(rep.today_orders), sub: 'من التقارير المرسلة', dot: 'o', href: '#/daily' }));
      if (rep) row2.push(BT.kpi({ label: 'الكاش المُبلّغ اليوم', value: fmt.money(rep.today_cash), sub: BT.config.currency, dot: 'g', href: '#/daily' }));
      if (cash) row2.push(BT.kpi({ label: 'الكاش لدى السائقين', value: fmt.money(cash.held_by_drivers), sub: fmt.int(cash.over_limit) + ' فوق حد ' + fmt.money(cash.limit) + ' · منه غير معتمد ' + fmt.money(cash.unapproved), dot: 'o', tone: cash.over_limit ? 'warning' : null, href: '#/cash' }));
      if (cash) row2.push(BT.kpi({ label: 'أُودع بإيصالات اليوم', value: fmt.money(cash.deposited_today), sub: BT.config.currency, dot: 'g', tone: 'success', href: '#/cash?tab=receipts' }));
      if (row2.length) rows.push(h`<div class="kpis">${row2}</div>`);
      var mnt = d.maintenance;
      if (mnt) rows.push(h`<div class="kpis">
        ${BT.kpi({ label: 'صيانة بانتظار القرار', value: fmt.int(mnt.pending_approval), sub: 'طلبات وعروض أسعار فوق الحد', dot: 'o', tone: mnt.pending_approval ? 'warning' : null, href: '#/maintenance?status=pending' })}
        ${BT.kpi({ label: 'تحت الإصلاح', value: fmt.int(mnt.under_repair), sub: fmt.int(mnt.referred) + ' محالة لم تصل المركز بعد', dot: 'p', href: '#/maintenance?status=at_center' })}
        ${BT.kpi({ label: 'جاهزة للاستلام', value: fmt.int(mnt.ready), sub: 'من مراكز الصيانة', dot: 'g', tone: mnt.ready ? 'success' : null, href: '#/maintenance?status=ready' })}
      </div>`);
      var acc = d.accidents;
      if (acc) rows.push(h`<div class="kpis">
        ${BT.kpi({ label: 'حوادث مفتوحة', value: fmt.int(acc.open), sub: fmt.int(acc.this_month) + ' هذا الشهر', dot: 'r', href: '#/accidents' })}
        ${BT.kpi({ label: 'بلا محضر شرطة', value: fmt.int(acc.no_police_report), sub: 'لا تُحدد المسؤولية قبله', dot: 'o', tone: acc.no_police_report ? 'warning' : null, href: '#/accidents?chip=police' })}
        ${BT.kpi({ label: 'تقديرات بانتظار الاعتماد', value: fmt.int(acc.estimate_pending), sub: 'من مراكز الصيانة', dot: 'p', href: '#/accidents?chip=estimate' })}
        ${BT.kpi({ label: 'بانتظار تحديد المسؤولية', value: fmt.int(acc.awaiting_outcome), sub: 'التقدير معتمد', dot: 'b', href: '#/accidents?chip=outcome' })}
      </div>`);
      var fin = d.fines;
      if (fin) rows.push(h`<div class="kpis">
        ${BT.kpi({ label: 'مخالفات بانتظار القرار', value: fmt.int(fin.open), sub: fin.no_driver ? fmt.int(fin.no_driver) + ' بلا سائق وقت المخالفة' : 'خصم من السائق أو على الشركة', dot: 'o', tone: fin.no_driver ? 'warning' : null, href: '#/fines' })}
        ${BT.kpi({ label: 'غير مدفوعة للمرور', value: fmt.int(fin.unpaid), sub: fmt.money(fin.unpaid_total) + ' ' + BT.config.currency, dot: 'r', href: '#/fines?chip=unpaid' })}
      </div>`);

      var a = d.alerts;
      var alertCard = h`<div class="card"><div class="card-h"><div class="card-t">تنبيهات مفتوحة</div><span class="flex gap-8">${a.critical ? BT.pill(a.critical + ' حرج', 'r') : ''}${a.warning ? BT.pill(a.warning + ' تحذير', 'o') : ''}${a.info ? BT.pill(a.info + ' معلومة', 'b') : ''}</span></div>
        ${alerts.length ? h`<div class="list">${alerts.map(function (x) { return h`<a class="li" href="#/alerts"><span class="li-ic ${{ critical: 'r', warning: 'o', info: 'b' }[x.severity]}">${icon(x.severity === 'critical' ? 'siren' : x.severity === 'warning' ? 'triangle-alert' : 'info', 16)}</span><div class="li-main"><div class="li-t">${x.message}</div><div class="li-d">${fmt.since(x.created_at)}</div></div></a>`; })}</div><div class="mt-8"><a class="link-row" href="#/alerts">كل التنبيهات ${icon('arrow-left', 14)}</a></div>` : BT.empty('circle-check', 'لا توجد تنبيهات مفتوحة', '')}</div>`;
      var docCard = docs ? h`<div class="card"><div class="card-h"><div class="card-t">${icon('file-clock', 17)} مستندات تنتهي خلال 30 يوماً</div><span class="card-meta">${d.documents ? fmt.int(d.documents.expiring) + ' قريباً · ' + fmt.int(d.documents.expired) + ' منتهية' : ''}</span></div>
        ${docs.length ? h`<div class="list">${docs.slice(0, 6).map(function (x) { var n = BT.date.daysLeft(x.expiry_date); return h`<a class="li" href="${x.owner_type === 'vehicle' ? '#/vehicles/' + x.owner_id : '#/employees?tab=docs'}"><span class="li-ic ${n < 0 ? 'r' : ''}">${icon(x.owner_type === 'vehicle' ? 'car' : x.owner_type === 'company' ? 'building-2' : 'file-badge', 16)}</span><div class="li-main"><div class="li-t"><bdi>${api.name(x.owner_name) || '—'}</bdi></div><div class="li-d">${A.docTypeName(x.type_code)} · <span class="num">${fmt.date(x.expiry_date)}</span></div></div>${BT.pill(fmt.daysLabel(n), n < 0 ? 'r' : n <= 15 ? 'o' : 'b')}</a>`; })}</div>` : BT.empty('circle-check', 'لا شيء ينتهي قريباً', '')}</div>` : '';
      var quick = [];
      if (api.can('custody.assign')) quick.push(['#/custody?new=1', 'key-round', 'تسليم سيارة لسائق']);
      if (api.can('odometer.review')) quick.push(['#/odometer', 'gauge', 'مراجعة قراءات العداد']);
      if (api.can('daily_reports.review')) quick.push(['#/daily', 'clipboard-check', 'مراجعة التقارير اليومية']);
      if (api.can('cash.collect')) quick.push(['#/cash?tab=receipts', 'hand-coins', 'استلام كاش بإيصال']);
      if (api.can('employees.onboarding')) quick.push(['#/employees?tab=reg', 'user-round-check', 'طلبات التسجيل']);
      var quickCard = quick.length ? h`<div class="card"><div class="card-h"><div class="card-t">${icon('list-checks', 17)} إجراءات سريعة</div></div><div class="list">${quick.map(function (x) { return h`<a class="li" href="${x[0]}"><span class="li-ic b">${icon(x[1], 16)}</span><div class="li-main"><div class="li-t">${x[2]}</div></div>${icon('chevron-left', 14)}</a>`; })}</div></div>` : '';
      var weekCard = d.week ? h`<div class="card mb-16"><div class="card-h"><div><div class="card-t" data-week-title>الطلبات — آخر 7 أيام</div><div class="card-meta">من التقارير اليومية غير المرفوضة، كما تُحسب أرقام اليوم</div></div>
          <div class="flex gap-8 items-center">${BT.tabs('dash-week', [['orders', 'الطلبات'], ['cash', 'الكاش المُبلّغ']], 'orders')}
          <button type="button" class="icon-btn sm sq" data-week-table data-tip="عرض كجدول" aria-label="عرض كجدول">${icon('table-2', 16)}</button></div></div>
        <div data-week-chart></div></div>` : '';
      return h`${A.head((hour < 12 ? 'صباح الخير' : 'مساء الخير') + '، ' + api.me.full_name.split(' ')[0], 'ملخص اليوم ' + fmt.dateLong(BT.config.today) + ' · آخر تحديث ' + fmt.time(d.as_of), A.btn('تحديث', { icon: 'refresh-cw', cls: 'btn-outline', action: 'reload' }))}
        ${rows}
        ${weekCard}
        <div class="grid" style="grid-template-columns:minmax(0,1.3fr) minmax(0,1fr)">${alertCard}<div class="grid" style="gap:16px">${docCard}${quickCard}</div></div>`;
    }).then(function (r) { if (r && r[0].week) week(v, r[0].week); }).catch(function () {});
  };

  /* آخر 7 أيام: الطلبات أو الكاش المُبلّغ لكل يوم، ورسمٌ يُعرض جدولاً لمن يريد الأرقام */
  function week(v, days) {
    var el = v.querySelector('[data-week-chart]'), metric = 'orders';
    if (!el) return;
    function draw() {
      var orders = metric === 'orders';
      BT.chart.bars(el, {
        name: orders ? 'الطلبات آخر 7 أيام' : 'الكاش المُبلّغ آخر 7 أيام',
        labels: days.map(function (x) { return BT.date.dayName(x.day); }), sublabels: days.map(function (x) { return fmt.dm(x.day); }),
        values: days.map(function (x) { return orders ? x.orders : Number(x.cash); }),
        format: orders ? fmt.int : fmt.money, unitLabel: orders ? 'طلب' : BT.config.currency, height: 230
      });
      v.querySelector('[data-week-title]').textContent = orders ? 'الطلبات — آخر 7 أيام' : 'الكاش المُبلّغ (' + BT.config.currency + ') — آخر 7 أيام';
    }
    draw();
    v.querySelector('[data-tabs="dash-week"]').addEventListener('bt:tab', function (e) { metric = e.detail; draw(); });
    v.querySelector('[data-week-table]').addEventListener('click', function () {
      BT.modal.open({
        title: 'آخر 7 أيام', icon: 'table-2',
        body: BT.chart.table(['اليوم', 'التقارير', 'الطلبات', 'الكاش المُبلّغ'], days.map(function (x) { return [BT.date.dayName(x.day) + ' ' + fmt.dm(x.day), fmt.int(x.reports), fmt.int(x.orders), fmt.money(x.cash)]; })),
        buttons: [{ label: 'إغلاق', cls: 'btn-primary' }]
      });
    });
  }
})();
