/* =====================================================================
   app/pages/site.js — الموقع التعريفي: ما يظهر على الدومين الرئيسي للشركة (الاسم، الجملة التعريفية، عن الشركة،
   الخدمات، بيانات التواصل، اللوجو، زرار تحميل التطبيق) بالعربي والإنجليزي، ورسائل «تواصل معنا».
   المحتوى قسم إعدادات «site»: يُحفظ بنسخة (version) ويُسجَّل في سجل التدقيق مثل باقي الإعدادات.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, icon = BT.icon, fmt = BT.fmt, api = BT.api, A = BT.A;

  var STATUS = { new: ['جديدة', 'b'], read: ['اطُّلع عليها', 'o'], done: ['تمت المعالجة', 'g'] };
  function pill(k) { var x = STATUS[k] || [k, 'n']; return BT.pill(x[0], x[1]); }

  BT.pages['site'] = function (p, q) {
    A.setTitle('الموقع التعريفي');
    var v = A.view();
    var tabs = [['content', 'المحتوى'], ['messages', 'رسائل تواصل معنا']];
    var tab = q.tab === 'messages' ? 'messages' : 'content';
    BT.render(v, h`${A.head('الموقع التعريفي', 'الصفحة اللي بتظهر على الدومين الرئيسي للشركة: التعريف، الخدمات، التواصل، وتحميل التطبيق. كل تعديل هنا بيظهر على الموقع فوراً.', h`<a class="btn btn-sm btn-secondary" href="/" target="_blank" rel="noopener" data-open-site>${icon('external-link', 14)} فتح الموقع</a>`)}
      ${BT.tabs('site', tabs, tab, 'tabs-line')}
      ${tabs.map(function (t) { return h`<div data-panel="${t[0]}" data-group="site" class="${t[0] === tab ? 'active' : ''}"><div id="site-${t[0]}"></div></div>`; })}`);
    var drawn = {};
    function show(t) {
      if (drawn[t]) return; drawn[t] = true;
      var el = document.getElementById('site-' + t);
      if (t === 'content') contentPanel(el);
      else messagesPanel(el);
    }
    v.addEventListener('bt:tab', function (e) { show(e.detail); history.replaceState(null, '', '#/site?tab=' + e.detail); });
    show(tab);
  };

  /* ---------- المحتوى ---------- */
  function pair(name, label, value, o) {
    o = o || {};
    var ctl = o.long ? BT.f.textarea : BT.f.input;
    return h`<div class="form-grid">
      ${ctl({ name: name + '.ar', label: label + ' (عربي)', value: (value || {}).ar || '', maxlength: o.long ? 2000 : 200, rows: o.long ? 5 : undefined, required: o.required })}
      ${ctl({ name: name + '.en', label: label + ' (English)', value: (value || {}).en || '', maxlength: o.long ? 2000 : 200, rows: o.long ? 5 : undefined, dir: 'ltr' })}
    </div>`;
  }

  function serviceRow(s, i) {
    s = s || { title: {}, text: {} };
    return h`<div class="card mb-8" data-service>
      <div class="card-b">
        <div class="between mb-8"><b>خدمة ${i + 1}</b><button type="button" class="btn btn-sm btn-ghost" data-remove-service>${icon('trash-2', 14)} حذف</button></div>
        ${pair('svc_title', 'العنوان', s.title, { required: true })}
        ${pair('svc_text', 'الوصف', s.text, { long: true })}
      </div></div>`;
  }

  function contentPanel(el) {
    var editable = api.can('settings.update');
    function draw() {
      A.load(el, api.get('/settings'), function (all) {
        var cur = all.site, s = cur.value;
        setTimeout(function () { wire(cur); });
        return h`<form class="form" data-site-form novalidate>
          <div class="card mb-12"><div class="card-b">
            ${BT.f.switch({ name: 'enabled', label: 'الموقع ظاهر للناس', checked: s.enabled })}
            <div class="hint mt-4">لو قفلته، الدومين الرئيسي هيوري صفحة «الصفحة مش موجودة».</div>
          </div></div>

          <div class="card mb-12"><div class="card-h"><div class="card-t">${icon('building-2', 16)} الشركة</div></div><div class="card-b">
            ${pair('company_name', 'اسم الشركة', s.company_name, { required: true })}
            ${pair('tagline', 'الجملة التعريفية', s.tagline)}
            ${pair('about', 'عن الشركة', s.about, { long: true })}
            <div class="field"><label class="label">اللوجو</label>
              <div class="row gap-8" style="align-items:center">
                <img data-logo-preview alt="" style="max-height:56px;${s.logo ? '' : 'display:none'}" src="${s.logo ? '/api/v1/site/logo/' + s.logo : ''}">
                <input type="hidden" name="logo" value="${s.logo || ''}">
                ${editable ? h`<label class="btn btn-sm btn-secondary">${icon('upload', 14)} ${s.logo ? 'تغيير اللوجو' : 'رفع لوجو'}<input type="file" accept="image/png,image/jpeg" hidden data-logo-file></label>
                <button type="button" class="btn btn-sm btn-ghost" data-logo-clear${s.logo ? '' : ' hidden'}>${icon('x', 14)} إزالة</button>` : ''}
              </div><div class="hint">PNG أو JPG.</div></div>
          </div></div>

          <div class="card mb-12"><div class="card-h"><div class="card-t">${icon('list', 16)} الخدمات</div></div><div class="card-b">
            <div data-services>${(s.services || []).map(serviceRow)}</div>
            ${editable ? h`<button type="button" class="btn btn-sm btn-secondary" data-add-service>${icon('plus', 14)} إضافة خدمة</button>` : ''}
          </div></div>

          <div class="card mb-12"><div class="card-h"><div class="card-t">${icon('phone', 16)} التواصل</div></div><div class="card-b">
            <div class="form-grid">
              ${BT.f.input({ name: 'phone', label: 'التليفون', value: s.phone, maxlength: 200, dir: 'ltr', placeholder: '+965 …' })}
              ${BT.f.input({ name: 'whatsapp', label: 'واتساب', value: s.whatsapp, maxlength: 200, dir: 'ltr', placeholder: '+965 …' })}
              ${BT.f.input({ name: 'email', label: 'الإيميل', value: s.email, maxlength: 200, dir: 'ltr', type: 'email' })}
              ${BT.f.input({ name: 'map_url', label: 'رابط الخريطة (اختياري)', value: s.map_url, maxlength: 500, dir: 'ltr', placeholder: 'https://maps.google.com/…', pattern: 'https://\\S+', msg: 'لازم يبدأ بـ https://' })}
            </div>
            ${pair('address', 'العنوان', s.address)}
            ${BT.f.switch({ name: 'show_contact_form', label: 'إظهار فورم «تواصل معنا»', checked: s.show_contact_form })}
            ${BT.f.switch({ name: 'show_download', label: 'إظهار زرار «تحميل تطبيق السائق»', checked: s.show_download })}
            <div class="hint mt-4">الزرار بيظهر بس لو فيه إصدار من التطبيق منشور (الإعدادات ← تحديثات التطبيق).</div>
          </div></div>

          ${editable ? h`<div class="row gap-8"><button type="submit" class="btn btn-primary">${icon('check', 14)} حفظ</button></div>` : h`<div class="banner info fs-sm">${icon('info', 16)}<div>للعرض بس: التعديل محتاج صلاحية تعديل الإعدادات.</div></div>`}
        </form>`;
      });
    }

    function wire(cur) {
      var form = el.querySelector('[data-site-form]');
      if (!form) return;
      if (!editable) { BT.$$('input,textarea,select', form).forEach(function (i) { i.disabled = true; }); return; }
      var box = form.querySelector('[data-services]');
      function renumber() { BT.$$('[data-service]', box).forEach(function (row, i) { row.querySelector('b').textContent = 'خدمة ' + (i + 1); }); }
      form.addEventListener('click', function (e) {
        var rm = e.target.closest('[data-remove-service]');
        if (rm) { rm.closest('[data-service]').remove(); renumber(); }
        if (e.target.closest('[data-add-service]')) {
          if (BT.$$('[data-service]', box).length >= 12) { BT.toast('أقصى عدد 12 خدمة', { type: 'error' }); return; }
          var tmp = document.createElement('div');
          BT.render(tmp, serviceRow(null, BT.$$('[data-service]', box).length));
          box.appendChild(tmp.firstElementChild);
        }
        if (e.target.closest('[data-logo-clear]')) {
          form.querySelector('[name=logo]').value = '';
          form.querySelector('[data-logo-preview]').style.display = 'none';
          e.target.closest('[data-logo-clear]').hidden = true;
        }
      });
      var file = form.querySelector('[data-logo-file]');
      if (file) file.addEventListener('change', function () {
        var f = file.files[0]; if (!f) return;
        api.upload(f).then(function (r) {
          form.querySelector('[name=logo]').value = r.sha256;
          var img = form.querySelector('[data-logo-preview]');
          img.src = URL.createObjectURL(f); img.style.display = '';
          form.querySelector('[data-logo-clear]').hidden = false;
          BT.toast('اللوجو اترفع', { sub: 'اضغط «حفظ» عشان يظهر على الموقع' });
        }, function (err) { BT.toast(api.message(err), { type: 'error', timeout: 8000 }); });
      });
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        if (!BT.form.validate(form)) return;
        var vals = BT.form.values(form);
        function lang(name) { var o = {}; if (vals[name + '.ar']) o.ar = vals[name + '.ar']; if (vals[name + '.en']) o.en = vals[name + '.en']; return o; }
        var services = BT.$$('[data-service]', box).map(function (row) {
          var g = function (n) { return (row.querySelector('[name="' + n + '"]') || {}).value || ''; };
          var title = {}, text = {};
          if (g('svc_title.ar')) title.ar = g('svc_title.ar'); if (g('svc_title.en')) title.en = g('svc_title.en');
          if (g('svc_text.ar')) text.ar = g('svc_text.ar'); if (g('svc_text.en')) text.en = g('svc_text.en');
          return { title: title, text: text };
        }).filter(function (s) { return s.title.ar || s.title.en; });
        var value = Object.assign({}, cur.value, {
          enabled: !!vals.enabled,
          company_name: lang('company_name'), tagline: lang('tagline'), about: lang('about'), address: lang('address'),
          services: services, phone: vals.phone || '', whatsapp: vals.whatsapp || '', email: vals.email || '',
          map_url: vals.map_url || '', show_contact_form: !!vals.show_contact_form, show_download: !!vals.show_download,
          logo: vals.logo || null
        });
        var btn = form.querySelector('[type=submit]'); btn.classList.add('is-loading');
        api.put('/settings/site', { version: cur.version, value: value }).then(function () {
          btn.classList.remove('is-loading'); BT.toast('اتحفظ، والموقع اتحدّث'); draw();
        }, function (err) { btn.classList.remove('is-loading'); BT.toast(api.message(err), { type: 'error', timeout: 9000 }); });
      });
    }
    draw();
  }

  /* ---------- رسائل تواصل معنا ---------- */
  function messagesPanel(el) {
    var status = 'new';
    function draw() {
      A.load(el, api.get('/site/messages', status ? { status: status } : null), function (r) {
        var c = r.counts;
        var chips = [['new', 'جديدة', c.new], ['read', 'اطُّلع عليها', c.read], ['done', 'تمت المعالجة', c.done], ['', 'الكل', c.new + c.read + c.done]];
        setTimeout(wire);
        return h`<div class="chips mb-12">${chips.map(function (x) { return h`<button type="button" class="chip${x[0] === status ? ' active' : ''}" data-status="${x[0]}">${x[1]} <span class="num">${fmt.int(x[2])}</span></button>`; })}</div>
          ${r.items.length ? h`<div class="grid" style="grid-template-columns:1fr;gap:10px">${r.items.map(function (m) {
            return h`<div class="card" data-message="${m.id}"><div class="card-b">
              <div class="between mb-4"><b>${m.name}</b>${pill(m.status)}</div>
              <div class="fs-sm muted mb-8">${fmt.dt(m.created_at)}${m.phone ? h` · <bdi dir="ltr">${m.phone}</bdi>` : ''}${m.email ? h` · <bdi dir="ltr">${m.email}</bdi>` : ''}</div>
              <p style="white-space:pre-line;margin:0 0 10px">${m.message}</p>
              ${api.can('settings.update') ? h`<div class="row gap-8">
                ${m.status === 'new' ? h`<button type="button" class="btn btn-sm btn-secondary" data-set="read">${icon('eye', 14)} تم الاطلاع</button>` : ''}
                ${m.status !== 'done' ? h`<button type="button" class="btn btn-sm btn-primary" data-set="done">${icon('check', 14)} تمت المعالجة</button>` : h`<button type="button" class="btn btn-sm btn-ghost" data-set="new">${icon('rotate-ccw', 14)} إرجاعها جديدة</button>`}
              </div>` : ''}
            </div></div>`;
          })}</div>` : h`<div class="empty">${icon('inbox', 28)}<div>مفيش رسائل هنا.</div></div>`}`;
      });
    }
    function wire() {
      BT.$$('[data-status]', el).forEach(function (b) { b.onclick = function () { status = b.getAttribute('data-status'); draw(); }; });
      BT.$$('[data-set]', el).forEach(function (b) {
        b.onclick = function () {
          var id = b.closest('[data-message]').getAttribute('data-message');
          b.classList.add('is-loading');
          api.post('/site/messages/' + id + '/status', { status: b.getAttribute('data-set') }).then(function () { BT.toast('اتحدّثت'); draw(); },
            function (err) { b.classList.remove('is-loading'); BT.toast(api.message(err), { type: 'error' }); });
        };
      });
    }
    draw();
  }
})();
