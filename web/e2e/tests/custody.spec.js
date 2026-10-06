// A vehicle from the office to a driver and back: the handover with the odometer photo, the driver's start of day
// from his phone, a reading below the handover reviewed and corrected, and the return. And the pickers list every
// driver: the handover form once showed the first 200 only, and the client has about 240.
const { test, expect, uid, phone, settled, jpeg } = require('./fixtures');

const photo = (name) => ({ name: name + '.jpg', mimeType: 'image/jpeg', buffer: jpeg() });

async function company(api, n) {
  return api.post('/companies', { name: { ar: 'شركة العهد ' + n, en: 'Custody company ' + n } });
}

test('the handover and receipt pickers list every driver, past the first 200', async ({ admin, api }) => {
  test.setTimeout(240_000);
  const n = uid();
  const c = await company(api, n);
  const names = [];
  for (let i = 0; i < 205; i++) {
    const d = await api.post('/employees', {
      employee_number: 'M' + n + String(i).padStart(3, '0'), name: { ar: `سائق ${n} رقم ${i}`, en: `Driver ${n} ${i}` },
      company_id: c.id, is_driver: true,
    });
    names.push(d.name.ar + ' — ' + d.employee_number);
  }
  const listed = (input) => admin.locator(input).evaluate((el) => [...el.list.options].map((o) => o.value));
  await admin.goto('/admin.html#/custody');
  await settled(admin);
  await admin.getByRole('button', { name: 'تسليم سيارة لسائق' }).click();
  await expect(admin.locator('.overlay[data-open] [name=driver]')).toBeVisible();
  const handover = await listed('.overlay[data-open] [name=driver]');
  expect(names.filter((x) => !handover.includes(x))).toEqual([]);
  await admin.keyboard.press('Escape');

  await admin.goto('/admin.html#/cash');
  await settled(admin);
  await admin.getByRole('button', { name: 'استلام كاش بإيصال' }).click();
  await expect(admin.locator('.overlay[data-open] [name=drv]')).toBeVisible();
  const receipt = await listed('.overlay[data-open] [name=drv]');
  expect(names.map((x) => x.split(' — ')[0]).filter((x) => !receipt.some((o) => o.startsWith(x + ' — ')))).toEqual([]);
});

test('handover, start of day, a low reading corrected, then the return', async ({ admin, api }) => {
  const n = uid();
  const c = await company(api, n);
  const plate = '7/' + n.slice(-6);
  const vehicle = await api.post('/vehicles', { plate_number: plate, make: 'Toyota', model: 'Yaris', company_id: c.id, last_odometer_km: 44800 });
  const driver = await api.post('/employees', {
    employee_number: 'H' + n, name: { ar: 'سائق العهدة ' + n, en: 'Custody driver ' + n }, company_id: c.id, is_driver: true,
    phone: phone(),
  });
  const top = () => admin.locator('.overlay[data-open]').last();

  // ---- the handover from the vehicle's file: the driver picked, the reading and its photo
  await admin.goto('/admin.html#/vehicles/' + vehicle.id);
  await settled(admin);
  await admin.click('#veh-handover');
  const h = top();
  await expect(h.locator('[name=odometer_km]')).toHaveValue('44800'); // the vehicle's last reading, to confirm
  await h.locator('[name=driver]').fill(driver.name.ar + ' — ' + driver.employee_number);
  await h.locator('[name=odometer_km]').fill('45000');
  await h.locator('input[name=odo_photo]').setInputFiles(photo('odo'));
  await h.locator('input[name=ph_front]').setInputFiles(photo('front'));
  await h.locator('button[type=submit]').click();
  await expect(h).toBeHidden();
  await expect(admin.locator('#veh-return')).toBeVisible(); // the file now offers the return
  const open = (await api.get('/custodies?open=true&limit=200')).find((x) => x.vehicle.plate_number === plate);
  expect([open.driver.id, open.kind]).toEqual([driver.id, 'normal']);
  let detail = await api.get('/custodies/' + open.id);
  expect(detail.readings.map((x) => [x.kind, x.value_km])).toEqual([['handover', 45000]]);
  expect(detail.photos.map((x) => [x.stage, x.position])).toEqual([['handover', 'front']]);

  // ---- his phone: the vehicle in his custody, and a start of day below the handover
  const app = await api.driverPhone(driver.id, 'e2e-' + n);
  const today = await app.call('GET', '/driver/today');
  expect([today.custody.plate_number, today.start_day_done]).toEqual([plate, false]);
  const low = await app.call('POST', '/driver/odometer', {
    kind: 'start_day', value_km: 44500, photo_sha256: await app.photo('camera'), recorded_at: new Date().toISOString(),
  });
  expect(low.flags).toContain('lower_than_previous');

  // ---- the reviewer corrects it with the reason
  await admin.goto('/admin.html#/odometer');
  await settled(admin);
  await admin.locator('#view tbody tr', { hasText: driver.name.ar }).click();
  const r = top();
  await r.locator('[name=corrected_km]').fill('45050');
  await r.locator('[name=reason]').fill('الصورة تقول 45050');
  await r.locator('button[type=submit]').click();
  await expect(r).toBeHidden();
  const reviewed = (await api.get('/odometer/readings?review_status=reviewed&limit=200')).find((x) => x.id === low.id);
  expect([reviewed.corrected_km, reviewed.effective_km, reviewed.review_reason]).toEqual([45050, 45050, 'الصورة تقول 45050']);

  // ---- the return from the vehicle's file
  await admin.goto('/admin.html#/vehicles/' + vehicle.id);
  await settled(admin);
  await admin.click('#veh-return');
  const back = top();
  await back.locator('[name=odometer_km]').fill('45230');
  await back.locator('input[name=odo_photo]').setInputFiles(photo('odo-back'));
  await back.locator('button[type=submit]').click();
  await expect(back).toBeHidden();
  await expect(admin.locator('#veh-handover')).toBeVisible();
  detail = await api.get('/custodies/' + open.id);
  expect(detail.ended_at).not.toBeNull();
  expect(detail.readings.map((x) => [x.kind, x.effective_km]).sort()).toEqual([['handover', 45000], ['return', 45230], ['start_day', 45050]]);
  expect((await app.call('GET', '/driver/today')).custody).toBeNull();
});
