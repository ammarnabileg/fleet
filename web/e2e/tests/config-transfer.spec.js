// Moving the configuration (Integrations -> «نقل الإعدادات (JSON)»): the export downloads a JSON file with the
// sections chosen; importing it back previews what would change (nothing saved), then applies it and a setting
// changed meanwhile comes back to the file's value.
const fs = require('fs');
const { test, expect, settled, uid } = require('./fixtures');

async function setTracking(api, seconds) {
  const s = (await api.get('/settings')).tracking;
  await api.put('/settings/tracking', { version: s.version, value: Object.assign({}, s.value, { interval_moving_s: seconds }) });
}

test('export the chosen sections, preview the import, import: a changed setting comes back', async ({ admin, api }) => {
  const code = 'st_' + uid().toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 12);
  await api.post('/employment-statuses', { code, name: { ar: 'حالة ' + code, en: 'Status ' + code } });
  await setTracking(api, 47);

  await admin.goto('/admin.html#/integrations');
  await settled(admin);
  const card = admin.locator('[data-transfer]');
  await expect(card).toContainText('نقل الإعدادات (JSON)');
  // only the settings and the employment statuses
  await card.locator('input[name=all]').uncheck();
  await card.locator('[data-section="settings"]').check();
  await card.locator('[data-section="employment_statuses"]').check();
  const download = admin.waitForEvent('download');
  await card.locator('[data-export]').click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^fleet-config-.*\.json$/);
  const doc = JSON.parse(fs.readFileSync(await file.path(), 'utf8'));
  expect(doc.format).toBe('fleet-config');
  expect(Object.keys(doc.sections).sort()).toEqual(['employment_statuses', 'settings']);
  expect(doc.sections.settings.tracking.interval_moving_s).toBe(47);
  expect(doc.sections.employment_statuses.map((s) => s.code)).toContain(code);
  expect(doc.secrets).toBeNull();

  // changed after the export: the import brings it back
  await setTracking(api, 120);
  await card.locator('[data-import-file]').setInputFiles({ name: 'config.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(doc)) });
  await card.locator('[data-preview]').click();
  const preview = card.locator('[data-report="preview"]');
  await expect(preview.locator('tr[data-row="settings"] [data-updated]')).toHaveText('1');
  await expect(preview.locator('tr[data-row="employment_statuses"] [data-created]')).toHaveText('0');
  expect((await api.get('/settings')).tracking.value.interval_moving_s).toBe(120); // the preview saved nothing

  await card.locator('[data-import]').click();
  await admin.locator('.modal').getByRole('button', { name: 'استيراد' }).click();
  await expect(card.locator('[data-result]')).toContainText('تم الاستيراد');
  await expect(card.locator('[data-report="done"] tr[data-row="settings"] [data-updated]')).toHaveText('1');
  await expect.poll(async () => (await api.get('/settings')).tracking.value.interval_moving_s).toBe(47);
  await expect(card.locator('[data-import]')).toBeDisabled();
});
