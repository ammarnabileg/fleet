// The employees list filtered by branch, department, job and whether the driver holds a vehicle now (BRD FR-HR-03);
// and a vehicle's file with its daily use over the last 30 days and the changes made to its record (FR-VEH-04).
const { test, expect, uid, phone, settled, jpeg } = require('./fixtures');

test('the employees list by branch, department, job and vehicle', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الفلاتر ' + n, en: 'Filters company ' + n } });
  const branch = await api.post('/branches', { name: { ar: 'فرع ' + n, en: 'Branch ' + n } });
  const person = (code, extra) => api.post('/employees', {
    employee_number: code + uid(), name: { ar: code + ' ' + n, en: code + ' ' + n }, company_id: company.id, ...extra,
  });
  const dept = 'قسم ' + n, job = 'وظيفة ' + n;
  const clerk = await person('كاتب', { department: dept, job_title: job, branch_id: branch.id });
  const driving = await person('يقود', { department: dept, is_driver: true, phone: phone() });
  const walking = await person('بلا سيارة', { department: dept, is_driver: true, phone: phone() });
  const vehicle = await api.post('/vehicles', { plate_number: '8/' + n.slice(-6), company_id: company.id, last_odometer_km: 100 });
  await api.post('/custodies', { vehicle_id: vehicle.id, driver_id: driving.id, odometer_km: 100, photo_sha256: await api.upload('o.jpg', 'image/jpeg', jpeg()) });

  await admin.goto('/admin.html#/employees');
  await admin.reload(); // the branches are read once when the panel opens
  await settled(admin);
  const view = admin.locator('#emp-table');
  const names = () => view.locator('tbody tr').allInnerTexts();
  const pick = async (key, value) => { await view.locator(`[data-f=${key}]`).selectOption(value); await settled(admin); };

  await pick('department', dept);
  await expect(view.locator('tbody tr')).toHaveCount(3);
  await pick('vehicle', 'true');
  await expect(view.locator('tbody tr')).toHaveCount(1);
  expect((await names())[0]).toContain(driving.name.ar);
  await pick('vehicle', 'false');
  await expect(view.locator('tbody tr')).toHaveCount(2);
  expect((await names()).join(' ')).toContain(walking.name.ar);
  await pick('vehicle', '');
  await pick('job', job);
  await expect(view.locator('tbody tr')).toHaveCount(1);
  expect((await names())[0]).toContain(clerk.name.ar);
  await pick('job', '');
  await pick('department', '');
  await pick('branch', String(branch.id));
  await expect(view.locator('tbody tr')).toHaveCount(1);
  expect((await names())[0]).toContain(clerk.name.ar);
});

test('a vehicle file shows its kilometers by day and the changes to its record', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الملف ' + n, en: 'File company ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '9/' + n.slice(-6), company_id: company.id, last_odometer_km: 5000 });
  const driver = await api.post('/employees', {
    employee_number: 'V' + uid(), name: { ar: 'سائق الملف ' + n, en: 'File driver ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  const custody = await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 5000, photo_sha256: await api.upload('a.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 3600e3).toISOString(),
  });
  await api.post(`/custodies/${custody.id}/return`, { odometer_km: 5120, photo_sha256: await api.upload('b.jpg', 'image/jpeg', jpeg()) });
  const now = await api.get('/vehicles/' + vehicle.id);
  await api.patch('/vehicles/' + vehicle.id, { version: now.version, color: 'أبيض' });

  await admin.goto('/admin.html#/vehicles/' + vehicle.id);
  await settled(admin);
  const usage = admin.locator('[data-veh-usage]');
  await expect(usage.locator('.kpi').first()).toContainText('120'); // 5000 to 5120 with the driver, today
  await expect(usage.locator('[data-usage-chart] rect.hit')).toHaveCount(30);
  const today = await usage.locator('[data-usage-chart] rect.hit').last().getAttribute('aria-label');
  expect(today).toContain('120');
  await usage.locator('[data-usage-table]').click();
  const rows = admin.locator('.overlay[data-open] tbody tr');
  await expect(rows).toHaveCount(30);
  await expect(rows.first()).toContainText('120'); // newest first
  await admin.locator('.overlay[data-open] .btn', { hasText: 'إغلاق' }).click();

  const audit = admin.locator('[data-veh-audit] [data-event]');
  await expect(audit).toHaveCount(2);
  await expect(audit.first()).toContainText('vehicle.updated');
  await expect(audit.last()).toContainText('vehicle.created');
  await audit.first().click();
  const drawer = admin.locator('.overlay[data-open]').last();
  await expect(drawer).toContainText('أبيض');
  await expect(drawer.locator('[data-device]')).toBeVisible(); // the client that made the change
});
