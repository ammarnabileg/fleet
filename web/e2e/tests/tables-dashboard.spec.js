// The shared table: sorted from the keyboard, columns chosen and kept, a view saved by name, and «back» returning to
// the same search, filter and page; a dashboard figure opens the very records it counts.
const { test, expect, uid, phone, settled, jpeg } = require('./fixtures');

test('a dashboard figure lists what it counts, sorted from the keyboard', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الأرقام ' + n, en: 'Drill company ' + n } });
  const idle = await api.post('/employees', { employee_number: 'I' + uid(), name: { ar: 'سائق بلا سيارة ' + n, en: 'Idle ' + n }, company_id: company.id, is_driver: true, phone: phone() });
  const vehicle = await api.post('/vehicles', { plate_number: '4/' + n.slice(-6), company_id: company.id, last_odometer_km: 100 });
  const driving = await api.post('/employees', { employee_number: 'D' + uid(), name: { ar: 'سائق صامت ' + n, en: 'Silent ' + n }, company_id: company.id, is_driver: true, phone: phone() });
  await api.post('/custodies', { vehicle_id: vehicle.id, driver_id: driving.id, odometer_km: 100, photo_sha256: await api.upload('o.jpg', 'image/jpeg', jpeg()), started_at: new Date(Date.now() - 3 * 3600e3).toISOString() });
  const d = await api.get('/dashboard');

  await admin.goto('/admin.html#/dashboard');
  await admin.reload(); // the new company
  await settled(admin);
  // signal lost: one of the exceptions, opening the custodies it counts
  await admin.locator('[data-exceptions] [data-arg=signal_lost]').click();
  let drawer = admin.locator('.overlay[data-open]').last();
  await expect(drawer.locator('tbody tr', { hasText: vehicle.plate_number })).toHaveCount(1);
  // the same count as the figure (asked again now: on a shared database other cars go silent as time passes)
  const lost = (await api.get('/dashboard')).drivers.signal_lost;
  await expect(drawer.locator('[data-drill=signal_lost]')).toContainText(lost + ' سجل');
  await expect(drawer.locator('tbody tr', { hasText: vehicle.plate_number })).toContainText('لا موقع منذ التسليم');
  await admin.keyboard.press('Escape');

  await admin.locator('details[data-group=fleet] > summary').click();
  await admin.locator('[data-drivers] [data-arg=without_vehicle]').click();
  drawer = admin.locator('.overlay[data-open]').last();
  await expect(drawer.locator('[data-drill=without_vehicle]')).toContainText(d.drivers.without_vehicle + ' سجل');
  const rows = drawer.locator('tbody tr');
  await expect(rows).toHaveCount(Math.min(d.drivers.without_vehicle, 25));
  // the sort is a button: reached and pressed from the keyboard, the header says the order
  const sortBtn = drawer.locator('th [data-sort=driver]');
  await sortBtn.focus();
  await admin.keyboard.press('Enter');
  await expect(drawer.locator('th[aria-sort=ascending]')).toContainText('السائق');
  await expect(drawer.locator('th [data-sort=driver]')).toBeFocused();
  await admin.keyboard.press('Enter');
  await expect(drawer.locator('th[aria-sort=descending]')).toContainText('السائق');
  // «فتح» on the row opens the driver
  await drawer.locator('tbody tr', { hasText: idle.name.ar }).locator('[data-row-open]').click();
  await expect(admin.locator('.overlay[data-open]').last()).toContainText(idle.name.ar);
});

test('columns chosen and a view saved; back returns to the same search, chip and page', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الجدول ' + n, en: 'Table company ' + n } });
  const cars = [];
  for (let i = 0; i < 3; i++) cars.push(await api.post('/vehicles', { plate_number: (30 + i) + '/' + n.slice(-5), company_id: company.id, make: 'Make' + n }));

  await admin.goto('/admin.html#/vehicles');
  await settled(admin);
  const table = admin.locator('#veh-table');
  await table.locator('[data-chip=available]').click();
  await table.locator('input[type=search]').fill('Make' + n);
  await expect(table.locator('[aria-busy]')).toHaveCount(0);
  await expect(table.locator('tbody tr')).toHaveCount(3);

  // hide a column; it stays hidden after a reload (this browser)
  await table.locator('[data-t-view]').click();
  const pop = admin.locator('.t-views');
  await pop.locator('[data-col=km]').uncheck();
  await expect(table.locator('thead th', { hasText: 'العداد' })).toHaveCount(0);
  await pop.locator('[name=name]').fill('متاحة ' + n);
  await pop.getByRole('button', { name: 'حفظ' }).click();
  await expect(admin.locator('.t-views')).toHaveCount(0);

  // to a vehicle and back: the same chip and search
  await table.locator('tbody tr', { hasText: cars[0].plate_number }).locator('[data-row-open]').click();
  await expect(admin).toHaveURL(new RegExp('#/vehicles/' + cars[0].id));
  await settled(admin);
  await admin.goBack();
  await settled(admin);
  await expect(table.locator('input[type=search]')).toHaveValue('Make' + n);
  await expect(table.locator('[data-chip=available]')).toHaveClass(/active/);
  await expect(table.locator('[aria-busy]')).toHaveCount(0);
  await expect(table.locator('tbody tr')).toHaveCount(3);

  // a fresh visit starts clean; the saved view brings it all back
  await admin.goto('/admin.html#/custody');
  await settled(admin);
  await admin.goto('/admin.html#/vehicles');
  await settled(admin);
  await expect(table.locator('input[type=search]')).toHaveValue('');
  await expect(table.locator('thead th', { hasText: 'العداد' })).toHaveCount(0); // the columns are kept
  await table.locator('[data-t-view]').click();
  await admin.locator('.t-views [data-view-apply]', { hasText: 'متاحة ' + n }).click();
  await expect(table.locator('input[type=search]')).toHaveValue('Make' + n);
  await expect(table.locator('[aria-busy]')).toHaveCount(0);
  await expect(table.locator('tbody tr')).toHaveCount(3);
  await table.locator('[data-t-view]').click();
  await admin.locator('.t-views [data-col=km]').check(); // back as it was, for the other tests
  await expect(table.locator('thead th', { hasText: 'العداد' })).toHaveCount(1);
});
