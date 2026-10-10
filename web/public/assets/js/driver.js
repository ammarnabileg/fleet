/* =====================================================================
   BrilliantTech UI — driver.js  (تطبيق السائق)
   الشاشات: رابط التفعيل ← التسجيل الأول (بياناتك · مستنداتك · سيارتك · مراجعة) ← بانتظار المشرف ·
   الدخول ← رمز OTP ← الرئيسية · بدء اليوم (العداد) · التقرير اليومي ·
   الكاش والإيصالات · الصيانة · الإبلاغ عن حادث · حسابي · المستندات
   بوب أب (bottom sheets): الإشعارات · تأكيد الإرسال · تأكيد استلام إيصال ·
   ربط الهاتف · قسيمة الراتب · تحذير فرق العداد · تسجيل الخروج
   كل الشاشات في D.screen[...] — للإضافة: اكتب شاشة جديدة واستدعِ go('name')
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, D = BT.data;
  var cfg = BT.config;
  var ME = D.byName['Ahmed Ali'], CAR = D.byPlate[ME.vehicleId], REP = ME.today;
  var S = { day: REP && REP.orders != null ? 'sent' : 'started', dayStart: { time: '07:52', odo: 45198 }, stack: [], tab: 'home' };
  var root, viewEl, tabEl;

  var TABS = [['home', 'house', 'الرئيسية'], ['report', 'clipboard-list', 'العمل اليومي'], ['cash', 'wallet', 'الكاش'], ['maint', 'wrench', 'الصيانة'], ['account', 'user-round', 'حسابي']];
  var myJobs = [{ id: 'M-2588', date: BT.date.add(cfg.today, -12), desc: 'تبديل زيت وفلتر', stage: 'تم الاستلام', center: 'مركز الملا' }, { id: 'M-2571', date: BT.date.add(cfg.today, -21), desc: 'تبديل إطار أمامي أيمن', stage: 'تم الاستلام', center: 'ورشة الفحيحيل' }];
  var notifs = [
    { icon: 'clipboard-check', tone: 'b', t: 'تقريرك اليومي وصل للمراجعة', d: 'اليوم 23:12' },
    { icon: 'receipt', tone: 'o', t: 'إيصال 31012 بانتظار تأكيدك', d: 'أمس 20:15' },
    { icon: 'key-round', tone: 'g', t: 'تم تسليمك السيارة 18/23456 · العداد 45,070', d: 'أمس 07:40' },
    { icon: 'badge-check', tone: 'g', t: 'اعتُمد تقرير يوم 23-11', d: 'أمس 23:40' }
  ];

  /* ---------- هيكل الشاشة ---------- */
  function screen(o) { // {title, back, actions, body, tabbar}
    return h`${o.title != null ? h`<div class="app-head">${o.back ? h`<button type="button" class="back" data-back aria-label="رجوع">${icon('arrow-right', 18)}</button>` : ''}<h2>${o.title}</h2>${o.actions ? h`<div class="head-actions">${o.actions}</div>` : ''}</div>` : ''}<div class="screen">${o.body}</div>`;
  }
  function go(name, params, opts) {
    opts = opts || {};
    if (!opts.replace && S.cur) S.stack.push(S.cur);
    if (opts.reset) S.stack = [];
    S.cur = { name: name, params: params || {} };
    var tab = TABS.find(function (t) { return t[0] === name; });
    if (tab) { S.tab = name; S.stack = []; }
    var fn = SCREENS[name];
    BT.closeAll();
    var fresh = viewEl.cloneNode(false); viewEl.replaceWith(fresh); viewEl = fresh; // بدون تراكم مستمعات
    BT.render(viewEl, fn(params || {}));
    var sc = viewEl.querySelector('.screen'); if (sc) sc.scrollTop = 0;
    tabEl.style.display = SCREENS[name].noTabs ? 'none' : '';
    drawTabs();
    if (fn.after) fn.after(params || {});
  }
  function back() { var p = S.stack.pop(); if (p) { S.cur = null; go(p.name, p.params, { replace: true }); S.cur = p; } else go('home', {}, { reset: true }); }
  function drawTabs() { BT.render(tabEl, h`${TABS.map(function (t) { return h`<button type="button" data-tab-go="${t[0]}" class="${S.tab === t[0] ? 'active' : ''}"${S.tab === t[0] ? raw(' aria-current="page"') : ''}>${icon(t[1], 21)}<span>${t[2]}</span></button>`; })}`); }
  function pendingRc() { return D.receipts.filter(function (r) { return r.empId === ME.id && r.status !== 'مؤكد' && r.status !== 'ملغى'; }).length; }
  function bell() { return h`<button type="button" class="icon-btn" data-d="notifs" aria-label="الإشعارات">${icon('bell', 19)}<span class="dot-badge">2</span></button>`; }

  var SCREENS = {};

  /* ---------- الدخول + OTP ---------- */
  SCREENS.login = function () {
    return h`<div class="d-login"><div class="lg-top"><span class="logo lg">${icon('diamond', 24)}</span><div class="d-title">تطبيق السائق</div><div class="d-sub">${cfg.client}</div></div>
      <div class="lang-switch" style="align-self:center"><button type="button" class="active">العربية</button><button type="button" data-d="lang">English</button></div>
      <form id="lg-form" class="form" novalidate><div class="field"><label>رقم الجوال</label><div class="phone-in"><span class="cc">🇰🇼 +965</span><input class="input" name="phone" inputmode="numeric" maxlength="8" required data-validate="kwPhone" placeholder="6512 3480" value="${ME.phone}"></div><div class="err-msg"></div></div>
      <button type="submit" class="btn btn-primary d-cta">إرسال رمز التحقق</button></form>
      <div class="d-sub center" style="margin-top:auto">يصلك رمز من 6 أرقام على واتساب. أول مرة؟ افتح رابط التفعيل الذي أرسله المشرف. الحساب يعمل على هاتف واحد فقط.</div></div>`;
  };
  SCREENS.login.noTabs = true;
  SCREENS.login.after = function () {
    var f = document.getElementById('lg-form'); BT.form.live(f);
    f.addEventListener('submit', function (e) { e.preventDefault(); if (!BT.form.validate(f)) return; var b = f.querySelector('button'); b.classList.add('is-loading'); setTimeout(function () { go('otp', { phone: BT.form.values(f).phone }); }, 600); });
  };
  SCREENS.otp = function (p) {
    return screen({ title: '', back: true, body: h`<div class="col center" style="gap:14px;margin-top:10px"><span class="icon-tile lg" style="margin:0 auto">${icon('message-square', 22)}</span><div class="d-title">أدخل رمز التحقق</div><div class="d-sub">أرسلنا رمزاً من 6 أرقام إلى <b class="num">+965 ${p.phone}</b></div>
      ${BT.otp.html(6)}<div class="err-msg center" id="otp-err" style="display:none">الرمز غير صحيح — جرّب مرة أخرى</div>
      <div class="d-sub" id="otp-timer">إعادة الإرسال بعد <span class="num">00:45</span></div>
      <button type="button" class="btn btn-primary d-cta" id="otp-go">تأكيد</button><div class="d-sub">للتجربة: أي 6 أرقام عدا 000000</div></div>` });
  };
  SCREENS.otp.noTabs = true;
  SCREENS.otp.after = function () {
    var box = viewEl.querySelector('.otp'), n = 45;
    box.querySelector('input').focus();
    var t = setInterval(function () { if (!document.contains(box)) return clearInterval(t); n--; var el = document.getElementById('otp-timer'); if (n <= 0) { clearInterval(t); BT.render(el, h`<button type="button" class="btn btn-link" data-d="resend">إعادة إرسال الرمز</button>`); } else el.querySelector('span').textContent = '00:' + String(n).padStart(2, '0'); }, 1000);
    function check() {
      var v = BT.otp.value(box);
      if (v.length < 6) { box.classList.add('invalid'); return; }
      if (v === '000000') { box.classList.add('invalid'); document.getElementById('otp-err').style.display = 'block'; return; }
      clearInterval(t);
      BT.sheet.open({ title: 'ربط الحساب بهذا الهاتف', icon: 'smartphone', body: h`<div class="confirm-msg">سيتم ربط حسابك بهذا الهاتف فقط. للدخول من هاتف آخر يجب أن يفصل المشرف الهاتف الحالي أولاً.</div>`, buttons: [{ label: 'موافق', cls: 'btn-primary', onClick: function () { setTimeout(function () { go('home', {}, { reset: true }); BT.toast('تم تسجيل الدخول', { sub: 'الموقع يُرسل طوال فترة تسليم السيارة' }); }, 200); } }], dismissible: false });
    }
    box.addEventListener('otp:complete', check);
    document.getElementById('otp-go').onclick = check;
  };

  /* ---------- التسجيل الأول (بعد رابط التفعيل، دون OTP) ----------
     API: GET/PUT /api/v1/driver/onboarding · POST /api/v1/driver/onboarding/submit
     الصور: POST /api/v1/driver/files?source=camera (السيارة والعداد) أو source=upload (المستندات)
     المستندات وصور السيارة المطلوبة تأتي من الإعدادات (required_documents, vehicle_photos). */
  var OB_STEPS = ['بياناتك', 'مستنداتك', 'سيارتك', 'مراجعة'];
  var OB_DOCS = [['residence', 'الإقامة'], ['driving_license', 'رخصة القيادة'], ['passport', 'جواز السفر']];
  var OB_SIDES = [['front', 'أمام'], ['back', 'خلف'], ['right', 'يمين'], ['left', 'يسار']];
  S.ob = { status: 'draft', note: null, data: {} };
  function obSteps(cur) {
    return h`<div class="stepper" style="margin-bottom:4px">${OB_STEPS.map(function (s, i) { return h`${i ? raw('<div class="step-line' + (i <= cur ? ' done' : '') + '"></div>') : ''}<div class="step${i === cur ? ' active' : i < cur ? ' done' : ''}"><span class="sn">${i < cur ? icon('check', 13) : i + 1}</span>${i === cur ? s : ''}</div>`; })}</div>`;
  }
  function docTile(name, label) {
    return h`<label class="cam-tile" style="min-height:96px"><span class="cam-ic">${icon('file-up', 18)}</span><span>${label}</span><input type="file" accept="image/*,application/pdf" name="${name}" required data-msg="صورة المستند مطلوبة"></label>`;
  }
  SCREENS.onboard = function (p) {
    var step = p.step || 0, d = S.ob.data, body;
    if (step === 0) body = h`<div class="d-card col" style="gap:12px">
        <div class="kv"><div><span>الاسم</span><b>${ME.name}</b></div><div><span>الجوال</span><span class="num" dir="ltr">+965 ${ME.phone}</span></div></div>
        ${BT.f.input({ name: 'civil', label: 'الرقم المدني', optional: true, validate: 'civilId', maxlength: 12, num: true, value: d.civil || '', hint: 'اتركه فارغاً إذا كانت الإقامة تحت الإجراء' })}
        ${BT.f.select({ name: 'nat', label: 'الجنسية', required: true, value: d.nat || '', options: ['الهند', 'باكستان', 'بنغلاديش', 'نيبال', 'سريلانكا', 'مصر', 'الفلبين', 'أخرى'] })}</div>`;
    else if (step === 1) body = h`${OB_DOCS.map(function (doc) { return h`<div class="d-card col" style="gap:10px"><b>${doc[1]}</b>
        <div class="field"><div class="cam-grid" style="grid-template-columns:1fr 1fr">${docTile(doc[0] + '-f', 'الوجه')}${docTile(doc[0] + '-b', 'الظهر')}</div><div class="err-msg"></div></div>
        ${BT.f.date({ name: doc[0] + '-exp', label: 'تاريخ الانتهاء', required: true })}</div>`; })}
        <div class="banner info fs-sm">${icon('info', 15)}<div>صوّر المستند كاملاً وواضحاً، أو اختر صورة أو PDF من هاتفك.</div></div>`;
    else if (step === 2) body = h`<div class="d-card col" style="gap:12px">
        ${BT.f.switch({ name: 'none', label: 'لا توجد سيارة معي الآن', checked: !!d.none })}
        <div id="ob-car" class="col${d.none ? ' hidden' : ''}" style="gap:12px">
          ${BT.f.input({ name: 'plate', label: 'رقم اللوحة', required: true, value: d.plate || '', placeholder: '18/23456', hint: 'كما هو مكتوب على اللوحة' })}
          ${BT.f.camera({ name: 'odo-ph', label: 'صورة العداد', required: true, cta: 'التقط صورة العداد', msg: 'صورة العداد مطلوبة' })}
          ${BT.f.input({ name: 'odo', label: 'قراءة العداد', required: true, num: true, lg: true, value: d.odo || '', placeholder: '000000' })}
          <div class="field"><div class="label mb-8">صور السيارة <span class="t-danger">*</span></div><div class="cam-grid">${OB_SIDES.map(function (s) { return h`<label class="cam-tile"><span class="cam-ic">${icon('camera', 18)}</span><span>${s[1]}</span><input type="file" accept="image/*" capture="environment" name="ph-${s[0]}" required data-msg="التقط الصور الأربع من الكاميرا"></label>`; })}</div><div class="err-msg"></div></div>
        </div></div>
        <div class="banner info fs-sm">${icon('shield-check', 15)}<div>هذه الصور تثبت حالة السيارة عند استلامك لها. تبدأ عهدتك بعد اعتماد المشرف.</div></div>`;
    else body = h`<div class="d-card"><div class="list">
        ${[['user-round', 'بياناتك', (d.nat || '—') + (d.civil ? ' · ' + d.civil : '')], ['file-badge', 'مستنداتك', OB_DOCS.length + ' مستندات بالوجه والظهر'], ['car', 'سيارتك', d.none ? 'لا توجد سيارة' : (d.plate || '—') + ' · العداد ' + (d.odo ? fmt.km(+d.odo) : '—') + ' · 4 صور']].map(function (r, i) {
          return h`<div class="li"><span class="li-ic g">${icon(r[0], 16)}</span><div class="li-main"><div class="li-t">${r[1]}</div><div class="li-d">${r[2]}</div></div><button type="button" class="btn btn-sm btn-ghost" data-ob-edit="${i}">${icon('pencil', 13)} تعديل</button></div>`; })}
        </div></div>
        <div class="banner info fs-sm">${icon('info', 15)}<div>بعد الإرسال لا يمكنك التعديل إلا إذا أعاده المشرف لك مع السبب.</div></div>`;
    return screen({ title: 'التسجيل الأول', back: step > 0, body: h`<form id="ob-form" class="col" novalidate style="gap:12px">${obSteps(step)}
      ${S.ob.status === 'rejected' && step === 0 ? h`<div class="banner danger fs-sm">${icon('triangle-alert', 15)}<div><b>يحتاج تصحيحاً:</b> ${S.ob.note}</div></div>` : ''}
      ${body}<button type="submit" class="btn btn-primary d-cta">${step < 3 ? 'التالي' : h`${icon('send', 17)} إرسال للمشرف`}</button></form>` });
  };
  SCREENS.onboard.noTabs = true;
  SCREENS.onboard.after = function (p) {
    var step = p.step || 0, f = document.getElementById('ob-form'); BT.form.live(f);
    var sw = f.querySelector('[name=none]');
    if (sw) sw.addEventListener('change', function () {
      var car = f.querySelector('#ob-car'); car.classList.toggle('hidden', sw.checked);
      BT.$$('input,select', car).forEach(function (x) { if (sw.checked) x.removeAttribute('required'); else if (x.type !== 'checkbox') x.setAttribute('required', ''); });
    });
    BT.on(f, 'click', '[data-ob-edit]', function (e, b) { go('onboard', { step: +b.getAttribute('data-ob-edit') }, { replace: true }); });
    viewEl.querySelector('[data-back]') && viewEl.querySelector('[data-back]').addEventListener('click', function (e) { e.stopPropagation(); go('onboard', { step: step - 1 }, { replace: true }); }, true);
    f.addEventListener('submit', function (e) {
      e.preventDefault(); if (!BT.form.validate(f)) return;
      Object.assign(S.ob.data, BT.form.values(f));
      if (step < 3) return go('onboard', { step: step + 1 }, { replace: true });
      S.ob.status = 'submitted'; go('ob-wait', {}, { reset: true }); BT.toast('أُرسلت بياناتك للمشرف', { sub: 'يصلك إشعار على واتساب عند المراجعة' });
    });
  };
  SCREENS['ob-wait'] = function () {
    return screen({ title: 'التسجيل الأول', body: h`<div class="d-card col center" style="gap:10px;padding:24px 16px"><span class="cam-ic" style="width:56px;height:56px;border-radius:50%;background:var(--primary-soft);color:var(--primary-strong);display:flex;align-items:center;justify-content:center;margin:0 auto">${icon('hourglass', 26)}</span>
      <b style="font-size:17px">بياناتك عند المشرف للمراجعة</b><div class="d-sub">يصلك إشعار على واتساب عند الاعتماد أو إذا احتاج شيء للتصحيح.</div></div>
      <div class="d-card"><div class="timeline">
        <div class="tl-item"><span class="tl-ic g">${icon('check', 13)}</span><div><div class="tl-t">أُرسلت البيانات والمستندات وصور السيارة</div><div class="tl-d">الآن</div></div></div>
        <div class="tl-item"><span class="tl-ic">${icon('hourglass', 13)}</span><div><div class="tl-t">مراجعة المشرف</div><div class="tl-d">عادةً خلال يوم عمل</div></div></div>
        <div class="tl-item"><span class="tl-ic">${icon('key-round', 13)}</span><div><div class="tl-t">بدء العهدة والتتبع</div><div class="tl-d">بعد الاعتماد</div></div></div></div></div>
      <button type="button" class="btn btn-ghost" data-d="ob-rejected">مثال: أعاده المشرف للتصحيح</button>` });
  };
  SCREENS['ob-wait'].noTabs = true;

  /* ---------- الرئيسية ---------- */
  SCREENS.home = function () {
    var dayCard = S.day === 'not-started'
      ? h`<div class="d-card col" style="gap:12px"><div class="day-state"><span class="ds-ic" style="background:var(--primary-soft);color:var(--primary-strong)">${icon('sunrise', 22)}</span><div><b>لم تبدأ يومك بعد</b><div class="d-sub">ابدأ بتصوير العداد من الكاميرا</div></div></div><button type="button" class="btn btn-primary d-cta" data-d="start">${icon('play', 18)} بدء اليوم</button></div>`
      : S.day === 'started'
        ? h`<div class="d-card col" style="gap:12px"><div class="day-state"><span class="ds-ic" style="background:var(--success-soft);color:var(--success-text)">${icon('timer', 22)}</span><div><b>يومك بدأ الساعة <span class="num">${S.dayStart.time}</span></b><div class="d-sub">عداد البداية <span class="num">${fmt.km(S.dayStart.odo)}</span></div></div></div><button type="button" class="btn btn-primary d-cta" data-tab-go="report">${icon('send', 17)} إرسال التقرير اليومي</button></div>`
        : h`<div class="d-card"><div class="day-state"><span class="ds-ic" style="background:var(--warning-soft);color:var(--warning-text)">${icon('hourglass', 22)}</span><div class="flex-1"><b>أُرسل تقرير اليوم <span class="num">${REP.sent}</span></b><div class="d-sub">${REP.orders} طلباً · ${fmt.kwd(REP.cash)} د.ك</div></div>${BT.pill(REP.status === 'معتمد' ? 'معتمد' : 'بانتظار المراجعة', REP.status === 'معتمد' ? 'g' : 'o')}</div></div>`;
    return screen({
      title: raw('مرحباً، ' + BT.esc(ME.name.split(' ')[0] === 'Ahmed' ? 'أحمد' : ME.name.split(' ')[0])), actions: bell(),
      body: h`<div class="d-veh"><small>سيارتك</small><div class="flex items-center gap-8"><span class="plate">${CAR.plate}</span><span style="font-size:13px;opacity:.9" class="ltr">${CAR.make} ${CAR.model} ${CAR.year}</span></div>
          <div class="gps-row"><span class="sdot"></span><span>التتبع يعمل · آخر إرسال ${fmt.ago(CAR.lastSec)}</span></div><span class="veh-ic">${icon('car', 64)}</span></div>
        ${dayCard}
        <div class="d-sec">إجراءات سريعة</div>
        <div class="qa-grid">
          <button type="button" class="qa" data-tab-go="cash"><span class="qa-ic">${icon('wallet', 18)}</span><b>رصيدي</b><small><span class="num">${fmt.kwd(ME.balance)}</span> د.ك</small></button>
          <button type="button" class="qa" data-go="receipts"><span class="qa-ic">${icon('receipt', 18)}</span><b>إيصالاتي</b><small>${pendingRc() ? pendingRc() + ' بانتظار تأكيدك' : 'كلها مؤكدة'}</small></button>
          <button type="button" class="qa" data-go="maint-new"><span class="qa-ic">${icon('wrench', 18)}</span><b>طلب صيانة</b><small>عطل أو ملاحظة</small></button>
          <button type="button" class="qa danger" data-go="accident"><span class="qa-ic">${icon('triangle-alert', 18)}</span><b>الإبلاغ عن حادث</b><small>صور + تقرير الشرطة</small></button>
        </div>`
    });
  };

  /* ---------- بدء اليوم: صورة العداد + الرقم ---------- */
  SCREENS.start = function () {
    var last = S.day === 'not-started' ? CAR.odo : 45196;
    return screen({ title: 'بدء اليوم', back: true, body: h`<form id="st-form" class="col" novalidate style="gap:12px">
      <div class="d-card col" style="gap:12px">
        ${BT.f.camera({ name: 'photo', label: 'صورة العداد', required: true, cta: 'التقط صورة العداد', sub: 'من الكاميرا فقط — لا يُسمح بالمعرض', msg: 'صورة العداد مطلوبة' })}
        ${BT.f.input({ name: 'odo', label: 'قراءة العداد', required: true, num: true, lg: true, placeholder: '000000', hint: 'آخر قراءة مسجلة للسيارة: ' + fmt.km(last) })}
      </div>
      <div class="banner info fs-sm">${icon('info', 15)}<div>اكتب الرقم كما يظهر في الصورة. أي فرق مع القراءة السابقة يظهر للمشرف.</div></div>
      <button type="submit" class="btn btn-primary d-cta">${icon('play', 18)} بدء اليوم</button></form>` });
  };
  SCREENS.start.noTabs = true;
  SCREENS.start.after = function () {
    var f = document.getElementById('st-form'), last = S.day === 'not-started' ? CAR.odo : 45196; BT.form.live(f);
    f.addEventListener('submit', function (e) {
      e.preventDefault(); if (!BT.form.validate(f)) return;
      var v = BT.form.values(f), diff = v.odo - last;
      if (diff < 0) { var fl = f.querySelector('[name=odo]').closest('.field'); fl.classList.add('invalid'); fl.querySelector('.err-msg').textContent = 'القراءة أقل من آخر قراءة (' + fmt.km(last) + ') — تأكد من الرقم'; return; }
      var done = function () { S.day = 'started'; S.dayStart = { time: '07:52', odo: v.odo }; go('home', {}, { reset: true }); BT.toast('بدأ يومك', { sub: 'العداد ' + fmt.km(v.odo) }); };
      if (diff > cfg.odoGapKm) BT.sheet.open({ title: 'فرق ' + diff + ' كم عن آخر قراءة', icon: 'triangle-alert', iconTone: 'warn', body: h`<div class="confirm-msg">آخر قراءة للسيارة <b class="num">${fmt.km(last)}</b> وقراءتك <b class="num">${fmt.km(v.odo)}</b>. سيظهر الفرق للمشرف كـ«كم خارج العمل». إذا كان الرقم خطأ عدّله.</div>`, buttons: [{ label: 'تعديل الرقم', cls: 'btn-outline' }, { label: 'الرقم صحيح', cls: 'btn-primary', onClick: function () { setTimeout(done, 200); } }] });
      else done();
    });
  };

  /* ---------- التقرير اليومي ---------- */
  SCREENS.report = function () {
    if (S.day === 'not-started') return screen({ title: 'التقرير اليومي', body: h`<div class="d-card">${BT.empty('sunrise', 'ابدأ يومك أولاً', 'التقرير اليومي يُرسل بعد بدء اليوم', h`<button type="button" class="btn btn-primary mt-8" data-d="start">بدء اليوم</button>`)}</div>` });
    if (S.day === 'sent') return screen({ title: 'التقرير اليومي', actions: bell(), body: h`<div class="d-sub">${fmt.dateLong(cfg.today)}</div>
      <div class="d-card"><div class="between"><b>تقرير اليوم</b>${BT.pill(REP.status === 'معتمد' ? 'معتمد' : 'بانتظار المراجعة', REP.status === 'معتمد' ? 'g' : 'o')}</div>
        <div class="kv mt-8"><div><span>عدد الطلبات</span><b class="num">${REP.orders}</b></div><div><span>إجمالي الكاش</span><b class="num">${fmt.kwd(REP.cash)}</b></div><div><span>عداد نهاية اليوم</span><b class="num">${fmt.km(REP.end)}</b></div><div><span>أُرسل</span><span class="num">${REP.sent}</span></div></div></div>
      <div class="d-card" style="display:flex;gap:10px;align-items:center">${icon('image', 18, 't-success')}<div class="flex-1"><b class="fs-sm">لقطة شاشة شركة التوصيل</b><div class="d-sub t-success">مرفقة ✓</div></div><button type="button" class="btn btn-sm btn-ghost" data-d="shot">عرض</button></div>
      <div class="banner note fs-sm">${icon('lock', 15)}<div>لا يمكن تعديل التقرير بعد الإرسال. إذا طلب المراجع تعديلاً يصلك إشعار بالسبب.</div></div>
      <button type="button" class="btn btn-outline" data-d="reset-day">${icon('rotate-ccw', 15)} يوم جديد (للتجربة)</button>` });
    return screen({ title: 'التقرير اليومي', actions: bell(), body: h`<div class="d-sub">${fmt.dateLong(cfg.today)} · بدأت <span class="num">${S.dayStart.time}</span></div>
      <form id="rp-form" class="col" novalidate style="gap:12px">
      <div class="d-card col" style="gap:12px">${BT.f.input({ name: 'orders', label: 'عدد الطلبات المكتملة', required: true, num: true, min: 0, max: 99, lg: true })}${BT.f.money({ name: 'cash', label: 'إجمالي الكاش المحصّل', required: true, min: 0, hint: 'كما يظهر في تطبيق شركة التوصيل' })}</div>
      <div class="d-card">${BT.f.upload({ name: 'shot', label: 'لقطة شاشة ملخص اليوم من تطبيق شركة التوصيل', required: true, accept: 'image/*', icon: 'image', accept_label: 'صورة من المعرض' })}</div>
      <div class="d-card col" style="gap:12px">${BT.f.camera({ name: 'odoPhoto', label: 'صورة عداد نهاية اليوم', required: true, sub: 'من الكاميرا فقط' })}${BT.f.input({ name: 'odo', label: 'قراءة العداد', required: true, num: true, lg: true, hint: 'عداد البداية اليوم: ' + fmt.km(S.dayStart.odo) })}</div>
      <button type="submit" class="btn btn-primary d-cta">${icon('send', 17)} إرسال للمراجعة</button></form>` });
  };
  SCREENS.report.after = function () {
    var f = document.getElementById('rp-form'); if (!f) return; BT.form.live(f);
    f.addEventListener('submit', function (e) {
      e.preventDefault(); if (!BT.form.validate(f)) return;
      var v = BT.form.values(f);
      if (v.odo < S.dayStart.odo) { var fl = f.querySelector('[name=odo]').closest('.field'); fl.classList.add('invalid'); fl.querySelector('.err-msg').textContent = 'أقل من عداد البداية ' + fmt.km(S.dayStart.odo); return; }
      BT.sheet.open({ title: 'إرسال التقرير؟', icon: 'send', body: h`<div class="kv"><div><span>الطلبات</span><b class="num">${v.orders}</b></div><div><span>الكاش</span><b class="num">${fmt.kwd(v.cash)} د.ك</b></div><div><span>كم اليوم</span><b class="num">${v.odo - S.dayStart.odo}</b></div></div><div class="d-sub mt-8">لا يمكن التعديل بعد الإرسال.</div>`,
        buttons: [{ label: 'مراجعة', cls: 'btn-outline' }, { label: 'إرسال', cls: 'btn-primary', onClick: function () { REP.orders = v.orders; REP.cash = v.cash; REP.end = v.odo; REP.start = S.dayStart.odo; REP.sent = cfg.now; REP.status = 'بانتظار المراجعة'; S.day = 'sent'; setTimeout(function () { go('done', { t: 'أُرسل التقرير للمراجعة', d: 'يصلك إشعار عند الاعتماد. أُضيف الكاش إلى رصيدك كرصيد غير معتمد.' }, { replace: true }); }, 200); } }] });
    });
  };
  SCREENS.done = function (p) { return h`<div class="success-screen"><span class="ok${p.warn ? ' warn' : ''}">${icon(p.warn ? 'triangle-alert' : 'check', 40)}</span><div class="d-title">${p.t}</div><div class="d-sub" style="line-height:1.8">${p.d}</div><button type="button" class="btn btn-primary d-cta mt-16" data-tab-go="home">الرئيسية</button></div>`; };
  SCREENS.done.noTabs = true;

  /* ---------- الكاش ---------- */
  SCREENS.cash = function () {
    var pc = Math.min(100, ME.balance / cfg.cashAlert * 100), L = D.ledger(ME).slice().reverse();
    var today = REP && REP.cash != null && REP.status !== 'معتمد' ? REP.cash : 0;
    return screen({ title: 'الكاش', actions: bell(), body: h`<div class="d-card"><div class="d-sub">رصيدك الحالي (د.ك)</div><div class="bal num">${fmt.kwd(ME.balance)}</div>
        ${today ? h`<div class="d-sub">منها <span class="num">${fmt.kwd(today)}</span> من تقرير اليوم (غير معتمد)</div>` : ''}
        <div class="meter ${pc >= 100 ? 'danger' : pc >= 85 ? 'warn' : ''} mt-12"><i style="width:${pc.toFixed(0)}%"></i></div>
        <div class="fs-sm mt-4 ${pc >= 85 ? 't-warning' : 'muted'}">${pc >= 100 ? 'تجاوزت حد التنبيه ' + fmt.kwd(cfg.cashAlert) + ' — سلّم الكاش للمحاسب' : pc >= 85 ? 'اقتربت من حد التنبيه ' + fmt.kwd(cfg.cashAlert) : 'حد التنبيه ' + fmt.kwd(cfg.cashAlert)}</div></div>
      <div class="d-sec">الحركات <button type="button" data-go="receipts">الإيصالات</button></div>
      <div class="d-card" style="padding:4px 14px">${L.map(function (x) { return h`<div class="d-row"><div class="r-main"><div class="r-t">${x.text.replace(' (غير معتمد)', '')}</div><div class="r-d"><span class="num">${fmt.date(x.date)}</span>${/غير معتمد/.test(x.text) ? ' · غير معتمد' : ''}</div></div><div class="r-v"><div class="num fw-700 ${x.amount > 0 ? 't-success' : x.amount < 0 ? 't-danger' : ''}">${x.amount == null ? fmt.kwd(x.balance) : fmt.signed(x.amount)}</div><div class="r-d num">الرصيد ${fmt.kwd(x.balance)}</div></div></div>`; })}</div>` });
  };
  SCREENS.receipts = function () {
    var R = D.receipts.filter(function (r) { return r.empId === ME.id; });
    return screen({ title: 'إيصالاتي', back: true, body: h`<div class="d-card" style="padding:4px 14px">${R.map(function (r) { return h`<button type="button" class="d-row" data-rc="${r.no}"><span class="qa-ic" style="width:36px;height:36px;border-radius:11px;background:var(--primary-soft);color:var(--primary-strong);display:flex;align-items:center;justify-content:center">${icon('receipt', 17)}</span><div class="r-main"><div class="r-t">إيصال <span class="num">${r.no}</span></div><div class="r-d"><span class="num">${fmt.date(r.date)} ${r.time}</span> · <bdi>${r.by}</bdi></div></div><div class="r-v"><div class="num fw-700">${fmt.kwd(r.amount)}</div>${BT.pill(r.status === 'مؤكد' ? 'مؤكد' : 'أكّد الاستلام', r.status === 'مؤكد' ? 'g' : 'o')}</div></button>`; })}</div>
      <div class="banner info fs-sm">${icon('info', 15)}<div>أكّد كل إيصال فقط إذا سلّمت المبلغ فعلاً. إذا كان المبلغ غير صحيح اضغط «لم أسلّم هذا المبلغ».</div></div>` });
  };
  SCREENS.receipts.after = function () {
    BT.on(viewEl, 'click', '[data-rc]', function (e, b) {
      var r = D.receipts.find(function (x) { return String(x.no) === b.getAttribute('data-rc'); }), pending = r.status !== 'مؤكد';
      BT.sheet.open({ title: 'إيصال ' + r.no, icon: 'receipt', body: h`<div class="center"><div class="d-sub">المبلغ المستلم</div><div class="bal num">${fmt.kwd(r.amount)}</div><div class="d-sub">د.ك</div></div><div class="kv mt-12"><div><span>التاريخ</span><span class="num">${fmt.date(r.date)} ${r.time}</span></div><div><span>المحاسب</span><span><bdi>${r.by}</bdi></span></div><div><span>الحالة</span>${BT.pill(r.status, pending ? 'o' : 'g')}</div></div>`,
        buttons: pending ? [{ label: 'لم أسلّم هذا المبلغ', cls: 'btn-danger', onClick: function () { setTimeout(function () { BT.toast('أُرسل اعتراضك للمشرف', { type: 'warning', sub: 'إيصال ' + r.no }); }, 200); } }, { label: 'تأكيد الاستلام', cls: 'btn-success', onClick: function () { r.status = 'مؤكد'; setTimeout(function () { go('receipts', {}, { replace: true }); BT.toast('تم تأكيد الإيصال ' + r.no); }, 200); } }] : [{ label: 'إغلاق', cls: 'btn-secondary' }] });
    });
  };

  /* ---------- الصيانة ---------- */
  SCREENS.maint = function () {
    return screen({ title: 'الصيانة', actions: bell(), body: h`<button type="button" class="btn btn-primary d-cta" data-go="maint-new">${icon('plus', 18)} طلب صيانة جديد</button>
      <div class="d-card"><div class="between"><b>الصيانة القادمة</b>${BT.pill('بعد ' + fmt.km(CAR.nextServiceKm - CAR.odo) + ' كم', 'b')}</div><div class="d-sub mt-4">تغيير زيت عند <span class="num">${fmt.km(CAR.nextServiceKm)}</span> كم</div></div>
      <div class="d-sec">طلباتي</div>
      <div class="d-card" style="padding:4px 14px">${myJobs.map(function (j) { return h`<div class="d-row"><span class="li-ic" style="width:36px;height:36px;border-radius:11px;background:var(--surface-3);display:flex;align-items:center;justify-content:center;color:var(--text-3)">${icon('wrench', 16)}</span><div class="r-main"><div class="r-t">${j.desc}</div><div class="r-d"><span class="num">${j.id}</span> · <span class="num">${fmt.date(j.date)}</span> · ${j.center}</div></div>${BT.pill(j.stage === 'تم الاستلام' ? 'مكتمل' : j.stage, j.stage === 'تم الاستلام' ? 'g' : 'b')}</div>`; })}</div>` });
  };
  SCREENS['maint-new'] = function () {
    return screen({ title: 'طلب صيانة', back: true, body: h`<form id="mn-form" class="col" novalidate style="gap:12px"><div class="d-card col" style="gap:12px">
      ${BT.f.radios({ name: 'type', label: 'نوع الطلب', required: true, value: 'عطل', options: [{ v: 'عطل', t: 'عطل' }, { v: 'صيانة دورية', t: 'صيانة دورية' }, { v: 'أخرى', t: 'أخرى' }] })}
      ${BT.f.textarea({ name: 'desc', label: 'وصف المشكلة', required: true, rows: 3, placeholder: 'مثال: صوت عند الفرملة' })}
      ${BT.f.camera({ name: 'ph', label: 'صورة', optional: true, cta: 'التقط صورة' })}
      ${BT.f.switch({ name: 'urgent', label: 'عاجل — السيارة لا تعمل' })}</div>
      <button type="submit" class="btn btn-primary d-cta">${icon('send', 17)} إرسال للمشرف</button></form>` });
  };
  SCREENS['maint-new'].noTabs = true;
  SCREENS['maint-new'].after = function () {
    var f = document.getElementById('mn-form'); BT.form.live(f);
    f.addEventListener('submit', function (e) { e.preventDefault(); if (!BT.form.validate(f)) return; var v = BT.form.values(f); myJobs.unshift({ id: 'M-27' + (10 + myJobs.length), date: cfg.today, desc: v.desc, stage: 'بانتظار المشرف', center: '—' }); go('done', { t: 'أُرسل طلب الصيانة', d: 'يراجعه المشرف ويحيله لمركز الصيانة. تستمر في العمل بالسيارة ما لم يطلب المشرف غير ذلك.' }, { replace: true }); });
  };

  /* ---------- الإبلاغ عن حادث ---------- */
  SCREENS.accident = function () {
    return screen({ title: 'الإبلاغ عن حادث', back: true, body: h`<div class="emergency">${icon('siren', 22)}<div>إذا كانت هناك إصابات اتصل بالطوارئ <a href="tel:112">112</a> أولاً.</div></div>
      <form id="ac-form" class="col" novalidate style="gap:12px">
      <div class="d-card">${BT.kv([['الوقت', h`<span class="num">${cfg.now}</span> · تلقائي`], ['الموقع', 'المهبولة · تلقائي من GPS'], ['السيارة', h`<span class="plate">${CAR.plate}</span>`]])}</div>
      <div class="d-card"><div class="label mb-8">صور السيارة <span class="t-danger">*</span></div><div class="field"><div class="cam-grid">${['أمام', 'خلف', 'يمين', 'يسار'].map(function (s) { return h`<label class="cam-tile"><span class="cam-ic">${icon('camera', 18)}</span><span>${s}</span><input type="file" accept="image/*" capture="environment" name="ph-${s}" required data-msg="التقط الصور الأربع من الكاميرا"></label>`; })}</div><div class="err-msg"></div></div></div>
      <div class="d-card col" style="gap:12px">${BT.f.radios({ name: 'police', label: 'تقرير الشرطة', required: true, value: 'later', options: [{ v: 'now', t: 'إرفاق الآن' }, { v: 'later', t: 'لاحقاً', d: 'خلال 48 ساعة' }] })}<div id="pol-up" class="hidden">${BT.f.upload({ name: 'pfile', label: 'صورة/ملف التقرير', accept: 'image/*,application/pdf' })}</div></div>
      <div class="d-card">${BT.f.select({ name: 'other', label: 'الطرف الآخر', required: true, options: ['مركبة خاصة', 'مركبة نقل', 'لا يوجد', 'أخرى'] })}<div class="mt-12">${BT.f.textarea({ name: 'desc', label: 'ماذا حدث؟', required: true, rows: 3 })}</div></div>
      <button type="submit" class="btn btn-danger-solid d-cta">${icon('send', 17)} إرسال البلاغ</button></form>` });
  };
  SCREENS.accident.noTabs = true;
  SCREENS.accident.after = function () {
    var f = document.getElementById('ac-form'); BT.form.live(f);
    BT.on(f, 'change', '[name=police]', function (e, r) { f.querySelector('#pol-up').classList.toggle('hidden', r.value !== 'now'); });
    f.addEventListener('submit', function (e) { e.preventDefault(); if (!BT.form.validate(f)) return; go('done', { warn: true, t: 'تم إرسال البلاغ A-0145', d: 'أُشعر المشرف ومدير الصيانة. ' + (BT.form.values(f).police === 'later' ? 'أرفق تقرير الشرطة من «حسابي ← الحوادث» خلال 48 ساعة — لا تُحدد المسؤولية دون تقرير.' : 'سيراجع المشرف التقرير ويحيل السيارة لتقدير التلفيات.') }, { replace: true }); });
  };

  /* ---------- حسابي ---------- */
  SCREENS.account = function () {
    var pay = D.payroll.rows.find(function (r) { return r.empId === ME.id; });
    return screen({ title: 'حسابي', body: h`<div class="d-card flex items-center gap-12">${BT.avatar(ME.name, 'lg')}<div class="flex-1"><b class="ltr" style="display:block;text-align:right">${ME.name}</b><div class="d-sub">${ME.id} · ${ME.role} · ${cfg.client}</div></div></div>
      <div class="d-card" style="padding:4px 14px">
        <button type="button" class="d-row" data-go="docs">${icon('file-badge', 18, 'text-3')}<div class="r-main"><div class="r-t">مستنداتي</div><div class="r-d">الإقامة · الرخصة · الجواز</div></div>${icon('chevron-left', 16, 'faint')}</button>
        <button type="button" class="d-row" data-d="payslip">${icon('receipt', 18, 'text-3')}<div class="r-main"><div class="r-t">الراتب</div><div class="r-d">${D.payroll.month} · صافي <span class="num">${fmt.kwd(pay.net)}</span> (بانتظار الاعتماد)</div></div>${icon('chevron-left', 16, 'faint')}</button>
        <div class="d-row">${icon('minus-circle', 18, 'text-3')}<div class="r-main"><div class="r-t">الخصومات</div><div class="r-d">لا توجد خصومات</div></div></div>
        <div class="d-row">${icon('smartphone', 18, 'text-3')}<div class="r-main"><div class="r-t">هذا الهاتف</div><div class="r-d">${ME.device.model} · مربوط منذ ${fmt.date(ME.device.since)}</div></div>${BT.pill('مربوط', 'g')}</div>
        <div class="d-row">${icon('languages', 18, 'text-3')}<div class="r-main"><div class="r-t">اللغة</div></div><div class="lang-switch"><button type="button" class="active">العربية</button><button type="button" data-d="lang">English</button></div></div>
        <a class="d-row" href="tel:+96555000111">${icon('phone', 18, 'text-3')}<div class="r-main"><div class="r-t">اتصال بالمشرف</div><div class="r-d">فهد الرشيدي</div></div>${icon('chevron-left', 16, 'faint')}</a>
      </div>
      <button type="button" class="btn btn-danger" data-d="logout">${icon('log-out', 16)} تسجيل الخروج</button>` });
  };
  SCREENS.docs = function () {
    return screen({ title: 'مستنداتي', back: true, body: h`<div class="d-card" style="padding:4px 14px">${ME.docs.map(function (d) { var n = BT.date.daysLeft(d.exp); return h`<div class="d-row">${icon('file-badge', 18, 'text-3')}<div class="r-main"><div class="r-t">${d.type}</div><div class="r-d">ينتهي <span class="num">${fmt.date(d.exp)}</span></div></div>${BT.pill(n <= 30 ? fmt.daysLabel(n) : 'ساري', n <= 30 ? 'o' : 'g')}</div>`; })}</div><div class="banner info fs-sm">${icon('bell', 15)}<div>يصلك تنبيه قبل انتهاء أي مستند بـ 30 يوماً.</div></div>` });
  };

  /* ---------- أحداث عامة ---------- */
  var D_ACT = {
    notifs: function () { BT.sheet.open({ title: 'الإشعارات', icon: 'bell', body: h`${notifs.map(function (n) { return h`<div class="d-row"><span style="width:36px;height:36px;border-radius:11px;display:flex;align-items:center;justify-content:center;flex-shrink:0;background:var(--${{ b: 'info', o: 'warning', g: 'success' }[n.tone]}-soft);color:var(--${{ b: 'info', o: 'warning', g: 'success' }[n.tone]}-text)">${icon(n.icon, 17)}</span><div class="r-main"><div class="r-t" style="font-weight:500">${n.t}</div><div class="r-d">${n.d}</div></div></div>`; })}`, buttons: [{ label: 'تم', cls: 'btn-secondary' }] }); },
    start: function () { go('start'); },
    'reset-day': function () { S.day = 'not-started'; REP.orders = null; REP.cash = null; go('home', {}, { reset: true }); BT.toast('يوم جديد للتجربة', { type: 'info', sub: 'ابدأ اليوم ثم أرسل التقرير' }); },
    shot: function () { BT.lightbox({ html: h`<div class="shot lg" style="cursor:default"><div class="shot-in"><div class="s-top"><span>${REP.sent}</span><span>▮▮▮</span></div><div style="font-weight:700;margin-top:8px">ملخص اليوم</div><div class="s-box"><small>الطلبات المكتملة</small><b>${REP.orders}</b></div><div class="s-box"><small>النقد المحصّل (د.ك)</small><b>${fmt.kwd(REP.cash)}</b></div></div></div>`, caption: 'لقطة الشاشة المرفوعة' }); },
    payslip: function () { var r = D.payroll.rows.find(function (x) { return x.empId === ME.id; }); BT.sheet.open({ title: 'راتب ' + D.payroll.month, icon: 'receipt', body: h`<div class="kv"><div><span>الأساسي</span><span class="num">${fmt.kwd(r.basic)}</span></div><div><span>الحوافز</span><span class="num">${fmt.kwd(r.incentives)}</span></div><div><span>الخصومات</span><span class="num">${fmt.kwd(r.deductions)}</span></div><div class="total"><span>الصافي</span><b class="num">${fmt.kwd(r.net)} د.ك</b></div></div><div class="d-sub mt-8">بانتظار اعتماد الكشف — قد يتغير قبل الإقفال.</div>`, buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }] }); },
    'ob-rejected': function () { S.ob.status = 'rejected'; S.ob.note = 'صورة الإقامة غير واضحة، صوّرها من جديد'; go('onboard', { step: 0 }, { reset: true }); },
    lang: function () { BT.toast('English is available in the production app', { type: 'info', sub: 'هذا القالب بالعربية فقط' }); },
    resend: function () { BT.toast('أُرسل رمز جديد'); },
    logout: function () { BT.confirm({ sheet: true, title: 'تسجيل الخروج', message: 'لن يُرسل موقعك بعد تسجيل الخروج. إذا كانت السيارة معك يُنبَّه المشرف.', confirmText: 'تسجيل الخروج', tone: 'danger', icon: 'log-out' }).then(function (r) { if (r.ok) go('login', {}, { reset: true }); }); }
  };

  function boot() {
    root = document.getElementById('screen-root'); viewEl = document.getElementById('app-view'); tabEl = document.getElementById('tabbar');
    BT.ui.root = root; // النوافذ والإشعارات داخل شاشة الهاتف
    root.addEventListener('click', function (e) {
      var t = e.target.closest('[data-tab-go],[data-go],[data-d],[data-back]'); if (!t) return;
      if (t.hasAttribute('data-back')) return back();
      if (t.hasAttribute('data-tab-go')) return go(t.getAttribute('data-tab-go'), {}, { reset: true });
      if (t.hasAttribute('data-go')) return go(t.getAttribute('data-go'));
      var fn = D_ACT[t.getAttribute('data-d')]; if (fn) fn();
    });
    var jumps = [['onboard', 'التسجيل الأول'], ['ob-wait', 'بانتظار المراجعة'], ['login', 'الدخول و OTP'], ['home', 'الرئيسية'], ['start', 'بدء اليوم'], ['report-new', 'التقرير اليومي'], ['cash', 'الكاش'], ['receipts', 'تأكيد إيصال'], ['maint-new', 'طلب صيانة'], ['accident', 'حادث'], ['account', 'حسابي']];
    BT.render(document.getElementById('jump'), h`${jumps.map(function (j) { return h`<button type="button" class="chip" data-jump="${j[0]}">${j[1]}</button>`; })}`);
    BT.on(document.getElementById('jump'), 'click', '[data-jump]', function (e, b) {
      var k = b.getAttribute('data-jump');
      if (k === 'report-new') { S.day = 'started'; REP.orders = null; return go('report', {}, { reset: true }); }
      if (k === 'start') { S.day = 'not-started'; return go('start', {}, { reset: true }); }
      if (k === 'onboard') { S.ob = { status: 'draft', note: null, data: {} }; return go('onboard', { step: 0 }, { reset: true }); }
      go(k, {}, { reset: true });
    });
    setInterval(function () { var d = new Date(); var el = document.getElementById('sb-time'); if (el) el.textContent = d.getHours() + ':' + String(d.getMinutes()).padStart(2, '0'); }, 20000);
    BT.hydrate(document);
    go(location.hash === '#login' ? 'login' : 'home', {}, { reset: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else setTimeout(boot, 0);
})();
