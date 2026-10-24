// Printing: the cash receipt (the driver found by plate, civil ID or name; the printed receipt shows them), the print
// templates designer (header, footer, watermark reflected in the live preview, published), and the report center
// (a report opened under a chosen company prints with its header, footer and watermark, on A4).
const { test, expect, uid, settled, clearToasts, jpeg } = require('./fixtures');

const civil = (n) => '2' + String(n).padStart(11, '0').slice(-11);

async function driverWithCar(api, n) {
  const c = await api.post('/companies', { name: { ar: 'شركة الطباعة ' + n, en: 'Printing company ' + n }, cr_number: 'CR' + n });
  const plate = n.slice(0, 2) + '/' + n.slice(2);
  const vehicle = await api.post('/vehicles', { plate_number: plate, company_id: c.id, last_odometer_km: 1000 });
  const driver = await api.post('/employees', {
    employee_number: 'PR' + n, name: { ar: 'سائق الإيصال ' + n, en: 'Receipt driver ' + n }, company_id: c.id, is_driver: true,
    civil_id: civil(n),
  });
  await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 1000, photo_sha256: await api.upload('h.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 3600e3).toISOString(),
  });
  return { company: c, vehicle, driver, plate };
}

const top = (page) => page.locator('.overlay[data-open]').last();
const noPrintWindow = (page) => page.evaluate(() => { window.__printed = 0; window.print = () => { window.__printed += 1; }; });

test('the receipt finds the driver by plate, civil ID or name, and prints them', async ({ admin, api }) => {
  const n = uid();
  const { driver, plate } = await driverWithCar(api, n);
  await admin.goto('/admin.html#/cash');
  await settled(admin);
  await noPrintWindow(admin);
  await admin.getByRole('button', { name: 'استلام كاش بإيصال' }).click();
  const dlg = top(admin);
  const hits = dlg.locator('[data-drv-id]');
  for (const q of [plate.replace('/', ' '), plate.replace('/', ''), civil(n), driver.name.ar, driver.name.en.toLowerCase()]) {
    await dlg.locator('[name=drv_q]').fill(q);
    await expect(dlg.locator('[data-drv-results]')).toHaveAttribute('data-q', q);
    await expect(hits).toHaveCount(1);
    await expect(hits).toContainText(driver.name.ar);
    await expect(hits).toContainText(plate);
    await expect(hits).toContainText(civil(n));
  }
  await hits.click();
  await expect(dlg.locator('[data-drv-picked]')).toContainText(plate);
  await dlg.locator('[name=amount]').fill('5');
  await clearToasts(admin);
  await dlg.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('إيصال رقم');
  const printed = admin.locator('#bt-print [data-receipt-print]');
  await expect(printed.locator('[data-r=name]')).toHaveText(driver.name.ar);
  await expect(printed.locator('[data-r=civil]')).toHaveText(civil(n));
  await expect(printed.locator('[data-r=plate]')).toHaveText(plate);
  await expect(admin.locator('#bt-print .pd-name')).toContainText('شركة الطباعة ' + n); // the driver's company on top
  await expect.poll(() => admin.evaluate(() => window.__printed)).toBe(1);
  const css = await admin.locator('#bt-print-page').textContent();
  expect(css).toContain('size: A4');
  expect(css).toContain('counter(pages)');
});

