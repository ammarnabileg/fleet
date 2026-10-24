// A new alert reaches the open screen by itself: a toast says what arrived, the bell counts it, and the dashboard or
// the alerts page redraw in place; an open drawer is never closed for it (the redraw waits until it is).
const { test, expect, uid, settled } = require('./fixtures');

async function fineWithNobodyDriving(api, n) {
  const company = await api.post('/companies', { name: { ar: 'شركة التنبيه ' + n, en: 'Live alert company ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '5/' + n.slice(-6), company_id: company.id, last_odometer_km: 100 });
  await api.post('/fines', { vehicle_id: vehicle.id, occurred_at: new Date(Date.now() - 3600e3).toISOString(), violation: 'وقوف ' + n, amount: '5' });
  return vehicle;
}
const poll = (page) => page.evaluate(() => document.dispatchEvent(new Event('visibilitychange'))); // what a tab does on return

test('a new alert shows on the open dashboard without reloading', async ({ admin, api }) => {
  const n = uid();
  await admin.goto('/admin.html');
  await settled(admin);
  const badge = admin.locator('#bell-badge');
  const before = Number((await badge.isVisible()) ? (await badge.textContent()).replace('+', '') : 0);
  const vehicle = await fineWithNobodyDriving(api, n);
  await poll(admin);
  await expect(admin.locator('.toast').last()).toContainText(vehicle.plate_number);
  await expect(admin.locator('#view .li', { hasText: vehicle.plate_number })).toHaveCount(1); // the dashboard card, redrawn
  if (before < 99) await expect(badge).toHaveText(String(before + 1));
});

test('the alerts page lists a new alert by itself, and an open drawer is left alone', async ({ admin, api }) => {
  const n = uid();
  await admin.goto('/admin.html#/alerts');
  await settled(admin);
  const first = await fineWithNobodyDriving(api, n);
  await poll(admin);
  const row = admin.locator('#alerts-table tbody tr', { hasText: first.plate_number });
  await expect(row).toHaveCount(1);
  await row.locator('[data-action="alert-open"]').click(); // a drawer is open...
  const drawer = admin.locator('.overlay[data-open]').last();
  await expect(drawer).toBeVisible();
  const second = await fineWithNobodyDriving(api, n + 'b');
  await poll(admin); // ...a new alert arrives: toast, but the drawer stays
  await expect(admin.locator('.toast').last()).toContainText(second.plate_number);
  await expect(drawer).toBeVisible();
  await admin.keyboard.press('Escape');
  await poll(admin); // closed: the page catches up
  await expect(admin.locator('#alerts-table tbody tr', { hasText: second.plate_number })).toHaveCount(1);
});
