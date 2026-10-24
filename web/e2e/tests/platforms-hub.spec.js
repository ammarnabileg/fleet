// «الشركات المتعاقد معها»: the section in the menu with the two core platforms, a platform's page and its tabs, Keeta's
// default batch rule edited in the designer from the platform page, a driver's platform ID linked inline, a driver's
// company request from the app approved with his ID, and the old payroll links landing in the new section.
const { test, expect, uid, phone, settled, search, clearToasts } = require('./fixtures');

const top = (page) => page.locator('.overlay[data-open]').last();

async function core(api) {
  const list = await api.get('/payroll/platforms');
  return { keeta: list.find((p) => p.code === 'keeta'), talabat: list.find((p) => p.code === 'talabat') };
}

test('the section, a platform page and Keeta\'s batch rule edited from it', async ({ admin, api }) => {
  const { keeta, talabat } = await core(api);
  await admin.goto('/admin.html#/platforms');
  await settled(admin);
  const nav = admin.locator('#nav');
  await expect(nav).toContainText('الشركات المتعاقد معها');
  await expect(nav.locator(`a[href="#/platforms/${keeta.id}"]`)).toBeVisible();
  await expect(nav.locator(`a[href="#/platforms/${talabat.id}"]`)).toBeVisible();
  const card = admin.locator('[data-platform-card=keeta]');
  await expect(card).toContainText('أساسية');
  await expect(card.locator('[data-del]')).toHaveCount(0); // a core platform is never deleted

  await nav.locator(`a[href="#/platforms/${keeta.id}"]`).click();
  await settled(admin);
  await expect(admin.locator('#tb-title h1')).toContainText('كيتا');
  await expect(nav.locator(`a[href="#/platforms/${keeta.id}"]`)).toHaveClass(/active/);
  const tabs = admin.locator('#view [role=tab]');
  await expect(tabs).toHaveText(['نظرة عامة', 'أنظمة الدفع', 'السواقين ومعرّفاتهم', 'حقول التقرير', 'استيراد الشهر']);
  await expect(admin.locator('[data-overview]')).toBeVisible();

  // ---- a scheme from Keeta's default template (chosen already), a rate changed in the designer
  await admin.getByRole('tab', { name: 'أنظمة الدفع' }).click();
  await admin.click(`[data-new="${keeta.id}"]`);
  const m = top(admin);
  await expect(m.locator('input[name=template][value=keeta_batches]')).toBeChecked();
  await expect(m.locator('[data-templates]')).toContainText('الافتراضي للمنصة');
  const code = 'kb' + uid();
  await m.locator('[name=code]').fill(code);
  await m.locator('[name=name_ar]').fill('باتشات ' + code);
  await m.locator('[name=name_en]').fill('Batches ' + code);
  await clearToasts(admin);
  await m.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('أُنشئ النظام');
  const scheme = (await api.get('/payroll/schemes')).find((s) => s.platform_id === keeta.id && s.code === code);
  expect(scheme.blocks.map((b) => b.type)).toEqual(['batch_rate', 'star_day', 'special_day_violation', 'missing_orders', 'attendance_marks', 'required_days']);
  await admin.locator(`[data-scheme="${scheme.id}"]`).click();
  await settled(admin);
  await expect(admin.locator('#tb-title .crumbs')).toContainText('كيتا');
  await admin.click('[data-edit-block="0"]');
  const f = top(admin);
  await f.locator('[data-cell="rates:0:rate"]').fill('0.500');
  await f.locator('button[type=submit]').click();
  await expect(admin.locator('[data-block="0"]')).toContainText('0.500');
  await admin.click('#ds-save');
  await clearToasts(admin);
  await top(admin).locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('حُفظت النسخة');
  await expect.poll(async () => (await api.get(`/payroll/schemes/${scheme.id}/designer`)).versions[0].blocks[0].params.rates[0])
    .toEqual({ batch: 1, rate: '0.500' });
  await admin.click('#ds-back');
  await expect(admin).toHaveURL(new RegExp(`#/platforms/${keeta.id}\\?tab=schemes`));
});

