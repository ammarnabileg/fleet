/* =====================================================================
   BrilliantTech UI — data.js  (بيانات تجريبية فقط)
   كل الأسماء والأرقام وهمية لغرض العرض. المجاميع متسقة بين كل الشاشات:
   386 سيارة = 352 مسلّمة + 11 في الصيانة + 23 بلا سائق
   428 موظفاً = 391 على رأس العمل + 22 تحت إجراء الفيزا + 15 مستقيل
   تقارير اليوم: 338 بدأ · 301 أرسل (264 معتمد + 37 قيد المراجعة) · 37 متأخر
   الطلبات اليوم 7,826 · الكاش المُبلّغ اليوم 13,084.750 · أرصدة السائقين 9,482.750
   عند ربط النظام الفعلي: استبدل هذا الملف باستدعاءات الـ API بنفس شكل الكائنات.
   ===================================================================== */
(function () {
  'use strict';
  var BT = window.BT;
  var R = BT.rng(20261124);
  var TODAY = BT.config.today;
  var D = function (n) { return BT.date.add(TODAY, n); };   // D(-1) = أمس
  var U = 0.25;                                                // وحدة المبالغ 0.250 د.ك
  var toKd = function (u) { return BT.round3(u * U); };

  /* توزيع مجموع ثابت على n قيمة صحيحة بين min و max */
  function distribute(n, total, min, max, weights) {
    var raw = [], i;
    for (i = 0; i < n; i++) raw.push(weights ? weights[i] : min + R() * (max - min));
    var s = BT.sum(raw), out = raw.map(function (v) { return Math.max(min, Math.min(max, Math.round(v / s * total))); });
    var diff = total - BT.sum(out), guard = 0;
    while (diff !== 0 && guard++ < 200000) {
      var k = Math.floor(R() * n), step = diff > 0 ? 1 : -1;
      if (out[k] + step >= min && out[k] + step <= max) { out[k] += step; diff -= step; }
    }
    return out;
  }

  /* ---------------- المراجع الثابتة ---------------- */
  var data = BT.data = {};
  data.company = { name: 'أجواد جروب', legal: 'شركة أجواد لتوصيل الطلبات الاستهلاكية', branches: ['المهبولة', 'الفروانية'] };
  data.centers = [
    { id: 'C1', name: 'مركز الملا للصيانة', short: 'مركز الملا', area: 'الشويخ الصناعية', phone: '22000101', users: 2 },
    { id: 'C2', name: 'مركز الغانم', short: 'مركز الغانم', area: 'الري', phone: '22000202', users: 1 },
    { id: 'C3', name: 'ورشة الفحيحيل', short: 'ورشة الفحيحيل', area: 'الفحيحيل', phone: '23000303', users: 1 }
  ];
  data.stages = ['مستلمة', 'فحص', 'بانتظار اعتماد العرض', 'قيد الإصلاح', 'بانتظار قطع', 'مكتملة', 'جاهزة للاستلام', 'تم الاستلام'];
  data.stageTone = { 'مستلمة': 'n', 'فحص': 'b', 'بانتظار اعتماد العرض': 'o', 'قيد الإصلاح': 'b', 'بانتظار قطع': 'p', 'مكتملة': 'g', 'جاهزة للاستلام': 'g', 'تم الاستلام': 'n' };
  data.empStatusTone = { 'على رأس العمل': 'g', 'تحت إجراء الفيزا': 'o', 'مستقيل': 'n' };
  data.vehStatusTone = { 'مسلّمة': 'g', 'في الصيانة': 'b', 'بلا سائق': 'o', 'موقوفة': 'r' };
  data.reportTone = { 'معتمد': 'g', 'بانتظار المراجعة': 'o', 'انحراف عن المتوسط': 'r', 'مطلوب تعديل': 'p', 'مرفوض': 'r', 'متأخر: لم يُرسل': 'n' };
  data.signalTone = { 'يرسل': 'g', 'متأخر': 'o', 'انقطاع': 'r', 'خارج يوم العمل': 'p' };
  data.models = [['Toyota', 'Yaris'], ['Nissan', 'Sunny'], ['Suzuki', 'Dzire'], ['Hyundai', 'Accent'], ['Kia', 'Pegas'], ['Toyota', 'Corolla'], ['Mitsubishi', 'Attrage'], ['Chevrolet', 'Spark']];

  /* ---------------- الموظفون (428) ---------------- */
  var FIRST = ['Mohammed', 'Bilal', 'Faisal', 'Tariq', 'Arjun', 'Ramesh', 'Sanjay', 'Karim', 'Yasir', 'Nabil', 'Samir', 'Usman', 'Zubair', 'Kamal', 'Anil', 'Vijay', 'Sunil', 'Prakash', 'Dinesh', 'Manoj', 'Abdul', 'Salman', 'Adnan', 'Jamal', 'Khalid', 'Waleed', 'Hamza', 'Irfan', 'Asif', 'Naveed', 'Shahid', 'Sajid', 'Raju', 'Bikash', 'Deepak', 'Krishna', 'Ramil', 'Joel', 'Mark', 'Jomar', 'Rafiq', 'Shafiq', 'Habib', 'Nasir', 'Amir', 'Ravi', 'Santosh', 'Ganesh', 'Hari', 'Mahesh'];
  var LAST = ['Hussain', 'Ahmed', 'Sharma', 'Singh', 'Rahman', 'Uddin', 'Yousef', 'Mahmoud', 'Gurung', 'Tamang', 'Rai', 'Pillai', 'Menon', 'Das', 'Iqbal', 'Malik', 'Butt', 'Shaikh', 'Farooq', 'Siddiqui', 'Reyes', 'Santos', 'Cruz', 'Chowdhury', 'Mia', 'Karki', 'Magar', 'Joshi', 'Verma', 'Patel'];
  var NAT = { 'Gurung': 'نيبال', 'Tamang': 'نيبال', 'Rai': 'نيبال', 'Karki': 'نيبال', 'Magar': 'نيبال', 'Thapa': 'نيبال', 'Reyes': 'الفلبين', 'Santos': 'الفلبين', 'Cruz': 'الفلبين', 'Rahman': 'بنغلاديش', 'Uddin': 'بنغلاديش', 'Chowdhury': 'بنغلاديش', 'Mia': 'بنغلاديش', 'Islam': 'بنغلاديش', 'Yousef': 'مصر', 'Mahmoud': 'مصر', 'Salem': 'مصر', 'Hassan': 'مصر', 'Iqbal': 'باكستان', 'Malik': 'باكستان', 'Butt': 'باكستان', 'Shaikh': 'باكستان', 'Farooq': 'باكستان', 'Siddiqui': 'باكستان', 'Qadir': 'باكستان', 'Khan': 'باكستان' };
  function nat(name) { var l = name.split(' ').pop(); return NAT[l] || 'الهند'; }
  function phone() { return R.pick(['5', '6', '9']) + String(R.int(1000000, 9999999)); }
  function civil() { return '2' + String(R.int(10, 99)) + String(R.int(1000000, 9999999)) + String(R.int(10, 99)); }

  var STAFF = [
    { name: 'سامي الأنصاري', role: 'مدير العمليات', basic: 1200 },
    { name: 'نورة الشمري', role: 'الموارد البشرية', basic: 850 },
    { name: 'فهد الرشيدي', role: 'مشرف تشغيل', basic: 700 },
    { name: 'يوسف الكندري', role: 'مشرف تشغيل', basic: 700 },
    { name: 'Rajesh Menon', role: 'محاسب', basic: 520 },
    { name: 'Anil Pillai', role: 'محاسب', basic: 480 },
    { name: 'محمد السيد', role: 'مدير الصيانة', basic: 900 },
    { name: 'ريم العلي', role: 'المالية', basic: 800 }
  ];
  // سائقون مذكورون بالاسم في الشاشات (قيم ثابتة)
  var NAMED = ['Ahmed Ali', 'Rami Hassan', 'Imran Qadir', 'Suresh Kumar', 'Hassan Salem', 'Rahul Nair', 'Rahim Islam', 'Omar Thapa', 'Ahmed Khan'];
  var used = {}; NAMED.forEach(function (n) { used[n] = 1; });
  function newName() { var n, g = 0; do { n = R.pick(FIRST) + ' ' + R.pick(LAST); } while (used[n] && g++ < 500); used[n] = 1; return n; }

  var employees = data.employees = [];
  var eid = 1001;
  STAFF.forEach(function (s) {
    employees.push({ id: 'E-' + (eid++), name: s.name, role: s.role, status: 'على رأس العمل', branch: 'المهبولة', phone: phone(), civilId: civil(), nationality: /[؀-ۿ]/.test(s.name) ? 'الكويت' : 'الهند', join: D(-R.int(300, 1400)), basic: s.basic, staff: true });
  });
  // 420 سائقاً: 383 على رأس العمل (منهم 352 مع سيارة) + 22 فيزا + 15 مستقيل
  var driverNames = NAMED.slice();
  while (driverNames.length < 420) driverNames.push(newName());
  driverNames.forEach(function (n, i) {
    var status = i < 383 ? 'على رأس العمل' : i < 405 ? 'تحت إجراء الفيزا' : 'مستقيل';
    employees.push({ id: 'E-' + (eid++), name: n, role: 'سائق', status: status, branch: R() < .72 ? 'المهبولة' : 'الفروانية', phone: phone(), civilId: status === 'تحت إجراء الفيزا' ? '' : civil(), nationality: nat(n), join: status === 'تحت إجراء الفيزا' ? D(-R.int(3, 40)) : D(-R.int(60, 1500)), basic: R.pick([140, 145, 150, 150, 155, 160, 165, 170]) });
  });
  var byName = data.byName = {};
  employees.forEach(function (e) { byName[e.name] = e; });
  byName['Ahmed Ali'].basic = 150; byName['Omar Thapa'].basic = 170; byName['Rami Hassan'].basic = 145; byName['Hassan Salem'].basic = 165; byName['Suresh Kumar'].basic = 150;
  byName['Ahmed Ali'].phone = '65123480'; byName['Ahmed Ali'].nationality = 'الهند'; byName['Ahmed Ali'].join = '2024-03-10';
  var drivers = employees.filter(function (e) { return e.role === 'سائق'; });
  data.currentUser = employees[0];

  // مستندات: 17 مستنداً تنتهي خلال 30 يوماً (منها 3 مذكورة بالاسم)
  employees.forEach(function (e) {
    if (e.status === 'تحت إجراء الفيزا') { e.docs = [{ type: 'الجواز', exp: D(R.int(200, 1500)) }]; return; }
    e.docs = [{ type: 'الإقامة', exp: D(R.int(45, 700)) }, { type: 'الجواز', exp: D(R.int(120, 2500)) }];
    if (e.role === 'سائق') e.docs.splice(1, 0, { type: 'رخصة القيادة', exp: D(R.int(45, 1000)) });
  });
  byName['Rahul Nair'].docs[0].exp = '2026-12-09';
  byName['Imran Qadir'].docs[1].exp = '2026-12-18';
  byName['Suresh Kumar'].docs[2].exp = '2026-12-22';
  var pool = R.shuffle(drivers.filter(function (e) { return e.status === 'على رأس العمل' && NAMED.indexOf(e.name) < 0; })).slice(0, 14);
  pool.forEach(function (e, i) { e.docs[i % e.docs.length].exp = D(R.int(2, 30)); });
  byName['Ahmed Ali'].docs = [{ type: 'الإقامة', exp: '2027-06-14' }, { type: 'رخصة القيادة', exp: '2028-01-20' }, { type: 'الجواز', exp: '2029-09-02' }];
  employees.forEach(function (e) { if (e.status !== 'تحت إجراء الفيزا') e.device = { bound: e.status === 'على رأس العمل' && (e.role === 'سائق'), model: R.pick(['Samsung A14', 'Samsung A24', 'Redmi Note 12', 'Oppo A58', 'Realme C55', 'Samsung A34']), since: D(-R.int(5, 300)) }; });
  byName['Ahmed Ali'].device = { bound: true, model: 'Samsung A24', since: '2026-10-28' };
  data.docsExpiring = function (days) {
    var out = [];
    employees.forEach(function (e) { if (e.status === 'مستقيل') return; (e.docs || []).forEach(function (d) { var n = BT.date.daysLeft(d.exp); if (n >= 0 && n <= (days || 30)) out.push({ id: e.id + d.type, emp: e, type: d.type, exp: d.exp, days: n }); }); });
    return out.sort(function (a, b) { return a.days - b.days; });
  };

  /* ---------------- السيارات (386) ---------------- */
  var plates = {};
  function plate() { var p; do { p = R.int(10, 99) + '/' + R.int(10000, 99999); } while (plates[p]); plates[p] = 1; return p; }
  var V = function (p, make, model, year, extra) { plates[p] = 1; return Object.assign({ id: p, plate: p, make: make, model: model, year: year }, extra); };
  var withCar = drivers.filter(function (e) { return e.status === 'على رأس العمل'; }).slice(0, 352); // أول 352 سائقاً على رأس العمل
  var fixedCars = {
    'Ahmed Ali': V('18/23456', 'Toyota', 'Yaris', 2023, { odo: 45320, pos: [222, 168] }),
    'Rahul Nair': V('12/40077', 'Hyundai', 'Accent', 2022, { odo: 61840, pos: [262, 318] }),
    'Rahim Islam': V('30/66024', 'Nissan', 'Sunny', 2022, { odo: 58210, pos: [170, 250] }),
    'Suresh Kumar': V('27/30211', 'Suzuki', 'Dzire', 2023, { odo: 39870, pos: [238, 232] }),
    'Imran Qadir': V('41/88415', 'Kia', 'Pegas', 2023, { odo: 41236, pos: [112, 160] }),
    'Rami Hassan': V('33/19552', 'Toyota', 'Yaris', 2022, { odo: 66412, pos: [206, 290] }),
    'Omar Thapa': V('22/61503', 'Nissan', 'Sunny', 2021, { odo: 88105, pos: [248, 372] }),
    'Ahmed Khan': V('16/51190', 'Hyundai', 'Accent', 2023, { odo: 37642, pos: [228, 352] }),
    'Hassan Salem': V('25/72318', 'Suzuki', 'Dzire', 2022, { odo: 70355, pos: [266, 398] })
  };
  function randPos() { // نقطة داخل منطقة التشغيل تقريباً
    var a = R() * Math.PI * 2, r = Math.sqrt(R());
    var x = 222 + Math.cos(a) * 62 * r, y = 275 + Math.sin(a) * 112 * r;
    return [Math.round(Math.min(300, x)), Math.round(y)];
  }
  var vehicles = data.vehicles = [];
  withCar.forEach(function (e) {
    var v = fixedCars[e.name];
    if (!v) { var m = R.pick(data.models); v = V(plate(), m[0], m[1], R.int(2021, 2024), { odo: R.int(18000, 96000), pos: randPos() }); }
    v.status = 'مسلّمة'; v.driverId = e.id; e.vehicleId = v.id;
    vehicles.push(v);
  });
  var maintCars = [
    V('45/11820', 'Nissan', 'Sunny', 2021, { odo: 92430 }), V('18/30211', 'Toyota', 'Yaris', 2022, { odo: 71120 }), V('27/88410', 'Suzuki', 'Dzire', 2022, { odo: 64018 }),
    V('14/52209', 'Hyundai', 'Accent', 2021, { odo: 83560 }), V('36/70418', 'Kia', 'Pegas', 2023, { odo: 30211 })
  ];
  for (var mi = 0; mi < 6; mi++) { var mm = R.pick(data.models); maintCars.push(V(plate(), mm[0], mm[1], R.int(2021, 2024), { odo: R.int(30000, 90000) })); }
  maintCars.forEach(function (v) { v.status = 'في الصيانة'; vehicles.push(v); });
  for (var ni = 0; ni < 23; ni++) { var nm = R.pick(data.models); vehicles.push(V(plate(), nm[0], nm[1], R.int(2021, 2024), { odo: R.int(15000, 90000), status: 'بلا سائق' })); }
  vehicles.forEach(function (v, i) {
    v.color = R() < .7 ? 'أبيض' : R.pick(['فضي', 'رمادي', 'أسود']);
    v.branch = R() < .72 ? 'المهبولة' : 'الفروانية';
    v.insuranceExp = D(R.int(40, 360)); v.regExp = D(R.int(40, 360));
    v.nextServiceKm = (Math.floor(v.odo / 5000) + 1) * 5000 + (R() < .5 ? 1000 : 0);
    v.chassis = 'JT' + String(R.int(100000000, 999999999)) + String(R.int(1000, 9999));
  });
  var byPlate = data.byPlate = {};
  vehicles.forEach(function (v) { byPlate[v.plate] = v; });
  byPlate['18/23456'].insuranceExp = '2027-03-15'; byPlate['18/23456'].nextServiceKm = 46000; byPlate['18/23456'].color = 'أبيض'; byPlate['18/23456'].branch = 'المهبولة';
  byPlate['45/11820'].regExp = '2026-12-15';
  ['30/66024', '12/40077', '41/88415'].forEach(function (p, i) { byPlate[p].regExp = D([12, 26, 29][i]); });
  data.driverOf = function (v) { return v && v.driverId ? employees.find(function (e) { return e.id === v.driverId; }) : null; };
  data.vehicleOf = function (e) { return e && e.vehicleId ? byPlate[e.vehicleId] : null; };
  data.vehDocsExpiring = function (days) {
    var out = [];
    vehicles.forEach(function (v) { [['استمارة', v.regExp], ['التأمين', v.insuranceExp]].forEach(function (d) { var n = BT.date.daysLeft(d[1]); if (n >= 0 && n <= (days || 30)) out.push({ id: v.plate + d[0], v: v, type: d[0], exp: d[1], days: n }); }); });
    return out.sort(function (a, b) { return a.days - b.days; });
  };

  /* ---------------- التتبع ---------------- */
  // 352 مسلّمة: انقطاع 3 · متأخر 12 · يرسل 337 (منها 9 تتحرك بعد التقرير = خارج يوم العمل)
  var tracked = vehicles.filter(function (v) { return v.status === 'مسلّمة'; });
  var sig = R.shuffle(tracked.filter(function (v) { return !fixedCars[(data.driverOf(v) || {}).name]; }));
  tracked.forEach(function (v) { v.signal = 'يرسل'; v.lastSec = R.int(3, 45); v.speed = R() < .55 ? R.int(18, 92) : 0; });
  function setSig(v, s, sec) { v.signal = s; v.lastSec = sec; if (s === 'انقطاع') v.speed = null; }
  setSig(byPlate['30/66024'], 'انقطاع', 14 * 60);
  setSig(sig[0], 'انقطاع', 22 * 60); setSig(sig[1], 'انقطاع', 11 * 60);
  setSig(byPlate['12/40077'], 'متأخر', 6 * 60);
  for (var si = 2; si < 13; si++) setSig(sig[si], 'متأخر', R.int(2, 9) * 60);
  byPlate['18/23456'].lastSec = 12; byPlate['18/23456'].speed = 0;
  byPlate['27/30211'].lastSec = 20; byPlate['33/19552'].lastSec = 9; byPlate['41/88415'].lastSec = 30; byPlate['41/88415'].speed = 54;

  /* ---------------- التقارير اليومية (اليوم) ---------------- */
  // ترتيب الحالات: 338 بدأ، 301 أرسل، 37 متأخر، 14 لم يبدأ
  var carDrivers = withCar.slice();
  var fixedRep = {
    'Ahmed Ali': { orders: 25, cash: 40.5, status: 'بانتظار المراجعة', avgO: 23, avgC: 37.9, start: 45198, end: 45320, gps: 118, first: '11:02', last: '22:47', sent: '23:12' },
    'Rami Hassan': { orders: 21, cash: 33.25, status: 'معتمد', avgO: 22, avgC: 35.5, start: 66290, end: 66412, gps: 119, first: '10:40', last: '22:10', sent: '22:31' },
    'Imran Qadir': { orders: 18, cash: 52.75, status: 'انحراف عن المتوسط', avgO: 19, avgC: 36.13, start: 41076, end: 41236, gps: 118, first: '11:30', last: '21:55', sent: '22:20' },
    'Suresh Kumar': { orders: 27, cash: 44, status: 'مطلوب تعديل', avgO: 26, avgC: 42.5, start: 39742, end: 39870, gps: 124, first: '10:15', last: '22:30', sent: '22:52' },
    'Ahmed Khan': { orders: 23, cash: 36.75, status: 'بانتظار المراجعة', avgO: 24, avgC: 39.1, start: 37520, end: 37642, gps: 117, first: '11:10', last: '22:40', sent: '23:01' }
  };
  var others = R.shuffle(carDrivers.filter(function (e) { return !fixedRep[e.name] && e.name !== 'Hassan Salem'; }));
  var notStarted = others.slice(0, 14), late = [byName['Hassan Salem']].concat(others.slice(14, 50)); // 37 متأخر
  var senders = others.slice(50); // 296 + 5 ثابتة = 301
  var oUnits = distribute(senders.length, 7826 - 114, 10, 42);
  var cUnits = distribute(senders.length, Math.round((13084.75 - 207.25) / U), 48, 380, oUnits.map(function (o) { return o * (1.25 + R() * .8); }));
  var reports = data.reports = [];
  var rid = 88001;
  function mkReport(e, o) {
    var v = data.vehicleOf(e);
    var r = Object.assign({ id: 'R-' + (rid++), date: TODAY, empId: e.id, driver: e.name, plate: v ? v.plate : '', sent: o.sent || null }, o);
    reports.push(r); e.today = r; return r;
  }
  Object.keys(fixedRep).forEach(function (n) { mkReport(byName[n], fixedRep[n]); });
  var statuses = [];
  var i;
  for (i = 0; i < 264 - 1; i++) statuses.push('معتمد');                                   // + Rami = 264
  for (i = 0; i < 26 - 2; i++) statuses.push('بانتظار المراجعة');                        // + Ahmed Ali + Ahmed Khan = 26
  for (i = 0; i < 4; i++) statuses.push('انحراف عن المتوسط');                             // + Imran = 5
  for (i = 0; i < 3; i++) statuses.push('مطلوب تعديل');                                    // + Suresh = 4
  for (i = 0; i < 2; i++) statuses.push('مرفوض');                                         // 2
  R.shuffle(statuses);
  senders.forEach(function (e, k) {
    var orders = oUnits[k], cash = toKd(cUnits[k]), st = statuses[k];
    var dev = st === 'انحراف عن المتوسط' ? (R() < .5 ? 1.45 + R() * .3 : .5 - R() * .1) : .82 + R() * .34;
    var v = data.vehicleOf(e), km = R.int(88, 150), start = v.odo - km;
    var lastM = R.int(19 * 60, 22 * 60 + 50), sentM = Math.min(lastM + R.int(6, 45), 23 * 60 + 13); // الإرسال قبل "الآن" 23:14
    var hm = function (m) { return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0'); };
    mkReport(e, { orders: orders, cash: cash, status: st, avgO: Math.max(8, Math.round(orders / (.85 + R() * .3))), avgC: BT.round3(cash / dev), start: start, end: v.odo, gps: km - R.int(0, 6), first: '1' + R.int(0, 1) + ':' + String(R.int(0, 59)).padStart(2, '0'), last: hm(lastM), sent: hm(sentM) });
  });
  late.forEach(function (e) { mkReport(e, { orders: null, cash: null, status: 'متأخر: لم يُرسل', started: '0' + R.int(8, 9) + ':' + String(R.int(0, 59)).padStart(2, '0'), start: (data.vehicleOf(e) || {}).odo - R.int(80, 140) }); });
  notStarted.forEach(function (e) { e.today = null; });
  // "خارج يوم العمل": 9 سيارات أرسل سائقوها التقرير وما زالت تتحرك
  R.shuffle(senders.map(data.vehicleOf).filter(function (v) { return v.signal === 'يرسل'; })).slice(0, 8).concat([byPlate['41/88415']]).forEach(function (v) { v.outOfDay = true; v.speed = v.speed || R.int(20, 70); });
  data.vehicleSignal = function (v) { return v.signal === 'يرسل' && v.outOfDay ? 'خارج يوم العمل' : v.signal; };
  data.reportStats = function () {
    var s = { started: 0, sent: 0, approved: 0, review: 0, late: 0, orders: 0, cash: 0 };
    reports.forEach(function (r) { s.started++; if (r.orders != null) { s.sent++; s.orders += r.orders; s.cash += r.cash; if (r.status === 'معتمد') s.approved++; else s.review++; } else s.late++; });
    s.cash = BT.round3(s.cash); return s;
  };
  data.history = { // آخر 7 أيام (الأقدم أولاً) — اليوم = مجموع التقارير أعلاه
    days: [-6, -5, -4, -3, -2, -1, 0].map(D),
    orders: [7412, 7655, 7980, 7506, 8102, 7734, 7826],
    cash: [12104.25, 12618.5, 13402, 12236.75, 13915.25, 12807.5, 13084.75]
  };

  /* ---------------- الكاش: الأرصدة والإيصالات والخزينة ---------------- */
  // مجموع الأرصدة 9,482.750 · 14 سائقاً فوق حد التنبيه 80.000
  var balDrivers = carDrivers.filter(function (e) { return e.name !== 'Ahmed Khan' && e.name !== 'Ahmed Ali'; });
  R.shuffle(balDrivers);
  var high = balDrivers.slice(0, 13), rest = balDrivers.slice(13);
  var hUnits = high.map(function () { return R.int(322, 520); });
  var restTotal = Math.round(9482.75 / U) - 329 - 305 - BT.sum(hUnits);
  var rUnits = distribute(rest.length, restTotal, 0, 316, rest.map(function () { return Math.pow(R(), 1.6) * 300 + 4; }));
  byName['Ahmed Khan'].balance = 82.25; byName['Ahmed Ali'].balance = 76.25;
  high.forEach(function (e, k) { e.balance = toKd(hUnits[k]); });
  rest.forEach(function (e, k) { e.balance = toKd(rUnits[k]); });
  employees.forEach(function (e) { if (e.balance == null) e.balance = 0; });

  // الإيصالات: اليوم 118 إيصالاً (31045 → 31162) بمجموع 6,215.500 · الرقم التالي 31163
  var receipts = data.receipts = [];
  var collectors = ['Rajesh Menon', 'Anil Pillai'];
  var todayPayers = R.shuffle(carDrivers.filter(function (e) { return e.name !== 'Ahmed Khan' && e.name !== 'Ahmed Ali'; })).slice(0, 117);
  var rcUnits = distribute(117, Math.round((6215.5 - 50) / U), 80, 480);
  var rno = 31045, placed = false;
  todayPayers.forEach(function (e, k) {
    if (!placed && rno === 31107) { receipts.push({ id: 31107, no: 31107, date: TODAY, empId: byName['Ahmed Khan'].id, driver: 'Ahmed Khan', amount: 50, by: 'Rajesh Menon', status: 'بانتظار تأكيد السائق' }); rno++; placed = true; }
    receipts.push({ id: rno, no: rno, date: TODAY, empId: e.id, driver: e.name, amount: toKd(rcUnits[k]), by: R.pick(collectors), status: R() < .88 ? 'مؤكد' : 'بانتظار تأكيد السائق' });
    rno++;
  });
  receipts.forEach(function (x, k) { var m = 540 + Math.round(k * (1394 - 540) / 117); x.time = String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0'); }); // 09:00 → 23:14
  data.nextReceipt = 31163;
  receipts.push({ id: 31012, no: 31012, date: D(-1), time: '20:15', empId: byName['Ahmed Ali'].id, driver: 'Ahmed Ali', amount: 43, by: 'Anil Pillai', status: 'بانتظار تأكيد السائق' });
  receipts.push({ id: 30884, no: 30884, date: D(-2), time: '18:05', empId: byName['Ahmed Ali'].id, driver: 'Ahmed Ali', amount: 60, by: 'Rajesh Menon', status: 'مؤكد' });
  receipts.push({ id: 30871, no: 30871, date: D(-2), time: '17:20', empId: byName['Ahmed Khan'].id, driver: 'Ahmed Khan', amount: 70, by: 'Rajesh Menon', status: 'مؤكد' });
  receipts.push({ id: 30412, no: 30412, date: D(-6), time: '19:30', empId: byName['Ahmed Ali'].id, driver: 'Ahmed Ali', amount: 45, by: 'Anil Pillai', status: 'مؤكد' });
  receipts.sort(function (a, b) { return b.no - a.no; });
  data.treasury = {
    yesterday: 10124.75, collectedToday: 6215.5, depositedToday: 5000, balance: 11340.25,
    deposits: [
      { id: 'DP-1188', date: TODAY, amount: 5000, bank: 'البنك التجاري الكويتي', ref: 'CBK-778120', by: 'ريم العلي' },
      { id: 'DP-1187', date: D(-1), amount: 6000, bank: 'البنك التجاري الكويتي', ref: 'CBK-776904', by: 'ريم العلي' },
      { id: 'DP-1186', date: D(-2), amount: 7500, bank: 'البنك التجاري الكويتي', ref: 'CBK-775311', by: 'ريم العلي' }
    ]
  };

  // دفتر السائق: حركات آخر 5 أيام تنتهي بالرصيد الحالي
  var FIXED_LEDGER = {
    'Ahmed Khan': [
      [D(-4), 'رصيد افتتاحي', null, 43.75], [D(-3), 'كاش يومي', 38.25, 82], [D(-2), 'تحصيل · إيصال 30871', -70, 12, 'مؤكد'],
      [D(-2), 'كاش يومي', 41.5, 53.5], [D(-1), 'كاش يومي', 44, 97.5], [D(-1), 'تسوية · تعديل المراجع', -2, 95.5, 'بسبب مسجّل'],
      [TODAY, 'تحصيل · إيصال 31107', -50, 45.5, 'بانتظار تأكيد السائق'], [TODAY, 'كاش يومي (غير معتمد)', 36.75, 82.25]
    ],
    'Ahmed Ali': [
      [D(-4), 'رصيد افتتاحي', null, 21.5], [D(-4), 'كاش يومي', 37.5, 59], [D(-3), 'كاش يومي', 38.75, 97.75], [D(-2), 'تحصيل · إيصال 30884', -60, 37.75, 'مؤكد'],
      [D(-1), 'كاش يومي', 41, 78.75], [D(-1), 'تحصيل · إيصال 31012', -43, 35.75, 'بانتظار تأكيد السائق'], [TODAY, 'كاش يومي (غير معتمد)', 40.5, 76.25]
    ]
  };
  data.ledger = function (e) {
    var rows = FIXED_LEDGER[e.name];
    if (rows) return rows.map(function (r, k) { return { id: k, date: r[0], text: r[1], amount: r[2], balance: r[3], note: r[4] || '' }; });
    var L = BT.rng(parseInt(e.id.slice(2), 10) * 7919);
    var todayCash = e.today && e.today.cash != null ? e.today.cash : 0;
    var todayRc = receipts.filter(function (x) { return x.empId === e.id && x.date === TODAY; });
    var R0 = BT.sum(todayRc, function (x) { return x.amount; });
    var days = [D(-3), D(-2), D(-1)].map(function (d) { return [d, BT.round3(L.int(100, 200) * U)]; });
    var S = BT.sum(days, function (d) { return d[1]; }) + todayCash;
    var open = BT.round3(L.int(8, 120) * U), C = BT.round3(open + S - R0 - e.balance);
    if (C < 0) { C = 0; open = BT.round3(e.balance + R0 - S); }
    var out = [[D(-4), 'رصيد افتتاحي', null]];
    days.forEach(function (d, k) { out.push([d[0], 'كاش يومي', d[1]]); if (k === 1 && C > 0) out.push([d[0], 'تحصيل · إيصال ' + (30700 + L.int(0, 260)), -C, 'مؤكد']); });
    todayRc.forEach(function (x) { out.push([TODAY, 'تحصيل · إيصال ' + x.no, -x.amount, x.status]); });
    if (todayCash) out.push([TODAY, 'كاش يومي (غير معتمد)', todayCash]);
    var bal = open;
    return out.map(function (r, k) { if (r[2] != null) bal = BT.round3(bal + r[2]); return { id: k, date: r[0], text: r[1], amount: r[2], balance: k === 0 ? open : bal, note: r[3] || '' }; });
  };

  /* ---------------- سجل التسليم وسلسلة العداد ---------------- */
  data.assignments = [
    { id: 'A-9031', plate: '18/23456', driver: 'Ahmed Ali', from: D(-1) + ' 07:40', to: null, odoFrom: 45070, odoTo: null },
    { id: 'A-9018', plate: '18/23456', driver: 'Rami Hassan', from: D(-2) + ' 07:55', to: D(-2) + ' 23:10', odoFrom: 44953, odoTo: 45068 },
    { id: 'A-8940', plate: '18/23456', driver: 'Ahmed Ali', from: D(-9) + ' 08:00', to: D(-3) + ' 23:20', odoFrom: 44120, odoTo: 44941 }
  ];
  var aid = 9040;
  R.shuffle(tracked.filter(function (v) { return v.plate !== '18/23456'; })).slice(0, 26).forEach(function (v, k) {
    var e = data.driverOf(v), d = D(-Math.floor(k / 4));
    data.assignments.push({ id: 'A-' + (aid++), plate: v.plate, driver: e.name, from: d + ' 0' + R.int(7, 9) + ':' + String(R.int(0, 59)).padStart(2, '0'), to: null, odoFrom: v.odo - R.int(100, 900), odoTo: null });
  });
  data.odoChain = function (plate) {
    if (plate === '18/23456') return [
      { day: D(0), driver: 'Ahmed Ali', start: 45198, end: 45320, gap: 2 }, { day: D(-1), driver: 'Ahmed Ali', start: 45070, end: 45196, gap: 2 },
      { day: D(-2), driver: 'Rami Hassan', start: 44953, end: 45068, gap: 12, gapNote: 'بين إرجاع Ahmed Ali واستلام Rami Hassan' },
      { day: D(-3), driver: 'Ahmed Ali', start: 44815, end: 44941, gap: 3 }, { day: D(-4), driver: 'Ahmed Ali', start: 44690, end: 44812, gap: null }
    ];
    var v = byPlate[plate], e = data.driverOf(v), L = BT.rng(v.odo), end = v.odo, out = [];
    for (var k = 0; k < 5; k++) { var km = L.int(90, 150), gap = k === 4 ? null : L.int(0, 4); out.push({ day: D(-k), driver: e ? e.name : '—', start: end - km, end: end, gap: gap }); end = end - km - (gap || 0); }
    return out;
  };

  /* ---------------- مراجعة العداد ---------------- */
  data.odoReviews = [
    { id: 'OD-311', plate: '18/23456', driver: 'Rami Hassan', date: D(-2), kind: 'فرق بين يومين', detail: '12 كم بين إرجاع Ahmed Ali (44,941) واستلام Rami Hassan (44,953)', typed: 44953, prev: 44941, status: 'بانتظار المراجعة' },
    { id: 'OD-314', plate: '30/66024', driver: 'Rahim Islam', date: D(0), kind: 'أقل من السابقة', detail: 'القراءة المكتوبة 58,120 أقل من آخر قراءة 58,210', typed: 58120, prev: 58210, photo: 58210, status: 'بانتظار المراجعة' },
    { id: 'OD-315', plate: '41/88415', driver: 'Imran Qadir', date: D(0), kind: 'فرق كبير مع GPS', detail: 'العداد 160 كم · GPS 118 كم (فرق 42 كم)', typed: 41236, prev: 41076, status: 'بانتظار المراجعة' },
    { id: 'OD-309', plate: '27/30211', driver: 'Suresh Kumar', date: D(-1), kind: 'فرق بين يومين', detail: '7 كم بين نهاية يوم 23-11 وبداية يوم 24-11', typed: 39742, prev: 39735, status: 'تم القبول', by: 'فهد الرشيدي', reason: 'مشوار لمحطة الوقود بموافقة المشرف' },
    { id: 'OD-305', plate: '12/40077', driver: 'Rahul Nair', date: D(-2), kind: 'الصورة غير واضحة', detail: 'الأرقام غير مقروءة في الصورة', typed: 61610, prev: 61494, status: 'تم التصحيح', by: 'يوسف الكندري', reason: 'أعاد السائق التصوير في اليوم التالي' }
  ];

  /* ---------------- الصيانة (نوفمبر: 29 زيارة) ---------------- */
  var jobs = data.jobs = [];
  var jn = 2601;
  function job(o) { var j = Object.assign({ id: 'M-' + (jn++) }, o); j.vehicle = byPlate[j.plate] || null; jobs.push(j); return j; }
  job({ plate: '45/11820', center: 'C1', stage: 'قيد الإصلاح', days: 3, type: 'عطل', source: 'تطبيق السائق', desc: 'ارتفاع حرارة المحرك', opened: D(-3), cost: 118.5, estimate: { total: 118.5, status: 'معتمد' } });
  job({ plate: '18/30211', center: 'C1', stage: 'بانتظار اعتماد العرض', days: 1, type: 'عطل', source: 'تطبيق السائق', desc: 'صوت في ناقل الحركة', opened: D(-1), cost: 185, estimate: { total: 185, status: 'بانتظار الاعتماد', items: [['تبديل زيت ناقل الحركة', 35], ['حساس سرعة', 48], ['عمرة جزئية للقير', 102]] } });
  job({ plate: '27/88410', center: 'C1', stage: 'بانتظار قطع', days: 5, type: 'حادث', source: 'حادث A-0142', desc: 'إصلاح الصدام الأمامي والرفرف', opened: D(-5), cost: 150, accident: 'A-0142', estimate: { total: 150, status: 'معتمد' } });
  job({ plate: '14/52209', center: 'C1', stage: 'جاهزة للاستلام', days: 2, type: 'دورية', source: 'صيانة دورية', desc: 'صيانة 85,000 كم وتبديل فحمات', opened: D(-2), cost: 141, estimate: { total: 135, status: 'معتمد' }, invoice: { no: '7781', parts: 96, labour: 45, total: 141, status: 'بانتظار الاعتماد المالي' } });
  job({ plate: '36/70418', center: 'C1', stage: 'مستلمة', days: 0, type: 'عطل', source: 'تطبيق السائق', desc: 'المكيف لا يبرّد', opened: D(0), cost: 0 });
  var gh = maintCars.slice(5);
  job({ plate: gh[0].plate, center: 'C2', stage: 'فحص', days: 4, type: 'عطل', source: 'تطبيق السائق', desc: 'اهتزاز عند الفرملة', opened: D(-4), cost: 0 });
  job({ plate: gh[1].plate, center: 'C2', stage: 'قيد الإصلاح', days: 2, type: 'دورية', source: 'صيانة دورية', desc: 'صيانة 60,000 كم', opened: D(-2), cost: 64, estimate: { total: 64, status: 'معتمد' } });
  job({ plate: gh[2].plate, center: 'C2', stage: 'بانتظار قطع', days: 6, type: 'عطل', source: 'تطبيق السائق', desc: 'تبديل دينامو', opened: D(-6), cost: 96.5, estimate: { total: 96.5, status: 'معتمد' } });
  job({ plate: gh[3].plate, center: 'C2', stage: 'قيد الإصلاح', days: 1, type: 'حادث', source: 'حادث A-0144', desc: 'باب خلفي أيمن', opened: D(-1), cost: 0, accident: 'A-0144' });
  job({ plate: gh[4].plate, center: 'C3', stage: 'مستلمة', days: 1, type: 'دورية', source: 'صيانة دورية', desc: 'تبديل زيت وفلاتر', opened: D(-1), cost: 18.25 });
  job({ plate: gh[5].plate, center: 'C3', stage: 'مكتملة', days: 2, type: 'عطل', source: 'تطبيق السائق', desc: 'تبديل بطارية', opened: D(-2), cost: 32 });
  // 18 زيارة مغلقة هذا الشهر (المدة والتكلفة مضبوطة على متوسطات تقرير الصيانة)
  var closedDays = { C1: [2.5, 3, 2.8, 3.4, 1.9, 2.6, 3.1, 2.9, 3.2], C2: [3.2, 3.8, 3.5, 3.6, 3.5], C3: [2.1, 1.8, 2.4, 2.1] };
  var centerCost = { C1: 2140.5, C2: 1605, C3: 712.25 };
  var TYPES = [['دورية', 'صيانة دورية', 'صيانة دورية وتبديل زيت'], ['عطل', 'تطبيق السائق', 'تبديل فحمات الفرامل'], ['عطل', 'تطبيق السائق', 'إصلاح المكيف'], ['دورية', 'صيانة دورية', 'تبديل إطارات'], ['عطل', 'تطبيق السائق', 'تبديل مساعدات']];
  Object.keys(closedDays).forEach(function (c) {
    var openCost = BT.sum(jobs.filter(function (j) { return j.center === c; }), function (j) { return j.cost; });
    var cu = distribute(closedDays[c].length, Math.round((centerCost[c] - openCost) / U), 60, 2400);
    closedDays[c].forEach(function (d, k) {
      var t = R.pick(TYPES), p = R.pick(tracked).plate, cost = toKd(cu[k]);
      job({ plate: p, center: c, stage: 'تم الاستلام', days: d, type: t[0], source: t[1], desc: t[2], opened: D(-R.int(4, 23)), cost: cost, estimate: { total: cost, status: 'معتمد' }, invoice: { no: String(7700 + R.int(0, 79)), total: cost, status: 'مدفوعة' } });
    });
  });
  // 6 عروض فوق حد الاعتماد (100) اعتُمدت قبل الإصلاح
  data.overLimitApproved = function () { return jobs.filter(function (j) { return j.estimate && j.estimate.status === 'معتمد' && j.estimate.total > BT.config.approvalLimit; }).length; };
  data.centerStats = function () {
    return data.centers.map(function (c) {
      var js = jobs.filter(function (j) { return j.center === c.id; });
      return { center: c, visits: js.length, avgDays: BT.sum(js, function (j) { return j.days; }) / js.length, cost: BT.round3(BT.sum(js, function (j) { return j.cost; })) };
    });
  };
  data.centerName = function (id) { var c = data.centers.find(function (x) { return x.id === id; }); return c ? c.short : '—'; };

  /* ---------------- الحوادث ---------------- */
  data.accidents = [
    { id: 'A-0144', plate: gh[3].plate, driver: drivers[60].name, date: D(-2), time: '14:25', location: 'الفروانية', other: 'مركبة خاصة', injuries: 'لا يوجد', status: 'بانتظار تقدير التلفيات', statusTone: 'o', police: { no: '2026/4471', file: 'police_report_A0144.pdf' }, center: 'C2', estimate: null, liability: null },
    { id: 'A-0143', plate: '33/19552', driver: 'Rami Hassan', date: D(-1), time: '20:05', location: 'حولي', other: 'لا يوجد (اصطدام بعمود)', injuries: 'لا يوجد', status: 'بانتظار تقرير الشرطة', statusTone: 'r', police: null, center: null, estimate: null, liability: null },
    { id: 'A-0142', plate: '27/88410', driver: 'Omar Thapa', date: D(-5), time: '21:40', location: 'المهبولة', other: 'مركبة خاصة', injuries: 'لا يوجد', status: 'مغلق — خصم معتمد', statusTone: 'g', police: { no: '2026/4390', file: 'police_report_A0142.pdf' }, center: 'C1', estimate: 150, liability: 'السائق', installments: 3,
      timeline: [['بلاغ السائق من التطبيق', BT.fmt.dm(D(-5)) + ' · 21:52 · الموقع: المهبولة', 'g'], ['تقرير الشرطة مرفق', BT.fmt.dm(D(-4)) + ' · PDF', 'g'], ['تقدير التلفيات من مركز الملا', BT.fmt.dm(D(-3)) + ' · 150.000 د.ك', 'g'], ['اعتماد مدير الصيانة', BT.fmt.dm(D(-3)), 'g'], ['النتيجة وفق تقرير الشرطة', 'مسؤولية السائق', 'g'], ['خصم بالأقساط', '3 × 50.000 · نوفمبر – يناير', 'b']] },
    { id: 'A-0140', plate: R.pick(tracked).plate, driver: drivers[88].name, date: D(-12), time: '09:15', location: 'الأحمدي', other: 'مركبة نقل', injuries: 'لا يوجد', status: 'مغلق — على الطرف الآخر', statusTone: 'n', police: { no: '2026/4102', file: 'police_report_A0140.pdf' }, center: 'C3', estimate: 210, liability: 'الطرف الآخر' },
    { id: 'A-0139', plate: R.pick(tracked).plate, driver: drivers[141].name, date: D(-16), time: '17:48', location: 'مبارك الكبير', other: 'مركبة خاصة', injuries: 'إصابة طفيفة للسائق', status: 'مغلق — مسؤولية مشتركة', statusTone: 'n', police: { no: '2026/3988', file: 'police_report_A0139.pdf' }, center: 'C1', estimate: 96, liability: 'مشتركة 50%', installments: 2 }
  ];

  /* ---------------- الخصومات والرواتب (نوفمبر 2026) ---------------- */
  data.deductions = [
    { id: 'DD-201', empId: byName['Omar Thapa'].id, driver: 'Omar Thapa', reason: 'حادث A-0142', total: 150, count: 3, paid: 0, per: 50, start: 'نوفمبر 2026', status: 'معتمد' },
    { id: 'DD-202', empId: byName['Hassan Salem'].id, driver: 'Hassan Salem', reason: 'مخالفة مرورية', total: 12, count: 1, paid: 0, per: 12, start: 'نوفمبر 2026', status: 'معتمد' },
    { id: 'DD-198', empId: drivers[141].id, driver: drivers[141].name, reason: 'حادث A-0139 (50%)', total: 48, count: 2, paid: 1, per: 24, start: 'أكتوبر 2026', status: 'معتمد' }
  ];
  R.shuffle(drivers.filter(function (e) { return e.status === 'على رأس العمل' && NAMED.indexOf(e.name) < 0 && e !== drivers[141]; })).slice(0, 9).forEach(function (e, k) {
    var t = R.pick([['مخالفة مرورية', 10], ['مخالفة مرورية', 15], ['فقدان معدات التوصيل', 20], ['مخالفة وقوف', 5]]);
    data.deductions.push({ id: 'DD-' + (203 + k), empId: e.id, driver: e.name, reason: t[0], total: t[1], count: 1, paid: 0, per: t[1], start: 'نوفمبر 2026', status: k < 7 ? 'معتمد' : 'بانتظار الاعتماد' });
  });
  var fixedPay = { 'Ahmed Ali': [150, 10], 'Omar Thapa': [170, 0], 'Rami Hassan': [145, 15], 'Hassan Salem': [165, 0], 'Suresh Kumar': [150, 5] };
  data.payroll = {
    month: 'نوفمبر 2026', status: 'بانتظار الاعتماد',
    rows: employees.filter(function (e) { return e.status === 'على رأس العمل'; }).map(function (e) {
      var f = fixedPay[e.name];
      var inc = f ? f[1] : e.staff ? 0 : R.pick([0, 0, 5, 5, 10, 10, 15, 20]);
      var ded = BT.sum(data.deductions.filter(function (d) { return d.empId === e.id && d.status === 'معتمد'; }), function (d) { return d.per; });
      return { id: e.id, empId: e.id, name: e.name, role: e.role, basic: e.basic, incentives: inc, deductions: ded, dedNote: (data.deductions.find(function (d) { return d.empId === e.id && d.status === 'معتمد'; }) || {}).reason || '', net: BT.round3(e.basic + inc - ded) };
    })
  };
  var order = ['Ahmed Ali', 'Omar Thapa', 'Rami Hassan', 'Hassan Salem', 'Suresh Kumar'];
  data.payroll.rows.sort(function (a, b) { var x = order.indexOf(a.name), y = order.indexOf(b.name); return (x < 0 ? 99 : x) - (y < 0 ? 99 : y); });

  /* ---------------- المالية ---------------- */
  data.expenses = [
    { id: 'EX-4410', date: D(0), cat: 'صيانة', desc: 'فاتورة 7781 — مركز الملا', amount: 141, status: 'بانتظار الاعتماد' },
    { id: 'EX-4409', date: D(-1), cat: 'رسوم حكومية', desc: 'تجديد استمارات (6 سيارات)', amount: 60, status: 'معتمد' },
    { id: 'EX-4406', date: D(-2), cat: 'مخالفات', desc: 'مخالفات مرورية — تُخصم من السائقين', amount: 87, status: 'معتمد' },
    { id: 'EX-4401', date: D(-4), cat: 'تأمين', desc: 'تأمين 12 سيارة — نوفمبر', amount: 540, status: 'مدفوع' },
    { id: 'EX-4398', date: D(-6), cat: 'إيجارات', desc: 'إيجار مواقف السيارات — المهبولة', amount: 350, status: 'مدفوع' },
    { id: 'EX-4392', date: D(-9), cat: 'أخرى', desc: 'حقائب توصيل (40 حقيبة)', amount: 220, status: 'مدفوع' }
  ];

  /* ---------------- الاعتمادات ---------------- */
  data.approvals = [
    { id: 'AP-1', type: 'عرض سعر صيانة', title: 'عرض 185.000 — 18/30211', meta: 'مركز الملا · فوق حد الاعتماد 100.000', amount: 185, age: 'منذ 5 س', tone: 'o', link: 'maintenance', ref: 'M-2602' },
    { id: 'AP-2', type: 'فاتورة', title: 'فاتورة 7781 — 14/52209', meta: 'فرق +6.000 عن العرض المعتمد', amount: 141, age: 'منذ 2 س', tone: 'o', link: 'finance', ref: 'M-2604' },
    { id: 'AP-3', type: 'كشف رواتب', title: 'كشف رواتب نوفمبر 2026', meta: '391 موظفاً', amount: null, age: 'منذ يوم', tone: 'b', link: 'payroll' },
    { id: 'AP-4', type: 'تقارير يومية', title: '37 تقريراً بانتظار المراجعة', meta: 'منها 5 بانحراف عن المتوسط', amount: null, age: 'اليوم', tone: 'p', link: 'daily' },
    { id: 'AP-5', type: 'خصم', title: 'خصم ' + data.deductions[data.deductions.length - 1].driver, meta: data.deductions[data.deductions.length - 1].reason, amount: data.deductions[data.deductions.length - 1].total, age: 'منذ 3 س', tone: 'n', link: 'payroll' },
    { id: 'AP-6', type: 'مراجعة عداد', title: '3 قراءات عداد بانتظار المراجعة', meta: 'أقل من السابقة · فرق GPS · فرق بين يومين', amount: null, age: 'اليوم', tone: 'o', link: 'odometer' }
  ];

  /* ---------------- التنبيهات والإشعارات ---------------- */
  data.alerts = [
    { id: 'AL-1', level: 'حرج', tone: 'r', text: 'انقطاع إشارة هاتف السائق Rahim Islam منذ 14 دقيقة', link: 'tracking', plate: '30/66024', at: '23:00' },
    { id: 'AL-2', level: 'تحذير', tone: 'o', text: 'فرق عداد 12 كم بين يومين — سيارة 18/23456', link: 'odometer', plate: '18/23456', at: '07:56' },
    { id: 'AL-3', level: 'تحذير', tone: 'o', text: 'رصيد Ahmed Khan تجاوز حد التنبيه 80.000', link: 'cash', at: '23:01' },
    { id: 'AL-4', level: 'تحذير', tone: 'o', text: 'عرض سعر 185.000 بانتظار الاعتماد — مركز الملا', link: 'approvals', at: '18:12' },
    { id: 'AL-5', level: 'معلومة', tone: 'b', text: 'استمارة سيارة 45/11820 تنتهي بعد 21 يوماً', link: 'vehicles/45-11820', at: '08:00' }
  ];
  data.notifications = [
    { id: 'N1', icon: 'wifi-off', tone: 'r', text: 'انقطاع إشارة: Rahim Islam (30/66024)', at: 'منذ 14 د', unread: true, link: 'tracking' },
    { id: 'N2', icon: 'clipboard-list', tone: 'o', text: 'تقرير Ahmed Ali بانتظار مراجعتك', at: 'منذ 2 د', unread: true, link: 'daily' },
    { id: 'N3', icon: 'receipt-text', tone: 'b', text: 'فاتورة 7781 من مركز الملا بانتظار الاعتماد المالي', at: 'منذ 2 س', unread: true, link: 'finance' },
    { id: 'N4', icon: 'triangle-alert', tone: 'r', text: 'حادث جديد A-0143 — Rami Hassan (بانتظار تقرير الشرطة)', at: 'أمس', unread: false, link: 'accidents' },
    { id: 'N5', icon: 'file-badge', tone: 'o', text: 'إقامة Rahul Nair تنتهي بعد 15 يوماً', at: 'أمس', unread: false, link: 'employees' },
    { id: 'N6', icon: 'badge-check', tone: 'g', text: 'اعتمد محمد السيد تقدير حادث A-0142', at: 'منذ 3 أيام', unread: false, link: 'accidents' }
  ];

  /* ---------------- سجل التدقيق ---------------- */
  var AUD = [
    ['23:14', receipts[0].by, 'إصدار إيصال', 'إيصال ' + receipts[0].no + ' · ' + receipts[0].driver + ' · ' + BT.fmt.kwd(receipts[0].amount), 'Windows · 10.0.4.21'],
    ['23:12', 'Ahmed Ali', 'إرسال تقرير يومي', 'R-88001 · 25 طلباً · 40.500', 'Samsung A24 · تطبيق السائق'],
    ['22:58', 'فهد الرشيدي', 'اعتماد تقرير يومي', 'R-88002 · Rami Hassan', 'Chrome · 10.0.4.33'],
    ['22:41', 'يوسف الكندري', 'طلب تعديل تقرير', 'R-88004 · Suresh Kumar · السبب: لقطة الشاشة لا تطابق عدد الطلبات', 'Chrome · 10.0.4.35'],
    ['18:12', 'مركز الملا', 'إرسال عرض سعر', 'M-2602 · 18/30211 · 185.000', 'بوابة مراكز الصيانة'],
    ['16:05', 'ريم العلي', 'إيداع بنكي', 'DP-1188 · 5,000.000 · CBK-778120', 'Chrome · 10.0.4.40'],
    [receipts.find(function (x) { return x.no === 31107; }).time, 'Rajesh Menon', 'إصدار إيصال', 'إيصال 31107 · Ahmed Khan · 50.000', 'Windows · 10.0.4.21'],
    ['11:20', 'نورة الشمري', 'تغيير حالة موظف', 'E-1398: تحت إجراء الفيزا ← على رأس العمل', 'Chrome · 10.0.4.12'],
    ['09:02', 'سامي الأنصاري', 'تعديل قاعدة تشغيل', 'حد تنبيه الكاش: 75.000 ← 80.000', 'Chrome · 10.0.4.10'],
    ['07:56', 'النظام', 'تنبيه عداد', '18/23456 · فرق 12 كم بين يومين', 'تلقائي'],
    ['07:40', 'فهد الرشيدي', 'تسليم سيارة', '18/23456 ← Ahmed Ali · العداد 45,070', 'Chrome · 10.0.4.33'],
    ['02:00', 'النظام', 'نسخة احتياطية', 'اكتملت بنجاح · 1.8 GB', 'تلقائي']
  ];
  data.audit = AUD.sort(function (a, b) { return b[0].localeCompare(a[0]); }).map(function (a, k) { return { id: 'AU-' + (5210 - k), time: a[0], date: TODAY, user: a[1], action: a[2], detail: a[3], device: a[4] }; });

  /* ---------------- المستخدمون والأدوار ---------------- */
  data.roles = ['مدير النظام', 'مدير العمليات', 'مشرف تشغيل', 'محاسب', 'مدير الصيانة', 'الموارد البشرية', 'المالية', 'مركز صيانة', 'سائق'];
  data.users = STAFF.map(function (s, k) { var e = employees[k]; return { id: 'U-' + (10 + k), name: s.name, role: k === 0 ? 'مدير النظام' : s.role, email: '', phone: e.phone, last: k < 4 ? 'اليوم' : 'أمس', twoFA: true, active: true }; })
    .concat([{ id: 'U-31', name: 'مركز الملا — الاستقبال', role: 'مركز صيانة', phone: '22000101', last: 'اليوم', twoFA: true, active: true, center: 'C1' },
             { id: 'U-32', name: 'مركز الملا — المحاسبة', role: 'مركز صيانة', phone: '22000102', last: 'أمس', twoFA: true, active: true, center: 'C1' },
             { id: 'U-33', name: 'مركز الغانم', role: 'مركز صيانة', phone: '22000202', last: 'منذ 3 أيام', twoFA: true, active: true, center: 'C2' },
             { id: 'U-34', name: 'ورشة الفحيحيل', role: 'مركز صيانة', phone: '23000303', last: 'أمس', twoFA: false, active: true, center: 'C3' }]);
  data.permModules = ['لوحة التحكم', 'التتبع الحي', 'السيارات', 'تسليم السيارات', 'العداد', 'العمل اليومي', 'الكاش والخزينة', 'الصيانة', 'الحوادث', 'الموظفون', 'الرواتب', 'المالية', 'التقارير', 'الاعتمادات', 'الإعدادات'];
  data.permActions = ['عرض', 'إضافة', 'تعديل', 'اعتماد', 'حذف', 'تصدير'];
  data.perms = function (role) {
    var all = role === 'مدير النظام';
    return data.permModules.map(function (m, k) {
      return data.permActions.map(function (a, j) {
        if (all) return true;
        if (role === 'مشرف تشغيل') return k <= 5 && j <= 3 && j !== 4;
        if (role === 'محاسب') return (k === 6 && j !== 4) || (k === 0 && j === 0) || (k === 12 && (j === 0 || j === 5));
        if (role === 'مدير العمليات') return j !== 4 || k < 3;
        if (role === 'مدير الصيانة') return (k === 7 || k === 8) ? j !== 4 : (k === 2 && j === 0);
        if (role === 'الموارد البشرية') return (k === 9 || k === 10) ? j !== 4 : false;
        if (role === 'المالية') return (k === 11 || k === 6) ? j !== 4 : (k === 12 && (j === 0 || j === 5));
        return j === 0 && k < 2;
      });
    });
  };

  /* ---------------- مسار سيارة (للتتبع) ---------------- */
  data.route = function (plate, day) {
    var L = BT.rng((plate.replace(/\D/g, '') | 0) + day.length * 31 + (day === 'أمس' ? 7 : 0));
    var v = byPlate[plate], p = v && v.pos ? v.pos.slice() : [220, 270], pts = [p.slice()], stops = [];
    for (var k = 0; k < 26; k++) {
      p = [Math.max(150, Math.min(300, p[0] + L.int(-22, 22))), Math.max(150, Math.min(400, p[1] + L.int(-26, 26)))];
      pts.push(p.slice()); if (k % 6 === 3) stops.push(p.slice());
    }
    var rep = v && data.driverOf(v) && data.driverOf(v).today;
    return { points: pts, stops: stops, km: rep && rep.gps ? rep.gps : L.int(90, 140), start: '08:0' + L.int(0, 9), end: rep && rep.last ? rep.last : '22:' + L.int(10, 59), stopsCount: stops.length, maxSpeed: L.int(78, 104) };
  };
})();
