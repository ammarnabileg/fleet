/* =====================================================================
   BrilliantTech UI — kit.js  (صفحة مكتبة المكونات ui-kit.html)
   كل مكون + كل نوع نافذة منبثقة مع زر تجربة ومثال كود.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, D = BT.data;
  var K = {};
  function code(s) { return h`<pre class="code">${s.replace(/^\n/, '')}</pre>`; }
  function b(label, cls, act, ic) { return h`<button type="button" class="btn ${cls}" data-k="${act}">${ic ? icon(ic, 15) : ''}${label}</button>`; }

  var SECTIONS = [
    { id: 'colors', title: 'الألوان والخط', lead: 'كل الألوان متغيرات CSS في assets/css/tokens.css — غيّرها مرة واحدة فتتغير في كل الشاشات، ولها نسخة للوضع الداكن.',
      html: function () {
        var sw = [['--primary', 'الأساسي'], ['--text', 'العناوين'], ['--text-2', 'النص'], ['--muted', 'ثانوي'], ['--success', 'نجاح'], ['--warning', 'تحذير'], ['--danger', 'خطر'], ['--purple', 'بنفسجي'], ['--surface-2', 'القائمة'], ['--bg', 'الخلفية']];
        return h`<div class="demo">${sw.map(function (s) { return h`<div class="swatch"><i style="background:var(${s[0]})"></i><span>${s[0]}<br>${s[1]}</span></div>`; })}</div>
          <div class="kit-h3">الخط: IBM Plex Sans Arabic (ملفات محلية، بدون إنترنت)</div>
          <div class="col" style="gap:4px"><h1>عنوان رئيسي 26</h1><h2>عنوان قسم 20</h2><h3>عنوان بطاقة 16</h3><p>نص عادي 14 — السائق يكتب القراءة ويرفع صورة العداد من الكاميرا مباشرة.</p><p class="muted fs-sm">نص ثانوي 12.5</p>
          <p>أرقام داخل جملة: الرصيد <span class="num">9,482.750</span> والتاريخ ${fmt.date('2026-11-24')} واللوحة ${BT.plate('18/23456')}</p></div>`;
      },
      code: `
:root { --primary: #0A84FF; --radius…; }     /* assets/css/tokens.css */
<span class="num">9,482.750</span>          /* رقم (LTR معزول) */
BT.fmt.date('2026-11-24')  → 24-11-2026    /* تاريخ لا ينقلب بعد العربي */
BT.plate('18/23456')                        /* لوحة سيارة */` },

    { id: 'buttons', title: 'الأزرار', lead: 'btn + نوع + حجم. زر التحميل: أضف class="is-loading".',
      html: function () {
        return h`<div class="demo">${[['btn-primary', 'أساسي', 'check'], ['btn-secondary', 'ثانوي'], ['btn-outline', 'محدد', 'download'], ['btn-ghost', 'شفاف'], ['btn-soft', 'ناعم', 'plus'], ['btn-success', 'اعتماد', 'check'], ['btn-danger', 'رفض'], ['btn-danger-solid', 'حذف', 'trash-2'], ['btn-link', 'رابط']].map(function (x) { return h`<button type="button" class="btn ${x[0]}">${x[2] ? icon(x[2], 15) : ''}${x[1]}</button>`; })}</div>
          <div class="demo"><button type="button" class="btn btn-primary btn-lg">كبير</button><button type="button" class="btn btn-primary">عادي</button><button type="button" class="btn btn-primary btn-sm">صغير</button><button type="button" class="btn btn-primary btn-xs">صغير جداً</button><button type="button" class="btn btn-primary" data-k="loading">اضغط للتحميل</button><button type="button" class="btn btn-primary" disabled>معطّل</button>
          <button type="button" class="icon-btn" data-tip="زر أيقونة" aria-label="مثال">${icon('settings', 18)}</button><button type="button" class="icon-btn" aria-label="إشعارات">${icon('bell', 18)}<span class="dot-badge">3</span></button></div>`;
      },
      code: `
