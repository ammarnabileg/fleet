// The reports a manager reads: kilometers by vehicle and driver, cash by age, daily work, payroll by month; each one
// filtered to one vehicle or one driver, exported to Excel (the file holds what the screen shows, in Arabic, numbers
// as numbers), and printed with its filters (saved as PDF from the print window).
const fs = require('fs');
const { test, expect, uid, phone, settled, jpeg } = require('./fixtures');
const { readXlsx } = require('./xlsx');

const kuwaitDay = () => new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 10);

async function setup(api) {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة التقارير ' + n, en: 'Reports company ' + n } });
  const plate = '44/' + n.slice(-6);
  const vehicle = await api.post('/vehicles', { plate_number: plate, make: 'Kia', model: 'Picanto', company_id: company.id, last_odometer_km: 20000 });
  const driver = await api.post('/employees', {
    employee_number: 'R' + n, name: { ar: 'سائق التقارير ' + n, en: 'Reports driver ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  const photo = () => api.upload('odo.jpg', 'image/jpeg', jpeg());
  // held for two days: 50 km to the start of today's work, 30 more to the return
  const custody = await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 20000, photo_sha256: await photo(), started_at: new Date(Date.now() - 2 * 86400e3).toISOString(),
  });
  const app = await api.driverPhone(driver.id, 'e2e-' + n);
  await app.call('POST', '/driver/odometer', { value_km: 20050, photo_sha256: await app.photo('camera'), recorded_at: new Date().toISOString(), lat: 29.37, lng: 47.97 });
  await api.post(`/custodies/${custody.id}/return`, { odometer_km: 20080, photo_sha256: await photo() }); // closes his day
  const report = await app.call('POST', '/driver/reports', { business_date: kuwaitDay(), orders_count: 21, cash_amount: '17.500', screenshot_sha256: await app.photo() });
  await api.post(`/daily-reports/${report.id}/approve`, {});
  // another vehicle and driver of the same company, which the filters must leave out
  const other = await api.post('/vehicles', { plate_number: '45/' + n.slice(-6), make: 'Kia', model: 'Rio', company_id: company.id, last_odometer_km: 9000 });
  const second = await api.post('/employees', {
    employee_number: 'S' + n, name: { ar: 'سائق آخر ' + n, en: 'Other driver ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  const c2 = await api.post('/custodies', {
    vehicle_id: other.id, driver_id: second.id, odometer_km: 9000, photo_sha256: await photo(), started_at: new Date(Date.now() - 86400e3).toISOString(),
  });
  await api.post(`/custodies/${c2.id}/return`, { odometer_km: 9040, photo_sha256: await photo() });
  return { n, plate, vehicle, driver };
}

/** The option of a filter's list that holds this text, once the list has loaded. */
async function option(field, text) {
  let found;
  await expect.poll(async () => {
    found = await field.evaluate((el, t) => [...document.getElementById(el.getAttribute('list')).options].map((o) => o.value).find((v) => v.includes(t)), text);
    return found;
  }).toBeTruthy();
  return found;
}

async function download(page, button) {
  const [file] = await Promise.all([page.waitForEvent('download'), button.click()]);
  return { name: file.suggestedFilename(), rows: readXlsx(fs.readFileSync(await file.path())) };
}

test('reports: filtered to a vehicle or a driver, exported to Excel, printed', async ({ admin, api }) => {
  test.setTimeout(150_000);
  const s = await setup(api);
  const asked = [];
  admin.on('request', (r) => { if (r.url().includes('/api/v1/reports/')) asked.push(r.url()); });

  // ---- kilometers: one vehicle
  await admin.goto('/admin.html#/reports?tab=km');
  await settled(admin);
  await admin.evaluate(() => { window.__printed = 0; window.print = () => { window.__printed += 1; }; }); // no print window in a test
  const km = admin.locator('[data-p=km]');
  const vehicleLabel = await option(km.locator('[name=vehicle]'), s.plate);
  await km.locator('[name=vehicle]').fill(vehicleLabel);
  await km.locator('button[type=submit]').click();
  const rows = km.locator('[data-veh] tbody tr');
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText(s.plate);
  await expect(km.locator('.kpi', { hasText: 'الكيلومترات' }).locator('.v')).toHaveText('80');
  await expect(km.locator('[data-drv] tbody tr').first()).toContainText(s.driver.name.ar);
  const file = await download(admin, km.locator('[data-export=xlsx]'));
  expect(file.name).toMatch(/^kilometers-vehicles-\d{4}-\d{2}-\d{2}-\d{4}-\d{2}-\d{2}\.xlsx$/);
  expect(file.rows[0].slice(0, 5)).toEqual(['اللوحة', 'النوع', 'الموديل', 'الكيلومترات', 'في العمل']);
  expect(file.rows.length).toBe(2); // the header and this vehicle: the filter went with the export
  expect([file.rows[1][0], file.rows[1][3], file.rows[1][4]]).toEqual([s.plate, 80, 80]);
  await km.locator('[name=section]').selectOption('drivers');
  const drivers = await download(admin, km.locator('[data-export=xlsx]'));
  expect(drivers.name).toMatch(/^kilometers-drivers-/);
  expect(drivers.rows[1][0]).toBe(s.driver.name.ar);

  // printed: every table, under the report's title and its filters
  await km.locator('[data-print]').click();
  const printed = admin.locator('#bt-print');
  await expect(printed).toContainText('تقرير الكيلومترات');
  await expect(printed).toContainText(vehicleLabel);
  await expect(printed.locator('table').first()).toContainText(s.plate);
  await expect.poll(() => admin.evaluate(() => window.__printed)).toBe(1);

  // a name that is not in the list is refused before anything is asked
  const before = asked.length;
  await km.locator('[name=vehicle]').fill('سيارة لا توجد');
  await km.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('اختر السيارة من القائمة');
  expect(asked.length).toBe(before);

  // ---- cash: the driver's approved collection, held since today
  await admin.goto('/admin.html#/reports?tab=cash');
  await settled(admin);
  const cash = admin.locator('[data-p=cash]');
  await cash.locator('[name=driver]').fill(await option(cash.locator('[name=driver]'), s.driver.employee_number));
  await cash.locator('button[type=submit]').click();
  const aging = cash.locator('[data-aging] tbody tr');
  await expect(aging).toHaveCount(1);
  await expect(aging.first()).toContainText('17.500');
  const held = await download(admin, cash.locator('[data-export=xlsx]'));
  expect(held.name).toMatch(/^cash-aging-/);
  expect(held.rows[0].slice(0, 4)).toEqual(['السائق', 'معتمد', 'غير معتمد', 'حتى يوم']);
  expect([held.rows[1][0], held.rows[1][1], held.rows[1][3]]).toEqual([s.driver.name.ar, 17.5, 17.5]);

  // ---- daily work: the same driver's day
  await admin.goto('/admin.html#/reports?tab=daily');
  await settled(admin);
  const daily = admin.locator('[data-p=daily]');
  await daily.locator('[name=driver]').fill(await option(daily.locator('[name=driver]'), s.driver.employee_number));
  await daily.locator('button[type=submit]').click();
  await expect(daily.locator('[data-t] tbody tr')).toHaveCount(1);
  await expect(daily.locator('[data-t] tbody tr').first()).toContainText('21');

  // ---- payroll by month: opens, and its Excel downloads
  await admin.goto('/admin.html#/reports?tab=payroll');
  await settled(admin);
  const payroll = admin.locator('[data-p=payroll]');
  await expect(payroll.locator('.kpi', { hasText: 'الصافي' })).toBeVisible();
  const runs = await download(admin, payroll.locator('[data-export=xlsx]'));
  expect(runs.name).toMatch(/^payroll-runs-\d{4}-\d{2}-\d{4}-\d{2}\.xlsx$/);
  expect(runs.rows[0].slice(0, 3)).toEqual(['الشهر', 'الشركة', 'الحالة']);
});
