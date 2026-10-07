// The dashboard's last seven days: a report sent today shows in today's bar, the bars carry the API's numbers for
// orders then cash, and the table view lists the same days.
const { test, expect, uid, phone, settled } = require('./fixtures');

const day = (back) => new Date(Date.now() + 3 * 3600e3 - back * 86400e3).toISOString().slice(0, 10); // Kuwait date
const value = (label) => Number(label.split(': ')[1].split(' ')[0].replace(/,/g, '')); // "الأربعاء 07-10: 1,234 طلب"

test('the last seven days on the dashboard are the API\'s, orders then cash, and as a table', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة اللوحة ' + n, en: 'Dashboard company ' + n } });
  const platform = await api.post('/payroll/platforms', { code: 'd' + n, name: { ar: 'منصة ' + n, en: 'Platform ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'D' + uid(), name: { ar: 'سائق اللوحة ' + n, en: 'Dashboard driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(), platform_id: platform.id,
  });
  const before = (await api.get('/dashboard')).week;
  const app = await api.driverPhone(driver.id, 'e2e-' + n);
  await app.call('POST', '/driver/reports', { business_date: day(0), orders_count: 37, cash_amount: '12.500', screenshot_sha256: await app.photo() });
  const week = (await api.get('/dashboard')).week;
  expect(week.map((x) => x.day)).toEqual([6, 5, 4, 3, 2, 1, 0].map(day));
  expect(week[6].orders - before[6].orders).toBe(37); // today's bar has his report

  await admin.goto('/admin.html#/dashboard');
  await settled(admin);
  const bars = admin.locator('[data-week-chart] rect.hit');
  await expect(bars).toHaveCount(7);
  const labels = () => bars.evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')));
  expect((await labels()).map(value)).toEqual(week.map((x) => x.orders));
  await admin.locator('#view [data-tabs="dash-week"] [role=tab]', { hasText: 'الكاش' }).click();
  await expect(admin.locator('[data-week-title]')).toContainText('الكاش');
  expect((await labels()).map(value)).toEqual(week.map((x) => Number(x.cash)));

  await admin.locator('[data-week-table]').click();
  const rows = admin.locator('.overlay[data-open] tbody tr');
  await expect(rows).toHaveCount(7);
  await expect(rows.last()).toContainText(String(week[6].orders));
  await expect(rows.last()).toContainText(Number(week[6].cash).toFixed(3));
});
