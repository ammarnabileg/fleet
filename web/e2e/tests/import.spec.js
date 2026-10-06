// Importing from Excel. The contract's template: checked without saving, imported all at once (vehicles with their
// documents, a driver and a supervisor, the driver's opening cash balance), imported again with changes (updated, never
// duplicated), and a file with one mistake refused with its sheet and row. Then a client's own workbook (other sheet
// names and columns, a sheet without a header row): the server's suggestion, a column it could not guess picked by hand,
// the driver told apart by his profession, and the driver without a phone given a first sign-in by civil ID.
const { test, expect, uid, settled, kuwaitInput } = require('./fixtures');
const { xlsx } = require('./xlsx');

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
// the template's sheets and columns, as the contract gave them to the client
const VEHICLES = ['السيارات', ['#', 'رقم اللوحة *', 'النوع *', 'الموديل *', 'السنة *', 'اللون *', 'رقم الهيكل (VIN) *', 'الشركة *', 'الفرع *', 'تاريخ انتهاء التأمين *', 'تاريخ انتهاء الاستمارة *']];
const PEOPLE = ['المستخدمون والسائقون', ['#', 'الاسم *', 'الدور *', 'الرقم المدني *', 'رقم الهاتف (لرمز التحقق) *', 'الشركة *', 'الفرع *', 'القسم *', 'الوظيفة *', 'الحالة الوظيفية *', 'الراتب الأساسي (د.ك) *', 'تاريخ انتهاء الإقامة *', 'موديل الهاتف (للسائقين)']];
const OPENING = ['الأرصدة الافتتاحية', ['#', 'اسم السائق *', 'الرقم المدني *', 'الرصيد الافتتاحي (د.ك) *', 'تاريخ الرصيد *', 'اعتماد المحاسب (الاسم) *']];

function template(vehicles, people, opening) {
  const sheet = ([, columns], rows) => [columns, ['مثال', ...columns.slice(1).map(() => 'x')], ...rows.map((r, i) => [i + 1, ...r])];
  return xlsx({ 'التعليمات': [['املأ الأوراق التالية']], [VEHICLES[0]]: sheet(VEHICLES, vehicles), [PEOPLE[0]]: sheet(PEOPLE, people), [OPENING[0]]: sheet(OPENING, opening) });
}

/** A civil ID with a valid check digit, from 9 digits. */
function civil(digits) {
  const w = [2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2];
  for (let k = 0; ; k++) {
    const base = digits + String(k).padStart(2, '0');
    const check = 11 - ([...base].reduce((s, d, i) => s + d * w[i], 0) % 11);
    if (check < 10) return base + check;
  }
}

const one = async (api, path, q) => {
  const rows = await api.get(path + '?q=' + encodeURIComponent(q));
  expect(rows.length, path + ' ' + q).toBe(1);
  return rows[0];
};

