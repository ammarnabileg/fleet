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
  const tab = (name) => admin.locator('#view [data-tabs="dash-week"] [role=tab]', { hasText: name });
  const title = admin.locator('[data-week-title]');
  const quiet = () => admin.evaluate(() => new Promise((ok) => setTimeout(ok, 400))); // past the chart's resize wait
  expect((await labels()).map(value)).toEqual(week.map((x) => x.orders));
  // every chart drawn after the switch to cash, in order: a resize draws the cash again and nothing else. Each tab's
  // chart used to stay subscribed to the size and draw its own numbers, so the orders came back under the cash title
  await quiet();
  await admin.evaluate(() => {
    const el = document.querySelector('[data-week-chart]');
    window.drawn = [];
    new MutationObserver(() => window.drawn.push([...el.querySelectorAll('rect.hit')].map((r) => r.getAttribute('aria-label'))))
      .observe(el, { childList: true });
  });
  await tab('الكاش').click();
  await expect(title).toContainText('الكاش');
  await admin.setViewportSize({ width: 1100, height: 900 });
  await quiet();
  const drawn = await admin.evaluate(() => window.drawn);
  expect(drawn.length).toBeGreaterThanOrEqual(2); // the switch, then the resize
  for (const chart of drawn) expect(chart.map(value)).toEqual(week.map((x) => Number(x.cash)));
  await tab('الطلبات').click();
  await expect(title).toContainText('الطلبات');
  expect((await labels()).map(value)).toEqual(week.map((x) => x.orders));

  await admin.locator('[data-week-table]').click();
  const rows = admin.locator('.overlay[data-open] tbody tr');
  await expect(rows).toHaveCount(7);
  await expect(rows.last()).toContainText(String(week[6].orders));
  await expect(rows.last()).toContainText(Number(week[6].cash).toFixed(3));
});

test('the drivers, the employees by status and each company apart, each opening its list', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الأرقام ' + n, en: 'Figures company ' + n } });
  await api.post('/employees', {
    employee_number: 'F' + uid(), name: { ar: 'سائق بلا سيارة ' + n, en: 'No car ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  const d = await api.get('/dashboard');
  expect(d.drivers.without_vehicle).toBeGreaterThanOrEqual(1);
  const mine = d.by_company.find((c) => c.company_id === company.id);
  expect([mine.on_duty, mine.reports_today, mine.cash_held]).toEqual([0, 0, '0.000']);

  await admin.goto('/admin.html#/dashboard');
  await settled(admin);
  await expect(admin.locator('[data-drivers]')).toContainText('بلا سيارة');
  await expect(admin.locator('[data-drivers]')).toContainText(String(d.drivers.without_vehicle));
  await expect(admin.locator(`[data-by-company] tr[data-company="${company.id}"]`)).toContainText('شركة الأرقام ' + n);
  const active = admin.locator('[data-hr] [data-status=active]');
  await expect(active).toContainText(String(d.hr.statuses.find((s) => s.code === 'active').count));
  await active.click();
  await expect(admin).toHaveURL(/#\/employees\?status=active/);
  await settled(admin);
  await expect(admin.locator('#view [data-f=status]')).toHaveValue('active');
});
