/* =====================================================================
   app/pages/schemes.js — أنظمة الدفع لكل منصة (سعر ثابت، باتش، سعر أساسي
   وشرائح وعقوبات)، ومن على أي نظام من أي شهر، وطلبات السائقين لتغيير
   نظامهم من التطبيق (docs/payroll-schemes.md).
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  var CALCS = ['per_order', 'batch', 'tiered_target', 'platform_rates'];
  var STEPS = { per_order: [], platform_rates: [], batch: ['batch_rate'], tiered_target: ['tier_bonus', 'marks_deduction', 'marks_reduce'] };
  var COVERS = ['maintenance', 'housing', 'gas', 'sim'];
  var REQ_TONE = { pending: 'o', approved: 'g', rejected: 'r', cancelled: 'n' };
  function money(v) { return v == null ? '—' : fmt.money(v); }
  function minus(v) { return fmt.ltr('−' + fmt.money(v)); } // معزول حتى لا تنتقل الإشارة لطرف الرقم الآخر في النص العربي
  function fils(v) { return v === '' || v == null ? null : Number(v).toFixed(3); }
  function monthLabel(iso) { var m = String(iso).split('-'); return fmt.month(+m[0], +m[1]); }
  function thisMonth() { return BT.config.today.slice(0, 7); }

  /* ما يقرؤه المكتب والسائق: شروط النظام في سطور */
  A.schemeTerms = function (s) {
    var steps = function (kind) { return s.steps.filter(function (x) { return x.kind === kind; }); };
    var out = [];
    if (s.calculator === 'per_order') out.push(['سعر الطلب', money(s.per_order)]);
    if (s.calculator === 'batch') out.push(['سعر الطلب حسب الباتش', steps('batch_rate').map(function (x) { return 'باتش ' + Number(x.threshold) + ': ' + fmt.money(x.amount); }).join(' · ')]);
    if (s.calculator === 'tiered_target') {
      out.push(['سعر الطلب', money(s.per_order) + ' (ينخفض إلى ' + money(s.reduced_rate) + ')']);
      out.push(['بونص الشرائح', steps('tier_bonus').map(function (x) { return Number(x.threshold) + ' طلب: ' + fmt.money(x.amount); }).join(' · ') || '—']);
      var marks = steps('marks_deduction').map(function (x) { return Number(x.threshold) + ' علامات: ' + minus(x.amount); });
      var reduce = steps('marks_reduce')[0];
      if (reduce) marks.push(Number(reduce.threshold) + ' علامات فأكثر: كل الطلبات بالسعر المخفض');
      out.push(['علامات الحضور', marks.join(' · ') || '—']);
      out.push(['Star Day', 'التفويت: كل الطلبات بالسعر المخفض']);
    }
    if (s.calculator !== 'platform_rates') {
      out.push(['التارجت', fmt.int(s.target_orders) + ' طلب · ' + s.required_valid_days + ' يوم صالح' + (s.missing_order_rate ? ' · كل طلب ناقص ' + minus(s.missing_order_rate) : ' · لا خصم على النقص')]);
      out.push(['على الشركة', s.company_covers.length ? s.company_covers.map(function (c) { return api.t('expense', c); }).join('، ') : 'لا شيء (على السائق)']);
    }
    return out;
  };

  /* ================= أنظمة الدفع ================= */
  A.schemesPanel = function (el) {
    var canEdit = api.can('payroll.schemes');
    A.load(el, Promise.all([A.platforms(true), api.get('/payroll/schemes')]), function (r) {
      var plats = r[0], schemes = r[1];
      setTimeout(function () {
        BT.on(el, 'click', '[data-new]', function (e, b) { var p = plats.find(function (x) { return String(x.id) === b.getAttribute('data-new'); }); schemeForm(p, null, function () { A.schemesPanel(el); }); });
        BT.on(el, 'click', '[data-scheme]', function (e, b) { var s = schemes.find(function (x) { return x.id === b.getAttribute('data-scheme'); }); var p = plats.find(function (x) { return x.id === s.platform_id; }); schemeForm(p, s, function () { A.schemesPanel(el); }); });
      });
      return h`<div class="hint mb-12">كل منصة تعرض أنظمتها، وكل سائق على نظام واحد في الشهر. أسعار نظام عليه سائقون لا تتغير: السعر الجديد نظام جديد، وتنقل السائقين إليه من شهر (قائمة الموظفين ← حدّدهم ← «نظام الدفع»)، فلا يُعاد حساب شهر بسعر لم يكن له. منصة بلا أنظمة تبقى على قاعدتها في تبويب المنصات.</div>
        ${plats.filter(function (p) { return p.is_active; }).map(function (p) {
          var mine = schemes.filter(function (s) { return s.platform_id === p.id; });
          return h`<div class="card mb-12"><div class="card-h"><div class="card-t">${api.name(p.name)}</div><span class="muted fs-sm">${mine.length ? mine.length + ' نظام' : 'بلا أنظمة: قاعدة المنصة'}</span>${canEdit ? h`<button type="button" class="btn btn-sm btn-primary ms-auto" data-new="${p.id}">${icon('plus', 14)} نظام جديد</button>` : ''}</div>
            ${mine.length ? h`<div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;padding:12px">${mine.map(function (s) {
              return h`<button type="button" class="card" data-scheme="${s.id}" style="text-align:start;cursor:pointer"><div class="card-h"><div class="card-t">${api.name(s.name)}</div>${s.is_active ? '' : BT.pill('موقوف', 'n')}${s.driver_selectable ? BT.pill('يختاره السائق', 'b') : BT.pill('من المكتب فقط', 'n')}</div>
                <div class="card-b">${BT.kv([['الحساب', api.t('scheme_calculator', s.calculator)]].concat(A.schemeTerms(s)).concat([['السائقون هذا الشهر', fmt.int(s.drivers)]]))}</div></button>`;
            })}</div>` : ''}</div>`;
        })}`;
    }).catch(function () {});
  };

  function stepRows(steps, calc) {
    var kinds = STEPS[calc] || [];
    return h`${steps.map(function (st, i) {
      return h`<tr><td><select class="select" data-step-k="${i}" style="min-width:210px">${kinds.map(function (k) { return h`<option value="${k}"${k === st.kind ? raw(' selected') : ''}>${api.t('scheme_step', k)}</option>`; })}</select></td>
        <td><input class="input num" data-step-t="${i}" value="${st.threshold == null ? '' : Number(st.threshold)}" inputmode="decimal"></td>
        <td><input class="input num" data-step-a="${i}" value="${st.amount == null ? '' : st.amount}" inputmode="decimal" placeholder="${st.kind === 'marks_reduce' ? 'السعر المخفض' : '0.000'}"${st.kind === 'marks_reduce' ? raw(' disabled') : ''}></td>
        <td><button type="button" class="btn btn-sm btn-ghost" data-step-x="${i}">${icon('x', 14)}</button></td></tr>`;
    })}`;
  }

  function schemeForm(platform, s, after) {
    var editing = !!s, canEdit = api.can('payroll.schemes'), used = editing && s.drivers > 0;
    s = s || { code: '', name: {}, description: null, calculator: 'per_order', per_order: '', target_orders: 420, required_valid_days: 28, missing_order_rate: null, reduced_rate: null, bonus_when_reduced: false, marks_when_reduced: false, floor_at_zero: true, company_covers: [], driver_selectable: true, is_active: true, steps: [], version: 0 };
    var steps = s.steps.map(function (x) { return { kind: x.kind, threshold: x.threshold, amount: x.amount }; });
    var calc = s.calculator;
    var locked = used ? raw(' disabled') : '';
    var dlg = A.formModal({
      title: editing ? api.name(s.name) : 'نظام جديد', subtitle: api.name(platform.name), icon: 'banknote', size: 'lg', done: editing ? 'حُفظ النظام' : 'أُضيف النظام',
      body: h`${used ? h`<div class="banner note fs-sm mb-12">${icon('lock', 15)}<div>على هذا النظام سائقون هذا الشهر: أسعاره لا تتغير حتى لا يُعاد حساب شهر بسعر لم يكن له. للسعر الجديد أنشئ نظاماً جديداً وانقل السائقين إليه من شهر. الاسم والوصف والإيقاف يتغيرون.</div></div>` : ''}
        <div class="form-grid">
          ${editing ? '' : BT.f.input({ name: 'code', label: 'الرمز', required: true, pattern: '[a-z][a-z0-9_]{1,30}', msg: 'حروف إنجليزية صغيرة وأرقام وشرطة سفلية', hint: 'مثل fixed_2 أو batch' })}
          ${BT.f.input({ name: 'name_ar', label: 'الاسم بالعربية (يراه السائق)', required: true, value: s.name.ar || '' })}
          ${BT.f.input({ name: 'name_en', label: 'الاسم بالإنجليزية', required: true, value: s.name.en || '' })}
          ${BT.f.input({ name: 'desc_ar', label: 'وصف للسائق (اختياري)', optional: true, value: (s.description || {}).ar || '' })}
          ${BT.f.select({ name: 'calculator', label: 'طريقة الحساب', value: calc, placeholder: false, options: CALCS.map(function (c) { return { v: c, t: api.t('scheme_calculator', c) }; }) })}
          ${BT.f.switch({ name: 'driver_selectable', label: 'يظهر للسائق ويستطيع طلبه', checked: s.driver_selectable })}
          ${editing ? BT.f.switch({ name: 'is_active', label: 'النظام نشط', checked: s.is_active }) : ''}
        </div>
        <div data-prices>
          <div class="section-t mt-12">الأسعار</div>
          <div class="form-grid">
            <div data-for="per_order tiered_target">${BT.f.money({ name: 'per_order', label: 'سعر الطلب', value: s.per_order || '' })}</div>
            <div data-for="tiered_target">${BT.f.money({ name: 'reduced_rate', label: 'السعر المخفض (علامات كثيرة أو تفويت Star Day)', value: s.reduced_rate || '' })}</div>
            <div data-for="per_order batch tiered_target">${BT.f.input({ name: 'target_orders', label: 'التارجت الشهري (طلب)', value: s.target_orders, num: true })}</div>
            <div data-for="per_order batch tiered_target">${BT.f.input({ name: 'required_valid_days', label: 'الأيام الصالحة المطلوبة', value: s.required_valid_days, num: true })}</div>
            <div data-for="per_order batch tiered_target">${BT.f.money({ name: 'missing_order_rate', label: 'خصم كل طلب ناقص عن التارجت (فارغ = لا خصم)', value: s.missing_order_rate || '', optional: true })}</div>
          </div>
          <div data-for="batch tiered_target"><div class="section-t mt-12">البنود</div>
            <div class="table-wrap"><table class="t compact"><thead><tr><th>البند</th><th class="num">من (باتش / طلبات / علامات)</th><th class="num">المبلغ</th><th></th></tr></thead><tbody data-steps>${stepRows(steps, calc)}</tbody></table></div>
            <button type="button" class="btn btn-sm btn-outline mt-8" data-step-add${locked}>${icon('plus', 14)} بند</button></div>
          <div data-for="tiered_target"><div class="section-t mt-12">القرارات (افتراضياً كما في وثيقة الرواتب)</div>
            <div class="flex gap-12 wrap">${BT.f.check({ name: 'bonus_when_reduced', label: 'يُصرف البونص في شهر بالسعر المخفض', checked: s.bonus_when_reduced })}${BT.f.check({ name: 'marks_when_reduced', label: 'يُخصم مبلغ العلامات مع السعر المخفض', checked: s.marks_when_reduced })}</div></div>
          <div data-for="per_order batch tiered_target">${BT.f.check({ name: 'floor_at_zero', label: 'العقوبات لا تنزل بالشهر تحت الصفر (يظهر ما لم يُخصم)', checked: s.floor_at_zero })}
            <div class="section-t mt-12">ما تتحمله الشركة (الباقي على السائق)</div>
            <div class="flex gap-12 wrap">${COVERS.map(function (c) { return BT.f.check({ name: 'cover_' + c, label: api.t('expense', c), checked: s.company_covers.indexOf(c) >= 0 }); })}</div></div>
          <div data-for="platform_rates" class="hint">الأساسي والأسعار والأيام غير الصالحة من قاعدة المنصة نفسها (تبويب المنصات).</div>
        </div>`,
      submit: function (v, d) {
        var panel = d && d.panel ? d.panel : document;
        readSteps(panel);
        var body = { name: Object.assign({}, s.name, { ar: v.name_ar, en: v.name_en }), description: v.desc_ar ? { ar: v.desc_ar, en: (s.description || {}).en || v.desc_ar } : null, driver_selectable: !!v.driver_selectable };
        if (editing) body.is_active = !!v.is_active;
        if (!used) {
          Object.assign(body, {
            calculator: v.calculator,
            per_order: v.calculator === 'per_order' || v.calculator === 'tiered_target' ? fils(v.per_order) : null,
            reduced_rate: v.calculator === 'tiered_target' ? fils(v.reduced_rate) : null,
            missing_order_rate: v.calculator === 'platform_rates' ? null : fils(v.missing_order_rate),
            target_orders: Math.round(Number(v.target_orders || 0)), required_valid_days: Math.round(Number(v.required_valid_days || 0)),
            bonus_when_reduced: !!v.bonus_when_reduced, marks_when_reduced: !!v.marks_when_reduced, floor_at_zero: !!v.floor_at_zero,
            company_covers: COVERS.filter(function (c) { return v['cover_' + c]; }),
            steps: (STEPS[v.calculator] || []).length ? steps.filter(function (st) { return st.threshold !== '' && st.threshold != null; }).map(function (st) { return { kind: st.kind, threshold: Number(st.threshold), amount: st.kind === 'marks_reduce' || st.amount === '' || st.amount == null ? null : Number(st.amount).toFixed(3) }; }) : []
          });
        }
        if (editing) return api.patch('/payroll/schemes/' + s.id, Object.assign({ version: s.version }, body));
        return api.post('/payroll/schemes', Object.assign(body, { platform_id: platform.id, code: v.code }));
      },
      after: after
    });
    var panel = dlg && dlg.panel ? dlg.panel : document.querySelector('.modal:last-of-type');
    if (!panel) return;
    function readSteps(p) {
      steps.forEach(function (st, i) {
        var k = p.querySelector('[data-step-k="' + i + '"]'), t = p.querySelector('[data-step-t="' + i + '"]'), a = p.querySelector('[data-step-a="' + i + '"]');
        if (k) st.kind = k.value; if (t) st.threshold = t.value; if (a) st.amount = st.kind === 'marks_reduce' ? null : a.value;
      });
    }
    function showFor() {
      var c = panel.querySelector('[name=calculator]').value;
      BT.$$('[data-for]', panel).forEach(function (x) { x.style.display = x.getAttribute('data-for').split(' ').indexOf(c) >= 0 ? '' : 'none'; });
      if (c !== calc) { calc = c; steps = steps.filter(function (st) { return (STEPS[c] || []).indexOf(st.kind) >= 0; }); BT.render(panel.querySelector('[data-steps]'), stepRows(steps, c)); }
    }
    showFor();
    if (used) BT.$$('[data-prices] input, [data-prices] select, [name=calculator]', panel).forEach(function (x) { x.disabled = true; });
    panel.querySelector('[name=calculator]').addEventListener('change', showFor);
    BT.on(panel, 'click', '[data-step-add]', function () { readSteps(panel); steps.push({ kind: (STEPS[calc] || ['batch_rate'])[0], threshold: '', amount: '' }); BT.render(panel.querySelector('[data-steps]'), stepRows(steps, calc)); });
    BT.on(panel, 'click', '[data-step-x]', function (e, b) { readSteps(panel); steps.splice(+b.getAttribute('data-step-x'), 1); BT.render(panel.querySelector('[data-steps]'), stepRows(steps, calc)); });
    BT.on(panel, 'change', '[data-step-k]', function () { readSteps(panel); BT.render(panel.querySelector('[data-steps]'), stepRows(steps, calc)); });
    if (!canEdit) BT.$$('input, select', panel).forEach(function (x) { x.disabled = true; });
  }

  /* ================= نقل سائقين إلى نظام من شهر (من قائمة الموظفين أو ملف السائق) ================= */
  A.assignScheme = function (rows, after) {
    var drivers = rows.filter(function (r) { return r.is_driver; });
    if (!drivers.length) { BT.toast('لا يوجد سائقون في التحديد', { type: 'info' }); return; }
    Promise.all([api.get('/payroll/schemes'), A.platforms()]).then(function (r) {
      var active = r[0].filter(function (s) { return s.is_active; }), plats = r[1];
      if (!active.length) { BT.toast('لا توجد أنظمة دفع بعد: أضفها من الرواتب ← أنظمة الدفع', { type: 'info' }); return; }
      A.formModal({
        title: 'نظام الدفع', subtitle: drivers.length === 1 ? api.name(drivers[0].name) : drivers.length + ' سائق', icon: 'banknote', size: 'sm', done: false,
        body: h`<div class="form">${BT.f.select({ name: 'scheme', label: 'النظام', required: true, placeholder: 'اختر', options: active.map(function (s) { return { v: s.id, t: A.platformName(plats, s.platform_id) + ' — ' + api.name(s.name) }; }) })}
          ${BT.f.input({ name: 'month', label: 'من شهر', type: 'month', required: true, value: thisMonth() })}
          <div class="hint">يبدأ من أول الشهر ويحل محل ما كان من هذا الشهر فصاعداً. شهر رواتبه معتمدة لا يتغير، والسائق على منصة أخرى يُتخطى.</div></div>`,
        submit: function (v) {
          return api.post('/payroll/schemes/' + v.scheme + '/assign', { employee_ids: drivers.map(function (d) { return d.id; }), month: v.month + '-01' }).then(function (res) {
            BT.toast('نظام الدفع لـ ' + res.set + ' سائق من ' + monthLabel(res.from), { sub: res.skipped.length ? res.skipped.length + ' تُخطّي: ' + res.skipped.map(function (x) { return api.name(x.employee.name) + ' (' + api.t('errors', x.code) + ')'; }).join('، ') : '', timeout: 8000 });
            return res;
          });
        },
        after: after
      });
    }, api.fail);
  };

  /* في ملف الموظف: نظامه هذا الشهر وما قبله */
  A.schemeBox = function (box, e, after) {
    api.get('/employees/' + e.id + '/schemes').then(function (hist) {
      if (!document.contains(box)) return;
      var today = thisMonth() + '-01';
      var now = hist.find(function (x) { return x.valid_from <= today && (!x.valid_to || x.valid_to > today); });
      var later = hist.find(function (x) { return x.valid_from > today; });
      BT.render(box, h`<div class="section-t mt-16">نظام الدفع</div>
        ${BT.kv([
          ['هذا الشهر', now ? h`<b>${api.name(now.scheme.name)}</b> <span class="muted fs-sm">منذ ${monthLabel(now.valid_from)}</span>` : raw('<span class="muted">لا نظام</span>')],
          later ? ['من ' + monthLabel(later.valid_from), api.name(later.scheme.name)] : null
        ].filter(Boolean))}
        ${api.can('payroll.schemes') && e.is_driver && !e.is_terminal ? h`<button type="button" class="btn btn-sm btn-outline mt-8" data-scheme-set>${icon('banknote', 14)} تغيير النظام</button>` : ''}`);
      var b = box.querySelector('[data-scheme-set]');
      if (b) b.onclick = function () { A.assignScheme([e], after); };
    }, function () {});
  };

  /* ================= طلبات السائقين ================= */
  A.schemeRequestsPanel = function (el, q) {
    BT.render(el, h`<div class="card"><div class="hint mb-12">يطلب السائق من التطبيق نظاماً آخر تعرضه منصته، ويبدأ من الشهر التالي. الموافقة تنقله من أول شهر لم تُعتمد رواتبه، والرفض يصله بسببه.</div><div data-t></div></div>`);
    var t = BT.table(el.querySelector('[data-t]'), {
      empty: { icon: 'banknote', title: 'لا توجد طلبات هنا', text: 'يطلب السائق تغيير نظامه من شاشة «نظام الدفع» في التطبيق' },
      chips: { value: q.status || 'pending', all: false, options: ['pending', 'approved', 'rejected', 'cancelled'].map(function (k) { return { v: k, t: api.t('scheme_request_status', k) }; }).concat([{ v: 'all', t: 'الكل' }]) },
      fetch: function (s) { return api.get('/payroll/scheme-requests', { status: s.chip === 'all' ? null : s.chip, limit: s.limit, offset: s.offset }); },
      columns: [
        { key: 'employee', label: 'السائق', render: function (r) { return A.person(r.employee); } },
        { key: 'change', label: 'من ← إلى', render: function (r) { return h`${r.current ? api.name(r.current.name) : h`<span class="muted">لا نظام</span>`} ${icon('arrow-left', 13)} <b>${api.name(r.requested.name)}</b>`; } },
        { key: 'month', label: 'من شهر', render: function (r) { return monthLabel(r.effective_month); } },
        { key: 'note', label: 'ملاحظة', render: function (r) { return r.driver_note || r.admin_note || '—'; } },
        { key: 'status', label: 'الحالة', render: function (r) { return BT.pill(api.t('scheme_request_status', r.status), REQ_TONE[r.status]); } },
        { key: 'created_at', label: 'الطلب', render: function (r) { return h`<span class="num">${fmt.dt(r.created_at)}</span>`; } }
      ],
      rowClick: function (r) { decide(r, function () { t.refresh(); if (A.refreshCounts) A.refreshCounts(); }); }
    });
  };
  function decide(r, done) {
    var can = api.can('payroll.schemes') && r.status === 'pending';
    Promise.all([api.get('/payroll/schemes')]).then(function (res) {
      var all = res[0], want = all.find(function (s) { return s.id === r.requested.id; }), cur = r.current && all.find(function (s) { return s.id === r.current.id; });
      var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
      if (can) {
        btns.push({ label: 'رفض', cls: 'btn-outline', icon: 'ban', close: false, onClick: function (dlg) {
          A.confirmRun({ title: 'رفض الطلب', message: 'يرى السائق السبب في التطبيق ويصله على واتساب.', tone: 'danger', confirmText: 'رفض', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/payroll/scheme-requests/' + r.id + '/reject', { version: r.version, note: reason }); }, done: 'رُفض الطلب', after: function () { dlg.close(); done(); } });
        } });
        btns.push({ label: 'موافقة', cls: 'btn-primary', icon: 'check', close: false, onClick: function (dlg) {
          var m = dlg.panel.querySelector('[name=month]').value;
          api.post('/payroll/scheme-requests/' + r.id + '/approve', { version: r.version, month: m ? m + '-01' : null }).then(function (x) { BT.toast('وُوفق: من ' + monthLabel(x.effective_month)); dlg.close(); done(); }, api.fail);
        } });
      }
      BT.drawer.open({
        title: 'طلب تغيير نظام الدفع', subtitle: api.name((r.employee || {}).name || {}), icon: 'banknote', size: 'lg', buttons: btns,
        body: h`${BT.kv([['الحالة', BT.pill(api.t('scheme_request_status', r.status), REQ_TONE[r.status])], ['من شهر', monthLabel(r.effective_month)], r.driver_note ? ['ملاحظة السائق', r.driver_note] : null, r.admin_note ? ['رد المكتب', r.admin_note] : null].filter(Boolean))}
          <div class="grid mt-12" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px">
            <div class="card"><div class="card-h"><div class="card-t">الآن: ${cur ? api.name(cur.name) : 'لا نظام'}</div></div><div class="card-b">${cur ? BT.kv(A.schemeTerms(cur)) : ''}</div></div>
            <div class="card"><div class="card-h"><div class="card-t">يطلب: ${want ? api.name(want.name) : api.name(r.requested.name)}</div></div><div class="card-b">${want ? BT.kv(A.schemeTerms(want)) : ''}</div></div>
          </div>
          ${can ? h`<div class="form mt-12">${BT.f.input({ name: 'month', label: 'يبدأ من (اختياري: شهر أبعد مما طلب، لا أقرب)', type: 'month', optional: true, value: '' })}<div class="hint">بلا تعديل: من ${monthLabel(r.effective_month)}، أو أول شهر بعده لم تُعتمد رواتبه.</div></div>` : ''}`
      });
    }, api.fail);
  }
})();
