/* =====================================================================
   app/pages/ops.js — التقارير اليومية، الكاش والخزينة، التقارير
   كل مبلغ من الخادم نص بثلاث خانات عشرية؛ الواجهة لا تحسب أرصدة بنفسها.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;
  var amt = function (s, cls) { return BT.amt(Number(s), cls ? { cls: cls } : null); };

  /* تنزيل ملف بنفس جلسة الواجهة ولغتها */
  A.downloadFile = function (path, query, filename) {
    return fetch(api.url(path, query), { credentials: 'same-origin', headers: { 'Accept-Language': api.lang } }).then(function (res) {
      if (!res.ok) return res.json().then(function (b) { throw new api.ApiError(res.status, b); }, function () { throw new api.ApiError(res.status, {}); });
      return res.blob();
    }).then(function (blob) {
      var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = filename; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
    }).catch(function (err) { BT.toast(api.message(err), { type: 'error', timeout: 6000 }); });
  };

  /* ================= التقارير اليومية ================= */
  BT.pages['daily'] = function (p, q) {
    A.setTitle('التقارير اليومية');
    var v = A.view(), filters = { day: q.date || '' };
    BT.render(v, h`${A.head('تقارير السائقين اليومية', 'عدد الطلبات والكاش المحصّل ولقطة شاشة تطبيق الطلبات. الاعتماد يرحّل الكاش إلى حساب السائق، والتصحيح يحتاج سبباً', '')}<div id="daily-changes"></div><div class="card"><div id="daily-table"></div></div>`);
    var el = document.getElementById('daily-table');
    var review = api.can('daily_reports.review');
    if (review) changeRequests(document.getElementById('daily-changes'), function () { t.refresh(); });
    var t = BT.table(el, {
      fetch: function (s) { return api.get('/daily-reports', { status: s.chip, business_date: filters.day, limit: s.limit, offset: s.offset }); },
      chips: { value: q.status || 'submitted', all: false, options: A.options('report_status', ['submitted', 'returned', 'approved', 'rejected']) },
      tools: h`<input class="input" type="date" data-day value="${filters.day}" aria-label="يوم العمل" title="يوم العمل">`,
      selectable: review,
      id: function (r) { return r.id; },
      bulk: [{ label: 'اعتماد المحدد كما هو', icon: 'check', cls: 'btn-primary', run: function (rows, clear) { bulkApprove(rows.filter(function (r) { return r.status === 'submitted'; }), function () { clear(); t.refresh(); }); } }],
      columns: [
        { key: 'driver', label: 'السائق', render: function (r) { return A.person(r.driver, r.vehicle_plate || ''); } },
        { key: 'business_date', label: 'اليوم', render: function (r) { return h`<span class="num">${fmt.date(r.business_date)}</span>`; } },
        { key: 'orders', label: 'الطلبات', num: true, render: function (r) { return r.orders_count != null ? h`<span class="num">${fmt.int(r.orders_count)}</span>${off(r, 'orders')}` : '—'; } },
        { key: 'valid_day', label: 'حسب المنصة', render: function (r) { return r.valid_day == null ? '—' : r.valid_day ? BT.pill('صالح', 'g') : BT.pill('غير صالح', 'n'); } },
        { key: 'cash', label: 'الكاش', num: true, render: function (r) { return h`${amt(r.cash_amount)}${off(r, 'cash')}${r.approved_cash != null && Number(r.approved_cash) !== Number(r.cash_amount) ? h`<span class="sub">المعتمد ${fmt.money(r.approved_cash)}</span>` : ''}`; } },
        { key: 'shot', label: 'اللقطة', render: function (r) { return r.has_screenshot ? icon('image', 16, 't-success') : raw('<span class="muted">—</span>'); } },
        { key: 'status', label: 'الحالة', render: function (r) { return h`${A.pill('report_status', r.status)}${r.late ? h` ${BT.pill('متأخر', 'o')}` : ''}${r.change_pending ? h` ${BT.pill('طلب تعديل', 'b')}` : ''}`; } },
        { key: 'submitted_at', label: 'أُرسل', render: function (r) { return fmt.dt(r.submitted_at); } }
      ],
      rowClick: function (r) { A.report(r, t.refresh); },
      empty: { icon: 'clipboard-check', title: 'لا توجد تقارير هنا' }
    });
    el.querySelector('[data-day]').addEventListener('change', function (e) { filters.day = e.target.value; t.refresh(); });
  };

  // FR-DWR-06: what a change touched, as the reviewer reads it
  var FIELD_LABEL = { orders_count: 'الطلبات', cash_amount: 'الكاش', valid_day: 'اليوم حسب المنصة', screenshot_sha256: 'لقطة الشاشة', notes: 'الملاحظات' };
  function fieldValue(k, v) {
    if (v == null || v === '') return '—';
    if (k === 'cash_amount') return fmt.money(v);
    if (k === 'valid_day') return v ? 'صالح' : 'غير صالح';
    if (k === 'screenshot_sha256') return 'صورة';
    return String(v);
  }
  function diff(c) {
    var keys = Object.keys(c.after || {});
    if (!keys.length) return '';
    return h`${keys.map(function (k) { return h`<div class="fs-sm">${FIELD_LABEL[k] || k}: <span class="num">${fieldValue(k, (c.before || {})[k])}</span> ← <b class="num">${fieldValue(k, c.after[k])}</b></div>`; })}`;
  }
  var CHANGE_KIND = { edit: 'عدّله السائق', returned: 'أُعيد للسائق', request: 'طلب تعديل بعد الاعتماد' };
  var CHANGE_STATUS = { pending: ['بانتظار القرار', 'o'], approved: ['وافق', 'g'], rejected: ['رُفض', 'r'] };
  function changeLog(list) {
    if (!list.length) return '';
    return h`<div class="section-t mt-16">سجل التعديلات</div><div class="timeline">${list.map(function (c) {
      var st = CHANGE_STATUS[c.status];
      var tone = c.kind === 'returned' ? 'o' : st ? st[1] : 'b';
      return h`<div class="tl-item" data-change="${c.kind}"><span class="tl-ic ${tone}">${icon(c.kind === 'returned' ? 'undo-2' : 'pencil', 13)}</span><div class="flex-1"><div class="tl-t">${CHANGE_KIND[c.kind] || c.kind}${st ? h` ${BT.pill(st[0], st[1])}` : ''}</div><div class="tl-d">${fmt.dt(c.created_at)}</div>${diff(c)}${c.reason ? h`<div class="tl-d">السبب: ${c.reason}</div>` : ''}${c.decision_note ? h`<div class="tl-d">القرار: ${c.decision_note}</div>` : ''}</div></div>`;
    })}</div>`;
  }
  function changeRequests(box, after) {
    api.get('/daily-reports/change-requests').then(function (list) {
      if (!document.contains(box)) return;
      if (!list.length) { BT.render(box, ''); return; }
      BT.render(box, h`<div class="card mb-16" data-change-requests><div class="card-h"><b>طلبات تعديل تقارير معتمدة</b> <span class="muted fs-sm">يطلبها السائق بعد الاعتماد؛ الموافقة ترحّل فرق الكاش بقيد تسوية بسببه</span></div><div class="card-b">${list.map(function (c) {
        return h`<div class="between mb-12" data-change-id="${c.id}"><div>${A.person(c.driver)} <span class="num muted">${fmt.date(c.business_date)}</span>${diff(c)}<div class="fs-sm muted">السبب: ${c.reason || '—'}</div></div><div class="nowrap"><button type="button" class="btn btn-sm btn-primary" data-change-ok="${c.id}">موافقة</button> <button type="button" class="btn btn-sm btn-outline" data-change-no="${c.id}">رفض</button></div></div>`;
      })}</div></div>`);
      var reload = function () { changeRequests(box, after); if (after) after(); A.refreshCounts(); };
      box.querySelectorAll('[data-change-ok]').forEach(function (b) {
        b.addEventListener('click', function () {
          A.confirmRun({ title: 'الموافقة على التعديل', message: 'يأخذ التقرير الأرقام الجديدة، ويُرحّل فرق الكاش لحساب السائق بسببه.', confirmText: 'موافقة', tone: 'success',
            run: function () { return api.post('/daily-reports/change-requests/' + b.getAttribute('data-change-ok') + '/approve', {}); }, done: 'تمت الموافقة على التعديل', after: reload });
        });
      });
      box.querySelectorAll('[data-change-no]').forEach(function (b) {
        b.addEventListener('click', function () {
          A.confirmRun({ title: 'رفض التعديل', message: 'يصل السبب للسائق في التطبيق.', confirmText: 'رفض', tone: 'danger', reason: { label: 'سبب الرفض' },
            run: function (reason) { return api.post('/daily-reports/change-requests/' + b.getAttribute('data-change-no') + '/reject', { note: reason }); }, done: 'تم رفض التعديل', after: reload });
        });
      });
    }, function () { BT.render(box, ''); });
  }

  // FR-DWR-08: far from the driver's own 30-day average, by the percent set in the settings
  function off(r, field) { return (r.deviations || []).indexOf(field) >= 0 ? h` ${BT.pill('بعيد عن متوسطه', 'o')}` : ''; }

  function evidence(r, ev) {
    var a = ev.average, km = function (n) { return n == null ? '—' : h`<span class="num">${fmt.int(n)}</span> كم`; };
    var photos = [];
    if (ev.start) photos.push({ src: api.url('/daily-reports/' + r.id + '/odometer/start'), caption: 'عداد بداية اليوم ' + fmt.int(ev.start.km) + ' كم' });
    if (ev.end) photos.push({ src: api.url('/daily-reports/' + r.id + '/odometer/end'), caption: (ev.end.kind === 'return' ? 'عداد استلام السيارة ' : 'عداد نهاية اليوم ') + fmt.int(ev.end.km) + ' كم' });
    var avg = a.days ? h`<span class="num">${fmt.int(a.days)}</span> يوم معتمد: الطلبات <span class="num">${a.orders == null ? '—' : a.orders}</span> · الكاش ${a.cash == null ? '—' : amt(a.cash)}${a.km != null ? h` · <span class="num">${fmt.int(a.km)}</span> كم` : ''}` : h`<span class="muted">لا توجد تقارير معتمدة في آخر 30 يوماً</span>`;
    return h`<div class="section-t mt-16">العداد والمتوسط</div>
      <div class="grid" style="grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px">
        <div>${photos.length ? A.thumbs(photos) : BT.empty('gauge', 'لا قراءة عداد لهذا اليوم', 'لم يبدأ السائق يومه بقراءة')}</div>
        <div>${BT.kv([['مسافة اليوم', ev.km != null ? km(ev.km) : (ev.start ? h`<span class="muted">لم يُغلق اليوم بقراءة</span>` : '—')], ['متوسط آخر 30 يوماً', avg], ev.deviations.length ? ['انحراف', h`${ev.deviations.map(function (f) { return BT.pill(f === 'orders' ? 'الطلبات بعيدة عن متوسطه' : 'الكاش بعيد عن متوسطه', 'o'); })}`] : null].filter(Boolean))}</div>
      </div>`;
  }

  function bulkApprove(rows, done) {
    if (!rows.length) { BT.toast('لا يوجد تقارير بانتظار المراجعة في التحديد', { type: 'info' }); return; }
    A.confirmRun({ title: 'اعتماد ' + rows.length + ' تقرير', message: 'تُعتمد بالمبالغ التي أرسلها السائقون دون تعديل. التقرير الذي يحتاج تصحيحاً افتحه واعتمده منفرداً مع السبب.', confirmText: 'اعتماد', tone: 'success',
      run: function () {
        var ok = 0, failed = [];
        return rows.reduce(function (pr, r) {
          return pr.then(function () { return api.post('/daily-reports/' + r.id + '/approve', {}).then(function () { ok++; }, function (err) { failed.push(api.name(r.driver && r.driver.name) + ': ' + api.message(err)); }); });
        }, Promise.resolve()).then(function () {
          BT.toast('اعتُمد ' + ok + ' تقرير', { type: failed.length ? 'warning' : 'success', sub: failed.length ? 'تعذر ' + failed.length + ': ' + failed.slice(0, 2).join(' · ') : '', timeout: failed.length ? 8000 : 3800 });
          A.refreshCounts(); done();
        });
      } });
  }

  A.report = function (r, after) {
    var canReview = r.status === 'submitted' && api.can('daily_reports.review');
    var body = h`<div class="grid" style="grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px">
      <div>${r.has_screenshot ? A.thumbs([{ src: api.url('/daily-reports/' + r.id + '/screenshot'), caption: 'لقطة تطبيق الطلبات' }]) : BT.empty('image', 'بدون لقطة شاشة', '')}</div>
      <div>${BT.kv([['السائق', A.person(r.driver)], ['السيارة', r.vehicle_plate ? BT.plate(r.vehicle_plate) : '—'], ['يوم العمل', h`<span class="num">${fmt.date(r.business_date)}</span>`], ['الطلبات', r.orders_count != null ? h`<span class="num">${fmt.int(r.orders_count)}</span>` : '—'], r.valid_day != null ? ['اليوم حسب تطبيق المنصة', r.valid_day ? BT.pill('صالح', 'g') : BT.pill('غير صالح', 'n')] : null, ['الكاش المُبلّغ', amt(r.cash_amount)], r.approved_cash != null ? ['الكاش المعتمد', amt(r.approved_cash)] : null, ['الحالة', A.pill('report_status', r.status)], ['أُرسل', h`${fmt.dt(r.submitted_at)}${r.late ? h` ${BT.pill('متأخر — بعد يومه', 'o')}` : ''}`], r.notes ? ['ملاحظات السائق', r.notes] : null, r.review_note ? ['ملاحظة المراجعة', r.review_note] : null].filter(Boolean))}</div></div>
      <div data-evidence></div><div data-changes></div>
      ${canReview ? h`<div class="form mt-16">${BT.f.money({ name: 'cash_amount', label: 'الكاش الصحيح (اختياري)', hint: 'اتركه فارغاً لاعتماد المبلغ كما أرسله السائق' })}${BT.f.textarea({ name: 'reason', label: 'السبب (إلزامي عند التصحيح أو الرفض أو الإعادة للسائق)', rows: 2 })}</div>` : ''}`;
    var showEvidence = function (d) {
      var el = d.panel.querySelector('[data-evidence]'), log = d.panel.querySelector('[data-changes]');
      if (el) A.load(el, api.get('/daily-reports/' + r.id + '/evidence'), function (ev) { return evidence(r, ev); }).catch(function () {});
      if (log) api.get('/daily-reports/' + r.id + '/changes').then(function (list) { if (document.contains(log)) BT.render(log, changeLog(list)); }, function () {});
      return d;
    };
    if (!canReview) return showEvidence(BT.drawer.open({ title: 'تقرير يومي', icon: 'clipboard-list', size: 'lg', body: body, buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }] }));
    var dlg = BT.drawer.open({
      title: 'مراجعة تقرير يومي', icon: 'clipboard-check', size: 'lg', form: true, body: body,
      buttons: [{ label: 'إعادة للسائق', cls: 'btn-ghost', icon: 'undo-2', close: false, onClick: function () { decide('send-back'); return false; } }, { label: 'رفض', cls: 'btn-outline', icon: 'x', close: false, onClick: function () { decide('reject'); return false; } }, { label: 'اعتماد', cls: 'btn-primary', icon: 'check', submit: true }],
      onSubmit: function () { decide('approve'); return false; }
    });
    showEvidence(dlg);
    function decide(kind) {
      var v = BT.form.values(dlg.form), reason = (v.reason || '').trim();
      if (kind === 'reject' && !reason) { BT.toast('اكتب سبب الرفض', { type: 'error' }); return; }
      if (kind === 'send-back' && !reason) { BT.toast('اكتب ما يصححه السائق في خانة السبب', { type: 'error' }); return; }
      if (kind === 'approve' && v.cash_amount !== '' && !reason) { BT.toast('التصحيح يحتاج سبباً', { type: 'error' }); return; }
      var call = kind === 'approve' ? api.post('/daily-reports/' + r.id + '/approve', { cash_amount: v.cash_amount === '' ? null : String(v.cash_amount), reason: reason || null }) : api.post('/daily-reports/' + r.id + '/' + kind, { reason: reason });
      var btn = { 'send-back': 0, reject: 1, approve: 2 }[kind];
      dlg.busy(btn, true);
      call.then(function (res) {
        // with a workflow, an approval may only record this step: the report stays waiting for the next
        BT.toast(kind === 'reject' ? 'تم رفض التقرير' : kind === 'send-back' ? 'أُعيد التقرير للسائق للتصحيح' : res && res.status === 'approved' ? 'تم اعتماد التقرير' : 'سُجلت موافقتك؛ ينتظر الخطوة التالية');
        dlg.close(); A.refreshCounts(); if (after) after();
      }, function (err) { dlg.busy(btn, false); BT.toast(api.message(err), { type: 'error', timeout: 6000 }); });
    }
    return dlg;
  };

  /* ================= الكاش والخزينة ================= */
  BT.pages['cash'] = function (p, q) {
    A.setTitle('الكاش والخزينة');
    var v = A.view(), tab = q.tab === 'treasury' ? 'treasury' : 'balances';
    var tabs = [];
    if (api.can('cash.view')) tabs.push(['balances', 'أرصدة السائقين']);
    if (api.can('treasury.view')) tabs.push(['treasury', 'الخزينة والبنك']);
    if (!tabs.some(function (t) { return t[0] === tab; })) tab = tabs[0][0];
    BT.render(v, h`${A.head('دفتر الكاش', 'كل حركة قيد مزدوج لا يُحذف: التصحيح بقيد تسوية أو عكس مع السبب. رصيد السائق = ما في ذمته للشركة', api.can('cash.collect') ? A.btn('استلام كاش بإيصال', { icon: 'hand-coins', cls: 'btn-primary', action: 'cash-receipt' }) : '')}
      ${tabs.length > 1 ? BT.tabs('cash', tabs, tab, 'tabs-line') : ''}
      <div data-panel="balances" data-group="cash" class="${tab === 'balances' ? 'active' : ''}"><div id="bal-panel"></div></div>
      <div data-panel="treasury" data-group="cash" class="${tab === 'treasury' ? 'active' : ''}"><div id="tre-panel"></div></div>`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      if (t === 'balances') balancesPanel(document.getElementById('bal-panel'));
      if (t === 'treasury') treasuryPanel(document.getElementById('tre-panel'));
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); });
    show(tab);
    if (q.tab === 'receipts' && api.can('cash.collect')) A.receipt(null);
  };
  BT.actions['cash-receipt'] = function () { A.receipt(null); };

  function balancesPanel(el) {
    A.load(el, Promise.all([api.get('/cash/balances'), api.get('/cash/receipts/unconfirmed')]), function (r) {
      var rows = r[0], late = r[1];
      var sum = function (k) { return rows.reduce(function (s, r) { return s + Number(r[k]); }, 0); };
      var over = rows.filter(function (r) { return r.over_limit; }).length;
      setTimeout(function () {
        var tbl = el.querySelector('[data-bal]');
        if (!tbl) return;
        BT.table(tbl, {
          rows: rows, pageSize: 25,
          search: { placeholder: 'اسم السائق…', text: function (r) { return api.name(r.driver.name); } },
          chips: { key: 'over_limit', options: [{ v: 'true', t: 'فوق الحد' }], match: function (r, c) { return String(r.over_limit) === c; } },
          sort: { key: 'total', dir: 'desc' },
          columns: [
            { key: 'driver', label: 'السائق', sort: function (r) { return api.name(r.driver.name); }, render: function (r) { return A.person(r.driver, api.company(r.company_id)); } },
            { key: 'posted', label: 'معتمد', num: true, sort: function (r) { return Number(r.posted); }, render: function (r) { return amt(r.posted); } },
            { key: 'pending', label: 'غير معتمد', num: true, sort: function (r) { return Number(r.pending); }, render: function (r) { return Number(r.pending) ? amt(r.pending) : raw('<span class="muted">—</span>'); } },
            { key: 'total', label: 'الإجمالي', num: true, sort: function (r) { return Number(r.total); }, render: function (r) { return h`<b>${amt(r.total)}</b>${r.over_limit ? h` ${BT.pill('فوق الحد', 'o')}` : ''}`; } }
          ],
          rowClick: function (r) { A.statement(r.driver); },
          rowMenu: function (r) {
            var m = [{ label: 'كشف الحساب', icon: 'receipt-text', onClick: function () { A.statement(r.driver); } }];
            if (api.can('cash.collect')) m.push({ label: 'استلام كاش بإيصال', icon: 'hand-coins', onClick: function () { A.receipt(r.driver); } });
            if (api.can('cash.adjust')) m.push({ label: 'تسوية يدوية', icon: 'scale', onClick: function () { A.adjust(r.driver); } });
            if (api.can('cash.writeoff')) m.push({ label: 'تسوية نهاية الخدمة', icon: 'user-round-check', onClick: function () { A.settle(r.driver, r); } });
            return m;
          },
          foot: function (list) { return h`<tr><td>الإجمالي (${fmt.int(list.length)})</td><td class="num">${fmt.kwd(list.reduce(function (s, r) { return s + Number(r.posted); }, 0))}</td><td class="num">${fmt.kwd(list.reduce(function (s, r) { return s + Number(r.pending); }, 0))}</td><td class="num"><b>${fmt.kwd(list.reduce(function (s, r) { return s + Number(r.total); }, 0))}</b></td><td></td></tr>`; },
          empty: { icon: 'wallet', title: 'لا توجد أرصدة', text: 'تظهر هنا أرصدة السائقين بعد أول تقرير معتمد أو رصيد افتتاحي' }
        });
      });
      // receipts the drivers have not confirmed a day after they were given (FR-CSH-05): ask them before it is forgotten
      var lateCard = late.length ? h`<div class="card mb-16" data-unconfirmed><div class="card-h"><div class="card-t">${icon('receipt', 16)} إيصالات لم يؤكدها السائق بعد 24 ساعة ${BT.pill(fmt.int(late.length), 'o')}</div><span class="card-meta">اسأل السائق: هل استلم الكاش منه من أعطاه الإيصال؟</span></div>
        <div class="table-wrap"><table class="t compact"><thead><tr><th>السائق</th><th class="num">رقم الإيصال</th><th class="num">المبلغ</th><th class="num">أُعطي في</th></tr></thead>
        <tbody>${late.map(function (x) { return h`<tr data-receipt="${x.id}"><td>${api.name(x.driver.name)}</td><td class="num">${x.receipt_no}</td><td class="num">${fmt.money(x.amount)}</td><td class="num">${fmt.dt(x.created_at)}</td></tr>`; })}</tbody></table></div></div>` : '';
      return h`${lateCard}<div class="kpis">${BT.kpi({ label: 'لدى السائقين (الإجمالي)', value: fmt.kwd(sum('total')), sub: BT.config.currency, dot: 'o' })}${BT.kpi({ label: 'منه معتمد', value: fmt.kwd(sum('posted')), dot: 'g' })}${BT.kpi({ label: 'منه غير معتمد', value: fmt.kwd(sum('pending')), sub: 'تقارير بانتظار المراجعة', dot: 'b' })}${BT.kpi({ label: 'فوق حد التنبيه', value: fmt.int(over), sub: 'تنبيه فقط، لا يوقف السائق', dot: 'r', tone: over ? 'danger' : null })}</div>
        <div class="card">${api.can('cash.view') && api.can('reports.export') ? h`<div class="card-h"><span></span><button type="button" class="btn btn-sm btn-outline ms-auto" data-csv>${icon('download', 14)} تصدير CSV</button></div>` : ''}<div data-bal></div></div>`;
    }).then(function () {
      var c = el.querySelector('[data-csv]');
      if (c) c.onclick = function () { A.downloadFile('/reports/cash-balances', { format: 'csv' }, 'cash-balances.csv'); };
    }).catch(function () {});
  }

  A.statement = function (driver) {
    var dlg = BT.drawer.open({ title: 'كشف حساب: ' + api.name(driver.name), icon: 'receipt-text', size: 'lg', body: A.spinner(), buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }] });
    api.get('/cash/drivers/' + driver.id + '/statement').then(function (s) {
      dlg.setBody(h`<div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">${BT.kpi({ label: 'معتمد', value: fmt.money(s.posted), dot: 'g' })}${BT.kpi({ label: 'غير معتمد', value: fmt.money(s.pending), dot: 'b' })}${BT.kpi({ label: 'الإجمالي', value: fmt.money(s.total), dot: 'o' })}</div>
        ${s.lines.length ? h`<div class="table-wrap"><table class="t compact"><thead><tr><th>الحركة</th><th class="num">اليوم</th><th class="num">المبلغ</th><th class="num">الحالة</th><th></th></tr></thead><tbody>${s.lines.map(function (l) {
          var canRev = l.status === 'posted' && api.can('cash.reverse') && l.kind !== 'reversal';
          return h`<tr><td>${api.t('journal_kind', l.kind)}${l.reason ? h`<span class="sub">${l.reason}</span>` : ''}</td><td class="num">${fmt.date(l.business_date)}</td><td class="num"><span class="${Number(l.amount) > 0 ? '' : 't-success'}">${fmt.signed(Number(l.amount))}</span></td><td class="num">${A.pill('journal_status', l.status)}</td><td class="num">${canRev ? h`<button type="button" class="btn btn-sm btn-ghost" data-rev="${l.journal_id}">${icon('rotate-ccw', 13)} عكس</button>` : ''}</td></tr>`;
        })}</tbody></table></div>` : BT.empty('receipt-text', 'لا توجد حركات', '')}
        <div class="hint mt-8">موجب = يزيد ما في ذمة السائق (تحصيل)، سالب = ينقصه (إيداع أو تسوية).</div>`);
      BT.on(dlg.body, 'click', '[data-rev]', function (e, b) {
        A.confirmRun({ title: 'عكس الحركة', message: 'يُسجَّل قيد معاكس بنفس المبلغ ويبقى الأصل ظاهراً في السجل. يُعكس القيد مرة واحدة فقط.', confirmText: 'عكس', tone: 'danger', icon: 'rotate-ccw', reason: { label: 'السبب', required: true },
          run: function (reason) { return api.post('/cash/journals/' + b.getAttribute('data-rev') + '/reverse', { reason: reason }); }, done: 'تم عكس الحركة', after: function () { dlg.close(); A.statement(driver); refreshCash(); } });
      });
    }, function (err) { dlg.setBody(A.errorBox(err)); });
  };
  function refreshCash() { if (A.router.current === 'cash') A.router.refresh(); }

  function driverPicker(driver) {
    if (driver) return h`<div class="field"><label>السائق</label><div class="input" style="display:flex;align-items:center">${api.name(driver.name)}</div><input type="hidden" name="driver_id" value="${driver.id}"></div>`;
    return null;
  }
  function withDrivers(driver, build) {
    if (driver) { build(driverPicker(driver), function (v) { return v.driver_id; }); return; }
    A.all('/employees', { is_driver: true }).then(function (rows) {
      build(A.picker({ name: 'drv', label: 'السائق', required: true, items: rows.map(function (e) { return { id: e.id, label: api.name(e.name) + ' — ' + e.employee_number }; }) }), function (v) { return A.picked('drv', v.drv); });
    }, api.fail).catch(function () {});
  }

  /* إيصال استلام كاش: رقم متسلسل، والسائق يؤكده من التطبيق */
  A.receipt = function (driver) {
    withDrivers(driver, function (field, idOf) {
      A.formModal({
        title: 'استلام كاش بإيصال', icon: 'hand-coins', size: 'sm', submitText: 'استلام وطباعة الإيصال', done: false,
        body: h`<div class="form">${field}${BT.f.money({ name: 'amount', label: 'المبلغ المستلم', required: true, min: 0.001 })}<div class="hint">يُرحّل فوراً: ينقص رصيد السائق ويزيد خزينة فرعه، ويصل الإيصال لتطبيق السائق ليؤكده.</div></div>`,
        submit: function (v) {
          var did = idOf(v);
          return api.post('/cash/receipts', { driver_id: did, amount: String(v.amount) }).then(function (rc) {
            BT.toast('إيصال رقم ' + rc.receipt_no, { sub: fmt.money(rc.amount) + ' ' + BT.config.currency });
            printReceipt(rc, driver ? api.name(driver.name) : v.drv);
            refreshCash();
          });
        }
      });
    });
  };
  function printReceipt(rc, name) {
    BT.print(h`<div style="font-family:inherit;padding:24px;max-width:420px" dir="rtl"><h2 style="margin:0">${A.brand || ''}</h2><div>إيصال استلام نقدية رقم <b class="num">${rc.receipt_no}</b></div><hr>
      ${BT.kv([['استلمنا من', name], ['المبلغ', h`<b class="num">${fmt.money(rc.amount)}</b> ${BT.config.currency}`], ['الفرع', api.branch(rc.branch_id)], ['التاريخ', fmt.dt(rc.created_at)], ['المستلم', api.me.full_name]])}
      <div style="margin-top:40px;display:flex;justify-content:space-between"><span>توقيع المستلم ____________</span><span>توقيع السائق ____________</span></div></div>`);
  }

  A.adjust = function (driver) {
    A.formModal({
      title: 'تسوية يدوية', subtitle: api.name(driver.name), icon: 'scale', size: 'sm',
      done: function (j) { return j && j.status === 'pending' ? 'أُرسلت التسوية للاعتماد: تظهر غير معتمدة حتى تُعتمد' : 'تم تسجيل التسوية'; },
      body: h`<div class="form">${BT.f.radios({ name: 'dir', label: 'الاتجاه', required: true, value: 'plus', options: [{ v: 'plus', t: 'يزيد ما عليه', d: 'مبلغ لم يُسجَّل' }, { v: 'minus', t: 'ينقص ما عليه', d: 'مبلغ سُجّل بالخطأ' }] })}${BT.f.money({ name: 'amount', label: 'المبلغ', required: true, min: 0.001 })}${BT.f.textarea({ name: 'reason', label: 'السبب', required: true, rows: 2 })}</div>`,
      submit: function (v) { var a = Number(v.amount).toFixed(3); return api.post('/cash/adjustments', { driver_id: driver.id, amount: v.dir === 'minus' ? '-' + a : a, reason: v.reason }); },
      after: refreshCash
    });
  };

  A.settle = function (driver, bal) {
    var owed = Number(bal.posted);
    A.formModal({
      title: 'تسوية نهاية الخدمة', subtitle: api.name(driver.name), icon: 'user-round-check', done: 'تمت التسوية وأُقفل الحساب',
      body: h`<div class="form">${BT.kv([['الرصيد المعتمد', amt(bal.posted)], ['غير معتمد', amt(bal.pending)]])}
        ${Number(bal.pending) ? h`<div class="banner warn fs-sm">${icon('triangle-alert', 15)}<div>توجد حركات غير معتمدة: اعتمد تقاريره أو ارفضها أولاً.</div></div>` : ''}
        ${owed > 0 ? h`<p class="fs-sm">قسّم المبلغ الذي عليه بين الخصم من الراتب والإعدام، بحيث يصبح الرصيد صفراً.</p>${BT.f.money({ name: 'payroll_amount', label: 'يُخصم من مستحقاته', value: owed.toFixed(3) })}${BT.f.money({ name: 'writeoff_amount', label: 'يُعدم (يحتاج سبباً)', value: '0.000' })}` : h`<p class="fs-sm">${owed < 0 ? 'للسائق مبلغ على الشركة يُصرف من خزينة فرعه.' : 'الرصيد صفر: تُقفل الحساب فقط.'}</p>`}
        ${BT.f.textarea({ name: 'reason', label: 'السبب / ملاحظة', rows: 2, optional: true })}<div class="hint">متاحة فقط لمن انتهت خدمته.</div></div>`,
      submit: function (v) { return api.post('/cash/settlements', { driver_id: driver.id, payroll_amount: String(v.payroll_amount || 0), writeoff_amount: String(v.writeoff_amount || 0), reason: v.reason || null }); },
      after: refreshCash
    });
  };

  function treasuryPanel(el) {
    A.load(el, api.get('/cash/treasury'), function (rows) {
      var manage = api.can('treasury.manage') && api.me.all_companies;
      return h`<div class="card"><div class="card-h"><div class="card-t">${icon('landmark', 16)} الخزينة حسب الفرع</div>${manage ? h`<button type="button" class="btn btn-sm btn-primary ms-auto" data-dep>${icon('landmark', 14)} إيداع في البنك</button>` : ''}</div>
        ${BT.chart.table(['الفرع', 'الخزينة', 'البنك', 'مقاصة الدفع عند الاستلام'], rows.map(function (r) { return [api.name(r.branch.name), fmt.money(r.treasury), fmt.money(r.bank), fmt.money(r.cod_clearing)]; }))}
        ${api.can('treasury.manage') && !api.me.all_companies ? h`<div class="hint mt-8">الإيداع البنكي يحتاج صلاحية على كل الشركات لأن الخزينة مشتركة بين شركات الفرع.</div>` : ''}</div>`;
    }).then(function (rows) {
      var b = el.querySelector('[data-dep]');
      if (b) b.onclick = function () {
        A.formModal({
          title: 'إيداع في البنك', icon: 'landmark', size: 'sm', done: 'تم تسجيل الإيداع',
          body: h`<div class="form">${BT.f.select({ name: 'branch_id', label: 'الفرع', required: true, options: rows.map(function (r) { return { v: r.branch.id, t: api.name(r.branch.name) + ' — ' + fmt.money(r.treasury) }; }), placeholder: false })}${BT.f.money({ name: 'amount', label: 'المبلغ', required: true, min: 0.001 })}${BT.f.input({ name: 'reference', label: 'رقم إيصال البنك', required: true })}${BT.f.upload({ name: 'photo', label: 'صورة إيصال البنك', required: true, accept: 'image/*,application/pdf' })}</div>`,
          // the bank's receipt is kept with the deposit (FR-CSH-07): uploaded first, then the deposit names it
          submit: function (v) {
            return api.upload(v.photo[0]).then(function (f) { return api.post('/cash/bank-deposits', { branch_id: +v.branch_id, amount: String(v.amount), reference: v.reference, receipt_sha256: f.sha256 }); });
          },
          after: function () { treasuryPanel(el); }
        });
      };
    }).catch(function () {});
  }

})();
