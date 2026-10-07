// The audit log searched by who acted, the record type and the day, then exported to Excel with the same filters:
// only the admin's company records of today, the sheet in Arabic.
const fs = require('fs');
const { test, expect, uid, settled } = require('./fixtures');
const { readXlsx } = require('./xlsx');

const today = () => new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 10); // Kuwait date

test('audit log: by user, record type and day, exported with the same filters', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة التدقيق ' + n, en: 'Audit company ' + n } });
  await api.post('/payroll/platforms', { code: 'a' + n, name: { ar: 'منصة ' + n, en: 'Platform ' + n } }); // another type

  await admin.goto('/admin.html#/audit');
  await settled(admin);
  const tools = admin.locator('#view .toolbar');
  const me = await tools.locator('[data-f=actor_id] option').evaluateAll((os) => os.find((o) => o.textContent.endsWith('(admin)')).value);
  await tools.locator('[data-f=actor_id]').selectOption(me);
  await tools.locator('[data-f=entity_type]').selectOption('company');
  await tools.locator('[data-f=date_from]').fill(today());
  await expect(admin.locator('#view [aria-busy]')).toHaveCount(0); // the rows of the last filter are drawn
  const rows = admin.locator('#view tbody tr');
  await expect(rows.filter({ hasText: company.public_id.slice(0, 8) })).toHaveCount(1);
  await expect(rows.filter({ hasText: 'منصة' })).toHaveCount(0);
  expect(await rows.evaluateAll((trs) => trs.every((tr) => tr.innerText.includes('شركة')))).toBe(true);

  const [file] = await Promise.all([admin.waitForEvent('download'), admin.locator('[data-audit-export=xlsx]').click()]);
  expect(file.suggestedFilename()).toBe(`audit-${today()}.xlsx`);
  const sheet = readXlsx(fs.readFileSync(await file.path()));
  expect(sheet[0].slice(0, 4)).toEqual(['الوقت (الكويت)', 'بواسطة', 'الإجراء', 'نوع السجل']);
  const data = sheet.slice(1);
  expect(data.length).toBeGreaterThan(0);
  expect(data.every((r) => r[3] === 'شركة' && r[1].endsWith('(admin)') && r[0].startsWith(today()))).toBe(true);
  expect(data.some((r) => r[2] === 'company.created')).toBe(true);
});
