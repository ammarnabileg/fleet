/* =====================================================================
   BrilliantTech UI — core.js
   الأساسيات: BT.h (قوالب HTML آمنة)، الأيقونات، التنسيق، التواريخ،
   الوضع الليلي، الأحداث، والتنقل بين الصفحات (router).
   لا يحتاج أي مكتبة ولا build — يعمل بفتح ملف HTML مباشرة.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT = window.BT || {};

  /* ---------- الإعدادات العامة (غيّرها حسب العميل) ---------- */
  BT.config = Object.assign({
    brand: 'BrilliantTech',
    client: 'أجواد جروب',
    systemName: 'نظام إدارة الأسطول',
    currency: 'د.ك',
    today: '2026-11-24',        // تاريخ "اليوم" في البيانات التجريبية
    now: '23:14',
    cashAlert: 80,               // حد تنبيه رصيد السائق (د.ك) — تنبيه فقط
    signalLossMin: 10,           // انقطاع الإشارة (دقائق) قبل التنبيه
    odoGapKm: 5,                 // فرق العداد بين يومين قبل التنبيه (كم)
    approvalLimit: 100,          // عروض الصيانة فوق هذا المبلغ تحتاج اعتماد
    maxDeductionPct: 25,         // الحد الأقصى للخصم من الراتب (%) — يُضبط وفق المستشار القانوني
    gpsIntervalSec: 30
  }, BT.config || {});

  /* ---------- Safe HTML templates ----------
     BT.h`<b>${name}</b>`  → كل قيمة يتم تهريبها (escape) تلقائياً.
     لإدراج HTML جاهز استخدم BT.raw(html) أو نتيجة BT.h أخرى.        */
  function Raw(s) { this.s = s; }
  Raw.prototype.toString = function () { return this.s; };
  BT.Raw = Raw;
  BT.raw = function (s) { return new Raw(s == null ? '' : String(s)); };
  var ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  BT.esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return ESC[c]; }); };
  function renderVal(v) {
    if (v == null || v === false) return '';
    if (v instanceof Raw) return v.s;
    if (Array.isArray(v)) return v.map(renderVal).join('');
    return BT.esc(v);
  }
  BT.h = function (strings) {
    var out = '';
    for (var i = 0; i < strings.length; i++) {
      out += strings[i];
      if (i + 1 < arguments.length) out += renderVal(arguments[i + 1]);
    }
    return new Raw(out);
  };
  BT.render = function (el, content) { el.innerHTML = String(content); BT.hydrate(el); return el; };

  /* ---------- DOM helpers ---------- */
  BT.$ = function (sel, root) { return (root || document).querySelector(sel); };
  BT.$$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  BT.on = function (root, evt, sel, fn) {
    root.addEventListener(evt, function (e) {
      var t = e.target.closest && e.target.closest(sel);
      if (t && root.contains(t)) fn(e, t);
    });
  };
  BT.el = function (html) { var d = document.createElement('div'); d.innerHTML = String(html).trim(); BT.hydrate(d); return d.firstElementChild; };
  BT.uid = (function () { var n = 0; return function (p) { return (p || 'bt') + '-' + (++n); }; })();
  BT.debounce = function (fn, ms) { var t; return function () { var a = arguments, s = this; clearTimeout(t); t = setTimeout(function () { fn.apply(s, a); }, ms || 200); }; };

  /* ---------- Icons (lucide) ----------
     BT.icon('car', 16)  أو في HTML: <i data-icon="car" data-size="16"></i> */
  BT.icon = function (name, size, cls) {
    var body = (BT.ICONS || {})[name];
    if (!body) { if (window.console) console.warn('BT.icon: missing icon "' + name + '"'); body = '<circle cx="12" cy="12" r="9"/>'; }
    size = size || 16;
    return new Raw('<svg xmlns="http://www.w3.org/2000/svg" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"' + (cls ? ' class="' + cls + '"' : '') + '>' + body + '</svg>');
  };
  BT.hydrate = function (root) {
    BT.$$('i[data-icon]', root || document).forEach(function (i) {
      var svg = BT.el(String(BT.icon(i.getAttribute('data-icon'), +i.getAttribute('data-size') || 16, i.getAttribute('class'))));
      if (svg) i.replaceWith(svg);
    });
  };

  /* ---------- Formatting ---------- */
  var AR_DAYS = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
  var AR_MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function parseDate(s) { var p = String(s).split('-'); return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])); }
  function iso(d) { return d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-' + pad(d.getUTCDate()); }
  BT.date = {
    parse: parseDate,
    iso: iso,
    today: function () { return BT.config.today; },
    add: function (s, days) { var d = parseDate(s); d.setUTCDate(d.getUTCDate() + days); return iso(d); },
    diff: function (a, b) { return Math.round((parseDate(a) - parseDate(b)) / 86400000); }, // a - b بالأيام
    daysLeft: function (s) { return Math.round((parseDate(s) - parseDate(BT.config.today)) / 86400000); },
    dayName: function (s) { return AR_DAYS[parseDate(s).getUTCDay()]; },
    monthName: function (m) { return AR_MONTHS[m - 1]; }
  };
  BT.fmt = {
    int: function (n) { return n == null || n === '' ? '—' : Math.round(n).toLocaleString('en-US'); },
    km: function (n) { return n == null ? '—' : Math.round(n).toLocaleString('en-US'); },
    kwd: function (n) {
      if (n == null || n === '' || isNaN(n)) return '—';
      return (Math.round(n * 1000) / 1000).toLocaleString('en-US', { minimumFractionDigits: 3, maximumFractionDigits: 3 });
    },
    signed: function (n) { return (n > 0 ? '+' : n < 0 ? '−' : '') + BT.fmt.kwd(Math.abs(n)); },
    pct: function (n, d) { return (n > 0 ? '+' : '') + n.toFixed(d || 0) + '%'; },
    // التواريخ معزولة باتجاه LTR (U+2066…U+2069) حتى لا تنقلب بعد كلمة عربية: 24-11-2026 وليس 2026-11-24
    date: function (s) { if (!s) return '—'; var p = s.split('-'); return '\u2066' + p[2] + '-' + p[1] + '-' + p[0] + '\u2069'; },
    dm: function (s) { if (!s) return '—'; var p = s.split('-'); return '\u2066' + p[2] + '-' + p[1] + '\u2069'; },
    iso: function (s) { var p = s.split('-'); return p[2] + '-' + p[1] + '-' + p[0]; }, // بدون عزل (للتصدير والحقول)
    ltr: function (s) { return '\u2066' + s + '\u2069'; },
    month: function (y, m) { return AR_MONTHS[m - 1] + ' ' + y; },
    dateLong: function (s) { var d = parseDate(s); return AR_DAYS[d.getUTCDay()] + ' ' + BT.fmt.date(s); },
    ago: function (sec) {
      if (sec < 60) return 'منذ ' + sec + ' ث';
      if (sec < 3600) return 'منذ ' + Math.round(sec / 60) + ' د';
      if (sec < 86400) return 'منذ ' + Math.round(sec / 3600) + ' س';
      return 'منذ ' + Math.round(sec / 86400) + ' يوم';
    },
    daysLabel: function (n) {
      if (n < 0) return 'منتهي منذ ' + (-n) + ' يوم';
      if (n === 0) return 'ينتهي اليوم';
      if (n === 1) return 'بعد يوم';
      if (n === 2) return 'بعد يومين';
      if (n <= 10) return 'بعد ' + n + ' أيام';
      return 'بعد ' + n + ' يوماً';
    },
    bytes: function (b) { return b < 1024 ? b + ' B' : b < 1048576 ? (b / 1024).toFixed(0) + ' KB' : (b / 1048576).toFixed(1) + ' MB'; },
    initials: function (name) { return String(name).split(/\s+/).filter(Boolean).slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase(); }
  };
  BT.round3 = function (n) { return Math.round(n * 1000) / 1000; };
  BT.sum = function (arr, fn) { return arr.reduce(function (a, x) { return a + (fn ? fn(x) : x); }, 0); };

  /* ---------- Small HTML builders (مستخدمة في كل الصفحات) ---------- */
  BT.pill = function (text, cls, dot) { return BT.h`<span class="pill ${cls || 'n'}${dot ? ' dot' : ''}">${text}</span>`; };
  BT.amt = function (n, opts) { // مبلغ بالدينار: الرقم + د.ك (يظهر مثل العرض التقديمي)
    opts = opts || {};
    return BT.h`<span class="nowrap${opts.cls ? ' ' + opts.cls : ''}"><span class="num">${opts.signed ? BT.fmt.signed(n) : BT.fmt.kwd(n)}</span>${opts.noCur ? '' : BT.raw(' <small class="muted">' + BT.config.currency + '</small>')}</span>`;
  };
  BT.plate = function (p) { return BT.h`<span class="plate">${p}</span>`; };
  BT.avatar = function (name, cls) {
    var n = 0; for (var i = 0; i < name.length; i++) n += name.charCodeAt(i);
    return BT.h`<span class="av c${(n % 6) + 1}${cls ? ' ' + cls : ''}">${BT.fmt.initials(name)}</span>`;
  };
  BT.person = function (name, sub, cls) {
    return BT.h`<span class="person">${BT.avatar(name, cls || 'sm')}<span><b>${name}</b>${sub ? BT.h`<small>${sub}</small>` : ''}</span></span>`;
  };
  BT.kpi = function (o) { // {label, value, sub, dot, tone, href, action, ltr}
    var tag = o.href ? 'a' : o.action ? 'button' : 'div';
    var attrs = o.href ? BT.h` href="${o.href}"` : o.action ? BT.h` type="button" data-action="${o.action}"${o.arg ? BT.h` data-arg="${o.arg}"` : ''}` : '';
    var isLtr = o.ltr != null ? o.ltr : !/[؀-ۿ]/.test(String(o.value).replace(/<[^>]+>/g, ''));
    return BT.raw('<' + tag + ' class="kpi"' + attrs + '>' + BT.h`<div class="l"><span class="sdot ${o.dot || 'b'}"></span>${o.label}</div><div class="v${isLtr ? ' ltr-v' : ''}${o.tone ? ' t-' + o.tone : ''}">${o.value}</div>${o.sub ? BT.h`<div class="s">${o.sub}</div>` : ''}` + '</' + tag + '>');
  };
  BT.kv = function (rows) { // [[label, value], ...]
    return BT.h`<div class="kv">${rows.map(function (r) { return BT.h`<div${r[2] ? BT.raw(' class="' + r[2] + '"') : ''}><span>${r[0]}</span><span>${r[1]}</span></div>`; })}</div>`;
  };
  BT.empty = function (icon, title, text, action) {
    return BT.h`<div class="empty"><div class="em-ic">${BT.icon(icon || 'inbox', 26)}</div><h4>${title}</h4>${text ? BT.h`<div class="fs-sm">${text}</div>` : ''}${action || ''}</div>`;
  };

  /* ---------- Theme (فاتح / داكن) ---------- */
  BT.store = {
    get: function (k, d) { try { var v = localStorage.getItem('bt-' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem('bt-' + k, JSON.stringify(v)); } catch (e) { /* private mode */ } }
  };
  BT.theme = {
    get: function () { return document.documentElement.getAttribute('data-theme') || 'light'; },
    set: function (t) { document.documentElement.setAttribute('data-theme', t); BT.store.set('theme', t); document.dispatchEvent(new CustomEvent('bt:theme', { detail: t })); },
    toggle: function () { BT.theme.set(BT.theme.get() === 'dark' ? 'light' : 'dark'); },
    init: function () { document.documentElement.setAttribute('data-theme', BT.store.get('theme', 'light')); }
  };
  BT.theme.init();
  // أي زر عليه data-theme-icon تتبدل أيقونته (قمر/شمس) مع الوضع
  function themeIcons() { BT.$$('[data-theme-icon]').forEach(function (b) { var d = BT.theme.get() === 'dark'; b.innerHTML = String(BT.icon(d ? 'sun' : 'moon', +b.getAttribute('data-theme-icon') || 18)); b.setAttribute('aria-label', d ? 'الوضع الفاتح' : 'الوضع الداكن'); if (b.hasAttribute('data-tip')) b.setAttribute('data-tip', d ? 'الوضع الفاتح' : 'الوضع الداكن'); }); }
  document.addEventListener('bt:theme', themeIcons);
  document.addEventListener('DOMContentLoaded', function () { setTimeout(themeIcons, 0); });

  /* ---------- Declarative actions ----------
     <button data-action="add-vehicle" data-arg="18/23456">  →  BT.actions['add-vehicle'](arg, el, event) */
  BT.actions = BT.actions || {};
  document.addEventListener('click', function (e) {
    var el = e.target.closest && e.target.closest('[data-action]');
    if (!el) return;
    var fn = BT.actions[el.getAttribute('data-action')];
    if (!fn) { if (window.console) console.warn('BT: no action "' + el.getAttribute('data-action') + '"'); return; }
    e.preventDefault();
    fn(el.getAttribute('data-arg'), el, e);
  });

  /* ---------- Hash router ----------
     BT.router({ 'dashboard': fn, 'vehicles/:plate': fn }, { default: 'dashboard', view: el, onChange })
     الرابط: admin.html#/vehicles/18-23456                                                      */
  BT.router = function (routes, opts) {
    var compiled = Object.keys(routes).map(function (pattern) {
      var keys = [];
      var re = new RegExp('^' + pattern.replace(/:([a-zA-Z]+)/g, function (_, k) { keys.push(k); return '([^/]+)'; }) + '$');
      return { pattern: pattern, re: re, keys: keys, fn: routes[pattern] };
    });
    var api = { current: null, params: {}, query: {} };
    function run() {
      var hash = location.hash.replace(/^#\/?/, '') || opts.default;
      var parts = hash.split('?'), path = parts[0], query = {};
      (parts[1] || '').split('&').forEach(function (kv) { if (kv) { var p = kv.split('='); query[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || ''); } });
      for (var i = 0; i < compiled.length; i++) {
        var m = path.match(compiled[i].re);
        if (m) {
          var params = {};
          compiled[i].keys.forEach(function (k, j) { params[k] = decodeURIComponent(m[j + 1]); });
          api.current = compiled[i].pattern; api.path = path; api.params = params; api.query = query;
          if (opts.onBefore) opts.onBefore(api);
          compiled[i].fn(params, query);
          if (opts.view) { BT.hydrate(typeof opts.view === 'function' ? opts.view() : opts.view); }
          if (opts.onChange) opts.onChange(api);
          return;
        }
      }
      location.hash = '#/' + opts.default;
    }
    api.go = function (path) { if (location.hash === '#/' + path) run(); else location.hash = '#/' + path; };
    api.refresh = run;
    window.addEventListener('hashchange', run);
    api.start = run;
    return api;
  };

  /* ---------- Seeded random (بيانات تجريبية ثابتة في كل مرة) ---------- */
  BT.rng = function (seed) {
    var a = seed >>> 0;
    var r = function () { a |= 0; a = a + 0x6D2B79F5 | 0; var t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
    r.int = function (min, max) { return min + Math.floor(r() * (max - min + 1)); };
    r.pick = function (arr) { return arr[Math.floor(r() * arr.length)]; };
    r.shuffle = function (arr) { for (var i = arr.length - 1; i > 0; i--) { var j = Math.floor(r() * (i + 1)); var t = arr[i]; arr[i] = arr[j]; arr[j] = t; } return arr; };
    return r;
  };
})();
