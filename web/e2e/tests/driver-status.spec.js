// Drivers' status: a status template is edited with a live preview, published as a new config version and rolled
// back; a contact request sent from the panel reaches the driver's live status, is acknowledged from his phone (the
// same acknowledgement again changes nothing) and shows acknowledged in the panel, then is closed.
const { test, expect, uid, phone, settled, jpeg } = require('./fixtures');

test('a status template: edit with preview, publish, then back to the previous setting', async ({ admin, api }) => {
  const before = (await api.get('/driver-status/templates')).config_version;
  await admin.goto('/admin.html#/driver-status?tab=templates');
  await settled(admin);
  await expect(admin.locator('[data-config-version]')).toHaveText(String(before));

  await admin.locator('[data-edit="custody_settlement"]').click();
  const form = admin.locator('[data-template-form]');
  await expect(form.locator('[data-preview]')).toBeVisible();
  await form.locator('[name="title_ar"]').fill('سلّم {amount} الآن');
  await expect(form.locator('[data-preview-title]')).toHaveText('سلّم 125.500 الآن');
  await admin.getByRole('button', { name: 'نشر' }).click();
  await expect(admin.locator('[data-config-version]')).toHaveText(String(before + 1));
  await expect(admin.locator('[data-template="custody_settlement"] [data-template-title]')).toHaveText('سلّم {amount} الآن');

  await admin.locator('[data-rollback]').click();
  await admin.locator('.modal').getByRole('button', { name: 'رجوع' }).click();
  await expect(admin.locator('[data-config-version]')).toHaveText(String(before + 2));
  await expect(admin.locator('[data-template="custody_settlement"] [data-template-title]')).not.toHaveText('سلّم {amount} الآن');
});

test('a contact request reaches the driver, is acknowledged from his phone and closed', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الحالة ' + n, en: 'Status company ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '5/' + n.slice(-5), company_id: company.id, last_odometer_km: 1000 });
  const driver = await api.post('/employees', {
    employee_number: 'DS' + n, name: { ar: 'سائق الحالة ' + n, en: 'Status driver ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 1000, photo_sha256: await api.upload('h.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 3600e3).toISOString(),
  });
  const app = await api.driverPhone(driver.id, 'status-' + n);

  await admin.goto('/admin.html#/driver-status');
  await settled(admin);
  const row = admin.locator('#dst-status tr', { hasText: 'سائق الحالة ' + n });
  await expect(row.locator('[data-tracking]')).toHaveAttribute('data-tracking', 'stale'); // nothing sent yet: never "live"
  await row.locator('[data-contact]').click();
  await admin.locator('.modal [name="message"]').fill('اتصل بي عند وصولك');
  await admin.locator('.modal').getByRole('button', { name: 'إرسال' }).click();
  await expect(row.locator('[data-alert-code="contact_request"]')).toBeVisible();

  const live = await app.call('GET', '/driver/live-status');
  const contact = live.alerts.find((a) => a.code === 'contact_request');
  expect(contact.data.message).toBe('اتصل بي عند وصولك');
  expect(live.shift.state).toBe('off_duty');
  const ref = require('crypto').randomUUID();
  const ack = await app.call('POST', `/driver/contact-requests/${contact.data.request_id}/ack`, { client_ref: ref });
  expect(ack.status).toBe('acknowledged');
  const again = await app.call('POST', `/driver/contact-requests/${contact.data.request_id}/ack`, { client_ref: ref });
  expect(again).toEqual(ack);

  await admin.locator('[role=tab]', { hasText: 'طلبات التواصل' }).click();
  await settled(admin);
  const req = admin.locator('#dst-contacts tr', { hasText: 'سائق الحالة ' + n });
  await expect(req.locator('[data-contact-status]')).toHaveAttribute('data-contact-status', 'acknowledged', { timeout: 10_000 });
  await req.locator('[data-close]').click();
  await expect(admin.locator('#dst-contacts tr', { hasText: 'سائق الحالة ' + n })).toHaveCount(0);
});