test('the designer: header, footer and watermark show in the preview, then print with them', async ({ admin, api }) => {
  const n = uid();
  const { company } = await driverWithCar(api, n);
  await admin.goto('/admin.html#/settings?tab=print');
  await admin.reload(); // the companies list is read when the panel starts: the new company in it
  await settled(admin);
  const panel = admin.locator('[data-p=print]');
  await expect(panel.locator('[data-pt-form]')).toBeVisible();
  const preview = panel.locator('[data-pt-preview] .pd');
  await panel.locator('[data-k="header.name_ar"]').fill('مجموعة التجربة ' + n);
  await expect(preview.locator('.pd-name')).toHaveText('مجموعة التجربة ' + n);
  await panel.locator('[data-k="footer.text"]').fill('ورقة {page} من {pages} — ' + n);
  await expect(preview.locator('.pd-foot-screen')).toContainText('ورقة 1 من 1 — ' + n);
  await panel.locator('[data-k="watermark.mode"]').selectOption('always');
  await panel.locator('[data-k="watermark.text"]').fill('سري ' + n);
  await expect(preview.locator('.pd-wm')).toHaveText('سري ' + n);
  const before = Number(await panel.locator('[data-pt-version]').textContent());
  await panel.locator('[data-pt-publish]').click();
  await expect(panel.locator('[data-pt-version]')).toHaveText(String(before + 1));
  const saved = await api.get('/print-templates');
  expect(saved.default.watermark.text).toBe('سري ' + n);

  // a company's own template: its accent, and it prints under its name
  await panel.locator('[data-pt-target]').selectOption(String(company.id));
  await panel.locator('[data-pt-own]').click();
  await panel.locator('[data-k="header.name_ar"]').fill('');
  await panel.locator('[data-k="header.lines"]').fill('سجل {cr_number}');
  await expect(preview.locator('.pd-lines')).toContainText('سجل CR' + n);
  await panel.locator('[data-pt-publish]').click();
  await expect(panel.locator('[data-pt-version]')).toHaveText(String(before + 2));
  expect((await api.get('/print-templates')).companies[company.id].header.lines).toEqual(['سجل {cr_number}']);

  // back to the previous setting: the company's template is gone again
  await panel.locator('[data-pt-rollback]').click();
  await top(admin).getByRole('button', { name: 'رجوع' }).click();
  await expect(panel.locator('[data-pt-version]')).toHaveText(String(before + 3));
  expect((await api.get('/print-templates')).companies[company.id]).toBeUndefined();
});

test('the report center opens a report under a chosen company and prints it on A4', async ({ admin, api }) => {
  const n = uid();
  const { company } = await driverWithCar(api, n);
  const m = await api.get('/print-templates');
  const t = m.default;
  await api.put('/print-templates/default', {
    config_version: m.config_version,
    template: Object.assign({}, t, { footer: Object.assign({}, t.footer, { text: 'صفحة {page} من {pages} · ' + n }), watermark: Object.assign({}, t.watermark, { mode: 'always', kind: 'text', text: 'نسخة ' + n }) }),
  });
  await admin.goto('/admin.html#/report-center');
  await admin.reload();
  await settled(admin);
  await noPrintWindow(admin);
  await admin.locator('[data-rc=km]').click();
  await admin.locator('[data-rc-company]').selectOption(String(company.id));
  const open = admin.locator('[data-rc-open=km]');
  await expect(open.locator('[data-range]')).toBeVisible();
  await expect(open.locator('.table-wrap, .empty').first()).toBeVisible();
  await open.locator('[data-preview]').click();
  const pv = top(admin).locator('[data-print-preview] .pd');
  await expect(pv.locator('.pd-name')).toHaveText('شركة الطباعة ' + n);
  await expect(pv.locator('.pd-foot-screen')).toContainText('صفحة 1 من 1 · ' + n);
  await expect(pv.locator('.pd-wm')).toHaveText('نسخة ' + n);
  await admin.keyboard.press('Escape');
  await open.locator('[data-print]').click();
  await expect.poll(() => admin.evaluate(() => window.__printed)).toBe(1);
  const sheet = admin.locator('#bt-print .pd');
  await expect(sheet).toHaveAttribute('data-company', String(company.id));
  await expect(sheet.locator('.pd-frame > thead .pd-name')).toHaveText('شركة الطباعة ' + n); // repeated on every page
  await expect(sheet.locator('.pd-wm')).toHaveText('نسخة ' + n);
  const css = await admin.locator('#bt-print-page').textContent();
  expect(css).toContain('size: A4');
  expect(css).toContain('· ' + n);
  // the printed page in the print media: A4, header and watermark there
  await admin.evaluate(() => document.body.classList.add('printing'));
  await admin.emulateMedia({ media: 'print' });
  await expect(admin.locator('#bt-print')).toBeVisible();
  await expect(admin.locator('#view')).toBeHidden();
  const pdf = await admin.pdf({ format: 'A4', preferCSSPageSize: true });
  expect(pdf.length).toBeGreaterThan(1000);
  await admin.emulateMedia({ media: 'screen' });
  await admin.evaluate(() => document.body.classList.remove('printing'));
});