test('a driver\'s platform ID linked from the platform page', async ({ admin, api }) => {
  const n = uid();
  const { keeta } = await core(api);
  const company = await api.post('/companies', { name: { ar: 'شركة المعرّف ' + n, en: 'ID company ' + n } });
  const d = await api.post('/employees', {
    employee_number: 'PI' + n, name: { ar: 'سائق المعرّف ' + n, en: 'ID driver ' + n }, company_id: company.id, is_driver: true, phone: phone(), platform_id: keeta.id,
  });
  await admin.goto(`/admin.html#/platforms/${keeta.id}?tab=drivers`);
  await settled(admin);
  await admin.locator('#view .chip', { hasText: 'بلا معرّف' }).click();
  await search(admin, 'PI' + n);
  const row = admin.locator('#view tbody tr', { hasText: 'PI' + n });
  await expect(row).toContainText('بلا معرّف');
  await row.locator('[name=pdid]').fill('KE-' + n);
  await clearToasts(admin);
  await row.getByRole('button', { name: 'حفظ' }).click();
  await expect(admin.locator('.toast').last()).toContainText('حُفظ المعرّف KE-' + n);
  await expect.poll(async () => (await api.get('/employees/' + d.id)).platform_driver_id).toBe('KE-' + n);
});

test('a driver\'s company request from the app approved with his ID', async ({ admin, api }) => {
  const n = uid();
  const { keeta, talabat } = await core(api);
  const company = await api.post('/companies', { name: { ar: 'شركة الطلب ' + n, en: 'Request company ' + n } });
  const d = await api.post('/employees', {
    employee_number: 'PR' + n, name: { ar: 'سائق الطلب ' + n, en: 'Request driver ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  const app = await api.driverPhone(d.id, 'dev-pr-' + n);
  const view = await app.call('GET', '/driver/platform-request');
  expect(view.ask).toBe(true);
  await app.call('POST', '/driver/platform-request', { platform_id: talabat.id, note: 'سائق ' + n });

  await admin.goto('/admin.html#/platforms?tab=requests');
  await settled(admin);
  const row = admin.locator('#view tbody tr', { hasText: 'سائق الطلب ' + n });
  await expect(row).toContainText('بانتظار الموافقة');
  await row.getByRole('button', { name: 'موافقة' }).click();
  const m = top(admin);
  await expect(m.locator('[name=platform_id]')).toHaveValue(String(talabat.id));
  await m.locator('[name=platform_driver_id]').fill('TB-' + n);
  await clearToasts(admin);
  await m.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('وُوفق الطلب');
  await expect.poll(async () => { const e = await api.get('/employees/' + d.id); return [e.platform_id, e.platform_driver_id]; })
    .toEqual([talabat.id, 'TB-' + n]);
  const after = await app.call('GET', '/driver/platform-request');
  expect([after.ask, after.platform.code]).toEqual([false, 'talabat']);
  expect(keeta.is_core).toBe(true);
});

test('the old payroll links land in the new section', async ({ admin }) => {
  await admin.goto('/admin.html#/payroll?tab=schemes');
  await expect(admin).toHaveURL(/#\/platforms\?tab=schemes$/);
  await settled(admin);
  await expect(admin.getByRole('tab', { name: 'أنظمة الدفع' })).toHaveAttribute('aria-selected', 'true');
  await admin.goto('/admin.html#/payroll?tab=platforms');
  await expect(admin).toHaveURL(/#\/platforms$/);
  await settled(admin);
  await expect(admin.locator('#plat-new')).toBeVisible();
  await admin.goto('/admin.html#/payroll');
  await settled(admin);
  await expect(admin.locator('#view [role=tab]', { hasText: 'أنظمة الدفع' })).toHaveCount(0);
});
