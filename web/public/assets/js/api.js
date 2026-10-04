/* =====================================================================
   BrilliantTech — api.js  (الاتصال بالخادم)
   كل طلبات لوحة الإدارة تمر من هنا: جلسة بالكوكي + رمز CSRF في كل طلب
   يغيّر بيانات، والأخطاء (problem+json) تُترجم من كتالوج الخادم نفسه
   (errors.<code>) بدل نصوص مكتوبة في الواجهة.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT;
  var BASE = '/api/v1';
  var api = BT.api = { me: null, csrf: null, cat: {}, lang: 'ar', companies: [], branches: [] };

  function ApiError(status, body) {
    this.status = status;
    this.body = body || {};
    this.code = this.body.code || (status ? 'http_' + status : 'network');
  }
  api.ApiError = ApiError;

  function qs(query) {
    if (!query) return '';
    var parts = [];
    Object.keys(query).forEach(function (k) {
      var v = query[k];
      if (v == null || v === '') return;
      (Array.isArray(v) ? v : [v]).forEach(function (x) { parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(x)); });
    });
    return parts.length ? '?' + parts.join('&') : '';
  }
  api.url = function (path, query) { return BASE + path + qs(query); };

  api.request = function (method, path, opts) {
    opts = opts || {};
    var headers = { Accept: 'application/json', 'Accept-Language': api.lang };  // نصوص التنبيهات بلغة الواجهة لا بلغة المتصفح
    if (method !== 'GET' && api.csrf) headers['X-CSRF-Token'] = api.csrf;
    var body;
    if (opts.form) body = opts.form;
    else if (opts.body !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(opts.body); }
    return fetch(api.url(path, opts.query), { method: method, headers: headers, body: body, credentials: 'same-origin', cache: 'no-store' })
      .then(function (res) {
        if (res.status === 204) return null;
        var json = (res.headers.get('content-type') || '').indexOf('json') > -1;
        return (json ? res.json() : res.text()).then(function (data) {
          if (res.ok) return data;
          var err = new ApiError(res.status, json ? data : {});
          if (res.status === 401 && !opts.noRedirect) api.toLogin();
          throw err;
        });
      }, function () { throw new ApiError(0, { code: 'network' }); });
  };
  api.get = function (path, query, opts) { return api.request('GET', path, Object.assign({ query: query }, opts)); };
  api.post = function (path, body, query) { return api.request('POST', path, { body: body === undefined ? {} : body, query: query }); };
  api.put = function (path, body) { return api.request('PUT', path, { body: body === undefined ? {} : body }); };
  api.patch = function (path, body) { return api.request('PATCH', path, { body: body }); };
  api.del = function (path) { return api.request('DELETE', path, {}); };

  /* رفع ملف واحد ← {sha256, size_bytes, content_type} */
  api.upload = function (file) {
    var fd = new FormData();
    fd.append('file', file, file.name || 'file');
    return api.request('POST', '/files', { form: fd });
  };
  api.uploadForm = function (path, file, query) {
    var fd = new FormData();
    fd.append('file', file, file.name || 'file');
    return api.request('POST', path, { form: fd, query: query });
  };

  api.toLogin = function () {
    if (api._leaving) return;
    api._leaving = true;
    location.href = 'login.html?next=' + encodeURIComponent(location.hash || '');
  };

  /* ---------- الترجمة من كتالوج الخادم ---------- */
  function fill(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (m, k) { return params && params[k] != null ? params[k] : m; });
  }
  api.t = function (ns, key, params, fallback) {
    var n = api.cat[ns] || {};
    var v = n[key];
    return v == null ? (fallback != null ? fallback : key) : fill(v, params);
  };
  api.loadCatalog = function (lang) {
    return api.get('/i18n/catalog/' + encodeURIComponent(lang || api.lang), null, { noRedirect: true }).then(function (c) {
      api.cat = c.messages || {};
      api.lang = c.lang;
      return c;
    });
  };
  /* الأسماء متعددة اللغات {ar, en} */
  api.name = function (o) {
    if (o == null) return '';
    if (typeof o !== 'object') return String(o);
    return o[api.lang] || o.ar || o.en || Object.keys(o).map(function (k) { return o[k]; }).filter(Boolean)[0] || '';
  };

  var VALIDATION_FIELDS = {
    username: 'اسم المستخدم', password: 'كلمة المرور', new_password: 'كلمة المرور الجديدة', current_password: 'كلمة المرور الحالية',
    full_name: 'الاسم', phone: 'الجوال', name: 'الاسم', employee_number: 'الرقم الوظيفي', civil_id: 'الرقم المدني',
    plate_number: 'رقم اللوحة', odometer_km: 'العداد', amount: 'المبلغ', reason: 'السبب', note: 'الملاحظة',
    code: 'الرمز', year: 'سنة الصنع', vin: 'رقم الشاصي', expiry_date: 'تاريخ الانتهاء', cash_amount: 'المبلغ', corrected_km: 'القراءة الصحيحة'
  };
  /* رسالة مفهومة لأي خطأ */
  api.message = function (err) {
    if (!(err instanceof ApiError)) return String(err && err.message || err || 'خطأ غير متوقع');
    if (err.code === 'network') return 'تعذر الاتصال بالخادم، تحقق من الشبكة وحاول مرة أخرى';
    if (err.code === 'validation_error') {
      var fields = (err.body.errors || []).map(function (e) {
        var loc = (e.loc || []).filter(function (x) { return x !== 'body' && x !== 'query' && typeof x === 'string'; });
        var f = loc[loc.length - 1];
        return VALIDATION_FIELDS[f] || f;
      }).filter(Boolean);
      return 'بيانات غير صحيحة' + (fields.length ? ': ' + fields.filter(function (x, i) { return fields.indexOf(x) === i; }).join('، ') : '');
    }
    var params = Object.assign({}, err.body.params || {});
    if (params.permission) params.permission = String(params.permission).split(', ').map(function (p) { return api.t('permissions', p); }).join('، ');
    var text = api.t('errors', err.code, params, '');
    if (text) return text;
    if (err.status === 403) return 'ليست لديك صلاحية لهذا الإجراء';
    if (err.status === 404) return 'العنصر غير موجود أو خارج نطاق صلاحياتك';
    if (err.status === 409) return 'تم تعديل هذه البيانات من مستخدم آخر، حدّث الصفحة وحاول مرة أخرى';
    return err.body.detail || err.body.title || ('خطأ من الخادم (' + err.status + ')');
  };
  /* يعرض الخطأ ثم يعيد رفضه حتى يبقى النموذج مفتوحاً */
  api.fail = function (err) {
    if (err instanceof ApiError && err.status === 401) throw err;
    BT.toast(api.message(err), { type: 'error', timeout: 6000 });
    throw err;
  };

  /* ---------- الصلاحيات والنطاق ---------- */
  api.can = function (perm) { var m = api.me; return !!m && (m.is_superuser || m.permissions.indexOf(perm) > -1); };
  api.canAny = function (list) { return list.some(api.can); };
  api.company = function (id) { var c = api.companies.find(function (x) { return x.id === id; }); return c ? api.name(c.name) : '—'; };
  api.branch = function (id) { var b = api.branches.find(function (x) { return x.id === id; }); return b ? api.name(b.name) : '—'; };
  api.companyOptions = function () { return api.companies.filter(function (c) { return c.is_active; }).map(function (c) { return { v: c.id, t: api.name(c.name) }; }); };
  api.branchOptions = function () { return api.branches.filter(function (b) { return b.is_active; }).map(function (b) { return { v: b.id, t: api.name(b.name) }; }); };
  api.defaultBranch = function () { var b = api.branches.find(function (x) { return x.is_default; }); return b ? b.id : null; };

  /* حساب مركز صيانة: صلاحيات البوابة فقط، مكانه center.html لا لوحة الإدارة */
  api.isCenterAccount = function (me) {
    return !!me && !me.is_superuser && me.permissions.length > 0 && me.permissions.every(function (p) { return p.indexOf('portal.') === 0; });
  };

  /* بداية كل صفحة محمية: الجلسة، الكتالوج، الشركات والفروع */
  api.boot = function () {
    return api.get('/auth/me').then(function (me) {
      api.me = me;
      api.csrf = me.csrf_token;
      if (api.isCenterAccount(me)) { location.replace('center.html'); return new Promise(function () {}); }
      return Promise.all([
        api.loadCatalog(me.locale || 'ar').catch(function () { return api.loadCatalog('ar'); }),
        api.get('/companies/options').then(function (c) { api.companies = c; }),
        api.get('/branches').then(function (b) { api.branches = b; })
      ]);
    }).then(function () { return api.me; });
  };

  /* ---------- التنسيق: الأوقات من الخادم UTC وتُعرض بتوقيت الكويت ---------- */
  var TZ = 'Asia/Kuwait';
  function parts(iso) {
    var d = new Date(iso), o = {};
    new Intl.DateTimeFormat('en-GB', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
      .formatToParts(d).forEach(function (p) { o[p.type] = p.value; });
    return o;
  }
  BT.fmt.dt = function (iso) { if (!iso) return '—'; var p = parts(iso); return '⁦' + p.day + '-' + p.month + '-' + p.year + ' ' + p.hour + ':' + p.minute + '⁩'; };
  BT.fmt.time = function (iso) { if (!iso) return '—'; var p = parts(iso); return '⁦' + p.hour + ':' + p.minute + '⁩'; };
  BT.fmt.dayOf = function (iso) { var p = parts(iso); return p.year + '-' + p.month + '-' + p.day; };
  BT.fmt.since = function (iso) { return iso ? BT.fmt.ago(Math.max(0, Math.round((Date.now() - new Date(iso)) / 1000))) : '—'; };
  BT.fmt.money = function (s) { return s == null || s === '' ? '—' : BT.fmt.kwd(Number(s)); };
  BT.config.today = BT.fmt.dayOf(new Date().toISOString());
  BT.config.client = '';
})();
