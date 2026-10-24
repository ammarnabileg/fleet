// Broadcasts (ركن الإشعارات): a message composed in two languages, sent to one chosen driver with only the inbox on
// (push and WhatsApp are off here and shown so), the counts confirmed before sending, the history showing it delivered,
// and the driver's app reading it in his language (English when his own is not written).
const { test, expect, uid, phone, settled, search, clearToasts } = require('./fixtures');

test('composed, previewed with its counts, sent with only the inbox, delivered in the driver\'s language', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الإشعارات ' + n, en: 'Broadcast co ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'BC' + n, name: { ar: 'سائق الإشعارات ' + n, en: 'Broadcast driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(),
  });
  const app = await api.driverPhone(driver.id, 'e2e-bc-' + n);
  const top = () => admin.locator('.overlay[data-open]').last();

  await admin.goto('/admin.html#/broadcasts');
  await settled(admin);
  await admin.getByRole('button', { name: 'إشعار جديد' }).click();
  const m = top();
  await m.locator('[name=title_ar]').fill('اجتماع ' + n);
  await m.locator('[name=body_ar]').fill('اجتماع السائقين غداً الساعة التاسعة');
  await expect(m.locator('[data-count=ar]')).toContainText('35');
  await m.getByRole('tab', { name: /English/ }).click();
  await m.locator('[name=title_en]').fill('Meeting ' + n);
  await m.locator('[name=body_en]').fill('Drivers meeting tomorrow at nine');
  await expect(m.locator('[data-pv-title]')).toHaveText('اجتماع ' + n); // the preview, in Arabic
  await m.locator('[name=pv_lang]').selectOption('fr');
  await expect(m.locator('[data-pv-title]')).toHaveText('Meeting ' + n); // French not written: English
  // push and WhatsApp are off: unticked, and the way to the integrations page shown
  await expect(m.locator('[name=ch_push]')).toBeDisabled();
  await expect(m.locator('[name=ch_whatsapp]')).toBeDisabled();
  await expect(m.locator('[data-channel=push] a[href="#/integrations"]')).toHaveCount(1);
  await expect(m.locator('[name=ch_inbox]')).toBeChecked();
  await m.locator('label.option-card', { hasText: 'سائقون محددون' }).click();
  const filter = m.locator('[data-filter=employee_ids]');
  if (await filter.count()) await filter.fill('BC' + n);
  await m.locator('[data-multi=employee_ids] label', { hasText: 'BC' + n }).click();
  await m.getByRole('button', { name: 'متابعة' }).click();

  const c = top();
  await expect(c.locator('[data-confirm-recipients]')).toHaveText('1');
  await expect(c.locator('[data-count-channel=inbox]')).toContainText('1');
  await expect(c.locator('[data-inbox-only]')).toHaveText('1');
  await clearToasts(admin);
  await c.getByRole('button', { name: 'إرسال', exact: true }).click();
  await expect(admin.locator('.toast').last()).toContainText('أُرسل الإشعار');

  await search(admin, 'اجتماع ' + n);
  const row = admin.locator('#view tbody tr', { hasText: 'اجتماع ' + n });
  await expect(row).toContainText('أُرسل');
  await expect(row.locator('[data-stat=inbox]')).toContainText('1');
  await row.click();
  const d = top();
  await expect(d.locator('[data-stats-channel=inbox]')).toContainText('1');
  await expect(d).toContainText('وصل لكل المستلمين');

  const inbox = async (lang) => (await app.call('GET', '/driver/notifications', undefined, lang ? { 'Accept-Language': lang } : {}))
    .items.find((x) => x.kind === 'broadcast');
  const en = await inbox('en');
  expect([en.title, en.body]).toEqual(['Meeting ' + n, 'Drivers meeting tomorrow at nine']);
  expect((await inbox('fr')).title).toBe('Meeting ' + n);
  expect((await inbox('ar')).message).toBe('اجتماع ' + n + '\nاجتماع السائقين غداً الساعة التاسعة');
});
