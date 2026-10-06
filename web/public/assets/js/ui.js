/* =====================================================================
   BrilliantTech UI — ui.js
   كل النوافذ المنبثقة والمكونات التفاعلية:
   BT.modal · BT.drawer · BT.sheet · BT.confirm · BT.toast · BT.menu ·
   BT.popover · BT.lightbox · BT.cmdk · BT.form · BT.f (حقول) ·
   BT.table (جدول بفرز وبحث وترقيم) · tabs · upload · camera · OTP
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon;
  BT.ui = BT.ui || { root: null }; // حاوية النوافذ (تطبيق السائق يضبطها على شاشة الهاتف)
  function root() { return BT.ui.root || document.body; }

  /* =================================================================
     Overlay engine (مشترك بين modal / drawer / sheet / lightbox / cmdk)
     ================================================================= */
  var stack = [];
  var FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]):not([type=hidden]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

  function mountOverlay(ovClass, panelHtml, opts) {
    opts = opts || {};
    var ov = document.createElement('div');
    ov.className = 'overlay ' + (ovClass || '');
    // open from the moment it exists until close() (the "show" class follows a frame later, for the animation)
    ov.setAttribute('data-open', '');
    ov.innerHTML = String(panelHtml);
    BT.hydrate(ov);
    var panel = ov.firstElementChild;
    var prevFocus = document.activeElement;
    var closed = false, resolveFn;
    var api = {
      el: ov, panel: panel,
      promise: new Promise(function (r) { resolveFn = r; }),
      close: function (result) {
        if (closed) return; closed = true;
        ov.removeAttribute('data-open');
        ov.classList.remove('show');
        var i = stack.indexOf(api); if (i > -1) stack.splice(i, 1);
        setTimeout(function () { ov.remove(); }, 230);
        if (prevFocus && prevFocus.focus && document.contains(prevFocus)) { try { prevFocus.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
        if (opts.onClose) opts.onClose(result);
        resolveFn(result);
        if (!stack.length) document.documentElement.style.overflow = '';
      },
      dismissible: opts.dismissible !== false
    };
    ov.addEventListener('mousedown', function (e) { api._downOnBackdrop = e.target === ov; });
    ov.addEventListener('click', function (e) { if (e.target === ov && api._downOnBackdrop && api.dismissible) api.close(); });
    BT.on(ov, 'click', '[data-close]', function (e) { e.preventDefault(); api.close(); });
    root().appendChild(ov);
    stack.push(api);
    if (!BT.ui.root) document.documentElement.style.overflow = 'hidden';
    requestAnimationFrame(function () { ov.classList.add('show'); });
    setTimeout(function () {
      // already in one of its fields (a quick tap, or a slow phone where this runs late): never pull the focus back,
      // or the rest of what is typed lands in the first field
      if (panel.contains(document.activeElement)) return;
      var target = panel.querySelector('[autofocus]') || panel.querySelector('input:not([type=hidden]):not([readonly]),select,textarea') || panel;
      try { target.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
    }, 60);
    return api;
  }

  document.addEventListener('keydown', function (e) {
    var top = stack[stack.length - 1];
    if (!top) return;
    if (e.key === 'Escape' && top.dismissible) { e.preventDefault(); top.close(); return; }
    if (e.key === 'Tab') {
      var f = BT.$$(FOCUSABLE, top.panel).filter(function (x) { return x.offsetParent !== null; });
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
    if (top.onKey) top.onKey(e);
  });

  /* ---------- Dialog builder (modal / drawer / sheet) ---------- */
  function btnHtml(b, i) {
    var type = b.submit ? 'submit' : 'button';
    return h`<button type="${type}" class="btn ${b.cls || 'btn-secondary'}" data-btn="${i}"${b.disabled ? raw(' disabled') : ''}>${b.icon ? icon(b.icon, 15) : ''}${b.label}</button>`;
  }
  function dialog(kind, opts) {
    opts = opts || {};
    var id = BT.uid('dlg');
    var buttons = opts.buttons || [];
    var head = h`<div class="modal-h">
      ${opts.icon ? h`<div class="mh-ic ${opts.iconTone || ''}">${icon(opts.icon, 20)}</div>` : ''}
      <div class="flex-1"><h3 id="${id}-t">${opts.title || ''}</h3>${opts.subtitle ? h`<p>${opts.subtitle}</p>` : ''}</div>
      ${opts.dismissible === false ? '' : h`<button type="button" class="icon-btn sm x" data-close aria-label="إغلاق">${icon('x', 18)}</button>`}
    </div>`;
    var foot = (buttons.length || opts.footNote || opts.footer) ? h`<div class="modal-f">${opts.footNote ? h`<span class="f-note">${opts.footNote}</span>` : raw('<span class="spacer"></span>')}${opts.footer || ''}${buttons.map(btnHtml)}</div>` : '';
    var inner = opts.form
      ? h`<form class="dlg-form" novalidate style="display:contents">${head}<div class="modal-b">${opts.body || ''}</div>${foot}</form>`
      : h`${head}<div class="modal-b">${opts.body || ''}</div>${foot}`;
    var cls = { modal: 'modal ' + (opts.size || ''), drawer: 'drawer ' + (opts.size || ''), sheet: 'sheet' }[kind];
    var panel = h`<div class="${cls}" role="dialog" aria-modal="true" aria-labelledby="${id}-t" tabindex="-1">${kind === 'sheet' ? raw('<div class="grab"></div>') : ''}${inner}</div>`;
    var api = mountOverlay({ modal: '', drawer: 'drawer-ov', sheet: 'sheet-ov' }[kind], panel, opts);
    api.body = api.panel.querySelector('.modal-b');
    api.form = api.panel.querySelector('form');
    api.btn = function (i) { return api.panel.querySelector('[data-btn="' + i + '"]'); };
    api.busy = function (i, on) { var b = api.btn(i); if (b) { b.classList.toggle('is-loading', on !== false); b.disabled = on !== false; } };
    api.setBody = function (html) { BT.render(api.body, html); };

    BT.on(api.panel, 'click', '[data-btn]', function (e, b) {
      var cfg = buttons[+b.getAttribute('data-btn')];
      if (!cfg || cfg.submit) return;
      var r = cfg.onClick ? cfg.onClick(api) : undefined;
      if (r !== false && cfg.close !== false) api.close(cfg.value);
    });
    if (api.form) {
      BT.form.live(api.form);
      api.form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (!BT.form.validate(api.form)) return;
        var si = buttons.findIndex(function (b) { return b.submit; });
        var vals = BT.form.values(api.form);
        var r = opts.onSubmit ? opts.onSubmit(vals, api) : undefined;
        if (r && typeof r.then === 'function') {
          api.busy(si, true);
          r.then(function (res) { api.busy(si, false); if (res !== false) api.close(vals); }, function () { api.busy(si, false); });
        } else if (r !== false) api.close(vals);
      });
    }
    if (opts.onOpen) opts.onOpen(api);
    return api;
  }
  BT.modal = { open: function (o) { return dialog('modal', o); } };
  BT.drawer = { open: function (o) { return dialog('drawer', o); } };
  BT.sheet = { open: function (o) { return dialog('sheet', o); } };
  BT.closeAll = function () { stack.slice().reverse().forEach(function (a) { a.close(); }); };

  /* ---------- Confirm ----------
     BT.confirm({title, message, confirmText, tone:'danger'|'warn'|'success', reason:{label, required}, typed:'نص'})
     → Promise<{ok:true, reason}> أو {ok:false}                                                      */
  BT.confirm = function (o) {
    o = o || {};
    var tone = o.tone || 'primary';
    var btnCls = { danger: 'btn-danger-solid', warn: 'btn-primary', success: 'btn-success', primary: 'btn-primary' }[tone];
    var ic = o.icon || { danger: 'triangle-alert', warn: 'circle-alert', success: 'circle-check', primary: 'circle-help' }[tone];
    var body = h`<div class="confirm-msg">${o.message || ''}</div>
      ${o.details || ''}
      ${o.reason ? h`<div class="field mt-12"><label>${o.reason.label || 'السبب'}${o.reason.required !== false ? raw('<span class="req">*</span>') : ''}</label>
        <textarea class="textarea" name="reason" ${o.reason.required !== false ? raw('required') : ''} placeholder="${o.reason.placeholder || 'اكتب السبب…'}"></textarea><div class="err-msg"></div></div>` : ''}
      ${o.typed ? h`<div class="field mt-12"><label>للتأكيد اكتب: <b>${o.typed}</b></label><input class="input" name="typed" required data-equals="${o.typed}" autocomplete="off"><div class="err-msg"></div></div>` : ''}`;
    var d = (o.sheet ? BT.sheet : BT.modal).open({
      size: 'sm', title: o.title || 'تأكيد', icon: ic, iconTone: tone === 'primary' ? '' : tone === 'warn' ? 'warn' : tone,
      body: body, form: true,
      buttons: [{ label: o.cancelText || 'إلغاء', cls: 'btn-ghost', value: null }, { label: o.confirmText || 'تأكيد', cls: btnCls, submit: true }],
      onSubmit: function (v) { d._ok = v; }
    });
    return d.promise.then(function (v) { return v && d._ok ? { ok: true, reason: (d._ok.reason || '').trim() } : { ok: false }; });
  };

  /* ---------- Toast ----------
     BT.toast('تم الحفظ', {type:'success'|'error'|'warning'|'info', sub, timeout, action:{label, fn}}) */
  BT.toast = function (msg, o) {
    o = o || {};
    var type = o.type || 'success';
    var box = root().querySelector(':scope > .toasts');
    if (!box) { box = document.createElement('div'); box.className = 'toasts'; box.setAttribute('aria-live', 'polite'); root().appendChild(box); }
    var ic = { success: 'check', error: 'x', warning: 'triangle-alert', info: 'info' }[type];
    var t = BT.el(String(h`<div class="toast ${type}" role="status"><span class="t-ic">${icon(ic, 14)}</span><div class="t-body">${msg}${o.sub ? h`<small>${o.sub}</small>` : ''}</div>${o.action ? h`<button class="t-act" type="button">${o.action.label}</button>` : ''}<button class="t-x" type="button" aria-label="إغلاق">${icon('x', 14)}</button></div>`));
    box.appendChild(t);
    requestAnimationFrame(function () { t.classList.add('show'); });
    var kill = function () { t.classList.remove('show'); setTimeout(function () { t.remove(); }, 250); };
    t.querySelector('.t-x').onclick = kill;
    if (o.action) t.querySelector('.t-act').onclick = function () { o.action.fn(); kill(); };
    setTimeout(kill, o.timeout || 3800);
    return { close: kill };
  };

  /* =================================================================
     Dropdown menu & popover
     ================================================================= */
  var openMenu = null;
  function place(menu, anchor, align) {
    var r = anchor.getBoundingClientRect(), mw = menu.offsetWidth, mh = menu.offsetHeight;
    var vw = window.innerWidth, vh = window.innerHeight;
    var left = align === 'start' ? r.left : r.right - mw; // RTL: يحاذي الحافة اليمنى
    left = Math.max(8, Math.min(left, vw - mw - 8));
    var top = r.bottom + 6;
    if (top + mh > vh - 8 && r.top - mh - 6 > 8) top = r.top - mh - 6;
    menu.style.left = left + 'px'; menu.style.top = Math.max(8, top) + 'px';
  }
  function closeMenu() { if (openMenu) { var m = openMenu; openMenu = null; m.el.classList.remove('show'); m.anchor.setAttribute('aria-expanded', 'false'); setTimeout(function () { m.el.remove(); }, 130); if (m.onClose) m.onClose(); } }
  BT.closeMenu = closeMenu;
  function showFloating(anchor, html, o) {
    o = o || {};
    if (openMenu && openMenu.anchor === anchor) { closeMenu(); return null; }
    closeMenu();
    var el = BT.el(String(html));
    document.body.appendChild(el);
    place(el, anchor, o.align);
    anchor.setAttribute('aria-expanded', 'true');
    openMenu = { el: el, anchor: anchor, onClose: o.onClose };
    requestAnimationFrame(function () { el.classList.add('show'); });
    return el;
  }
  document.addEventListener('mousedown', function (e) { if (openMenu && !openMenu.el.contains(e.target) && !openMenu.anchor.contains(e.target)) closeMenu(); });
  window.addEventListener('resize', closeMenu);
  document.addEventListener('scroll', function (e) { if (openMenu && !openMenu.el.contains(e.target)) closeMenu(); }, true);
  document.addEventListener('keydown', function (e) {
    if (!openMenu) return;
    if (e.key === 'Escape') { var a = openMenu.anchor; closeMenu(); a.focus(); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      var items = BT.$$('.menu-item', openMenu.el); if (!items.length) return;
      e.preventDefault();
      var i = items.indexOf(document.activeElement);
      i = e.key === 'ArrowDown' ? (i + 1) % items.length : (i - 1 + items.length) % items.length;
      items[i].focus();
    }
  });

  /* BT.menu(anchorEl, [{label, icon, onClick, danger, checked, sub}, {sep:true}, {head:'عنوان'}], {align}) */
  BT.menu = function (anchor, items, o) {
    var html = h`<div class="menu" role="menu">${items.map(function (it, i) {
      if (it.sep) return raw('<div class="menu-sep"></div>');
      if (it.head) return h`<div class="menu-head">${it.head}</div>`;
      return h`<button type="button" role="menuitem" class="menu-item${it.danger ? ' danger' : ''}${it.checked ? ' checked' : ''}" data-mi="${i}">${it.icon ? icon(it.icon, 16) : ''}<span>${it.label}</span>${it.sub ? h`<small>${it.sub}</small>` : ''}</button>`;
    })}</div>`;
    var el = showFloating(anchor, html, o);
    if (!el) return;
    BT.on(el, 'click', '[data-mi]', function (e, b) { var it = items[+b.getAttribute('data-mi')]; closeMenu(); if (it.onClick) it.onClick(); });
    var f = el.querySelector('.menu-item'); if (f && o && o.focus) f.focus();
    return el;
  };
  /* BT.popover(anchorEl, html, {cls:'wide', align}) */
  BT.popover = function (anchor, content, o) {
    o = o || {};
    var el = showFloating(anchor, h`<div class="menu popover ${o.cls || ''}" role="dialog">${content}</div>`, o);
    if (el && o.onOpen) o.onOpen(el);
    return el;
  };

  /* =================================================================
     Lightbox — BT.lightbox([{src|html, caption, sub}], startIndex)
     ================================================================= */
  BT.lightbox = function (items, start) {
    if (!Array.isArray(items)) items = [items];
    var i = start || 0;
    var api = mountOverlay('lightbox-ov', h`<div class="lb" role="dialog" aria-modal="true" aria-label="عرض" tabindex="-1" style="display:contents">
      <button class="lb-btn lb-close" type="button" data-close aria-label="إغلاق">${icon('x', 22)}</button>
      ${items.length > 1 ? h`<span class="lb-count"></span><button class="lb-btn lb-prev" type="button" aria-label="السابق">${icon('chevron-right', 24)}</button><button class="lb-btn lb-next" type="button" aria-label="التالي">${icon('chevron-left', 24)}</button>` : ''}
      <div class="lb-stage"></div><div class="lb-cap"></div></div>`);
    var ov = api.el;
    function show() {
      var it = items[i];
      BT.render(ov.querySelector('.lb-stage'), it.src ? h`<img src="${it.src}" alt="${it.caption || ''}">` : (it.html || ''));
      BT.render(ov.querySelector('.lb-cap'), h`${it.caption || ''}${it.sub ? h`<small>${it.sub}</small>` : ''}`);
      var c = ov.querySelector('.lb-count'); if (c) c.textContent = (i + 1) + ' / ' + items.length;
    }
    function go(d) { i = (i + d + items.length) % items.length; show(); }
    if (items.length > 1) {
      ov.querySelector('.lb-prev').onclick = function () { go(-1); };
      ov.querySelector('.lb-next').onclick = function () { go(1); };
      api.onKey = function (e) { if (e.key === 'ArrowLeft') go(1); if (e.key === 'ArrowRight') go(-1); };
    }
    ov.addEventListener('click', function (e) { if (e.target.classList.contains('lb-stage') || e.target === ov) api.close(); });
    show();
    return api;
  };

  /* =================================================================
     Command palette — BT.cmdk({ source: () => [{group, label, icon, hint, run}] })
     ================================================================= */
  function norm(s) {
    return String(s || '').toLowerCase().replace(/[أإآ]/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي').replace(/[ً-ْـ]/g, '').replace(/[/\-\s]+/g, ' ').trim();
  }
  BT.norm = norm;
  BT.cmdk = function (o) {
    var all = o.source();
    var api = mountOverlay('cmdk-ov', h`<div class="cmdk" role="dialog" aria-modal="true" aria-label="بحث" tabindex="-1">
      <div class="cmdk-in">${icon('search', 20)}<input type="search" placeholder="${o.placeholder || 'ابحث عن سيارة، سائق، صفحة، أو إجراء…'}" autocomplete="off" aria-label="بحث"><kbd>Esc</kbd></div>
      <div class="cmdk-list" role="listbox"></div>
      <div class="cmdk-foot"><span><kbd>↑</kbd> <kbd>↓</kbd> للتنقل</span><span><kbd>Enter</kbd> للفتح</span><span><kbd>Ctrl</kbd> + <kbd>K</kbd> للبحث من أي صفحة</span></div></div>`);
    var input = api.panel.querySelector('input'), list = api.panel.querySelector('.cmdk-list');
    var shown = [], active = 0;
    function draw() {
      var q = norm(input.value);
      shown = all.filter(function (it) { return !q || norm(it.label + ' ' + (it.hint || '') + ' ' + (it.keywords || '')).indexOf(q) > -1; }).slice(0, 40);
      active = Math.min(active, Math.max(0, shown.length - 1));
      if (!shown.length) { list.innerHTML = '<div class="cmdk-empty">لا توجد نتائج</div>'; return; }
      var g = null, out = '';
      shown.forEach(function (it, i) {
        if (it.group !== g) { g = it.group; out += String(h`<div class="cmdk-group">${g}</div>`); }
        out += String(h`<button type="button" class="cmdk-item${i === active ? ' active' : ''}" data-i="${i}" role="option">${icon(it.icon || 'arrow-left', 16)}<span>${it.label}</span>${it.hint ? h`<small>${it.hint}</small>` : ''}</button>`);
      });
      list.innerHTML = out;
      var a = list.querySelector('.active'); if (a) a.scrollIntoView({ block: 'nearest' });
    }
    function run(i) { var it = shown[i]; if (!it) return; api.close(); setTimeout(it.run, 10); }
    input.addEventListener('input', function () { active = 0; draw(); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(active + 1, shown.length - 1); draw(); }
      if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); draw(); }
      if (e.key === 'Enter') { e.preventDefault(); run(active); }
    });
    BT.on(list, 'click', '[data-i]', function (e, b) { run(+b.getAttribute('data-i')); });
    BT.on(list, 'mousemove', '[data-i]', function (e, b) { var i = +b.getAttribute('data-i'); if (i !== active) { active = i; BT.$$('.cmdk-item', list).forEach(function (x) { x.classList.toggle('active', +x.getAttribute('data-i') === i); }); } });
    draw();
    return api;
  };

  /* =================================================================
     Forms — BT.form.values / validate / live  +  BT.f.* field builders
     ================================================================= */
  BT.form = {
    values: function (form) {
      var out = {};
      BT.$$('input,select,textarea', form).forEach(function (el) {
        var n = el.name; if (!n || el.disabled) return;
        if (el.type === 'file') { out[n] = Array.prototype.slice.call(el.files || []); return; }
        if (el.type === 'radio') { if (el.checked) out[n] = el.value; else if (!(n in out)) out[n] = ''; return; }
        if (el.type === 'checkbox') {
          var group = form.querySelectorAll('input[type=checkbox][name="' + n + '"]');
          if (group.length > 1) { out[n] = out[n] || []; if (el.checked) out[n].push(el.value); }
          else out[n] = el.hasAttribute('value') ? (el.checked ? el.value : '') : el.checked;
          return;
        }
        var v = el.value;
        if (el.dataset.type === 'number' || el.type === 'number') v = v === '' ? '' : Number(String(v).replace(/,/g, ''));
        out[n] = v;
      });
      return out;
    },
    validate: function (form) {
      var ok = true, firstBad = null;
      BT.$$('.field', form).forEach(function (f) { f.classList.remove('invalid'); });
      BT.$$('input,select,textarea', form).forEach(function (el) {
        if (el.disabled || !el.name) return;
        var msg = BT.form.check(el, form);
        if (msg) {
          ok = false;
          var f = el.closest('.field');
          if (f) {
            f.classList.add('invalid');
            var em = f.querySelector('.err-msg'); if (!em) { em = document.createElement('div'); em.className = 'err-msg'; f.appendChild(em); }
            em.textContent = msg;
          }
          if (!firstBad) firstBad = el;
        }
      });
      if (firstBad) { try { firstBad.focus({ preventScroll: false }); } catch (e) { /* ignore */ } }
      return ok;
    },
    check: function (el, form) {
      var v = (el.value || '').trim();
      if (el.type === 'file') {
        if (el.required && !(el.files && el.files.length)) return el.dataset.msg || 'يلزم إرفاق ملف';
        return '';
      }
      if (el.type === 'checkbox' || el.type === 'radio') {
        if (!el.required) return '';
        var any = form.querySelectorAll('input[name="' + el.name + '"]:checked').length;
        return any ? '' : (el.dataset.msg || 'هذا الحقل مطلوب');
      }
      if (el.required && !v) return el.dataset.msg || 'هذا الحقل مطلوب';
      if (!v) return '';
      if (el.dataset.type === 'number' || el.type === 'number') {
        var n = Number(v.replace(/,/g, ''));
        if (isNaN(n)) return 'أدخل رقماً صحيحاً';
        if (el.hasAttribute('min') && n < +el.getAttribute('min')) return el.dataset.minMsg || ('أقل قيمة ' + el.getAttribute('min'));
        if (el.hasAttribute('max') && n > +el.getAttribute('max')) return el.dataset.maxMsg || ('أعلى قيمة ' + el.getAttribute('max'));
      }
      if (el.pattern && !new RegExp('^(?:' + el.pattern + ')$').test(v)) return el.dataset.patternMsg || 'الصيغة غير صحيحة';
      if (el.dataset.equals && v !== el.dataset.equals) return 'النص غير مطابق';
      if (el.minLength > 0 && v.length < el.minLength) return 'الحد الأدنى ' + el.minLength + ' حروف';
      if (el.dataset.validate && BT.validators[el.dataset.validate]) return BT.validators[el.dataset.validate](v, el, form) || '';
      return '';
    },
    live: function (form) {
      form.addEventListener('input', function (e) { var f = e.target.closest('.field'); if (f && f.classList.contains('invalid') && !BT.form.check(e.target, form)) f.classList.remove('invalid'); });
      form.addEventListener('change', function (e) { var f = e.target.closest('.field'); if (f && f.classList.contains('invalid') && !BT.form.check(e.target, form)) f.classList.remove('invalid'); });
    }
  };
  BT.validators = {
    kwPhone: function (v) { return /^[5692]\d{7}$/.test(v.replace(/\s/g, '')) ? '' : 'رقم كويتي من 8 أرقام'; },
    plate: function (v) { return /^\d{1,2}\/\d{3,6}$/.test(v) ? '' : 'الصيغة: 18/23456'; },
    civilId: function (v) { return /^\d{12}$/.test(v) ? '' : 'الرقم المدني 12 رقماً'; }
  };

  /* ---------- Field builders ----------
     BT.f.input({name, label, required, value, placeholder, hint, num, addon, full, type, min, max, readonly, validate}) */
  function wrap(o, control) {
    return h`<div class="field${o.full ? ' full' : ''}"${o.id ? raw(' id="' + BT.esc(o.id) + '"') : ''}>${o.label ? h`<label${o.name ? raw(' for="f-' + BT.esc(o.name) + '"') : ''}>${o.label}${o.required ? raw('<span class="req">*</span>') : o.optional ? raw(' <span class="opt">(اختياري)</span>') : ''}</label>` : ''}${control}${o.hint ? h`<div class="hint">${o.hint}</div>` : ''}<div class="err-msg"></div></div>`;
  }
  function attrs(o) {
    var a = '';
    if (o.name) a += ' name="' + BT.esc(o.name) + '" id="f-' + BT.esc(o.name) + '"';
    if (o.required) a += ' required';
    if (o.readonly) a += ' readonly';
    if (o.disabled) a += ' disabled';
    if (o.placeholder) a += ' placeholder="' + BT.esc(o.placeholder) + '"';
    if (o.min != null) a += ' min="' + o.min + '"';
    if (o.max != null) a += ' max="' + o.max + '"';
    if (o.step != null) a += ' step="' + o.step + '"';
    if (o.pattern) a += ' pattern="' + BT.esc(o.pattern) + '"';
    if (o.validate) a += ' data-validate="' + BT.esc(o.validate) + '"';
    if (o.msg) a += ' data-msg="' + BT.esc(o.msg) + '"';
    if (o.autofocus) a += ' autofocus';
    if (o.maxlength) a += ' maxlength="' + o.maxlength + '"';
    if (o.num) a += ' data-type="number" inputmode="decimal"';
    return raw(a);
  }
  BT.f = {
    input: function (o) {
      var type = o.type || 'text';
      var ctl = h`<input class="input${o.num ? ' num-in' : ''}${o.lg ? ' lg' : ''}" type="${type}"${attrs(o)} value="${o.value == null ? '' : o.value}" autocomplete="off">`;
      if (o.addon) ctl = h`<div class="input-group">${ctl}<span class="addon">${o.addon}</span></div>`;
      return wrap(o, ctl);
    },
    money: function (o) { return BT.f.input(Object.assign({ num: true, addon: BT.config.currency, placeholder: '0.000' }, o)); },
    date: function (o) { return BT.f.input(Object.assign({ type: 'date' }, o)); },
    select: function (o) {
      var opts = (o.options || []).map(function (x) { return typeof x === 'object' ? x : { v: x, t: x }; });
      return wrap(o, h`<select class="select"${attrs(o)}>${o.placeholder !== false ? h`<option value="">${o.placeholder || 'اختر…'}</option>` : ''}${opts.map(function (x) { return h`<option value="${x.v}"${String(x.v) === String(o.value) ? raw(' selected') : ''}${x.disabled ? raw(' disabled') : ''}>${x.t}</option>`; })}</select>`);
    },
    textarea: function (o) { return wrap(o, h`<textarea class="textarea"${attrs(o)} rows="${o.rows || 3}">${o.value || ''}</textarea>`); },
    check: function (o) { return h`<label class="check"><input type="checkbox" name="${o.name || ''}"${o.required ? raw(' required') : ''}${o.value != null ? raw(' value="' + BT.esc(o.value) + '"') : ''}${o.checked ? raw(' checked') : ''}><span>${o.label}</span></label>`; },
    switch: function (o) { return h`<label class="switch"><input type="checkbox" name="${o.name}"${o.checked ? raw(' checked') : ''}><span>${o.label}</span></label>`; },
    radios: function (o) { // option cards
      return wrap(o, h`<div class="options">${o.options.map(function (x, i) {
        return h`<label class="option-card"><input class="radio-in" type="radio" name="${o.name}" value="${x.v}"${String(x.v) === String(o.value) ? raw(' checked') : ''}${o.required && i === 0 ? raw(' required') : ''}><span><b>${x.t}</b>${x.d ? h`<small>${x.d}</small>` : ''}</span></label>`;
      })}</div>`);
    },
    upload: function (o) {
      return wrap(o, h`<label class="dropzone">${icon(o.icon || 'upload', 22)}<span><b>اختر ملفاً</b> أو اسحبه هنا</span><span class="hint">${o.accept_label || 'PDF أو صورة · حتى 10MB'}</span>
        <input type="file"${attrs(Object.assign({}, o, { placeholder: null }))} accept="${o.accept || 'image/*,application/pdf'}"${o.multiple ? raw(' multiple') : ''}></label><div class="file-list"></div>`);
    },
    /* كاميرا فقط: capture="environment" يفتح الكاميرا مباشرة على أندرويد/iOS.
       ملاحظة: بعض المتصفحات تتجاهل capture — المنع الكامل للمعرض يتم داخل التطبيق الأصلي (CameraX). */
    camera: function (o) {
      return wrap(o, h`<label class="cam-tile"><span class="cam-ic">${icon('camera', 20)}</span><span>${o.cta || 'التقاط صورة'}</span><span class="hint">${o.sub || 'من الكاميرا فقط'}</span>
        <input type="file" accept="image/*" capture="environment"${attrs(Object.assign({}, o, { placeholder: null }))}></label>`);
    }
  };

  /* Upload + camera previews (delegated — تعمل في أي مكان) */
  document.addEventListener('change', function (e) {
    var inp = e.target;
    if (!inp || inp.type !== 'file') return;
    var cam = inp.closest('.cam-tile');
    if (cam) {
      var f = inp.files && inp.files[0];
      BT.$$('img,.cam-ok', cam).forEach(function (x) { x.remove(); });
      cam.classList.toggle('has-img', !!f);
      if (f) {
        var img = document.createElement('img'); img.alt = ''; img.src = URL.createObjectURL(f); cam.appendChild(img);
        cam.appendChild(BT.el(String(h`<span class="cam-ok">${icon('check', 12)} تم الالتقاط</span>`)));
      }
      return;
    }
    var dz = inp.closest('.dropzone');
    if (dz) {
      var list = dz.parentElement.querySelector('.file-list');
      if (!list) return;
      BT.render(list, h`${Array.prototype.map.call(inp.files, function (file) {
        var isImg = /^image\//.test(file.type);
        return h`<div class="file-item"><span class="fi-ic">${isImg ? raw('<img alt="" src="' + URL.createObjectURL(file) + '">') : icon('file-text', 16)}</span><span class="fi-name">${file.name}</span><span class="fi-size">${BT.fmt.bytes(file.size)}</span>${icon('circle-check', 16, 't-success')}</div>`;
      })}`);
    }
  });
  ['dragenter', 'dragover'].forEach(function (ev) { document.addEventListener(ev, function (e) { var dz = e.target.closest && e.target.closest('.dropzone'); if (dz) dz.classList.add('drag'); }); });
  ['dragleave', 'drop'].forEach(function (ev) { document.addEventListener(ev, function (e) { var dz = e.target.closest && e.target.closest('.dropzone'); if (dz) dz.classList.remove('drag'); }); });

  /* ---------- OTP input: <div class="otp" data-otp="6"></div> ---------- */
  BT.otp = {
    html: function (n) { var s = ''; for (var i = 0; i < (n || 6); i++) s += '<input inputmode="numeric" maxlength="1" aria-label="رقم ' + (i + 1) + '">'; return raw('<div class="otp">' + s + '</div>'); },
    value: function (el) { return BT.$$('input', el).map(function (i) { return i.value; }).join(''); }
  };
  document.addEventListener('input', function (e) {
    var inp = e.target; if (!inp.closest || !inp.closest('.otp')) return;
    inp.value = inp.value.replace(/\D/g, '').slice(-1);
    if (inp.value && inp.nextElementSibling) inp.nextElementSibling.focus();
    inp.closest('.otp').classList.remove('invalid');
    var all = BT.$$('input', inp.closest('.otp'));
    if (all.every(function (x) { return x.value; })) inp.closest('.otp').dispatchEvent(new CustomEvent('otp:complete', { bubbles: true, detail: BT.otp.value(inp.closest('.otp')) }));
  });
  document.addEventListener('keydown', function (e) {
    var inp = e.target; if (!inp.closest || !inp.closest('.otp')) return;
    if (e.key === 'Backspace' && !inp.value && inp.previousElementSibling) { inp.previousElementSibling.focus(); inp.previousElementSibling.value = ''; e.preventDefault(); }
  });
  document.addEventListener('paste', function (e) {
    var inp = e.target; if (!inp.closest || !inp.closest('.otp')) return;
    var d = (e.clipboardData.getData('text') || '').replace(/\D/g, ''); if (!d) return;
    e.preventDefault();
    var all = BT.$$('input', inp.closest('.otp'));
    all.forEach(function (x, i) { x.value = d[i] || ''; });
    (all[Math.min(d.length, all.length) - 1] || inp).focus();
    if (d.length >= all.length) inp.closest('.otp').dispatchEvent(new CustomEvent('otp:complete', { bubbles: true, detail: d.slice(0, all.length) }));
  });

  /* ---------- Tabs ----------
     <div class="tabs" data-tabs="g1"><button data-tab="a" class="active">أ</button>…</div>
     <div data-panel="a" data-group="g1" class="active">…</div>                              */
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-tabs] [data-tab]');
    if (!b) return;
    var bar = b.closest('[data-tabs]'), g = bar.getAttribute('data-tabs'), t = b.getAttribute('data-tab');
    BT.$$('[data-tab]', bar).forEach(function (x) { x.classList.toggle('active', x === b); x.setAttribute('aria-selected', x === b); });
    BT.$$('[data-panel][data-group="' + g + '"]').forEach(function (p) { p.classList.toggle('active', p.getAttribute('data-panel') === t); });
    bar.dispatchEvent(new CustomEvent('bt:tab', { bubbles: true, detail: t }));
  });
  BT.tabs = function (group, items, active, cls) { // items: [[key, label, count?]]
    return h`<div class="${cls || 'tabs'}" data-tabs="${group}" role="tablist">${items.map(function (it) {
      return h`<button type="button" role="tab" data-tab="${it[0]}" class="${it[0] === active ? 'active' : ''}">${it[1]}${it[2] != null ? h` <span class="count">${it[2]}</span>` : ''}</button>`;
    })}</div>`;
  };

  /* =================================================================
     Data table — BT.table(el, opts)
     opts: { columns:[{key,label,num,sort,render,width,cls}], rows, pageSize,
             search:{placeholder, text:(row)=>string}, chips:{key,options:[{v,t}],all},
             tools: Raw, rowClick, rowClass, rowMenu:(row)=>items, selectable, bulk:[{label,icon,cls,run}],
             empty:{icon,title,text}, foot:(rows)=>Raw, sort:{key,dir}, id:(row)=>key,
             fetch:({q, chip, offset, limit})=>Promise<rows> }
     fetch: الصفوف من الخادم صفحةً صفحة (البحث والتصفية والترقيم على الخادم، بلا فرز محلي)
     ================================================================= */
  BT.table = function (el, o) {
    var st = { q: '', chip: o.chips ? (o.chips.value || '') : '', page: 1, size: o.pageSize || (o.fetch ? 25 : 10), sort: o.fetch ? null : o.sort || null, sel: {}, selRows: {}, loaded: [], more: false, loading: !!o.fetch, error: null, ticket: 0 };
    var getRows = function () { return o.fetch ? st.loaded : typeof o.rows === 'function' ? o.rows() : o.rows; };
    var idOf = o.id || function (r, i) { return r.id != null ? r.id : i; };
    var cols = o.columns.slice();
    if (o.rowMenu) cols.push({ key: '_menu', label: '', cls: 'actions', render: function (r, i) { return h`<button type="button" class="icon-btn sm" data-row-menu="${i}" aria-label="إجراءات">${icon('ellipsis-vertical', 16)}</button>`; } });
    var searchId = BT.uid('tsearch');
    BT.render(el, h`
      ${(o.search || o.chips || o.tools) ? h`<div class="toolbar">
        ${o.search ? h`<div class="search-box">${icon('search', 16)}<input id="${searchId}" class="input" type="search" placeholder="${o.search.placeholder || 'بحث…'}" aria-label="بحث"></div>` : ''}
        ${o.chips ? h`<div class="chips" data-chips></div>` : ''}
        ${o.tools ? h`<div class="page-actions ms-auto">${o.tools}</div>` : ''}
      </div>` : ''}
      ${o.selectable ? raw('<div class="banner info hidden" data-bulk style="align-items:center;margin-bottom:10px"></div>') : ''}
      <div class="table-wrap" data-wrap></div>
      ${o.pageSize === 0 ? '' : raw('<div class="pager" data-pager></div>')}`);
    var wrapEl = el.querySelector('[data-wrap]'), pager = el.querySelector('[data-pager]'), chipsEl = el.querySelector('[data-chips]'), bulkEl = el.querySelector('[data-bulk]');
    var current = [], pageRows = [];

    function load() {
      var ticket = ++st.ticket;
      st.loading = true; st.error = null; draw();
      Promise.resolve(o.fetch({ q: st.q.trim(), chip: st.chip, offset: (st.page - 1) * st.size, limit: st.size + 1 })).then(function (rows) {
        if (ticket !== st.ticket) return;
        st.loading = false; st.more = rows.length > st.size; st.loaded = rows.slice(0, st.size); draw();
      }, function (err) {
        if (ticket !== st.ticket) return;
        st.loading = false; st.loaded = []; st.more = false; st.error = (BT.api && BT.api.message) ? BT.api.message(err) : 'تعذر تحميل البيانات'; draw();
      });
    }
    function filtered() {
      var rows = getRows();
      if (o.fetch) return rows;
      if (o.chips && st.chip !== '') rows = rows.filter(function (r) { return o.chips.match ? o.chips.match(r, st.chip) : String(r[o.chips.key]) === String(st.chip); });
      if (st.q) { var q = norm(st.q); rows = rows.filter(function (r) { return norm(o.search.text ? o.search.text(r) : Object.values(r).join(' ')).indexOf(q) > -1; }); }
      if (st.sort) {
        var c = cols.find(function (x) { return x.key === st.sort.key; });
        var get = c && typeof c.sort === 'function' ? c.sort : function (r) { return r[st.sort.key]; };
        var dir = st.sort.dir === 'desc' ? -1 : 1;
        rows = rows.slice().sort(function (a, b) { var x = get(a), y = get(b); if (x == null) return 1; if (y == null) return -1; return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'ar')) * dir; });
      }
      return rows;
    }
    function drawChips() {
      if (!chipsEl) return;
      var all = getRows();
      var items = (o.chips.all === false ? [] : [{ v: '', t: o.chips.all || 'الكل' }]).concat(o.chips.options);
      BT.render(chipsEl, h`${items.map(function (it) {
        var n = o.fetch ? (o.chips.counts ? o.chips.counts[it.v] : null) : it.v === '' ? all.length : all.filter(function (r) { return o.chips.match ? o.chips.match(r, it.v) : String(r[o.chips.key]) === String(it.v); }).length;
        return h`<button type="button" class="chip${String(st.chip) === String(it.v) ? ' active' : ''}" data-chip="${it.v}">${it.t}${n != null ? h` <span class="n">${BT.fmt.int(n)}</span>` : ''}</button>`;
      })}`);
    }
    function draw() {
      current = filtered();
      var pages = o.fetch ? st.page + (st.more ? 1 : 0) : st.size ? Math.max(1, Math.ceil(current.length / st.size)) : 1;
      if (!o.fetch) st.page = Math.min(st.page, pages);
      var start = o.fetch ? 0 : st.size ? (st.page - 1) * st.size : 0;
      pageRows = o.fetch || !st.size ? current : current.slice(start, start + st.size);
      var allSel = pageRows.length && pageRows.every(function (r, i) { return st.sel[idOf(r, start + i)]; });
      var html = h`<table class="t${o.compact ? ' compact' : ''}"><thead><tr>
        ${o.selectable ? h`<th class="cell-check"><label class="check"><input type="checkbox" data-sel-all${allSel ? raw(' checked') : ''} aria-label="تحديد الكل"></label></th>` : ''}
        ${cols.map(function (c) {
          var sortable = !o.fetch && c.sort !== false && c.key !== '_menu' && c.label;
          var sorted = st.sort && st.sort.key === c.key;
          return h`<th class="${c.num ? 'num ' : ''}${sortable ? 'sortable ' : ''}${sorted ? 'sorted' : ''}"${c.width ? raw(' style="width:' + c.width + '"') : ''}${sortable ? h` data-sort="${c.key}"` : ''}${sorted ? raw(' aria-sort="' + (st.sort.dir === 'desc' ? 'descending' : 'ascending') + '"') : ''}>${c.label}${sortable ? icon(sorted ? (st.sort.dir === 'desc' ? 'arrow-down' : 'arrow-up') : 'arrow-up-down', 12, 'sort-ic') : ''}</th>`;
        })}</tr></thead><tbody>
        ${pageRows.length ? pageRows.map(function (r, i) {
          var id = idOf(r, start + i);
          var rc = (o.rowClass ? o.rowClass(r) || '' : '') + (o.rowClick ? ' clickable' : '') + (st.sel[id] ? ' selected' : '');
          return h`<tr data-i="${i}" class="${rc}">${o.selectable ? h`<td class="cell-check"><label class="check"><input type="checkbox" data-sel="${id}"${st.sel[id] ? raw(' checked') : ''} aria-label="تحديد"></label></td>` : ''}${cols.map(function (c) {
            var v = c.render ? c.render(r, i) : r[c.key];
            return h`<td class="${c.num ? 'num ' : ''}${c.cls || ''}">${v == null || v === '' ? '—' : v}</td>`;
          })}</tr>`;
        }) : h`<tr><td class="t-empty" colspan="${cols.length + (o.selectable ? 1 : 0)}">${st.loading ? raw('<div class="t-loading"><span class="spinner"></span> جاري التحميل…</div>') : st.error ? BT.empty('wifi-off', 'تعذر تحميل البيانات', st.error, raw('<button type="button" class="btn btn-sm btn-secondary mt-8" data-t-retry>إعادة المحاولة</button>')) : BT.empty((o.empty || {}).icon || 'search-x', (o.empty || {}).title || 'لا توجد نتائج', (o.empty || {}).text || (st.q ? 'جرّب كلمة بحث أخرى' : ''))}</td></tr>`}
        </tbody>${o.foot && current.length ? h`<tfoot>${o.foot(current)}</tfoot>` : ''}</table>`;
      BT.render(wrapEl, html);
      if (pager && o.fetch) {
        BT.render(pager, h`<span>صفحة <span class="num">${BT.fmt.int(st.page)}</span>${pageRows.length ? h` · <span class="num">${BT.fmt.int(pageRows.length)}</span> صف` : ''}</span>
          <div class="flex items-center gap-8"><select class="select" data-size aria-label="عدد الصفوف">${[25, 50, 100, 200].map(function (n) { return h`<option value="${n}"${n === st.size ? raw(' selected') : ''}>${n} صف</option>`; })}</select>
          <div class="pages"><button type="button" data-page="${st.page - 1}"${st.page <= 1 || st.loading ? raw(' disabled') : ''} aria-label="السابق">${icon('chevron-right', 16)}</button>
          <button type="button" class="active" disabled>${st.page}</button>
          <button type="button" data-page="${st.page + 1}"${!st.more || st.loading ? raw(' disabled') : ''} aria-label="التالي">${icon('chevron-left', 16)}</button></div></div>`);
      } else if (pager) {
        var from = current.length ? start + 1 : 0, to = start + pageRows.length;
        var nums = [], p;
        for (p = 1; p <= pages; p++) { if (p === 1 || p === pages || Math.abs(p - st.page) <= 1) nums.push(p); else if (nums[nums.length - 1] !== '…') nums.push('…'); }
        BT.render(pager, h`<span>عرض <span class="num">${BT.fmt.int(from)}–${BT.fmt.int(to)}</span> من <span class="num">${BT.fmt.int(current.length)}</span></span>
          <div class="flex items-center gap-8"><select class="select" data-size aria-label="عدد الصفوف">${[10, 25, 50, 100].map(function (n) { return h`<option value="${n}"${n === st.size ? raw(' selected') : ''}>${n} صف</option>`; })}</select>
          <div class="pages"><button type="button" data-page="${st.page - 1}"${st.page <= 1 ? raw(' disabled') : ''} aria-label="السابق">${icon('chevron-right', 16)}</button>
          ${nums.map(function (n) { return n === '…' ? raw('<button type="button" disabled>…</button>') : h`<button type="button" data-page="${n}" class="${n === st.page ? 'active' : ''}">${n}</button>`; })}
          <button type="button" data-page="${st.page + 1}"${st.page >= pages ? raw(' disabled') : ''} aria-label="التالي">${icon('chevron-left', 16)}</button></div></div>`);
      }
      drawBulk();
    }
    function selectedRows() {
      if (o.fetch) return Object.keys(st.sel).filter(function (k) { return st.sel[k]; }).map(function (k) { return st.selRows[k]; });
      var all = getRows(); return all.filter(function (r, i) { return st.sel[idOf(r, i)]; });
    }
    function drawBulk() {
      if (!bulkEl) return;
      var n = Object.keys(st.sel).filter(function (k) { return st.sel[k]; }).length;
      bulkEl.classList.toggle('hidden', !n);
      if (!n) return;
      BT.render(bulkEl, h`${icon('list-checks', 16)}<span>تم تحديد <b class="num">${n}</b></span><div class="btn-group ms-auto">${(o.bulk || []).map(function (b, i) { return h`<button type="button" class="btn btn-sm ${b.cls || 'btn-outline'}" data-bulk-i="${i}">${b.icon ? icon(b.icon, 14) : ''}${b.label}</button>`; })}<button type="button" class="btn btn-sm btn-ghost" data-bulk-clear>إلغاء التحديد</button></div>`);
    }

    var reload = function () { if (o.fetch) load(); else draw(); };
    if (o.search) el.querySelector('#' + searchId).addEventListener('input', BT.debounce(function (e) { st.q = e.target.value; st.page = 1; reload(); }, o.fetch ? 350 : 150));
    BT.on(el, 'click', '[data-chip]', function (e, b) { st.chip = b.getAttribute('data-chip'); st.page = 1; drawChips(); reload(); if (o.onChip) o.onChip(st.chip); });
    BT.on(el, 'click', '[data-t-retry]', function () { load(); });
    BT.on(el, 'click', '[data-sort]', function (e, th) {
      var k = th.getAttribute('data-sort');
      st.sort = st.sort && st.sort.key === k ? (st.sort.dir === 'asc' ? { key: k, dir: 'desc' } : null) : { key: k, dir: 'asc' };
      draw();
    });
    BT.on(el, 'click', '[data-page]', function (e, b) { st.page = +b.getAttribute('data-page'); reload(); el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); });
    el.addEventListener('change', function (e) {
      if (e.target.matches('[data-size]')) { st.size = +e.target.value; st.page = 1; reload(); }
      if (e.target.matches('[data-sel]')) {
        var k = e.target.getAttribute('data-sel');
        st.sel[k] = e.target.checked;
        if (o.fetch) { var hit = pageRows.find(function (r, i) { return String(idOf(r, i)) === k; }); if (hit) st.selRows[k] = hit; }
        draw();
      }
      if (e.target.matches('[data-sel-all]')) { var start = o.fetch ? 0 : (st.page - 1) * st.size; pageRows.forEach(function (r, i) { var id = idOf(r, start + i); st.sel[id] = e.target.checked; st.selRows[id] = r; }); draw(); }
    });
    BT.on(el, 'click', '[data-bulk-i]', function (e, b) { var cfg = o.bulk[+b.getAttribute('data-bulk-i')]; cfg.run(selectedRows(), function () { st.sel = {}; st.selRows = {}; draw(); }); });
    BT.on(el, 'click', '[data-bulk-clear]', function () { st.sel = {}; st.selRows = {}; draw(); });
    BT.on(el, 'click', '[data-row-menu]', function (e, b) { e.stopPropagation(); BT.menu(b, o.rowMenu(pageRows[+b.getAttribute('data-row-menu')]), { align: 'start' }); });
    if (o.rowClick) BT.on(el, 'click', 'tbody tr[data-i]', function (e, tr) {
      if (e.target.closest('button,a,input,label,select')) return;
      o.rowClick(pageRows[+tr.getAttribute('data-i')]);
    });
    drawChips(); draw(); if (o.fetch) load();
    return {
      refresh: function () { drawChips(); reload(); },
      setChip: function (v) { st.chip = v; st.page = 1; drawChips(); reload(); },
      rows: function () { return current; },
      clear: function () { st.sel = {}; st.selRows = {}; draw(); }
    };
  };

  /* Keyboard shortcut: Ctrl/Cmd + K → command palette (إن وُجد BT.openSearch) */
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K') && BT.openSearch) { e.preventDefault(); if (!stack.some(function (s) { return s.el.classList.contains('cmdk-ov'); })) BT.openSearch(); }
  });

  /* Print helper — BT.print(html) يطبع هذا المحتوى فقط (مثل الإيصال) */
  BT.print = function (html) {
    var p = document.getElementById('bt-print');
    if (!p) { p = document.createElement('div'); p.id = 'bt-print'; document.body.appendChild(p); }
    BT.render(p, html);
    document.body.classList.add('printing');
    setTimeout(function () { window.print(); document.body.classList.remove('printing'); }, 50);
  };
})();
