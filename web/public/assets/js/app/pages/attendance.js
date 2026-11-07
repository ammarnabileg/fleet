/* =====================================================================
   app/pages/attendance.js — الغياب والإجازات: أيام السائقين التي لم يبدأوا فيها
   يوماً ولم يرسلوا تقريراً يصنّفها الموارد البشرية (غياب، إجازة، راحة، بلا سيارة،
   عطل في النظام)؛ والإجازات تُسجّل وتُعتمد وتُرفض وتُلغى، ولا تتداخل. الراتب
   يخصم الغياب والإجازة بدون راتب فقط إن نصّت الإعدادات على ذلك.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  var MARKS = ['absence', 'leave', 'rest', 'no_vehicle', 'system_fault'];
  var MAX_DAYS = 62;
  A.tone.leave_status = { pending: 'o', approved: 'g', rejected: 'r', cancelled: 'n' };
  A.tone.day_mark = { absence: 'r', leave: 'b', rest: 'n', no_vehicle: 'o', system_fault: 'o' };

  function who(x) { return api.name(x.employee.name) + ' ' + x.employee.employee_number; }
  function day(d) { return h`<span class="num">${fmt.date(d)}</span><span class="sub">${BT.date.dayName(d)}</span>`; }
  function range(from, to) { return h`<span class="num">${fmt.date(from)}</span>${from !== to ? h` ← <span class="num">${fmt.date(to)}</span>` : ''}`; }
  function rangeTools(r) {
    return h`<input class="input" type="date" data-from value="${r.from}" aria-label="من" title="من">
      <input class="input" type="date" data-to value="${r.to}" aria-label="إلى" title="إلى">`;
  }
  function wireRange(el, r, reload) {
    el.addEventListener('change', function (e) {
      if (!e.target.matches('[data-from],[data-to]')) return;
      var from = el.querySelector('[data-from]').value, to = el.querySelector('[data-to]').value;
      if (!from || !to) return;
      if (to < from || BT.date.diff(to, from) >= MAX_DAYS) { BT.toast('الفترة من يوم إلى ' + MAX_DAYS + ' يوماً', { type: 'error' }); return; }
      r.from = from; r.to = to; reload();
    });
  }

  BT.pages['attendance'] = function (p, q) {
    A.setTitle('الغياب والإجازات');
    var v = A.view(), tab = ['days', 'leaves', 'marks', 'types'].indexOf(q.tab) > -1 ? q.tab : q.leave ? 'leaves' : 'days';
    var approve = api.can('leaves.approve');
    BT.render(v, h`${A.head('الغياب والإجازات', 'أيام بلا بداية يوم ولا تقرير يصنّفها الموارد البشرية، والإجازات. الراتب يخصم الغياب والإجازة بدون راتب فقط إن نصّت الإعدادات على ذلك',
        approve ? A.btn('تسجيل إجازة أو طلب تغيب', { icon: 'plus', cls: 'btn-primary', action: 'leave-new' }) : '')}
      ${BT.tabs('att', [['days', 'أيام بلا بداية يوم'], ['leaves', 'طلبات التغيب' + (A.counts.leaves ? ' (' + A.counts.leaves + ')' : '')], ['marks', 'الأيام المصنفة'], ['types', 'أنواع الإجازات']], tab, 'tabs-line')}
      <div data-panel="days" data-group="att" class="${tab === 'days' ? 'active' : ''}"><div class="card"><div id="att-days"></div></div></div>
      <div data-panel="leaves" data-group="att" class="${tab === 'leaves' ? 'active' : ''}"><div class="card"><div id="att-leaves"></div></div></div>
      <div data-panel="marks" data-group="att" class="${tab === 'marks' ? 'active' : ''}"><div class="card"><div id="att-marks"></div></div></div>
      <div data-panel="types" data-group="att" class="${tab === 'types' ? 'active' : ''}"><div class="card"><div class="card-b" id="att-types"></div></div></div>`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      if (t === 'days') daysPanel(document.getElementById('att-days'));
      if (t === 'leaves') leavesPanel(document.getElementById('att-leaves'), q.status);
      if (t === 'marks') marksPanel(document.getElementById('att-marks'));
      if (t === 'types') typesPanel(document.getElementById('att-types'));
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/attendance?tab=' + e.detail); });
    show(tab);
    if (q.leave) A.leaveView(q.leave, function () { if (A._leavesTable) A._leavesTable.refresh(); A.refreshCounts(); });
  };
  BT.actions['leave-new'] = function () { newLeave(function () { A.refreshIfAt('attendance'); A.refreshCounts(); }); };

  /* ---------- أيام بلا بداية يوم ---------- */
  function daysPanel(el) {
    var yesterday = BT.date.add(BT.config.today, -1);
    var r = { from: BT.date.add(yesterday, -13), to: yesterday }, data = { days: [], total: 0 };
    var approve = api.can('leaves.approve');
    var t = BT.table(el, {
      rows: function () { return data.days; },
      search: { placeholder: 'اسم السائق أو رقمه…', text: who },
      tools: rangeTools(r),
      selectable: approve,
      id: function (x) { return x.employee.id + '|' + x.day; },
      bulk: [{ label: 'تصنيف المحدد', icon: 'list-checks', cls: 'btn-primary', run: function (rows, clear) { classify(rows, function () { clear(); load(); }); } }],
      columns: [
        { key: 'employee', label: 'السائق', render: function (x) { return A.person(x.employee, x.employee.employee_number); } },
        { key: 'day', label: 'اليوم', render: function (x) { return day(x.day); } },
        { key: 'held_vehicle', label: 'السيارة', render: function (x) { return x.held_vehicle ? BT.pill('كانت معه سيارة', 'o') : BT.pill('بلا سيارة', 'n'); } }
      ],
      rowClick: approve ? function (x) { classify([x], load); } : null,
      empty: { icon: 'circle-check', title: 'لا توجد أيام تحتاج تصنيفاً', text: 'كل سائق بدأ يومه أو أرسل تقريره أو صُنّف يومه' }
    });
    var note = document.createElement('div');
    note.className = 'hint mt-8';
    el.appendChild(note);
    function load() {
      return api.get('/attendance/days', { date_from: r.from, date_to: r.to }).then(function (res) {
        data = res; t.refresh();
        note.textContent = res.total > res.days.length ? 'يظهر ' + res.days.length + ' من ' + res.total + ': صنّفها ثم اعرض الباقي، أو ضيّق الفترة' : '';
      }, api.fail);
    }
    wireRange(el, r, load);
    load();
  }

  function classify(rows, done) {
    if (!rows.length) return;
    var who = rows.length === 1 ? api.name(rows[0].employee.name) + ' · ' + fmt.date(rows[0].day) : rows.length + ' يوم';
    A.formModal({
      title: 'تصنيف ' + (rows.length === 1 ? 'اليوم' : 'الأيام'), subtitle: who, icon: 'list-checks', size: 'sm',
      body: h`<div class="form">${BT.f.select({ name: 'kind', label: 'التصنيف', required: true, placeholder: false, options: A.options('day_mark', MARKS) })}
        ${BT.f.input({ name: 'note', label: 'ملاحظة', optional: true, placeholder: 'لم يرد على الهاتف' })}</div>
        <div class="hint mt-8">الغياب وحده يُخصم من الراتب، وفقط إن نصّت الإعدادات على ذلك. اليوم المصنّف يُرفع من القائمة، ويمكن إلغاء التصنيف من «الأيام المصنفة».</div>`,
      submitText: 'تصنيف', done: false,
      submit: function (f) {
        return api.post('/attendance/marks', { kind: f.kind, note: f.note || null, days: rows.map(function (x) { return { employee_id: x.employee.id, day: x.day }; }) });
      },
      after: function (res) { BT.toast('صُنّف ' + res.marked + ' يوم'); if (done) done(); }
    });
  }

  /* ---------- طلبات التغيب والإجازات ----------
     أنواع الإجازات بياناتٌ قواعدها قيم افتراضية حسب قانون العمل الكويتي (القطاع الأهلي 6/2010) تُراجع مع الموارد البشرية
     أو المستشار القانوني. الطلب من التطبيق أو من المكتب يُفحص بالقواعد نفسها: الأهلية والحدود والرصيد، وتقسيم أيامه بين
     مدفوع بنسبه وغير مدفوع. ولكل طلب تاريخ بداية احتساب المتابعة: بعد أيام الإعداد يصل تنبيه متابعة حتى «تمت المتابعة». */
  var LEGAL = 'قيم افتراضية حسب قانون العمل — راجعها مع الموارد البشرية/المستشار القانوني';
  var types = null;
  function loadTypes() { return types ? Promise.resolve(types) : api.get('/leave-types').then(function (r) { types = r; return r; }); }
  function kindName(x) { return x.kind_name ? api.name(x.kind_name) : api.t('leave_kind', x.kind); }
  function splitText(split) {
    if (!split || !split.length) return '—';
    return split.map(function (p) { return p.days + ' يوم ' + (p.pay_percent === 100 ? 'مدفوعة' : p.pay_percent === 0 ? 'بدون راتب' : 'بـ ' + p.pay_percent + '%'); }).join(' + ');
  }
  function tiersText(tiers) { return tiers.map(function (t) { return (t.days == null ? 'الباقي' : t.days + ' يوم') + ' @ ' + t.pay_percent + '%'; }).join(' ، '); }
  var PROBLEM_TEXT = function (p) { return api.message({ code: p.code, params: p.params, status: 422 }) || api.t('errors', p.code); };

  function leavesPanel(el, status) {
    var kind = '', source = '';
    loadTypes().then(function (ts) {
      var t = BT.table(el, {
        fetch: function (s) { return api.get('/leaves', { status: s.chip || null, kind: kind || null, source: source || null, limit: s.limit, offset: s.offset }); },
        chips: { value: status || 'pending', all: 'الكل', options: A.options('leave_status', ['pending', 'approved', 'rejected', 'cancelled']) },
        tools: h`<select class="select" data-kind aria-label="النوع"><option value="">كل الأنواع</option>${ts.map(function (x) { return h`<option value="${x.code}">${api.name(x.name)}</option>`; })}</select>
          <select class="select" data-source aria-label="المصدر"><option value="">كل المصادر</option><option value="driver">من التطبيق</option><option value="office">من المكتب</option></select>`,
        columns: [
          { key: 'employee', label: 'الموظف', render: function (x) { return A.person(x.employee); } },
          { key: 'kind', label: 'النوع', render: function (x) { return h`${kindName(x)}<span class="sub">${x.source === 'driver' ? 'من التطبيق' : 'من المكتب'}</span>`; } },
          { key: 'range', label: 'الفترة', render: function (x) { return range(x.date_from, x.date_to); } },
          { key: 'days', label: 'الأيام', num: true, render: function (x) { return h`<span class="num">${x.counted_days}</span>`; } },
          { key: 'split', label: 'الأجر', render: function (x) { return h`<span class="fs-sm">${splitText(x.split)}</span>`; } },
          { key: 'status', label: 'الحالة', render: function (x) { return A.pill('leave_status', x.status); } },
          { key: 'followup', label: 'المتابعة', render: function (x) { return x.followed_up_at ? BT.pill('تمت المتابعة', 'g') : h`<span class="num">${fmt.date(x.followup_due)}</span>`; } },
          { key: 'created_at', label: 'سُجّل', render: function (x) { return h`${fmt.dt(x.created_at)}<span class="sub">${x.created_by || ''}</span>`; } }
        ],
        rowClick: function (x) { A.leaveView(x.id, function () { t.refresh(); A.refreshCounts(); }); },
        empty: { icon: 'calendar', title: 'لا توجد طلبات هنا' }
      });
      el.addEventListener('change', function (e) {
        if (e.target.matches('[data-kind]')) { kind = e.target.value; t.refresh(); }
        if (e.target.matches('[data-source]')) { source = e.target.value; t.refresh(); }
      });
      A._leavesTable = t;
    }, api.fail);
  }

  function newLeave(done) {
    Promise.all([A.allEmployees({}), loadTypes()]).then(function (r) {
      var people = r[0], ts = r[1].filter(function (x) { return x.active; });
      A.formModal({
        title: 'تسجيل إجازة أو طلب تغيب', subtitle: 'لا تتداخل إجازتان للموظف نفسه. ' + LEGAL, icon: 'calendar', size: 'lg',
        body: h`<div class="form-grid">
          <div class="full">${A.picker({ name: 'employee', label: 'الموظف', required: true, items: people.map(function (x) { return { id: x.id, label: x.employee_number + ' · ' + api.name(x.name) }; }) })}</div>
          ${BT.f.select({ name: 'kind', label: 'النوع', required: true, placeholder: false, options: ts.map(function (x) { return { v: x.code, t: api.name(x.name) }; }) })}
          ${BT.f.date({ name: 'followup_from', label: 'تاريخ بداية احتساب المتابعة', required: true, value: BT.config.today, hint: 'يصل تنبيه المتابعة بعد عدد الأيام المحدد في الإعدادات من هذا التاريخ' })}
          ${BT.f.input({ name: 'from', label: 'من', type: 'date', required: true, value: BT.config.today })}
          ${BT.f.input({ name: 'to', label: 'إلى', type: 'date', required: true, value: BT.config.today })}
          <div class="full" data-preview></div>
          ${BT.f.upload({ name: 'file', label: 'شهادة مرضية أو مستند', optional: true, full: true, accept: 'image/*,application/pdf' })}
          ${BT.f.textarea({ name: 'note', label: 'السبب أو ملاحظة', optional: true, full: true, rows: 2 })}
          <label class="check full"><input type="checkbox" name="approve" checked> <span>معتمدة الآن (اتُّفق عليها)</span></label>
          <label class="check full"><input type="checkbox" name="paid"> <span>مدفوعة (للطارئة والأخرى فقط، عند الاعتماد)</span></label>
          <label class="check full"><input type="checkbox" name="override"> <span>تسجيلها رغم مخالفة القواعد (يُسجَّل في سجل التدقيق)</span></label></div>`,
        submitText: 'تسجيل', done: false,
        onOpen: function (dlg) {
          var form = dlg.form, box = form.querySelector('[data-preview]');
          function preview() {
            var v = BT.form.values(form), emp = v.employee ? A.picked('employee', v.employee) : null;
            if (!emp || !v.kind || !v.from || !v.to || v.to < v.from) { BT.render(box, ''); return; }
            api.post('/leaves/preview', { employee_id: emp, kind: v.kind, date_from: v.from, date_to: v.to, paid: !!form.querySelector('[name=paid]').checked }).then(function (p) {
              BT.render(box, h`<div class="card"><div class="card-b fs-sm" data-leave-preview>
                <div><b>${p.days}</b> يوم محسوب · ${splitText(p.split)}</div>
                ${p.balance && p.balance.available != null ? h`<div class="muted">الرصيد المتاح: <span class="num">${p.balance.available}</span></div>` : ''}
                ${p.problems.map(function (x) { return h`<div class="text-danger" data-problem="${x.code}">${PROBLEM_TEXT(x)}</div>`; })}
                ${p.warnings.map(function (w) { return h`<div class="muted" data-warning="${w}">${w === 'gender_unknown' ? 'جنس الموظف غير مسجّل: لم يُفحص' : w}</div>`; })}</div></div>`);
            }, function (err) { BT.render(box, h`<div class="text-danger fs-sm">${api.message(err)}</div>`); });
          }
          form.addEventListener('change', preview);
        },
        submit: function (f, dlg) {
          if (f.to < f.from) return Promise.reject(new Error('تاريخ النهاية قبل البداية'));
          var c = function (n) { return dlg.form.querySelector('[name=' + n + ']').checked; };
          return (f.file && f.file[0] ? api.upload(f.file[0]).then(function (x) { return x.sha256; }) : Promise.resolve(null)).then(function (sha) {
            return api.post('/leaves', { employee_id: A.picked('employee', f.employee), kind: f.kind, date_from: f.from, date_to: f.to, note: f.note || null, file_sha256: sha, approve: c('approve'), paid: c('paid'), override: c('override'), followup_from: f.followup_from || null });
          });
        },
        after: function (x) { BT.toast(x.status === 'approved' ? 'سُجّلت الإجازة معتمدة' : 'سُجّلت الإجازة بانتظار الاعتماد', { sub: api.name(x.employee.name) + ' · ' + x.counted_days + ' يوم' }); if (done) done(); }
      });
    }, api.fail);
  }

  function balancesTable(rows) {
    return h`<div class="table-wrap"><table class="t compact" data-balances><thead><tr><th>النوع</th><th class="num">هذه السنة</th><th class="num">المتبقي</th><th class="num">بانتظار</th></tr></thead><tbody>${rows.map(function (b) {
      var left = b.available != null ? b.available : b.left_year != null ? b.left_year : b.left_service;
      return h`<tr data-balance="${b.code}"><td>${api.name(b.name)}${b.eligible ? '' : h`<span class="sub">${api.t('errors', b.reason)}</span>`}</td><td class="num">${b.used_year}</td><td class="num">${left == null ? '—' : left}${b.accrued != null ? h`<span class="sub">مكتسب ${b.accrued}</span>` : ''}</td><td class="num">${b.pending}</td></tr>`;
    })}</tbody></table></div>`;
  }
  A.leaveBalances = function (employeeId) { return api.get('/employees/' + employeeId + '/leave-balances').then(balancesTable); };

  A.leaveView = function leave(id, done) {
    Promise.all([api.get('/leaves/' + id), loadTypes()]).then(function (r) {
      var x = r[0];
      var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }], can = api.can('leaves.approve');
      function act(fn) { return function (dlg) { fn(x, function () { dlg.close(); if (done) done(); leave(id, done); }); }; }
      if (can && (x.status === 'pending' || x.status === 'approved')) btns.push({ label: 'إلغاء', cls: 'btn-ghost', icon: 'ban', close: false, onClick: act(cancel) });
      if (!x.followed_up_at && (x.status === 'pending' || x.status === 'approved')) btns.push({ label: 'تمت المتابعة', cls: 'btn-outline', icon: 'circle-check', close: false, onClick: act(followedUp) });
      if (can && x.status === 'pending') btns.push({ label: 'رفض', cls: 'btn-outline', icon: 'x', close: false, onClick: act(reject) });
      if (can && x.status === 'pending') btns.push({ label: 'اعتماد', cls: 'btn-primary', icon: 'check', close: false, onClick: act(approveIt) });
      var bal = BT.uid('bal');
      BT.drawer.open({
        title: h`${kindName(x)} · <span class="num">${x.counted_days}</span> يوم`, subtitle: api.name(x.employee.name), icon: 'calendar',
        body: h`${BT.kv([
          ['الحالة', A.pill('leave_status', x.status)],
          ['الموظف', A.person(x.employee)],
          ['الفترة', range(x.date_from, x.date_to)],
          ['الأيام المحسوبة', h`<span class="num">${x.counted_days}</span> من <span class="num">${x.days}</span> يوم تقويمي`],
          ['الأجر', h`<span data-split>${splitText(x.split)}</span>${x.paid_override ? ' (جعلها المكتب مدفوعة)' : ''}`],
          ['المصدر', x.source === 'driver' ? 'طلب من التطبيق' : 'سجّله المكتب'],
          x.rules_overridden ? ['القواعد', BT.pill('سُجّلت رغم مخالفة القواعد', 'o')] : null,
          x.note ? ['السبب / ملاحظة', h`<span style="white-space:normal">${x.note}</span>`] : null,
          x.has_file ? ['المرفق', h`<a href="${api.url('/leaves/' + x.id + '/file')}" target="_blank" rel="noopener">${icon('file-text', 14)} فتح</a>`] : null,
          ['بداية احتساب المتابعة', h`<span class="num" data-followup-from>${fmt.date(x.followup_from)}</span> ${can ? h`<button type="button" class="btn btn-sm btn-ghost" data-edit-followup>${icon('pencil', 12)} تعديل</button>` : ''}<span class="sub">التنبيه في ${fmt.date(x.followup_due)}</span>`],
          x.followed_up_at ? ['المتابعة', (x.followed_up_by || '') + ' · ' + fmt.dt(x.followed_up_at)] : null,
          ['التسجيل', (x.created_by || (x.source === 'driver' ? 'السائق' : '')) + ' · ' + fmt.dt(x.created_at)],
          x.decided_at ? ['القرار', (x.decided_by || '') + ' · ' + fmt.dt(x.decided_at) + (x.decision_note ? ' · ' + x.decision_note : '')] : null,
          x.cancel_reason ? ['سبب الإلغاء', x.cancel_reason] : null
        ].filter(Boolean))}<div class="section-t mt-16">رصيد الموظف</div><div id="${bal}">${A.spinner()}</div><div class="hint mt-8">${LEGAL}</div>`,
        buttons: btns,
        onOpen: function (dlg) {
          var root = dlg.panel;
          A.leaveBalances(x.employee.id).then(function (t) { var b = document.getElementById(bal); if (b) BT.render(b, t); }, function () {});
          var edit = root.querySelector('[data-edit-followup]');
          if (edit) edit.addEventListener('click', function () {
            A.formModal({ title: 'تاريخ بداية احتساب المتابعة', icon: 'calendar', size: 'sm',
              body: h`<div class="form">${BT.f.date({ name: 'd', label: 'التاريخ', required: true, value: x.followup_from })}</div>`,
              submit: function (f) { return api.put('/leaves/' + x.id + '/followup-from', { followup_from: f.d }); },
              done: 'عُدّل تاريخ المتابعة', after: function () { dlg.close(); if (done) done(); leave(id, done); } });
          });
        }
      });
    }, api.fail);
  };
  function approveIt(x, done) {
    var t = (types || []).find(function (k) { return k.code === x.kind; });
    var mayPay = t && t.office_may_pay;
    A.formModal({ title: 'اعتماد الطلب', icon: 'check', size: 'sm', submitText: 'اعتماد',
      body: h`<div class="confirm-msg">أيامه لا تُعرض في «أيام بلا بداية يوم»، والأيام غير المدفوعة تُخصم من الراتب إن نصّت الإعدادات على ذلك.<br>${splitText(x.split)}</div>
        ${mayPay ? h`<label class="check mt-12"><input type="checkbox" name="paid"> <span>مدفوعة بالكامل</span></label>` : ''}`,
      submit: function (f, dlg) { var p = dlg.form.querySelector('[name=paid]'); return api.post('/leaves/' + x.id + '/approve', { paid: !!(p && p.checked) }); },
      done: 'اعتُمد الطلب', after: done });
  }
  function reject(x, done) {
    A.confirmRun({ title: 'رفض الطلب', confirmText: 'رفض', tone: 'danger', reason: { label: 'السبب (يراه السائق)', required: true }, run: function (reason) { return api.post('/leaves/' + x.id + '/reject', { note: reason }); }, done: 'رُفض الطلب', after: done });
  }
  function cancel(x, done) {
    A.confirmRun({ title: 'إلغاء الطلب', message: 'تعود أيامه إلى قائمة الأيام التي تحتاج تصنيفاً. لا يُلغى طلب في شهر اعتُمد راتبه.', confirmText: 'إلغاء', tone: 'danger', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/leaves/' + x.id + '/cancel', { reason: reason }); }, done: 'أُلغي الطلب', after: done });
  }
  function followedUp(x, done) {
    A.confirmRun({ title: 'تمت المتابعة', message: 'يُغلق تنبيه المتابعة ولا يتكرر لهذا الطلب.', confirmText: 'تمت المتابعة', tone: 'success', run: function () { return api.post('/leaves/' + x.id + '/followed-up', {}); }, done: 'سُجّلت المتابعة', after: done });
  }

  /* ---------- أنواع الإجازات ---------- */
  function typesPanel(el) {
    var canEdit = api.can('settings.update');
    function draw() {
      types = null;
      A.load(el, loadTypes(), function (ts) {
        setTimeout(function () { BT.$$('[data-type-edit]', el).forEach(function (b) { b.addEventListener('click', function () { editType(ts.find(function (t) { return t.code === b.getAttribute('data-type-edit'); }), draw); }); }); });
        return h`<div class="hint mb-12" data-legal>${LEGAL}. الغياب بدون إذن ليس نوعاً يُطلب: يسجّله المكتب من «أيام بلا بداية يوم»، وتنبيهات المادة 41 في الإعدادات.</div>
          <div class="table-wrap"><table class="t compact" data-types><thead><tr><th>النوع</th><th>المادة</th><th>شرائح الأجر</th><th>الحدود</th><th>الشروط</th><th>الحالة</th><th></th></tr></thead><tbody>${ts.map(function (t) {
            var limits = [t.max_per_occurrence ? 'للمرة ' + t.max_per_occurrence : '', t.max_per_year ? (t.accrues ? 'تُكتسب ' + t.max_per_year + ' سنوياً' : 'للسنة ' + t.max_per_year) : '', t.max_per_service ? 'للخدمة ' + t.max_per_service : ''].filter(Boolean).join(' · ') || '—';
            var conds = [t.min_service_months ? 'بعد ' + t.min_service_months + ' شهراً' : '', t.once_per_service ? 'مرة في الخدمة' : '', t.requires_attachment ? 'مرفق إلزامي' : '', t.eligible_gender === 'female' ? 'للإناث' : t.eligible_gender === 'male' ? 'للذكور' : '', t.counts === 'working' ? 'أيام عمل' : 'أيام تقويمية', t.office_may_pay ? 'يجعلها المكتب مدفوعة' : ''].filter(Boolean).join(' · ');
            return h`<tr data-type="${t.code}"><td><b>${api.name(t.name)}</b><span class="sub ltr">${t.code}</span></td><td>${t.legal_ref || '—'}</td><td class="fs-sm">${tiersText(t.tiers)}</td><td class="fs-sm">${limits}</td><td class="fs-sm">${conds}</td><td>${t.active ? BT.pill('مفعّل', 'g') : BT.pill('موقوف', 'n')}</td><td>${canEdit ? h`<button type="button" class="btn btn-sm btn-outline" data-type-edit="${t.code}">${icon('pencil', 12)} تعديل</button>` : ''}</td></tr>`;
          })}</tbody></table></div>`;
      }).catch(function () {});
    }
    draw();
  }
  function editType(t, done) {
    var n = function (v) { return v == null ? '' : v; };
    A.formModal({
      title: 'تعديل نوع الإجازة', subtitle: LEGAL, icon: 'settings', size: 'lg',
      body: h`<div class="form-grid">
        ${['ar', 'en', 'fr', 'sw', 'hi', 'fil'].map(function (l) { return BT.f.input({ name: 'name_' + l, label: 'الاسم (' + l + ')', required: l === 'ar' || l === 'en', value: (t.name || {})[l] || '' }); })}
        ${BT.f.input({ name: 'legal_ref', label: 'المادة', optional: true, value: n(t.legal_ref) })}
        ${BT.f.input({ name: 'tiers', label: 'شرائح الأجر (أيام:نسبة، مفصولة بفواصل؛ * للباقي)', required: true, full: true, value: t.tiers.map(function (x) { return (x.days == null ? '*' : x.days) + ':' + x.pay_percent; }).join(', '), hint: 'مثال المرضية: 15:100, 10:75, 10:50, 10:25, 30:0' })}
        ${BT.f.select({ name: 'tier_period', label: 'الشرائح تُحتسب', placeholder: false, value: t.tier_period, options: [{ v: 'occurrence', t: 'لكل إجازة' }, { v: 'service_year', t: 'على سنة الخدمة كلها' }] })}
        ${BT.f.select({ name: 'counts', label: 'الأيام', placeholder: false, value: t.counts, options: [{ v: 'calendar', t: 'أيام تقويمية' }, { v: 'working', t: 'أيام عمل (دون أيام الراحة)' }] })}
        ${BT.f.input({ name: 'max_per_occurrence', label: 'أقصى أيام للمرة', optional: true, num: true, value: n(t.max_per_occurrence) })}
        ${BT.f.input({ name: 'max_per_year', label: t.accrues ? 'الاستحقاق السنوي (يُكتسب)' : 'أقصى أيام لسنة الخدمة', optional: true, num: true, value: n(t.max_per_year) })}
        ${BT.f.input({ name: 'max_per_service', label: 'أقصى أيام لمدة الخدمة', optional: true, num: true, value: n(t.max_per_service) })}
        ${BT.f.input({ name: 'min_service_months', label: 'أشهر الخدمة المطلوبة', num: true, value: t.min_service_months })}
        ${BT.f.select({ name: 'eligible_gender', label: 'ينطبق على', placeholder: false, value: t.eligible_gender || '', options: [{ v: '', t: 'الجميع' }, { v: 'female', t: 'الإناث' }, { v: 'male', t: 'الذكور' }] })}
        ${BT.f.input({ name: 'sort_order', label: 'الترتيب', num: true, value: t.sort_order })}
        <label class="check"><input type="checkbox" name="once_per_service"${t.once_per_service ? raw(' checked') : ''}> <span>مرة واحدة في الخدمة</span></label>
        <label class="check"><input type="checkbox" name="requires_attachment"${t.requires_attachment ? raw(' checked') : ''}> <span>مرفق إلزامي</span></label>
        <label class="check"><input type="checkbox" name="office_may_pay"${t.office_may_pay ? raw(' checked') : ''}> <span>يجعلها المكتب مدفوعة عند الاعتماد</span></label>
        <label class="check"><input type="checkbox" name="driver_may_request"${t.driver_may_request ? raw(' checked') : ''}> <span>يطلبها السائق من التطبيق</span></label>
        <label class="check"><input type="checkbox" name="active"${t.active ? raw(' checked') : ''}> <span>مفعّل</span></label></div>`,
      submit: function (f, dlg) {
        var tiers = String(f.tiers).split(/[,،]/).map(function (s) { return s.trim(); }).filter(Boolean).map(function (s) {
          var p = s.split(':'); return { days: p[0].trim() === '*' ? null : Number(p[0]), pay_percent: Number(p[1]) };
        });
        if (tiers.some(function (x) { return isNaN(x.pay_percent) || (x.days != null && isNaN(x.days)); })) return Promise.reject(new Error('اكتب الشرائح هكذا: 15:100, 10:75'));
        var name = {}; ['ar', 'en', 'fr', 'sw', 'hi', 'fil'].forEach(function (l) { if (f['name_' + l]) name[l] = f['name_' + l]; });
        var num = function (v) { return v === '' || v == null ? null : Number(v); };
        var c = function (k) { return dlg.form.querySelector('[name=' + k + ']').checked; };
        return api.put('/leave-types/' + t.code, { version: t.version, name: name, legal_ref: f.legal_ref || null, tiers: tiers, tier_period: f.tier_period, counts: f.counts,
          max_per_occurrence: num(f.max_per_occurrence), max_per_year: num(f.max_per_year), max_per_service: num(f.max_per_service), min_service_months: num(f.min_service_months) || 0,
          eligible_gender: f.eligible_gender || null, sort_order: num(f.sort_order) || 0, once_per_service: c('once_per_service'), requires_attachment: c('requires_attachment'),
          office_may_pay: c('office_may_pay'), driver_may_request: c('driver_may_request'), active: c('active') });
      },
      done: 'حُفظ نوع الإجازة', after: done
    });
  }

  /* ---------- الأيام المصنفة ---------- */
  function marksPanel(el) {
    var r = { from: BT.date.add(BT.config.today, -30), to: BT.config.today }, rows = [];
    var t = BT.table(el, {
      rows: function () { return rows; },
      search: { placeholder: 'اسم الموظف أو رقمه…', text: who },
      chips: { value: '', all: 'الكل', key: 'kind', options: A.options('day_mark', MARKS) },
      tools: rangeTools(r),
      columns: [
        { key: 'employee', label: 'الموظف', render: function (x) { return A.person(x.employee, x.employee.employee_number); } },
        { key: 'day', label: 'اليوم', render: function (x) { return day(x.day); } },
        { key: 'kind', label: 'التصنيف', render: function (x) { return A.pill('day_mark', x.kind); } },
        { key: 'note', label: 'ملاحظة', render: function (x) { return x.note || '—'; } },
        { key: 'marked_at', label: 'صنّفه', render: function (x) { return h`${x.marked_by || '—'}<span class="sub">${fmt.dt(x.marked_at)}</span>`; } }
      ],
      rowMenu: api.can('leaves.approve') ? function (x) {
        return [{ label: 'إلغاء التصنيف', icon: 'undo-2', danger: true, onClick: function () {
          A.confirmRun({ title: 'إلغاء تصنيف اليوم', message: api.name(x.employee.name) + ' · ' + fmt.date(x.day) + ': يعود اليوم إلى قائمة الأيام التي تحتاج تصنيفاً.', confirmText: 'إلغاء التصنيف', tone: 'danger',
            run: function () { return api.post('/attendance/marks/remove', { employee_id: x.employee.id, day: x.day }); }, done: 'أُلغي التصنيف', after: load });
        } }];
      } : null,
      empty: { icon: 'calendar', title: 'لا توجد أيام مصنفة في هذه الفترة' }
    });
    function load() { return api.get('/attendance/marks', { date_from: r.from, date_to: r.to }).then(function (res) { rows = res; t.refresh(); }, api.fail); }
    wireRange(el, r, load);
    load();
  }
})();