test('the contract template: checked, imported, imported again, a mistake refused', async ({ admin, api }) => {
  const n = uid();
  const company = 'شركة الاستيراد ' + n;
  await api.post('/companies', { name: { ar: company, en: 'Import company ' + n } });
  const branch = (await api.get('/branches')).find((b) => b.is_default).name.ar;
  const plates = ['41/' + n.slice(-6), '42/' + n.slice(-6)];
  const car = (plate, vin, color) => [plate, 'تويوتا', 'يارس', 2023, color, vin, company, branch, '15/03/2027', '20/06/2027'];
  const drv = { name: 'سائق الاستيراد ' + n, civil: civil('29' + n), phone: '5' + uid() };
  const sup = { name: 'مشرف الاستيراد ' + n, civil: civil('28' + n), phone: '6' + uid() };
  const person = (p, role, job, residence) => [p.name, role, p.civil, p.phone, company, branch, 'العمليات', job, 'على رأس العمل', '150.000', residence, 'Samsung A15'];
  const yesterday = kuwaitInput(Date.now() - 86400e3).slice(0, 10).split('-').reverse().join('/');
  const file = (color, residence, extra) => template(
    [car(plates[0], 'MR0AA0000BB' + n.slice(-6), color), car(plates[1], 'MR0AA0000BC' + n.slice(-6), 'أبيض')],
    [person(drv, 'سائق', 'سائق توصيل', residence), person(sup, 'مشرف', 'مشرف عمليات', '30/09/2027'), ...(extra || [])],
    [[drv.name, drv.civil, '12.500', yesterday, 'المحاسب']],
  );
  const panel = admin.locator('[data-p=template]');
  const result = panel.locator('[data-result]');
  const kpi = (label) => result.locator('.kpi', { hasText: label }).locator('.v');
  const choose = (buffer) => panel.locator('input[type=file]').setInputFiles({ name: 'بيانات العميل.xlsx', mimeType: XLSX, buffer });
  const apply = async () => {
    await panel.locator('[data-apply]').click();
    await admin.locator('.overlay[data-open]').last().getByRole('button', { name: 'تنفيذ', exact: true }).click();
    await expect(result).toContainText('تم الاستيراد');
    await expect(panel.locator('[data-apply]')).toBeHidden();
  };

  await admin.goto('/admin.html#/import');
  await settled(admin);

  // ---- checked: sound, and nothing saved yet
  await choose(file('أبيض', '30/09/2027'));
  await panel.locator('[data-check]').click();
  await expect(result).toContainText('الملف سليم وجاهز للتنفيذ');
  await expect(kpi('السيارات')).toHaveText('2 جديد · 0 تحديث');
  await expect(kpi('الموظفون والسائقون')).toHaveText('2 جديد · 0 تحديث');
  await expect(kpi('المستندات')).toHaveText('6'); // insurance and registration of each vehicle, each person's residence
  await expect(kpi('الأرصدة الافتتاحية')).toHaveText('1');
  expect(await api.get('/vehicles?q=' + encodeURIComponent(plates[0]))).toEqual([]);

  // ---- imported all at once
  await apply();
  const vehicle = await one(api, '/vehicles', plates[0]);
  expect([vehicle.make, vehicle.model, vehicle.year, vehicle.color]).toEqual(['تويوتا', 'يارس', 2023, 'أبيض']);
  const docs = await api.get(`/documents?owner_type=vehicle&owner_id=${vehicle.id}`);
  expect(docs.map((d) => [d.type_code, d.expiry_date]).sort()).toEqual([['insurance', '2027-03-15'], ['registration', '2027-06-20']]);
  const driver = await one(api, '/employees', drv.civil);
  expect([driver.is_driver, driver.phone, driver.basic_salary, driver.app_access]).toEqual([true, '+965' + drv.phone, '150.000', 'active']);
  const supervisor = await one(api, '/employees', sup.civil);
  expect([supervisor.is_driver, supervisor.app_access]).toEqual([false, 'none']);
  const cash = async () => (await api.get(`/cash/drivers/${driver.id}/statement`)).total;
  expect(await cash()).toBe('12.500');

  // ---- the same people and vehicles again, one colour and one residence changed: updated, never duplicated
  await choose(file('فضي', '30/09/2028'));
  await panel.locator('[data-check]').click();
  await expect(kpi('السيارات')).toHaveText('0 جديد · 2 تحديث');
  await expect(kpi('الموظفون والسائقون')).toHaveText('0 جديد · 2 تحديث');
  await expect(kpi('الأرصدة الافتتاحية')).toHaveText('0'); // already there
  await apply();
  expect((await one(api, '/vehicles', plates[0])).color).toBe('فضي');
  await one(api, '/employees', drv.civil);
  expect(await cash()).toBe('12.500'); // not counted twice

  // ---- one mistake in the file: refused with its sheet and row, nothing to execute
  const typo = [{ name: 'خطأ ' + n, civil: '2900101', phone: '9' + uid() }].map((p) => person(p, 'سائق', 'سائق توصيل', '30/09/2027'));
  await choose(file('أحمر', '30/09/2028', typo));
  await panel.locator('[data-check]').click();
  await expect(result).toContainText('1 خطأ');
  const err = result.locator('tbody tr');
  await expect(err).toHaveCount(1);
  await expect(err).toContainText(PEOPLE[0]);
  await expect(err.locator('td').nth(1)).toHaveText('5'); // the header, the example, then the third person
  await expect(err).toContainText('رقم مدني غير صحيح: 2900101');
  await expect(panel.locator('[data-apply]')).toBeHidden();
  expect((await one(api, '/vehicles', plates[0])).color).toBe('فضي');
});

