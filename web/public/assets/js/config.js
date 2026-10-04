/* =====================================================================
   BrilliantTech — config.js  (إعدادات الواجهة وقت النشر)
   يمكن استبدال هذا الملف عند النشر دون إعادة بناء الصورة.
   اسم العميل لا يُكتب هنا: يأتي من إعدادات النظام (branding) عبر /api/v1/branding.
   ===================================================================== */
window.BT = window.BT || {};
BT.config = Object.assign(BT.config || {}, {
  /* خرائط التتبع الحي. خوادم OpenStreetMap العامة للتجربة والاستخدام الخفيف فقط (سياسة الاستخدام:
     https://operations.osmfoundation.org/policies/tiles/). في الإنتاج: مزوّد خرائط بعقد أو خادم خرائط ذاتي. */
  mapTiles: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  mapAttribution: '&copy; OpenStreetMap contributors',
  mapCenter: [29.31, 47.98],
  mapZoom: 11,
  refreshCountsSec: 60
});
