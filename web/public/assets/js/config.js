/* =====================================================================
   BrilliantTech — config.js  (إعدادات الواجهة وقت النشر)
   يمكن استبدال هذا الملف عند النشر دون إعادة بناء الصورة.
   اسم العميل لا يُكتب هنا: يأتي من إعدادات النظام (branding) عبر /api/v1/branding.
   ===================================================================== */
window.BT = window.BT || {};
BT.config = Object.assign(BT.config || {}, {
  /* الخريطة: ملف واحد للكويت على خادمنا (Protomaps PMTiles من بيانات OpenStreetMap)، ينزّله ويحدّثه
     deploy/maps/update-map.sh. مجاني، بلا حدود استخدام، ولا يرى طرف ثالث مواقع السيارات. */
  mapPmtiles: 'maps/kuwait.pmtiles',
  /* فقط إن لم يوجد الملف على الخادم، مع ملاحظة ظاهرة على الخريطة. خوادم OpenStreetMap العامة للاستخدام الخفيف فقط
     (https://operations.osmfoundation.org/policies/tiles/) وتكشف لهم المنطقة المعروضة. '' = لا طرف ثالث أبداً. */
  mapFallbackTiles: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  mapCenter: [29.31, 47.98],
  mapZoom: 10,
  refreshCountsSec: 60
});
