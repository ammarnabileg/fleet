// An accident from the report to the deduction: the office reports it with photos, the liability is refused before the
// police report, the center estimates in its portal (seeing the damage, not the other party), the manager approves the
// estimate, the police report, the driver held liable in 3 installments, the repair; the deductions page and the
// driver's app show the same schedule.
const { test, expect, uid, phone, settled, clearToasts, jpeg, pdf, centerWithUser, centerSignIn, kuwaitInput } = require('./fixtures');

// an office computer not set to Kuwait time: the accident time typed is still Kuwait's
test.use({ timezoneId: 'UTC' });

const file = (name, mimeType, buffer) => ({ name, mimeType, buffer });

test('an accident: report, estimate, police report, liability in installments, repair', async ({ admin, api, portal }) => {
  test.setTimeout(180_000);
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الحوادث ' + n, en: 'Accidents company ' + n } });
  const plate = '3/' + n.slice(-6);
  const vehicle = await api.post('/vehicles', { plate_number: plate, make: 'Kia', model: 'Pegas', company_id: company.id, last_odometer_km: 30000 });
  const driver = await api.post('/employees', {
    employee_number: 'X' + n, name: { ar: 'سائق الحادث ' + n, en: 'Accident driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(),
  });
  await api.post('/custodies', {
    vehicle_id: vehicle.id, driver_id: driver.id, odometer_km: 30100, photo_sha256: await api.upload('odo.jpg', 'image/jpeg', jpeg()),
    started_at: new Date(Date.now() - 2 * 86400e3).toISOString(),
  });
  const when = kuwaitInput(Date.now() - 86400e3); // yesterday, as the office types it
  const { center, username } = await centerWithUser(api, n);
  const top = (page) => page.locator('.overlay[data-open]').last();
  const detail = (id) => api.get('/accidents/' + id);

  // ---- the office reports it, with three photos and the other party
  await admin.goto('/admin.html#/accidents');
  await settled(admin);
  await admin.click('[data-action="acc-new"]');
  const m = top(admin);
  const label = await m.locator('[name=vehicle]').evaluate((el, p) => [...el.list.options].map((o) => o.value).find((v) => v.includes(p)), plate);
  await m.locator('[name=vehicle]').fill(label);
  await m.locator('[name=at]').fill(when);
  await m.locator('[name=place]').fill('الدائري الرابع قرب مخرج السالمية');
  await m.locator('[name=desc]').fill('صدمته سيارة من الخلف عند الإشارة');
  await m.locator('[name=other]').fill('بيك أب أبيض، لوحة 12345، تأمين الخليج');
  await m.locator('[name=ph]').setInputFiles(['back', 'left', 'right'].map((x) => file(x + '.jpg', 'image/jpeg', jpeg())));
  await m.locator('button[type=submit]').click();
  await admin.waitForURL(/#\/accidents\/[0-9a-f-]{36}/);
  const id = admin.url().split('#/accidents/')[1];
  let a = await detail(id);
  expect([a.driver && a.driver.id, a.has_police_report, a.liability]).toEqual([driver.id, false, null]); // the driver who held it
  expect(new Date(a.occurred_at).toISOString()).toBe(new Date(when + ':00+03:00').toISOString()); // Kuwait time

  // ---- no liability without the police report: refused in the screen, nothing sent
  await settled(admin);
  await clearToasts(admin);
  await admin.click('[data-action="acc-outcome"]');
  await expect(admin.locator('.toast').last()).toContainText('محضر الشرطة');
  await expect(admin.locator('.overlay[data-open]')).toHaveCount(0);

  // ---- referred to the center, which estimates in its portal
  await admin.click('[data-action="acc-refer"]');
  await top(admin).locator('[name=center]').selectOption(center.id);
  await top(admin).locator('button[type=submit]').click();
  await expect(top(admin)).toBeHidden();
  await centerSignIn(portal, username);
  await portal.goto('/center.html#/a/' + id);
  await settled(portal);
  await expect(portal.locator('#view')).not.toContainText('بيك أب'); // the center sees the damage, not the other party
  await expect(portal.locator('#view')).not.toContainText(driver.name.ar);
  await portal.click('[data-est]');
  const e = top(portal);
  await e.locator('[data-k=d]').fill('صدام خلفي');
  await e.locator('[data-k=p]').fill('110');
  await e.locator('[data-items-add]').click();
  await e.locator('[data-k=kind]').nth(1).selectOption('labour');
  await e.locator('[data-k=d]').nth(1).fill('صبغ وتركيب');
  await e.locator('[data-k=p]').nth(1).fill('40');
  await expect(e.locator('[data-items-total]')).toContainText('150.000');
  await e.locator('[name=ph]').setInputFiles(file('estimate.jpg', 'image/jpeg', jpeg()));
  await e.locator('button[type=submit]').click();
  await expect(e).toBeHidden();
  await expect.poll(async () => (await detail(id)).estimate_status).toBe('pending'); // waiting for the manager

  // ---- the manager approves the estimate; the police report; the driver liable in 3 installments
  await admin.reload();
  await settled(admin);
  await admin.click('[data-est-ok]');
  await top(admin).locator('.btn-primary').last().click();
  await expect.poll(async () => (await detail(id)).estimate_status).toBe('approved');
  await admin.click('[data-action="acc-police"]');
  await top(admin).locator('[name=file]').setInputFiles(file('police.pdf', 'application/pdf', pdf()));
  await top(admin).locator('[name=no]').fill('4471/2026');
  await top(admin).locator('button[type=submit]').click();
  await expect.poll(async () => (await detail(id)).has_police_report).toBe(true);
  await settled(admin);
  await admin.click('[data-action="acc-outcome"]');
  const o = top(admin);
  await o.locator('[name=inst]').fill('3');
  await expect(o.locator('[data-preview]')).toContainText('150.000');
  await o.locator('button[type=submit]').click();
  await expect(o).toBeHidden();
  a = await detail(id);
  expect([a.liability, a.deduction_total, a.deduction.installments, a.police_report_no]).toEqual(['driver', '150.000', 3, '4471/2026']);
  // from next month (Kuwait time), one installment a month
  const [y, mo] = new Date(Date.now() + 3 * 3600e3).toISOString().slice(0, 7).split('-').map(Number);
  const month = (k) => { const t = (mo - 1) + k; return `${y + Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}-01`; };
  expect(a.deduction.schedule.map((x) => [x.month, x.amount])).toEqual([[month(1), '50.000'], [month(2), '50.000'], [month(3), '50.000']]);

  // ---- the repair is ordered; the deductions page and the driver's app show the schedule
  await admin.click('[data-action="acc-repair"]');
  await top(admin).locator('.btn-primary').last().click();
  await expect(top(admin)).toBeHidden();
  await admin.goto('/admin.html#/deductions');
  await settled(admin);
  await admin.locator('#view .chip', { hasText: 'كل المعتمدة' }).click();
  await settled(admin);
  await admin.locator('#view tbody tr', { hasText: driver.name.ar }).click();
  await expect(top(admin).locator('tbody tr')).toHaveCount(3);
  const app = await api.driverPhone(driver.id, 'e2e-' + n);
  const mine = (await app.call('GET', '/driver/accidents')).find((x) => x.id === id);
  expect([mine.liability, mine.deduction.total, mine.deduction.schedule.length]).toEqual(['driver', '150.000', 3]);
});
