// Every page of the menu, and every tab in it, opens and loads with no page, console or API error; and at phone width
// no page scrolls sideways.
const { test, expect, settled } = require('./fixtures');

const PAGES = [
  'dashboard', 'tracking', 'alerts', 'vehicles', 'custody', 'odometer', 'daily', 'maintenance', 'accidents', 'fines',
  'cash', 'finance', 'deductions', 'payroll', 'employees', 'attendance', 'reports', 'import', 'settings', 'integrations', 'audit',
];

async function open(page, key) {
  await page.goto('/admin.html#/' + key);
  await page.waitForFunction((k) => window.BT.A.router && window.BT.A.router.current === k, key);
  await settled(page);
  await expect(page.locator('#tb-title h1')).not.toBeEmpty();
}

test('every page and every tab opens without an error', async ({ admin }) => {
  admin.allow(/\/maps\//); // the map extract is not in the repository (deploy/maps/update-map.sh on the server)
  const menu = await admin.locator('#nav .nav-item').evaluateAll((els) => els.map((a) => a.getAttribute('href').slice(2)));
  expect(menu.sort()).toEqual([...PAGES].sort()); // a page added to the menu is added here
  for (const key of PAGES) {
    await test.step(key, async () => {
      await open(admin, key);
      const tabs = admin.locator('#view [role=tab]');
      const n = await tabs.count();
      for (let i = 0; i < n; i++) {
        const tab = tabs.nth(i);
        if (!(await tab.isVisible())) continue;
        await tab.click();
        await settled(admin);
      }
    });
  }
});

test('at phone width no page scrolls sideways', async ({ admin }) => {
  admin.allow(/\/maps\//);
  await admin.setViewportSize({ width: 390, height: 844 });
  for (const key of PAGES) {
    await test.step(key, async () => {
      await open(admin, key);
      const overflow = await admin.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, key + ' is wider than the phone').toBeLessThanOrEqual(1);
    });
  }
});