test('a client\'s own workbook: suggested, corrected, drivers told apart, a first sign-in by civil ID', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الملف ' + n, en: 'Own sheets company ' + n } });
  const plate = '43/' + n.slice(-6);
  const rider = { name: 'سائق الملف ' + n, civil: civil('27' + n) };
  const clerk = { name: 'محاسب الملف ' + n, civil: civil('26' + n), phone: '6' + uid() };
  const book = xlsx({
    // headers in the client's words, one of them unknown to the server
    'Cars': [['No', 'Car Number', 'Vehicle Type', 'Model Year', 'Date of Expiry', 'تأمين حتى'], [1, plate, 'Nissan', 2022, '10/12/2027', '01/02/2027']],
    // no header row at all
    'Staff': [[1, rider.name, rider.civil, 'سائق دراجة', ''], [2, clerk.name, clerk.civil, 'محاسب', clerk.phone]],
    'ملاحظات': [],
  });

  await admin.goto('/admin.html#/import?tab=sheets');
  await settled(admin);
  const panel = admin.locator('[data-p=sheets]');
  await panel.locator('input[type=file]').setInputFiles({ name: 'ملف الشركة.xlsx', mimeType: XLSX, buffer: book });
  await expect(panel.locator('[data-sheet]')).toHaveCount(2);
  await expect(panel).toContainText('أوراق بلا بيانات لم تُعرض: ملاحظات');

  // ---- the server's suggestion, and the column it could not know picked by hand
  const cars = panel.locator('[data-sheet]', { hasText: 'Cars' });
  await expect(cars.locator('[name=kind]')).toHaveValue('vehicles');
  for (const [field, col] of [['plate_number', '1'], ['make', '2'], ['year', '3'], ['registration_expiry', '4'], ['insurance_expiry', '']]) {
    await expect(cars.locator(`[name=col_${field}]`), field).toHaveValue(col);
  }
  await cars.locator('[name=col_insurance_expiry]').selectOption('5');
  const staff = panel.locator('[data-sheet]', { hasText: 'Staff' });
  await expect(staff).toContainText('بلا صف عناوين');
  await expect(staff.locator('[name=kind]')).toHaveValue('employees');
  for (const [field, col] of [['name', '1'], ['civil_id', '2'], ['job_title', '3'], ['phone', '4']]) {
    await expect(staff.locator(`[name=col_${field}]`), field).toHaveValue(col);
  }

  // ---- the company, the first sign-in for drivers without a phone; checked, then imported
  await panel.locator('[name=company_id]').selectOption(String(company.id));
  await panel.locator('[name=claim_on]').check();
  await panel.locator('[name=claim_password]').fill('first-login-' + n);
  const result = panel.locator('[data-result]');
  const kpi = (label) => result.locator('.kpi', { hasText: label }).locator('.v');
  await panel.locator('[data-check]').click();
  await expect(result).toContainText('الملف سليم وجاهز للتنفيذ');
  await expect(kpi('السيارات')).toHaveText('1 جديد · 0 تحديث');
  await expect(kpi('الموظفون والسائقون')).toHaveText('2 جديد · 0 تحديث');
  await panel.locator('[data-apply]').click();
  await admin.locator('.overlay[data-open]').last().getByRole('button', { name: 'تنفيذ', exact: true }).click();
  await expect(result).toContainText('تم الاستيراد');
  await expect(kpi('يدخلون بالرقم المدني')).toHaveText('1'); // the rider, who has no phone in the file

  const vehicle = await one(api, '/vehicles', plate);
  expect([vehicle.make, vehicle.year, vehicle.company_id]).toEqual(['Nissan', 2022, company.id]);
  const docs = await api.get(`/documents?owner_type=vehicle&owner_id=${vehicle.id}`);
  expect(docs.map((d) => [d.type_code, d.expiry_date]).sort()).toEqual([['insurance', '2027-02-01'], ['registration', '2027-12-10']]);
  const r = await one(api, '/employees', rider.civil);
  const c = await one(api, '/employees', clerk.civil);
  expect([r.is_driver, r.job_title, r.phone, c.is_driver, c.job_title, c.phone]).toEqual([true, 'سائق دراجة', null, false, 'محاسب', '+965' + clerk.phone]);
});
