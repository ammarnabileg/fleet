/* اللوحة بالإنجليزي: النصوص مكتوبة بالعربي في الصفحات، وهذا الملف يترجم ما يظهر على الشاشة من قاموس
   i18n-en.js (نص عربي ← إنجليزي) ويقلب الاتجاه. اللغة محفوظة في المتصفح وفي حساب المستخدم (رسائل الخادم بلغته).
   نص جديد في صفحة: أضفه للقاموس، واختبار e2e «english» يكشف أي نص بقي عربياً. */
(function () {
  'use strict';
  var KEY = 'ui.lang';
  var lang = 'ar';
  try { lang = localStorage.getItem(KEY) === 'en' ? 'en' : 'ar'; } catch (e) { /* التخزين ممنوع: عربي */ }
  var BT = window.BT = window.BT || {};
  BT.lang = lang;
  BT.setLang = function (next) {
    try { localStorage.setItem(KEY, next); } catch (e) { /* يبقى للجلسة فقط */ }
    var save = window.api && window.api.me ? window.api.put('/auth/me/locale', { locale: next }).catch(function () {}) : Promise.resolve();
    return save.then(function () { location.reload(); });
  };
  document.documentElement.lang = lang;
  if (lang !== 'en') return;
  document.documentElement.dir = 'ltr';

  var AR = /[؀-ۿ]/;
  var dict = window.BT_EN || {};
  var exact = Object.create(null), pattern = Object.create(null), keys = [];
  function norm(s) { return s.replace(/\s+/g, ' ').trim(); }
  function shape(s) { return s.replace(/\d[\d,.]*/g, '#'); }
  Object.keys(dict).forEach(function (k) {
    var n = norm(k);
    exact[n] = dict[k];
    if (/\d/.test(n)) pattern[shape(n)] = dict[k];
    if (n.length > 1) keys.push(n);
  });
  keys.sort(function (a, b) { return b.length - a.length; });
  var esc = function (s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); };
  // جملة فيها قيمة (رقم، اسم): تُترجم أجزاؤها المعروفة، كلمةً كاملة لا جزء كلمة
  var phrases = keys.length ? new RegExp('(?<![\\u0600-\\u06FF])(?:' + keys.map(esc).join('|') + ')(?![\\u0600-\\u06FF])', 'g') : null;

  var missing = BT.i18nMissing = {};
  function tr(text, quiet) {
    if (!text || !AR.test(text)) return text;
    var n = norm(text);
    var lead = text.match(/^\s*/)[0], tail = text.match(/\s*$/)[0];
    var hit = exact[n];
    if (hit == null && /\d/.test(n)) {
      var nums = n.match(/\d[\d,.]*/g), p = pattern[shape(n)];
      if (p != null) { var i = 0; hit = p.replace(/\d[\d,.]*/g, function () { return nums[i++]; }); }
    }
    if (hit == null && /،/.test(n)) {
      // قائمة مفصولة بفاصلة عربية: كل جزء وحده (والجزء بلا عربي، اسم أو رقم، كما هو)
      var parts = n.split(/\s*،\s*/).map(function (x) { return AR.test(x) ? tr(x, true) : x; });
      if (!parts.some(function (x) { return AR.test(x); })) hit = parts.join(', ');
    }
    if (hit == null && phrases) {
      hit = n.replace(phrases, function (m) { return exact[m]; });
      // نصف عربي ونصف إنجليزي أسوأ من العربي: يبقى كما هو ويُسجَّل ليُضاف للقاموس
      if (AR.test(hit)) { if (!quiet) missing[n] = 1; return text; }
    }
    return lead + hit + tail;
  }
  BT.tr = tr;
  // يُكتب فقط ما تغيّر: كتابة نفس النص تُطلق المراقب من جديد بلا نهاية
  function text(n) { var v = tr(n.nodeValue); if (v !== n.nodeValue) n.nodeValue = v; }

  var ATTRS = ['placeholder', 'title', 'aria-label', 'data-tip', 'alt', 'data-empty'];
  var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1 };
  function el(node) {
    ATTRS.forEach(function (a) {
      var v = node.getAttribute && node.getAttribute(a);
      if (v && AR.test(v)) { var t = tr(v); if (t !== v) node.setAttribute(a, t); }
    });
    if (node.tagName === 'INPUT' && (node.type === 'button' || node.type === 'submit') && AR.test(node.value) && tr(node.value) !== node.value) node.value = tr(node.value);
  }
  function walk(root) {
    if (root.nodeType === 3) { if (AR.test(root.nodeValue) && !skipped(root.parentNode)) text(root); return; }
    if (root.nodeType !== 1 || SKIP[root.tagName] || skipped(root)) return;
    el(root);
    var w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        if (n.nodeType !== 1) return NodeFilter.FILTER_ACCEPT;
        if (n.hasAttribute('data-no-tr')) return NodeFilter.FILTER_REJECT;
        if (SKIP[n.tagName]) { if (n.tagName === 'TEXTAREA') el(n); return NodeFilter.FILTER_REJECT; }  // نص المستخدم لا يُترجم، تلميحه يُترجم
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    for (var n = w.nextNode(); n; n = w.nextNode()) {
      if (n.nodeType === 1) el(n);
      else if (AR.test(n.nodeValue)) text(n);
    }
  }
  function skipped(n) { return !!(n && n.closest && n.closest('[data-no-tr],[contenteditable=true]')); }

  function start() {
    walk(document.body);
    if (AR.test(document.title) && tr(document.title) !== document.title) document.title = tr(document.title);
    new MutationObserver(function (list) {
      list.forEach(function (m) {
        if (m.type === 'characterData') { if (AR.test(m.target.nodeValue) && !skipped(m.target.parentNode)) text(m.target); }
        else if (m.type === 'attributes') el(m.target);
        else m.addedNodes.forEach(walk);
      });
      if (AR.test(document.title) && tr(document.title) !== document.title) document.title = tr(document.title);
    }).observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);
  // نوافذ المتصفح الأصلية
  ['alert', 'confirm', 'prompt'].forEach(function (f) {
    var orig = window[f];
    window[f] = function (msg) { var a = Array.prototype.slice.call(arguments); a[0] = tr(String(msg == null ? '' : msg)); return orig.apply(window, a); };
  });
})();
