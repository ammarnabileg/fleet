// Fuel from the panel (BRD FR-FUL-01..05, UAT-03): a clean fill from the app approved by itself, one above the tank
// held for review and approved with the reason from its drawer, a fill entered from a paper invoice, and the
// consumption and prices tabs.
const { test, expect, uid, phone, settled, clearToasts, jpeg } = require('./fixtures');

async function option(field, text) {
  let found;
  await expect.poll(async () => {
    found = await field.evaluate((el, t) => [...document.getElementById(el.getAttribute('list')).options].map((o) => o.value).find((v) => v.includes(t)), text);
    return found;
  }).toBeTruthy();
  return found;
}

test('fills checked: the clean one approved, the large one reviewed with a reason, one from an invoice', async ({ admin, api }) => {
  const n = uid();
  const make = 'Make' + n, model = 'M' + n.slice(-4);
  const day = (back) => new Date(Date.now() + 3 * 3600e3 - back * 86400e3).toISOString().slice(0, 10);
  await api.post('/fuel/prices', { fuel_type: 'super_95', price: '0.105', effective_from: day(400 + (Number(n) % 300)) }).catch(() => {}); // set once per database
  await api.post('/fuel/models', { make, model, tank_litres: '40', fuel_types: ['super_95'], litres_per_100km: '7.0' });
  const company = await api.post('/companies', { name: { ar: 'شركة الوقود ' + n, en: 'Fuel company ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '4/' + n.slice(-6), make, model, company_id: company.id, last_odometer_km: 30000 });
  const driver = await api.post('/employees', {
    employee_number: 'G' + uid(), name: { ar: 'سائق الوقود ' + n, en: 'Fuel driver ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 30000, photo_sha256: await api.upload('h.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 6 * 3600e3).toISOString(),
  });
  const app = await api.driverPhone(driver.id, 'e2e-' + n);
  const send = async (litres, amount, km, minutes) => app.call('POST', '/driver/fuel', {
    filled_at: new Date(Date.now() - minutes * 60e3).toISOString(), litres, amount, fuel_type: 'super_95', odometer_km: km,
    invoice_sha256: await app.photo('camera'), odometer_sha256: await app.photo('camera'),
  });
  const prices = await api.get('/fuel/prices');
  const price = Number(prices.current.super_95);
  const clean = await send('30', (30 * price).toFixed(3), 30100, 120);
  expect([clean.status, clean.flags]).toEqual(['approved', []]);
  const big = await send('48', (48 * price).toFixed(3), 30200, 60); // more than its 40-litre tank
  expect([big.status, big.flags]).toEqual(['pending', ['over_tank']]);

  const top = () => admin.locator('.overlay[data-open]').last();
  await admin.goto('/admin.html#/fuel');
  await settled(admin);
  const row = admin.locator('#fuel-fills tbody tr', { hasText: '#' + big.number });
  await expect(row).toContainText('أكثر من سعة الخزان');
  await expect(admin.locator('#fuel-fills tbody tr', { hasText: '#' + clean.number })).toHaveCount(0); // not waiting
  await row.click();
  const drawer = top();
  await expect(drawer.locator('[data-fuel-flags]')).toContainText('أكثر من سعة الخزان');
  await expect(drawer.locator('img')).toHaveCount(2); // the invoice and the odometer
  await drawer.getByRole('button', { name: 'اعتماد بسبب' }).click();
  await top().locator('[name=reason]').fill('خزان إضافي مركّب');
  await clearToasts(admin);
  await top().getByRole('button', { name: 'اعتماد' }).click();
  await expect(admin.locator('.toast').last()).toContainText('اعتُمدت التعبئة');
  const after = await api.get('/fuel/fills/' + big.id);
  expect([after.status, after.decision_note]).toEqual(['approved', 'خزان إضافي مركّب']);

  // from a paper invoice: the driver who held the car then
  await admin.locator('#view [data-action=fuel-new]').click();
  const m = top();
  await m.locator('[name=vehicle]').fill(await option(m.locator('[name=vehicle]'), vehicle.plate_number));
  await m.locator('[name=at]').fill(new Date(Date.now() + 3 * 3600e3 - 30 * 60e3).toISOString().slice(0, 16));
  await m.locator('[name=litres]').fill('20');
  await m.locator('[name=amount]').fill((20 * price).toFixed(3));
  await m.locator('[name=km]').fill('30300');
  await m.locator('[name=invoice]').setInputFiles({ name: 'inv.jpg', mimeType: 'image/jpeg', buffer: jpeg() });
  await clearToasts(admin);
  await m.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('سُجّلت التعبئة واعتُمدت');
  await expect(top()).toContainText(driver.name.ar);
  await top().getByRole('button', { name: 'إغلاق' }).last().click();

  await admin.locator('#view [data-tabs=fuel] [role=tab]', { hasText: 'الاستهلاك' }).click();
  const cons = admin.locator('#fuel-consumption tbody tr', { hasText: vehicle.plate_number });
  await expect(cons).toContainText('3'); // three approved fills
  await admin.locator('#view [data-tabs=fuel] [role=tab]', { hasText: 'الأسعار الرسمية' }).click();
  await expect(admin.locator('#fuel-prices .kpi', { hasText: 'خصوصي 95' })).toContainText(price.toFixed(3));
});
