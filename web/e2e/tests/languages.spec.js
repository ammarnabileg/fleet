// Languages and translations of the driver app: a French string is edited in the panel (a broken message is refused
// on the form), marked reviewed and published; the driver API then names a new version whose bundle carries it. The
// translation sheet goes out and comes back (Excel), and a language is turned off and on again.
const { test, expect, settled, clearToasts, uid } = require('./fixtures');
const { xlsx, readXlsx } = require('./xlsx');

async function driverGet(api, path) {
  const res = await api.ctx.fetch('/api/v1' + path);
  expect(res.ok()).toBeTruthy();
  return res;
}

async function openLanguage(admin, code, q) {
  await admin.goto('/admin.html#/settings?tab=languages');
  await settled(admin);
  await admin.locator(`[data-pick-lang="${code}"]`).click();
  await settled(admin);
  if (q) {
    await admin.fill('#view [data-f="q"]', q);
    await admin.press('#view [data-f="q"]', 'Enter');
    await settled(admin);
  }
}

test('a French string edited, reviewed and published reaches the driver API in a new version', async ({ admin, api }) => {
  const before = (await (await driverGet(api, '/driver/translations/manifest')).json()).languages.find((l) => l.code === 'fr');
  await openLanguage(admin, 'fr', 'otpResend');
  const row = admin.locator('#view tbody tr', { hasText: 'otpResend' });
  await expect(row).toContainText('No code? Send again');
  const text = `Toujours pas de code ? Renvoyer ${uid()}`;
  await row.click();

  const modal = admin.locator('.modal');
  admin.allow(/HTTP 422 PUT \S+\/api\/v1\/i18n\/translations\/fr$/); // the broken message, refused
  await modal.locator('[name=text]').fill('Pas de code {phone ? Renvoyer');
  await modal.getByRole('button', { name: 'حفظ' }).click();
  await expect(modal.locator('[data-err]')).toBeVisible();
  await expect(modal.locator('[data-err]')).toContainText('otpResend');

  await clearToasts(admin);
  await modal.locator('[name=text]').fill(text);
  await modal.locator('[name=reviewed]').check();
  await modal.getByRole('button', { name: 'حفظ' }).click();
  await expect(admin.locator('.toast')).toContainText('مسودة');
  await settled(admin);
  await admin.fill('#view [data-f="q"]', 'otpResend');
  await admin.press('#view [data-f="q"]', 'Enter');
  const saved = admin.locator('#view tbody tr', { hasText: 'otpResend' });
  await expect(saved).toContainText(text);
  await expect(saved.locator('[data-status]')).toContainText('تمت المراجعة');

  // a draft: the drivers still have the published version
  const draft = (await (await driverGet(api, '/driver/translations/manifest')).json()).languages.find((l) => l.code === 'fr');
  expect(draft.version).toBe(before.version);

  await clearToasts(admin);
  await admin.locator('[data-publish="fr"]').click();
  await expect(admin.locator('.toast')).toContainText('نُشر الإصدار');
  await expect(admin.locator('[data-published="fr"]')).toHaveText(String(before.version + 1));

  const fr = (await (await driverGet(api, '/driver/translations/manifest')).json()).languages.find((l) => l.code === 'fr');
  expect(fr.version).toBe(before.version + 1);
  const bundle = await (await driverGet(api, `/driver/translations/bundle/fr/${fr.version}`)).json();
  expect(bundle.strings.otpResend).toBe(text);
  const again = await (await driverGet(api, `/driver/translations?lang=fr&version=${fr.version}`)).json();
  expect(again.unchanged).toBe(true);
});

test('the translation sheet out and back in, and a language off and on', async ({ admin, api }) => {
  await openLanguage(admin, 'sw');
  const [download] = await Promise.all([admin.waitForEvent('download'), admin.locator('[data-export]').click()]);
  const rows = readXlsx(require('fs').readFileSync(await download.path()));
  expect(rows[0]).toEqual(['scope', 'key', 'en', 'translation', 'status']);
  const cancel = rows.find((r) => r[0] === 'app' && r[1] === 'cancel');
  expect(cancel[2]).toBe('Cancel');
  expect(cancel[3]).toBeTruthy();

  const word = `Sitisha${uid()}`;
  const back = [rows[0], ['app', 'cancel', 'Cancel', word, 'needs_review']];
  await admin.locator('[data-import]').setInputFiles({
    name: 'sw.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: xlsx({ Sheet1: back }),
  });
  await expect(admin.locator('.toast')).toContainText('استُورد 1');
  await settled(admin);
  await admin.fill('#view [data-f="q"]', word);
  await admin.press('#view [data-f="q"]', 'Enter');
  await expect(admin.locator('#view tbody tr', { hasText: word })).toHaveCount(1);
  await expect(admin.locator('[data-unpublished="sw"]')).not.toHaveText('—');

  // a broken message in the sheet: nothing saved
  admin.allow(/HTTP 422 POST \S+\/api\/v1\/i18n\/translations\/sw\/import$/);
  await clearToasts(admin);
  await admin.locator('[data-import]').setInputFiles({
    name: 'bad.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: xlsx({ Sheet1: [rows[0], ['app', 'greeting', 'Hello, {name}', 'Habari {name', '']] }),
  });
  await expect(admin.locator('.toast')).toContainText('greeting');

  // off: gone from the app's list; on again
  await admin.locator('[data-toggle-lang="sw"]').click();
  await expect(admin.locator('[data-lang-row="sw"]')).toContainText('موقوفة');
  let langs = await (await driverGet(api, '/driver/languages')).json();
  expect(langs.map((l) => l.code)).not.toContain('sw');
  await admin.locator('[data-toggle-lang="sw"]').click();
  await expect(admin.locator('[data-lang-row="sw"]')).toContainText('مفعّلة');
  langs = await (await driverGet(api, '/driver/languages')).json();
  expect(langs.map((l) => l.code)).toContain('sw');
  await expect(admin.locator('[data-toggle-lang="ar"]')).toHaveCount(0); // Arabic and English stay on
});
