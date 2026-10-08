// Fuel a driver paid from his cash: claimed from the app with the receipt's camera photo, approved in the panel with a
// corrected amount; the driver's cash goes down by the approved amount and the fuel movement shows in his statement.
const { test, expect, uid, phone, settled, search, jpeg } = require('./fixtures');

const kuwaitMonth = () => new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 7) + '-01';

test('fuel paid from the cash: claimed in the app, approved corrected in the panel, off the driver\'s balance', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة البنزين ' + n, en: 'Fuel company ' + n } });
  const platform = await api.post('/payroll/platforms', { code: 'f' + n, name: { ar: 'منصة ' + n, en: 'Platform ' + n } });
  const scheme = await api.post('/payroll/schemes', {
    platform_id: platform.id, code: 'gas' + n, name: { ar: 'بنزين على الشركة ' + n, en: 'Fuel on the company ' + n },
    calculator: 'per_order', per_order: '0.350', company_covers: ['gas'],
  });
  const driver = await api.post('/employees', {
    employee_number: 'F' + n, name: { ar: 'سائق البنزين ' + n, en: 'Fuel driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(), platform_id: platform.id,
  });
  const set = await api.post(`/payroll/schemes/${scheme.id}/assign`, { employee_ids: [driver.id], month: kuwaitMonth() });
  expect(set.set).toBe(1);
  const plate = '7/' + n.slice(-6);
  const vehicle = await api.post('/vehicles', { plate_number: plate, company_id: company.id, last_odometer_km: 20000 });
  await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 20000, photo_sha256: await api.upload('odo.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 2 * 86400e3).toISOString(),
  });
  const name = driver.name.ar;
  const top = () => admin.locator('.overlay[data-open]').last();

  // ---- his phone: fuel is on the company, he claims 7.250 with the receipt's photo
  const app = await api.driverPhone(driver.id, 'e2e-fuel-' + n);
  const view = await app.call('GET', '/driver/fuel');
  expect([view.allowed, view.reason]).toEqual([true, null]);
  const claim = await app.call('POST', '/driver/fuel', {
    client_ref: require('crypto').randomUUID(), paid_at: new Date(Date.now() - 20 * 60e3).toISOString(), amount: '7.250',
    odometer_km: 20150, receipt_sha256: await app.photo('camera'), notes: 'محطة السالمية',
  });
  expect(claim.status).toBe('pending');
  expect((await app.call('GET', '/driver/cash')).total).toBe('0.000'); // nothing until the accountant approves

  // ---- the accountant: the fuel tab's queue, approved at 6.500 with a note
  await admin.goto('/admin.html#/cash?tab=fuel');
  await settled(admin);
  const row = admin.locator('#view [data-pending="fuel"] [data-pending-id]', { hasText: name });
  await expect(row).toContainText('7.250');
  await expect(row).toContainText(plate);
  await expect(row.locator('.thumbs img')).toHaveCount(1);
  await row.getByRole('button', { name: 'قبول' }).click();
  const m = top();
  await m.locator('[name=amount]').fill('6.5');
  await m.locator('[name=note]').fill('المبلغ في الفاتورة 6.500');
  await m.locator('button[type=submit]').click();
  await expect(m).toBeHidden();
  await expect(row).toHaveCount(0);
  const all = admin.locator('#view [data-fuel-table] tbody tr', { hasText: name });
  await expect(all).toContainText('مقبول');
  await expect(all).toContainText('6.500');

  // ---- his cash went down by the approved amount, as a fuel movement
  const cash = await app.call('GET', '/driver/cash');
  expect(cash.total).toBe('-6.500');
  expect([cash.lines[0].kind, cash.lines[0].amount]).toEqual(['fuel', '-6.500']);
  expect((await app.call('GET', '/driver/fuel')).claims.map((c) => [c.status, c.approved_amount])).toEqual([['approved', '6.500']]);

  // ---- the journal in his statement, from the balances tab
  await admin.goto('/admin.html#/cash?tab=balances');
  await settled(admin);
  await search(admin, name);
  await admin.locator('#view tbody tr', { hasText: name }).click();
  const drawer = admin.locator('.drawer, .overlay[data-open]').last();
  await expect(drawer).toContainText('بنزين');
  await expect(drawer).toContainText('6.500');
});
