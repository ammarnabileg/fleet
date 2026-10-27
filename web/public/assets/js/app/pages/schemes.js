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
    if (s.blocks) { // built in the rules designer: its rules in their order
      return [['القواعد بالترتيب', s.blocks.map(function (b, i) { return (i + 1) + '. ' + (b.label || api.t('rule_block', b.type)); }).join(' ← ')],
        ['على الشركة', s.company_covers && s.company_covers.length ? s.company_covers.map(function (c) { return api.t('expense', c); }).join('، ') : 'لا شيء (على السائق)']];
    }
    var steps = function (kind) { return (s.steps || []).filter(function (x) { return x.kind === kind; }); };
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

  /* نظام مبني بالقواعد مكتوب بلغة صاحب الشركة: نوعه، سعره الأساسي، شروطه سطراً سطراً، ومن يدفع كل مصروف */
  A.schemeSummary = function (s) {
    var en = BT.lang === 'en', T = function (ar, e) { return en ? e : ar; };
    var kind = s.pay_kind || 'per_order', rows = [], company = [], driver = [], head = null, unit = '';
    var KWD = function (v) { return fmt.money(v); }, sep = T(' · ', ' · ');
    (s.blocks || []).forEach(function (b) {
      var x = b.params || {}, c = b.condition || [];
      var star = c.some(function (y) { return y.fact === 'month_invalid' && y.op === 'is_true'; });
      var many = c.filter(function (y) { return y.fact === 'marks' && y.op === 'gt'; })[0];
      if ((b.type === 'per_order' || b.type === 'price_change') && (star || many)) {
        rows.push(['triangle-alert', star ? T('علامة في يوم النجمة', 'A mark on a Star Day') : T('أكثر من ' + many.value + ' علامات', 'More than ' + many.value + ' marks'),
          T('كل الطلبات بـ ' + KWD(x.rate) + ' بدل الراتب والبونص', 'Every order at ' + KWD(x.rate) + ' instead of the salary and bonus')]);
        return;
      }
      switch (b.type) {
        case 'fixed_salary': head = x.mode === 'contract' ? T('حسب العقد', 'Per contract') : KWD(x.amount); unit = x.mode === 'contract' ? '' : T('د.ك / شهر', 'KWD / month'); break;
        case 'per_order': if (!head) { head = KWD(x.rate); unit = T('د.ك / طلب', 'KWD / order'); } else rows.push(['receipt', T('سعر الطلب', 'Order price'), KWD(x.rate)]); break;
        case 'batch_rate':
          var rates = (x.rates || []).map(function (r) { return Number(r.rate); });
          head = KWD(Math.min.apply(null, rates)) + ' – ' + KWD(Math.max.apply(null, rates)); unit = T('د.ك / طلب حسب الباتش', 'KWD / order by batch');
          rows.push(['list-ordered', T('الباتشات', 'Batches'), (x.rates || []).map(function (r) { return T('باتش ', 'Batch ') + r.batch + ': ' + KWD(r.rate); }).join(sep)]);
          break;
        case 'tiered_rate': rows.push(['list-ordered', T('سعر الطلب بالشرائح', 'Order price by tier'), (x.tiers || []).map(function (r) { return T('من ', 'From ') + r.from + ': ' + KWD(r.rate); }).join(sep)]); break;
        case 'target_overage': rows.push(['trending-up', T('التارجت ' + x.threshold + ' طلب', 'Target ' + x.threshold + ' orders'), T('+ ' + KWD(x.rate) + ' لكل طلب فوقه', '+ ' + KWD(x.rate) + ' per order above') + (x.below_rate ? sep + T('− ' + KWD(x.below_rate) + ' لكل طلب ناقص', '− ' + KWD(x.below_rate) + ' per order short') : '')]); break;
        case 'missing_orders': rows.push(['trending-up', T('التارجت ' + x.target + ' طلب', 'Target ' + x.target + ' orders'), T('− ' + KWD(x.rate) + ' لكل طلب ناقص', '− ' + KWD(x.rate) + ' per order short')]); break;
        case 'tier_bonus': rows.push(['hand-coins', T('البونص', 'Bonus'), (x.tiers || []).map(function (r) { return r.from + T(' طلب: ', ' orders: ') + KWD(r.amount); }).join(sep)]); break;
        case 'monthly_bonus': rows.push(['hand-coins', T('بونص شهري', 'Monthly bonus'), KWD(x.amount)]); break;
        case 'attendance_marks':
          if (x.mode === 'per_mark') rows.push(['circle-x', T('العلامات الحمراء', 'Red marks'), T('− ' + KWD(x.amount) + ' لكل علامة', '− ' + KWD(x.amount) + ' per mark')]);
          else {
            var t = x.table || [], free = t.length ? t[0].from - 1 : 0;
            rows.push(['circle-x', T('العلامات الحمراء', 'Red marks'), (free > 0 ? T('حتى ' + free + ' بدون خصم', 'Up to ' + free + ' free') + sep : '') + t.map(function (r) { return r.from + ': − ' + KWD(r.amount); }).join(sep)]);
          }
          break;
        case 'required_days': rows.push(['calendar', T('أيام صالحة', 'Valid days'), T(x.days + ' يوماً في الشهر', x.days + ' days a month')]); break;
        case 'platform_amounts': rows.push(['file-spreadsheet', T('من شيت المنصة', 'From the platform sheet'), T('البقشيش يُضاف، والتلف والتعديلات والخصم تُخصم', 'Tips added; food damage, adjustments and discount deducted')]); break;
        case 'expense': (x.responsibility === 'company' ? company : driver).push(api.t('expense', x.kind === 'phone' ? 'sim' : x.kind)); break;
      }
    });
    return { kind: kind, head: head, unit: unit, rows: rows, company: company, driver: driver };
  };
  var KIND = { fixed_salary: ['راتب ثابت', 'wallet', 'g'], per_order: ['بالطلب', 'receipt', 'b'], batch: ['باتش', 'list-ordered', 'o'] };

  function schemeCard(s, canEdit) {
    var k = KIND[s.pay_kind || 'per_order'] || KIND.per_order;
    var body;
    if (s.blocks) {
      var m = A.schemeSummary(s);
      body = h`<div class="sc-price">${m.head ? h`<b class="num">${m.head}</b><span>${m.unit}</span>` : h`<span class="muted">قواعد مخصصة</span>`}</div>
        <ul class="sc-rows">${m.rows.map(function (r) { return h`<li>${icon(r[0], 16)}<div><b>${r[1]}</b><span>${r[2]}</span></div></li>`; })}</ul>
        <div class="sc-exp">${m.company.length ? h`<div><small>على الشركة</small>${m.company.map(function (x) { return h`<span class="pill g">${x}</span>`; })}</div>` : ''}${m.driver.length ? h`<div><small>على السائق</small>${m.driver.map(function (x) { return h`<span class="pill n">${x}</span>`; })}</div>` : ''}</div>`;
    } else {
      body = h`<div class="sc-legacy">${BT.kv(A.schemeTerms(s))}</div>`;
    }
    return h`<div class="sc-card${s.is_active ? '' : ' off'}" data-scheme-box="${s.id}">
      <button type="button" class="sc-main" data-scheme="${s.id}">
        <div class="sc-top"><span class="sc-ic t-${k[2]}">${icon(k[1], 18)}</span><div class="sc-name"><b>${api.name(s.name)}</b><small><span>${k[0]}</span> · <span>${'النسخة ' + s.version_no}</span> · <span>${monthLabel(s.effective_month)}</span></small></div>
          ${s.is_active ? '' : BT.pill('موقوف', 'n')}</div>
        ${body}
        ${s.next_version ? h`<div class="sc-next" data-next-version>${icon('history', 14)} النسخة ${s.next_version.version_no} من ${monthLabel(s.next_version.effective_month)}</div>` : ''}
      </button>
      <div class="sc-foot"><span>${icon('users', 14)} <b class="num">${fmt.int(s.drivers)}</b> سائق هذا الشهر</span>${s.driver_selectable ? BT.pill('يختاره السائق', 'b') : BT.pill('من المكتب فقط', 'n')}
        ${canEdit ? h`<button type="button" class="btn btn-sm btn-ghost t-danger ms-auto" data-del-scheme="${s.id}">${icon('trash-2', 14)} حذف النظام</button>` : ''}</div>
    </div>`;
  }

  /* ================= أنظمة الدفع ================= */
  A.schemesPanel = function (el, q, only) { // only: one platform's page
    var canEdit = api.can('payroll.schemes');
    var again = function () { A.schemesPanel(el, q, only); };
    A.load(el, Promise.all([A.platforms(true), api.get('/payroll/schemes')]), function (r) {
      var plats = r[0], schemes = r[1];
      // a new scheme starts in the rules designer (from a template or a single price); a scheme built there opens
      // there, one still on its old calculator in the old form (its versions to view, its terms by version)
      A.delegate(el, 'click', '[data-new]', function (e, b) { var p = plats.find(function (x) { return String(x.id) === b.getAttribute('data-new'); }); A.newBlockScheme(p, again); });
      A.delegate(el, 'click', '[data-del-scheme]', function (e, b) { removeScheme(schemes.find(function (x) { return x.id === b.getAttribute('data-del-scheme'); }), schemes, again); });
      A.delegate(el, 'click', '[data-scheme]', function (e, b) { var s = schemes.find(function (x) { return x.id === b.getAttribute('data-scheme'); }); if (s.designed) { A.go('payroll/scheme/' + s.id); return; } var p = plats.find(function (x) { return x.id === s.platform_id; }); schemeForm(p, s, again); });
      return h`<div class="hint mb-12">كل منصة تعرض أنظمتها، وكل سائق على نظام واحد في الشهر. تغيير شروط نظام نسخة جديدة «يسري من شهر»: كل شهر يُحسب على نسخة شهره، فلا يُعاد حساب شهر صُرف بسعر لم يكن له. طريقة الحساب لا تتغير لنظام مستخدم: نظام جديد تنقل السائقين إليه من شهر (قائمة الموظفين ← حدّدهم ← «نظام الدفع»). منصة بلا أنظمة تبقى على قاعدتها (صفحة الشركة).</div>
        ${plats.filter(function (p) { return p.is_active && (!only || p.id === only); }).map(function (p) {
          var mine = schemes.filter(function (s) { return s.platform_id === p.id; });
          return h`<div class="card mb-12"><div class="card-h"><div class="card-t">${api.name(p.name)}</div><span class="muted fs-sm">${mine.length ? mine.length + ' نظام' : 'بلا أنظمة: قاعدة المنصة'}</span>${canEdit ? h`<button type="button" class="btn btn-sm btn-primary ms-auto" data-new="${p.id}">${icon('plus', 14)} نظام جديد</button>` : ''}</div>
            ${mine.length ? h`<div class="sc-groups">${['fixed_salary', 'per_order', 'batch'].map(function (kind) {
              var list = mine.filter(function (s) { return (s.pay_kind || 'per_order') === kind; });
              return list.length ? h`<div class="sc-group"><div class="sc-gt">${icon(KIND[kind][1], 15)} ${KIND[kind][0]} <span class="muted">${list.length}</span></div><div class="sc-grid">${list.map(function (s) { return schemeCard(s, canEdit); })}</div></div>` : '';
            })}</div>` : ''}</div>`;
        })}`;
    }).catch(function () {});
  };

  /* حذف نظام: عليه سواقين من هذا الشهر ← يُنقلون لنظام آخر لنفس الشركة أولاً؛ ثم يُحذف إن لم يُستخدم قط، وإلا يُوقف
     (لا يُعرض بعد ذلك، وتبقى الأشهر التي حُسبت عليه كما هي) */
  function removeScheme(s, schemes, after) {
    function done(r) {
      BT.toast(r.deleted ? 'حُذف النظام' : r.retired ? 'أُوقف النظام: استُخدم في أشهر سابقة فبقي لها' : 'لم يُحذف: ' + r.skipped.length + ' سائق لم يُنقل (شهر مقفل)');
      after();
    }
    var others = schemes.filter(function (x) { return x.platform_id === s.platform_id && x.id !== s.id && x.is_active; });
    function move() {
      if (!others.length) { BT.toast('لا يوجد نظام آخر نشط لهذه الشركة يُنقل إليه السائقون', { type: 'error' }); return; }
      A.formModal({
        title: 'نقل السائقين ثم حذف النظام', subtitle: api.name(s.name), icon: 'users', submitText: 'نقل وحذف', submitCls: 'btn-danger-solid', done: false,
        body: h`<div class="banner warn fs-sm mb-12">${icon('users', 15)}<div>على هذا النظام سائقون من هذا الشهر. اختر نظاماً آخر لنفس الشركة يُنقلون إليه من هذا الشهر.</div></div>
          ${BT.f.select({ name: 'move_to', label: 'ينقلون إلى', required: true, options: others.map(function (x) { return { v: x.id, t: api.name(x.name) }; }) })}`,
        submit: function (v) { return api.del('/payroll/schemes/' + s.id + '?move_to=' + encodeURIComponent(v.move_to)).then(done); }
      });
    }
    BT.confirm({ title: 'حذف النظام', message: 'يُحذف «' + api.name(s.name) + '». لو استُخدم في أشهر سابقة يُوقف بدل الحذف ويبقى لتلك الأشهر.', confirmText: 'حذف', tone: 'danger' }).then(function (c) {
      if (!c.ok) return;
      api.del('/payroll/schemes/' + s.id).then(done, function (err) {
        if (err && err.code === 'scheme_has_drivers') move(); else api.fail(err);
      });
    });
  }

  function stepRows(steps, calc) {
    var kinds = STEPS[calc] || [];
    return h`${steps.map(function (st, i) {
      return h`<tr><td><select class="select" data-step-k="${i}" style="min-width:210px">${kinds.map(function (k) { return h`<option value="${k}"${k === st.kind ? raw(' selected') : ''}>${api.t('scheme_step', k)}</option>`; })}</select></td>
        <td><input class="input num" data-step-t="${i}" value="${st.threshold == null ? '' : Number(st.threshold)}" inputmode="decimal"></td>
        <td><input class="input num" data-step-a="${i}" value="${st.amount == null ? '' : st.amount}" inputmode="decimal" placeholder="${st.kind === 'marks_reduce' ? 'السعر المخفض' : '0.000'}"${st.kind === 'marks_reduce' ? raw(' disabled') : ''}></td>
        <td><button type="button" class="btn btn-sm btn-ghost" data-step-x="${i}">${icon('x', 14)}</button></td></tr>`;
    })}`;
  }

  /* سجل نسخ الشروط: كل نسخة من شهر حتى النسخة التالية */
  function versionsTable(s) {
    return h`<div class="section-t mt-12">سجل النسخ</div><div class="table-wrap"><table class="t compact" data-versions><thead><tr><th>النسخة</th><th>يسري من</th><th>الشروط</th><th>ملاحظة</th></tr></thead><tbody>${s.versions.map(function (v) {
      var terms = A.schemeTerms(Object.assign({}, s, v)).map(function (x) { return x[0] + ': ' + (typeof x[1] === 'string' ? x[1] : String(x[1])); });
      return h`<tr data-version="${v.version_no}"><td class="num">${v.version_no}${v.version_no === s.version_no ? h` ${BT.pill('هذا الشهر', 'g')}` : ''}</td><td>${monthLabel(v.effective_month)}</td><td class="fs-sm">${terms.join(' · ')}</td><td class="fs-sm">${v.note || '—'}${v.created_by ? h`<span class="sub">${v.created_by} · ${fmt.dt(v.created_at)}</span>` : ''}</td></tr>`;
    })}</tbody></table></div>`;
  }

  function schemeForm(platform, s, after) {
    var editing = !!s, canEdit = api.can('payroll.schemes'), used = editing && s.used;
    s = s || { code: '', name: {}, description: null, calculator: 'per_order', per_order: '', target_orders: 420, required_valid_days: 28, missing_order_rate: null, reduced_rate: null, bonus_when_reduced: false, marks_when_reduced: false, floor_at_zero: true, company_covers: [], driver_selectable: true, is_active: true, steps: [], version: 0, versions: [] };
    // the form starts from the latest version: a change applies from its month or later
    var latest = editing && s.versions.length ? Object.assign({}, s, s.versions[0]) : s;
    var steps = latest.steps.map(function (x) { return { kind: x.kind, threshold: x.threshold, amount: x.amount }; });
    var calc = s.calculator;
    var dlg = A.formModal({
      title: editing ? api.name(s.name) : 'نظام جديد', subtitle: api.name(platform.name), icon: 'banknote', size: 'lg', done: editing ? 'حُفظ النظام' : 'أُضيف النظام',
      body: h`${editing ? h`<div class="banner note fs-sm mb-12">${icon('history', 15)}<div>تغيير الأسعار أو البنود أو القرارات نسخة جديدة «يسري من» الشهر الذي تختاره: الأشهر قبله تبقى على شروطها، وما صُرف لا يتغير.${used ? ' طريقة الحساب لا تتغير لنظام مستخدم.' : ''}${s.versions.length > 1 || s.next_version ? ' المعروض أدناه آخر نسخة (من ' + monthLabel(latest.effective_month) + ').' : ''}</div></div>` : ''}
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
          ${editing ? h`<div class="form-grid mt-12" data-effective>${BT.f.input({ name: 'effective_month', label: 'يسري من شهر', type: 'month', required: true, value: String(s.change_from).slice(0, 7), min: String(s.change_from).slice(0, 7), hint: 'أقرب شهر: ' + monthLabel(s.change_from) + ' (بعد آخر شهر صُرف على هذا النظام). من نفس شهر آخر نسخة: تُستبدل.' })}${BT.f.input({ name: 'version_note', label: 'سبب التغيير (يظهر في سجل النسخ)', optional: true, value: '' })}</div>` : ''}
          <div class="section-t mt-12">الأسعار</div>
          <div class="form-grid">
            <div data-for="per_order tiered_target">${BT.f.money({ name: 'per_order', label: 'سعر الطلب', value: latest.per_order || '' })}</div>
            <div data-for="tiered_target">${BT.f.money({ name: 'reduced_rate', label: 'السعر المخفض (علامات كثيرة أو تفويت Star Day)', value: latest.reduced_rate || '' })}</div>
            <div data-for="per_order batch tiered_target">${BT.f.input({ name: 'target_orders', label: 'التارجت الشهري (طلب)', value: latest.target_orders, num: true })}</div>
            <div data-for="per_order batch tiered_target">${BT.f.input({ name: 'required_valid_days', label: 'الأيام الصالحة المطلوبة (للعرض: أقل منها لا يُخصم شيء تلقائياً)', value: latest.required_valid_days, num: true })}</div>
            <div data-for="per_order batch tiered_target">${BT.f.money({ name: 'missing_order_rate', label: 'خصم كل طلب ناقص عن التارجت (فارغ = لا خصم)', value: latest.missing_order_rate || '', optional: true })}</div>
          </div>
          <div data-for="batch tiered_target"><div class="section-t mt-12">البنود</div>
            <div class="table-wrap"><table class="t compact"><thead><tr><th>البند</th><th class="num">من (باتش / طلبات / علامات)</th><th class="num">المبلغ</th><th></th></tr></thead><tbody data-steps>${stepRows(steps, calc)}</tbody></table></div>
            <button type="button" class="btn btn-sm btn-outline mt-8" data-step-add>${icon('plus', 14)} بند</button></div>
          <div data-for="tiered_target"><div class="section-t mt-12">القرارات (قرار العميل: لا بونص ولا خصم علامات في شهر بالسعر المخفض)</div>
            <div class="flex gap-12 wrap">${BT.f.check({ name: 'bonus_when_reduced', label: 'يُصرف البونص في شهر بالسعر المخفض', checked: latest.bonus_when_reduced })}${BT.f.check({ name: 'marks_when_reduced', label: 'يُخصم مبلغ العلامات مع السعر المخفض', checked: latest.marks_when_reduced })}</div></div>
          <div data-for="per_order batch tiered_target">${BT.f.check({ name: 'floor_at_zero', label: 'عقوبات النظام لا تتجاوز أجر النظام (لا تمس البونص والبقشيش). والصافي لا ينزل تحت الصفر أبداً: الباقي «خصومات غير محصلة» للمراجعة', checked: latest.floor_at_zero })}
            <div class="section-t mt-12">ما تتحمله الشركة (الباقي على السائق، للعلم فقط: لا يُخصم من راتبه)</div>
            <div class="flex gap-12 wrap">${COVERS.map(function (c) { return BT.f.check({ name: 'cover_' + c, label: api.t('expense', c), checked: latest.company_covers.indexOf(c) >= 0 }); })}</div></div>
          <div data-for="platform_rates" class="hint">الأساسي والأسعار والأيام غير الصالحة من قاعدة المنصة نفسها (صفحة الشركة).</div>
        </div>
        ${editing && s.versions.length ? versionsTable(s) : ''}`,
      submit: function (v, d) {
        var panel = d && d.panel ? d.panel : document;
        readSteps(panel);
        var body = { name: Object.assign({}, s.name, { ar: v.name_ar, en: v.name_en }), description: v.desc_ar ? { ar: v.desc_ar, en: (s.description || {}).en || v.desc_ar } : null, driver_selectable: !!v.driver_selectable };
        if (editing) body.is_active = !!v.is_active;
        var c = used ? s.calculator : v.calculator; // a used scheme keeps its way of computing (the select is disabled)
        Object.assign(body, {
          calculator: c,
          per_order: c === 'per_order' || c === 'tiered_target' ? fils(v.per_order) : null,
          reduced_rate: c === 'tiered_target' ? fils(v.reduced_rate) : null,
          missing_order_rate: c === 'platform_rates' ? null : fils(v.missing_order_rate),
          target_orders: Math.round(Number(v.target_orders || 0)), required_valid_days: Math.round(Number(v.required_valid_days || 0)),
          bonus_when_reduced: !!v.bonus_when_reduced, marks_when_reduced: !!v.marks_when_reduced, floor_at_zero: !!v.floor_at_zero,
          company_covers: COVERS.filter(function (x) { return v['cover_' + x]; }),
          steps: (STEPS[c] || []).length ? steps.filter(function (st) { return st.threshold !== '' && st.threshold != null; }).map(function (st) { return { kind: st.kind, threshold: Number(st.threshold), amount: st.kind === 'marks_reduce' || st.amount === '' || st.amount == null ? null : Number(st.amount).toFixed(3) }; }) : []
        });
        if (editing) return api.patch('/payroll/schemes/' + s.id, Object.assign({ version: s.version, effective_month: v.effective_month + '-01', version_note: v.version_note || null }, body));
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
    if (used) panel.querySelector('[name=calculator]').disabled = true; // another way of computing is another scheme
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
          ${BT.f.money({ name: 'personal_rate', label: 'سعر خاص للطلب (اختياري)', optional: true, hint: 'سعر متفق عليه مع السائق، يستخدمه نظام الباتش إن سمح به' })}
          <div class="banner warn fs-sm" data-rate-warning hidden>${icon('triangle-alert', 15)}<div>هذا النظام لا يستخدم السعر الخاص (لا قاعدة «سعر حسب الباتش» تسمح به): يُحفظ ولا يغيّر الحساب.</div></div>
          <div class="hint">يبدأ من أول الشهر ويحل محل ما كان من هذا الشهر فصاعداً. شهر رواتبه معتمدة لا يتغير، والسائق على منصة أخرى يُتخطى.</div></div>`,
        submit: function (v) {
          return api.post('/payroll/schemes/' + v.scheme + '/assign', { employee_ids: drivers.map(function (d) { return d.id; }), month: v.month + '-01', personal_rate: v.personal_rate === '' || v.personal_rate == null ? null : Number(v.personal_rate).toFixed(3) }).then(function (res) {
            BT.toast('نظام الدفع لـ ' + res.set + ' سائق من ' + monthLabel(res.from), { sub: res.skipped.length ? res.skipped.length + ' تُخطّي: ' + res.skipped.map(function (x) { return api.name(x.employee.name) + ' (' + api.t('errors', x.code) + ')'; }).join('، ') : '', timeout: 8000 });
            return res;
          });
        },
        after: after,
        onOpen: function (dlg) {
          // a personal rate only counts for a scheme whose batch rule allows it: said before saving
          function check() {
            var s = active.find(function (x) { return x.id === dlg.panel.querySelector('[name=scheme]').value; });
            var rate = dlg.panel.querySelector('[name=personal_rate]').value;
            var used = s && (s.blocks || []).some(function (b) { return b.type === 'batch_rate' && b.params.personal_rate !== false; });
            dlg.panel.querySelector('[data-rate-warning]').hidden = !(rate && s && !used);
          }
          BT.on(dlg.panel, 'change', '[name=scheme], [name=personal_rate]', check);
          BT.on(dlg.panel, 'input', '[name=personal_rate]', check);
        }
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
        { key: 'change', label: 'من ← إلى', render: function (r) { return h`${r.current ? api.name(r.current.name) : h`<span class="muted">لا نظام</span>`} ${icon('arrow-left', 13)} ${r.requested ? h`<b>${api.name(r.requested.name)}</b>` : h`<span class="muted">${r.status === 'approved' ? 'لم يختر بعد' : 'يختار بعد الموافقة'}</span>`}`; } },
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
      var all = res[0], want = r.requested && all.find(function (s) { return s.id === r.requested.id; }), cur = r.current && all.find(function (s) { return s.id === r.current.id; });
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
            ${r.requested ? h`<div class="card"><div class="card-h"><div class="card-t">${r.picked_at ? 'اختار' : 'يطلب'}: ${want ? api.name(want.name) : api.name(r.requested.name)}</div></div><div class="card-b">${want ? BT.kv(A.schemeTerms(want)) : ''}</div></div>` : h`<div class="card"><div class="card-h"><div class="card-t">يطلب تغيير نظامه</div></div><div class="card-b muted">لم يحدد نظاماً: بعد موافقتك تظهر له أنظمة المنصة في التطبيق ويختار منها مرة واحدة، ويبدأ النظام الجديد من الشهر الموافق عليه.</div></div>`}
          </div>
          ${can ? h`<div class="form mt-12">${BT.f.input({ name: 'month', label: 'يبدأ من (اختياري: شهر أبعد مما طلب، لا أقرب)', type: 'month', optional: true, value: '' })}<div class="hint">بلا تعديل: من ${monthLabel(r.effective_month)}، أو أول شهر بعده لم تُعتمد رواتبه.</div></div>` : ''}`
      });
    }, api.fail);
  }
})();
