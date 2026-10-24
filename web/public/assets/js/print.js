/* =====================================================================
   BrilliantTech — print.js  (محرك الطباعة الموحد: كل ما يُطبع من اللوحة)
   ورقة A4 واحدة لكل التقارير والإيصالات: الهيدر (الشعار، اسم الشركة بالعربي
   والإنجليزي، سطور السجل التجاري والعنوان والهاتف، العنوان)، الفوتر (نص بمتغيرات
   {page} {pages} {printed_at} {printed_by} {company}، تاريخ الطباعة ومن طبع،
   سطور التوقيع)، والعلامة المائية، حسب قالب الطباعة للشركة التي يخصها التقرير
   (أو قالب المجموعة إن شمل أكثر من شركة).
   الهيدر يتكرر في كل صفحة (thead جدول)، والعلامة المائية (position: fixed)،
   ورقم الصفحة «صفحة X من Y» في هامش الصفحة (@page @bottom-center بعدّادات
   counter(page) و counter(pages)) — يدعمها Chromium منذ الإصدار 131.
   BT.printDoc({ title, meta, body, companyId, draft, signatures, note })
   BT.printPreview(doc)  — نفس الورقة في نافذة معاينة على الشاشة
   BT.printSheet(layout, doc, { screen })  — HTML الورقة (لمعاينة المصمم)
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h;
  var cache = {};

  BT.printLayout = function (companyId) {
    var key = companyId ? String(companyId) : 'group';
    if (!cache[key]) cache[key] = BT.api.get('/print/layout', companyId ? { company_id: companyId } : null).catch(function (e) { delete cache[key]; throw e; });
    return cache[key];
  };
  BT.printLayoutReset = function () { cache = {}; };

  var VAR = /\{(\w+)\}/g;
  function fill(text, values) { return String(text || '').replace(VAR, function (m, k) { return values[k] == null ? '' : String(values[k]); }); }
  /* a header line whose every variable is empty (no CR number for this company) is left out */
  function line(text, values) {
    var vars = String(text || '').match(VAR) || [];
    if (vars.length && vars.every(function (v) { return !values[v.slice(1, -1)]; })) return '';
    return fill(text, values).trim();
  }
  function cssString(s) { return '"' + String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, ' ') + '"'; }
  /* the footer as CSS content: text with counter(page) and counter(pages) where {page} and {pages} are */
  function footerContent(text, values) {
    var parts = [], last = 0;
    String(text || '').replace(VAR, function (m, k, at) {
      if (at > last) parts.push(cssString(fill(text.slice(last, at), values)));
      parts.push(k === 'page' ? 'counter(page)' : k === 'pages' ? 'counter(pages)' : cssString(values[k] == null ? '' : values[k]));
      last = at + m.length;
      return m;
    });
    if (last < String(text || '').length) parts.push(cssString(fill(text.slice(last), values)));
    return parts.length ? parts.join(' ') : '""';
  }
  function footerExtra(t, values) {
    var x = [];
    if (t.footer.show_printed_at) x.push('طُبع ' + values.printed_at);
    if (t.footer.show_printed_by && values.printed_by) x.push(values.printed_by);
    return x.join(' · ');
  }
  function nowText() { return BT.fmt && BT.fmt.dt ? BT.fmt.dt(new Date().toISOString()) : new Date().toLocaleString(); }

  /* @page: A4, the template's margins (start = right in Arabic), the running footer in the bottom margin */
  BT.printPageCss = function (layout, doc) {
    var t = layout.template, p = t.page, values = docValues(layout, doc || {});
    var foot = footerContent(t.footer.text, values), extra = footerExtra(t, values);
    return '@page { size: A4; margin: ' + p.margin_top + 'mm ' + p.margin_start + 'mm ' + p.margin_bottom + 'mm ' + p.margin_end + 'mm;'
      + ' @bottom-center { content: ' + (extra ? foot + ' "   ·   " ' + cssString(extra) : foot) + '; font-family: "IBM Plex Sans Arabic", sans-serif; font-size: 8pt; color: #555; } }';
  };
  function docValues(layout, doc) {
    return Object.assign({}, layout.identity, { printed_at: doc.printedAt || nowText(), printed_by: doc.printedBy != null ? doc.printedBy : (BT.api.me ? BT.api.me.full_name : '') });
  }

  BT.printSheet = function (layout, doc, opts) {
    opts = opts || {};
    var t = layout.template, hd = t.header, ft = t.footer, wm = t.watermark, pg = t.page, id = layout.identity, values = docValues(layout, doc);
    var logo = hd.show_logo && layout.images && layout.images.logo ? h`<img class="pd-logo" src="${layout.images.logo}" alt="">` : '';
    var lines = (hd.lines || []).map(function (l) { return line(l, values); }).filter(Boolean);
    var names = h`<div class="pd-names">${hd.show_name_ar && id.company ? h`<div class="pd-name">${id.company}</div>` : ''}${hd.show_name_en && id.company_en && id.company_en !== id.company ? h`<div class="pd-name-en" dir="ltr">${id.company_en}</div>` : ''}${lines.length ? h`<div class="pd-lines">${lines.map(function (l) { return h`<span>${l}</span>`; })}</div>` : ''}</div>`;
    var showWm = wm.mode === 'always' || (wm.mode === 'drafts' && doc.draft);
    var mark = !showWm ? '' : wm.kind === 'image' && layout.images && layout.images.watermark
      ? h`<div class="pd-wm" style="opacity:${wm.opacity};transform:translate(-50%,-50%) rotate(${wm.angle}deg)"><img src="${layout.images.watermark}" alt="" style="width:${wm.size}mm"></div>`
      : wm.text ? h`<div class="pd-wm" style="opacity:${wm.opacity};transform:translate(-50%,-50%) rotate(${wm.angle}deg);font-size:${wm.size}px">${wm.text}</div>` : '';
    var sigs = doc.signatures || ft.signatures || [];
    var note = doc.note || ft.note;
    var style = '--pd-accent:' + pg.accent + ';--pd-text:' + pg.text_color + ';--pd-fs:' + pg.font_size + 'pt';
    var screenPad = opts.screen ? ';padding:' + pg.margin_top + 'mm ' + pg.margin_start + 'mm ' + pg.margin_bottom + 'mm ' + pg.margin_end + 'mm' : '';
    var footText = fill(ft.text, Object.assign({}, values, { page: 1, pages: 1 })), extra = footerExtra(t, values);
    return h`<div class="pd${opts.screen ? ' pd-screen' : ''}${pg.zebra ? ' pd-zebra' : ''}" dir="rtl" style="${style + screenPad}" data-print-doc data-company="${layout.company_id || ''}">
      ${mark}
      <table class="pd-frame"><thead><tr><td>
        <div class="pd-head pd-logo-${hd.logo_position}${pg.header_rule ? ' pd-rule' : ''}">${logo}${names}</div>
      </td></tr></thead>
      <tfoot><tr><td><div class="pd-foot-gap"></div></td></tr></tfoot>
      <tbody><tr><td>
        ${hd.show_title && doc.title ? h`<div class="pd-title" style="text-align:${hd.title_align}">${doc.title}</div>` : ''}
        ${hd.show_filters && doc.meta ? h`<div class="pd-meta" style="text-align:${hd.title_align}">${doc.meta}</div>` : ''}
        <div class="pd-body">${doc.body || ''}</div>
        ${note ? h`<div class="pd-note">${note}</div>` : ''}
        ${sigs.length ? h`<div class="pd-sigs">${sigs.map(function (s) { return h`<div class="pd-sig"><div class="pd-sig-line"></div>${s}</div>`; })}</div>` : ''}
      </td></tr></tbody></table>
      <div class="pd-foot-screen">${footText}${extra ? '   ·   ' + extra : ''}</div>
    </div>`;
  };

  function waitImages(root) {
    return Promise.all(BT.$$('img', root).map(function (img) { return img.complete ? null : (img.decode ? img.decode().catch(function () {}) : null); }));
  }

  /* prints the document alone, on A4, in the company's template */
  BT.printDoc = function (doc) {
    return BT.printLayout(doc.companyId).then(function (layout) {
      var p = document.getElementById('bt-print');
      if (!p) { p = document.createElement('div'); p.id = 'bt-print'; document.body.appendChild(p); }
      var st = document.getElementById('bt-print-page');
      if (!st) { st = document.createElement('style'); st.id = 'bt-print-page'; document.head.appendChild(st); }
      st.textContent = '@media print { ' + BT.printPageCss(layout, doc) + ' }';
      BT.render(p, BT.printSheet(layout, doc));
      return waitImages(p).then(function () {
        document.body.classList.add('printing');
        setTimeout(function () { window.print(); document.body.classList.remove('printing'); }, 50);
        return layout;
      });
    }, function (err) { BT.toast(BT.api.message(err), { type: 'error' }); throw err; });
  };

  /* the same sheet on screen, with a print button */
  BT.printPreview = function (doc) {
    var dlg = BT.modal.open({ size: 'lg', title: 'معاينة الطباعة', icon: 'printer', body: h`<div class="pd-preview-wrap"><div class="spinner"></div></div>`,
      buttons: [{ label: 'طباعة / PDF', icon: 'printer', cls: 'btn-primary', close: false, onClick: function () { BT.printDoc(doc); return false; } }, { label: 'إغلاق', cls: 'btn-secondary' }] });
    BT.printLayout(doc.companyId).then(function (layout) {
      dlg.setBody(h`<div class="pd-preview-wrap" data-print-preview><div class="pd-page">${BT.printSheet(layout, doc, { screen: true })}</div></div>`);
    }, function (err) { dlg.setBody(h`<div class="banner danger">${BT.api.message(err)}</div>`); });
    return dlg;
  };

  /* a table for printing: every row (not the page on screen) */
  BT.printTable = function (columns, rows, cell) {
    if (!rows.length) return h`<div class="pd-empty">لا يوجد</div>`;
    return h`<table class="pd-table"><thead><tr>${columns.map(function (c) { return h`<th class="${c.num ? 'num' : ''}">${c.label}</th>`; })}</tr></thead><tbody>${rows.map(function (r) { return h`<tr>${columns.map(function (c) { return h`<td class="${c.num ? 'num' : ''}">${cell(c, r)}</td>`; })}</tr>`; })}</tbody></table>`;
  };
})();
