// The driver app's in-app updates: an APK is uploaded in Settings -> App updates (another app's package refused),
// published and marked required; the driver API (no session, as the sign-in screen asks) then offers it as a required
// update and serves the file.
const { test, expect, settled } = require('./fixtures');
const { apk } = require('./apk');

const PKG = 'com.example.e2e.driver';

test('an APK uploaded, published and marked required reaches the driver API', async ({ admin, api }) => {
  const s = (await api.get('/settings')).driver_app;
  await api.put('/settings/driver_app', { version: s.version, value: Object.assign({}, s.value, { android_package: PKG }) });
  const code = Math.floor(Date.now() / 1000) - 1700000000; // grows from run to run: above any earlier release
  const name = `0.${code}.0`;

  await admin.goto('/admin.html#/settings?tab=updates');
  await settled(admin);
  await expect(admin.locator('#view')).toContainText(PKG);

  admin.allow(/HTTP 422 POST \S+\/api\/v1\/app-releases$/); // another app's APK, refused
  await admin.locator('input[name=apk]').setInputFiles({ name: 'other.apk', mimeType: 'application/vnd.android.package-archive', buffer: apk('com.other.app', code, name) });
  await expect(admin.locator('.toast').last()).toContainText('com.other.app');

  await admin.locator('input[name=apk]').setInputFiles({ name: 'driver.apk', mimeType: 'application/vnd.android.package-archive', buffer: apk(PKG, code, name) });
  const row = admin.locator(`[data-releases] tr[data-release="${code}"]`);
  await expect(row).toContainText('مسودة');
  await expect(row).toContainText(name);

  await row.locator('[data-publish]').click();
  await admin.locator('.modal').getByRole('button', { name: 'نشر' }).click();
  await expect(row).toContainText('منشور');
  await row.locator('[data-required]').click();
  await admin.locator('.modal').getByRole('button', { name: 'تأكيد' }).click();
  // saved: the button now offers the opposite (its own label was «إلزامي», so the row's text alone proves nothing)
  await expect(row.locator('[data-required]')).toHaveText('اختياري');

  const res = await api.ctx.fetch(`/api/v1/driver/app-update?version_code=${code - 1}`, { headers: { Cookie: '' } });
  expect(res.ok()).toBeTruthy();
  const body = await res.json();
  expect(body.required).toBe(true);
  expect(body.latest.version_code).toBe(code);
  expect(body.latest.version_name).toBe(name);
  const file = await api.ctx.fetch(body.latest.url);
  expect(file.ok()).toBeTruthy();
  expect((await file.body()).length).toBe(body.latest.size);
  const upToDate = await (await api.ctx.fetch(`/api/v1/driver/app-update?version_code=${code}`)).json();
  expect(upToDate).toEqual({ latest: null, required: false });
});
