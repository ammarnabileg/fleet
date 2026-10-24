// From an alert straight to its decision (the bell, the alerts page): a driver's registration is reviewed and
// approved from its alert, and a fine with nobody driving is decided from the alerts page; each alert then closes.
const { test, expect, uid, phone, settled, clearToasts } = require('./fixtures');

const IBAN = 'KW81CBKU0000000000001234560101';

test('a registration is approved from the bell, straight from its alert', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة التسجيل ' + n, en: 'Registration company ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'OB' + n, name: { ar: 'سائق التسجيل ' + n, en: 'Registering ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  const ph = await api.driverPhone(driver.id, 'e2e-ob-' + n, { onboarding: true });
  const view = await ph.call('GET', '/driver/onboarding');
  const documents = [];
  for (const code of view.required_documents) {
    documents.push({ type_code: code, number: 'N-' + code, expiry_date: '2030-01-31', front_sha256: await ph.photo(), back_sha256: await ph.photo() });
  }
  await ph.call('PUT', '/driver/onboarding', {
    civil_id: '29' + n + '000', nationality: 'الهند', iban: IBAN, bank_name: 'NBK', documents, no_vehicle: true,
  });
  await ph.call('POST', '/driver/onboarding/submit');
  const top = () => admin.locator('.overlay[data-open]').last();

  await admin.goto('/admin.html'); // as after signing in: the dashboard is the default page, with no hash
  await admin.reload(); // the new company
  await settled(admin);
  const onDashboard = admin.locator('#view .li', { hasText: driver.name.ar });
  await expect(onDashboard).toHaveCount(1); // the dashboard's open alerts list it too
  await admin.click('[data-action="notifications"]');
  const row = admin.locator('.notif-menu .notif', { hasText: driver.name.ar });
  await expect(row).toContainText('أرسل بياناته ومستنداته للمراجعة');
  await row.locator('[data-action="alert-open"]').click(); // «مراجعة واعتماد»
  await expect(admin.locator('.notif-menu')).toHaveCount(0); // the bell's menu closed under the drawer
  const drawer = top();
  await expect(drawer).toContainText(driver.name.ar);
  await expect(drawer).toContainText('الهند');
  await drawer.locator('[data-x=approve]').click();
  await clearToasts(admin);
  await top().getByRole('button', { name: 'اعتماد', exact: true }).click();
  await expect(admin.locator('.toast').last()).toContainText('تم اعتماد التسجيل');
  await expect(onDashboard).toHaveCount(0); // the alert closed itself and the dashboard was redrawn
  const emp = await api.get('/employees/' + driver.id);
  expect([emp.civil_id, emp.nationality, emp.bank_name]).toEqual(['29' + n + '000', 'الهند', 'NBK']);
  const open = await api.get('/alerts?limit=200');
  expect(open.filter((a) => a.kind === 'onboarding_submitted' && a.params.driver === driver.name.ar)).toEqual([]); // closed itself
});

test('a fine with nobody driving is decided from the alerts page, and its alert leaves the list', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة المخالفة ' + n, en: 'Fine company ' + n } });
  const vehicle = await api.post('/vehicles', { plate_number: '7/' + n.slice(-6), company_id: company.id, last_odometer_km: 100 });
  const fine = await api.post('/fines', {
    vehicle_id: vehicle.id, occurred_at: new Date(Date.now() - 3600e3).toISOString(), violation: 'وقوف خاطئ ' + n, amount: '10', reference_no: 'AL-' + n,
  });
  const top = () => admin.locator('.overlay[data-open]').last();

  await admin.goto('/admin.html#/alerts');
  await admin.reload();
  await settled(admin);
  const row = admin.locator('#alerts-table tbody tr', { hasText: vehicle.plate_number });
  await row.locator('[data-action="alert-open"]').click(); // «فتح»
  await expect(top()).toContainText('#' + fine.number);
  await top().getByRole('button', { name: 'على الشركة', exact: true }).click();
  await top().locator('[name=reason]').fill('لم يكن أحد يقود');
  await clearToasts(admin);
  await top().getByRole('button', { name: 'على الشركة', exact: true }).click();
  await expect(admin.locator('.toast').last()).toContainText('سُجّل القرار');
  await admin.keyboard.press('Escape');
  await expect(admin.locator('#alerts-table tbody tr', { hasText: vehicle.plate_number })).toHaveCount(0); // closed, and the list redrawn
});
