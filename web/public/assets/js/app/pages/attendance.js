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
  var KINDS = ['annual', 'sick', 'emergency', 'unpaid', 'other'];
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
    var v = A.view(), tab = ['days', 'leaves', 'marks'].indexOf(q.tab) > -1 ? q.tab : 'days';
    var approve = api.can('leaves.approve');
    BT.render(v, h`${A.head('الغياب والإجازات', 'أيام بلا بداية يوم ولا تقرير يصنّفها الموارد البشرية، والإجازات. الراتب يخصم الغياب والإجازة بدون راتب فقط إن نصّت الإعدادات على ذلك',
        approve ? A.btn('تسجيل إجازة', { icon: 'plus', cls: 'btn-primary', action: 'leave-new' }) : '')}
      ${BT.tabs('att', [['days', 'أيام بلا بداية يوم'], ['leaves', 'الإجازات'], ['marks', 'الأيام المصنفة']], tab, 'tabs-line')}
      <div data-panel="days" data-group="att" class="${tab === 'days' ? 'active' : ''}"><div class="card"><div id="att-days"></div></div></div>
      <div data-panel="leaves" data-group="att" class="${tab === 'leaves' ? 'active' : ''}"><div class="card"><div id="att-leaves"></div></div></div>
      <div data-panel="marks" data-group="att" class="${tab === 'marks' ? 'active' : ''}"><div class="card"><div id="att-marks"></div></div></div>`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      if (t === 'days') daysPanel(document.getElementById('att-days'));
      if (t === 'leaves') leavesPanel(document.getElementById('att-leaves'), q.status);
      if (t === 'marks') marksPanel(document.getElementById('att-marks'));
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/attendance?tab=' + e.detail); });
    show(tab);
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

  /* ---------- الإجازات ---------- */
  function leavesPanel(el, status) {
    var t = BT.table(el, {
      fetch: function (s) { return api.get('/leaves', { status: s.chip || null, limit: s.limit, offset: s.offset }); },
      chips: { value: status || 'pending', all: 'الكل', options: A.options('leave_status', ['pending', 'approved', 'rejected', 'cancelled']) },
      columns: [
        { key: 'employee', label: 'الموظف', render: function (x) { return A.person(x.employee); } },
        { key: 'kind', label: 'النوع', render: function (x) { return api.t('leave_kind', x.kind); } },
        { key: 'range', label: 'الفترة', render: function (x) { return range(x.date_from, x.date_to); } },
        { key: 'days', label: 'الأيام', num: true, render: function (x) { return h`<span class="num">${x.days}</span>`; } },
        { key: 'status', label: 'الحالة', render: function (x) { return A.pill('leave_status', x.status); } },
        { key: 'created_at', label: 'سُجّلت', render: function (x) { return h`${fmt.dt(x.created_at)}<span class="sub">${x.created_by || ''}</span>`; } }
      ],
      rowClick: function (x) { leave(x.id, function () { t.refresh(); A.refreshCounts(); }); },
      empty: { icon: 'calendar', title: 'لا توجد إجازات هنا' }
    });
    A._leavesTable = t;
  }

  function newLeave(done) {
    A.allEmployees({}).then(function (people) {
      A.formModal({
        title: 'تسجيل إجازة', subtitle: 'لا تتداخل إجازتان للموظف نفسه', icon: 'calendar', size: 'lg',
        body: h`<div class="form-grid">
          <div class="full">${A.picker({ name: 'employee', label: 'الموظف', required: true, items: people.map(function (x) { return { id: x.id, label: x.employee_number + ' · ' + api.name(x.name) }; }) })}</div>
          ${BT.f.select({ name: 'kind', label: 'النوع', required: true, placeholder: false, options: A.options('leave_kind', KINDS) })}
          <div></div>
          ${BT.f.input({ name: 'from', label: 'من', type: 'date', required: true, value: BT.config.today })}
          ${BT.f.input({ name: 'to', label: 'إلى', type: 'date', required: true, value: BT.config.today })}
          ${BT.f.upload({ name: 'file', label: 'شهادة مرضية أو مستند', optional: true, full: true, accept: 'image/*,application/pdf' })}
          ${BT.f.textarea({ name: 'note', label: 'ملاحظة', optional: true, full: true, rows: 2 })}
          <label class="check full"><input type="checkbox" name="approve" checked> <span>معتمدة الآن (اتُّفق عليها)</span></label></div>`,
        submitText: 'تسجيل', done: false,
        submit: function (f, dlg) {
          if (f.to < f.from) return Promise.reject(new Error('تاريخ النهاية قبل البداية'));
          var approve = dlg.form.querySelector('[name=approve]').checked;
          return (f.file && f.file[0] ? api.upload(f.file[0]).then(function (x) { return x.sha256; }) : Promise.resolve(null)).then(function (sha) {
            return api.post('/leaves', { employee_id: A.picked('employee', f.employee), kind: f.kind, date_from: f.from, date_to: f.to, note: f.note || null, file_sha256: sha, approve: approve });
          });
        },
        after: function (x) { BT.toast(x.status === 'approved' ? 'سُجّلت الإجازة معتمدة' : 'سُجّلت الإجازة بانتظار الاعتماد', { sub: api.name(x.employee.name) + ' · ' + x.days + ' يوم' }); if (done) done(); }
      });
    }, api.fail);
  }

  function leave(id, done) {
    api.get('/leaves/' + id).then(function (x) {
      var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }], can = api.can('leaves.approve');
      function act(fn) { return function (dlg) { fn(x, function () { dlg.close(); if (done) done(); leave(id, done); }); }; }
      if (can && (x.status === 'pending' || x.status === 'approved')) btns.push({ label: 'إلغاء الإجازة', cls: 'btn-ghost', icon: 'ban', close: false, onClick: act(cancel) });
      if (can && x.status === 'pending') btns.push({ label: 'رفض', cls: 'btn-outline', icon: 'x', close: false, onClick: act(reject) });
      if (can && x.status === 'pending') btns.push({ label: 'اعتماد', cls: 'btn-primary', icon: 'check', close: false, onClick: act(approveIt) });
      BT.drawer.open({
        title: h`إجازة ${api.t('leave_kind', x.kind)} · <span class="num">${x.days}</span> يوم`, subtitle: api.name(x.employee.name), icon: 'calendar',
        body: BT.kv([
          ['الحالة', A.pill('leave_status', x.status)],
          ['الموظف', A.person(x.employee)],
          ['الفترة', range(x.date_from, x.date_to)],
          x.note ? ['ملاحظة', h`<span style="white-space:normal">${x.note}</span>`] : null,
          x.has_file ? ['المستند', h`<a href="${api.url('/leaves/' + x.id + '/file')}" target="_blank" rel="noopener">${icon('file-text', 14)} فتح</a>`] : null,
          ['التسجيل', (x.created_by || '') + ' · ' + fmt.dt(x.created_at)],
          x.decided_at ? ['القرار', (x.decided_by || '') + ' · ' + fmt.dt(x.decided_at) + (x.decision_note ? ' · ' + x.decision_note : '')] : null,
          x.cancel_reason ? ['سبب الإلغاء', x.cancel_reason] : null
        ].filter(Boolean)),
        buttons: btns
      });
    }, api.fail);
  }
  function approveIt(x, done) {
    A.confirmRun({ title: 'اعتماد الإجازة', message: 'أيامها لا تُعرض في «أيام بلا بداية يوم»' + (x.kind === 'unpaid' ? '، وتُخصم من الراتب إن نصّت الإعدادات على ذلك.' : '.'), confirmText: 'اعتماد', tone: 'success', run: function () { return api.post('/leaves/' + x.id + '/approve', {}); }, done: 'اعتُمدت الإجازة', after: done });
  }
  function reject(x, done) {
    A.confirmRun({ title: 'رفض الإجازة', confirmText: 'رفض', tone: 'danger', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/leaves/' + x.id + '/reject', { note: reason }); }, done: 'رُفضت الإجازة', after: done });
  }
  function cancel(x, done) {
    A.confirmRun({ title: 'إلغاء الإجازة', message: 'تعود أيامها إلى قائمة الأيام التي تحتاج تصنيفاً. لا تُلغى إجازة في شهر اعتُمد راتبه.', confirmText: 'إلغاء الإجازة', tone: 'danger', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/leaves/' + x.id + '/cancel', { reason: reason }); }, done: 'أُلغيت الإجازة', after: done });
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
