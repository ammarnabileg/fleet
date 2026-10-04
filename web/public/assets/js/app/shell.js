/* =====================================================================
   BrilliantTech — app/shell.js  (هيكل لوحة الإدارة المربوطة بالخادم)
   القائمة حسب صلاحيات المستخدم، التنبيهات، قائمة المستخدم، البحث، والتنقل.
   كل صفحة في assets/js/app/pages/*.js وتسجّل نفسها في BT.pages['key'].
   قالب الواجهات القديم ببيانات تجريبية بقي في demo.html للعرض فقط.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, api = BT.api;
  var A = BT.A = BT.A || {};
  BT.pages = BT.pages || {};
  A.counts = {};

  var IMPORT_PERMS = ['employees.create', 'employees.update', 'vehicles.create', 'vehicles.update', 'documents.manage'];

  /* ---------- القائمة الجانبية: لا يظهر إلا ما يملك المستخدم صلاحيته ---------- */
  A.NAV = [
    { sec: null, items: [
      { key: 'dashboard', icon: 'house', label: 'لوحة التحكم', any: ['dashboard.view'] },
      { key: 'tracking', icon: 'map', label: 'التتبع الحي', any: ['tracking.live'], count: 'signal_lost', hot: true },
      { key: 'alerts', icon: 'bell-ring', label: 'التنبيهات', count: 'alerts', hot: true },
      { key: 'vehicles', icon: 'car', label: 'السيارات', any: ['vehicles.view'] },
      { key: 'custody', icon: 'key-round', label: 'العُهد والتسليم', any: ['custody.view'] },
      { key: 'odometer', icon: 'gauge', label: 'العداد', any: ['odometer.view'], count: 'odometer' },
      { key: 'daily', icon: 'clipboard-list', label: 'التقارير اليومية', any: ['daily_reports.view'], count: 'daily' },
      { key: 'maintenance', icon: 'wrench', label: 'الصيانة', any: ['maintenance.view', 'invoices.view'], count: 'maintenance' },
      { key: 'accidents', icon: 'shield-alert', label: 'الحوادث', any: ['accidents.view'], count: 'accidents' },
      { key: 'fines', icon: 'file-warning', label: 'المخالفات المرورية', any: ['fines.view'], count: 'fines' },
      { key: 'cash', icon: 'wallet', label: 'الكاش والخزينة', any: ['cash.view', 'treasury.view'] },
      { key: 'deductions', icon: 'minus-circle', label: 'الخصومات', any: ['deductions.view'] },
      { key: 'employees', icon: 'users', label: 'الموظفون والسائقون', any: ['employees.view'], count: 'onboarding' },
      { key: 'reports', icon: 'chart-column', label: 'التقارير', any: ['reports.view', 'cash.view'] }
    ] },
    { sec: 'الإدارة', items: [
      { key: 'import', icon: 'file-spreadsheet', label: 'استيراد البيانات', all: IMPORT_PERMS },
      { key: 'settings', icon: 'settings', label: 'الإعدادات والصلاحيات', any: ['settings.view', 'users.view', 'roles.view', 'companies.view', 'branches.manage', 'i18n.manage'] },
      { key: 'integrations', icon: 'puzzle', label: 'التكاملات', any: ['integrations.manage'] },
      { key: 'audit', icon: 'shield-check', label: 'سجل التدقيق', any: ['audit.view'] }
    ] }
  ];
  A.allowed = function (it) {
    if (!it) return false;
    if (it.all) return it.all.every(api.can);
    return !it.any || api.canAny(it.any);
  };
  A.navItem = function (key) { var f = null; A.NAV.forEach(function (s) { s.items.forEach(function (i) { if (i.key === key) f = i; }); }); return f; };
  A.firstAllowed = function () { var f = null; A.NAV.forEach(function (s) { s.items.forEach(function (i) { if (!f && A.allowed(i)) f = i.key; }); }); return f || 'alerts'; };

  A.renderNav = function (active) {
    BT.render(document.getElementById('nav'), h`${A.NAV.map(function (s) {
      var items = s.items.filter(A.allowed);
      if (!items.length) return '';
      return h`${s.sec ? h`<div class="nav-sec">${s.sec}</div>` : ''}${items.map(function (it) {
        var c = it.count ? A.counts[it.count] : null;
        return h`<a class="nav-item${it.key === active ? ' active' : ''}" href="#/${it.key}"${it.key === active ? raw(' aria-current="page"') : ''}>${icon(it.icon, 17)}<span>${it.label}</span>${c ? h`<span class="count${it.hot ? ' hot' : ''}">${c >= 200 ? '200+' : c}</span>` : ''}</a>`;
      })}`;
    })}`);
  };

  /* ---------- أدوات مشتركة للصفحات ---------- */
  A.view = function () { return document.getElementById('view'); };
  A.setTitle = function (title, crumbs) {
    document.title = title + ' — ' + (A.brand || BT.config.systemName);
    BT.render(document.getElementById('tb-title'), h`${crumbs && crumbs.length ? h`<div class="crumbs">${crumbs.map(function (c, i) { return h`${i ? icon('chevron-left', 12) : ''}${c[1] ? h`<a href="#/${c[1]}">${c[0]}</a>` : c[0]}`; })}</div>` : h`<div class="crumbs">${A.brand || ''}${A.brand ? ' · ' : ''}${BT.fmt.dateLong(BT.config.today)}</div>`}<h1>${title}</h1>`);
  };
  A.head = function (title, sub, actions) {
    return h`<div class="page-head"><div><h2>${title}</h2>${sub ? h`<p>${sub}</p>` : ''}</div>${actions ? h`<div class="page-actions">${actions}</div>` : ''}</div>`;
  };
  A.btn = function (label, opts) {
    opts = opts || {};
    return h`<button type="button" class="btn ${opts.cls || 'btn-secondary'}"${opts.action ? h` data-action="${opts.action}"` : ''}${opts.arg != null ? h` data-arg="${opts.arg}"` : ''}${opts.id ? h` id="${opts.id}"` : ''}>${opts.icon ? icon(opts.icon, 15) : ''}${label}</button>`;
  };
  A.go = function (path) { A.router.go(path); };
  A.spinner = function (text) { return h`<div class="page-loading"><span class="spinner"></span>${text || 'جاري التحميل…'}</div>`; };
  A.errorBox = function (err) {
    return h`<div class="card"><div class="card-b">${BT.empty('wifi-off', 'تعذر تحميل البيانات', api.message(err), raw('<button type="button" class="btn btn-sm btn-secondary mt-8" data-action="reload">إعادة المحاولة</button>'))}</div></div>`;
  };
  BT.actions['reload'] = function () { A.router.refresh(); };
  /* يعرض التحميل ثم المحتوى، أو رسالة خطأ مع إعادة المحاولة. el مثبّت عند بداية الصفحة. */
  A.load = function (el, promise, render) {
    BT.render(el, A.spinner());
    return Promise.resolve(promise).then(function (data) { if (document.contains(el)) { BT.render(el, render(data)); } return data; }, function (err) {
      if (err instanceof api.ApiError && err.status === 401) return;
      if (document.contains(el)) BT.render(el, A.errorBox(err));
      throw err;
    });
  };
  A.forbidden = function () {
    return h`<div class="card"><div class="card-b">${BT.empty('lock', 'لا تملك صلاحية هذه الصفحة', 'اطلب من مدير النظام إضافة الصلاحية إلى دورك.')}</div></div>`;
  };
  /* تنظيف عند مغادرة الصفحة (مثل إغلاق اتصال الخريطة الحية) */
  var leaving = [];
  A.onLeave = function (fn) { leaving.push(fn); };

  A.person = function (ref, sub) { return ref ? BT.person(api.name(ref.name) || '—', sub) : raw('<span class="muted">—</span>'); };
  A.plate = function (plate, id) { return plate ? (id && api.can('vehicles.view') ? h`<a class="plate" href="#/vehicles/${id}">${plate}</a>` : BT.plate(plate)) : '—'; };
  A.tone = {
    vehicle_status: { available: 'o', assigned: 'g', maintenance: 'b', accident: 'r', inactive: 'n' },
    app_access: { none: 'n', active: 'g', suspended: 'o', disabled: 'r' },
    severity: { info: 'b', warning: 'o', critical: 'r' },
    onboarding_status: { none: 'n', draft: 'n', submitted: 'o', approved: 'g', rejected: 'r' },
    link_status: { queued: 'b', sent: 'g', failed: 'r', cancelled: 'n', already_queued: 'b' },
    journal_status: { pending: 'o', posted: 'g', rejected: 'r' },
    report_status: { submitted: 'o', approved: 'g', rejected: 'r' },
    custody_kind: { normal: 'n', emergency: 'r' }
  };
  A.pill = function (ns, code, tone) { return BT.pill(api.t(ns, code), tone || (A.tone[ns] || {})[code] || 'n'); };
  A.options = function (ns, codes) { return codes.map(function (c) { return { v: c, t: api.t(ns, c) }; }); };

  /* صور محمية بالجلسة: تُفتح بالضغط في عارض الصور */
  A.thumbs = function (items) { // [{src, caption}]
    if (!items.length) return raw('<div class="muted fs-sm">لا توجد صور</div>');
    var key = BT.uid('th');
    A._thumbs = A._thumbs || {};
    A._thumbs[key] = items;
    return h`<div class="thumbs">${items.map(function (it, i) { return h`<figure data-thumbs="${key}" data-i="${i}"><img src="${it.src}" alt="${it.caption || ''}" loading="lazy"><figcaption>${it.caption || ''}</figcaption></figure>`; })}</div>`;
  };
  document.addEventListener('click', function (e) {
    var f = e.target.closest && e.target.closest('[data-thumbs]');
    if (!f) return;
    BT.lightbox(A._thumbs[f.getAttribute('data-thumbs')] || [], +f.getAttribute('data-i'));
  });

  /* نموذج في نافذة: onSubmit يعيد Promise، والخطأ يبقي النافذة مفتوحة مع رسالة */
  A.formModal = function (o) {
    return BT.modal.open({
      title: o.title, subtitle: o.subtitle, icon: o.icon, size: o.size, form: true,
      body: o.body,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: o.submitText || 'حفظ', cls: o.submitCls || 'btn-primary', submit: true }],
      onOpen: o.onOpen,
      onSubmit: function (vals, dlg) {
        return Promise.resolve(o.submit(vals, dlg)).then(function (res) {
          if (o.done !== false) BT.toast(o.done || 'تم الحفظ');
          if (o.after) o.after(res);
          return res === false ? false : true;
        }).catch(api.fail);
      }
    });
  };
  /* إجراء بتأكيد (وسبب إن لزم) */
  A.confirmRun = function (o) {
    return BT.confirm(o).then(function (r) {
      if (!r.ok) return null;
      return Promise.resolve(o.run(r.reason)).then(function (res) { if (o.done) BT.toast(o.done); if (o.after) o.after(res); return res; }, function (err) { BT.toast(api.message(err), { type: 'error', timeout: 6000 }); });
    });
  };
  A.loadScript = function (src) {
    A._scripts = A._scripts || {};
    if (!A._scripts[src]) A._scripts[src] = new Promise(function (ok, bad) { var s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = bad; document.head.appendChild(s); });
    return A._scripts[src];
  };
  A.loadCss = function (href) { if (!document.querySelector('link[href="' + href + '"]')) { var l = document.createElement('link'); l.rel = 'stylesheet'; l.href = href; document.head.appendChild(l); } };
  A.download = function (path, query) { var a = document.createElement('a'); a.href = api.url(path, query); a.download = ''; document.body.appendChild(a); a.click(); a.remove(); };
  A.query = function (q) { return Object.keys(q).filter(function (k) { return q[k] != null && q[k] !== ''; }).map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(q[k]); }).join('&'); };

  /* ---------- العدادات في القائمة (كل دقيقة) ---------- */
  A.refreshCounts = function () {
    var jobs = [api.get('/alerts', { limit: 200 }).then(function (r) { A.counts.alerts = r.length; }, function () {})];
    if (api.can('dashboard.view')) jobs.push(api.get('/dashboard').then(function (d) {
      A.counts.daily = d.daily_reports ? d.daily_reports.waiting_review : null;
      A.counts.signal_lost = d.drivers ? d.drivers.signal_lost : null;
    }, function () {}));
    if (api.can('odometer.view')) jobs.push(api.get('/odometer/readings', { review_status: 'pending', limit: 200 }).then(function (r) { A.counts.odometer = r.length; }, function () {}));
    if (api.can('maintenance.approve')) jobs.push(api.get('/maintenance/requests', { status: 'requested,quote_pending', limit: 200 }).then(function (r) { A.counts.maintenance = r.length; }, function () {}));
    if (api.can('fines.manage') || api.can('deductions.manage')) jobs.push(api.get('/fines', { status: 'open', limit: 200 }).then(function (r) { A.counts.fines = r.length; }, function () {}));
    if (api.can('accidents.view')) jobs.push(api.get('/accidents', { stage: api.can('accidents.approve') ? 'reported,estimate_pending,awaiting_outcome' : 'reported,estimate_pending', limit: 200 }).then(function (r) { A.counts.accidents = r.length; }, function () {}));
    if (api.can('employees.onboarding')) jobs.push(api.get('/onboarding', { status: 'submitted', limit: 200 }).then(function (r) { A.counts.onboarding = r.length; }, function () {}));
    return Promise.all(jobs).then(function () {
      A.renderNav((A.router && A.router.current || '').split('/')[0]);
      A.updateBell();
    });
  };

  /* ---------- التنبيهات ---------- */
  A.updateBell = function () {
    var b = document.getElementById('bell-badge'), n = A.counts.alerts || 0;
    if (b) { b.textContent = n >= 200 ? '200+' : n; b.hidden = !n; }
  };
  BT.actions['notifications'] = function (arg, el) {
    var pop = BT.popover(el, h`<div class="nm-h"><b>التنبيهات المفتوحة</b><a class="btn btn-link fs-sm" href="#/alerts">عرض الكل</a></div><div class="nm-list" data-alerts>${A.spinner()}</div>`, { cls: 'notif-menu' });
    if (!pop) return;
    api.get('/alerts', { limit: 15 }).then(function (rows) {
      var list = pop.querySelector('[data-alerts]');
      if (!list) return;
      if (!rows.length) { BT.render(list, BT.empty('bell', 'لا توجد تنبيهات مفتوحة')); return; }
      BT.render(list, h`${rows.map(function (a) {
        var tone = { critical: 'danger', warning: 'warning', info: 'info' }[a.severity];
        return h`<div class="notif" style="cursor:default"><span class="li-ic" style="width:34px;height:34px;border-radius:9px;display:flex;align-items:center;justify-content:center;flex-shrink:0;background:var(--${tone}-soft);color:var(--${tone}-text)">${icon(a.severity === 'critical' ? 'siren' : a.severity === 'warning' ? 'triangle-alert' : 'info', 16)}</span><span class="flex-1"><span class="n-t" style="display:block">${a.message}</span><span class="n-d">${BT.fmt.since(a.created_at)}</span></span><button type="button" class="btn btn-sm btn-ghost" data-ack="${a.id}" title="تم الاطلاع">${icon('check', 14)}</button></div>`;
      })}`);
      BT.on(list, 'click', '[data-ack]', function (e, b) {
        b.disabled = true;
        api.post('/alerts/' + b.getAttribute('data-ack') + '/ack').then(function () { b.closest('.notif').remove(); A.counts.alerts = Math.max(0, (A.counts.alerts || 1) - 1); A.updateBell(); A.renderNav(A.router.current.split('/')[0]); }, function (err) { b.disabled = false; BT.toast(api.message(err), { type: 'error' }); });
      });
    }, function (err) { var list = pop.querySelector('[data-alerts]'); if (list) BT.render(list, BT.empty('wifi-off', api.message(err))); });
  };

  /* ---------- قائمة المستخدم ---------- */
  BT.actions['user-menu'] = function (arg, el) {
    var dark = BT.theme.get() === 'dark';
    BT.menu(el, [
      { head: api.me.full_name + ' · ' + api.me.username },
      { label: 'تغيير كلمة المرور', icon: 'key-round', onClick: function () { A.changePassword(false); } },
      { label: 'التحقق بخطوتين', icon: 'shield-check', onClick: A.setupMfa },
      { sep: true },
      { label: dark ? 'الوضع الفاتح' : 'الوضع الداكن', icon: dark ? 'sun' : 'moon', onClick: function () { BT.theme.toggle(); } },
      { sep: true },
      { label: 'تسجيل الخروج', icon: 'log-out', danger: true, onClick: A.logout }
    ], { focus: true });
  };
  A.logout = function () {
    api.post('/auth/logout').then(null, function () { /* الجلسة منتهية أصلاً */ }).then(function () { location.href = 'login.html'; });
  };
  A.changePassword = function (forced) {
    return BT.modal.open({
      title: forced ? 'غيّر كلمة المرور للمتابعة' : 'تغيير كلمة المرور', icon: 'key-round', size: 'sm', form: true, dismissible: !forced,
      subtitle: forced ? 'كلمة المرور الحالية مؤقتة، اختر كلمة مرور جديدة خاصة بك' : null,
      body: h`<div class="form">${BT.f.input({ name: 'old', label: 'كلمة المرور الحالية', type: 'password', required: true })}
        ${BT.f.input({ name: 'pw', label: 'كلمة المرور الجديدة', type: 'password', required: true, hint: 'كلمة طويلة يصعب تخمينها؛ الخادم يرفض القصيرة' })}
        ${BT.f.input({ name: 'pw2', label: 'تأكيد كلمة المرور', type: 'password', required: true, validate: 'samePw' })}</div>`,
      buttons: forced ? [{ label: 'تسجيل الخروج', cls: 'btn-ghost', onClick: function () { A.logout(); return false; } }, { label: 'حفظ', cls: 'btn-primary', submit: true }] : [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ', cls: 'btn-primary', submit: true }],
      onSubmit: function (v) {
        return api.post('/auth/password', { current_password: v.old, new_password: v.pw }).then(function () {
          api.me.must_change_password = false;
          BT.toast('تم تغيير كلمة المرور');
        }).catch(api.fail);
      }
    }).promise;
  };
  BT.validators.samePw = function (v, el, form) { return v === form.querySelector('[name=pw]').value ? '' : 'كلمتا المرور غير متطابقتين'; };

  A.setupMfa = function () {
    BT.confirm({ title: 'التحقق بخطوتين', icon: 'shield-check', message: 'ستحتاج تطبيق مصادقة على جوالك (Google Authenticator أو Microsoft Authenticator). بعد التفعيل يُطلب الرمز من التطبيق عند كل دخول. إن كان مفعّلاً، يستبدل هذا الإعداد المفتاح القديم.', confirmText: 'متابعة' }).then(function (r) {
      if (!r.ok) return;
      Promise.all([api.post('/auth/mfa/setup'), A.loadScript('assets/vendor/qrcode/qrcode.js')]).then(function (res) {
        var uri = res[0].otpauth_uri, secret = (uri.match(/secret=([A-Z2-7]+)/i) || [])[1] || '';
        var qr = window.qrcode(0, 'M'); qr.addData(uri); qr.make();
        BT.modal.open({
          title: 'امسح الرمز بتطبيق المصادقة', icon: 'shield-check', size: 'sm', form: true,
          body: h`<div class="center">${raw(qr.createSvgTag({ cellSize: 5, margin: 2, scalable: true }).replace('<svg ', '<svg style="width:220px;height:220px;background:#fff;border-radius:12px" '))}</div>
            <p class="muted fs-sm mt-8">أو أدخل المفتاح يدوياً: <b class="num ltr" style="word-break:break-all">${secret}</b></p>
            <div class="form mt-12">${BT.f.input({ name: 'code', label: 'الرمز الظاهر في التطبيق', required: true, num: true, maxlength: 6, pattern: '\\d{6}', msg: '6 أرقام' })}</div>`,
          buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'تفعيل', cls: 'btn-primary', submit: true }],
          onSubmit: function (v) {
            return api.post('/auth/mfa/enable', { code: String(v.code).padStart(6, '0') }).then(function () { BT.toast('تم تفعيل التحقق بخطوتين'); }).catch(api.fail);
          }
        });
      }, api.fail).catch(function () {});
    });
  };

  /* ---------- نطاق الشركات ---------- */
  BT.actions['switch-branch'] = function (arg, el) {
    var mine = api.me.all_companies ? api.companies : api.companies.filter(function (c) { return api.me.company_ids.indexOf(c.id) > -1; });
    BT.menu(el, [{ head: api.me.all_companies ? 'صلاحيتك تشمل كل الشركات' : 'الشركات ضمن صلاحيتك' }].concat(mine.map(function (c) {
      return { label: api.name(c.name), icon: 'building-2', sub: c.is_active ? '' : 'غير نشطة' };
    })), { align: 'start' });
  };
  function scopeLabel() {
    var mine = api.me.all_companies ? api.companies : api.companies.filter(function (c) { return api.me.company_ids.indexOf(c.id) > -1; });
    if (mine.length === 1) return api.name(mine[0].name);
    return api.me.all_companies ? 'كل الشركات' : mine.length + ' شركات';
  }

  /* ---------- البحث (Ctrl + K) ---------- */
  BT.openSearch = function () {
    BT.cmdk({
      placeholder: 'اكتب اسم صفحة، أو رقم لوحة، أو اسم سائق ثم Enter…',
      source: function () {
        var out = [];
        A.NAV.forEach(function (s) { s.items.filter(A.allowed).forEach(function (it) { out.push({ group: 'الصفحات', label: it.label, icon: it.icon, run: function () { A.go(it.key); } }); }); });
        if (api.can('vehicles.view')) out.push({ group: 'بحث', label: 'بحث في السيارات…', icon: 'car', keywords: 'لوحة سيارة plate', run: function () { A.go('vehicles'); } });
        if (api.can('employees.view')) out.push({ group: 'بحث', label: 'بحث في الموظفين والسائقين…', icon: 'users', keywords: 'سائق موظف driver', run: function () { A.go('employees'); } });
        out.push({ group: 'إجراءات', label: BT.theme.get() === 'dark' ? 'الوضع الفاتح' : 'الوضع الداكن', icon: 'moon', run: BT.theme.toggle });
        return out;
      }
    });
  };
  BT.actions['search'] = function () { BT.openSearch(); };
  BT.actions['toggle-nav'] = function () { document.getElementById('app').classList.toggle('nav-open'); };
  BT.actions['theme'] = function () { BT.theme.toggle(); };

  /* ---------- التشغيل ---------- */
  function fillUser() {
    var me = api.me;
    document.querySelectorAll('[data-me-name]').forEach(function (e) { e.textContent = me.full_name; });
    document.querySelectorAll('[data-me-sub]').forEach(function (e) { e.textContent = me.is_superuser ? 'مدير النظام' : me.username; });
    document.querySelectorAll('[data-me-av]').forEach(function (e) { e.textContent = BT.fmt.initials(me.full_name); });
    document.querySelectorAll('[data-scope]').forEach(function (e) { e.textContent = scopeLabel(); });
  }
  function boot() {
    BT.hydrate(document);
    BT.render(A.view(), A.spinner('جاري فتح الجلسة…'));
    api.boot().then(function () {
      api.get('/branding', null, { noRedirect: true }).then(function (b) { A.brand = b.display_name; document.querySelectorAll('[data-brand]').forEach(function (e) { e.textContent = b.display_name; }); if (A.router) A.router.refresh(); }, function () {});
      fillUser();
      var routes = {};
      Object.keys(BT.pages).forEach(function (k) {
        routes[k] = function (p, q) {
          var it = A.navItem(k.split('/')[0]);
          if (it && !A.allowed(it)) { A.setTitle(it.label); BT.render(A.view(), A.forbidden()); return; }
          BT.pages[k](p, q);
        };
      });
      A.router = BT.router(routes, {
        default: A.firstAllowed(),
        view: A.view,
        onBefore: function (r) {
          leaving.splice(0).forEach(function (fn) { try { fn(); } catch (e) { /* ignore */ } });
          BT.closeAll(); BT.closeMenu();
          var old = A.view(), fresh = old.cloneNode(false); old.replaceWith(fresh);
          document.getElementById('app').classList.remove('nav-open');
          A.renderNav(r.current.split('/')[0]);
          window.scrollTo(0, 0);
          var m = document.querySelector('.main'); if (m) m.scrollTop = 0;
        }
      });
      BT.on(document.getElementById('sidebar'), 'click', '.nav-item', function () { document.getElementById('app').classList.remove('nav-open'); });
      document.querySelector('.sb-backdrop').addEventListener('click', function () { document.getElementById('app').classList.remove('nav-open'); });
      var start = function () {
        A.router.start();
        A.refreshCounts();
        setInterval(function () { if (!document.hidden) A.refreshCounts(); }, (BT.config.refreshCountsSec || 60) * 1000);
      };
      if (api.me.must_change_password) A.changePassword(true).then(start); else start();
    }, function (err) {
      if (err instanceof api.ApiError && err.status === 401) return; // إلى صفحة الدخول
      BT.render(A.view(), A.errorBox(err));
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else setTimeout(boot, 0);
})();
