/* =====================================================================
   app/pages/home.js — لوحة التحكم (#/dashboard)
   كل رقم من /api/v1/dashboard، وكل قسم يظهر حسب صلاحيات المستخدم. ثلاثة مستويات:
   1) الآن: أهم المؤشرات (حتى 8) والإجراءات السريعة؛
   2) الاتجاهات والاستثناءات: آخر 7 أيام، ما يحتاج تدخلاً، التنبيهات، المستندات؛
   3) التفاصيل حسب المجال: المؤشرات الثانوية مجمّعة (تُطوى وتُفتح، ويُحفظ اختيارك على هذا الجهاز).
   الضغط على أي رقم يفتح السجلات التي يعدّها: صفحة مفلترة، أو قائمة السجلات نفسها حين لا تفلتر صفحةٌ بها.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  BT.pages['dashboard'] = function () {
    A.setTitle('لوحة التحكم');
    var v = A.view();
    function fetch() {
      var jobs = [api.get('/dashboard'), api.get('/alerts', { limit: 8, sort: 'severity' })];
      jobs.push(api.can('documents.view') ? Promise.all([api.get('/documents/expiring', { within_days: 30 }), A.docTypes()]).then(function (x) { return x[0]; }) : Promise.resolve(null));
      return Promise.all(jobs);
    }
    A.load(v, fetch(), draw).then(function (r) { if (r && r[0].week) week(v, r[0].week); }).catch(function () {});
    // a new alert redraws it in place: no spinner, no jump to the top
    A._dashboardRedraw = function () {
      return fetch().then(function (r) { if (!document.contains(v)) return; BT.render(v, draw(r)); if (r[0].week) week(v, r[0].week); }, function () {});
    };
    A.onLeave(function () { A._dashboardRedraw = null; });
  };

  /* رقم يفتح ما يعدّه: href لصفحة مفلترة، أو drill لقائمة السجلات نفسها */
  function kpi(o) {
    if (o.drill) { o.action = 'dash-drill'; o.arg = o.drill; }
    return BT.kpi(o);
  }
  function group(id, title, ic, note, body) {
    if (!body || !String(body)) return '';
    var open = (BT.store.get('dash-open', {}) || {})[id];
    return h`<details class="card dash-group" data-group="${id}"${open ? raw(' open') : ''}><summary><span class="dash-group-t">${icon(ic, 17)} ${title}</span><span class="card-meta">${note}</span>${icon('chevron-down', 16, 'dash-chev')}</summary><div class="dash-group-b">${body}</div></details>`;
  }
  document.addEventListener('toggle', function (e) {
    var d = e.target;
    if (!d.matches || !d.matches('details.dash-group')) return;
    var s = BT.store.get('dash-open', {}) || {}; s[d.getAttribute('data-group')] = d.open; BT.store.set('dash-open', s);
  }, true);

  function draw(r) {
    var d = r[0], alerts = r[1], docs = r[2];
    var veh = d.vehicles, drv = d.drivers, rep = d.daily_reports, cash = d.cash, mnt = d.maintenance, acc = d.accidents, fin = d.fines;
    var today = BT.config.today, cur = BT.config.currency;
    var hour = +new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kuwait', hour: '2-digit', hourCycle: 'h23' }).format(new Date());
    var total = veh ? Object.keys(veh).reduce(function (s, k) { return s + veh[k]; }, 0) : 0;
    var a = d.alerts, openAlerts = a.critical + a.warning + a.info;

    /* ---- 1) الآن ---- */
    var top = [];
    if (veh) top.push(kpi({ label: 'سيارات في العهدة', value: h`${fmt.int(veh.assigned)}<small> / ${fmt.int(total)}</small>`, sub: fmt.int(veh.available) + ' متاحة · ' + fmt.int(veh.maintenance) + ' في الصيانة', dot: 'g', href: '#/vehicles?status=assigned' }));
    if (drv) top.push(kpi({ label: 'سائقون في العهدة الآن', value: fmt.int(drv.on_duty), sub: drv.signal_lost != null ? fmt.int(drv.signal_lost) + ' انقطعت إشارتهم' : 'عهد مفتوحة', dot: 'b', href: '#/custody?view=open' }));
    if (rep) top.push(kpi({ label: 'تقارير اليوم', value: h`${fmt.int(rep.today_sent)}${rep.drivers_on_duty != null ? h`<small> / ${fmt.int(rep.drivers_on_duty)}</small>` : ''}`, sub: fmt.int(rep.today_approved) + ' معتمدة · ' + fmt.int(rep.waiting_review) + ' بانتظار المراجعة', dot: 'p', drill: 'reports_today' }));
    if (rep) top.push(kpi({ label: 'طلبات اليوم', value: fmt.int(rep.today_orders), sub: 'كاش مُبلّغ ' + fmt.money(rep.today_cash) + ' ' + cur, dot: 'o', drill: 'reports_today' }));
    if (d.driver_cash) {
      var dc = d.driver_cash;
      top.push(kpi({ label: 'أرصدة كاش السائقين', value: fmt.money(dc.net), sub: h`<span data-cash-split>على السائقين ${fmt.money(dc.owed_by_drivers)} (${fmt.int(dc.drivers_owing)}) · للسائقين ${fmt.money(dc.owed_to_drivers)} (${fmt.int(dc.drivers_owed)}) · الصافي</span>`, dot: 'o', tone: cash && cash.over_limit ? 'warning' : null, href: '#/cash' }));
    } else if (cash) {
      top.push(kpi({ label: 'الكاش لدى السائقين', value: fmt.money(cash.held_by_drivers), sub: fmt.int(cash.over_limit) + ' فوق حد ' + fmt.money(cash.limit) + ' · منه غير معتمد ' + fmt.money(cash.unapproved), dot: 'o', tone: cash.over_limit ? 'warning' : null, href: '#/cash' }));
    }
    if (d.approvals) top.push(kpi({ label: 'اعتمادات بانتظارك', value: fmt.int(d.approvals.waiting), sub: d.approvals.oldest ? h`أقدمها ${fmt.agoEl(d.approvals.oldest)}` : 'لا شيء ينتظر قرارك', dot: 'p', tone: d.approvals.waiting ? 'warning' : null, href: '#/approvals' }));
    top.push(kpi({ label: 'تنبيهات مفتوحة', value: fmt.int(openAlerts), sub: openAlerts ? h`${fmt.int(a.critical)} حرجة · ${fmt.int(a.warning)} تحذير${d.alerts_oldest ? h` · أقدمها ${fmt.agoEl(d.alerts_oldest)}` : ''}` : 'لا شيء مفتوح', dot: 'r', tone: a.critical ? 'danger' : null, href: a.critical ? '#/alerts?status=open&severity=critical' : '#/alerts' }));
    if (d.documents) top.push(kpi({ label: 'مستندات منتهية', value: fmt.int(d.documents.expired), sub: fmt.int(d.documents.expiring) + ' تنتهي قريباً', dot: 'r', tone: d.documents.expired ? 'danger' : null, href: '#/employees?tab=docs&days=30' }));

    var quick = [];
    if (api.can('custody.assign')) quick.push(['#/custody?new=1', 'key-round', 'تسليم سيارة لسائق']);
    if (api.can('cash.collect')) quick.push(['#/cash?tab=receipts', 'hand-coins', 'استلام كاش بإيصال']);
    if (api.can('daily_reports.review')) quick.push(['#/daily', 'clipboard-check', 'مراجعة التقارير اليومية']);
    if (api.can('odometer.review')) quick.push(['#/odometer', 'gauge', 'مراجعة قراءات العداد']);
    if (api.can('employees.onboarding')) quick.push(['#/employees?tab=reg', 'user-round-check', 'طلبات التسجيل']);
    var level1 = h`<section class="dash-level" aria-labelledby="dash-l1"><h2 class="dash-level-t" id="dash-l1">الآن</h2>
      <div class="kpis dash-top">${top}</div>
      ${quick.length ? h`<div class="dash-quick" aria-label="إجراءات سريعة">${quick.map(function (x) { return h`<a class="btn btn-outline" href="${x[0]}">${icon(x[1], 15)} ${x[2]}</a>`; })}</div>` : ''}</section>`;

    /* ---- 2) الاتجاهات والاستثناءات ---- */
    var ex = []; // [tone, icon, text, count, href|drill]
    function x(n, tone, ic, text, target) { if (n) ex.push([tone, ic, text, n, target]); }
    x(a.critical, 'r', 'siren', 'تنبيهات حرجة مفتوحة', '#/alerts?status=open&severity=critical');
    if (drv) x(drv.signal_lost, 'r', 'signal', 'سيارات في العهدة انقطعت إشارتها', { drill: 'signal_lost' });
    if (rep) x(rep.overdue, 'o', 'timer', 'تقارير تأخرت مراجعتها', { drill: 'reports_overdue' });
    if (rep) x(rep.today_missing, 'o', 'clipboard-list', 'بدؤوا يومهم ولم يرسلوا تقريرهم', { drill: 'today_missing' });
    if (cash) x(cash.over_limit, 'o', 'wallet', 'سائقون رصيدهم فوق حد ' + fmt.money(cash.limit), '#/cash');
    if (drv) x(drv.without_vehicle, 'o', 'car', 'سائقون على رأس العمل بلا سيارة', { drill: 'without_vehicle' });
    if (d.documents) x(d.documents.expired, 'r', 'file-warning', 'مستندات انتهت', '#/employees?tab=docs&days=30');
    if (mnt) x(mnt.pending_approval, 'o', 'wrench', 'صيانة بانتظار القرار', '#/maintenance?status=pending');
    if (mnt) x(mnt.ready, 'g', 'wrench', 'سيارات جاهزة للاستلام من المراكز', '#/maintenance?status=ready');
    if (acc) x(acc.no_police_report, 'o', 'shield-alert', 'حوادث بلا محضر شرطة', '#/accidents?chip=police');
    if (acc) x(acc.estimate_pending, 'b', 'shield', 'تقديرات حوادث بانتظار الاعتماد', '#/accidents?chip=estimate');
    if (fin) x(fin.no_driver, 'o', 'receipt', 'مخالفات بلا سائق وقت المخالفة', '#/fines');
    if (d.approvals) x(d.approvals.waiting, 'b', 'list-checks', 'اعتمادات بانتظار قرارك', '#/approvals');
    var exCard = h`<div class="card" data-exceptions><div class="card-h"><div class="card-t">${icon('triangle-alert', 17)} يحتاج تدخلاً</div><span class="card-meta">ما خرج عن المعتاد الآن · اضغط لترى السجلات</span></div>
      ${ex.length ? h`<div class="list">${ex.map(function (e) {
        var inner = h`<span class="li-ic ${e[0]}">${icon(e[1], 16)}</span><div class="li-main"><div class="li-t">${e[2]}</div></div><b class="num dash-ex-n">${fmt.int(e[3])}</b>${icon('chevron-left', 14)}`;
        return e[4].drill ? h`<button type="button" class="li dash-ex" data-action="dash-drill" data-arg="${e[4].drill}">${inner}</button>` : h`<a class="li dash-ex" href="${e[4]}">${inner}</a>`;
      })}</div>` : BT.empty('circle-check', 'لا استثناءات الآن', 'كل ما يُتابَع هنا في حدوده')}</div>`;

    var weekCard = d.week ? h`<div class="card"><div class="card-h"><div><div class="card-t" data-week-title>الطلبات — آخر 7 أيام</div><div class="card-meta">من التقارير اليومية غير المرفوضة، كما تُحسب أرقام اليوم</div></div>
        <div class="flex gap-8 items-center">${BT.tabs('dash-week', [['orders', 'الطلبات'], ['cash', 'الكاش المُبلّغ']], 'orders')}
        <button type="button" class="icon-btn sm sq" data-week-table data-tip="عرض كجدول" aria-label="عرض كجدول">${icon('table-2', 16)}</button></div></div>
      <div data-week-chart></div></div>` : '';

    var alertCard = h`<div class="card" data-dash-alerts><div class="card-h"><div class="card-t">تنبيهات مفتوحة${d.alerts_oldest ? h` <span class="card-meta">أقدمها ${fmt.agoEl(d.alerts_oldest)}</span>` : ''}</div><span class="flex gap-8">${a.critical ? BT.pill(a.critical + ' حرج', 'r') : ''}${a.warning ? BT.pill(a.warning + ' تحذير', 'o') : ''}${a.info ? BT.pill(a.info + ' معلومة', 'b') : ''}</span></div>
      ${alerts.length ? h`<div class="list">${alerts.map(function (al) { return h`<div class="li"><a href="#/alerts" class="dash-alert-link"><span class="li-ic ${{ critical: 'r', warning: 'o', info: 'b' }[al.severity]}">${icon(al.severity === 'critical' ? 'siren' : al.severity === 'warning' ? 'triangle-alert' : 'info', 16)}</span><div class="li-main"><div class="li-t">${al.message}</div><div class="li-d"><span class="num" title="${fmt.dtKw(al.created_at)}">${fmt.dt(al.created_at)}</span> · ${fmt.agoEl(al.created_at)}${al.status === 'new' ? h` · ${BT.pill('جديد', 'b')}` : ''}${A.alertNow && A.alertNow(al, true) ? h` · ${A.alertNow(al, true)}` : ''}</div></div></a>${A.alertButton(al)}</div>`; })}</div><div class="mt-8"><a class="link-row" href="#/alerts">إدارة كل التنبيهات ${icon('arrow-left', 14)}</a></div>` : BT.empty('circle-check', 'لا توجد تنبيهات مفتوحة', '')}</div>`;
    var docCard = docs ? h`<div class="card"><div class="card-h"><div class="card-t">${icon('file-clock', 17)} مستندات تنتهي خلال 30 يوماً</div><span class="card-meta">${d.documents ? fmt.int(d.documents.expiring) + ' قريباً · ' + fmt.int(d.documents.expired) + ' منتهية' : ''}</span></div>
      ${docs.length ? h`<div class="list">${docs.slice(0, 6).map(function (x) { var n = BT.date.daysLeft(x.expiry_date); return h`<a class="li" href="${x.owner_type === 'vehicle' ? '#/vehicles/' + x.owner_id : '#/employees?tab=docs'}"><span class="li-ic ${n < 0 ? 'r' : ''}">${icon(x.owner_type === 'vehicle' ? 'car' : x.owner_type === 'company' ? 'building-2' : 'file-badge', 16)}</span><div class="li-main"><div class="li-t"><bdi>${api.name(x.owner_name) || '—'}</bdi></div><div class="li-d">${A.docTypeName(x.type_code)} · <span class="num">${fmt.date(x.expiry_date)}</span></div></div>${BT.pill(fmt.daysLabel(n), n < 0 ? 'r' : n <= 15 ? 'o' : 'b')}</a>`; })}</div><div class="mt-8"><a class="link-row" href="#/employees?tab=docs&days=30">كل المستندات ${icon('arrow-left', 14)}</a></div>` : BT.empty('circle-check', 'لا شيء ينتهي قريباً', '')}</div>` : '';
    var level2 = h`<section class="dash-level" aria-labelledby="dash-l2"><h2 class="dash-level-t" id="dash-l2">الاتجاهات والاستثناءات</h2>
      <div class="dash-grid dash-grid-ex">${exCard}${weekCard ? h`<div class="dash-wide">${weekCard}</div>` : ''}</div>
      <div class="dash-grid">${alertCard}${docCard}</div></section>`;

    /* ---- 3) التفاصيل حسب المجال ---- */
    var groups = [];
    var fleet = [];
    if (veh) fleet.push(kpi({ label: 'متاحة للتسليم', value: fmt.int(veh.available), sub: 'من ' + fmt.int(total) + ' سيارة', dot: 'g', href: '#/vehicles?status=available' }));
    if (veh) fleet.push(kpi({ label: 'في الصيانة', value: fmt.int(veh.maintenance), sub: fmt.int(veh.accident) + ' في حادث · ' + fmt.int(veh.inactive) + ' متوقفة', dot: 'o', href: '#/vehicles?status=maintenance' }));
    if (drv && drv.signal_lost != null) fleet.push(kpi({ label: 'انقطاع إشارة', value: fmt.int(drv.signal_lost), sub: 'خلال العهدة، الآن', dot: 'r', tone: drv.signal_lost ? 'danger' : null, drill: 'signal_lost' }));
    if (drv && drv.total != null) {
      fleet.push(kpi({ label: 'السائقون', value: h`${fmt.int(drv.working)}<small> / ${fmt.int(drv.total)}</small>`, sub: 'على رأس العمل من غير المنتهية خدمتهم', dot: 'b', href: '#/employees?driver=true' }));
      fleet.push(kpi({ label: 'بلا سيارة', value: fmt.int(drv.without_vehicle), sub: 'على رأس العمل ولا عهدة لهم', dot: 'o', tone: drv.without_vehicle ? 'warning' : null, drill: 'without_vehicle' }));
      fleet.push(kpi({ label: 'بدؤوا يومهم اليوم', value: fmt.int(drv.started_today), sub: 'بقراءة عداد البداية', dot: 'g', drill: 'started_today' }));
    }
    groups.push(group('fleet', 'الأسطول والسائقون', 'car', 'السيارات والعهد والإشارة', fleet.length ? h`<div class="kpis" data-drivers>${fleet}</div>` : ''));

    var ops = [];
    if (rep) {
      ops.push(kpi({ label: 'بانتظار المراجعة', value: fmt.int(rep.waiting_review), sub: rep.overdue ? fmt.int(rep.overdue) + ' تأخرت مراجعتها' : 'لا شيء متأخر', dot: 'p', tone: rep.overdue ? 'warning' : null, href: '#/daily?status=submitted' }));
      ops.push(kpi({ label: 'تأخرت مراجعتها', value: fmt.int(rep.overdue), sub: 'أكثر من المدة المحددة في الإعدادات', dot: 'o', tone: rep.overdue ? 'warning' : null, drill: 'reports_overdue' }));
      ops.push(kpi({ label: 'بدأ يومه بلا تقرير', value: fmt.int(rep.today_missing), sub: 'قرأ عداد البداية اليوم ولم يرسل', dot: 'o', tone: rep.today_missing ? 'warning' : null, drill: 'today_missing' }));
      ops.push(kpi({ label: 'الكاش المُبلّغ اليوم', value: fmt.money(rep.today_cash), sub: cur + ' · من ' + fmt.int(rep.today_sent) + ' سائق', dot: 'g', drill: 'reports_today' }));
    }
    groups.push(group('ops', 'العمليات اليومية', 'clipboard-check', 'التقارير والمراجعة', ops.length ? h`<div class="kpis">${ops}</div>` : ''));

    var money = [];
    if (cash) {
      if (d.driver_cash) money.push(kpi({ label: 'الكاش لدى السائقين (المعتمد وغير المعتمد)', value: fmt.money(cash.held_by_drivers), sub: 'منه غير معتمد ' + fmt.money(cash.unapproved), dot: 'o', href: '#/cash' }));
      money.push(kpi({ label: 'لديهم كاش يسلمونه', value: fmt.int(cash.drivers_holding), sub: fmt.int(cash.over_limit) + ' فوق حد ' + fmt.money(cash.limit), dot: 'o', tone: cash.over_limit ? 'warning' : null, href: '#/cash' }));
      money.push(kpi({ label: 'أُودع بإيصالات اليوم', value: fmt.money(cash.deposited_today), sub: cur, dot: 'g', tone: 'success', drill: 'deposited_today' }));
      if (cash.treasury != null) money.push(kpi({ label: 'رصيد الخزينة', value: fmt.money(cash.treasury), sub: 'في البنك ' + fmt.money(cash.bank) + ' ' + cur, dot: 'b', href: '#/cash?tab=treasury' }));
    }
    groups.push(group('cash', 'الكاش والخزينة', 'wallet', 'الأرصدة والإيداعات', money.length ? h`<div class="kpis">${money}</div>` : ''));

    var repair = [];
    if (mnt) {
      repair.push(kpi({ label: 'صيانة بانتظار القرار', value: fmt.int(mnt.pending_approval), sub: 'طلبات وعروض أسعار فوق الحد', dot: 'o', tone: mnt.pending_approval ? 'warning' : null, href: '#/maintenance?status=pending' }));
      repair.push(kpi({ label: 'تحت الإصلاح', value: fmt.int(mnt.under_repair), sub: fmt.int(mnt.referred) + ' محالة لم تصل المركز بعد', dot: 'p', href: '#/maintenance?status=at_center' }));
      repair.push(kpi({ label: 'جاهزة للاستلام', value: fmt.int(mnt.ready), sub: 'من مراكز الصيانة', dot: 'g', tone: mnt.ready ? 'success' : null, href: '#/maintenance?status=ready' }));
    }
    if (acc) {
      repair.push(kpi({ label: 'حوادث مفتوحة', value: fmt.int(acc.open), sub: fmt.int(acc.this_month) + ' هذا الشهر', dot: 'r', href: '#/accidents' }));
      repair.push(kpi({ label: 'بلا محضر شرطة', value: fmt.int(acc.no_police_report), sub: 'لا تُحدد المسؤولية قبله', dot: 'o', tone: acc.no_police_report ? 'warning' : null, href: '#/accidents?chip=police' }));
      repair.push(kpi({ label: 'تقديرات بانتظار الاعتماد', value: fmt.int(acc.estimate_pending), sub: 'من مراكز الصيانة', dot: 'p', href: '#/accidents?chip=estimate' }));
      repair.push(kpi({ label: 'بانتظار تحديد المسؤولية', value: fmt.int(acc.awaiting_outcome), sub: 'التقدير معتمد', dot: 'b', href: '#/accidents?chip=outcome' }));
    }
    if (fin) {
      repair.push(kpi({ label: 'مخالفات بانتظار القرار', value: fmt.int(fin.open), sub: fin.no_driver ? fmt.int(fin.no_driver) + ' بلا سائق وقت المخالفة' : 'خصم من السائق أو على الشركة', dot: 'o', tone: fin.no_driver ? 'warning' : null, href: '#/fines' }));
      repair.push(kpi({ label: 'غير مدفوعة للمرور', value: fmt.int(fin.unpaid), sub: fmt.money(fin.unpaid_total) + ' ' + cur, dot: 'r', href: '#/fines?chip=unpaid' }));
    }
    groups.push(group('repair', 'الصيانة والحوادث والمخالفات', 'wrench', 'ما ينتظر قراراً أو استلاماً', repair.length ? h`<div class="kpis">${repair}</div>` : ''));

    var hr = d.hr;
    if (hr) groups.push(group('hr', 'الموظفون والرواتب', 'users', 'حسب الحالة الوظيفية', h`<div data-hr>${hr.payroll ? h`<a class="card-meta dash-payroll" href="#/payroll">رواتب ${fmt.month(+hr.payroll.month.slice(0, 4), +hr.payroll.month.slice(5, 7))}: ${fmt.int(hr.payroll.paid)} مدفوعة · ${fmt.int(hr.payroll.approved)} معتمدة · ${fmt.int(hr.payroll.draft)} مسودة · ${fmt.int(hr.payroll.not_started)} لم تبدأ</a>` : ''}
      <div class="flex gap-8" style="flex-wrap:wrap">${hr.statuses.filter(function (s) { return s.count; }).map(function (s) { return h`<a class="chip" href="#/employees?status=${s.code}" data-status="${s.code}">${api.name(s.name)} <span class="n">${fmt.int(s.count)}</span></a>`; })}</div></div>`));
    if (d.by_company) groups.push(group('companies', 'حسب الشركة', 'building-2', 'نفس أرقام اليوم لكل شركة على حدة', h`<div class="table-wrap" data-by-company><table class="t compact"><thead><tr><th>الشركة</th>${'vehicles' in d.by_company[0] ? h`<th class="num">السيارات في العهدة</th>` : ''}${'on_duty' in d.by_company[0] ? h`<th class="num">سائقون في العهدة</th>` : ''}${'reports_today' in d.by_company[0] ? h`<th class="num">تقارير اليوم</th><th class="num">الطلبات</th>` : ''}${'cash_held' in d.by_company[0] ? h`<th class="num">الكاش لدى السائقين</th>` : ''}</tr></thead>
      <tbody>${d.by_company.map(function (c) { return h`<tr data-company="${c.company_id}"><td>${api.name(c.name)}</td>${'vehicles' in c ? h`<td class="num">${fmt.int(c.vehicles_assigned)} / ${fmt.int(c.vehicles)}</td>` : ''}${'on_duty' in c ? h`<td class="num">${fmt.int(c.on_duty)}</td>` : ''}${'reports_today' in c ? h`<td class="num">${fmt.int(c.reports_today)}</td><td class="num">${fmt.int(c.orders_today)}</td>` : ''}${'cash_held' in c ? h`<td class="num">${fmt.money(c.cash_held)}</td>` : ''}</tr>`; })}</tbody></table></div>`));
    var level3 = groups.filter(function (g) { return String(g); });
    level3 = level3.length ? h`<section class="dash-level" aria-labelledby="dash-l3"><h2 class="dash-level-t" id="dash-l3">التفاصيل حسب المجال <span class="card-meta">اضغط على المجال لفتحه</span></h2><div class="dash-groups">${level3}</div></section>` : '';

    return h`${A.head((hour < 12 ? 'صباح الخير' : 'مساء الخير') + '، ' + api.me.full_name.split(' ')[0], h`ملخص اليوم ${fmt.dateLong(today)} · آخر تحديث <span class="num">${fmt.time(d.as_of)}</span> بتوقيت الكويت`, A.btn('تحديث', { icon: 'refresh-cw', cls: 'btn-outline', action: 'reload' }))}
      ${level1}${level2}${level3}`;
  }

  /* السجلات وراء رقم لا تفلتر به صفحة: نفس شروط الرقم على الخادم، ولكل سجل زر يفتحه */
  var DRILL = {
    signal_lost: { title: 'انقطعت إشارتها الآن', icon: 'signal', page: ['#/tracking', 'التتبع الحي'], columns: [
      { key: 'plate', label: 'السيارة', sort: function (r) { return r.vehicle.plate; }, render: function (r) { return BT.plate(r.vehicle.plate); } },
      { key: 'driver', label: 'السائق', sort: function (r) { return api.name(r.driver.name); }, render: function (r) { return api.name(r.driver.name); } },
      { key: 'last_seen', label: 'آخر موقع', sort: function (r) { return r.last_seen; }, render: function (r) { return r.has_point ? h`<span class="num">${fmt.dt(r.last_seen)}</span><span class="sub">${fmt.agoEl(r.last_seen)}</span>` : h`<span class="muted">لا موقع منذ التسليم</span><span class="sub">سُلّمت ${fmt.agoEl(r.started_at)}</span>`; } }
    ], open: function (r) { A.custody(r.custody_id); } },
    without_vehicle: { title: 'على رأس العمل بلا سيارة', icon: 'car', page: ['#/employees?driver=true&vehicle=false', 'قائمة الموظفين'], columns: [
      { key: 'driver', label: 'السائق', sort: function (r) { return api.name(r.driver.name); }, render: function (r) { return BT.person(api.name(r.driver.name), r.employee_number); } },
      { key: 'status', label: 'الحالة', render: function (r) { return api.name(r.status); } },
      { key: 'company', label: 'الشركة', render: function (r) { return api.company(r.company_id); } }
    ], open: function (r) { A.employee(r.driver.id); } },
    started_today: { title: 'بدؤوا يومهم اليوم', icon: 'gauge', columns: [
      { key: 'driver', label: 'السائق', sort: function (r) { return api.name(r.driver.name); }, render: function (r) { return BT.person(api.name(r.driver.name), r.employee_number); } },
      { key: 'plate', label: 'السيارة', render: function (r) { return BT.plate(r.vehicle.plate); } },
      { key: 'at', label: 'قراءة البداية', sort: function (r) { return r.at; }, render: function (r) { return h`<span class="num">${fmt.time(r.at)}</span> · <span class="num">${fmt.km(r.km)}</span> كم`; } }
    ], open: function (r) { A.employee(r.driver.id); } },
    today_missing: { title: 'بدؤوا يومهم ولم يرسلوا تقريرهم', icon: 'clipboard-list', columns: null, open: function (r) { A.employee(r.driver.id); } },
    reports_overdue: { title: 'تقارير تأخرت مراجعتها', icon: 'timer', page: ['#/daily?status=submitted', 'التقارير اليومية'], columns: [
      { key: 'driver', label: 'السائق', sort: function (r) { return api.name(r.driver.name); }, render: function (r) { return api.name(r.driver.name); } },
      { key: 'day', label: 'اليوم', sort: function (r) { return r.business_date; }, render: function (r) { return h`<span class="num">${fmt.date(r.business_date)}</span>`; } },
      { key: 'submitted_at', label: 'أُرسل', sort: function (r) { return r.submitted_at; }, render: function (r) { return h`<span class="num">${fmt.dt(r.submitted_at)}</span><span class="sub">${fmt.agoEl(r.submitted_at)}</span>`; } },
      { key: 'cash', label: 'الكاش', num: true, render: function (r) { return fmt.money(r.cash); } }
    ], open: function (r) { A.go('daily?status=submitted&date=' + r.business_date); } },
    reports_today: { title: 'تقارير اليوم', icon: 'clipboard-check', page: ['#/daily?date=' + BT.config.today, 'التقارير اليومية'], columns: [
      { key: 'driver', label: 'السائق', sort: function (r) { return api.name(r.driver.name); }, render: function (r) { return api.name(r.driver.name); } },
      { key: 'status', label: 'الحالة', render: function (r) { return A.pill('report_status', r.status); } },
      { key: 'orders', label: 'الطلبات', num: true, sort: function (r) { return r.orders || 0; }, render: function (r) { return fmt.int(r.orders); } },
      { key: 'cash', label: 'الكاش', num: true, sort: function (r) { return Number(r.cash || 0); }, render: function (r) { return fmt.money(r.cash); } },
      { key: 'submitted_at', label: 'أُرسل', sort: function (r) { return r.submitted_at; }, render: function (r) { return h`<span class="num">${fmt.time(r.submitted_at)}</span>`; } }
    ], open: function (r) { A.go('daily?date=' + BT.config.today + '&status=' + r.status); },
    foot: function (rows) { return h`<tr><td>الإجمالي (${fmt.int(rows.length)} تقرير)</td><td></td><td class="num">${fmt.int(BT.sum(rows, function (r) { return r.orders || 0; }))}</td><td class="num">${fmt.kwd(BT.sum(rows, function (r) { return Number(r.cash || 0); }))}</td><td></td><td></td></tr>`; } },
    deposited_today: { title: 'أُودع بإيصالات اليوم', icon: 'hand-coins', columns: [
      { key: 'no', label: 'الإيصال', num: true, sort: function (r) { return r.receipt_no; }, render: function (r) { return h`<span class="num">${r.receipt_no}</span>`; } },
      { key: 'driver', label: 'السائق', sort: function (r) { return api.name(r.driver.name); }, render: function (r) { return api.name(r.driver.name); } },
      { key: 'amount', label: 'المبلغ', num: true, sort: function (r) { return Number(r.amount); }, render: function (r) { return fmt.money(r.amount); } },
      { key: 'at', label: 'الوقت', sort: function (r) { return r.at; }, render: function (r) { return h`<span class="num">${fmt.time(r.at)}</span>${r.confirmed ? '' : h` ${BT.pill('لم يؤكده السائق', 'o')}`}`; } }
    ], open: function (r) { A.statement(r.driver); },
    foot: function (rows) { return h`<tr><td>الإجمالي</td><td></td><td class="num">${fmt.kwd(BT.sum(rows, function (r) { return Number(r.amount); }))}</td><td></td><td></td></tr>`; } }
  };
  DRILL.today_missing.columns = DRILL.started_today.columns;
  BT.actions['dash-drill'] = function (metric) {
    var cfg = DRILL[metric];
    if (!cfg) return;
    var dlg = BT.drawer.open({ title: cfg.title, icon: cfg.icon, size: 'lg', body: A.spinner(), buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }] });
    api.get('/dashboard/details/' + metric).then(function (res) {
      dlg.setBody(h`<p class="muted fs-sm mb-12" data-drill="${metric}">${fmt.int(res.count)} سجل، بنفس شروط الرقم على لوحة التحكم، كما في ${fmt.time(res.as_of)} بتوقيت الكويت${res.count > res.rows.length ? ' (يظهر أول ' + fmt.int(res.rows.length) + ')' : ''}.${cfg.page ? h` <a href="${cfg.page[0]}" data-close>فتح ${cfg.page[1]}</a>` : ''}</p><div data-drill-table></div>`);
      BT.table(dlg.body.querySelector('[data-drill-table]'), {
        rows: res.rows, pageSize: 25, columns: cfg.columns, views: false, compact: true, foot: cfg.foot,
        rowClick: function (r) { dlg.close(); cfg.open(r); },
        empty: { icon: 'circle-check', title: 'لا شيء هنا الآن', text: 'تغيّر الرقم منذ فُتحت لوحة التحكم' }
      });
    }, function (err) { dlg.setBody(A.errorBox(err)); });
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
        format: orders ? fmt.int : fmt.money, unitLabel: orders ? 'طلب' : BT.config.currency, height: 210
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
