/* =====================================================================
   app/pages/print-designer.js — الإعدادات › قوالب الطباعة: شكل كل ما يُطبع
   (الهيدر، الفوتر، العلامة المائية، الهوامش والخط والألوان). قالب افتراضي
   وقالب خاص لكل شركة تريد شكلها، ومعاينة حية بتقرير وإيصال نموذجيين.
   كل نشر نسخة جديدة، و«رجوع للإعداد السابق» ينشر ما قبلها.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  /* the fields: [path, label, type, extra] — type bool | text | int | float | color | select | lines | image */
  var SECTIONS = [
    ['header', 'الهيدر', [
      ['header.show_logo', 'إظهار الشعار', 'bool'], ['header.logo', 'الشعار (PNG أو JPEG حتى 1 ميجا)', 'image'],
      ['header.logo_position', 'مكان الشعار', 'select', [['start', 'يمين'], ['center', 'وسط'], ['end', 'يسار']]],
      ['header.show_name_ar', 'إظهار الاسم بالعربي', 'bool'], ['header.name_ar', 'الاسم بالعربي (فارغ: اسم الشركة)', 'text'],
      ['header.show_name_en', 'إظهار الاسم بالإنجليزي', 'bool'], ['header.name_en', 'الاسم بالإنجليزي (فارغ: اسم الشركة)', 'text'],
      ['header.lines', 'سطور تحت الاسم (سطر لكل بيان، حتى 4)', 'lines'],
      ['header.show_title', 'إظهار عنوان التقرير', 'bool'], ['header.show_filters', 'إظهار الفلاتر والفترة', 'bool'],
      ['header.title_align', 'مكان العنوان', 'select', [['start', 'يمين'], ['center', 'وسط'], ['end', 'يسار']]]
    ]],
    ['footer', 'الفوتر', [
      ['footer.text', 'نص الفوتر (في كل صفحة)', 'text'], ['footer.show_printed_at', 'تاريخ ووقت الطباعة', 'bool'],
      ['footer.show_printed_by', 'اسم من طبع', 'bool'], ['footer.note', 'نص إقرار فوق التوقيعات', 'text'],
      ['footer.signatures', 'سطور التوقيع (سطر لكل توقيع، حتى 4)', 'lines']
    ]],
    ['watermark', 'العلامة المائية', [
      ['watermark.mode', 'تظهر', 'select', [['off', 'لا تظهر'], ['always', 'دائماً'], ['drafts', 'على المسودات وغير المعتمد فقط']]],
      ['watermark.kind', 'النوع', 'select', [['text', 'نص'], ['image', 'صورة']]], ['watermark.text', 'النص', 'text'],
      ['watermark.image', 'الصورة', 'image'], ['watermark.opacity', 'الشفافية (0.02 – 0.5)', 'float', { min: 0.02, max: 0.5, step: 0.01 }],
      ['watermark.angle', 'الزاوية (−90 – 90)', 'int', { min: -90, max: 90 }], ['watermark.size', 'الحجم', 'int', { min: 24, max: 240 }]
    ]],
    ['page', 'الصفحة', [
      ['page.margin_top', 'الهامش العلوي (مم)', 'int', { min: 5, max: 40 }], ['page.margin_bottom', 'الهامش السفلي (مم)', 'int', { min: 5, max: 40 }],
      ['page.margin_start', 'الهامش الأيمن (مم)', 'int', { min: 5, max: 40 }], ['page.margin_end', 'الهامش الأيسر (مم)', 'int', { min: 5, max: 40 }],
      ['page.font_size', 'حجم الخط (نقطة)', 'float', { min: 8, max: 16, step: 0.5 }], ['page.accent', 'لون التمييز', 'color'],
      ['page.text_color', 'لون النص', 'color'], ['page.header_rule', 'خط تحت الهيدر', 'bool'], ['page.zebra', 'صفوف الجداول بالتناوب', 'bool']
    ]]
  ];

  function get(o, path) { return path.split('.').reduce(function (x, k) { return x == null ? x : x[k]; }, o); }
  function set(o, path, v) { var ks = path.split('.'), x = o; ks.slice(0, -1).forEach(function (k) { x = x[k] = x[k] || {}; }); x[ks[ks.length - 1]] = v; }
  function clone(o) { return JSON.parse(JSON.stringify(o)); }

  function field(f, t, edit) {
    var path = f[0], label = f[1], type = f[2], extra = f[3] || {}, v = get(t, path), id = 'pt-' + path.replace('.', '-'), dis = edit ? '' : raw(' disabled');
    if (type === 'bool') return h`<label class="check pt-f" for="${id}"><input type="checkbox" id="${id}" data-k="${path}" data-t="bool"${v ? raw(' checked') : ''}${dis}> ${label}</label>`;
    if (type === 'select') return h`<div class="field pt-f"><label for="${id}">${label}</label><select class="select" id="${id}" data-k="${path}" data-t="text"${dis}>${extra.map(function (o) { return h`<option value="${o[0]}"${o[0] === v ? raw(' selected') : ''}>${o[1]}</option>`; })}</select></div>`;
    if (type === 'lines') return h`<div class="field pt-f full"><label for="${id}">${label}</label><textarea class="textarea" id="${id}" rows="3" data-k="${path}" data-t="lines"${dis}>${(v || []).join('\n')}</textarea></div>`;
    if (type === 'image') return h`<div class="field pt-f full"><label for="${id}">${label}</label><div class="flex gap-8" style="align-items:center"><input type="hidden" data-k="${path}" data-t="sha" value="${v || ''}"><span class="muted fs-sm" data-img-state="${path}">${v ? 'صورة مرفوعة' : 'لا توجد صورة'}</span>${edit ? h`<input type="file" accept="image/png,image/jpeg" id="${id}" data-upload="${path}" aria-label="${label}"> <button type="button" class="btn btn-sm btn-ghost" data-img-clear="${path}">إزالة</button>` : ''}</div></div>`;
    var num = type === 'int' || type === 'float';
    return h`<div class="field pt-f${type === 'text' ? ' full' : ''}"><label for="${id}">${label}</label><input class="input" id="${id}" type="${num ? 'number' : type === 'color' ? 'color' : 'text'}" data-k="${path}" data-t="${type}" value="${v == null ? '' : v}"${extra.min != null ? raw(' min="' + extra.min + '"') : ''}${extra.max != null ? raw(' max="' + extra.max + '"') : ''}${extra.step ? raw(' step="' + extra.step + '"') : ''}${dis}></div>`;
  }
  function read(root, base) {
    var t = clone(base);
    BT.$$('[data-k]', root).forEach(function (el) {
      var k = el.getAttribute('data-k'), ty = el.getAttribute('data-t'), v;
      if (ty === 'bool') v = el.checked;
      else if (ty === 'int') v = parseInt(el.value, 10);
      else if (ty === 'float') v = parseFloat(el.value);
      else if (ty === 'lines') v = el.value.split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
      else if (ty === 'sha') v = el.value || null;
      else v = el.value;
      if ((ty === 'int' || ty === 'float') && isNaN(v)) v = get(base, k);
      set(t, k, v);
    });
    return t;
  }

  var SAMPLE_ROWS = [{ a: 'سائق نموذجي ١', b: '12/3456', c: 24, d: '38.500' }, { a: 'سائق نموذجي ٢', b: '45/1200', c: 19, d: '27.250' }, { a: 'سائق نموذجي ٣', b: '7/88001', c: 31, d: '44.000' }];
  function sampleDoc(kind) {
    if (kind === 'receipt') {
      return { title: 'إيصال استلام نقدية رقم 1024', meta: 'الفرع الرئيسي · ' + fmt.dt(new Date().toISOString()), signatures: null,
        body: h`<table class="pd-kv"><tbody><tr><th>استلمنا من السائق</th><td>سائق نموذجي</td></tr><tr><th>الرقم المدني</th><td class="num">290010100000</td></tr><tr><th>رقم لوحة السيارة</th><td>12/3456</td></tr><tr><th>المبلغ</th><td><span class="pd-amount num">50.000</span> ${BT.config.currency}</td></tr></tbody></table>`, draft: true };
    }
    var cols = [{ key: 'a', label: 'السائق' }, { key: 'b', label: 'اللوحة' }, { key: 'c', label: 'الطلبات', num: true }, { key: 'd', label: 'الكاش', num: true }];
    return { title: 'تقرير العمل اليومي (نموذج)', meta: 'من 2026-10-01 إلى 2026-10-07 · كل الفروع', draft: true,
      body: h`<h2>حسب السائق</h2>${BT.printTable(cols, SAMPLE_ROWS, function (c, r) { return r[c.key]; })}` };
  }

  A.printTemplatesPanel = function (el) {
    var edit = api.can('settings.update'), state = null, target = 'default', kind = 'report', images = {}, identities = {};
    var companies = (api.companies || []).filter(function (c) { return c.is_active; });
    function load() { return api.get('/print-templates').then(function (m) { state = m; draw(); }, function (err) { BT.render(el, A.errorBox(err)); }); }
    function current() { return target === 'default' ? state.default : (state.companies[target] || null); }
    function identity() {
      if (target === 'default') return Promise.resolve(Object.assign({}, state.options.sample));
      if (identities[target]) return Promise.resolve(identities[target]);
      return api.get('/print/layout', { company_id: target }).then(function (l) { identities[target] = l.identity; return l.identity; });
    }
    function imgUrl(sha) { if (!sha) return null; return images[sha] || '/api/v1/print-templates/images/' + sha; }
    function preview() {
      var box = el.querySelector('[data-pt-preview]'), form = el.querySelector('[data-pt-form]');
      if (!box) return;
      var t = form ? read(form, current() || state.default) : state.default;
      identity().then(function (id) {
        var ident = Object.assign({}, id);
        if (t.header.name_ar) ident.company = t.header.name_ar;
        if (t.header.name_en) ident.company_en = t.header.name_en;
        var layout = { company_id: target === 'default' ? null : Number(target), template: t, identity: ident, images: { logo: imgUrl(t.header.logo), watermark: imgUrl(t.watermark.image) } };
        BT.render(box, h`<div class="pd-page">${BT.printSheet(layout, sampleDoc(kind), { screen: true })}</div>`);
      });
    }
    function draw() {
      var t = current(), own = target === 'default' || !!t;
      var who = target === 'default' ? 'القالب الافتراضي (للمجموعة ولكل شركة بلا قالب خاص)' : (own ? 'قالب خاص بهذه الشركة' : 'هذه الشركة تطبع بالقالب الافتراضي');
      BT.render(el, h`<div class="card mb-12"><div class="toolbar" style="margin:0">
          <div class="field"><label for="pt-target">القالب</label><select class="select" id="pt-target" data-pt-target><option value="default">الافتراضي</option>${companies.map(function (c) { return h`<option value="${c.id}"${String(c.id) === String(target) ? raw(' selected') : ''}>${api.name(c.name)}${state.companies[c.id] ? ' — خاص' : ''}</option>`; })}</select></div>
          <span class="muted fs-sm" style="align-self:center" data-pt-who>${who}</span>
          <div class="ms-auto flex gap-8" style="align-self:flex-end">
            ${edit && target !== 'default' && !own ? h`<button type="button" class="btn btn-outline" data-pt-own>${icon('copy', 14)} تخصيص لهذه الشركة</button>` : ''}
            ${edit && target !== 'default' && own ? h`<button type="button" class="btn btn-ghost" data-pt-drop>${icon('trash-2', 14)} حذف التخصيص</button>` : ''}
            ${edit ? h`<button type="button" class="btn btn-ghost" data-pt-rollback${state.config_version ? '' : raw(' disabled')}>${icon('rotate-ccw', 14)} رجوع للإعداد السابق</button>` : ''}
            ${edit && own ? h`<button type="button" class="btn btn-primary" data-pt-publish>${icon('upload', 14)} نشر</button>` : ''}
          </div></div>
          <div class="hint">النسخة الحالية: <b class="num" data-pt-version>${state.config_version}</b>. متغيرات الهيدر: ${state.options.header_variables.map(function (v) { return '{' + v + '}'; }).join(' ')} · متغيرات الفوتر: ${state.options.footer_variables.map(function (v) { return '{' + v + '}'; }).join(' ')}</div></div>
        <div class="pt-grid">
          <div class="card" data-pt-form>${own ? SECTIONS.map(function (s) { return h`<fieldset class="pt-sec"><legend>${s[1]}</legend><div class="form-grid">${s[2].map(function (f) { return field(f, t || state.default, edit); })}</div></fieldset>`; }) : BT.empty('printer', 'بالقالب الافتراضي', 'خصّص قالباً لهذه الشركة لتغيّر شكل أوراقها')}</div>
          <div class="card pt-side"><div class="card-h"><div class="card-t">${icon('eye', 15)} معاينة حية</div><div class="ms-auto">${BT.tabs('ptk', [['report', 'تقرير نموذجي'], ['receipt', 'إيصال نموذجي']], kind, 'tabs')}</div></div>
            <div class="pd-preview-wrap" data-pt-preview></div>
            ${state.history.length ? h`<div class="section-t mt-12">سجل النشر</div><div class="table-wrap"><table class="t compact"><thead><tr><th class="num">النسخة</th><th>التغيير</th><th>بواسطة</th><th class="num">في</th></tr></thead><tbody>${state.history.slice(0, 8).map(function (r) {
              return h`<tr><td class="num">${r.version}</td><td>${r.restored_from != null ? 'رجوع إلى النسخة ' + r.restored_from : r.changed === 'default' ? 'الافتراضي' : r.changed === 'import' ? 'استيراد إعدادات من ملف' : 'شركة ' + String(r.changed || '').replace('company:', '')}</td><td>${r.by ? r.by.name : '—'}</td><td class="num">${fmt.dt(r.at)}</td></tr>`;
            })}</tbody></table></div>` : ''}</div>
        </div>`);
      preview();
    }
    function publish(template) {
      var path = target === 'default' ? '/print-templates/default' : '/print-templates/companies/' + target;
      return api.put(path, { template: template, config_version: state.config_version }).then(function (m) {
        state = m; BT.printLayoutReset(); BT.toast(template === null ? 'حُذف التخصيص: تطبع الشركة بالقالب الافتراضي' : 'نُشر قالب الطباعة (النسخة ' + m.config_version + ')'); draw();
      }, api.fail);
    }
    el.addEventListener('input', BT.debounce(preview, 150));
    el.addEventListener('change', function (e) {
      if (e.target.matches('[data-pt-target]')) { target = e.target.value; draw(); return; }
      var up = e.target.closest('[data-upload]');
      if (up && up.files && up.files[0]) {
        var path = up.getAttribute('data-upload'), file = up.files[0];
        if (file.size > state.options.image_max_bytes) { BT.toast('الصورة أكبر من 1 ميجا', { type: 'error' }); up.value = ''; return; }
        api.uploadForm('/print-templates/images', file).then(function (x) {
          images[x.sha256] = URL.createObjectURL(file);
          el.querySelector('[data-k="' + path + '"]').value = x.sha256;
          el.querySelector('[data-img-state="' + path + '"]').textContent = 'صورة مرفوعة: انشر ليُعتمد';
          preview();
        }, api.fail);
        return;
      }
      preview();
    });
    el.addEventListener('bt:tab', function (e) { if (e.detail === 'report' || e.detail === 'receipt') { e.stopPropagation(); kind = e.detail; preview(); } });
    BT.on(el, 'click', '[data-img-clear]', function (e, b) { var p = b.getAttribute('data-img-clear'); el.querySelector('[data-k="' + p + '"]').value = ''; el.querySelector('[data-img-state="' + p + '"]').textContent = 'لا توجد صورة'; preview(); });
    BT.on(el, 'click', '[data-pt-publish]', function () { publish(read(el.querySelector('[data-pt-form]'), current() || state.default)); });
    BT.on(el, 'click', '[data-pt-own]', function () { state.companies[target] = clone(state.default); draw(); BT.toast('عدّل القالب ثم انشره لهذه الشركة'); });
    BT.on(el, 'click', '[data-pt-drop]', function () {
      if (!state.companies[target] || !state.history.some(function (r) { return r.changed === 'company:' + target; })) { delete state.companies[target]; draw(); return; }
      A.confirmRun({ title: 'حذف التخصيص', message: 'تعود الشركة للطباعة بالقالب الافتراضي.', confirmText: 'حذف', tone: 'danger', icon: 'trash-2', run: function () { return publish(null); } });
    });
    BT.on(el, 'click', '[data-pt-rollback]', function () {
      A.confirmRun({ title: 'رجوع للإعداد السابق', message: 'تُنشر قوالب الطباعة كما كانت قبل آخر نشر، كنسخة جديدة.', confirmText: 'رجوع', icon: 'rotate-ccw',
        run: function () { return api.post('/print-templates/rollback', { config_version: state.config_version }).then(function (m) { state = m; BT.printLayoutReset(); draw(); }); }, done: 'رجعت قوالب الطباعة للإعداد السابق' });
    });
    BT.render(el, A.spinner());
    load();
  };
})();
