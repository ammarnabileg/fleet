// The accountant's own entries from the panel: a manual entry written with its live difference, saved only once
// balanced, then approved; opening balances whose difference goes to 3900; the old system's books checked (an error
// shown) and then imported clean. The settings section «المحاسبة» shows its fields with their help.
const { test, expect, uid, settled, clearToasts } = require('./fixtures');
const { xlsx } = require('./xlsx');

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const OPENING = ['رمز الحساب', 'اسم الحساب', 'مدين', 'دائن', 'الرقم المدني للموظف'];
const ENTRIES = ['رقم القيد في النظام القديم', 'التاريخ', 'رمز الحساب', 'مدين', 'دائن', 'البيان', 'الرقم المدني'];

async function financeSettings(api, value) {
  const cur = (await api.get('/settings')).finance;
  return api.put('/settings/finance', { version: cur.version, value: Object.assign({}, cur.value, value) });
}

test.afterAll(async ({ playwright, baseURL }) => {
  // the books' start back as it was: the other specs enter documents of any date
  const ctx = await playwright.request.newContext({ baseURL });
  const login = await (await ctx.post('/api/v1/auth/login', { data: { username: process.env.ADMIN_USERNAME || 'admin', password: process.env.ADMIN_PASSWORD || 'correct-horse-battery' } })).json();
  const cur = await (await ctx.get('/api/v1/settings')).json();
  await ctx.put('/api/v1/settings/finance', { data: { version: cur.finance.version, value: Object.assign({}, cur.finance.value, { books_start_date: null }) }, headers: { 'X-CSRF-Token': login.csrf_token } });
  await ctx.dispose();
});

test('a manual entry, opening balances and the old books, from the entries tab', async ({ admin, api }) => {
  test.setTimeout(150_000);
  const n = uid();
  await financeSettings(api, { books_start_date: '2020-01-01', entry_approval: 'manual' });
  const company = await api.post('/companies', { name: { ar: 'شركة الافتتاح ' + n, en: 'Opening company ' + n } });
  const top = () => admin.locator('.overlay[data-open]').last();

  // ---- the settings: the accounting section with its fields
  await admin.goto('/admin.html#/settings?tab=system');
  await settled(admin);
  const section = admin.locator('form[data-sec=finance]');
  await expect(section).toContainText('المحاسبة');
  await expect(section.locator('[name=entry_approval]')).toHaveValue('manual');
  await expect(section.locator('[name=books_start_date]')).toHaveValue('2020-01-01');
  await expect(admin.locator('form[data-sec=cash] [data-weekdays]')).toContainText('السبت');

  // ---- a manual entry: saved only once balanced, then approved
  await admin.goto('/admin.html#/finance?tab=entries');
  await settled(admin);
  await admin.locator('#view [data-manual]').click();
  const m = top();
  await m.locator('[name=description]').fill('استحقاق إيجار ' + n);
  const rows = m.locator('tr[data-line]');
  await rows.nth(0).locator('select').selectOption({ label: '6130 · الإيجارات والسكن' });
  await rows.nth(0).locator('[data-debit]').fill('250');
  await rows.nth(1).locator('select').selectOption({ label: '2110 · الموردون ومراكز الصيانة' });
  await rows.nth(1).locator('[data-credit]').fill('200');
  await expect(m.locator('[data-diff]')).toHaveText('50.000');
  const save = m.getByRole('button', { name: 'حفظ القيد' });
  await expect(save).toBeDisabled();
  await rows.nth(1).locator('[data-credit]').fill('250');
  await expect(m.locator('[data-diff]')).toHaveText('0.000');
  await expect(save).toBeEnabled();
  await clearToasts(admin);
  await save.click();
  await expect(admin.locator('.toast').last()).toContainText('حُفظ القيد #');
  const row = admin.locator('#view [data-panel=entries] tbody tr', { hasText: 'استحقاق إيجار ' + n });
  await expect(row).toContainText('مسودة');
  await row.click();
  await expect(top().locator('tbody tr')).toHaveCount(2);
  await expect(top().getByRole('button', { name: 'حذف', exact: true })).toBeVisible(); // a manual draft can go
  await clearToasts(admin);
  await top().getByRole('button', { name: 'اعتماد', exact: true }).click();
  await expect(admin.locator('.toast').last()).toContainText('اعتُمد القيد');
  await expect(row).toHaveCount(0);

  // ---- opening balances: the difference to 3900, shown before saving
  await admin.locator('#view [data-opening]').click();
  const o = top();
  await o.locator('[name=company]').selectOption(String(company.id));
  const line = (code) => o.locator('tr[data-acc-line]', { hasText: code }).first();
  await line('1120').locator('[data-debit]').fill('1000');
  await line('2110').locator('[data-credit]').fill('300');
  await expect(o.locator('[data-opening-diff]')).toHaveText('700.000 دائن');
  await expect(o.locator('[data-equity]')).toContainText('3900');
  await clearToasts(admin);
  await o.getByRole('button', { name: 'حفظ الأرصدة' }).click();
  await expect(admin.locator('.toast').last()).toContainText('سُجّلت الأرصدة الافتتاحية');
  await expect(admin.locator('.toast').last()).toContainText('3900');
  const opening = (await api.get('/finance/entries?source_kind=opening&date_from=2019-12-31&date_to=2019-12-31&limit=500')).find((e) => e.company_id === company.id);
  const detail = await api.get('/finance/entries/' + opening.id);
  expect(detail.lines.map((l) => [l.account.code, l.debit, l.credit])).toEqual([
    ['1120', '1000.000', '0.000'], ['2110', '0.000', '300.000'], ['3900', '0.000', '700.000'],
  ]);

  // ---- the old system's books: an unbalanced entry shown as an error, then the corrected file imported
  const today = new Date().toLocaleDateString('en-GB', { timeZone: 'Asia/Kuwait' }); // dd/mm/yyyy
  const old = 'Q' + n;
  const book = (credit) => xlsx({
    'أرصدة افتتاحية': [OPENING],
    'قيود': [ENTRIES, [old, today, '6140', 12.5, null, 'هاتف ' + n], [old, today, '1110', null, credit]],
  });
  await admin.locator('#view [data-old-import]').click();
  const im = top();
  await im.locator('input[type=file]').setInputFiles({ name: 'old.xlsx', mimeType: XLSX, buffer: book(10) });
  await im.getByRole('button', { name: 'فحص' }).click();
  await expect(im.locator('[data-old-result] .banner.danger')).toContainText('غير متوازن');
  await expect(im.getByRole('button', { name: 'استيراد', exact: true })).toBeDisabled();
  await im.locator('input[type=file]').setInputFiles({ name: 'old.xlsx', mimeType: XLSX, buffer: book(12.5) });
  await im.getByRole('button', { name: 'فحص' }).click();
  await expect(im.locator('[data-old-result]')).toContainText('الملف سليم');
  await clearToasts(admin);
  await im.getByRole('button', { name: 'استيراد', exact: true }).click();
  await expect(admin.locator('.toast').last()).toContainText('تم الاستيراد');
  await im.getByRole('button', { name: 'إغلاق', exact: true }).last().click();
  const imported = admin.locator('#view [data-panel=entries] tbody tr', { hasText: 'OLD-' + old });
  await expect(imported).toContainText('هاتف ' + n);
  await expect(imported).toContainText('12.500');
});
