/* =====================================================================
   app/pages/admin.js — الاستيراد، الإعدادات والصلاحيات، سجل التدقيق
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  /* ================= استيراد ملف البيانات ================= */
  BT.pages['import'] = function (p, q) {
    A.setTitle('استيراد البيانات');
    var v = A.view(), tab = q.tab === 'sheets' ? 'sheets' : 'template';
    BT.render(v, h`${A.head('استيراد البيانات', 'الفحص لا يغيّر شيئاً، والتنفيذ لملف بلا أخطاء فقط ويُطبَّق كله أو لا شيء. نفس الملف يمكن استيراده مرة أخرى: يحدّث الموجود ولا يكرره.', '')}
      ${BT.tabs('imp', [['template', 'قالب العقد'], ['sheets', 'ملف بصيغة أخرى']], tab, 'tabs-line')}
      <div data-panel="template" data-group="imp" class="${tab === 'template' ? 'active' : ''}"><div data-p="template"></div></div>
      <div data-panel="sheets" data-group="imp" class="${tab === 'sheets' ? 'active' : ''}"><div data-p="sheets"></div></div>`);
    templatePanel(v.querySelector('[data-p="template"]'));
    if (A.phoneCodes) A.phoneCodes();
    sheetsPanel(v.querySelector('[data-p="sheets"]'));
    v.addEventListener('bt:tab', function (e) { history.replaceState(null, '', '#/import?tab=' + e.detail); });
  };

  function templatePanel(el) {
    var file = null;
    BT.render(el, h`<div class="card"><div class="form" style="max-width:560px">
        <p class="muted fs-sm">ملف Excel المرفق بالعقد (السيارات، المستخدمون والسائقون، الأرصدة الافتتاحية) كما هو: نفس أسماء الأوراق ونفس الأعمدة.</p>
        <p class="muted fs-sm">أعمدة اختيارية للسائقين في «المستخدمون والسائقون» بعد العمود M: تفعيل التطبيق (N: نعم أو لا، والفارغ يُفعَّل)، وكلمة المرور المبدئية (O)، وصلاحيتها بالأيام (P: من 1 إلى 60، والفارغ 14). ملف بلا هذه الأعمدة يُستورد كما كان.</p>
        <div class="banner info fs-sm">${icon('key-round', 15)}<div>كلمة المرور المبدئية تحتاج صلاحية «إدارة أجهزة السائقين»${api.can('devices.manage') ? '' : ' (ليست لديك: صفوفها تظهر خطأً)'}، ولا يغيّرها الاستيراد لسائق له كلمة مفتوحة أو دخل بها من قبل. الملف بعد كتابة كلمات المرور سري: احذفه بعد الاستيراد.</div></div>
        <div><button type="button" class="btn btn-outline btn-sm" data-template>${icon('download', 14)} تنزيل القالب</button></div>
        ${BT.f.upload({ name: 'file', label: 'ملف Excel (.xlsx)', accept: '.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', accept_label: 'xlsx · حتى 10MB' })}
        <div class="flex gap-8"><button type="button" class="btn btn-primary" data-check>${icon('list-checks', 15)} فحص الملف دون حفظ</button><button type="button" class="btn btn-success hidden" data-apply>${icon('check', 15)} تنفيذ الاستيراد</button></div></div>
        <div data-result class="mt-16"></div></div>`);
    var input = el.querySelector('input[type=file]'), res = el.querySelector('[data-result]'), applyBtn = el.querySelector('[data-apply]');
    input.addEventListener('change', function () { file = input.files[0] || null; applyBtn.classList.add('hidden'); BT.render(res, ''); });
    function run(apply, btn) {
      if (!file) { BT.toast('اختر الملف أولاً', { type: 'error' }); return; }
      btn.classList.add('is-loading'); btn.disabled = true;
      api.uploadForm('/imports/workbook', file, { apply: apply }).then(function (r) {
        btn.classList.remove('is-loading'); btn.disabled = false;
        BT.render(res, result(r, true));
        applyBtn.classList.toggle('hidden', apply || r.errors.length > 0);
        if (apply) { BT.toast('تم الاستيراد'); file = null; input.value = ''; }
      }, function (err) { btn.classList.remove('is-loading'); btn.disabled = false; BT.render(res, h`<div class="banner danger">${icon('circle-x', 16)}<div>${api.message(err)}</div></div>`); });
    }
    el.querySelector('[data-check]').onclick = function (e) { run(false, e.currentTarget); };
    el.querySelector('[data-template]').onclick = function () { A.downloadFile('/imports/workbook/template', {}, 'import-template.xlsx'); };
    applyBtn.onclick = function () {
      BT.confirm({ title: 'تنفيذ الاستيراد', message: 'تُضاف السجلات الجديدة وتُحدَّث الموجودة دفعة واحدة.', confirmText: 'تنفيذ', tone: 'success' }).then(function (r) { if (r.ok) run(true, applyBtn); });
    };
  }

  /* ملف العميل بصيغته: أي أسماء أوراق وأي ترتيب أعمدة، حتى بلا صف عناوين.
     الخادم يقترح نوع كل ورقة وعمود كل حقل، والمستخدم يؤكد أو يصحح قبل الفحص. */
  var KIND = { vehicles: 'السيارات', employees: 'الموظفون والسائقون' };
  function colName(i) { var s = ''; i++; while (i > 0) { var m = (i - 1) % 26; s = String.fromCharCode(65 + m) + s; i = Math.floor((i - 1) / 26); } return s; }
  function sheetsPanel(el) {
    var file = null, pv = null;
    BT.render(el, h`<div class="card"><div class="form">
        <p class="muted fs-sm">ملف Excel بصيغتكم كما هو: أوراق السيارات والموظفين بأي ترتيب أعمدة، ولو بلا صف عناوين. يقترح النظام نوع كل ورقة والعمود المناسب لكل حقل، فراجعها قبل الفحص. المستندات (الإقامة، الرخصة، الجواز) والهاتف والآيبان يكملها السائق في التسجيل الذاتي إن لم تكن في الملف. ولكل سائق إن كانت في الملف أعمدة لها: تفعيل التطبيق (نعم/لا)، وكلمة مرور مبدئية (تحتاج صلاحية «إدارة أجهزة السائقين»)، وصلاحيتها بالأيام.</p>
        <div style="max-width:560px">${BT.f.upload({ name: 'file', label: 'ملف Excel (.xlsx)', accept: '.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', accept_label: 'xlsx · حتى 10MB' })}</div>
        <div data-plan></div></div>
        <div data-result class="mt-16"></div></div>`);
    var input = el.querySelector('input[type=file]'), planBox = el.querySelector('[data-plan]'), res = el.querySelector('[data-result]');
    input.addEventListener('change', function () {
      file = input.files[0] || null; pv = null; BT.render(res, '');
      if (!file) { BT.render(planBox, ''); return; }
      A.load(planBox, Promise.all([api.uploadForm('/imports/sheets/preview', file), api.get('/companies/options'), api.get('/branches')]), function (r) {
        pv = r[0];
        setTimeout(function () { wire(r[1]); });
        return form(r[1], r[2]);
      }).catch(function () {});
    });
    function options(sheet, kind, field) {
      return [{ v: '', t: '— لا يوجد —' }].concat(sheet.columns.map(function (c) {
        var sample = field === 'initial_password' ? '' : c.samples.filter(Boolean).slice(0, 2).join('، ');
        return { v: c.index, t: colName(c.index) + (c.header ? ' · ' + c.header : '') + (sample ? ' — ' + sample : '') };
      }));
    }
    function mappingRows(sheet, kind) {
      var picked = kind === sheet.kind ? sheet.mapping : {};
      // drivers' passwords need «إدارة أجهزة السائقين»: without it the password and its days are not offered
      var shown = pv.fields[kind].filter(function (f) { return api.can('devices.manage') || (f.key !== 'initial_password' && f.key !== 'password_days'); });
      return shown.map(function (f) {
        return h`<tr><td>${api.t('import_field', f.key)}${f.required ? raw('<span class="req">*</span>') : ''}</td><td>${BT.f.select({ name: 'col_' + f.key, value: picked[f.key] != null ? picked[f.key] : '', placeholder: false, options: options(sheet, kind, f.key) })}</td></tr>`;
      });
    }
    function sheetCard(sheet, i) {
      var kind = sheet.kind || '';
      return h`<div class="card mt-12" data-sheet="${i}"><div class="card-h"><div class="card-t">${icon('sheet', 15)} ${sheet.name}</div><span class="muted fs-sm">${fmt.int(sheet.rows)} صف${sheet.header_row ? ' · العناوين في الصف ' + sheet.header_row : sheet.rows ? ' · بلا صف عناوين' : ''}</span></div>
        <div class="card-b"><div class="form-grid">${BT.f.select({ name: 'kind', label: 'تُستورد كـ', value: kind, placeholder: false, options: [{ v: '', t: 'لا تُستورد' }, { v: 'vehicles', t: KIND.vehicles }, { v: 'employees', t: KIND.employees }] })}${BT.f.input({ name: 'first_row', label: 'أول صف بيانات', value: sheet.first_row, num: true })}</div>
        <div data-map>${kind ? h`<div class="table-wrap mt-8"><table class="t compact"><thead><tr><th>الحقل</th><th>العمود في الملف</th></tr></thead><tbody>${mappingRows(sheet, kind)}</tbody></table></div>` : ''}</div></div></div>`;
    }
    function form(companies, branches) {
      var active = companies.filter(function (c) { return c.is_active; });
      return h`<div class="form-grid mt-12">${BT.f.select({ name: 'company_id', label: 'الشركة', required: true, value: active.length === 1 ? active[0].id : '', options: active.map(function (c) { return { v: c.id, t: api.name(c.name) }; }) })}
          ${BT.f.select({ name: 'branch_id', label: 'الفرع', value: '', placeholder: 'الفرع الرئيسي', options: branches.filter(function (b) { return b.is_active; }).map(function (b) { return { v: b.id, t: api.name(b.name) }; }) })}
          ${BT.f.input({ name: 'driver_keywords', label: 'يُعدّ الموظف سائقاً إذا احتوت مهنته على', value: 'سائق، driver', hint: 'كلمات مفصولة بفواصل' })}</div>
        ${api.can('devices.manage') ? h`<div class="card mt-12"><div class="card-b form">
          ${BT.f.check({ name: 'claim_on', label: A.codes === false ? 'السائقون بلا هاتف يدخلون برقمهم المدني وكلمة مرور مبدئية، ثم يختار كل منهم كلمة مروره' : 'السائقون بلا هاتف يدخلون مرة واحدة برقمهم المدني وكلمة مرور مبدئية، ثم يسجلون هواتفهم برمز واتساب' })}
          <div class="form-grid">${BT.f.input({ name: 'claim_password', label: 'كلمة مرور افتراضية لمن ليس له كلمة في الملف (ولا هاتف)', pattern: '.{8,64}', msg: '8 أحرف على الأقل', hint: 'تُبلَّغ للسائقين، وتعمل مرة واحدة لكل سائق. كلمة السائق في عمود الملف تُقدَّم عليها' })}${BT.f.input({ name: 'claim_days', label: 'صالحة لمدة (يوم)', value: 14, num: true })}</div>
          <div class="muted fs-sm">${A.codes === false ? 'ما يحمي الحساب: مرة واحدة (السائق الحقيقي يُرفض إن سبقه أحد فيبلغكم)، والمدة، ومراجعة تسجيله الذاتي (ومنه الآيبان) قبل الاعتماد. لا رمز واتساب: اجعل المدة قصيرة.' : 'ما يحمي الحساب: رمز واتساب على هاتف السائق، ومرة واحدة، والمدة، ومراجعة تسجيله الذاتي (ومنه الآيبان) قبل الاعتماد.'}</div></div></div>` : ''}
        ${pv.sheets.map(function (sh, i) { return sh.rows ? sheetCard(sh, i) : ''; })}
        ${pv.sheets.some(function (sh) { return !sh.rows; }) ? h`<div class="muted fs-sm mt-8">أوراق بلا بيانات لم تُعرض: ${pv.sheets.filter(function (sh) { return !sh.rows; }).map(function (sh) { return sh.name; }).join('، ')}</div>` : ''}
        <div class="flex gap-8 mt-12"><button type="button" class="btn btn-primary" data-check>${icon('list-checks', 15)} فحص دون حفظ</button><button type="button" class="btn btn-success hidden" data-apply>${icon('check', 15)} تنفيذ الاستيراد</button></div>`;
    }
    function plan() {
      var vals = BT.form.values(planBox);
      var out = { company_id: Number(vals.company_id), branch_id: vals.branch_id ? Number(vals.branch_id) : null, driver_keywords: String(vals.driver_keywords || '').split(/[,،]/).map(function (x) { return x.trim(); }).filter(Boolean), sheets: [] };
      if (vals.claim_on) { out.claim_password = vals.claim_password || ''; out.claim_days = Math.round(Number(vals.claim_days || 14)); }
      BT.$$('[data-sheet]', planBox).forEach(function (card) {
        var sheet = pv.sheets[+card.getAttribute('data-sheet')], kind = card.querySelector('[name=kind]').value;
        if (!kind) return;
        var columns = {};
        BT.$$('select[name^="col_"]', card).forEach(function (sel) { if (sel.value !== '') columns[sel.name.slice(4)] = Number(sel.value); });
        out.sheets.push({ name: sheet.name, kind: kind, first_row: Number(card.querySelector('[name=first_row]').value) || sheet.first_row, columns: columns });
      });
      return out;
    }
    function wire() {
      var applyBtn = planBox.querySelector('[data-apply]');
      BT.$$('[data-sheet] [name=kind]', planBox).forEach(function (sel) {
        sel.onchange = function () {
          var card = sel.closest('[data-sheet]'), sheet = pv.sheets[+card.getAttribute('data-sheet')];
          BT.render(card.querySelector('[data-map]'), sel.value ? h`<div class="table-wrap mt-8"><table class="t compact"><thead><tr><th>الحقل</th><th>العمود في الملف</th></tr></thead><tbody>${mappingRows(sheet, sel.value)}</tbody></table></div>` : '');
          applyBtn.classList.add('hidden');
        };
      });
      planBox.addEventListener('change', function (e) { if (e.target.name !== 'file') applyBtn.classList.add('hidden'); });
      function run(apply, btn) {
        var pl = plan();
        if (!file) { BT.toast('اختر الملف أولاً', { type: 'error' }); return; }
        if (!pl.company_id) { BT.toast('اختر الشركة', { type: 'error' }); return; }
        if (!pl.sheets.length) { BT.toast('لم تُختر أي ورقة للاستيراد', { type: 'error' }); return; }
        if (pl.claim_password !== undefined && pl.claim_password.length < 8) { BT.toast('كلمة المرور المبدئية 8 أحرف على الأقل', { type: 'error' }); return; }
        var fd = new FormData();
        fd.append('file', file, file.name || 'file');
        fd.append('plan', JSON.stringify(pl));
        btn.classList.add('is-loading'); btn.disabled = true;
        api.request('POST', '/imports/sheets', { form: fd, query: { apply: apply } }).then(function (r) {
          btn.classList.remove('is-loading'); btn.disabled = false;
          BT.render(res, result(r, false));
          applyBtn.classList.toggle('hidden', apply || r.errors.length > 0);
          if (apply) { BT.toast('تم الاستيراد'); file = null; input.value = ''; } // قد يحوي كلمات مرور: لا يبقى في الصفحة
          res.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, function (err) { btn.classList.remove('is-loading'); btn.disabled = false; BT.render(res, h`<div class="banner danger">${icon('circle-x', 16)}<div>${api.message(err)}</div></div>`); });
      }
      planBox.querySelector('[data-check]').onclick = function (e) { run(false, e.currentTarget); };
      applyBtn.onclick = function () {
        BT.confirm({ title: 'تنفيذ الاستيراد', message: 'تُضاف السجلات الجديدة وتُحدَّث الموجودة دفعة واحدة.', confirmText: 'تنفيذ', tone: 'success' }).then(function (r) { if (r.ok) run(true, applyBtn); });
      };
    }
  }
  function issue(x) {
    var params = Object.assign({}, x.params || {});
    if (params.field) params.field = api.t('import_field', params.field, null, params.field);
    return h`<tr><td>${x.sheet}</td><td class="num">${x.row || '—'}</td><td>${api.t('errors', x.code, params, x.code)}</td></tr>`;
  }
  function result(r, template) {
    var c = function (o) { return fmt.int(o.created) + ' جديد · ' + fmt.int(o.updated) + ' تحديث'; };
    return h`<div class="${r.errors.length ? 'banner danger' : r.applied ? 'banner success' : 'banner info'}">${icon(r.errors.length ? 'circle-x' : 'circle-check', 16)}<div>${r.errors.length ? h`<b>${fmt.int(r.errors.length)} خطأ</b>: صحّح الملف وافحصه من جديد` : r.applied ? 'تم الاستيراد' : 'الملف سليم وجاهز للتنفيذ'}</div></div>
      <div class="kpis mt-12">${BT.kpi({ label: 'السيارات', value: c(r.vehicles), dot: 'b' })}${BT.kpi({ label: 'الموظفون والسائقون', value: c(r.people), dot: 'g' })}${BT.kpi({ label: 'المستندات', value: fmt.int(r.documents), dot: 'p' })}${template ? BT.kpi({ label: 'الأرصدة الافتتاحية', value: fmt.int(r.opening_balances), dot: 'o' }) : ''}${BT.kpi({ label: 'تفعيل التطبيق', value: fmt.int(r.activated || 0), dot: 'g' })}${BT.kpi({ label: 'كلمات مرور مبدئية', value: fmt.int(r.claims || 0), dot: 'n' })}</div>
      ${r.errors.length ? h`<div class="section-t mt-12">الأخطاء</div><div class="table-wrap"><table class="t compact"><thead><tr><th>الورقة</th><th class="num">الصف</th><th>المشكلة</th></tr></thead><tbody>${r.errors.map(issue)}</tbody></table></div>` : ''}
      ${r.warnings.length ? h`<div class="section-t mt-12">تنبيهات (لا تمنع الاستيراد)</div><div class="table-wrap"><table class="t compact"><thead><tr><th>الورقة</th><th class="num">الصف</th><th>الملاحظة</th></tr></thead><tbody>${r.warnings.map(issue)}</tbody></table></div>` : ''}`;
  }

  /* ================= الإعدادات والصلاحيات ================= */
  var TABS = [
    ['users', 'المستخدمون', 'users.view'], ['roles', 'الأدوار والصلاحيات', 'roles.view'], ['companies', 'الشركات', 'companies.view'],
    ['branches', 'الفروع', null], ['system', 'إعدادات النظام', 'settings.view'], ['app', 'تطبيق السائق', 'settings.view'], ['statuses', 'الحالات الوظيفية', null], ['i18n', 'اللغات والترجمة', 'i18n.manage']
  ];
  BT.pages['settings'] = function (p, q) {
    A.setTitle('الإعدادات والصلاحيات');
    var v = A.view();
    var tabs = TABS.filter(function (t) { return !t[2] || api.can(t[2]); });
    var tab = tabs.some(function (t) { return t[0] === q.tab; }) ? q.tab : tabs[0][0];
    BT.render(v, h`${A.head('الإعدادات والصلاحيات', 'كل تغيير هنا يُسجَّل في سجل التدقيق باسمك', '')}${BT.tabs('set', tabs.map(function (t) { return [t[0], t[1]]; }), tab, 'tabs-line')}${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="set" class="${t[0] === tab ? 'active' : ''}"><div data-p="${t[0]}"></div></div>`; })}`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      var el = v.querySelector('[data-p="' + t + '"]');
      ({ users: usersPanel, roles: rolesPanel, companies: companiesPanel, branches: branchesPanel, system: systemPanel, app: appPanel, statuses: statusesPanel, i18n: i18nPanel })[t](el);
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/settings?tab=' + e.detail); });
    show(tab);
  };

  /* ---------- المستخدمون ---------- */
  var rolesCache = null;
  function loadRoles() { return api.can('roles.view') ? api.get('/roles').then(function (r) { rolesCache = r; return r; }) : Promise.resolve([]); }
  function usersPanel(el) {
    A.load(el, Promise.all([api.get('/users'), loadRoles()]), function (r) {
      var users = r[0], roles = r[1];
      var roleName = function (code) { var x = roles.find(function (y) { return y.code === code; }); return x ? api.name(x.name) : code; };
      setTimeout(function () {
        BT.table(el.querySelector('[data-t]'), {
          rows: users, pageSize: 25,
          search: { placeholder: 'الاسم أو اسم المستخدم…', text: function (u) { return u.full_name + ' ' + u.username + ' ' + (u.phone || ''); } },
          chips: { key: 'is_active', options: [{ v: 'true', t: 'نشط' }, { v: 'false', t: 'موقوف' }], match: function (u, c) { return String(u.is_active) === c; } },
          columns: [
            { key: 'full_name', label: 'المستخدم', render: function (u) { return BT.person(u.full_name, u.username); } },
            { key: 'roles', label: 'الأدوار', sort: false, render: function (u) { return u.is_superuser ? BT.pill('مدير النظام', 'p') : u.roles.length ? u.roles.map(function (c) { return BT.pill(roleName(c), 'b'); }) : raw('<span class="muted">—</span>'); } },
            { key: 'scope', label: 'النطاق', sort: false, render: function (u) { return u.all_companies ? 'كل الشركات' : u.company_ids.map(api.company).join('، ') || '—'; } },
            { key: 'mfa', label: 'التحقق بخطوتين', render: function (u) { return u.mfa_enabled ? BT.pill('مفعّل', 'g') : BT.pill('غير مفعّل', 'n'); } },
            { key: 'is_active', label: 'الحالة', render: function (u) { return h`${u.is_active ? BT.pill('نشط', 'g') : BT.pill('موقوف', 'r')}${u.must_change_password ? h` ${BT.pill('كلمة مرور مؤقتة', 'o')}` : ''}`; } }
          ],
          rowClick: function (u) { if (api.can('users.update')) userForm(u, roles, function () { usersPanel(el); }); },
          rowMenu: api.can('users.update') ? function (u) { return [{ label: 'تعديل', icon: 'pencil', onClick: function () { userForm(u, roles, function () { usersPanel(el); }); } }, { label: 'إعادة تعيين كلمة المرور', icon: 'key-round', onClick: function () { resetPassword(u, function () { usersPanel(el); }); } }]; } : null
        });
        var add = el.querySelector('[data-add]'); if (add) add.onclick = function () { userForm(null, roles, function () { usersPanel(el); }); };
      });
      return h`<div class="card"><div class="card-h"><div class="card-t">${fmt.int(users.length)} مستخدم</div>${api.can('users.create') ? h`<button type="button" class="btn btn-sm btn-primary ms-auto" data-add>${icon('user-plus', 14)} إضافة مستخدم</button>` : ''}</div><div data-t></div></div>`;
    }).catch(function () {});
  }
  function scopeFields(o) {
    return h`${BT.f.switch({ name: 'all_companies', label: 'كل الشركات (الحالية والمستقبلية)', checked: o.all_companies !== false })}
      <div data-cos class="${o.all_companies !== false ? 'hidden' : ''}"><div class="label mb-8">الشركات</div><div class="flex gap-12" style="flex-wrap:wrap">${api.companies.map(function (c) { return BT.f.check({ name: 'company_ids', value: c.id, label: api.name(c.name), checked: (o.company_ids || []).indexOf(c.id) > -1 }); })}</div></div>`;
  }
  function wireScope(d) { BT.on(d.el, 'change', '[name=all_companies]', function (e, x) { d.el.querySelector('[data-cos]').classList.toggle('hidden', x.checked); }); }
  function userForm(u, roles, after) {
    var editing = !!u;
    u = u || { roles: [], company_ids: [], all_companies: true, is_active: true };
    var custom = roles.filter(function (r) { return (!r.all_permissions || api.me.is_superuser) && (r.code !== 'maintenance_center' || u.roles.indexOf(r.code) > -1); }); // حساب المركز يُنشأ من صفحة المركز ليُربط به
    var d = A.formModal({
      title: editing ? 'تعديل مستخدم' : 'إضافة مستخدم', subtitle: editing ? u.username : null, icon: editing ? 'pencil' : 'user-plus', size: 'lg', done: editing ? 'تم الحفظ' : 'تمت إضافة المستخدم',
      body: h`<div class="form-grid">
        ${editing ? '' : BT.f.input({ name: 'username', label: 'اسم المستخدم', required: true, pattern: '[A-Za-z0-9._-]{3,50}', msg: 'حروف إنجليزية وأرقام و . _ - (3 على الأقل)' })}
        ${BT.f.input({ name: 'full_name', label: 'الاسم الكامل', required: true, value: u.full_name })}
        ${BT.f.input({ name: 'phone', label: 'الجوال', optional: true, value: u.phone, validate: 'phone' })}
        ${editing ? BT.f.switch({ name: 'is_active', label: 'الحساب نشط', checked: u.is_active }) : BT.f.input({ name: 'password', label: 'كلمة مرور مؤقتة', type: 'password', required: true, hint: 'يُطلب منه تغييرها عند أول دخول' })}
        <div class="full"><div class="label mb-8">الأدوار</div><div class="flex gap-12" style="flex-wrap:wrap">${custom.map(function (r) { return BT.f.check({ name: 'role_codes', value: r.code, label: api.name(r.name), checked: u.roles.indexOf(r.code) > -1 }); })}</div></div>
        <div class="full">${scopeFields(u)}</div></div>`,
      submit: function (v) {
        var roles_ = [].concat(v.role_codes || []).filter(Boolean), cos = [].concat(v.company_ids || []).filter(Boolean).map(Number);
        if (!v.all_companies && !cos.length) { BT.toast('اختر شركة واحدة على الأقل', { type: 'error' }); return Promise.reject(new Error('scope')); }
        var body = { full_name: v.full_name, phone: A.phoneE164(v.phone), role_codes: roles_, all_companies: !!v.all_companies, company_ids: v.all_companies ? [] : cos };
        if (!editing) return api.post('/users', Object.assign(body, { username: v.username, password: v.password }));
        return api.patch('/users/' + u.public_id, Object.assign(body, { version: u.version, is_active: !!v.is_active }));
      },
      after: after
    });
    wireScope(d);
  }
  function resetPassword(u, after) {
    A.formModal({
      title: 'إعادة تعيين كلمة المرور', subtitle: u.username, icon: 'key-round', size: 'sm', done: 'تم التعيين: سيُطلب منه تغييرها عند الدخول',
      body: h`<div class="form">${BT.f.input({ name: 'pw', label: 'كلمة مرور مؤقتة', type: 'password', required: true })}<div class="hint">تُنهى كل جلساته الحالية فوراً.</div></div>`,
      submit: function (v) { return api.post('/users/' + u.public_id + '/password', { new_password: v.pw }); },
      after: after
    });
  }

  /* ---------- الأدوار والصلاحيات ---------- */
  function rolesPanel(el) {
    A.load(el, Promise.all([loadRoles(), api.get('/permissions')]), function (r) {
      var roles = r[0], groups = r[1];
      A.delegate(el, 'click', '[data-role]', function (e, b) { var role = roles.find(function (x) { return x.code === b.getAttribute('data-role'); }); roleForm(role, groups, function () { rolesPanel(el); }); });
      setTimeout(function () {
        var add = el.querySelector('[data-add]'); if (add) add.onclick = function () { roleForm(null, groups, function () { rolesPanel(el); }); };
      });
      return h`<div class="card"><div class="card-h"><div class="card-t">${fmt.int(roles.length)} دور</div>${api.can('roles.manage') ? h`<button type="button" class="btn btn-sm btn-primary ms-auto" data-add>${icon('plus', 14)} دور جديد</button>` : ''}</div>
        <div class="list">${roles.map(function (x) { return h`<button type="button" class="li" data-role="${x.code}" style="width:100%;text-align:start"><span class="li-ic ${x.all_permissions ? 'p' : 'b'}">${icon(x.all_permissions ? 'shield' : 'shield-check', 16)}</span><div class="li-main"><div class="li-t">${api.name(x.name)} <span class="muted fs-sm ltr">${x.code}</span></div><div class="li-d">${x.all_permissions ? 'كل الصلاحيات' : fmt.int(x.permissions.length) + ' صلاحية'}${x.is_system ? ' · دور النظام (للقراءة)' : ''}</div></div>${icon('chevron-left', 14)}</button>`; })}</div></div>`;
    }).catch(function () {});
  }
  function roleForm(role, groups, after) {
    var editing = !!role, readonly = editing && (role.is_system || !api.can('roles.manage'));
    role = role || { name: {}, permissions: [] };
    var perms = h`${groups.map(function (g) {
      return h`<div class="mt-12"><div class="flex items-center gap-8 mb-8"><b>${g.label}</b>${readonly ? '' : h`<button type="button" class="btn btn-link fs-sm" data-all="${g.module}">الكل</button>`}</div><div class="flex gap-12" style="flex-wrap:wrap" data-mod="${g.module}">${g.permissions.map(function (p) {
        var on = role.all_permissions || role.permissions.indexOf(p.code) > -1;
        return readonly ? (on ? BT.pill(p.label, p.sensitive ? 'o' : 'b') : '') : BT.f.check({ name: 'perm', value: p.code, label: p.label + (p.sensitive ? ' ⚠' : ''), checked: on });
      })}</div></div>`;
    })}`;
    if (readonly) {
      return BT.drawer.open({ title: api.name(role.name), subtitle: role.is_system ? 'دور النظام: لا يُعدَّل، أنشئ دوراً جديداً بالصلاحيات التي تريدها' : '', icon: 'shield-check', size: 'lg', body: perms, buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }] });
    }
    var d = A.formModal({
      title: editing ? 'تعديل الدور' : 'دور جديد', subtitle: editing ? role.code : null, icon: 'shield-check', size: 'lg', done: 'تم حفظ الدور',
      body: h`<div class="form-grid">${editing ? '' : BT.f.input({ name: 'code', label: 'الرمز', required: true, pattern: '[a-z][a-z0-9_]{1,49}', msg: 'حروف إنجليزية صغيرة وأرقام و _' })}${BT.f.input({ name: 'name_ar', label: 'الاسم بالعربية', required: true, value: role.name.ar })}${BT.f.input({ name: 'name_en', label: 'الاسم بالإنجليزية', required: true, value: role.name.en })}</div>
        <div class="hint mt-8">⚠ صلاحية حساسة (تعديل مبالغ، اعتماد، رواتب): امنحها لمن يحتاجها فقط.</div>${perms}`,
      submit: function (v) {
        var body = { name: Object.assign({}, role.name, { ar: v.name_ar, en: v.name_en }), permissions: [].concat(v.perm || []).filter(Boolean) };
        return editing ? api.patch('/roles/' + role.code, Object.assign(body, { version: role.version })) : api.post('/roles', Object.assign(body, { code: v.code }));
      },
      after: after
    });
    BT.on(d.el, 'click', '[data-all]', function (e, b) { var boxes = BT.$$('[data-mod="' + b.getAttribute('data-all') + '"] input', d.el); var all = boxes.every(function (x) { return x.checked; }); boxes.forEach(function (x) { x.checked = !all; }); });
  }

  /* ---------- الشركات ---------- */
  function companiesPanel(el) {
    A.load(el, api.get('/companies'), function (rows) {
      setTimeout(function () {
        BT.table(el.querySelector('[data-t]'), {
          rows: rows, pageSize: 0,
          columns: [
            { key: 'name', label: 'الشركة', render: function (c) { return h`<b>${api.name(c.name)}</b>${c.trade_name ? h`<span class="sub">${api.name(c.trade_name)}</span>` : ''}`; } },
            { key: 'cr_number', label: 'السجل التجاري', render: function (c) { return c.cr_number ? h`<span class="num">${c.cr_number}</span>` : '—'; } },
            { key: 'license_expiry', label: 'انتهاء الترخيص', render: function (c) { if (!c.license_expiry) return '—'; var n = BT.date.daysLeft(c.license_expiry); return h`<span class="num">${fmt.date(c.license_expiry)}</span> ${n <= 60 ? BT.pill(fmt.daysLabel(n), n < 0 ? 'r' : 'o') : ''}`; } },
            { key: 'is_active', label: 'الحالة', render: function (c) { return c.is_active ? BT.pill('نشطة', 'g') : BT.pill('غير نشطة', 'n'); } }
          ],
          rowClick: function (c) { if (api.can('companies.update')) companyForm(c, function () { companiesPanel(el); }); }
        });
        var add = el.querySelector('[data-add]'); if (add) add.onclick = function () { companyForm(null, function () { companiesPanel(el); }); };
      });
      return h`<div class="card"><div class="card-h"><div class="card-t">الكيانات القانونية</div>${api.can('companies.create') ? h`<button type="button" class="btn btn-sm btn-primary ms-auto" data-add>${icon('plus', 14)} إضافة شركة</button>` : ''}</div><div class="hint mb-8">كل موظف وسيارة على أوراق شركة واحدة، وصلاحية كل مستخدم محصورة في شركاته.</div><div data-t></div></div>`;
    }).catch(function () {});
  }
  function companyForm(c, after) {
    var editing = !!c;
    c = c || { name: {} };
    A.formModal({
      title: editing ? 'تعديل الشركة' : 'إضافة شركة', icon: 'building-2', size: 'lg', done: 'تم الحفظ',
      body: h`<div class="form-grid">${BT.f.input({ name: 'name_ar', label: 'الاسم القانوني بالعربية', required: true, value: c.name.ar })}${BT.f.input({ name: 'name_en', label: 'الاسم القانوني بالإنجليزية', required: true, value: c.name.en })}
        ${BT.f.input({ name: 'trade_ar', label: 'الاسم التجاري بالعربية', optional: true, value: c.trade_name && c.trade_name.ar })}${BT.f.input({ name: 'trade_en', label: 'الاسم التجاري بالإنجليزية', optional: true, value: c.trade_name && c.trade_name.en })}
        ${BT.f.input({ name: 'cr_number', label: 'رقم السجل التجاري', optional: true, value: c.cr_number })}${BT.f.input({ name: 'license_number', label: 'رقم الترخيص', optional: true, value: c.license_number })}
        ${BT.f.date({ name: 'license_expiry', label: 'انتهاء الترخيص', optional: true, value: c.license_expiry })}${BT.f.input({ name: 'pam_file_number', label: 'رقم ملف الهيئة العامة للقوى العاملة', optional: true, value: c.pam_file_number })}
        ${BT.f.input({ name: 'phone', label: 'الهاتف', optional: true, value: c.phone })}${BT.f.input({ name: 'address', label: 'العنوان', optional: true, value: c.address })}
        ${BT.f.input({ name: 'contact_name', label: 'جهة الاتصال', optional: true, value: c.contact_name })}${BT.f.input({ name: 'contact_phone', label: 'هاتف جهة الاتصال', optional: true, value: c.contact_phone })}
        ${editing ? BT.f.switch({ name: 'is_active', label: 'الشركة نشطة', checked: c.is_active }) : ''}</div>`,
      submit: function (v) {
        var trade = v.trade_ar || v.trade_en ? { ar: v.trade_ar || v.trade_en, en: v.trade_en || v.trade_ar } : null;
        var body = { name: Object.assign({}, c.name, { ar: v.name_ar, en: v.name_en }), trade_name: trade };
        ['cr_number', 'license_number', 'license_expiry', 'pam_file_number', 'phone', 'address', 'contact_name', 'contact_phone'].forEach(function (k) { body[k] = v[k] || null; });
        if (!editing) return api.post('/companies', body).then(function (r) { return api.get('/companies/options').then(function (o) { api.companies = o; return r; }); });
        body.version = c.version; body.is_active = !!v.is_active;
        return api.patch('/companies/' + c.public_id, body).then(function (r) { return api.get('/companies/options').then(function (o) { api.companies = o; return r; }); });
      },
      after: after
    });
  }

  /* ---------- الفروع ---------- */
  function branchesPanel(el) {
    A.load(el, api.get('/branches'), function (rows) {
      api.branches = rows;
      var manage = api.can('branches.manage');
      A.delegate(el, 'click', '[data-br]', function (e, b) { var br = rows.find(function (x) { return String(x.public_id) === b.getAttribute('data-br'); }); branchForm(br, function () { branchesPanel(el); }); });
      setTimeout(function () {
        var add = el.querySelector('[data-add]'); if (add) add.onclick = function () { branchForm(null, function () { branchesPanel(el); }); };
      });
      return h`<div class="card"><div class="card-h"><div class="card-t">الفروع</div>${manage ? h`<button type="button" class="btn btn-sm btn-primary ms-auto" data-add>${icon('plus', 14)} إضافة فرع</button>` : ''}</div><div class="hint mb-8">لكل فرع خزينته، والخزينة مشتركة بين شركات الفرع.</div>
        <div class="list">${rows.map(function (b) { return h`<${raw(manage ? 'button type="button"' : 'div')} class="li" data-br="${b.public_id}" style="width:100%;text-align:start"><span class="li-ic">${icon('building-2', 16)}</span><div class="li-main"><div class="li-t">${api.name(b.name)} ${b.is_default ? BT.pill('الرئيسي', 'b') : ''}</div></div>${b.is_active ? BT.pill('نشط', 'g') : BT.pill('غير نشط', 'n')}</${raw(manage ? 'button' : 'div')}>`; })}</div></div>`;
    }).catch(function () {});
  }
  function branchForm(b, after) {
    var editing = !!b;
    b = b || { name: {} };
    A.formModal({
      title: editing ? 'تعديل الفرع' : 'إضافة فرع', icon: 'building-2', size: 'sm', done: 'تم الحفظ',
      body: h`<div class="form">${BT.f.input({ name: 'ar', label: 'الاسم بالعربية', required: true, value: b.name.ar })}${BT.f.input({ name: 'en', label: 'الاسم بالإنجليزية', required: true, value: b.name.en })}${editing && !b.is_default ? BT.f.switch({ name: 'is_active', label: 'الفرع نشط', checked: b.is_active }) : ''}</div>`,
      submit: function (v) {
        var name = Object.assign({}, b.name, { ar: v.ar, en: v.en });
        return editing ? api.patch('/branches/' + b.public_id, Object.assign({ version: b.version, name: name }, b.is_default ? {} : { is_active: !!v.is_active })) : api.post('/branches', { name: name });
      },
      after: after
    });
  }

  /* ---------- إعدادات النظام: كل قسم نموذج من قيمه الحالية ---------- */
  var ENUMS = {
    'payroll.deduction_cap_base': [{ v: 'gross', t: 'الراتب المستحق في الشهر' }, { v: 'basic', t: 'الراتب الأساسي' }],
    'payroll.absence_deduction': [{ v: 'none', t: 'لا يُخصم شيء' }, { v: 'daily_wage', t: 'أجر يوم لكل يوم (الأساسي ÷ أيام الشهر)' }],
    'finance.entry_approval': [{ v: 'manual', t: 'يدوي: القيود مسودات يعتمدها من له صلاحية الاعتماد' }, { v: 'auto', t: 'تلقائي: كل قيد يُعتمد فور إنشائه' }],
    'finance.fiscal_year_start_month': ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'].map(function (m, i) { return { v: i + 1, t: (i + 1) + ' · ' + m }; })
  };
  // أيام الأسبوع الكويتي: 0 السبت … 6 الجمعة (cash.treasury_deposit_weekdays)
  var WEEKDAYS = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة'];
  var DATES = { 'finance.books_start_date': true };
  var HINTS = {
    'finance.entry_approval': 'التحويل إلى «تلقائي» لا يعتمد المسودات الموجودة: اعتمدها من «القيود» ← «اعتماد المسودات». القيد اليدوي يتبع نفس الإعداد، والقيد العكسي يُعتمد فوراً دائماً.',
    'finance.fiscal_year_start_month': 'ميزان المراجعة وكشف الحساب يبدآن افتراضياً من أول السنة المالية حتى اليوم.',
    'finance.books_start_date': 'أول يوم للدفاتر في هذا النظام: الأرصدة الافتتاحية بتاريخ اليوم السابق له، ولا يُقبل قيد بتاريخ قبله.',
    'cash.treasury_deposit_limit': 'إذا بلغ رصيد خزينة فرع هذا المبلغ يصل تنبيه «أودع الخزينة في البنك» لمن يرى الخزينة، ويُغلق وحده عندما ينزل الرصيد تحته بإيداع أو أي حركة. 0 يوقف التنبيه.',
    'cash.treasury_deposit_weekdays': 'في هذه الأيام يصل صباحاً (7:00) تنبيه بإيداع الخزينة لكل فرع في خزينته مبلغ، ويُغلق نهاية اليوم أو عندما تفرغ الخزينة.'
  };
  function systemPanel(el) {
    A.load(el, Promise.all([api.get('/settings'), A.docTypes()]).then(function (r) { return r[0]; }), function (sections) {
      var canEdit = api.can('settings.update');
      setTimeout(function () {
        BT.$$('form[data-sec]', el).forEach(function (form) {
          form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (!BT.form.validate(form)) return;
            var name = form.getAttribute('data-sec'), cur = sections[name], vals = BT.form.values(form), value = {};
            Object.keys(cur.value).forEach(function (k) {
              var old = cur.value[k];
              if (name + '.' + k === 'cash.treasury_deposit_weekdays') value[k] = [].concat(vals[k] || []).map(Number);
              else if (ENUMS[name + '.' + k] && typeof old === 'number') value[k] = Number(vals[k]);
              else if (Array.isArray(old)) value[k] = String(vals[k] || '').split(/[,،]/).map(function (x) { return x.trim(); }).filter(Boolean);
              else if (typeof old === 'boolean') value[k] = !!vals[k];
              else if (typeof old === 'number') value[k] = vals[k] === '' ? old : Number(vals[k]);
              else if (/^-?\d+\.\d{3}$/.test(String(old))) value[k] = vals[k] === '' ? old : Number(vals[k]).toFixed(3); // مبلغ: 3 خانات
              else value[k] = vals[k] === '' ? null : String(vals[k]);
            });
            var b = form.querySelector('[type=submit]'); b.classList.add('is-loading');
            api.put('/settings/' + name, { version: cur.version, value: value }).then(function (r) { b.classList.remove('is-loading'); sections[name] = r; BT.toast('تم حفظ ' + api.t('settings', name)); if (name === 'branding') { A.brand = r.value.display_name; } if (name === 'driver_sign_in') { A._codes = null; A.codes = r.value.phone_codes; } }, function (err) { b.classList.remove('is-loading'); BT.toast(api.message(err), { type: 'error', timeout: 6000 }); });
          });
        });
      });
      return h`<div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(340px,1fr))">${Object.keys(sections).filter(function (name) { return name !== 'driver_app'; }).map(function (name) {
        var s = sections[name];
        return h`<form class="card" data-sec="${name}" novalidate><div class="card-h"><div class="card-t">${api.t('settings', name)}</div><span class="muted fs-sm">نسخة ${s.version}</span></div><div class="form">${Object.keys(s.value).map(function (k) {
          var val = s.value[k], label = api.t('settings', name + '.' + k), key = name + '.' + k, hint = HINTS[key];
          if (key === 'cash.treasury_deposit_weekdays') return h`<div class="field" data-weekdays><label>${label}</label><div class="flex gap-8" style="flex-wrap:wrap">${WEEKDAYS.map(function (d, i) { return h`<label class="check"><input type="checkbox" name="${k}" value="${i}"${val.indexOf(i) > -1 ? raw(' checked') : ''}${canEdit ? '' : raw(' disabled')}><span>${d}</span></label>`; })}</div><div class="hint">${hint}</div></div>`;
          if (ENUMS[key]) return BT.f.select({ name: k, label: label, value: val, placeholder: false, options: ENUMS[key], disabled: !canEdit, hint: hint });
          if (DATES[key]) return BT.f.input({ name: k, label: label, type: 'date', value: val || '', readonly: !canEdit, hint: hint });
          if (hint) return BT.f.input({ name: k, label: label, value: val == null ? '' : val, readonly: !canEdit, num: true, hint: hint });
          if (Array.isArray(val)) return BT.f.input({ name: k, label: label, value: val.join(', '), readonly: !canEdit, hint: 'قيم مفصولة بفواصل: ' + val.map(function (x) { return api.t('photo_position', x, null, '') || A.docTypeName(x); }).join('، ') });
          if (typeof val === 'boolean') return BT.f.switch({ name: k, label: label, checked: val });
          if (ENUMS[name + '.' + k]) return BT.f.select({ name: k, label: label, value: val, placeholder: false, options: ENUMS[name + '.' + k] });
          if (typeof val === 'number') return BT.f.input({ name: k, label: label, value: val, num: true, readonly: !canEdit });
          return BT.f.input({ name: k, label: label, value: val == null ? '' : val, readonly: !canEdit, num: /^\d+\.\d{3}$/.test(String(val)) });
        })}${canEdit ? h`<div><button type="submit" class="btn btn-sm btn-primary">${icon('check', 14)} حفظ</button></div>` : ''}</div></form>`;
      })}</div>`;
    }).catch(function () {});
  }

  /* ---------- تطبيق السائق: الشاشات تُظهر وتُخفى مثل الصلاحيات، وشاشة البداية صورة يصممها المكتب ---------- */
  var SCREEN_EFFECT = {
    daily_report: 'لا يرسل السائق تقريره اليومي ولا الكاش المحصّل من التطبيق: يسجّله المكتب',
    cash: 'يختفي تبويب الكاش: رصيده وإيصالات تسليم الكاش',
    maintenance: 'لا يطلب السائق صيانة من التطبيق، ولا يرى «سيارتك جاهزة»',
    accidents: 'لا يبلّغ السائق عن حادث ولا يرسل محضر الشرطة: يسجّله المكتب',
    fines: 'لا يرى السائق مخالفاته وأقساط خصمها',
    statement: 'لا يرسل السائق كشف منصته: يُدخله المكتب، وإلا توقفت رواتب المنصات التي تحتاج الأيام الصالحة',
    payslips: 'لا يرى السائق كشف راتبه في التطبيق',
    schemes: 'لا يرى السائق شروط أنظمة الدفع ولا يطلب تغيير نظامه: يغيّره المكتب',
    fuel: 'لا يسجّل السائق البنزين الذي دفعه من الكاش: لا يُخصم من رصيده إلا بتسوية يدوية'
  };
  function appPanel(el) {
    A.load(el, Promise.all([api.get('/settings'), api.get('/app-screens')]), function (r) {
      var cur = r[0].driver_app, reg = r[1], v = cur.value, canEdit = api.can('settings.update');
      var image = v.splash_image, preview = null;
      setTimeout(function () {
        var form = el.querySelector('form[data-app]'), box = form.querySelector('[data-preview]');
        function draw() {
          var vals = BT.form.values(form), color = /^#[0-9A-Fa-f]{6}$/.test(vals.splash_color || '') ? vals.splash_color : '#FFFFFF';
          var src = preview || (image && v.splash_enabled && image === v.splash_image ? '/api/v1/driver/splash/' + image : null);
          BT.render(box, h`<div class="flex gap-12 mt-8" style="align-items:flex-end;flex-wrap:wrap"><div data-phone style="width:150px;height:300px;border-radius:22px;border:6px solid var(--text);background:${color};display:flex;align-items:center;justify-content:center;overflow:hidden">${src ? h`<img src="${src}" alt="" style="max-width:100%;max-height:100%;object-fit:contain">` : h`<span class="muted fs-sm" style="padding:10px;text-align:center">${image ? 'الصورة محفوظة: تظهر هنا عند التفعيل' : 'لا توجد صورة بعد'}</span>`}</div><div class="muted fs-sm" style="max-width:320px">معاينة على هاتف طولي. على الشاشات الأعرض أو الأطول يملأ لون الخلفية ما حول الصورة.</div></div>`);
        }
        draw();
        form.addEventListener('input', draw);
        var file = form.querySelector('input[name=splash_file]');
        if (file) file.addEventListener('change', function () {
          var f = file.files[0]; if (!f) return;
          if (!/^image\/(png|jpeg)$/.test(f.type)) { BT.toast('الصورة JPEG أو PNG', { type: 'error' }); file.value = ''; return; }
          if (f.size > 2000000) { BT.toast('الصورة أكبر من 2 ميجابايت', { type: 'error' }); file.value = ''; return; }
          preview = URL.createObjectURL(f); draw();
          api.upload(f).then(function (x) { image = x.sha256; BT.toast('رُفعت الصورة: احفظ لتصل للتطبيق'); }, function (err) { preview = null; draw(); BT.toast(api.message(err), { type: 'error', timeout: 6000 }); });
        });
        form.addEventListener('submit', function (e) {
          e.preventDefault();
          if (!BT.form.validate(form)) return;
          var vals = BT.form.values(form), shown = [].concat(vals.screen || []).filter(Boolean);
          var value = {
            hidden_screens: reg.screens.filter(function (k) { return shown.indexOf(k) < 0; }),
            splash_enabled: !!vals.splash_enabled, splash_image: image || null,
            splash_color: vals.splash_color, splash_seconds: Math.round(Number(vals.splash_seconds || 2))
          };
          if (value.splash_enabled && !value.splash_image) { BT.toast('اختر صورة شاشة البداية أولاً', { type: 'error' }); return; }
          var hiding = value.hidden_screens.filter(function (k) { return v.hidden_screens.indexOf(k) < 0; });
          var go = function () {
            var b = form.querySelector('[type=submit]'); b.classList.add('is-loading');
            return api.put('/settings/driver_app', { version: cur.version, value: value }).then(function () { BT.toast('حُفظ: يصل للسائقين مع اتصال التطبيق التالي'); appPanel(el); }, function (err) { b.classList.remove('is-loading'); BT.toast(api.message(err), { type: 'error', timeout: 6000 }); });
          };
          if (!hiding.length) return go();
          A.confirmRun({ title: 'إخفاء ' + hiding.length + ' شاشة', icon: 'eye-off', tone: 'danger', confirmText: 'إخفاء', done: false,
            message: hiding.map(function (k) { return api.t('app_screen', k) + ': ' + (SCREEN_EFFECT[k] || ''); }).join('\n'), run: go });
        });
      });
      return h`<form class="card" data-app novalidate>
        <div class="card-h"><div class="card-t">شاشات التطبيق</div><span class="muted fs-sm">نسخة ${cur.version}</span></div>
        <div class="card-b form">
          <div class="hint">المؤشَّر يظهر للسائق. المخفي يختفي من التطبيق ويرفضه الخادم أيضاً (فلا تصل إليه نسخة قديمة أو اتصال مباشر)، وبياناته لا تُحذف: تعود كما هي عند إظهاره. يصل التغيير للسائق مع اتصال التطبيق التالي، دون تحديثه.</div>
          <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px">${reg.screens.map(function (k) {
            return h`<div data-screen="${k}">${canEdit ? BT.f.check({ name: 'screen', value: k, label: api.t('app_screen', k), checked: v.hidden_screens.indexOf(k) < 0 }) : BT.pill(api.t('app_screen', k), v.hidden_screens.indexOf(k) < 0 ? 'g' : 'n')}<div class="muted fs-sm" style="margin-inline-start:28px;margin-top:2px">${SCREEN_EFFECT[k] || ''}</div></div>`;
          })}</div>
          <div><b class="fs-sm">لا تُخفى (التطبيق لا يعمل بدونها)</b><div class="flex gap-8 mt-8" style="flex-wrap:wrap">${reg.locked.map(function (k) { return BT.pill(api.t('app_screen', k), 'n'); })}</div></div>
        </div>
        <div class="card-h"><div class="card-t">شاشة البداية</div></div>
        <div class="card-b form">
          ${canEdit ? BT.f.switch({ name: 'splash_enabled', label: 'تظهر عند فتح التطبيق', checked: v.splash_enabled }) : BT.pill(v.splash_enabled ? 'مفعّلة' : 'غير مفعّلة', v.splash_enabled ? 'g' : 'n')}
          <div class="hint">صمّمها صورة واحدة بالشكل الذي تريده (شعار، نص، ألوان)، طولية مثل 1080×1920، JPEG أو PNG حتى 2 ميجابايت. تصل للسائق مع اتصال التطبيق التالي وتظهر من الفتح الذي بعده، دون تحديث التطبيق.</div>
          <div class="form-grid">
            ${canEdit ? BT.f.upload({ name: 'splash_file', label: 'الصورة', accept: 'image/png,image/jpeg', accept_label: 'JPEG أو PNG · حتى 2MB' }) : ''}
            <div>${BT.f.input({ name: 'splash_color', label: 'لون الخلفية حول الصورة', value: v.splash_color, pattern: '#[0-9A-Fa-f]{6}', msg: 'مثل #0A6CFF', readonly: !canEdit })}${BT.f.input({ name: 'splash_seconds', label: 'مدة الظهور (ثانية، 1 إلى 5)', value: v.splash_seconds, num: true, readonly: !canEdit })}</div>
          </div>
          <div data-preview></div>
          ${canEdit ? h`<div><button type="submit" class="btn btn-primary">${icon('check', 15)} حفظ</button></div>` : ''}
        </div></form>`;
    }).catch(function () {});
  }

  /* ---------- الحالات الوظيفية ---------- */
  function statusesPanel(el) {
    A.load(el, api.get('/employment-statuses'), function (rows) {
      var canEdit = api.can('settings.update');
      A.delegate(el, 'click', '[data-toggle]', function (e, b) { var code = b.getAttribute('data-toggle'), s = rows.find(function (x) { return x.code === code; }); api.patch('/employment-statuses/' + code, { is_active: !s.is_active }).then(function () { BT.toast('تم التحديث'); statusesPanel(el); }, api.fail).catch(function () {}); });
      setTimeout(function () {
        var add = el.querySelector('[data-add]');
        if (add) add.onclick = function () {
          A.formModal({ title: 'حالة وظيفية جديدة', icon: 'repeat', size: 'sm', done: 'تمت الإضافة', after: function () { statusesPanel(el); },
            body: h`<div class="form">${BT.f.input({ name: 'code', label: 'الرمز', required: true, pattern: '[a-z][a-z0-9_]{1,30}', msg: 'حروف إنجليزية صغيرة' })}${BT.f.input({ name: 'ar', label: 'الاسم بالعربية', required: true })}${BT.f.input({ name: 'en', label: 'الاسم بالإنجليزية', required: true })}${BT.f.radios({ name: 'kind', label: 'النوع', required: true, value: 'working', options: [{ v: 'working', t: 'على رأس العمل' }, { v: 'paused', t: 'متوقف مؤقتاً' }, { v: 'terminal', t: 'تنهي الخدمة', d: 'تلغي وصول التطبيق' }] })}</div>`,
            submit: function (v) { return api.post('/employment-statuses', { code: v.code, name: { ar: v.ar, en: v.en }, is_working: v.kind === 'working', is_terminal: v.kind === 'terminal' }); } });
        };
      });
      return h`<div class="card"><div class="card-h"><div class="card-t">الحالات الوظيفية</div>${canEdit ? h`<button type="button" class="btn btn-sm btn-primary ms-auto" data-add>${icon('plus', 14)} حالة جديدة</button>` : ''}</div>
        <div class="table-wrap"><table class="t compact"><thead><tr><th>الحالة</th><th>الرمز</th><th>النوع</th><th>نشطة</th><th></th></tr></thead><tbody>${rows.map(function (s) { return h`<tr><td>${api.name(s.name)}</td><td class="ltr">${s.code}</td><td>${s.is_terminal ? BT.pill('تنهي الخدمة', 'r') : s.is_working ? BT.pill('على رأس العمل', 'g') : BT.pill('متوقف', 'o')}</td><td>${s.is_active ? 'نعم' : 'لا'}</td><td class="actions">${canEdit ? h`<button type="button" class="btn btn-sm btn-ghost" data-toggle="${s.code}">${s.is_active ? 'إيقاف' : 'تفعيل'}</button>` : ''}</td></tr>`; })}</tbody></table></div></div>`;
    }).catch(function () {});
  }

  /* ---------- اللغات والترجمة ---------- */
  function i18nPanel(el) {
    A.load(el, api.get('/i18n/admin/languages'), function (langs) {
      var lang = (langs.find(function (l) { return l.is_default; }) || langs[0] || {}).code;
      setTimeout(function () { var sel = el.querySelector('[data-lang]'); sel.onchange = function () { entries(sel.value); }; entries(lang); });
      function entries(code) {
        var box = el.querySelector('[data-entries]');
        A.load(box, api.get('/i18n/admin/entries/' + code), function (rows) {
          setTimeout(function () {
            BT.table(box.querySelector('[data-t]'), {
              rows: rows, pageSize: 25,
              search: { placeholder: 'ابحث في النصوص أو المفاتيح…', text: function (r) { return r.namespace + '.' + r.key + ' ' + r.reference + ' ' + (r.base || '') + ' ' + (r.override || ''); } },
              chips: { key: 'namespace', options: Array.from(new Set(rows.map(function (r) { return r.namespace; }))).map(function (n) { return { v: n, t: api.t('modules', n, null, n) }; }) },
              columns: [
                { key: 'key', label: 'المفتاح', render: function (r) { return h`<span class="ltr fs-sm muted">${r.namespace}.${r.key}</span>`; } },
                { key: 'reference', label: 'النص المرجعي', render: function (r) { return h`<span style="white-space:normal">${r.reference}</span>`; } },
                { key: 'value', label: 'الترجمة', sort: false, render: function (r) { return h`<span style="white-space:normal">${r.override || r.base || raw('<span class="t-danger">بلا ترجمة</span>')}</span>${r.override ? h` ${BT.pill('معدّل', 'b')}` : ''}`; } }
              ],
              rowClick: function (r) {
                A.formModal({ title: 'تعديل نص', subtitle: r.namespace + '.' + r.key, icon: 'languages', done: 'تم الحفظ', after: function () { entries(code); },
                  body: h`<div class="form">${BT.kv([['المرجع', r.reference], ['الأصلي', r.base || '—']])}${BT.f.textarea({ name: 'value', label: 'النص المعدّل', required: true, value: r.override || r.base || '', rows: 3, hint: 'احتفظ بالمتغيرات بين { } كما هي' })}${r.override ? h`<button type="button" class="btn btn-sm btn-ghost" data-reset>${icon('rotate-ccw', 13)} إرجاع للأصلي</button>` : ''}</div>`,
                  onOpen: function (d) { var rs = d.el.querySelector('[data-reset]'); if (rs) rs.onclick = function () { api.del('/i18n/admin/overrides/' + code + '/' + r.namespace + '/' + r.key).then(function () { d.close(); BT.toast('أُرجع النص الأصلي'); entries(code); }, api.fail).catch(function () {}); }; },
                  submit: function (v) { return api.put('/i18n/admin/overrides/' + code, { items: [{ namespace: r.namespace, key: r.key, value: v.value }] }); } });
              }
            });
          });
          return h`<div data-t></div>`;
        }).catch(function () {});
      }
      return h`<div class="card"><div class="card-h"><div class="card-t">نصوص النظام</div><select class="select ms-auto" data-lang style="width:auto">${langs.map(function (l) { return h`<option value="${l.code}"${l.code === lang ? raw(' selected') : ''}>${l.name_native} (${l.code})${l.is_active ? '' : ' — غير مفعّلة'}</option>`; })}</select></div><div class="hint mb-8">تعديل نصوص الرسائل والتنبيهات ورسائل واتساب لكل لغة، دون تغيير الكود.</div><div data-entries></div></div>`;
    }).catch(function () {});
  }

  /* ================= سجل التدقيق ================= */
  /* البحث بمن قام بالإجراء ونوع السجل والفترة (أيام الكويت) والإجراء، والتصدير Excel أو CSV بنفس الفلاتر (FR-AUD-03) */
  function entity(code) { var t = api.t('audit_entity', code); return t && t.indexOf('audit_entity.') !== 0 ? t : code; }
  function actor(e) { return e.actor_type === 'user' ? (e.actor_name || '#' + e.actor_user_id) : api.t('audit_actor', e.actor_type); }
  A.auditActor = actor;
  /* one event in full: who, from where, with what comment, and the record before and after (also from a record's own file) */
  A.auditEvent = function (e) {
    var pre = function (o) { return o == null ? raw('<span class="muted">—</span>') : h`<pre class="ltr fs-sm" style="white-space:pre-wrap;word-break:break-word;background:var(--surface-2);padding:10px;border-radius:8px;max-height:320px;overflow:auto">${JSON.stringify(o, null, 2)}</pre>`; };
    return BT.drawer.open({ title: e.action, subtitle: fmt.dt(e.occurred_at), icon: 'shield-check', size: 'lg', buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }],
      body: h`${BT.kv([['السجل', h`${entity(e.entity_type)} <span class="ltr fs-sm">${e.entity_id || ''}</span>`], ['بواسطة', actor(e)], ['التعليق', e.comment || '—'], ['العنوان', e.ip || '—'], ['الجهاز', e.device ? h`<span class="ltr fs-sm" data-device>${e.device}</span>` : '—'], ['رقم الطلب', e.request_id ? h`<span class="ltr fs-sm">${e.request_id}</span>` : '—']])}<div class="section-t mt-16">قبل</div>${pre(e.before)}<div class="section-t mt-16">بعد</div>${pre(e.after)}` });
  };

  BT.pages['audit'] = function () {
    A.setTitle('سجل التدقيق');
    var v = A.view(), filters = { actor_id: '', entity_type: '', action: '', date_from: '', date_to: '' }, cursors = [null];
    function query() { var q = {}; Object.keys(filters).forEach(function (k) { if (filters[k]) q[k] = filters[k]; }); return q; }
    BT.render(v, h`${A.head('سجل التدقيق', 'من غيّر ماذا ومتى ومن أي عنوان: لا يُعدَّل ولا يُحذف', api.can('audit.export') ? h`<div class="btn-group">
        <button type="button" class="btn btn-outline" data-audit-export="xlsx">${icon('file-spreadsheet', 16)} Excel</button>
        <button type="button" class="btn btn-ghost" data-audit-export="csv">CSV</button></div>` : '')}
      <div class="card"><div id="audit-table"></div></div>`);
    A.load(document.getElementById('audit-table'), api.get('/audit/users'), function () { return ''; }).then(function (users) {
      var el = document.getElementById('audit-table');
      var types = Object.keys(api.cat.audit_entity || {}).sort(function (a, b) { return entity(a).localeCompare(entity(b), 'ar'); });
      var t = BT.table(el, {
        fetch: function (s) {
          var page = Math.round(s.offset / (s.limit - 1));
          if (page === 0) cursors = [null];
          return api.get('/audit', Object.assign(query(), { before_id: cursors[page], limit: s.limit })).then(function (rows) {
            if (rows.length >= s.limit) cursors[page + 1] = rows[s.limit - 2].id;
            return rows;
          });
        },
        tools: h`<select class="select" data-f="actor_id" aria-label="بواسطة"><option value="">كل المستخدمين</option>${users.map(function (u) { return h`<option value="${u.id}">${u.name}</option>`; })}</select>
          <select class="select" data-f="entity_type" aria-label="نوع السجل"><option value="">كل السجلات</option>${types.map(function (c) { return h`<option value="${c}">${entity(c)}</option>`; })}</select>
          <input class="input" type="date" data-f="date_from" aria-label="من" title="من">
          <input class="input" type="date" data-f="date_to" aria-label="إلى" title="إلى">
          <input class="input ltr" data-f="action" placeholder="الإجراء (employee.updated…)" aria-label="الإجراء">`,
        columns: [
          { key: 'occurred_at', label: 'الوقت', render: function (e) { return fmt.dt(e.occurred_at); } },
          { key: 'actor', label: 'بواسطة', render: function (e) { return e.actor_type === 'user' ? actor(e) : BT.pill(actor(e), 'n'); } },
          { key: 'action', label: 'الإجراء', render: function (e) { return h`<span class="ltr fs-sm">${e.action}</span>`; } },
          { key: 'entity', label: 'السجل', render: function (e) { return h`${entity(e.entity_type)}${e.entity_id ? h`<span class="sub ltr">${String(e.entity_id).slice(0, 8)}</span>` : ''}`; } },
          { key: 'comment', label: 'التعليق', render: function (e) { return e.comment ? h`<span class="fs-sm" data-comment>${e.comment.length > 60 ? e.comment.slice(0, 60) + '…' : e.comment}</span>` : raw('<span class="muted">—</span>'); } },
          { key: 'company', label: 'الشركة', render: function (e) { return e.company_id ? api.company(e.company_id) : '—'; } },
          { key: 'ip', label: 'العنوان', render: function (e) { return e.ip ? h`<span class="num ltr fs-sm">${e.ip}</span>` : '—'; } }
        ],
        rowClick: function (e) { A.auditEvent(e); },
        empty: { icon: 'shield-check', title: 'لا توجد أحداث مطابقة' }
      });
      BT.on(el, 'change', '[data-f]', function (e, inp) {
        var from = el.querySelector('[data-f=date_from]').value, to = el.querySelector('[data-f=date_to]').value;
        if (from && to && to < from) { BT.toast('تاريخ النهاية قبل البداية', { type: 'error' }); return; }
        filters[inp.getAttribute('data-f')] = inp.value.trim(); cursors = [null]; t.refresh();
      });
      BT.on(v, 'click', '[data-audit-export]', function (e, b) {
        var ext = b.getAttribute('data-audit-export');
        A.downloadFile('/audit/export', Object.assign(query(), { format: ext }), 'audit' + (filters.date_from ? '-' + filters.date_from : '') + (filters.date_to ? '-' + filters.date_to : '') + '.' + ext);
      });
    }).catch(function () {});
  };
})();
