/* =====================================================================
   app/pages/designer.js — مصمم قواعد الرواتب (بلا كود): قائمة قواعد مرتبة
   لكل نسخة من نظام الدفع «يسري من شهر»، لوحة القواعد بفئاتها السبع، نموذج
   لكل قاعدة، الشروط من قائمة ثابتة، و«جرّب» على أرقام شهر؛ وحقول كل منصة
   (اليومية في التطبيق والشهرية في مراجعة الشهر)، وبيانات الشهر واستيرادها
   من Excel بفحص قبل التطبيق، ومراحل الشهر الست.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  var CAT_TONE = { pay: 'g', incentive: 'b', attendance: 'o', deduction: 'r', expense: 'n', exception: 'p', priority: 'n' };
  var NUMBER_OPS = ['gt', 'gte', 'lt', 'lte', 'eq'];
  function thisMonth() { return BT.config.today.slice(0, 7); }
  function monthLabel(iso) { var m = String(iso).split('-'); return fmt.month(+m[0], +m[1]); }
  function clone(x) { return JSON.parse(JSON.stringify(x)); }
  function slug(text, taken) {
    var base = String(text || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    if (!/^[a-z]/.test(base)) base = 'field' + (base ? '_' + base : '');
    base = base.slice(0, 30);
    var key = base, n = 2;
    while (taken.indexOf(key) >= 0) key = base + '_' + n++;
    return key;
  }

  /* «4:118, 2:39» → [{batch, orders}]; null when an entry is not batch:orders (said, never dropped silently) */
  A.parseBatches = function (text) {
    var out = [], bad = false;
    String(text || '').split(/[,،]/).map(function (x) { return x.trim(); }).filter(Boolean).forEach(function (x) {
      var m = /^(\d{1,2})\s*:\s*(\d{1,6})$/.exec(x);
      if (!m || +m[1] < 1 || +m[1] > 20) { bad = true; return; }
      out.push({ batch: +m[1], orders: +m[2] });
    });
    return bad ? null : out;
  };

  var catalog = null;
  A.rulesCatalog = function () {
    if (!catalog) catalog = api.get('/payroll/rules/catalog').then(null, function (e) { catalog = null; throw e; });
    return catalog;
  };
  function typeOf(cat, code) { return cat.types.find(function (t) { return t.type === code; }); }

  /* ---------- كيف تُقرأ القاعدة في سطر ---------- */
  function sourceLabel(key, sources) {
    var own = (sources || []).find(function (s) { return s.key === key; });
    return own ? api.name(own.label) : api.t('rule_source', key);
  }
  function paramText(p, v, ctx) {
    if (v == null || v === '') return null;
    if (p.kind === 'money') return fmt.money(v);
    if (p.kind === 'bool') return v ? 'نعم' : 'لا';
    if (p.kind === 'choice') return api.t('rule_choice', v);
    if (p.kind === 'source') return sourceLabel(v, ctx.sources);
    if (p.kind === 'rows') return v.map(function (r) { return p.rows.map(function (x) { return x.kind === 'money' ? fmt.money(r[x.name]) : r[x.name]; }).join(': '); }).join(' · ');
    return String(v);
  }
  function blockSummary(cat, b, ctx) {
    var t = typeOf(cat, b.type);
    if (!t) return '';
    return t.params.filter(function (p) { return !p.when || p.when[1].split('|').indexOf(String(b.params[p.when[0]])) >= 0; }).map(function (p) {
      var text = paramText(p, b.params[p.name], ctx);
      return text == null ? null : api.t('rule_param', p.name) + ': ' + text;
    }).filter(Boolean).join(' — ');
  }
  function clauseText(c, ctx) {
    var fact = c.fact === 'field' ? sourceLabel(c.key, ctx.sources) : api.t('rule_fact', c.fact);
    var val = c.fact === 'has_exception' ? api.t('rule_choice', c.value) : (c.op === 'is_true' || c.op === 'is_false' ? '' : c.value);
    return fact + ' ' + api.t('rule_op', c.op) + (val !== '' && val != null ? ' ' + val : '');
  }
  A.blockSummary = blockSummary;

  /* ================= نظام جديد: من قالب أو فارغ ================= */
  A.newBlockScheme = function (platform, done) {
    A.rulesCatalog().then(function (cat) {
      A.formModal({
        title: 'نظام دفع جديد', subtitle: api.name(platform.name), icon: 'banknote', size: 'lg', done: 'أُنشئ النظام',
        body: h`<div class="form-grid">
            ${BT.f.input({ name: 'code', label: 'الرمز', required: true, pattern: '[a-z][a-z0-9_]{1,30}', msg: 'حروف إنجليزية صغيرة وأرقام وشرطة سفلية', hint: 'مثل fixed_2 أو batch' })}
            ${BT.f.input({ name: 'name_ar', label: 'الاسم بالعربية (يراه السائق)', required: true })}
            ${BT.f.input({ name: 'name_en', label: 'الاسم بالإنجليزية', required: true })}
            ${BT.f.switch({ name: 'driver_selectable', label: 'يظهر للسائق ويستطيع طلبه', checked: true })}
          </div>
          <div class="section-t mt-12">ابدأ من</div>
          <div class="options" data-templates>
            <label class="option-card"><input class="radio-in" type="radio" name="template" value="" checked><span><b>فارغ</b><small>أضف القواعد بنفسك من لوحة القواعد</small></span></label>
            ${cat.templates.map(function (t) { return h`<label class="option-card"><input class="radio-in" type="radio" name="template" value="${t.code}"><span><b>${api.name(t.name)}</b> ${t.needs_confirmation ? BT.pill('قيم أولية تحتاج تأكيد', 'o') : BT.pill('كما صُرف فعلياً', 'g')}<small>${api.name(t.description)}</small></span></label>`; })}
          </div>
          <div class="hint">القالب يُنسخ في النظام الجديد وكل قيمه قابلة للتعديل: لا سعر فيه قاعدة على الجميع.</div>`,
        submit: function (v) {
          return api.post('/payroll/schemes/from-template', { platform_id: platform.id, template: v.template || null, code: v.code, name: { ar: v.name_ar, en: v.name_en }, driver_selectable: !!v.driver_selectable });
        },
        after: function (s) { if (done) done(s); else A.go('payroll/scheme/' + s.id); }
      });
    }, api.fail);
  };

  /* ================= مصمم القواعد ================= */
  BT.pages['payroll/scheme/:id'] = function (p) {
    A.setTitle('مصمم القواعد', [['الرواتب', 'payroll?tab=schemes'], ['مصمم القواعد']]);
    var v = A.view();
    A.load(v, Promise.all([api.get('/payroll/schemes/' + p.id + '/designer'), A.rulesCatalog()]), function (r) { return h`<div data-designer></div>`; })
      .then(function (r) { if (r) designer(v.querySelector('[data-designer]'), r[0], r[1]); }).catch(function () {});
  };

  function designer(el, d, cat) {
    _cat = cat;
    var canEdit = api.can('payroll.schemes');
    var ctx = { sources: d.sources, tasks: d.tasks };
    var versions = d.versions; // newest first
    var shown = versions[0];
    var draft = null; // the blocks being edited (a copy of the latest version)
    var floor = true;
    function startDraft(from) {
      draft = clone(from && from.blocks ? from.blocks : []);
      floor = from ? from.floor_at_zero !== false : true;
    }
    startDraft(versions.find(function (x) { return x.blocks; }));

    function versionChip(x) {
      return h`<button type="button" class="chip${x === shown ? ' active' : ''}" data-ver="${x.version_no}">ن${x.version_no} · يسري من ${monthLabel(x.effective_month)}${x.blocks ? '' : ' · نظام قديم'}</button>`;
    }
    function blockRow(b, i, editable) {
      var t = typeOf(cat, b.type) || { category: 'priority' };
      return h`<div class="card mb-8" data-block="${i}" style="border-inline-start:4px solid var(--${{ g: 'success', b: 'info', o: 'warning', r: 'danger', p: 'primary', n: 'border' }[CAT_TONE[t.category]] || 'border'})">
        <div class="card-h"><span class="num muted">${i + 1}</span><div class="card-t">${b.label || api.t('rule_block', b.type)}</div>${BT.pill(api.t('rule_category', t.category), CAT_TONE[t.category])}
          ${b.group ? BT.pill('أولوية: ' + b.group, 'p') : ''}${b.on_exception && b.on_exception !== 'none' ? BT.pill(api.t('rule_choice', b.on_exception), 'b') : ''}
          ${editable ? h`<span class="ms-auto nowrap"><button type="button" class="btn btn-sm btn-ghost" data-up="${i}" title="لأعلى"${i === 0 ? raw(' disabled') : ''}>${icon('arrow-up', 14)}</button><button type="button" class="btn btn-sm btn-ghost" data-down="${i}" title="لأسفل"${i === draft.length - 1 ? raw(' disabled') : ''}>${icon('arrow-down', 14)}</button><button type="button" class="btn btn-sm btn-ghost" data-edit-block="${i}">${icon('pencil', 14)} تعديل</button><button type="button" class="btn btn-sm btn-ghost" data-del="${i}" title="حذف">${icon('x', 14)}</button></span>` : ''}</div>
        <div class="card-b fs-sm"><div>${blockSummary(cat, b, ctx) || h`<span class="muted">${api.t('rule_block_help', b.type)}</span>`}</div>
          ${b.condition && b.condition.length ? h`<div class="mt-4"><span class="muted">${icon('filter', 13)} عندما: </span>${b.condition.map(function (c, j) { return h`${j ? ' و ' : ''}<b>${clauseText(c, ctx)}</b>`; })}</div>` : ''}</div></div>`;
    }
    function render() {
      var editable = canEdit && shown === versions[0] && shown.blocks;
      var list = editable ? draft : (shown.blocks || null);
      BT.render(el, h`${A.head(api.name(d.scheme.name), h`${api.name(d.platform.name)} · ${BT.pill(d.scheme.is_active ? 'نشط' : 'موقوف', d.scheme.is_active ? 'g' : 'n')} ${d.used ? BT.pill('عليه سائقون', 'b') : ''}`, h`${A.btn('رجوع للأنظمة', { icon: 'arrow-right', cls: 'btn-ghost', id: 'ds-back' })}`)}
        <div class="banner note fs-sm mb-12">${icon('info', 15)}<div>القواعد تُنفَّذ بالترتيب من الأعلى للأسفل، كل قاعدة مرة واحدة: الترتيب هو الأولوية المعتمدة (مثلاً خصم نقص التارجت قبل المكافأة أو بعدها، وتغيير السعر يحل محل السعر الأساسي أو سطر خصم منفصل). كل تعديل نسخة جديدة «يسري من شهر»، والأشهر المعتمدة لا تتغير.</div></div>
        <div class="flex gap-8 wrap mb-12 items-center"><span class="muted fs-sm">النسخ:</span>${versions.map(versionChip)}</div>
        <div class="grid" style="grid-template-columns:minmax(0,3fr) minmax(280px,2fr);gap:16px;align-items:start">
          <div>
            ${list ? h`<div data-blocks>${list.map(function (b, i) { return blockRow(b, i, editable); })}</div>
              <div class="card mb-8" style="border-inline-start:4px solid var(--border)"><div class="card-h"><span class="num muted">${(list.length || 0) + 1}</span><div class="card-t">الصافي لا يقل عن صفر</div>${BT.pill('دائماً الأخيرة', 'n')}</div>
                <div class="card-b fs-sm">${editable ? BT.f.check({ name: 'floor', label: 'العقوبات لا تنزل بالشهر تحت الصفر، وما لم يُخصم يظهر «خصومات غير محصلة» للمراجعة (القرار D)', checked: floor }) : (shown.floor_at_zero !== false ? 'العقوبات لا تنزل بالشهر تحت الصفر (القرار D)' : 'بلا حد أدنى')}</div></div>
              ${editable ? h`<div class="flex gap-8 wrap mt-12">${A.btn('قاعدة', { icon: 'plus', cls: 'btn-outline', id: 'ds-add' })}<span class="spacer"></span>${A.btn('حفظ كنسخة جديدة', { icon: 'check', cls: 'btn-primary', id: 'ds-save' })}</div>` : ''}`
              : h`<div class="card"><div class="card-h"><div class="card-t">نسخة بنظام الحساب القديم (للعرض فقط)</div></div><div class="card-b">${BT.kv(A.schemeTerms ? A.schemeTerms(Object.assign({ calculator: d.scheme.calculator }, shown.terms || {})) : [])}</div></div>`}
            ${shown.note ? h`<div class="muted fs-sm mt-8">ملاحظة النسخة: ${shown.note}</div>` : ''}
          </div>
          <div><div class="card"><div class="card-h"><div class="card-t">${icon('play', 16)} جرّب</div><span class="muted fs-sm">أرقام شهر تجريبية ← كل سطر ومعادلته والصافي</span></div><div class="card-b" data-try></div></div></div>
        </div>`);
      tryPanel(el.querySelector('[data-try]'), function () { return editable ? draft : (shown.blocks || []); }, function () { return editable ? floor : shown.floor_at_zero !== false; }, d, ctx);
    }
    render();

    A.delegate(el, 'click', '[data-ver]', function (e, b) { shown = versions.find(function (x) { return String(x.version_no) === b.getAttribute('data-ver'); }); render(); });
    A.delegate(el, 'click', '#ds-back', function () { A.go('payroll?tab=schemes'); });
    A.delegate(el, 'change', '[name=floor]', function (e, x) { floor = x.checked; });
    A.delegate(el, 'click', '[data-up]', function (e, b) { var i = +b.getAttribute('data-up'); if (i > 0) { draft.splice(i - 1, 0, draft.splice(i, 1)[0]); render(); } });
    A.delegate(el, 'click', '[data-down]', function (e, b) { var i = +b.getAttribute('data-down'); if (i < draft.length - 1) { draft.splice(i + 1, 0, draft.splice(i, 1)[0]); render(); } });
    A.delegate(el, 'click', '[data-del]', function (e, b) { draft.splice(+b.getAttribute('data-del'), 1); render(); });
    A.delegate(el, 'click', '[data-edit-block]', function (e, b) { var i = +b.getAttribute('data-edit-block'); blockForm(cat, draft[i], ctx, function (nb) { draft[i] = nb; render(); }); });
    A.delegate(el, 'click', '#ds-add', function () { palette(cat, function (type) { blockForm(cat, { type: type, params: {}, condition: [], on_exception: 'none', group: null, label: null }, ctx, function (nb) { draft.push(nb); render(); }); }); });
    A.delegate(el, 'click', '#ds-save', function () {
      var latest = versions[0];
      A.formModal({
        title: 'حفظ القواعد كنسخة جديدة', icon: 'check', size: 'sm', done: 'حُفظت النسخة',
        body: h`<div class="form">${d.used ? BT.f.input({ name: 'month', label: 'يسري من شهر', type: 'month', required: true, value: String(d.change_from).slice(0, 7), min: String(d.change_from).slice(0, 7), hint: 'لا يسبق ' + monthLabel(d.change_from) + ': شهر دُفعت رواتبه على هذا النظام لا يتغير' }) : h`<div class="hint mb-8">لم يُدفع لأحد على هذا النظام بعد: تُستبدل نسخته.</div>`}
          ${BT.f.input({ name: 'note', label: 'ملاحظة النسخة', optional: true })}</div>`,
        submit: function (x) {
          return api.post('/payroll/schemes/' + d.scheme.id + '/blocks', { version: d.scheme.version, blocks: draft, floor_at_zero: floor, effective_month: x.month ? x.month + '-01' : null, note: x.note || null });
        },
        after: function (nd) { d = nd; versions = d.versions; shown = versions[0]; startDraft(shown); render(); }
      });
      return latest;
    });
  }

  /* ---------- لوحة القواعد: الفئات السبع ---------- */
  function palette(cat, pick) {
    var dlg = BT.modal.open({
      title: 'قاعدة جديدة', subtitle: 'اختر نوع القاعدة', icon: 'plus', size: 'lg',
      body: h`${cat.categories.map(function (c) {
        var types = cat.types.filter(function (t) { return t.category === c; });
        return h`<div class="section-t mt-12">${api.t('rule_category', c)}</div>
          ${c === 'priority' ? h`<div class="hint">الأولوية هي ترتيب القائمة (حرّك القواعد لأعلى ولأسفل). وعندما تتحقق شروط أكثر من قاعدة، ضعها في «مجموعة أولوية» واحدة داخل نموذج كل قاعدة: تُطبق أول قاعدة يتحقق شرطها فقط.</div>` : ''}
          ${c === 'exception' ? h`<div class="hint mb-8">الاستثناءات (عذر مقبول، خطأ في بيانات الشركة، يوم معتمد كاستثناء) تُدخل لكل سائق في بيانات الشهر بملاحظة ومن اعتمدها، وكل قاعدة تحدد ماذا تفعل بها في «عند الاستثناء».</div>` : ''}
          <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px">${types.map(function (t) {
            return h`<button type="button" class="card" data-pick="${t.type}" style="text-align:start;cursor:pointer"><div class="card-b"><b>${api.t('rule_block', t.type)}</b><div class="muted fs-sm mt-4">${api.t('rule_block_help', t.type)}</div></div></button>`;
          })}</div>`;
      })}`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }]
    });
    BT.on(dlg.panel, 'click', '[data-pick]', function (e, b) { var t = b.getAttribute('data-pick'); dlg.close(); pick(t); });
  }

  /* ---------- نموذج القاعدة، من وصف نوعها ---------- */
  function sourceOptions(ctx) {
    return cat0().sources.map(function (s) { return { v: s, t: api.t('rule_source', s) }; }).concat((ctx.sources || []).map(function (s) { return { v: s.key, t: api.name(s.label) }; }));
  }
  var _cat = null;
  function cat0() { return _cat; }
  function rowsEditor(p, rows, ctx) {
    return h`<div class="table-wrap"><table class="t compact" data-rows="${p.name}"><thead><tr>${p.rows.map(function (x) { return h`<th>${api.t('rule_param', x.name)}</th>`; })}<th></th></tr></thead><tbody>
      ${rows.map(function (r, i) { return h`<tr>${p.rows.map(function (x) {
        if (x.kind === 'key' && ctx.tasks && ctx.tasks.length) return h`<td><select class="select" data-cell="${p.name}:${i}:${x.name}">${ctx.tasks.map(function (o) { return h`<option value="${o.value}"${o.value === r[x.name] ? raw(' selected') : ''}>${api.name(o.label)}</option>`; })}</select></td>`;
        return h`<td><input class="input num" data-cell="${p.name}:${i}:${x.name}" value="${r[x.name] == null ? '' : r[x.name]}" inputmode="decimal"${x.kind === 'key' ? raw(' dir="ltr"') : ''}></td>`;
      })}<td><button type="button" class="btn btn-sm btn-ghost" data-row-x="${p.name}:${i}">${icon('x', 14)}</button></td></tr>`; })}
      </tbody></table></div><button type="button" class="btn btn-sm btn-outline mt-4" data-row-add="${p.name}">${icon('plus', 14)} صف</button>`;
  }
  function conditionEditor(cond, ctx) {
    var facts = cat0().facts;
    return h`<div data-cond>${cond.map(function (c, i) {
      var f = facts.find(function (x) { return x.fact === c.fact; }) || facts[0];
      var value;
      if (c.fact === 'has_exception') value = h`<select class="select" data-c-value="${i}">${cat0().exception_kinds.concat(['any']).map(function (k) { return h`<option value="${k}"${k === c.value ? raw(' selected') : ''}>${api.t('rule_choice', k)}</option>`; })}</select>`;
      else if (c.op === 'is_true' || c.op === 'is_false') value = '';
      else value = h`<input class="input num" style="max-width:110px" data-c-value="${i}" value="${c.value == null ? '' : c.value}" inputmode="numeric">`;
      return h`<div class="flex gap-8 items-center mb-8 wrap" data-clause="${i}">${i ? h`<span class="muted">و</span>` : ''}
        <select class="select" data-c-fact="${i}">${facts.map(function (x) { return h`<option value="${x.fact}"${x.fact === c.fact ? raw(' selected') : ''}>${api.t('rule_fact', x.fact)}</option>`; })}</select>
        ${c.fact === 'field' ? h`<select class="select" data-c-key="${i}">${(ctx.sources || []).map(function (s) { return h`<option value="${s.key}"${s.key === c.key ? raw(' selected') : ''}>${api.name(s.label)}</option>`; })}</select>` : ''}
        <select class="select" data-c-op="${i}">${f.ops.map(function (o) { return h`<option value="${o}"${o === c.op ? raw(' selected') : ''}>${api.t('rule_op', o)}</option>`; })}</select>
        ${value}<button type="button" class="btn btn-sm btn-ghost" data-c-x="${i}">${icon('x', 14)}</button></div>`;
    })}</div><button type="button" class="btn btn-sm btn-outline" data-c-add>${icon('plus', 14)} شرط</button>`;
  }
  function blockForm(cat, block, ctx, save) {
    _cat = cat;
    var t = typeOf(cat, block.type);
    var b = clone(block);
    b.params = b.params || {};
    b.condition = b.condition || [];
    t.params.forEach(function (p) { if (b.params[p.name] == null && p.default != null) b.params[p.name] = p.default; if (p.kind === 'rows' && !b.params[p.name]) b.params[p.name] = []; });
    function wanted(p) { return !p.when || p.when[1].split('|').indexOf(String(b.params[p.when[0]])) >= 0; }
    function field(p) {
      var v = b.params[p.name];
      var label = api.t('rule_param', p.name);
      var o = { name: 'p_' + p.name, label: label, value: v == null ? '' : v, required: p.required && p.kind !== 'bool' };
      if (p.kind === 'money') return BT.f.money(o);
      if (p.kind === 'int') return BT.f.input(Object.assign(o, { num: true }));
      if (p.kind === 'bool') return h`<div class="field">${BT.f.check({ name: 'p_' + p.name, label: label, checked: !!v })}</div>`;
      if (p.kind === 'choice') return BT.f.select(Object.assign(o, { placeholder: false, options: p.options.map(function (x) { return { v: x, t: api.t('rule_choice', x) }; }) }));
      if (p.kind === 'source') return BT.f.select(Object.assign(o, { placeholder: false, options: sourceOptions(ctx) }));
      if (p.kind === 'key') return BT.f.input(o);
      if (p.kind === 'rows') return h`<div class="field full"><label>${label}</label>${rowsEditor(p, v || [], ctx)}</div>`;
      return '';
    }
    function body() {
      return h`<div class="hint mb-12">${api.t('rule_block_help', t.type)}</div>
        <div class="form-grid" data-params>${t.params.filter(wanted).map(field)}</div>
        <div class="section-t mt-12">${icon('filter', 14)} الشرط (اختياري${t.needs_condition ? '؛ مطلوب لهذه القاعدة' : ''}): تُطبق القاعدة فقط عندما تتحقق كل الشروط</div>
        ${conditionEditor(b.condition, ctx)}
        <div class="form-grid mt-12">
          ${t.on_exception.length > 1 ? BT.f.select({ name: 'on_exception', label: api.t('rule_param', 'on_exception'), value: b.on_exception || 'none', placeholder: false, options: t.on_exception.map(function (x) { return { v: x, t: api.t('rule_choice', x) }; }) }) : ''}
          ${BT.f.input({ name: 'group', label: api.t('rule_param', 'group'), optional: true, value: b.group || '', pattern: '[a-z][a-z0-9_]{0,39}', msg: 'حروف إنجليزية صغيرة', hint: 'قواعد بنفس المجموعة: تُطبق أول واحدة يتحقق شرطها' })}
          ${BT.f.input({ name: 'label', label: api.t('rule_param', 'label'), optional: true, value: b.label || '', maxlength: 80 })}
        </div>`;
    }
    function read(panel) {
      t.params.forEach(function (p) {
        var el = panel.querySelector('[name="p_' + p.name + '"]');
        if (p.kind === 'rows') {
          var rows = b.params[p.name] || [];
          rows.forEach(function (r, i) { p.rows.forEach(function (x) { var c = panel.querySelector('[data-cell="' + p.name + ':' + i + ':' + x.name + '"]'); if (c) r[x.name] = c.value === '' ? null : (x.kind === 'int' ? Number(c.value) : c.value); }); });
          return;
        }
        if (!el) return;
        if (p.kind === 'bool') b.params[p.name] = el.checked;
        else if (el.value === '') delete b.params[p.name];
        else b.params[p.name] = p.kind === 'int' ? Number(el.value) : el.value;
      });
      b.condition.forEach(function (c, i) {
        var f = panel.querySelector('[data-c-fact="' + i + '"]'), o = panel.querySelector('[data-c-op="' + i + '"]'), v = panel.querySelector('[data-c-value="' + i + '"]'), k = panel.querySelector('[data-c-key="' + i + '"]');
        if (f) c.fact = f.value; if (o) c.op = o.value; if (k) c.key = k.value;
        if (v) c.value = c.fact === 'has_exception' ? v.value : (v.value === '' ? null : Number(v.value)); else delete c.value;
        if (c.fact !== 'field') delete c.key;
      });
      var oe = panel.querySelector('[name=on_exception]'), g = panel.querySelector('[name=group]'), l = panel.querySelector('[name=label]');
      b.on_exception = oe ? oe.value : 'none';
      b.group = g && g.value ? g.value : null;
      b.label = l && l.value ? l.value : null;
    }
    var dlg = A.formModal({
      title: api.t('rule_block', t.type), subtitle: api.t('rule_category', t.category), icon: 'list-checks', size: 'lg', done: false, submitText: 'تم',
      body: body(),
      submit: function (v, d) { read(d.panel); if (t.needs_condition && !b.condition.length) { BT.toast('هذه القاعدة تحتاج شرطاً', { type: 'error' }); return false; } save(b); return true; }
    });
    function redraw() { read(dlg.panel); BT.render(dlg.body, body()); }
    BT.on(dlg.panel, 'change', '[name^=p_], [data-c-fact], [data-c-op]', function (e, x) {
      if (x.hasAttribute('data-c-fact')) { read(dlg.panel); var c = b.condition[+x.getAttribute('data-c-fact')]; var f = cat.facts.find(function (y) { return y.fact === c.fact; }); c.op = f.ops[0]; c.value = c.fact === 'has_exception' ? 'any' : null; if (c.fact === 'field') c.key = (ctx.sources[0] || {}).key; BT.render(dlg.body, body()); return; }
      if (x.tagName === 'SELECT') redraw();
    });
    BT.on(dlg.panel, 'click', '[data-row-add]', function (e, x) { read(dlg.panel); var p = t.params.find(function (y) { return y.name === x.getAttribute('data-row-add'); }); var r = {}; p.rows.forEach(function (y) { r[y.name] = null; }); b.params[p.name].push(r); BT.render(dlg.body, body()); });
    BT.on(dlg.panel, 'click', '[data-row-x]', function (e, x) { read(dlg.panel); var a = x.getAttribute('data-row-x').split(':'); b.params[a[0]].splice(+a[1], 1); BT.render(dlg.body, body()); });
    BT.on(dlg.panel, 'click', '[data-c-add]', function () { read(dlg.panel); b.condition.push({ fact: 'orders', op: 'gte', value: null }); BT.render(dlg.body, body()); });
    BT.on(dlg.panel, 'click', '[data-c-x]', function (e, x) { read(dlg.panel); b.condition.splice(+x.getAttribute('data-c-x'), 1); BT.render(dlg.body, body()); });
  }

  /* ---------- «جرّب» ---------- */
  var SAMPLE = [['orders', 'الطلبات'], ['valid_days', 'الأيام الصالحة'], ['working_days', 'أيام الدوام'], ['attendance_marks', 'علامات الحضور'], ['late_count', 'مرات التأخير'], ['absent_days', 'أيام الغياب'], ['basic_salary', 'أساسي العقد'], ['personal_rate', 'سعر خاص للسائق']];
  function tryPanel(box, blocks, floor, d, ctx) {
    var cat = _cat;
    BT.render(box, h`<form data-sample class="form" novalidate><div class="form-grid">
        ${SAMPLE.map(function (s) { return BT.f.input({ name: 's_' + s[0], label: s[1], num: true, optional: true }); })}
        ${BT.f.select({ name: 's_star', label: 'فوّت Star Day', placeholder: 'لم يُحدد', options: [{ v: 'false', t: 'لا' }, { v: 'true', t: 'نعم' }] })}
        ${BT.f.input({ name: 's_batches', label: 'الطلبات حسب الباتش', optional: true, placeholder: '4:118, 2:39', hint: 'باتش:طلبات، مفصولة بفواصل' })}
        ${(ctx.sources || []).map(function (s) { return BT.f.input({ name: 'f_' + s.key, label: api.name(s.label), num: s.type !== 'bool', optional: true, hint: s.type === 'bool' ? 'عدد الأيام بنعم' : '' }); })}
        ${(ctx.tasks || []).map(function (o) { return BT.f.input({ name: 't_' + o.value, label: api.name(o.label), num: true, optional: true }); })}
        ${BT.f.select({ name: 's_exception', label: 'استثناء معتمد يعذر عن', placeholder: 'لا يوجد', options: ['star_day', 'marks', 'lateness', 'absence', 'valid_days'].map(function (k) { return { v: k, t: api.t('rule_excuse', k) }; }) })}
        ${BT.f.input({ name: 's_exception_days', label: 'أيام الاستثناء (فارغ = كله)', num: true, optional: true })}
      </div><button type="submit" class="btn btn-primary mt-8" data-try-run>${icon('play', 14)} جرّب</button></form><div data-result class="mt-12"></div>`);
    var form = box.querySelector('[data-sample]');
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var v = BT.form.values(form), month = {};
      SAMPLE.forEach(function (s) { if (v['s_' + s[0]] !== '' && v['s_' + s[0]] != null) month[s[0]] = v['s_' + s[0]]; });
      if (v.s_star) month.star_day_failed = v.s_star === 'true';
      var parsed = A.parseBatches(v.s_batches);
      if (parsed === null) { BT.toast('الطلبات حسب الباتش: اكتبها باتش:طلبات مفصولة بفواصل، مثل 4:118, 2:39', { type: 'error' }); return; }
      month.batches = parsed;
      month.fields = {};
      (ctx.sources || []).forEach(function (s) { if (v['f_' + s.key] !== '' && v['f_' + s.key] != null) month.fields[s.key] = v['f_' + s.key]; });
      month.tasks = {};
      (ctx.tasks || []).forEach(function (o) { if (v['t_' + o.value] !== '' && v['t_' + o.value] != null) month.tasks[o.value] = v['t_' + o.value]; });
      if (v.s_exception) month.exceptions = [{ kind: v.s_exception === 'valid_days' ? 'exception_day' : 'accepted_excuse', days: v.s_exception_days === '' || v.s_exception_days == null ? (v.s_exception === 'valid_days' ? 1 : 0) : Math.round(Number(v.s_exception_days)), excuses: [v.s_exception] }];
      api.post('/payroll/rules/preview', { blocks: blocks(), floor_at_zero: floor(), platform_id: d.platform.id, month: month }).then(function (r) {
        BT.render(box.querySelector('[data-result]'), h`${r.needs.length ? h`<div class="banner warn fs-sm mb-8">${icon('triangle-alert', 15)}<div>أرقام ناقصة يحتاجها النظام (في الشهر الفعلي تُوقف الاعتماد): ${r.needs.map(function (n) { return api.t('rule_source', n, null, sourceLabel(n, ctx.sources)); }).join('، ')}</div></div>` : ''}
          <div class="table-wrap"><table class="t compact" data-try-lines><tbody>${r.lines.map(function (l) {
            var n = Number(l.amount), info = l.code === 'uncovered_penalty';
            return h`<tr><td>${api.t('payroll_column', l.code)}${l.block ? h` <span class="muted fs-sm">(#${l.block})</span>` : ''}<span class="sub ltr">${l.formula}</span></td><td class="num ${info ? 'muted' : n < 0 ? 't-danger' : ''}">${info ? BT.amt(n) : BT.amt(n, { signed: true })}</td></tr>`;
          })}<tr><td><b>الصافي</b>${Number(r.uncovered) ? h`<span class="sub">لم يُخصم: ${fmt.money(r.uncovered)} (للمراجعة)</span>` : ''}</td><td class="num" data-try-net><b>${fmt.money(r.net)}</b></td></tr></tbody></table></div>
          ${r.trace.filter(function (x) { return x.skipped || x.info; }).length ? h`<div class="section-t mt-8">ما لم يُطبق وما حدث للعلم</div><ul class="fs-sm muted">${r.trace.filter(function (x) { return x.skipped || x.info; }).map(function (x) { return h`<li>${x.block ? '#' + x.block + ' ' + api.t('rule_block', x.type) + ': ' : ''}${api.t('rule_trace', x.skipped || x.info)}</li>`; })}</ul>` : ''}`);
      }, api.fail);
    });
    return cat;
  }

  /* ================= حقول المنصة ================= */
  var DAILY_BUILTINS = ['orders', 'cash', 'valid_day'];
  var MONTHLY_BUILTINS = ['batch_orders', 'attendance_marks', 'star_day_failed', 'late_count', 'absent_days', 'task_counts'];
  var CUSTOM_TYPES = [['int', 'عدد صحيح'], ['money', 'مبلغ (3 أرقام عشرية)'], ['bool', 'نعم / لا'], ['choice', 'اختيار من قائمة']];
  var BUILTIN_LABEL = { orders: 'عدد الطلبات', cash: 'الكاش', valid_day: 'اليوم صالح', batch_orders: 'الطلبات حسب الباتش (صفوف)', attendance_marks: 'علامات الحضور', star_day_failed: 'فوّت Star Day', late_count: 'مرات التأخير', absent_days: 'أيام الغياب', task_counts: 'المهام حسب النوع' };
  var BUILTIN_TYPE = { orders: 'int', cash: 'money', valid_day: 'bool', batch_orders: 'batch_orders', attendance_marks: 'int', star_day_failed: 'bool', late_count: 'int', absent_days: 'int', task_counts: 'task_counts' };
  A.platformFields = function (platform, done) {
    api.get('/payroll/platforms/' + platform.id + '/fields').then(function (f) {
      var lists = { daily: clone(f.daily), monthly: clone(f.monthly) };
      function optsText(x) { return (x.options || []).map(function (o) { return o.value + '=' + api.name(o.label); }).join('، '); }
      function rowHtml(scope, x, i) {
        var builtin = !!x.builtin;
        return h`<tr data-frow="${scope}:${i}"><td class="nowrap"><button type="button" class="btn btn-sm btn-ghost" data-fup="${scope}:${i}"${i === 0 ? raw(' disabled') : ''}>${icon('arrow-up', 13)}</button><button type="button" class="btn btn-sm btn-ghost" data-fdown="${scope}:${i}"${i === lists[scope].length - 1 ? raw(' disabled') : ''}>${icon('arrow-down', 13)}</button></td>
          <td><input class="input" data-fl-ar="${scope}:${i}" value="${(x.label || {}).ar || ''}" placeholder="الاسم بالعربية" maxlength="80"><input class="input mt-4" data-fl-en="${scope}:${i}" value="${(x.label || {}).en || ''}" placeholder="English label" maxlength="80"></td>
          <td><span class="ltr muted fs-sm">${x.key}</span>${builtin ? h`<div>${BT.pill('أساسي', 'b')}</div>` : ''}</td>
          <td>${builtin ? api.t('rule_choice', x.type, null, BUILTIN_LABEL[x.builtin]) : h`<select class="select" data-ftype="${scope}:${i}">${CUSTOM_TYPES.map(function (t) { return h`<option value="${t[0]}"${t[0] === x.type ? raw(' selected') : ''}>${t[1]}</option>`; })}</select>`}
            ${x.type === 'choice' || x.type === 'task_counts' ? h`<input class="input mt-4" data-fopts="${scope}:${i}" value="${optsText(x)}" placeholder="القيمة=الاسم، مثل north=الشمال، south=الجنوب" dir="auto">` : ''}</td>
          <td>${BT.f.check({ name: 'freq_' + scope + '_' + i, label: 'مطلوب', checked: x.required })}<input class="input mt-4" data-fhelp="${scope}:${i}" value="${x.help ? x.help.ar || '' : ''}" placeholder="نص مساعد (اختياري)" maxlength="200"></td>
          <td><button type="button" class="btn btn-sm btn-ghost" data-fx="${scope}:${i}">${icon('x', 14)}</button></td></tr>`;
      }
      function table(scope) {
        return h`<div class="table-wrap"><table class="t compact" data-ftable="${scope}"><thead><tr><th></th><th>الاسم</th><th>المفتاح</th><th>النوع</th><th>مطلوب / مساعدة</th><th></th></tr></thead><tbody>${lists[scope].map(function (x, i) { return rowHtml(scope, x, i); })}</tbody></table></div>`;
      }
      function addMenu(scope) {
        var have = lists[scope].map(function (x) { return x.builtin; });
        var builtins = (scope === 'daily' ? DAILY_BUILTINS : MONTHLY_BUILTINS).filter(function (k) { return have.indexOf(k) < 0; });
        return h`<div class="flex gap-8 wrap mt-8"><button type="button" class="btn btn-sm btn-outline" data-fadd="${scope}:custom">${icon('plus', 14)} حقل جديد</button>${builtins.map(function (k) { return h`<button type="button" class="btn btn-sm btn-ghost" data-fadd="${scope}:${k}">${icon('plus', 14)} ${BUILTIN_LABEL[k]}</button>`; })}</div>`;
      }
      function body() {
        return h`<div class="banner note fs-sm mb-12">${icon('info', 15)}<div>الحقول تُعرف هنا لا في الكود: اليومية يملؤها السائق في التطبيق مع لقطة شاشته، والشهرية يدخلها المكتب أو يستوردها في بيانات الشهر. قواعد نظام الدفع تقرأ منها (مثلاً سعر لكل وحدة من حقل عددي، أو شرط على حقل نعم/لا). مجموع الحقل اليومي في الشهر: جمع الأرقام، أو عدد الأيام بنعم.</div></div>
          <div class="section-t">التقرير اليومي في تطبيق السائق</div>${table('daily')}${addMenu('daily')}
          <div class="form-grid mt-8">${BT.f.select({ name: 'screenshot', label: 'لقطة الشاشة اليومية', value: f.screenshot == null ? '' : String(f.screenshot), placeholder: 'حسب الإعداد العام', options: [{ v: 'true', t: 'مطلوبة' }, { v: 'false', t: 'غير مطلوبة' }] })}</div>
          <div class="section-t mt-16">بيانات الشهر (يدخلها المكتب أو يستوردها)</div>${table('monthly')}${addMenu('monthly')}`;
      }
      function read(panel) {
        ['daily', 'monthly'].forEach(function (scope) {
          lists[scope].forEach(function (x, i) {
            var id = scope + ':' + i;
            var ar = panel.querySelector('[data-fl-ar="' + id + '"]'), en = panel.querySelector('[data-fl-en="' + id + '"]');
            if (ar) x.label = { ar: ar.value.trim(), en: (en.value || ar.value).trim() };
            var t = panel.querySelector('[data-ftype="' + id + '"]'); if (t) x.type = t.value;
            var req = panel.querySelector('[name="freq_' + scope + '_' + i + '"]'); if (req) x.required = req.checked;
            var help = panel.querySelector('[data-fhelp="' + id + '"]'); if (help) x.help = help.value.trim() ? { ar: help.value.trim(), en: help.value.trim() } : null;
            var o = panel.querySelector('[data-fopts="' + id + '"]');
            if (o) x.options = o.value.split(/[،,]/).map(function (s) { var p = s.split('='); var val = (p[0] || '').trim(); return val ? { value: val.toLowerCase(), label: { ar: (p[1] || val).trim(), en: (p[1] || val).trim() } } : null; }).filter(Boolean);
          });
        });
      }
      var dlg = A.formModal({
        title: 'حقول المنصة', subtitle: api.name(platform.name), icon: 'list-checks', size: 'xl', done: 'حُفظت الحقول',
        body: body(),
        submit: function (v, d) {
          read(d.panel);
          var clean = function (x) { return { key: x.key, label: x.label, type: x.type, builtin: x.builtin || null, required: !!x.required, help: x.help || null, options: x.options || [] }; };
          return api.put('/payroll/platforms/' + platform.id + '/fields', { version: f.version, daily: lists.daily.map(clean), monthly: lists.monthly.map(clean), screenshot: v.screenshot === '' ? null : v.screenshot === 'true' });
        },
        after: function (r) { if (done) done(r); }
      });
      function redraw() { BT.render(dlg.body, body()); }
      function at(x, attr) { var a = x.getAttribute(attr).split(':'); return [a[0], +a[1]]; }
      BT.on(dlg.panel, 'click', '[data-fadd]', function (e, x) {
        read(dlg.panel);
        var a = x.getAttribute('data-fadd').split(':'), scope = a[0], kind = a[1];
        var taken = lists.daily.concat(lists.monthly).map(function (y) { return y.key; });
        if (kind === 'custom') {
          var label = window.prompt('اسم الحقل بالإنجليزية (منه يُصنع المفتاح)، مثل Grocery orders');
          if (label == null) return;
          lists[scope].push({ key: slug(label, taken.concat(DAILY_BUILTINS, MONTHLY_BUILTINS, ['valid_days', 'working_days', 'hours'])), label: { ar: label, en: label }, type: 'int', builtin: null, required: false, help: null, options: [] });
        } else {
          lists[scope].push({ key: kind, label: { ar: BUILTIN_LABEL[kind], en: kind }, type: BUILTIN_TYPE[kind], builtin: kind, required: false, help: null, options: kind === 'task_counts' ? [] : [] });
        }
        redraw();
      });
      BT.on(dlg.panel, 'click', '[data-fx]', function (e, x) { read(dlg.panel); var p = at(x, 'data-fx'); lists[p[0]].splice(p[1], 1); redraw(); });
      BT.on(dlg.panel, 'click', '[data-fup]', function (e, x) { read(dlg.panel); var p = at(x, 'data-fup'), l = lists[p[0]]; if (p[1] > 0) { l.splice(p[1] - 1, 0, l.splice(p[1], 1)[0]); redraw(); } });
      BT.on(dlg.panel, 'click', '[data-fdown]', function (e, x) { read(dlg.panel); var p = at(x, 'data-fdown'), l = lists[p[0]]; if (p[1] < l.length - 1) { l.splice(p[1] + 1, 0, l.splice(p[1], 1)[0]); redraw(); } });
      BT.on(dlg.panel, 'change', '[data-ftype]', function () { read(dlg.panel); redraw(); });
    }, api.fail);
  };

  /* ================= مراحل الشهر الست ================= */
  var STAGES = [
    ['collect', 'تجميع البيانات', 'طلبات كل سائق، الحضور، أيام النجمة، المخالفات، المصاريف'],
    ['check', 'التحقق', 'تكرار، أيام ناقصة، تعارض الحضور مع الطلبات، بيانات سائق ناقصة'],
    ['policy', 'تحديد السياسة', 'الشركة، النظام لكل سائق، نسخة القواعد للشهر'],
    ['engine', 'تشغيل المحرك', 'الأجر ثم الحوافز ثم الخصومات ثم المصاريف بالترتيب المعتمد'],
    ['review', 'المراجعة والاعتماد', 'حالات تحتاج إنساناً، الاعتماد حسب الصلاحيات واختبار المطابقة'],
    ['close', 'إقفال الشهر', 'كشوف مقفلة بتفاصيل الحساب، Excel، سجل التدقيق']
  ];
  var COUNT_TEXT = {
    drivers: 'سائق على المنصات', values_missing: 'سائق ينقصه رقم يحتاجه نظامه', daily_pending: 'تقرير يومي بانتظار المراجعة', imports: 'ملف مستورد هذا الشهر',
    orders_conflict: 'سائق طلبات الباتش عنده ≠ التقارير اليومية', driver_id_missing: 'سائق بلا رقم في المنصة', statements_pending: 'كشف منصة بانتظار المراجعة',
    scheme_missing: 'سائق بلا نظام دفع', schemes: 'نظام دفع مستخدم', runs: 'كشف رواتب', drafts: 'مسودة', figures_missing: 'سطر ينقصه رقم',
    blocking: 'سطر غير جاهز للاعتماد', approved: 'كشف معتمد', objections_open: 'اعتراض سائق مفتوح', gate_off: 'الاعتماد متوقف حتى اختبار المطابقة',
    paid: 'كشف مدفوع', uncollected: 'خصم غير محصل للمراجعة'
  };
  var PROBLEM_COUNTS = ['values_missing', 'daily_pending', 'orders_conflict', 'statements_pending', 'scheme_missing', 'figures_missing', 'blocking', 'gate_off'];
  A.monthStepper = function (box, month) {
    api.get('/payroll/month-status', { month: month + '-01' }).then(function (s) {
      if (!document.contains(box)) return;
      BT.render(box, h`<div class="grid mb-16" data-stepper style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px">${STAGES.map(function (st, i) {
        var x = s[st[0]] || {}, tone = x.state === 'done' ? 'g' : x.state === 'problem' ? 'r' : x.state === 'todo' ? 'o' : 'n';
        var link = x.link || null;
        return h`<div class="card" data-stage="${st[0]}" data-state="${x.state || 'na'}"><div class="card-b"><div class="flex gap-8 items-center"><span class="pill ${tone}">${i + 1}</span><b>${link ? h`<a href="#/${link}">${st[1]}</a>` : st[1]}</b></div>
          <div class="muted fs-sm mt-4">${st[2]}</div>
          <ul class="fs-sm mt-8" style="padding-inline-start:16px">${Object.keys(x.counts || {}).filter(function (k) { return x.counts[k] || k === 'drivers' || k === 'runs'; }).map(function (k) {
            var n = x.counts[k];
            return h`<li class="${PROBLEM_COUNTS.indexOf(k) >= 0 && n ? 't-danger' : ''}" data-count="${k}">${k === 'gate_off' ? COUNT_TEXT[k] : h`<b class="num">${n}</b> ${COUNT_TEXT[k] || k}`}</li>`;
          })}</ul></div></div>`;
      })}</div>`);
    }, function () { BT.render(box, ''); });
  };

  /* ================= بيانات الشهر ================= */
  var PROBLEM = { values_missing: 'أرقام ناقصة', orders_conflict: 'الباتش ≠ الطلبات اليومية', daily_pending: 'تقرير بانتظار المراجعة', scheme_missing: 'بلا نظام', driver_id_missing: 'بلا رقم في المنصة' };
  A.monthPanel = function (el, q) {
    var month = (q.month || thisMonth()).slice(0, 7), platformId = q.platform ? +q.platform : null;
    A.platforms().then(function (plats) {
      plats = plats.filter(function (p) { return p.is_active; });
      if (!platformId && plats.length) platformId = plats[0].id;
      BT.render(el, h`<div data-stepper-box></div><div class="card"><div class="flex gap-8 items-end wrap mb-12">
          <div class="field" style="max-width:200px"><label for="f-mi-month">الشهر</label><input class="input" type="month" id="f-mi-month" value="${month}"></div>
          <div class="field" style="max-width:240px"><label for="f-mi-plat">المنصة</label><select class="select" id="f-mi-plat">${plats.map(function (p) { return h`<option value="${p.id}"${p.id === platformId ? raw(' selected') : ''}>${api.name(p.name)}</option>`; })}</select></div>
          <span class="spacer"></span>
          ${api.can('payroll.view') ? A.btn('نموذج Excel فارغ', { icon: 'download', cls: 'btn-ghost', id: 'mi-template' }) : ''}
          ${api.can('payroll.prepare') ? A.btn('استيراد من Excel', { icon: 'file-spreadsheet', cls: 'btn-primary', id: 'mi-import' }) : ''}
        </div><div data-grid></div></div>`);
      A.monthStepper(el.querySelector('[data-stepper-box]'), month);
      function load() {
        var grid = el.querySelector('[data-grid]');
        if (!platformId) { BT.render(grid, BT.empty('banknote', 'لا توجد منصات', '')); return; }
        A.load(grid, api.get('/payroll/month-review', { platform_id: platformId, month: month + '-01' }), function (r) { return reviewTable(r); }).then(function (r) { if (r) wire(grid, r); }).catch(function () {});
      }
      function reviewTable(r) {
        var monthly = r.form.monthly.filter(function (x) { return x.type !== 'batch_orders' && x.type !== 'task_counts'; });
        var hasBatches = r.form.monthly.some(function (x) { return x.type === 'batch_orders'; }) || r.rows.some(function (x) { return x.batches.length; });
        var daily = r.form.daily.filter(function (x) { return !x.builtin && x.type !== 'choice'; });
        var counts = Object.keys(r.problems);
        return h`${counts.length ? h`<div class="flex gap-8 wrap mb-12">${counts.map(function (k) { return BT.pill(PROBLEM[k] + ': ' + r.problems[k], k === 'driver_id_missing' ? 'o' : 'r'); })}</div>` : h`<div class="banner success fs-sm mb-12">${icon('circle-check', 15)}<div>لا مشاكل في بيانات هذا الشهر.</div></div>`}
          <div class="table-wrap"><table class="t compact" data-month-grid><thead><tr><th>السائق</th><th>النظام</th><th class="num">الطلبات</th><th class="num">الأيام الصالحة</th>${hasBatches ? h`<th>حسب الباتش</th>` : ''}${monthly.map(function (x) { return h`<th class="num">${api.name(x.label)}</th>`; })}${daily.map(function (x) { return h`<th class="num">${api.name(x.label)} <span class="muted fs-sm">(شهري)</span></th>`; })}<th>استثناءات</th><th>ملاحظات</th></tr></thead><tbody>
            ${r.rows.map(function (x) {
              return h`<tr class="clickable" data-mrow="${x.employee.id}"><td>${A.person(x.employee, x.platform_driver_id || '')}</td><td>${x.scheme ? api.name(x.scheme.name) : h`<span class="muted">—</span>`}</td><td class="num">${x.orders}</td><td class="num">${x.valid_days == null ? '—' : x.valid_days}</td>
                ${hasBatches ? h`<td class="ltr fs-sm">${x.batches.map(function (b) { return b.batch + ':' + b.orders; }).join('  ') || '—'}</td>` : ''}
                ${monthly.map(function (f) { var val = x.values[f.key]; return h`<td class="num">${val == null ? h`<span class="${x.missing.indexOf(f.key) >= 0 ? 't-danger' : 'muted'}">—</span>` : f.type === 'bool' ? (Number(val) ? 'نعم' : 'لا') : Number(val)}</td>`; })}
                ${daily.map(function (f) { return h`<td class="num">${x.daily[f.key] == null ? '—' : Number(x.daily[f.key])}</td>`; })}
                <td>${x.exceptions.length ? BT.pill(x.exceptions.length, 'p') : ''}</td><td>${x.problems.map(function (k) { return BT.pill(PROBLEM[k], k === 'driver_id_missing' ? 'o' : 'r'); })}${x.locked ? BT.pill('مقفل', 'n') : ''}</td></tr>`;
            })}</tbody></table></div>`;
      }
      function wire(grid, r) {
        A.delegate(grid, 'click', '[data-mrow]', function (e, tr) { var row = r.rows.find(function (x) { return x.employee.id === tr.getAttribute('data-mrow'); }); if (row) driverMonth(r, row, month, load); });
      }
      el.querySelector('#f-mi-month').addEventListener('change', function (e) { month = e.target.value || thisMonth(); A.monthStepper(el.querySelector('[data-stepper-box]'), month); load(); });
      el.querySelector('#f-mi-plat').addEventListener('change', function (e) { platformId = +e.target.value; load(); });
      var tb = el.querySelector('#mi-template'); if (tb) tb.onclick = function () { A.download('/payroll/month-imports/template', { platform_id: platformId }); };
      var ib = el.querySelector('#mi-import'); if (ib) ib.onclick = function () { importMonth(plats.find(function (p) { return p.id === platformId; }), month, function () { load(); A.monthStepper(el.querySelector('[data-stepper-box]'), month); }); };
      load();
    }, api.fail);
  };

  function driverMonth(r, row, month, done) {
    var can = api.can('payroll.prepare') && !row.locked, canApprove = api.can('payroll.approve') && !row.locked;
    var monthly = r.form.monthly.filter(function (x) { return x.type !== 'batch_orders' && x.type !== 'task_counts' && x.type !== 'choice'; });
    ['attendance_marks', 'star_day_failed', 'late_count'].forEach(function (k) { if (row.missing.indexOf(k) >= 0 && !monthly.some(function (x) { return x.key === k; })) monthly.push({ key: k, type: k === 'star_day_failed' ? 'bool' : 'int', label: { ar: BUILTIN_LABEL[k], en: k } }); });
    var tasks = (r.form.monthly.find(function (x) { return x.type === 'task_counts'; }) || {}).options || [];
    var btns = [{ label: 'إغلاق', cls: 'btn-ghost' }];
    if (canApprove) btns.push({ label: 'استثناء', cls: 'btn-outline', icon: 'shield-check', close: false, onClick: function (dlg) { addException(row, month, function () { dlg.close(); done(); }); } });
    if (can) btns.push({ label: 'حفظ', cls: 'btn-primary', icon: 'check', close: false, onClick: function (dlg) {
      var form = dlg.panel.querySelector('form[data-mv]');
      if (!BT.form.validate(form)) return;
      var v = BT.form.values(form), values = {};
      monthly.forEach(function (f) { var x = v['v_' + f.key]; values[f.key] = x === '' || x == null ? null : f.type === 'bool' ? x === 'true' : (f.type === 'money' ? String(x) : Math.round(Number(x))); });
      var batches = A.parseBatches(v.batches);
      if (batches === null) { BT.toast('الطلبات حسب الباتش: كل صف باتش:طلبات (الباتش من 1 إلى 20)، مثل 4:118, 2:39', { type: 'error' }); return; }
      var body = { month: month + '-01', values: values, batches: batches };
      if (tasks.length) { body.tasks = {}; tasks.forEach(function (o) { if (v['t_' + o.value] !== '' && v['t_' + o.value] != null) body.tasks[o.value] = Math.round(Number(v['t_' + o.value])); }); }
      api.put('/payroll/month-review/' + row.employee.id, body).then(function () { BT.toast('حُفظت بيانات الشهر'); dlg.close(); done(); }, api.fail);
    } });
    BT.drawer.open({
      title: api.name(row.employee.name), subtitle: monthLabel(month + '-01') + (row.scheme ? ' · ' + api.name(row.scheme.name) : ''), icon: 'calendar', size: 'lg', buttons: btns,
      body: h`${row.problems.length ? h`<div class="flex gap-8 wrap mb-12">${row.problems.map(function (k) { return BT.pill(PROBLEM[k], 'r'); })}</div>` : ''}
        ${row.missing.length ? h`<div class="banner warn fs-sm mb-12" data-missing>${icon('triangle-alert', 15)}<div>ينقص ما يقرؤه نظامه: ${row.missing.map(function (k) { var f = r.form.monthly.find(function (x) { return x.key === k; }); return f ? api.name(f.label) : api.t('rule_source', k, null, BUILTIN_LABEL[k] || k); }).join('، ')}</div></div>` : ''}
        ${BT.kv([['الطلبات (التقارير المعتمدة أو الكشف)', String(row.orders)], ['الأيام الصالحة', row.valid_days == null ? '—' : String(row.valid_days)], ['أيام الدوام', String(row.working_days)]].concat(Object.keys(row.daily).map(function (k) { var f = r.form.daily.find(function (x) { return x.key === k; }); return [(f ? api.name(f.label) : k) + ' (مجموع الشهر)', String(Number(row.daily[k]))]; })))}
        <form data-mv class="form mt-12" novalidate><div class="form-grid">
          ${monthly.map(function (f) {
            var val = row.values[f.key];
            if (f.type === 'bool') return BT.f.select({ name: 'v_' + f.key, label: api.name(f.label), value: val == null ? '' : (Number(val) ? 'true' : 'false'), placeholder: 'لم يُدخل', options: [{ v: 'false', t: 'لا' }, { v: 'true', t: 'نعم' }], disabled: !can });
            return BT.f.input({ name: 'v_' + f.key, label: api.name(f.label), value: val == null ? '' : Number(val), num: true, optional: true, disabled: !can });
          })}
          ${BT.f.input({ name: 'batches', label: 'الطلبات حسب الباتش', value: row.batches.map(function (b) { return b.batch + ':' + b.orders; }).join(', '), optional: true, placeholder: '4:118, 2:39', hint: 'باتش:طلبات لكل صف؛ الطلبات قد تنقسم على أكثر من باتش في الشهر', disabled: !can })}
          ${tasks.map(function (o) { return BT.f.input({ name: 't_' + o.value, label: api.name(o.label), value: row.tasks[o.value] == null ? '' : row.tasks[o.value], num: true, optional: true, disabled: !can }); })}
        </div></form>
        <div class="section-t mt-16">الاستثناءات المعتمدة</div>
        ${row.exceptions.length ? h`<div class="table-wrap"><table class="t compact"><tbody>${row.exceptions.map(function (x) { return h`<tr><td><b>${api.t('rule_choice', x.kind)}</b>${(x.excuses || []).length ? ' · يعذر عن: ' + x.excuses.map(function (k) { return api.t('rule_excuse', k); }).join('، ') : ''}${x.days ? ' · ' + x.days : ''}${Object.keys(x.corrections || {}).length ? h`<span class="sub">التصحيح: ${Object.keys(x.corrections).map(function (k) { return k + ' = ' + x.corrections[k]; }).join('، ')}</span>` : ''}<span class="sub">${x.note} — ${x.approved_by || ''}</span></td><td>${canApprove ? h`<button type="button" class="btn btn-sm btn-ghost" data-xcancel="${x.id}">إلغاء</button>` : ''}</td></tr>`; })}</tbody></table></div>` : h`<div class="muted fs-sm">لا يوجد</div>`}`,
      onOpen: function (dlg) {
        BT.on(dlg.panel, 'click', '[data-xcancel]', function (e, b) {
          A.confirmRun({ title: 'إلغاء الاستثناء', message: 'يُلغى ولا يُحذف، ويبقى في سجل التدقيق.', confirmText: 'إلغاء الاستثناء', tone: 'danger', reason: { label: 'السبب', required: true }, run: function (reason) { return api.post('/payroll/month-exceptions/' + b.getAttribute('data-xcancel') + '/cancel', { note: reason }); }, done: 'أُلغي الاستثناء', after: function () { dlg.close(); done(); } });
        });
      }
    });
  }

  function addException(row, month, done) {
    A.formModal({
      title: 'استثناء معتمد', subtitle: api.name(row.employee.name) + ' · ' + monthLabel(month + '-01'), icon: 'shield-check', done: 'اعتُمد الاستثناء',
      body: h`<div class="form">${BT.f.radios({ name: 'kind', label: 'النوع', required: true, value: 'accepted_excuse', options: [{ v: 'accepted_excuse', t: 'عذر مقبول', d: 'يلغي شروط الحضور وStar Day في القواعد التي تقول ذلك' }, { v: 'exception_day', t: 'يوم معتمد كاستثناء', d: 'يُحسب يوماً صالحاً في القواعد التي تقول ذلك' }, { v: 'company_error', t: 'خطأ في بيانات الشركة', d: 'الأرقام المصححة تحل محل أرقام الشهر' }] })}
        <div class="field" data-excuses><label>يعذر عن (كل واحدة وحدها)</label><div class="flex gap-12 wrap">${['star_day', 'marks', 'lateness', 'absence', 'valid_days'].map(function (k) { return BT.f.check({ name: 'ex_' + k, label: api.t('rule_excuse', k) }); })}</div><div class="hint">عذر Star Day لا يمس العلامات، وعدد أيام لا يلغي تفويت Star Day.</div></div>
        ${BT.f.input({ name: 'days', label: 'عدد الأيام أو العلامات أو مرات التأخير (فارغ = كلها؛ مطلوب للأيام الصالحة)', num: true, optional: true })}
        ${BT.f.input({ name: 'orders', label: 'الطلبات المصححة (لخطأ بيانات الشركة)', num: true, optional: true })}
        ${BT.f.input({ name: 'valid_days', label: 'الأيام الصالحة المصححة', num: true, optional: true })}
        ${BT.f.input({ name: 'attendance_marks', label: 'العلامات المصححة', num: true, optional: true })}
        ${BT.f.input({ name: 'note', label: 'الملاحظة (مطلوبة)', required: true, pattern: '[\\s\\S]{3,}', msg: 'ثلاثة أحرف على الأقل' })}</div>`,
      submit: function (v) {
        var corrections = {};
        if (v.kind === 'company_error') ['orders', 'valid_days', 'attendance_marks'].forEach(function (k) { if (v[k] !== '' && v[k] != null) corrections[k] = Math.round(Number(v[k])); });
        var excuses = v.kind === 'company_error' ? [] : ['star_day', 'marks', 'lateness', 'absence', 'valid_days'].filter(function (k) { return v['ex_' + k]; });
        return api.post('/payroll/month-exceptions', { employee_id: row.employee.id, month: month + '-01', kind: v.kind, days: v.days === '' || v.days == null ? 0 : Math.round(Number(v.days)), excuses: excuses, corrections: corrections, note: v.note });
      },
      after: done
    });
  }

  function importMonth(platform, month, done) {
    var file = null, format = 'partner_batches', replace = false;
    function post(path) {
      var fd = new FormData();
      fd.append('file', file, file.name || 'month.xlsx');
      fd.append('platform_id', String(platform.id));
      fd.append('month', month + '-01');
      fd.append('format', format);
      fd.append('replace_month', replace ? 'true' : 'false');
      return api.request('POST', path, { form: fd });
    }
    var dlg = BT.modal.open({
      title: 'استيراد بيانات الشهر', subtitle: api.name(platform.name) + ' · ' + monthLabel(month + '-01'), icon: 'file-spreadsheet', size: 'lg', form: true,
      body: h`<div class="form">${BT.f.radios({ name: 'format', label: 'الملف', value: 'partner_batches', options: [{ v: 'partner_batches', t: 'تقرير المنصة للشركاء', d: 'Rider ID، Batch No.، Total Completed Deliveries: السائق برقمه في المنصة' }, { v: 'generic', t: 'النموذج البسيط', d: 'الرقم المدني أو رقم المنصة، الشهر، عمود لكل حقل شهري' }] })}
        ${BT.f.upload({ name: 'file', label: 'ملف Excel', accept: '.xlsx', accept_label: 'xlsx', required: true })}
        ${BT.f.check({ name: 'replace_month', label: 'استبدال الشهر كله: صفوف الباتش لهذا الشهر تُستبدل كلها بصفوف الملف' })}</div><div data-check class="mt-12"></div>`,
      buttons: [{ label: 'إغلاق', cls: 'btn-ghost' }, { label: 'فحص', cls: 'btn-outline', submit: true }, { label: 'تطبيق', cls: 'btn-primary', icon: 'check', close: false, disabled: true, onClick: function (d) {
        d.busy(2, true);
        post('/payroll/month-imports').then(function (r) { BT.toast('طُبق الملف على ' + r.applied + ' سائق'); d.close(); done(); }, function (e) { d.busy(2, false); api.fail(e); });
      } }],
      onSubmit: function (v, d) {
        file = v.file && v.file[0]; format = v.format || 'partner_batches'; replace = !!v.replace_month;
        if (!file) return false;
        post('/payroll/month-imports/check').then(function (c) {
          BT.render(d.panel.querySelector('[data-check]'), checkView(c));
          var apply = d.btn(2); apply.disabled = !!c.blocking;
        }, api.fail);
        return false;
      }
    });
    return dlg;
  }
  var REASON = {
    invalid_rows: 'صفوف لا تُقرأ (رقم غير صحيح، باتش 0، استثناء ناقص): لا يُطبق شيء حتى يُصحح الملف',
    duplicate_conflict: 'رقمان مختلفان لنفس السائق والباتش',
    month_locked: 'رواتب هذا الشهر معتمدة لبعض السائقين',
    no_drivers: 'لا سائق معروف في الملف',
    month_has_batches: 'لهذا الشهر صفوف باتش من قبل: اختر «استبدال الشهر كله» ثم افحص من جديد',
    exceptions_need_approval: 'في الملف استثناءات، واعتمادها يحتاج صلاحية اعتماد الرواتب'
  };
  function checkView(c) {
    var differing = c.duplicates.filter(function (x) { return !x.same; });
    return h`<div data-import-check><div class="flex gap-8 wrap mb-8">${BT.pill(c.rows + ' صف', 'n')}${BT.pill(c.drivers.length + ' سائق', 'g')}${c.unknown.length ? BT.pill(c.unknown.length + ' غير معروف', 'o') : ''}${c.duplicates.length ? BT.pill(c.duplicates.length + ' مكرر', differing.length ? 'r' : 'o') : ''}${c.conflicts.length ? BT.pill(c.conflicts.length + ' تعارض مع التقارير اليومية', 'o') : ''}${c.other_month.length ? BT.pill(c.other_month.length + ' صف لشهر آخر (يُتجاهل)', 'n') : ''}${c.imported_before ? BT.pill('استورد هذا الملف من قبل: يحل محل نفسه ولا يُجمع مرتين', 'b') : ''}</div>
      ${c.blocking ? h`<div class="banner danger fs-sm mb-8" data-reasons>${icon('circle-x', 15)}<div><b>لا يُطبق الملف:</b><ul>${c.reasons.map(function (r) { return h`<li data-reason="${r}">${REASON[r] || r}</li>`; })}</ul></div></div>` : h`<div class="banner note fs-sm mb-8">${icon('info', 15)}<div>${c.same_as_existing ? 'صفوف الباتش في الملف هي نفسها الموجودة: لا يتغير شيء ولا يُحسب شيء مرتين.' : c.replace_month ? 'صفوف الباتش لهذا الشهر تُستبدل كلها بصفوف الملف.' : 'تُضاف بيانات الشهر من الملف.'}</div></div>`}
      ${c.invalid.length ? h`<div class="section-t">صفوف لا تُقرأ</div><div class="fs-sm ltr t-danger" data-invalid-rows>${c.invalid.map(function (u) { return '#' + u.row + ' ' + (u.rider || ''); }).join(' · ')}</div>` : ''}
      ${(c.exceptions || []).length ? h`<div class="section-t mt-8">استثناءات معتمدة في الملف</div><ul class="fs-sm">${c.exceptions.map(function (x) { return h`<li>${api.name(x.employee.name)}: ${api.t('rule_choice', x.kind)} · ${x.excuses.map(function (k) { return api.t('rule_excuse', k); }).join('، ')}${x.days ? ' · ' + x.days : ''} — ${x.note}</li>`; })}</ul>` : ''}
      ${c.unknown.length ? h`<div class="section-t">لا نعرفهم (لم يُطابق رقمهم في المنصة)</div><div class="fs-sm ltr">${c.unknown.map(function (u) { return '#' + u.row + ' ' + u.rider; }).join(' · ')}</div>` : ''}
      ${c.conflicts.length ? h`<div class="section-t mt-8">طلبات الملف ≠ التقارير اليومية المعتمدة</div><ul class="fs-sm">${c.conflicts.map(function (x) { return h`<li>${api.name(x.employee.name)}: الملف ${x.file_orders}، التقارير ${x.daily_orders}</li>`; })}</ul>` : ''}
      ${c.duplicates.length ? h`<div class="section-t mt-8">صفوف مكررة</div><ul class="fs-sm">${c.duplicates.map(function (x) { return h`<li class="${x.same ? '' : 't-danger'}">#${x.row} (مثل #${x.first_row}) ${api.name(x.employee.name)}${x.sub ? ' باتش ' + x.sub : ''}: ${x.same ? 'نفس الرقم، يُحسب مرة' : 'رقم مختلف'}</li>`; })}</ul>` : ''}
      <div class="table-wrap mt-8"><table class="t compact"><thead><tr><th>السائق</th><th>حسب الباتش</th><th>حقول</th><th></th></tr></thead><tbody>${c.drivers.map(function (x) { return h`<tr><td>${api.name(x.employee.name)}<span class="sub ltr">${x.employee.platform_driver_id || ''}</span></td><td class="ltr">${x.batches.map(function (b) { return b.batch + ':' + b.orders; }).join('  ')}</td><td class="fs-sm">${Object.keys(x.values).map(function (k) { return k + '=' + Number(x.values[k]); }).join('، ')}</td><td>${x.replaces ? BT.pill('يستبدل ما سبق', 'b') : ''}</td></tr>`; })}</tbody></table></div></div>`;
  }
})();
