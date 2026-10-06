// Maintenance between the office and a center, each in its own browser: the driver's request from his phone, approved
// and referred; the center receives the vehicle, quotes; the office approves the quote; the center repairs, marks it
// ready and invoices; the driver sees it ready; the office records the pickup, approves and pays the invoice.
const { test, expect, uid, phone, settled, jpeg, pdf, centerWithUser, centerSignIn, kuwaitInput } = require('./fixtures');

// neither computer set to Kuwait time: the arrival time the center types is still Kuwait's
test.use({ timezoneId: 'UTC' });

const file = (name, mimeType, buffer) => ({ name, mimeType, buffer });

test('a repair from the driver\'s request to the paid invoice', async ({ admin, api, portal }) => {
  test.setTimeout(180_000);
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الصيانة ' + n, en: 'Maintenance company ' + n } });
  const plate = '9/' + n.slice(-6);
  const vehicle = await api.post('/vehicles', { plate_number: plate, make: 'Nissan', model: 'Sunny', company_id: company.id, last_odometer_km: 48000 });
  const driver = await api.post('/employees', {
    employee_number: 'W' + n, name: { ar: 'سائق الصيانة ' + n, en: 'Maintenance driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(),
  });
  await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 48100, photo_sha256: await api.upload('odo.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 2 * 3600e3).toISOString(),
  });
  const { center, username } = await centerWithUser(api, n);

  // ---- the driver asks from his phone, with a camera photo
  const app = await api.driverPhone(driver.id, 'e2e-' + n);
  const asked = await app.call('POST', '/driver/maintenance', {
    client_ref: require('crypto').randomUUID(), kind: 'mechanical', description: 'صوت من العجلة الأمامية',
    odometer_km: 48150, photos: [await app.photo('camera')],
  });
  expect(asked.status).toBe('requested');

  // ---- the office approves and refers it to the center
  const top = (page) => page.locator('.overlay[data-open]').last();
  await admin.goto('/admin.html#/maintenance/' + asked.id);
  await settled(admin);
  await admin.click('[data-action="mnt-approve"]');
  await top(admin).locator('button[type=submit]').click();
  await expect.poll(async () => (await api.get('/maintenance/requests/' + asked.id)).status).toBe('approved');
  await expect(admin.locator('[data-action="mnt-refer"]')).toBeVisible();
  await admin.click('[data-action="mnt-refer"]');
  await top(admin).locator('[name=center]').selectOption(center.id);
  await top(admin).locator('button[type=submit]').click();
  await expect.poll(async () => (await api.get('/maintenance/requests/' + asked.id)).status).toBe('referred');

  // ---- the center: first sign-in changes the password, then the request
  await centerSignIn(portal, username);
  await portal.goto('/center.html#/r/' + asked.id);
  await settled(portal);
  const step = async (act, fill) => {
    await portal.click(`[data-act="${act}"]`);
    const m = top(portal);
    if (fill) await fill(m);
    await m.locator('button[type=submit]').click();
    await expect(m).toBeHidden();
  };
  const arrived = kuwaitInput(Date.now() - 60e3); // a minute ago, as the center types it
  await step('receive', async (m) => {
    await m.locator('[name=at]').fill(arrived);
    await m.locator('[name=km]').fill('48210');
    await m.locator('[name=odo]').setInputFiles(file('odo.jpg', 'image/jpeg', jpeg()));
    await m.locator('[name=ph]').setInputFiles([file('front.jpg', 'image/jpeg', jpeg()), file('left.jpg', 'image/jpeg', jpeg())]);
    await m.locator('[name=cond]').fill('خدش بسيط في الباب الخلفي');
  });
  const received = (await api.get('/maintenance/requests/' + asked.id)).received_at;
  expect(new Date(received).toISOString()).toBe(new Date(arrived + ':00+03:00').toISOString()); // Kuwait time
  await step('inspection');
  await step('quote', async (m) => {
    await m.locator('[data-k=d]').fill('رولمان بلي أمامي');
    await m.locator('[data-k=q]').fill('2'); // two of them: the total multiplies
    await m.locator('[data-k=p]').fill('90');
    await m.locator('[data-items-add]').click();
    await m.locator('[data-k=kind]').nth(1).selectOption('labour');
    await m.locator('[data-k=d]').nth(1).fill('أجور التركيب');
    await m.locator('[data-k=p]').nth(1).fill('70');
    await expect(m.locator('[data-items-total]')).toContainText('250.000');
  });
  await expect.poll(async () => (await api.get('/maintenance/requests/' + asked.id)).status).toBe('quote_pending');

  // ---- the office approves the quote
  await admin.goto('/admin.html#/maintenance/' + asked.id);
  await admin.reload();
  await settled(admin);
  await admin.click('[data-q-ok]');
  await top(admin).locator('.btn-primary').last().click();
  await expect.poll(async () => (await api.get('/maintenance/requests/' + asked.id)).status).toBe('in_repair');

  // ---- the center repairs, marks it ready and invoices (a little above the quote)
  await portal.reload();
  await settled(portal);
  await step('complete', async (m) => {
    await m.locator('[name=details]').fill('تم تغيير رولمان البلي الأمامي الأيمن وفحص الميزان');
    await m.locator('[name=km]').fill('48236');
    await m.locator('[name=odo]').setInputFiles(file('odo2.jpg', 'image/jpeg', jpeg()));
  });
  await step('ready');
  const ready = (await app.call('GET', '/driver/maintenance')).find((x) => x.id === asked.id);
  expect(ready.status).toBe('ready'); // "your vehicle is ready" on his phone
  await step('invoice', async (m) => {
    await m.locator('[name=number]').fill('NR-' + n);
    await m.locator('[name=file]').setInputFiles(file('invoice.pdf', 'application/pdf', pdf()));
    await m.locator('[data-k=d]').fill('رولمان بلي');
    await m.locator('[data-k=q]').fill('2');
    await m.locator('[data-k=p]').fill('92.5');
    await m.locator('[data-items-add]').click();
    await m.locator('[data-k=kind]').nth(1).selectOption('labour');
    await m.locator('[data-k=d]').nth(1).fill('أجور');
    await m.locator('[data-k=p]').nth(1).fill('70');
    await expect(m.locator('[data-diff] .banner')).toBeVisible(); // differs from the approved quote
  });

  // ---- the office: picked up, the invoice approved then paid; the request closes
  await admin.goto('/admin.html#/maintenance/' + asked.id);
  await admin.reload();
  await settled(admin);
  await admin.click('[data-action="mnt-picked"]');
  await top(admin).locator('.btn-primary').last().click();
  await expect.poll(async () => (await api.get('/maintenance/requests/' + asked.id)).status).toBe('picked_up');
  await admin.goto('/admin.html#/maintenance?tab=invoices');
  await settled(admin);
  const invoiceRow = admin.locator('[data-p="invoices"] tbody tr', { hasText: 'NR-' + n });
  await invoiceRow.click();
  await expect(top(admin)).toContainText('255.000');
  await top(admin).locator('.btn-primary', { hasText: 'اعتماد' }).click();
  await top(admin).locator('.btn-primary').last().click();
  const invoice = async () => (await api.get('/maintenance/invoices?limit=200')).find((x) => x.number === 'NR-' + n);
  await expect.poll(async () => (await invoice()).status).toBe('approved');
  await expect.poll(async () => (await api.get('/maintenance/requests/' + asked.id)).status).toBe('closed');
  await admin.reload();
  await settled(admin);
  await admin.locator('[data-p="invoices"] .chip', { hasText: 'معتمدة غير مدفوعة' }).click();
  await settled(admin);
  await admin.locator('[data-p="invoices"] tbody tr', { hasText: 'NR-' + n }).click();
  await top(admin).locator('.btn-primary', { hasText: 'تسجيل الدفع' }).click();
  await top(admin).locator('[name=ref]').fill('TRX-' + n);
  await top(admin).locator('button[type=submit]').click();
  await expect.poll(async () => (await invoice()).payment_status).toBe('paid');
  const final = await invoice();
  expect([final.status, final.total, final.request && final.request.id, final.payment_ref]).toEqual(['approved', '255.000', asked.id, 'TRX-' + n]);
  const detail = await api.get('/maintenance/requests/' + asked.id);
  // the driver's photo; at reception two photos and the odometer; the odometer when the repair is done
  expect(detail.photos.map((x) => x.stage)).toEqual(['request', 'reception', 'reception', 'reception', 'repair']);
  expect(detail.quotes.map((q) => [q.status, q.amount, q.items.length])).toEqual([['approved', '250.000', 2]]);

  // ---- the two sides stay apart: the center's session reaches none of the company's data
  for (const path of ['/employees', '/vehicles', '/maintenance/requests', '/payroll/runs']) {
    const r = await portal.context().request.get('/api/v1' + path);
    expect([path, r.status()]).toEqual([path, 403]);
  }
});
