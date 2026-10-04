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
    BT.render(v, h`${A.head('تقارير السائقين اليومية', 'عدد الطلبات والكاش المحصّل ولقطة شاشة تطبيق الطلبات. الاعتماد يرحّل الكاش إلى حساب السائق، والتصحيح يحتاج سبباً', '')}<div class="card"><div id="daily-table"></div></div>`);
    var el = document.getElementById('daily-table');
    var review = api.can('daily_reports.review');
    var t = BT.table(el, {
      fetch: function (s) { return api.get('/daily-reports', { status: s.chip, business_date: filters.day, limit: s.limit, offset: s.offset }); },
      chips: { value: q.status || 'submitted', all: false, options: A.options('report_status', ['submitted', 'approved', 'rejected']) },
      tools: h`<input class="input" type="date" data-day value="${filters.day}" aria-label="يوم العمل" title="يوم العمل">`,
      selectable: review,
      id: function (r) { return r.id; },
      bulk: [{ label: 'اعتماد المحدد كما هو', icon: 'check', cls: 'btn-primary', run: function (rows, clear) { bulkApprove(rows.filter(function (r) { return r.status === 'submitted'; }), function () { clear(); t.refresh(); }); } }],
      columns: [
        { key: 'driver', label: 'السائق', render: function (r) { return A.person(r.driver, r.vehicle_plate || ''); } },
        { key: 'business_date', label: 'اليوم', render: function (r) { return h`<span class="num">${fmt.date(r.business_date)}</span>`; } },
        { key: 'orders', label: 'الطلبات', num: true, render: function (r) { return r.orders_count != null ? h`<span class="num">${fmt.int(r.orders_count)}</span>` : '—'; } },
        { key: 'cash', label: 'الكاش', num: true, render: function (r) { return h`${amt(r.cash_amount)}${r.approved_cash != null && Number(r.approved_cash) !== Number(r.cash_amount) ? h`<span class="sub">المعتمد ${fmt.money(r.approved_cash)}</span>` : ''}`; } },
        { key: 'shot', label: 'اللقطة', render: function (r) { return r.has_screenshot ? icon('image', 16, 't-success') : raw('<span class="muted">—</span>'); } },
        { key: 'status', label: 'الحالة', render: function (r) { return A.pill('report_status', r.status); } },
        { key: 'submitted_at', label: 'أُرسل', render: function (r) { return fmt.dt(r.submitted_at); } }
      ],
      rowClick: function (r) { A.report(r, t.refresh); },
      empty: { icon: 'clipboard-check', title: 'لا توجد تقارير هنا' }
    });
    el.querySelector('[data-day]').addEventListener('change', function (e) { filters.day = e.target.value; t.refresh(); });
  };

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
      <div>${BT.kv([['السائق', A.person(r.driver)], ['السيارة', r.vehicle_plate ? BT.plate(r.vehicle_plate) : '—'], ['يوم العمل', h`<span class="num">${fmt.date(r.business_date)}</span>`], ['الطلبات', r.orders_count != null ? h`<span class="num">${fmt.int(r.orders_count)}</span>` : '—'], ['الكاش المُبلّغ', amt(r.cash_amount)], r.approved_cash != null ? ['الكاش المعتمد', amt(r.approved_cash)] : null, ['الحالة', A.pill('report_status', r.status)], ['أُرسل', fmt.dt(r.submitted_at)], r.notes ? ['ملاحظات السائق', r.notes] : null, r.review_note ? ['ملاحظة المراجعة', r.review_note] : null].filter(Boolean))}</div></div>
      ${canReview ? h`<div class="form mt-16">${BT.f.money({ name: 'cash_amount', label: 'الكاش الصحيح (اختياري)', hint: 'اتركه فارغاً لاعتماد المبلغ كما أرسله السائق' })}${BT.f.textarea({ name: 'reason', label: 'السبب (إلزامي عند التصحيح أو الرفض)', rows: 2 })}</div>` : ''}`;
    if (!canReview) return BT.drawer.open({ title: 'تقرير يومي', icon: 'clipboard-list', size: 'lg', body: body, buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }] });
    var dlg = BT.drawer.open({
      title: 'مراجعة تقرير يومي', icon: 'clipboard-check', size: 'lg', form: true, body: body,
      buttons: [{ label: 'رفض', cls: 'btn-outline', icon: 'x', close: false, onClick: function () { decide('reject'); return false; } }, { label: 'اعتماد', cls: 'btn-primary', icon: 'check', submit: true }],
      onSubmit: function () { decide('approve'); return false; }
    });
    function decide(kind) {
      var v = BT.form.values(dlg.form), reason = (v.reason || '').trim();
      if (kind === 'reject' && !reason) { BT.toast('اكتب سبب الرفض', { type: 'error' }); return; }
      if (kind === 'approve' && v.cash_amount !== '' && !reason) { BT.toast('التصحيح يحتاج سبباً', { type: 'error' }); return; }
      var call = kind === 'reject' ? api.post('/daily-reports/' + r.id + '/reject', { reason: reason }) : api.post('/daily-reports/' + r.id + '/approve', { cash_amount: v.cash_amount === '' ? null : String(v.cash_amount), reason: reason || null });
      dlg.busy(kind === 'reject' ? 0 : 1, true);
      call.then(function () { BT.toast(kind === 'reject' ? 'تم رفض التقرير' : 'تم اعتماد التقرير'); dlg.close(); A.refreshCounts(); if (after) after(); }, function (err) { dlg.busy(kind === 'reject' ? 0 : 1, false); BT.toast(api.message(err), { type: 'error', timeout: 6000 }); });
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
    A.load(el, api.get('/cash/balances'), function (rows) {
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
      return h`<div class="kpis">${BT.kpi({ label: 'لدى السائقين (الإجمالي)', value: fmt.kwd(sum('total')), sub: BT.config.currency, dot: 'o' })}${BT.kpi({ label: 'منه معتمد', value: fmt.kwd(sum('posted')), dot: 'g' })}${BT.kpi({ label: 'منه غير معتمد', value: fmt.kwd(sum('pending')), sub: 'تقارير بانتظار المراجعة', dot: 'b' })}${BT.kpi({ label: 'فوق حد التنبيه', value: fmt.int(over), sub: 'تنبيه فقط، لا يوقف السائق', dot: 'r', tone: over ? 'danger' : null })}</div>
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
    api.get('/employees', { is_driver: true, limit: 200 }).then(function (rows) {
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
      title: 'تسوية يدوية', subtitle: api.name(driver.name), icon: 'scale', size: 'sm', done: 'تم تسجيل التسوية',
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
          body: h`<div class="form">${BT.f.select({ name: 'branch_id', label: 'الفرع', required: true, options: rows.map(function (r) { return { v: r.branch.id, t: api.name(r.branch.name) + ' — ' + fmt.money(r.treasury) }; }), placeholder: false })}${BT.f.money({ name: 'amount', label: 'المبلغ', required: true, min: 0.001 })}${BT.f.input({ name: 'reference', label: 'رقم إيصال البنك', required: true })}</div>`,
          submit: function (v) { return api.post('/cash/bank-deposits', { branch_id: +v.branch_id, amount: String(v.amount), reference: v.reference }); },
          after: function () { treasuryPanel(el); }
        });
      };
    }).catch(function () {});
  }

  /* ================= التقارير ================= */
  BT.pages['reports'] = function () {
    A.setTitle('التقارير');
    var v = A.view();
    var to = BT.config.today, from = BT.date.add(to, -6);
    BT.render(v, h`${A.head('التقارير', 'ملخص السائقين خلال فترة (حتى 93 يوماً) وأرصدة الكاش، مع التصدير إلى CSV يفتح في Excel', '')}
      ${api.can('reports.view') ? h`<div class="card"><form class="toolbar" data-range style="margin:0 0 12px">${BT.f.date({ name: 'from', label: 'من', value: from, required: true })}${BT.f.date({ name: 'to', label: 'إلى', value: to, required: true })}<button type="submit" class="btn btn-primary" style="align-self:flex-end">${icon('chart-column', 15)} عرض</button>${api.can('reports.export') ? h`<button type="button" class="btn btn-outline" data-csv style="align-self:flex-end">${icon('download', 15)} CSV</button>` : ''}</form><div data-sum></div></div>` : ''}
      ${api.can('cash.view') && api.can('reports.export') ? h`<div class="card mt-16"><div class="card-h"><div class="card-t">${icon('wallet', 16)} أرصدة الكاش لكل السائقين</div><button type="button" class="btn btn-sm btn-outline ms-auto" data-bal-csv>${icon('download', 14)} CSV</button></div><div class="hint">نفس أرقام صفحة الكاش، للتسليم إلى المحاسبة.</div></div>` : ''}`);
    var sumEl = v.querySelector('[data-sum]');
    function load(f, t2) {
      A.load(sumEl, api.get('/reports/daily-summary', { date_from: f, date_to: t2 }), function (d) {
        setTimeout(function () {
          var el = sumEl.querySelector('[data-t]');
          if (el) BT.table(el, {
            rows: d.rows, pageSize: 25, sort: { key: 'orders', dir: 'desc' },
            search: { placeholder: 'السائق أو الرقم الوظيفي…', text: function (r) { return api.name(r.driver.name) + ' ' + r.employee_number; } },
            columns: [
              { key: 'driver', label: 'السائق', sort: function (r) { return api.name(r.driver.name); }, render: function (r) { return A.person(r.driver, r.employee_number); } },
              { key: 'days', label: 'أيام', num: true },
              { key: 'orders', label: 'الطلبات', num: true, render: function (r) { return fmt.int(r.orders); } },
              { key: 'reported_cash', label: 'الكاش المُبلّغ', num: true, sort: function (r) { return Number(r.reported_cash); }, render: function (r) { return fmt.money(r.reported_cash); } },
              { key: 'approved_cash', label: 'المعتمد', num: true, sort: function (r) { return Number(r.approved_cash); }, render: function (r) { return fmt.money(r.approved_cash); } },
              { key: 'waiting', label: 'بانتظار', num: true },
              { key: 'rejected', label: 'مرفوض', num: true }
            ],
            empty: { icon: 'chart-column', title: 'لا توجد تقارير في هذه الفترة' }
          });
        });
        var T = d.totals || {};
        return h`<div class="kpis">${BT.kpi({ label: 'الطلبات', value: fmt.int(T.orders), dot: 'o' })}${BT.kpi({ label: 'الكاش المُبلّغ', value: fmt.money(T.reported_cash), dot: 'b' })}${BT.kpi({ label: 'الكاش المعتمد', value: fmt.money(T.approved_cash), dot: 'g' })}${BT.kpi({ label: 'سائقون', value: fmt.int(d.rows.length), dot: 'p' })}</div><div data-t></div>`;
      }).catch(function () {});
    }
    var form = v.querySelector('[data-range]');
    if (form) {
      form.addEventListener('submit', function (e) { e.preventDefault(); var x = BT.form.values(form); load(x.from, x.to); });
      var csv = v.querySelector('[data-csv]');
      if (csv) csv.onclick = function () { var x = BT.form.values(form); A.downloadFile('/reports/daily-summary', { date_from: x.from, date_to: x.to, format: 'csv' }, 'daily-summary-' + x.from + '-' + x.to + '.csv'); };
      load(from, to);
    }
    var bc = v.querySelector('[data-bal-csv]');
    if (bc) bc.onclick = function () { A.downloadFile('/reports/cash-balances', { format: 'csv' }, 'cash-balances.csv'); };
  };
})();
