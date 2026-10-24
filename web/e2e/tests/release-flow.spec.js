// Release flow: the daily reports page exports the filtered list to Excel; «تحديث التطبيق» names the announced
// version and forces it (the driver API then says so); the «تنزيل التطبيق» page copies a public link on our own
// address that serves the APK as "<name>-<version>.apk".
const fs = require('fs');
const { test, expect, uid, phone, settled, clearToasts } = require('./fixtures');
const { apk } = require('./apk');
const { readXlsx } = require('./xlsx');

const PKG = 'com.example.e2e.driver';
const day = (back) => new Date(Date.now() + 3 * 3600e3 - back * 86400e3).toISOString().slice(0, 10); // Kuwait date

/** A new release above any earlier one (the code grows from run to run), uploaded as a draft: its version name. */
async function draft(api) {
  const s = (await api.get('/settings')).driver_app;
  if (s.value.android_package !== PKG) {
    await api.put('/settings/driver_app', { version: s.version, value: Object.assign({}, s.value, { android_package: PKG }) });
  }
  const code = Math.floor(Date.now() / 1000) - 1700000000;
  const name = `0.1.${code}`;
  const res = await api.ctx.fetch('/api/v1/app-releases', {
    method: 'POST', headers: { 'X-CSRF-Token': api.csrf },
    multipart: { file: { name: 'driver.apk', mimeType: 'application/vnd.android.package-archive', buffer: apk(PKG, code, name) } },
  });
  expect(res.status(), await res.text()).toBe(201);
  return { code, name };
}

/** «تحديث التطبيق» back to «the newest published release, optional», so other tests see the usual behaviour. */
async function reset(api) {
  const u = await api.get('/app-update');
  await api.put('/app-update', { version: u.version, value: Object.assign({}, u.value, { latest_version: '', force_update: false }) });
}

test('daily reports: the filtered list downloads as Excel', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة التصدير ' + n, en: 'Export company ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'X' + uid(), name: { ar: 'سائق التصدير ' + n, en: 'Export driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(),
  });
  const app = await api.driverPhone(driver.id, 'e2e-x' + n);
  await app.call('POST', '/driver/reports', { business_date: day(0), orders_count: 37, cash_amount: '21.250', screenshot_sha256: await app.photo() });

  await admin.goto('/admin.html#/daily?date=' + day(0));
  await settled(admin);
  await expect(admin.locator('#view [data-day]')).toHaveValue(day(0));
  await expect(admin.locator('#view tbody tr', { hasText: driver.name.ar })).toHaveCount(1);
  const [file] = await Promise.all([admin.waitForEvent('download'), admin.locator('#view [data-daily-export]').click()]);
  expect(file.suggestedFilename()).toBe(`daily-reports-${day(0)}-submitted.xlsx`);
  const sheet = readXlsx(fs.readFileSync(await file.path()));
  expect(sheet[0].slice(0, 5)).toEqual(['السائق', 'السيارة', 'يوم العمل', 'الفترة', 'عدد الطلبات']);
  const mine = sheet.filter((r) => r[0] === driver.name.ar);
  expect(mine.length).toBe(1);
  expect(String(mine[0][2])).toBe(day(0));
  expect(Number(mine[0][4])).toBe(37);
  expect(mine[0]).toContain(21.25); // the cash, a number (empty cells are not in the file, so no fixed position)
  expect(sheet.slice(1).every((r) => String(r[2]) === day(0))).toBe(true); // the day filter holds
});

test('«تحديث التطبيق»: the announced version saved and forced reaches the driver API', async ({ admin, api }) => {
  const { code, name } = await draft(api);
  try {
    await admin.goto('/admin.html#/settings?tab=updates');
    await settled(admin);
    const form = admin.locator('form[data-app-update]');
    await expect(form).toBeVisible();
    await expect(form.locator('[name=download_url_view]')).toHaveValue(/\/app\/download$/);
    await form.locator('[name=latest_version]').fill(name);
    await form.locator('label.switch', { hasText: 'تحديث إجباري' }).click();
    await form.locator('[name=notes]').fill('إصلاحات e2e');
    await clearToasts(admin);
    await form.locator('button[type=submit]').click();
    // saved: the panel draws again from the server's answer, which announces it as forced
    await expect(admin.locator('form[data-app-update] [data-announced]')).toContainText(name);
    await expect(admin.locator('form[data-app-update] [data-announced]')).toContainText('إجباري');
    await expect(admin.locator('form[data-app-update] [data-remote]')).toContainText(/Firebase غير مفعّل|Remote Config/);
    await expect(admin.locator(`[data-releases] tr[data-release="${code}"]`)).toContainText('منشور'); // saving published it

    const u = await api.get('/app-update');
    expect(u.value.latest_version).toBe(name);
    expect(u.value.force_update).toBe(true);
    const res = await api.ctx.fetch(`/api/v1/driver/app-update?version_code=${code - 1}`, { headers: { Cookie: '' } });
    const body = await res.json();
    expect(body.required).toBe(true);
    expect(body.latest.version_name).toBe(name);
  } finally {
    await reset(api);
  }
});

test('«تنزيل التطبيق»: the copied link is ours and serves the APK under its version name', async ({ admin, api }) => {
  const { code, name } = await draft(api);
  try {
    const u = await api.get('/app-update');
    await api.put('/app-update', { version: u.version, value: Object.assign({}, u.value, { latest_version: name, download_name: 'Fleet-Driver' }) });
    await admin.context().grantPermissions(['clipboard-read', 'clipboard-write']);
    await admin.goto('/admin.html#/app-download');
    await settled(admin);
    await expect(admin.locator('#view [data-version]')).toHaveText(name);
    await expect(admin.locator('#view [data-qr] svg')).toBeVisible();
    await expect(admin.locator('#view [data-download]')).toHaveAttribute('download', `Fleet-Driver-${name}.apk`);
    await clearToasts(admin);
    await admin.locator('#view [data-copy-link]').click();
    await expect(admin.locator('.toast').last()).toContainText('تم نسخ الرابط');
    const link = await admin.evaluate(() => navigator.clipboard.readText());
    expect(link).toMatch(/^https?:\/\/[^/]+\/app\/download$/);
    expect(link).not.toMatch(/github|firebase|googleapis/i);

    const file = await api.ctx.fetch(new URL(link).pathname); // the same path on the server under test
    expect(file.status()).toBe(200);
    expect(file.headers()['content-type']).toBe('application/vnd.android.package-archive');
    expect(file.headers()['content-disposition']).toContain(`Fleet-Driver-${name}.apk`);
    const bytes = await file.body();
    expect(bytes.subarray(0, 2).toString()).toBe('PK');
    const one = await api.ctx.fetch(`/app/download/${code}`);
    expect(one.status()).toBe(200);
    expect(one.headers()['content-disposition']).toContain(`Fleet-Driver-${name}.apk`);
  } finally {
    await reset(api);
  }
});
