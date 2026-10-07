/* =====================================================================
   app/pages/approvals.js — مسارات الاعتماد: ما ينتظر قراري (خطواتي وخطوات من
   فوّضني)، ومسار كل عملية (الخطوات بالدور أو بالشخص ومن مبلغ، والتصعيد بعد ساعات)،
   والتفويض أثناء الغياب. عملية بلا مسار تبقى على صلاحيتها كما كانت.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  var PROCESSES = ['daily_report', 'maintenance_request', 'maintenance_quote', 'maintenance_invoice', 'accident_estimate', 'expense', 'payroll_run'];
  A.tone.approval_status = { pending: 'o', approved: 'g', rejected: 'r', cancelled: 'n' };
  A.tone.delegation_status = { active: 'g', upcoming: 'b', ended: 'n', cancelled: 'n' };

  function amt(v) { return v == null || Number(v) === 0 ? '—' : BT.amt(Number(v)); }
  function stepName(s) { return api.name(s.name); }
  function approver(s) { return s.user ? s.user.name : s.role ? api.name(s.role.name) : '—'; }
  /* أين يُفتح المستند نفسه */
  function link(r) {
    var routes = {
      daily_report: '#/daily', maintenance_request: '#/maintenance/' + r.document_id, maintenance_quote: '#/maintenance',
      maintenance_invoice: '#/maintenance?tab=invoices', accident_estimate: '#/accidents/' + r.document_id,
      expense: '#/finance', payroll_run: '#/payroll/run/' + r.document_id
    };
    return routes[r.process];
  }

  BT.pages['approvals'] = function (p, q) {
    A.setTitle('مسارات الاعتماد');
    var v = A.view();
    var tabs = [['inbox', 'بانتظار اعتمادي' + (A.counts.approvals ? ' (' + A.counts.approvals + ')' : '')], ['workflows', 'المسارات'], ['delegations', 'التفويض']];
    var tab = tabs.some(function (t) { return t[0] === q.tab; }) ? q.tab : 'inbox';
    BT.render(v, h`${A.head('مسارات الاعتماد', 'خطوات كل عملية بالدور أو بالشخص ومن مبلغ، وسبب لكل رفض، وسجل لكل قرار. العملية بلا مسار تُعتمد بالصلاحية كما كانت')}
      ${BT.tabs('wfl', tabs, tab, 'tabs-line')}
      ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="wfl" class="${t[0] === tab ? 'active' : ''}"><div id="wfl-${t[0]}"></div></div>`; })}`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      var el = document.getElementById('wfl-' + t);
      ({ inbox: inboxPanel, workflows: workflowsPanel, delegations: delegationsPanel })[t](el);
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/approvals?tab=' + e.detail); });
    show(tab);
  };

  /* ================= بانتظار اعتمادي ================= */
  function inboxPanel(el) {
    BT.render(el, h`<div class="card"><div data-t></div></div>`);
    var t = BT.table(el.querySelector('[data-t]'), {
      fetch: function () { return api.get('/approvals/inbox'); },
      search: { placeholder: 'بحث بالمرجع', text: function (r) { return r.document_ref + ' ' + api.t('approval_process', r.process); } },
      columns: [
        { key: 'process', label: 'العملية', render: function (r) { return h`${api.t('approval_process', r.process)}<span class="sub ltr">${r.document_ref}</span>`; } },
        { key: 'company', label: 'الشركة', render: function (r) { return r.company_id ? api.company(r.company_id) : '—'; } },
        { key: 'amount', label: 'المبلغ', num: true, render: function (r) { return amt(r.amount); } },
        { key: 'step', label: 'الخطوة', render: function (r) { var s = r.steps[r.current]; return h`<span class="num">${r.current + 1}/${r.steps.length}</span> ${stepName(s)}${r.escalated ? h` ${BT.pill('مُصعّد', 'r')}` : ''}`; } },
        { key: 'since', label: 'تنتظر منذ', render: function (r) { return fmt.since(r.step_since); } }
      ],
      rowClick: function (r) { request(r, function () { t.refresh(); A.refreshCounts(); }); },
      empty: { icon: 'inbox', title: 'لا شيء ينتظر قرارك', text: 'تظهر هنا المستندات التي تصل خطوتك فيها، أو خطوة من فوّضك' }
    });
  }

  /* الخطوات وما قيل في كل منها */
  function trail(r) {
    var by = {};
    r.decisions.forEach(function (d) { (by[d.step] = by[d.step] || []).push(d); });
    return h`<div class="timeline">${r.steps.map(function (s, i) {
      var ds = by[i] || [];
      var done = ds.some(function (d) { return d.decision === 'approved'; }), refused = ds.some(function (d) { return d.decision === 'rejected'; });
      var now = i === r.current && r.status === 'pending';
      var tone = refused ? 'r' : done ? 'g' : now ? 'o' : 'pending';
      return h`<div class="tl-item" data-step-state="${refused ? 'rejected' : done ? 'approved' : now ? 'current' : 'next'}"><span class="tl-ic ${tone}">${icon(refused ? 'x' : done ? 'check' : now ? 'hourglass' : 'circle-dot', 13)}</span><div>
        <div class="tl-t">${i + 1}. ${stepName(s)} · ${approver(s)}${s.escalate_role ? h`<span class="muted"> · التصعيد إلى ${api.name(s.escalate_role.name)}</span>` : ''}</div>
        ${ds.map(function (d) {
          return h`<div class="tl-d">${api.t('approval_decision', d.decision)}${d.by ? ' · ' + d.by.name : ' · النظام'}${d.on_behalf_of ? ' نيابة عن ' + d.on_behalf_of.name : ''} · ${fmt.dt(d.at)}${d.reason ? h`<div style="white-space:normal">${d.reason}</div>` : ''}</div>`;
        })}</div></div>`;
    })}</div>`;
  }
  A.approvalTrail = trail;

  function request(r, done) {
    var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
    function act(approve) {
      return function (dlg) {
        A.confirmRun({
          title: approve ? 'اعتماد الخطوة' : 'رفض المستند',
          message: approve ? (r.current + 1 < r.steps.length ? 'ينتقل المستند إلى الخطوة التالية: ' + stepName(r.steps[r.current + 1]) : 'آخر خطوة: يُعتمد المستند.') : 'يُرفض المستند ويعود لصاحبه بالسبب.',
          confirmText: approve ? 'اعتماد' : 'رفض', tone: approve ? 'success' : 'danger',
          reason: { label: approve ? 'ملاحظة' : 'السبب', required: !approve },
          run: function (reason) { return api.post('/approvals/requests/' + r.id + '/decide', { approve: approve, reason: reason || null }); },
          after: function (res) {
            if (!res) return;
            BT.toast(res.status === 'approved' ? 'اعتُمد المستند' : res.status === 'rejected' ? 'رُفض المستند' : 'سُجّل قرارك', { sub: res.status === 'pending' ? 'بانتظار: ' + stepName(res.steps[res.current]) : r.document_ref });
            dlg.close(); if (done) done();
          }
        });
      };
    }
    if (r.status === 'pending') {
      btns.push({ label: 'رفض', cls: 'btn-outline', icon: 'x', close: false, onClick: act(false) });
      btns.push({ label: 'اعتماد', cls: 'btn-primary', icon: 'check', close: false, onClick: act(true) });
    }
    BT.drawer.open({
      title: h`${api.t('approval_process', r.process)} · <span class="ltr">${r.document_ref}</span>`, subtitle: 'الخطوة ' + (r.current + 1) + ' من ' + r.steps.length, icon: 'list-checks', size: 'lg',
      body: h`${BT.kv([
        ['الحالة', A.pill('approval_status', r.status)],
        r.company_id ? ['الشركة', api.company(r.company_id)] : null,
        Number(r.amount) ? ['المبلغ', amt(r.amount)] : null,
        ['بدأ', fmt.dt(r.created_at)],
        r.status === 'pending' ? ['الخطوة الحالية منذ', fmt.dt(r.step_since) + ' (' + fmt.since(r.step_since) + ')'] : null,
        ['المستند', h`<a href="${link(r)}">${icon('arrow-left', 14)} فتح المستند</a>`]
      ].filter(Boolean))}<h4 class="mt-16">الخطوات</h4>${trail(r)}`,
      buttons: btns
    });
  }

  /* سجل اعتماد مستند، لصفحات المستندات */
  A.approvalHistory = function (el, process, documentId) {
    if (!api.can('approvals.view')) return;
    api.get('/approvals/history/' + process + '/' + documentId).then(function (rows) {
      if (!rows.length) return;
      BT.render(el, h`<h4 class="mt-16">مسار الاعتماد</h4>${rows.map(function (r) {
        return h`<div class="mt-8">${A.pill('approval_status', r.status)}${r.cancel_note ? h` <span class="muted fs-sm">${api.t('approval_cancel', r.cancel_note)}</span>` : ''}${trail(r)}</div>`;
      })}`);
    }, function () {});
  };

  /* ================= المسارات ================= */
  function workflowsPanel(el) {
    A.load(el, api.get('/approvals/workflows'), function (flows) {
      var edit = api.can('approvals.workflows');
      return h`<div class="grid-2">${flows.map(function (w) {
        return h`<div class="card" data-flow="${w.process}"><div class="card-h"><h3>${api.t('approval_process', w.process)}</h3>
          <div>${w.active ? BT.pill('مفعّل', 'g') : BT.pill('بالصلاحية', 'n')}${w.pending ? h` ${BT.pill(w.pending + ' قيد الاعتماد', 'o')}` : ''}
          ${edit ? h` <button type="button" class="btn btn-sm btn-outline" data-edit="${w.process}">${icon('pencil', 14)} تعديل</button>` : ''}</div></div>
          <div class="card-b">${w.steps.length ? h`<ol class="col gap-6" style="padding-inline-start:18px;margin:0">${w.steps.map(function (s) {
            return h`<li><b>${stepName(s)}</b> · ${approver(s)}${Number(s.min_amount) ? h` · من ${fmt.money(s.min_amount)}` : ''}${s.escalate_after_hours ? h` · تصعيد بعد ${s.escalate_after_hours} ساعة إلى ${api.name(s.escalate_role.name)}` : ''}${s.role && !s.holders ? h` ${BT.pill('لا أحد يحمل هذا الدور', 'r')}` : ''}</li>`;
          })}</ol>` : h`<p class="muted">لا خطوات: يعتمد من يملك صلاحية العملية</p>`}</div></div>`;
      })}</div>`;
    }).then(function (flows) {
      el._flows = flows;
      if (el._wired) return;
      el._wired = true;
      BT.on(el, 'click', '[data-edit]', function (e, b) {
        var w = el._flows.find(function (x) { return x.process === b.getAttribute('data-edit'); });
        editWorkflow(w, function () { workflowsPanel(el); A.refreshCounts(); });
      });
    }, function () {});
  }

  function editWorkflow(w, done) {
    api.get('/approvals/options').then(function (opt) {
      var roles = opt.roles.map(function (r) { return { v: r.code, t: api.name(r.name) }; });
      var users = opt.users.map(function (u) { return { v: u.id, t: u.name }; });
      var rows = w.steps.map(function (s) {
        return { ar: s.name.ar || '', en: s.name.en || '', kind: s.user ? 'user' : 'role', role: s.role ? s.role.code : '', user: s.user ? s.user.id : '',
          min: Number(s.min_amount) ? s.min_amount : '', hours: s.escalate_after_hours || '', esc: s.escalate_role ? s.escalate_role.code : '' };
      });
      function stepRow(s, i) {
        return h`<fieldset class="card mt-8" data-step="${i}" style="border:1px solid var(--border)"><div class="card-b"><div class="between"><b>الخطوة ${i + 1}</b>
          <span>${i ? h`<button type="button" class="btn btn-sm btn-ghost" data-up="${i}" aria-label="أعلى">${icon('arrow-up', 14)}</button>` : ''}<button type="button" class="btn btn-sm btn-ghost" data-del="${i}" aria-label="حذف الخطوة">${icon('trash-2', 14)}</button></span></div>
          <div class="form-grid">
            ${BT.f.input({ name: 'ar_' + i, label: 'الاسم بالعربية', required: true, value: s.ar })}
            ${BT.f.input({ name: 'en_' + i, label: 'الاسم بالإنجليزية', required: true, value: s.en })}
            ${BT.f.select({ name: 'kind_' + i, label: 'يعتمدها', placeholder: false, value: s.kind, options: [{ v: 'role', t: 'دور' }, { v: 'user', t: 'شخص بعينه' }] })}
            ${s.kind === 'user' ? BT.f.select({ name: 'user_' + i, label: 'الشخص', required: true, value: s.user, options: users }) : BT.f.select({ name: 'role_' + i, label: 'الدور', required: true, value: s.role, options: roles })}
            ${BT.f.money({ name: 'min_' + i, label: 'من مبلغ (اختياري)', optional: true, value: s.min })}
            ${BT.f.input({ name: 'hours_' + i, label: 'التصعيد بعد (ساعات)', optional: true, num: true, value: s.hours })}
            ${BT.f.select({ name: 'esc_' + i, label: 'إلى دور', optional: true, value: s.esc, options: roles })}
          </div></div></fieldset>`;
      }
      function body() {
        return h`<div class="form">${BT.f.switch({ name: 'active', label: 'المسار مفعّل', checked: w.active || !w.steps.length })}
          <p class="muted fs-sm">الخطوة تنطبق على المستند الذي يبلغ مبلغها. المستند يمر بالخطوات بالترتيب، ولا يعتمد شخص واحد خطوتين، والرفض دائماً بسبب. الطلبات الجارية تكمل بخطواتها.</p>
          <div data-steps>${rows.map(stepRow)}</div>
          <button type="button" class="btn btn-sm btn-outline mt-8" data-add>${icon('plus', 14)} إضافة خطوة</button></div>`;
      }
      function collect(form) {
        rows = rows.map(function (s, i) {
          var val = function (n) { var x = form.querySelector('[name=' + n + '_' + i + ']'); return x ? x.value : ''; };
          return { ar: val('ar'), en: val('en'), kind: val('kind') || s.kind, role: val('role') || s.role, user: val('user') || s.user, min: val('min'), hours: val('hours'), esc: val('esc') };
        });
      }
      var dlg = A.formModal({
        title: 'مسار ' + api.t('approval_process', w.process), subtitle: 'الخطوات بالترتيب', icon: 'list-checks', size: 'lg',
        body: body(), submitText: 'حفظ المسار', done: 'حُفظ المسار',
        onOpen: function (d) {
          var form = d.form;
          function redraw() { collect(form); BT.render(form.querySelector('[data-steps]'), h`${rows.map(stepRow)}`); }
          form.addEventListener('click', function (e) {
            var b = e.target.closest('button'); if (!b) return;
            if (b.hasAttribute('data-add')) { collect(form); rows.push({ ar: '', en: '', kind: 'role', role: '', user: '', min: '', hours: '', esc: '' }); BT.render(form.querySelector('[data-steps]'), h`${rows.map(stepRow)}`); }
            if (b.hasAttribute('data-del')) { collect(form); rows.splice(+b.getAttribute('data-del'), 1); BT.render(form.querySelector('[data-steps]'), h`${rows.map(stepRow)}`); }
            if (b.hasAttribute('data-up')) { collect(form); var i = +b.getAttribute('data-up'), x = rows[i]; rows[i] = rows[i - 1]; rows[i - 1] = x; BT.render(form.querySelector('[data-steps]'), h`${rows.map(stepRow)}`); }
          });
          form.addEventListener('change', function (e) { if (/^kind_/.test(e.target.name)) redraw(); });
        },
        submit: function (f, d) {
          collect(d.form);
          var steps = rows.map(function (s) {
            return { name: { ar: s.ar, en: s.en }, role: s.kind === 'role' ? s.role : null, user_id: s.kind === 'user' ? s.user : null,
              min_amount: s.min ? String(s.min) : '0', escalate_after_hours: s.hours ? Number(s.hours) : null, escalate_role: s.esc || null };
          });
          return api.put('/approvals/workflows/' + w.process, { version: w.version, active: !!f.active, steps: steps });
        },
        after: done
      });
      return dlg;
    }, api.fail);
  }

  /* ================= التفويض ================= */
  function delegationsPanel(el) {
    var manager = api.can('approvals.workflows');
    BT.render(el, h`<div class="card"><div data-t></div></div>`);
    var t = BT.table(el.querySelector('[data-t]'), {
      fetch: function () { return api.get('/approvals/delegations'); },
      tools: h`<button type="button" class="btn btn-sm btn-primary" data-new-delegation>${icon('plus', 14)} تفويض</button>`,
      columns: [
        { key: 'user', label: 'المفوِّض', render: function (d) { return d.user.name; } },
        { key: 'delegate', label: 'المفوَّض', render: function (d) { return d.delegate.name; } },
        { key: 'period', label: 'الفترة', render: function (d) { return h`<span class="num">${fmt.date(d.date_from)} — ${fmt.date(d.date_to)}</span>`; } },
        { key: 'reason', label: 'السبب', render: function (d) { return d.reason || '—'; } },
        { key: 'status', label: 'الحالة', render: function (d) { return A.pill('delegation_status', d.status); } }
      ],
      rowMenu: function (d) {
        if (d.status === 'cancelled' || d.status === 'ended') return [];
        if (!manager && d.user.id !== api.me.public_id) return [];
        return [{ label: 'إلغاء التفويض', icon: 'ban', danger: true, onClick: function () {
          A.confirmRun({ title: 'إلغاء التفويض', message: d.delegate.name + ' لن يعتمد نيابة عن ' + d.user.name + ' بعد الآن.', confirmText: 'إلغاء التفويض', tone: 'danger',
            run: function () { return api.post('/approvals/delegations/' + d.id + '/cancel', {}); }, done: 'أُلغي التفويض', after: t.refresh });
        } }];
      },
      empty: { icon: 'users', title: 'لا توجد تفويضات', text: 'فوّض من يعتمد بدلاً منك أثناء غيابك: يرى ما ينتظرك ويعتمده نيابة عنك' }
    });
    BT.on(el, 'click', '[data-new-delegation]', function () { newDelegation(manager, t.refresh); });
  }

  function newDelegation(manager, done) {
    api.get('/approvals/people').then(function (people) {
      var others = people.filter(function (u) { return u.id !== api.me.public_id; }).map(function (u) { return { v: u.id, t: u.name }; });
      A.formModal({
        title: 'تفويض الاعتماد', subtitle: 'يعتمد المفوَّض خطواتك نيابة عنك خلال الفترة', icon: 'users',
        body: h`<div class="form-grid">
          ${manager ? h`<div class="full">${BT.f.select({ name: 'user', label: 'المفوِّض', placeholder: 'أنا', options: people.map(function (u) { return { v: u.id, t: u.name }; }) })}</div>` : ''}
          <div class="full">${BT.f.select({ name: 'delegate', label: 'المفوَّض', required: true, options: others })}</div>
          ${BT.f.input({ name: 'from', label: 'من', type: 'date', required: true, value: BT.config.today })}
          ${BT.f.input({ name: 'to', label: 'إلى', type: 'date', required: true, value: BT.date.add(BT.config.today, 7) })}
          ${BT.f.input({ name: 'reason', label: 'السبب', optional: true, full: true })}</div>`,
        submitText: 'تفويض', done: 'سُجّل التفويض',
        submit: function (f) {
          return api.post('/approvals/delegations', { delegate_id: f.delegate, date_from: f.from, date_to: f.to, reason: f.reason || null, user_id: f.user || null });
        },
        after: done
      });
    }, api.fail);
  }
})();
