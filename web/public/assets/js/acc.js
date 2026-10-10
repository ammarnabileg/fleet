/* =====================================================================
   BrilliantTech — acc.js  (الحوادث: ما تشترك فيه لوحة الإدارة وبوابة المراكز)
   تسميات المراحل وحالة التقدير، الجدول الزمني، الصور، جدول الأقساط.
   الصفحة تمرّر fileUrl(sha) لأن الرابط يختلف بين /accidents و /portal/accidents.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT, h = BT.h, raw = BT.raw, icon = BT.icon, fmt = BT.fmt, api = BT.api;
  var C = BT.acc = {};

  C.STAGES = ['reported', 'awaiting_estimate', 'estimate_pending', 'estimate_rejected', 'awaiting_outcome', 'outcome_recorded', 'closed', 'cancelled'];
  C.TONE = {
    reported: 'o', awaiting_estimate: 'b', estimate_pending: 'o', estimate_rejected: 'r', awaiting_outcome: 'p',
    outcome_recorded: 'g', closed: 'n', cancelled: 'n'
  };
  C.EST_TONE = { none: 'n', pending: 'o', approved: 'g', rejected: 'r' };
  C.LIAB_TONE = { none: 'g', driver: 'r', shared: 'o' };
  C.NOTES = { ':replaced': 'استُبدل محضر الشرطة' };

  C.stage = function (s) { return BT.pill(api.t('accident_stage', s), C.TONE[s] || 'n'); };
  C.estimate = function (s) { return BT.pill(api.t('estimate_status', s), C.EST_TONE[s] || 'n'); };
  C.liability = function (a) {
    if (!a.liability) return raw('<span class="muted">لم تُحدد</span>');
    var pct = a.liability !== 'none' && a.liability_percent != null && Number(a.liability_percent) !== 100 ? ' · ' + Number(a.liability_percent) + '%' : '';
    return BT.pill(api.t('accident_liability', a.liability) + pct, C.LIAB_TONE[a.liability]);
  };
  C.police = function (a) {
    return a.has_police_report ? BT.pill('المحضر مرفق', 'g') : BT.pill('بانتظار محضر الشرطة', 'o');
  };
  C.note = function (n) { return n && n.charAt(0) === ':' ? (C.NOTES[n] || n.slice(1)) : n; };

  C.timeline = function (events) {
    var tones = { estimate_rejected: 'r', cancelled: 'r', estimate_approved: 'g', outcome: 'g', closed: 'g' };
    return h`<div class="timeline">${events.map(function (e) {
      var by = e.by === 'driver' ? 'السائق (من التطبيق)' : e.by;
      var note = e.kind === 'estimate_submitted' && e.note ? fmt.money(e.note) + ' د.ك' : C.note(e.note);
      return h`<div class="tl-item"><span class="tl-ic ${tones[e.kind] || 'b'}">${icon('circle-dot', 13)}</span><div><div class="tl-t">${api.t('accident_event', e.kind)}</div><div class="tl-d">${fmt.dt(e.at)}${by ? ' · ' + by : ''}</div>${note ? h`<div class="tl-d" style="white-space:normal">${note}</div>` : ''}</div></div>`;
    })}</div>`;
  };

  /* أقساط الخصم: الشهر والمبلغ */
  C.schedule = function (d) {
    if (!d) return '';
    return h`<div class="table-wrap"><table class="t"><thead><tr><th>الشهر</th><th class="num">القسط</th></tr></thead><tbody>${d.schedule.map(function (x) {
      var m = x.month.split('-');
      return h`<tr><td>${fmt.month(+m[0], +m[1])}</td><td class="num">${fmt.money(x.amount)}</td></tr>`;
    })}</tbody></table></div>`;
  };

  C.photos = function (shas, fileUrl) {
    return BT.mnt.thumbs((shas || []).map(function (s, i) { return { src: fileUrl(s), caption: 'صورة ' + (i + 1) }; }));
  };

  /* التقدير كما أرسله المركز */
  C.estimateCard = function (a, fileUrl, actions) {
    if (a.estimate_total == null && !a.estimate_reason) return '';
    return h`<div class="card mb-16"><div class="card-h"><div class="card-t">تقدير الأضرار</div><div>${C.estimate(a.estimate_status)}</div></div>
      ${a.estimate_total != null ? h`<div class="highlight-box mb-12 between"><b>الإجمالي</b><b>${BT.amt(a.estimate_total)}</b></div>` : ''}
      ${BT.mnt.itemsTable(a.estimate_items)}
      ${a.estimate_notes ? h`<div class="fs-sm mt-8" style="white-space:pre-wrap">${a.estimate_notes}</div>` : ''}
      ${a.estimate_reason ? h`<div class="fs-sm mt-8 t-danger">سبب الرفض: ${a.estimate_reason}</div>` : ''}
      <div class="muted fs-sm mt-8">${a.estimated_at ? fmt.dt(a.estimated_at) : ''}${a.estimate_decided_by ? ' · قرار: ' + a.estimate_decided_by : ''}${a.estimate_file_sha256 && fileUrl ? h` · <a href="${fileUrl(a.estimate_file_sha256)}" target="_blank" rel="noopener">ملف التقدير</a>` : ''}</div>
      ${actions || ''}</div>`;
  };
})();
