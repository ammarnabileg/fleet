/* =====================================================================
   BrilliantTech UI — admin.js  (هيكل لوحة الإدارة)
   القائمة الجانبية، الشريط العلوي، الإشعارات، قائمة المستخدم، البحث
   (Ctrl+K)، والتنقل. كل صفحة موجودة في assets/js/pages/*.js وتسجّل
   نفسها في BT.pages['اسم-الصفحة'].
   لإضافة صفحة جديدة: أضفها في A.NAV هنا + اكتب BT.pages['key'] = function(params){...}
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, D = BT.data;
  var A = BT.A = BT.A || {};
  BT.pages = BT.pages || {};

  /* ---------- القائمة الجانبية ---------- */
  A.NAV = [
    { sec: null, items: [
      { key: 'dashboard', icon: 'house', label: 'لوحة التحكم' },
      { key: 'tracking', icon: 'map', label: 'التتبع الحي', count: function () { return D.vehicles.filter(function (v) { return v.signal === 'انقطاع'; }).length; }, hot: true },
      { key: 'vehicles', icon: 'car', label: 'السيارات' },
      { key: 'handover', icon: 'key-round', label: 'تسليم السيارات' },
      { key: 'odometer', icon: 'gauge', label: 'العداد', count: function () { return D.odoReviews.filter(function (x) { return x.status === 'بانتظار المراجعة'; }).length; } },
      { key: 'daily', icon: 'clipboard-list', label: 'العمل اليومي', count: function () { return D.reportStats().review; } },
      { key: 'cash', icon: 'wallet', label: 'الكاش والخزينة' },
      { key: 'maintenance', icon: 'wrench', label: 'الصيانة', count: function () { return D.jobs.filter(function (j) { return j.stage !== 'تم الاستلام'; }).length; } },
      { key: 'accidents', icon: 'triangle-alert', label: 'الحوادث', count: function () { return D.accidents.filter(function (a) { return a.status.indexOf('مغلق') < 0; }).length; } },
      { key: 'employees', icon: 'users', label: 'الموظفون' },
      { key: 'payroll', icon: 'receipt', label: 'الرواتب' },
      { key: 'finance', icon: 'landmark', label: 'المالية' },
      { key: 'reports', icon: 'chart-column', label: 'التقارير' }
    ] },
    { sec: 'الإدارة', items: [
      { key: 'approvals', icon: 'badge-check', label: 'الاعتمادات', count: function () { return D.approvals.length; }, hot: true },
      { key: 'settings', icon: 'settings', label: 'الإعدادات والصلاحيات' },
      { key: 'audit', icon: 'shield-check', label: 'سجل التدقيق' }
    ] }
  ];
  A.labelOf = function (key) { var f = null; A.NAV.forEach(function (s) { s.items.forEach(function (i) { if (i.key === key) f = i; }); }); return f; };

  A.renderNav = function (active) {
    var nav = document.getElementById('nav');
    BT.render(nav, h`${A.NAV.map(function (s) {
      return h`${s.sec ? h`<div class="nav-sec">${s.sec}</div>` : ''}${s.items.map(function (it) {
        var c = it.count ? it.count() : null;
        return h`<a class="nav-item${it.key === active ? ' active' : ''}" href="#/${it.key}"${it.key === active ? raw(' aria-current="page"') : ''}>${icon(it.icon, 17)}<span>${it.label}</span>${c ? h`<span class="count${it.hot ? ' hot' : ''}">${c}</span>` : ''}</a>`;
      })}`;
    })}`);
  };

  /* ---------- أدوات مشتركة للصفحات ---------- */
  A.slug = function (plate) { return String(plate).replace('/', '-'); };
  A.unslug = function (s) { return String(s).replace('-', '/'); };
  A.view = function () { return document.getElementById('view'); };
  A.setTitle = function (title, crumbs) {
    document.title = title + ' — ' + BT.config.systemName;
    BT.render(document.getElementById('tb-title'), h`${crumbs && crumbs.length ? h`<div class="crumbs">${crumbs.map(function (c, i) { return h`${i ? icon('chevron-left', 12) : ''}${c[1] ? h`<a href="#/${c[1]}">${c[0]}</a>` : c[0]}`; })}</div>` : h`<div class="crumbs">${BT.config.client} · ${fmt.dateLong(BT.config.today)}</div>`}<h1>${title}</h1>`);
  };
  A.head = function (title, sub, actions) {
    return h`<div class="page-head"><div><h2>${title}</h2>${sub ? h`<p>${sub}</p>` : ''}</div>${actions ? h`<div class="page-actions">${actions}</div>` : ''}</div>`;
  };
  A.veh = function (v, noModel) {
    if (!v) return '—';
    return h`<a class="plate" href="#/vehicles/${A.slug(v.plate)}">${v.plate}</a>${noModel ? '' : h`<span class="sub ltr">${v.make} ${v.model} ${v.year}</span>`}`;
  };
  A.drv = function (name, sub) { return name ? BT.person(name, sub) : BT.raw('<span class="muted">بلا سائق</span>'); };
  A.go = function (path) { A.router.go(path); };
  A.soon = function (what) { BT.toast(what, { type: 'info', sub: 'واجهة فقط في هذا القالب — تُربط بالنظام الفعلي عند التنفيذ' }); };
  A.exportToast = function (name, format) { BT.toast('جاري تجهيز ' + name + ' (' + (format || 'Excel') + ')', { type: 'info', sub: 'سيبدأ التحميل تلقائياً عند الانتهاء' }); };
  A.btn = function (label, opts) { // A.btn('إضافة', {icon, cls, action, arg})
    opts = opts || {};
    return h`<button type="button" class="btn ${opts.cls || 'btn-secondary'}"${opts.action ? h` data-action="${opts.action}"` : ''}${opts.arg != null ? h` data-arg="${opts.arg}"` : ''}${opts.id ? h` id="${opts.id}"` : ''}>${opts.icon ? icon(opts.icon, 15) : ''}${label}</button>`;
  };

  /* ---------- الإشعارات ---------- */
  BT.actions['notifications'] = function (arg, el) {
    var unread = D.notifications.filter(function (n) { return n.unread; }).length;
    BT.popover(el, h`<div class="nm-h"><b>الإشعارات</b>${unread ? h`<button type="button" class="btn btn-link fs-sm" data-mark-read>تحديد الكل كمقروء</button>` : raw('<span class="muted fs-sm">لا يوجد جديد</span>')}</div>
      <div class="nm-list">${D.notifications.map(function (n) {
        return h`<button type="button" class="notif${n.unread ? ' unread' : ''}" data-link="${n.link}"><span class="li-ic ${n.tone}" style="width:34px;height:34px;border-radius:9px;display:flex;align-items:center;justify-content:center;flex-shrink:0;background:var(--${{ r: 'danger', o: 'warning', b: 'info', g: 'success' }[n.tone]}-soft);color:var(--${{ r: 'danger', o: 'warning', b: 'info', g: 'success' }[n.tone]}-text)">${icon(n.icon, 16)}</span><span><span class="n-t" style="display:block">${n.text}</span><span class="n-d">${n.at}</span></span></button>`;
      })}</div><div class="nm-f"><a class="btn btn-ghost btn-sm" href="#/settings?tab=notify">إعدادات الإشعارات</a></div>`, {
      cls: 'notif-menu',
      onOpen: function (pop) {
        BT.on(pop, 'click', '[data-link]', function (e, b) { var n = D.notifications.find(function (x) { return x.link === b.getAttribute('data-link'); }); if (n) n.unread = false; BT.closeMenu(); A.updateBell(); A.go(b.getAttribute('data-link')); });
        var mr = pop.querySelector('[data-mark-read]');
        if (mr) mr.onclick = function () { D.notifications.forEach(function (n) { n.unread = false; }); BT.closeMenu(); A.updateBell(); BT.toast('تم تحديد كل الإشعارات كمقروءة'); };
      }
    });
  };
  A.updateBell = function () {
    var n = D.notifications.filter(function (x) { return x.unread; }).length;
    var b = document.getElementById('bell-badge');
    if (b) { b.textContent = n; b.hidden = !n; }
  };

  /* ---------- قائمة المستخدم ---------- */
  BT.actions['user-menu'] = function (arg, el) {
    var dark = BT.theme.get() === 'dark', frame = document.body.classList.contains('frame');
    BT.menu(el, [
      { head: D.currentUser.name + ' · ' + D.users[0].role },
      { label: 'ملفي الشخصي', icon: 'user-round', onClick: A.profile },
      { label: 'تغيير كلمة المرور', icon: 'key-round', onClick: A.changePassword },
      { sep: true },
      { label: dark ? 'الوضع الفاتح' : 'الوضع الداكن', icon: dark ? 'sun' : 'moon', onClick: function () { BT.theme.toggle(); } },
      { label: 'وضع العرض التقديمي', icon: 'presentation', checked: frame, onClick: function () { document.body.classList.toggle('frame'); BT.store.set('frame', document.body.classList.contains('frame')); } },
      { sep: true },
      { label: 'بوابة مراكز الصيانة', icon: 'store', onClick: function () { location.href = 'portal.html'; } },
      { label: 'تطبيق السائق', icon: 'smartphone', onClick: function () { location.href = 'driver.html'; } },
      { label: 'مكتبة المكونات', icon: 'layout-grid', onClick: function () { location.href = 'ui-kit.html'; } },
      { sep: true },
      { label: 'تسجيل الخروج', icon: 'log-out', danger: true, onClick: function () {
        BT.confirm({ title: 'تسجيل الخروج', message: 'هل تريد تسجيل الخروج من النظام على هذا الجهاز؟', confirmText: 'تسجيل الخروج', tone: 'danger', icon: 'log-out' })
          .then(function (r) { if (r.ok) location.href = 'login.html'; });
      } }
    ], { focus: true });
  };
  A.profile = function () {
    var u = D.currentUser;
    BT.drawer.open({
      title: 'ملفي الشخصي', subtitle: D.users[0].role, icon: 'user-round',
      body: h`<div class="flex items-center gap-12 mb-16">${BT.avatar(u.name, 'xl')}<div><h3>${u.name}</h3><div class="muted fs-sm">${u.role} · ${BT.config.client}</div></div></div>
        ${BT.kv([['الجوال', h`<span class="num">${u.phone}</span>`], ['الصلاحية', D.users[0].role], ['التحقق بخطوتين', BT.pill('مفعّل', 'g')], ['آخر دخول', 'اليوم 07:31 · Chrome'], ['الفرع', 'كل الفروع']])}
        <div class="section-t mt-16">الأجهزة المسجلة</div>
        <div class="list">${[['monitor', 'Chrome · Windows', 'هذا الجهاز · اليوم'], ['smartphone', 'Safari · iPhone', 'أمس 21:10']].map(function (d, i) {
          return h`<div class="li"><span class="li-ic">${icon(d[0], 16)}</span><div class="li-main"><div class="li-t">${d[1]}</div><div class="li-d">${d[2]}</div></div>${i ? h`<button type="button" class="btn btn-sm btn-danger" data-action="soon" data-arg="إنهاء الجلسة على الجهاز">إنهاء الجلسة</button>` : BT.pill('نشط', 'g')}</div>`;
        })}</div>`,
      buttons: [{ label: 'إغلاق', cls: 'btn-secondary' }]
    });
  };
  A.changePassword = function () {
    BT.modal.open({
      title: 'تغيير كلمة المرور', icon: 'key-round', size: 'sm', form: true,
      body: h`<div class="form">${BT.f.input({ name: 'old', label: 'كلمة المرور الحالية', type: 'password', required: true })}
        ${BT.f.input({ name: 'pw', label: 'كلمة المرور الجديدة', type: 'password', required: true, hint: '8 حروف على الأقل، وتحتوي رقماً', pattern: '(?=.*\\d).{8,}', msg: 'مطلوب' })}
        ${BT.f.input({ name: 'pw2', label: 'تأكيد كلمة المرور', type: 'password', required: true, validate: 'samePw' })}</div>`,
      buttons: [{ label: 'إلغاء', cls: 'btn-ghost' }, { label: 'حفظ', cls: 'btn-primary', submit: true }],
      onSubmit: function () { BT.toast('تم تغيير كلمة المرور'); }
    });
  };
  BT.validators.samePw = function (v, el, form) { return v === form.querySelector('[name=pw]').value ? '' : 'كلمتا المرور غير متطابقتين'; };
  BT.actions['soon'] = function (arg) { A.soon(arg || 'هذا الإجراء'); };

  /* ---------- تبديل الشركة/الفرع ---------- */
  A.branch = 'كل الفروع';
  BT.actions['switch-branch'] = function (arg, el) {
    BT.menu(el, [{ head: BT.config.client }].concat(['كل الفروع'].concat(D.company.branches.map(function (b) { return 'فرع ' + b; })).map(function (b) {
      return { label: b, icon: 'building-2', checked: A.branch === b, onClick: function () { A.branch = b; el.querySelector('small').textContent = b; BT.toast('تم التبديل إلى: ' + b); } };
    })), { align: 'start' });
  };

  /* ---------- البحث (Ctrl + K) ---------- */
  BT.openSearch = function () {
    BT.cmdk({
      source: function () {
        var out = [];
        A.NAV.forEach(function (s) { s.items.forEach(function (it) { out.push({ group: 'الصفحات', label: it.label, icon: it.icon, run: function () { A.go(it.key); } }); }); });
        [['إضافة سيارة', 'plus', 'add-vehicle'], ['تسليم سيارة لسائق', 'key-round', 'handover-new'], ['من كان يقود؟', 'search', 'who-drove'], ['تسجيل تحصيل كاش', 'hand-coins', 'collect'], ['تسجيل حادث', 'triangle-alert', 'accident-new'], ['طلب صيانة', 'wrench', 'maint-new'], ['إضافة موظف', 'user-plus', 'employee-new'], ['تصدير تقرير', 'download', 'export']].forEach(function (a) {
          out.push({ group: 'إجراءات', label: a[0], icon: a[1], run: function () { BT.actions[a[2]](); } });
        });
        out.push({ group: 'إجراءات', label: BT.theme.get() === 'dark' ? 'الوضع الفاتح' : 'الوضع الداكن', icon: 'moon', run: BT.theme.toggle });
        D.vehicles.forEach(function (v) { var e = D.driverOf(v); out.push({ group: 'السيارات', label: v.plate + ' — ' + v.make + ' ' + v.model, hint: e ? e.name : v.status, icon: 'car', run: function () { A.go('vehicles/' + A.slug(v.plate)); } }); });
        D.employees.forEach(function (e) { out.push({ group: 'الموظفون', label: e.name, hint: e.role + ' · ' + e.id, keywords: e.phone, icon: 'user-round', run: function () { BT.actions['employee-open'](e.id); } }); });
        return out;
      }
    });
  };
  BT.actions['search'] = function () { BT.openSearch(); };

  /* ---------- القائمة على الجوال ---------- */
  BT.actions['toggle-nav'] = function () { document.getElementById('app').classList.toggle('nav-open'); };
  BT.actions['theme'] = function () { BT.theme.toggle(); };

  /* ---------- التشغيل ---------- */
  function boot() {
    if (BT.store.get('frame', false)) document.body.classList.add('frame');
    var routes = {};
    Object.keys(BT.pages).forEach(function (k) { routes[k] = BT.pages[k]; });
    A.router = BT.router(routes, {
      default: 'dashboard',
      view: A.view,
      onBefore: function (r) {
        BT.closeAll(); BT.closeMenu();
        // حاوية جديدة لكل صفحة حتى لا تتراكم مستمعات الأحداث بين الصفحات
        var old = A.view(), fresh = old.cloneNode(false); old.replaceWith(fresh);
        document.getElementById('app').classList.remove('nav-open');
        A.renderNav(r.current.split('/')[0]);
        A.view().scrollTop = 0; window.scrollTo(0, 0);
        var m = document.querySelector('.main'); if (m) m.scrollTop = 0;
      }
    });
    BT.on(document.getElementById('sidebar'), 'click', '.nav-item', function () { document.getElementById('app').classList.remove('nav-open'); });
    document.querySelector('.sb-backdrop').addEventListener('click', function () { document.getElementById('app').classList.remove('nav-open'); });
    A.updateBell();
    BT.hydrate(document);
    A.router.start();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else setTimeout(boot, 0);
})();
