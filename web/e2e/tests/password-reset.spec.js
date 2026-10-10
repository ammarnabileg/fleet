// An office user who forgot the password, from the sign-in page (BRD FR-USR-03): the code arrives on WhatsApp to the
// phone saved on the account, a wrong code is refused, the right one sets the new password, and the old one no longer
// opens the account. The development server keeps the messages it would send (its log provider), as a phone would.
const { test, expect, uid } = require('./fixtures');

test('a forgotten password replaced with a code sent to the phone', async ({ browser, api, baseURL }) => {
  const n = uid();
  const username = 'forgot' + n;
  const phone = '+9656' + n.slice(-7).padStart(7, '0');
  const role = await api.post('/roles', { code: 'r' + n, name: { ar: 'دور ' + n, en: 'Role ' + n }, permissions: ['vehicles.view'] });
  await api.post('/users', { username, full_name: 'ناسي ' + n, password: 'first-password-' + n, role_codes: [role.code], all_companies: true, phone });

  const ctx = await browser.newContext({ baseURL, locale: 'ar' });
  const page = await ctx.newPage();
  await page.goto('/login.html');
  await page.locator('#u').fill(username);
  await page.locator('#forgot').click();
  const dlg = page.locator('.overlay[data-open]').last();
  await expect(dlg.locator('[name=username]')).toHaveValue(username); // carried from the sign-in form
  await dlg.locator('.btn-primary').click();
  await expect(dlg.locator('[data-reset-sent]')).toContainText(username);

  const messages = await (await page.request.get('/__dev/messages?to=' + encodeURIComponent(phone))).json();
  const code = messages.at(-1).text.match(/\b(\d{6})\b/)[1];
  await dlg.locator('[name=code]').fill(code === '000000' ? '111111' : '000000');
  await dlg.locator('[name=new_password]').fill('second-password-' + n);
  await dlg.locator('.btn-primary').click();
  await expect(dlg.locator('[data-reset-err]')).toContainText('غير صحيح');
  await dlg.locator('[name=code]').fill(code);
  await dlg.locator('.btn-primary').click();
  await expect(page.locator('.toast').last()).toContainText('تم تغيير كلمة المرور');
  await expect(page.locator('#u')).toHaveValue(username);

  await page.locator('#p').fill('first-password-' + n);
  await page.locator('#step1 [type=submit]').click();
  await expect(page.locator('#login-err')).toBeVisible(); // the old password is gone
  await page.locator('#p').fill('second-password-' + n);
  await page.locator('#step1 [type=submit]').click();
  await expect(page).toHaveURL(/admin\.html/);
  await ctx.close();
});