<button class="btn btn-primary"><i data-icon="check"></i> اعتماد</button>
<button class="btn btn-outline btn-sm">تصدير</button>
el.classList.add('is-loading')              // حالة التحميل` },

    { id: 'status', title: 'الحالات والوسوم والصور الرمزية', lead: 'الألوان محجوزة للمعنى: أخضر = سليم/معتمد، برتقالي = تحذير/بانتظار، أحمر = خطر، أزرق = معلومة، بنفسجي = حالة خاصة، رمادي = محايد. دائماً مع نص، وليس لوناً فقط.',
      html: function () {
        return h`<div class="demo">${[['g', 'معتمد'], ['o', 'بانتظار المراجعة'], ['r', 'انقطاع'], ['b', 'قيد الإصلاح'], ['p', 'خارج يوم العمل'], ['n', 'مستقيل']].map(function (x) { return BT.pill(x[1], x[0]); })}${BT.pill('مع نقطة', 'g', true)}<span class="pill lg b">كبير</span></div>
          <div class="demo">${['g', 'o', 'r', 'b', 'p', 'n'].map(function (c) { return h`<span class="sdot ${c}"></span>`; })}<span class="sdot g pulse"></span> <span class="tag">${icon('building-2', 13)} وسم</span><kbd>Ctrl K</kbd></div>
          <div class="demo">${BT.avatar('Ahmed Ali', 'sm')}${BT.avatar('Rami Hassan')}${BT.avatar('Suresh Kumar', 'lg')}${BT.avatar('سامي الأنصاري', 'xl')}${BT.person('Imran Qadir', '41/88415')}</div>`;
      },
      code: `
BT.pill('معتمد', 'g')            // g o r b p n
BT.pill('مسلّمة', 'g', true)      // مع نقطة
BT.person('Ahmed Ali', '18/23456')
BT.avatar('Rami Hassan', 'lg')` },

    { id: 'kpi', title: 'مؤشرات وبطاقات', lead: 'BT.kpi يقبل href أو action ليصبح قابلاً للضغط. القيمة الرقمية تُعرض LTR تلقائياً.',
      html: function () {
        return h`<div class="kpis">${BT.kpi({ label: 'السيارات النشطة', value: h`352<small> / 386</small>`, sub: '11 في الصيانة · 23 بلا سائق', dot: 'g' })}${BT.kpi({ label: 'تحصيلات اليوم', value: '6,215.500', sub: '118 إيصالاً', dot: 'g', tone: 'success' })}${BT.kpi({ label: 'متوسط مدة البقاء', value: '2.7 يوم', dot: 'p' })}${BT.kpi({ label: 'انقطاع إشارة', value: '3', dot: 'r', tone: 'danger', action: 'kit-kpi' })}</div>
          <div class="grid-2 mt-16"><div class="card"><div class="card-h"><div class="card-t">${icon('wallet', 17)} بطاقة بعنوان</div><span class="card-meta">وصف صغير</span></div>${BT.kv([['رصيد أمس', BT.amt(10124.75)], ['تحصيلات اليوم', BT.amt(6215.5, { signed: true })], ['الرصيد', BT.amt(11340.25), 'total']])}</div>
          <div class="card"><div class="card-h"><div class="card-t">قائمة</div></div><div class="list">${[['wifi-off', 'r', 'انقطاع إشارة Rahim Islam'], ['triangle-alert', 'o', 'فرق عداد 12 كم'], ['info', 'b', 'استمارة تنتهي بعد 21 يوماً']].map(function (x) { return h`<button type="button" class="li"><span class="li-ic ${x[1]}">${icon(x[0], 16)}</span><div class="li-main"><div class="li-t">${x[2]}</div><div class="li-d">اليوم 23:00</div></div></button>`; })}</div></div></div>`;
      },
      code: `
BT.kpi({ label:'السيارات النشطة', value:'352', sub:'…', dot:'g', href:'#/vehicles' })
BT.kv([['رصيد أمس', BT.amt(10124.75)], ['الرصيد', BT.amt(11340.25), 'total']])
<div class="card"><div class="card-h"><div class="card-t">…</div></div>…</div>` },

    { id: 'table', title: 'الجدول الذكي', lead: 'BT.table: بحث، فلاتر (chips)، فرز بالضغط على العنوان، ترقيم صفحات، تحديد متعدد مع إجراءات جماعية، قائمة إجراءات لكل صف، وضغطة على الصف.',
      html: function () { return h`<div class="card"><div id="kit-table"></div></div>`; },
      after: function () {
        BT.table(document.getElementById('kit-table'), {
          rows: function () { return D.vehicles.slice(0, 60); }, pageSize: 5,
          search: { placeholder: 'ابحث بلوحة أو موديل…', text: function (v) { return v.plate + ' ' + v.model; } },
          chips: { key: 'status', options: [{ v: 'مسلّمة', t: 'مسلّمة' }, { v: 'في الصيانة', t: 'في الصيانة' }] },
          tools: h`<button type="button" class="btn btn-primary btn-sm">${icon('plus', 14)} إضافة</button>`,
          columns: [
            { key: 'plate', label: 'السيارة', render: function (v) { return h`<span class="plate">${v.plate}</span><span class="sub ltr">${v.make} ${v.model}</span>`; } },
            { key: 'status', label: 'الحالة', render: function (v) { return BT.pill(v.status, D.vehStatusTone[v.status]); } },
            { key: 'odo', label: 'العداد', num: true, render: function (v) { return fmt.km(v.odo); } },
            { key: 'branch', label: 'الفرع' }
          ],
          selectable: true, bulk: [{ label: 'تصدير المحدد', icon: 'download', run: function (rows, done) { BT.toast(rows.length + ' صفوف'); done(); } }],
          rowMenu: function (v) { return [{ label: 'عرض', icon: 'eye', onClick: function () { BT.toast(v.plate); } }, { sep: true }, { label: 'حذف', icon: 'trash-2', danger: true }]; },
          rowClick: function (v) { BT.toast('ضغطت على ' + v.plate, { type: 'info' }); }
        });
      },
      code: `
BT.table(el, {
  rows: () => data, pageSize: 10,
  search: { placeholder: 'بحث…', text: r => r.plate + ' ' + r.driver },
  chips:  { key: 'status', options: [{ v: 'مسلّمة', t: 'مسلّمة' }] },
  columns: [{ key: 'plate', label: 'السيارة', render: r => BT.plate(r.plate) },
            { key: 'odo', label: 'العداد', num: true }],
  selectable: true, bulk: [{ label: 'تصدير', run: (rows, done) => done() }],
  rowMenu: r => [{ label: 'عرض', icon: 'eye', onClick(){} }],
  rowClick: r => openDrawer(r)
});` },

    { id: 'forms', title: 'النماذج والتحقق', lead: 'BT.f.* يبني الحقول. التحقق تلقائي من required / min / max / pattern / data-validate. اضغط «تحقق» بدون تعبئة لترى رسائل الخطأ.',
      html: function () {
        return h`<form id="kit-form" class="card form" novalidate><div class="form-grid">
          ${BT.f.input({ name: 'name', label: 'حقل نص', required: true, placeholder: 'اكتب هنا' })}
          ${BT.f.input({ name: 'phone', label: 'جوال كويتي', required: true, validate: 'kwPhone', maxlength: 8, placeholder: '9xxxxxxx' })}
          ${BT.f.money({ name: 'amount', label: 'مبلغ بالدينار', required: true, min: 0.25 })}
          ${BT.f.input({ name: 'km', label: 'رقم مع وحدة', num: true, addon: 'كم', min: 0 })}
          ${BT.f.select({ name: 'sel', label: 'قائمة اختيار', required: true, options: ['المهبولة', 'الفروانية'] })}
          ${BT.f.date({ name: 'date', label: 'تاريخ', required: true })}
          ${BT.f.textarea({ name: 'notes', label: 'نص طويل', optional: true, full: true, rows: 2 })}
          <div class="full">${BT.f.radios({ name: 'r', label: 'اختيار بالبطاقات', required: true, options: [{ v: 'a', t: 'قبول', d: 'وصف قصير' }, { v: 'b', t: 'تصحيح', d: 'وصف قصير' }, { v: 'c', t: 'رفض', d: 'وصف قصير' }] })}</div>
          <div class="field"><label>مربعات ومفاتيح</label><div class="col" style="gap:8px">${BT.f.check({ name: 'c1', label: 'مربع اختيار', checked: true })}${BT.f.switch({ name: 's1', label: 'مفتاح تشغيل', checked: true })}</div></div>
          <div class="field"><label>رمز تحقق OTP</label>${BT.otp.html(6)}</div>
          ${BT.f.upload({ name: 'file', label: 'رفع ملف (سحب وإفلات)', required: true, multiple: true })}
          ${BT.f.camera({ name: 'cam', label: 'كاميرا فقط (صورة العداد)', required: true })}
        </div><div class="card-f"><button type="submit" class="btn btn-primary">${icon('check', 15)} تحقق</button><button type="reset" class="btn btn-ghost">مسح</button></div></form>`;
      },
      after: function () {
        var f = document.getElementById('kit-form'); BT.form.live(f);
        f.addEventListener('submit', function (e) { e.preventDefault(); if (BT.form.validate(f)) BT.toast('النموذج سليم', { sub: JSON.stringify(Object.keys(BT.form.values(f))).slice(0, 60) }); });
      },
      code: `
BT.f.input({ name:'phone', label:'الجوال', required:true, validate:'kwPhone' })
BT.f.money({ name:'amount', label:'المبلغ', required:true, min:0.25 })
BT.f.camera({ name:'photo', label:'صورة العداد', required:true })   // capture="environment"
if (BT.form.validate(form)) { const v = BT.form.values(form); }
BT.validators.myRule = (value, el, form) => value ? '' : 'رسالة الخطأ';` },

    { id: 'nav', title: 'التبويبات والتنقل', lead: 'tabs (مقسّم) و tabs-line (خط سفلي) مع data-panel، والفلاتر (chips)، ومراحل الصيانة (flow)، والمعالج (stepper).',
      html: function () {
        return h`${BT.tabs('kt1', [['a', 'اليوم'], ['b', 'أمس'], ['c', 'فترة']], 'a')}
          <div class="mt-16">${BT.tabs('kt2', [['x', 'نظرة عامة'], ['y', 'التسليم', 3], ['z', 'الصيانة', 2]], 'x', 'tabs-line')}</div>
          <div data-panel="x" data-group="kt2" class="active muted fs-sm mt-8">محتوى «نظرة عامة»</div><div data-panel="y" data-group="kt2" class="muted fs-sm mt-8">محتوى «التسليم»</div><div data-panel="z" data-group="kt2" class="muted fs-sm mt-8">محتوى «الصيانة»</div>
          <div class="chips mt-16"><button type="button" class="chip active">الكل <span class="n">386</span></button><button type="button" class="chip">مسلّمة <span class="n">352</span></button><button type="button" class="chip"><span class="sdot r"></span>انقطاع <span class="n">3</span></button></div>
          <div class="flow mt-16">${D.stages.slice(0, 6).map(function (s, i) { return h`${i ? raw('<span class="arr">←</span>') : ''}<span class="st${i === 2 ? ' active' : ''}">${s}</span>`; })}</div>
          <div class="stepper mt-16"><div class="step done"><span class="sn">${icon('check', 13)}</span>البيانات</div><div class="step-line done"></div><div class="step active"><span class="sn">2</span>المستندات</div><div class="step-line"></div><div class="step"><span class="sn">3</span>الراتب</div></div>
          <div class="crumbs mt-8"><a href="#">السيارات</a>${icon('chevron-left', 12)}<span>18/23456</span></div>`;
      },
      code: `
BT.tabs('group', [['a','اليوم'], ['b','أمس']], 'a')            // مقسّم
BT.tabs('group', [['x','نظرة عامة'], ['y','التسليم', 3]], 'x', 'tabs-line')
<div data-panel="x" data-group="group" class="active">…</div>
el.addEventListener('bt:tab', e => e.detail)                  // عند التبديل` },

    { id: 'feedback', title: 'رسائل ومؤشرات', lead: 'Banners للرسائل داخل الصفحة، والحالة الفارغة، والتحميل، والتقدم، والتسلسل الزمني.',
      html: function () {
        return h`<div class="col" style="gap:10px">${[['info', 'info', 'معلومة: التقرير يُرسل بعد بدء اليوم.'], ['warn', 'triangle-alert', 'تحذير: فرق 12 كم عن آخر قراءة.'], ['danger', 'circle-x', 'خطأ: تقرير الشرطة غير مرفق.'], ['success', 'circle-check', 'تم: اعتُمد التقرير.'], ['note', 'lightbulb', 'ملاحظة محايدة بخلفية بيضاء.']].map(function (x) { return h`<div class="banner ${x[0]}">${icon(x[1], 16)}<div>${x[2]}</div></div>`; })}</div>
          <div class="grid-3 mt-16"><div class="card">${BT.empty('inbox', 'لا توجد بيانات', 'نص توضيحي', h`<button type="button" class="btn btn-sm btn-primary mt-8">إضافة</button>`)}</div>
          <div class="card col" style="gap:10px"><div class="skel" style="width:60%"></div><div class="skel"></div><div class="skel" style="width:80%"></div><div class="skel" style="height:60px"></div>
            <div class="meter"><i style="width:40%"></i></div><div class="meter warn"><i style="width:88%"></i></div><div class="meter danger"><i style="width:100%"></i></div></div>
          <div class="card"><div class="timeline">${[['g', 'check', 'بلاغ السائق', '21:52'], ['g', 'check', 'تقرير الشرطة', '20-11'], ['o', 'clock', 'بانتظار التقدير', '']].map(function (x) { return h`<div class="tl-item"><span class="tl-ic ${x[0]}">${icon(x[1], 13)}</span><div><div class="tl-t">${x[2]}</div><div class="tl-d">${x[3]}</div></div></div>`; })}<div class="tl-item"><span class="tl-ic pending"></span><div><div class="tl-t muted">الخطوة التالية</div></div></div></div></div></div>`;
      },
      code: `
<div class="banner warn"><i data-icon="triangle-alert"></i><div>نص</div></div>
BT.empty('inbox', 'لا توجد بيانات', 'وصف', actionHtml)
<div class="meter warn"><i style="width:88%"></i></div>` },

    { id: 'charts', title: 'الرسوم البيانية والخريطة', lead: 'رسم أعمدة لسلسلة واحدة بمحور واحد (بدون محورين)، مع تلميح عند المرور والتركيز بالكيبورد، وبديل جدولي. الزمن من اليمين (الأقدم) إلى اليسار (الأحدث).',
      html: function () {
        return h`<div class="grid-2"><div class="card"><div class="card-t mb-8">الطلبات — آخر 7 أيام</div><div id="kit-bars"></div></div>
          <div class="card"><div class="card-t mb-12">متوسط مدة البقاء (يوم)</div>${BT.chart.hbars({ rows: [{ label: 'مركز الملا للصيانة', value: 2.6 }, { label: 'مركز الغانم', value: 3.4 }, { label: 'ورشة الفحيحيل', value: 1.9 }], max: 4, unit: 'يوم' })}
          <div class="mt-16">${BT.chart.table(['المركز', 'الأيام'], [['مركز الملا', '2.6'], ['مركز الغانم', '3.4']])}</div></div></div>
          <div class="card mt-16" style="max-width:560px">${BT.kuwaitMap({ pins: [{ id: 'a', x: 222, y: 168, label: '23456', tone: 'g' }, { id: 'b', x: 170, y: 250, label: '66024', tone: 'r' }, { id: 'c', x: 262, y: 318, label: '40077', tone: 'o' }] })}</div>`;
      },
      after: function () { BT.chart.bars(document.getElementById('kit-bars'), { name: 'الطلبات', labels: D.history.days.map(BT.date.dayName), sublabels: D.history.days.map(fmt.dm), values: D.history.orders, unitLabel: 'طلب', height: 210 }); },
      code: `
BT.chart.bars(el, { labels, values, format: BT.fmt.int, unitLabel: 'طلب' })
BT.chart.hbars({ rows: [{ label, value }], max: 4, unit: 'يوم' })
BT.chart.table(headers, rows)                     // البديل الجدولي
BT.kuwaitMap({ pins:[{id,x,y,label,tone}], route:[[x,y]…] })  // توضيحية فقط` },

    { id: 'popups', title: 'كل النوافذ المنبثقة', lead: 'اضغط أي زر لتجربة النافذة. كلها تُغلق بـ Esc أو بالضغط خارجها، وتحبس التركيز داخلها (إمكانية الوصول)، وتعيد التركيز للزر عند الإغلاق.',
      html: function () {
        return h`<div class="kit-h3">Modal — نافذة وسط الشاشة</div><div class="demo">${b('صغيرة', 'btn-outline', 'modal-sm')}${b('متوسطة', 'btn-outline', 'modal-md')}${b('كبيرة', 'btn-outline', 'modal-lg')}${b('كبيرة جداً', 'btn-outline', 'modal-xl')}${b('نموذج مع تحقق', 'btn-primary', 'modal-form', 'file-plus')}${b('معالج خطوات', 'btn-primary', 'wizard', 'list-ordered')}</div>
          <div class="kit-h3">Drawer — لوحة جانبية</div><div class="demo">${b('لوحة جانبية', 'btn-outline', 'drawer', 'panel-left')}${b('لوحة عريضة بتبويبات', 'btn-outline', 'drawer-lg', 'panel-left')}</div>
          <div class="kit-h3">Bottom sheet — للجوال</div><div class="demo">${b('Bottom sheet', 'btn-outline', 'sheet', 'panel-bottom')}</div>
          <div class="kit-h3">Confirm — تأكيد</div><div class="demo">${b('تأكيد عادي', 'btn-outline', 'confirm')}${b('تأكيد خطر', 'btn-danger', 'confirm-danger', 'trash-2')}${b('مع سبب إلزامي', 'btn-outline', 'confirm-reason')}${b('بكتابة نص للتأكيد', 'btn-outline', 'confirm-typed', 'lock')}</div>
          <div class="kit-h3">Toast — إشعار مؤقت</div><div class="demo">${b('نجاح', 'btn-success', 'toast-success')}${b('خطأ', 'btn-danger', 'toast-error')}${b('تحذير', 'btn-outline', 'toast-warning')}${b('معلومة + إجراء', 'btn-outline', 'toast-action')}</div>
          <div class="kit-h3">Menu / Popover / Tooltip</div><div class="demo">${b('قائمة منسدلة', 'btn-outline', 'menu', 'chevron-down')}${b('Popover', 'btn-outline', 'popover', 'message-square')}<button type="button" class="btn btn-outline" data-tip="تلميح يظهر عند المرور">مرّر هنا للتلميح</button><button type="button" class="btn btn-outline" data-tip="أسفل العنصر" data-tip-pos="bottom">تلميح لأسفل</button></div>
          <div class="kit-h3">عرض الصور والمستندات والبحث</div><div class="demo">${b('معرض صور (Lightbox)', 'btn-outline', 'lightbox', 'images')}${b('صورة العداد', 'btn-outline', 'odo', 'camera')}${b('معاينة مستند', 'btn-outline', 'doc', 'file-text')}${b('بحث سريع Ctrl+K', 'btn-outline', 'cmdk', 'search')}${b('إيصال للطباعة', 'btn-outline', 'receipt', 'printer')}</div>`;
      },
      code: `
BT.modal.open({ title, subtitle, icon, size:'sm|lg|xl', body, form:true,
  buttons:[{ label:'إلغاء', cls:'btn-ghost' }, { label:'حفظ', cls:'btn-primary', submit:true }],
  onSubmit: (values, api) => { /* return false لإبقاء النافذة */ } })
BT.drawer.open({ …نفس الخيارات… })      BT.sheet.open({ … })
BT.confirm({ title, message, tone:'danger', reason:{label:'السبب'}, typed:'نص' })
  .then(r => r.ok && r.reason)
BT.toast('تم الحفظ', { type:'success|error|warning|info', sub, action:{label, fn} })
BT.menu(anchorEl, [{ label, icon, onClick }, { sep:true }, { label, danger:true }])
BT.popover(anchorEl, html)     BT.lightbox([{ src|html, caption }], i)
BT.cmdk({ source: () => [{ group, label, icon, hint, run }] })     BT.print(html)` }
  ];

  /* ---------- أفعال الأزرار ---------- */
  var body = h`<p class="confirm-msg">هذا محتوى النافذة. يمكن أن يحتوي أي HTML: جداول، نماذج، صور…</p>`;
  K['modal-sm'] = function () { BT.modal.open({ size: 'sm', title: 'نافذة صغيرة', icon: 'info', body: body, buttons: [{ label: 'إغلاق', cls: 'btn-primary' }] }); };
  K['modal-md'] = function () { BT.modal.open({ title: 'نافذة متوسطة', subtitle: 'مع عنوان فرعي', icon: 'layout-panel-top', body: h`${body}${BT.kv([['السيارة', BT.plate('18/23456')], ['السائق', 'Ahmed Ali'], ['الحالة', BT.pill('مسلّمة', 'g')]])}`, footNote: 'ملاحظة في التذييل', buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ', cls: 'btn-primary' }] }); };
  K['modal-lg'] = function () { BT.modal.open({ size: 'lg', title: 'نافذة كبيرة', icon: 'maximize', body: h`<div class="kpis cols-3">${BT.kpi({ label: 'الطلبات', value: '25', dot: 'b' })}${BT.kpi({ label: 'الكاش', value: '40.500', dot: 'o' })}${BT.kpi({ label: 'كم', value: '122', dot: 'g' })}</div>`, buttons: [{ label: 'إغلاق', cls: 'btn-primary' }] }); };
  K['modal-xl'] = function () { BT.modal.open({ size: 'xl', title: 'نافذة كبيرة جداً (مثل مراجعة التقرير)', icon: 'clipboard-list', body: h`<div class="grid" style="grid-template-columns:minmax(0,1fr) 300px">${BT.kuwaitMap({ zone: false, route: D.route('18/23456', 'اليوم').points })}<div>${BT.kv([['المسافة', '118 كم'], ['التوقفات', '4']])}</div></div>`, buttons: [{ label: 'إغلاق', cls: 'btn-primary' }] }); };
  K['modal-form'] = function () {
    BT.modal.open({ title: 'نموذج داخل نافذة', icon: 'file-plus', form: true, body: h`<div class="form">${BT.f.input({ name: 'n', label: 'الاسم', required: true })}${BT.f.money({ name: 'a', label: 'المبلغ', required: true, min: 1 })}${BT.f.select({ name: 's', label: 'الفرع', required: true, options: ['المهبولة', 'الفروانية'] })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ', cls: 'btn-primary', submit: true }],
      onSubmit: function (v) { return new Promise(function (r) { setTimeout(function () { r(true); BT.toast('تم الحفظ', { sub: v.n + ' · ' + fmt.kwd(v.a) }); }, 700); }); } });
  };
  K['wizard'] = function () {
    var cur = 0, steps = ['البيانات', 'المستندات', 'المراجعة'];
    var d = BT.modal.open({ title: 'معالج خطوات', icon: 'list-ordered', size: 'lg', body: h`<div class="stepper" id="kw-s"></div>${steps.map(function (s, i) { return h`<div data-kw="${i}" class="${i ? 'hidden' : ''}"><div class="form">${BT.f.input({ name: 'f' + i, label: 'حقل في خطوة «' + s + '»', required: i < 2 })}</div></div>`; })}`,
      buttons: [{ label: 'رجوع', cls: 'btn-outline', close: false, onClick: function () { move(-1); } }, { label: 'التالي', cls: 'btn-primary', close: false, onClick: function () { move(1); } }] });
    function draw() { BT.render(d.el.querySelector('#kw-s'), h`${steps.map(function (s, i) { return h`${i ? raw('<div class="step-line' + (i <= cur ? ' done' : '') + '"></div>') : ''}<div class="step${i === cur ? ' active' : i < cur ? ' done' : ''}"><span class="sn">${i < cur ? icon('check', 13) : i + 1}</span>${s}</div>`; })}`); BT.$$('[data-kw]', d.el).forEach(function (p) { p.classList.toggle('hidden', +p.getAttribute('data-kw') !== cur); }); d.btn(0).style.visibility = cur ? '' : 'hidden'; d.btn(1).textContent = cur === steps.length - 1 ? 'إنهاء' : 'التالي'; }
    function move(x) { if (x > 0 && !BT.form.validate(d.el.querySelector('[data-kw="' + cur + '"]'))) return; if (x > 0 && cur === steps.length - 1) { d.close(); BT.toast('اكتمل المعالج'); return; } cur = Math.max(0, cur + x); draw(); }
    draw();
  };
  K['drawer'] = function () { BT.drawer.open({ title: 'لوحة جانبية', subtitle: 'تُستخدم لتفاصيل سجل دون مغادرة الصفحة', icon: 'panel-left', body: h`${BT.kv([['السيارة', BT.plate('18/23456')], ['السائق', 'Ahmed Ali'], ['آخر إشارة', 'منذ 12 ث']])}<div class="mt-16">${BT.kuwaitMap({ tools: false, zone: false, pins: [{ id: 'x', x: 222, y: 168, label: '23456', tone: 'g' }] })}</div>`, buttons: [{ label: 'إغلاق', cls: 'btn-ghost' }, { label: 'إجراء', cls: 'btn-primary' }] }); };
  K['drawer-lg'] = function () { BT.drawer.open({ size: 'lg', title: 'لوحة عريضة', icon: 'user-round', body: h`${BT.tabs('kd', [['a', 'البيانات'], ['b', 'المستندات'], ['c', 'السجل']], 'a', 'tabs-line')}<div class="mt-16"><div data-panel="a" data-group="kd" class="active">${BT.kv([['الجوال', '65123480'], ['الفرع', 'المهبولة']])}</div><div data-panel="b" data-group="kd">${BT.empty('file-badge', 'مستندات', '')}</div><div data-panel="c" data-group="kd">${BT.empty('history', 'السجل', '')}</div></div>`, buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }] }); };
  K['sheet'] = function () { BT.sheet.open({ title: 'Bottom sheet', icon: 'panel-bottom', body: h`<p class="confirm-msg">تظهر من أسفل الشاشة — مناسبة لتطبيق السائق. على الجوال تتحول كل النوافذ المتوسطة لهذا الشكل تلقائياً.</p>`, buttons: [{ label: 'إلغاء', cls: 'btn-outline' }, { label: 'موافق', cls: 'btn-primary' }] }); };
  K['confirm'] = function () { BT.confirm({ title: 'اعتماد 26 تقريراً', message: 'سيُضاف الكاش إلى أرصدة السائقين.', confirmText: 'اعتماد', tone: 'success' }).then(function (r) { BT.toast(r.ok ? 'تم التأكيد' : 'أُلغي', { type: r.ok ? 'success' : 'info' }); }); };
  K['confirm-danger'] = function () { BT.confirm({ title: 'إيقاف السيارة', message: 'لن يمكن تسليمها حتى تُعاد للخدمة.', confirmText: 'إيقاف', tone: 'danger' }).then(function (r) { if (r.ok) BT.toast('تم', { type: 'warning' }); }); };
  K['confirm-reason'] = function () { BT.confirm({ title: 'رفض التقرير', message: 'السبب يظهر للسائق.', confirmText: 'رفض', tone: 'danger', reason: { label: 'سبب الرفض' } }).then(function (r) { if (r.ok) BT.toast('السبب: ' + r.reason); }); };
  K['confirm-typed'] = function () { BT.confirm({ title: 'إقفال كشف الرواتب', message: 'لا يمكن التعديل بعد الإقفال.', confirmText: 'إقفال', tone: 'warn', icon: 'lock', typed: 'نوفمبر 2026' }).then(function (r) { if (r.ok) BT.toast('تم الإقفال'); }); };
  K['toast-success'] = function () { BT.toast('تم حفظ التعديلات', { sub: 'مسجّل في سجل التدقيق' }); };
  K['toast-error'] = function () { BT.toast('تعذّر الحفظ', { type: 'error', sub: 'تحقق من الاتصال' }); };
  K['toast-warning'] = function () { BT.toast('الرصيد فوق حد التنبيه', { type: 'warning' }); };
  K['toast-action'] = function () { BT.toast('تم حذف البند', { type: 'info', action: { label: 'تراجع', fn: function () { BT.toast('تمت الاستعادة'); } } }); };
  K['menu'] = function (el) { BT.menu(el, [{ head: 'إجراءات' }, { label: 'عرض الملف', icon: 'file-text' }, { label: 'تعديل', icon: 'pencil' }, { label: 'محدد', icon: 'check', checked: true }, { sep: true }, { label: 'حذف', icon: 'trash-2', danger: true, onClick: function () { BT.toast('حذف', { type: 'warning' }); } }], { focus: true }); };
  K['popover'] = function (el) { BT.popover(el, h`<b>Popover</b><p class="fs-sm text-2 mt-4">محتوى حر: نص، أزرار، نموذج صغير. يُغلق بالضغط خارجه أو Esc.</p><button type="button" class="btn btn-sm btn-primary mt-8" onclick="BT.closeMenu()">تم</button>`); };
  K['lightbox'] = function () { BT.lightbox(['أمام', 'خلف', 'يمين', 'يسار'].map(function (s) { return { html: h`<div class="ph" style="width:min(640px,86vw);height:400px">${icon('car', 64)}<span>${s}</span></div>`, caption: 'صورة ' + s, sub: 'استخدم الأسهم للتنقل' }; })); };
  K['odo'] = function () { BT.lightbox([{ html: h`<div class="odo lg"><span class="digits">045320</span><span class="meta">${icon('camera', 11)} من الكاميرا · 23:05</span></div>`, caption: 'عداد نهاية اليوم', sub: 'المكتوب 45,320' }]); };
  K['doc'] = function () { BT.lightbox({ html: h`<div class="lb-doc"><h3>تقرير قسم الشرطة</h3>${BT.kv([['الرقم', '2026/4390'], ['الموقع', 'المهبولة']])}<p class="muted fs-sm mt-24 center">معاينة توضيحية</p></div>`, caption: 'مستند PDF' }); };
  K['cmdk'] = function () { BT.openSearch(); };
  K['receipt'] = function () { var r = { no: 31163, amount: 50, driver: 'Ahmed Khan', date: '2026-11-24', time: '23:14', by: 'Rajesh Menon', status: 'بانتظار تأكيد السائق' }; var html = h`<div class="receipt"><div class="r-head"><b>${BT.config.client}</b><b class="num">${r.no}</b></div><div class="r-amt"><b class="num">${fmt.kwd(r.amount)}</b> د.ك</div><div class="r-row"><span>من السائق</span><b>${r.driver}</b></div><div class="r-sign"><div>توقيع المحاسب</div><div>توقيع السائق</div></div></div>`; BT.modal.open({ size: 'sm', title: 'إيصال', icon: 'receipt', body: html, buttons: [{ label: 'طباعة', cls: 'btn-outline', icon: 'printer', close: false, onClick: function () { BT.print(html); } }, { label: 'تم', cls: 'btn-primary' }] }); };
  K['loading'] = function (el) { el.classList.add('is-loading'); setTimeout(function () { el.classList.remove('is-loading'); }, 1200); };
  BT.actions['kit-kpi'] = function () { BT.toast('KPI قابل للضغط', { type: 'info' }); };
  BT.openSearch = function () { BT.cmdk({ source: function () { return [{ group: 'الصفحات', label: 'لوحة الإدارة', icon: 'house', run: function () { location.href = 'admin.html'; } }, { group: 'الصفحات', label: 'تطبيق السائق', icon: 'smartphone', run: function () { location.href = 'driver.html'; } }, { group: 'الصفحات', label: 'بوابة مراكز الصيانة', icon: 'store', run: function () { location.href = 'portal.html'; } }].concat(D.vehicles.slice(0, 50).map(function (v) { return { group: 'السيارات', label: v.plate, hint: v.make + ' ' + v.model, icon: 'car', run: function () { BT.toast(v.plate); } }; })); } }); };

  function boot() {
    BT.render(document.getElementById('kit-nav'), h`${SECTIONS.map(function (s) { return h`<a href="#${s.id}">${s.title}</a>`; })}`);
    BT.render(document.getElementById('kit'), h`${SECTIONS.map(function (s) { return h`<section class="kit-sec" id="${s.id}"><h2>${s.title}</h2><p class="lead">${s.lead}</p>${s.html()}${s.code ? h`<div class="kit-h3">الاستخدام</div>${code(s.code)}` : ''}</section>`; })}`);
    SECTIONS.forEach(function (s) { if (s.after) s.after(); });
    BT.on(document.body, 'click', '[data-k]', function (e, el) { var fn = K[el.getAttribute('data-k')]; if (fn) fn(el); });
    document.getElementById('kit-theme').onclick = BT.theme.toggle;
    BT.hydrate(document);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else setTimeout(boot, 0);
})();
