// The page that returns the system to new is not in the menu: its link opens it for the system administrator, who
// types their password and the phrase. A wrong password is refused and nothing is emptied. (The reset itself is
// checked in the API tests, inside a rolled-back transaction: here it would empty the database the other tests use.)
const { test, expect, settled } = require('./fixtures');

test('the reset page: hidden, the phrase and the password before anything is emptied', async ({ admin, api }) => {
  await admin.goto('/admin.html#/dashboard');
  await settled(admin);
  await expect(admin.locator('nav a[href="#/system-reset"], .nav a[href="#/system-reset"]')).toHaveCount(0); // not in the menu
  const before = (await api.get('/vehicles?limit=1')).length;
  await admin.goto('/admin.html#/system-reset');
  await settled(admin);
  const go = admin.locator('[data-reset-go]');
  await expect(go).toBeDisabled();
  await admin.locator('[data-reset-form] [name=password]').fill('not-my-password');
  await admin.locator('[data-reset-form] [name=confirm]').fill('امسح');
  await expect(go).toBeDisabled(); // the phrase exactly
  await admin.locator('[data-reset-form] [name=confirm]').fill('امسح كل البيانات');
  await expect(go).toBeEnabled();
  admin.allow(/factory-reset/); // the wrong password's 403 is expected
  await go.click();
  await admin.locator('.overlay[data-open]').last().getByRole('button', { name: 'امسح الآن' }).click();
  await expect(admin.locator('.toast').last()).toContainText(/كلمة المرور|بيانات الدخول/);
  expect((await api.get('/vehicles?limit=1')).length).toBe(before); // nothing emptied
});
