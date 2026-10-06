// Traffic fines: the ticket's time names the driver who held the vehicle, read as Kuwait time whatever the office
// computer's clock is set to; the fine charged to him in installments and paid to the traffic department, one at a time
// nobody held the vehicle (alerted, borne by the company), one cancelled as a wrong entry; the vehicle's file and the
// drivers' apps show the same.
const { test, expect, uid, phone, settled, clearToasts, jpeg, pdf, kuwaitInput } = require('./fixtures');

// an office computer not set to Kuwait time: a ticket at 13:00 is 13:00 Kuwait time, not 13:00 of the computer's zone
test.use({ timezoneId: 'UTC' });

const same = (a, b) => expect(new Date(a).toISOString()).toBe(new Date(b).toISOString());

test('fines: the driver at the ticket time, charged, paid, nobody driving, cancelled', async ({ admin, api }) => {
  test.setTimeout(180_000);
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة المخالفات ' + n, en: 'Fines company ' + n } });
  const plate = '5/' + n.slice(-6);
  const vehicle = await api.post('/vehicles', { plate_number: plate, make: 'Nissan', model: 'Sunny', company_id: company.id, last_odometer_km: 30000 });
  const driver = (name) => api.post('/employees', {
    employee_number: 'F' + uid(), name: { ar: name + ' ' + n, en: 'Driver ' + n }, company_id: company.id, is_driver: true, phone: phone(),
  });
  const ali = await driver('علي');
  const omar = await driver('عمر');
  const odo = () => api.upload('odo.jpg', 'image/jpeg', jpeg());

  // two days ago, Kuwait time: Ali held the vehicle 08:00 to 14:00, nobody until 15:00, then Omar
  const day = kuwaitInput(Date.now() - 2 * 86400e3).slice(0, 10);
  const at = (hhmm) => `${day}T${hhmm}:00+03:00`;
  const c = await api.post('/custodies', { vehicle_id: vehicle.id, driver_id: ali.id, odometer_km: 30100, photo_sha256: await odo(), started_at: at('08:00') });
  await api.post(`/custodies/${c.id}/return`, { odometer_km: 30150, photo_sha256: await odo(), ended_at: at('14:00') });
  await api.post('/custodies', { vehicle_id: vehicle.id, driver_id: omar.id, odometer_km: 30160, photo_sha256: await odo(), started_at: at('15:00') });

  const top = () => admin.locator('.overlay[data-open]').last();
  const fines = async () => api.get('/fines?vehicle_id=' + vehicle.id);
  const button = (name) => top().getByRole('button', { name, exact: true });

  /** Registered from the fines page as the ticket reads; the fine's drawer opens on it. */
  async function register(hhmm, amount, violation, ref, file) {
    await admin.click('[data-action="fine-new"]');
    const m = top();
    const label = await m.locator('[name=vehicle]').evaluate((el, p) => [...el.list.options].map((o) => o.value).find((v) => v.includes(p)), plate);
    await m.locator('[name=vehicle]').fill(label);
    await m.locator('[name=at]').fill(`${day}T${hhmm}`);
    await m.locator('[name=amount]').fill(amount);
    await m.locator('[name=violation]').fill(violation);
    await m.locator('[name=ref]').fill(ref);
    if (file) await m.locator('[name=file]').setInputFiles(file);
    await clearToasts(admin); // the previous fine's toast says the same
    await m.locator('button[type=submit]').click();
    await expect(admin.locator('.toast').last()).toContainText('سُجّلت المخالفة');
    const f = (await fines()).find((x) => x.reference_no === ref);
    await expect(top()).toContainText('#' + f.number); // its drawer
    return f;
  }

  await admin.goto('/admin.html#/fines');
  await settled(admin);

  // ---- 13:00: Ali had it; charged to him in 3 installments from next month, then paid to the traffic department
  let f1 = await register('13:00', '15', 'تجاوز السرعة 120 في 80', 'TKT-' + n, { name: 'ticket.pdf', mimeType: 'application/pdf', buffer: pdf() });
  same(f1.occurred_at, at('13:00'));
  expect([f1.driver && f1.driver.id, f1.has_file, f1.status]).toEqual([ali.id, true, 'open']);
  await expect(admin.locator('.toast').last()).toContainText(ali.name.ar);
  await expect(top()).toContainText(day.split('-').reverse().join('-') + ' 13:00'); // shown in Kuwait time too
  await button('خصم من السائق').click();
  const ch = top();
  const [y, mo] = kuwaitInput(Date.now()).slice(0, 7).split('-').map(Number);
  const month = (k) => { const t = (mo - 1) + k; return `${y + Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`; };
  await expect(ch.locator('[name=start]')).toHaveValue(month(1));
  await ch.locator('[name=inst]').fill('3');
  await ch.locator('button[type=submit]').click();
  await expect(top()).toContainText('مخصومة من السائق'); // the drawer again, decided
  await expect(top().locator('tbody tr')).toHaveCount(3);
  await expect(button('إلغاء')).toHaveCount(0); // not while the driver's deduction stands
  f1 = (await fines()).find((x) => x.id === f1.id);
  expect(f1.deduction.schedule.map((x) => [x.month, x.amount])).toEqual([1, 2, 3].map((k) => [month(k) + '-01', '5.000']));
  await button('دُفعت للمرور').click();
  await top().locator('[name=ref]').fill('MOI-' + n);
  await top().locator('button[type=submit]').click();
  await expect(top()).toContainText('MOI-' + n);
  await expect(button('دُفعت للمرور')).toHaveCount(0);
  f1 = (await fines()).find((x) => x.id === f1.id);
  expect([f1.status, f1.payment_ref, f1.paid_at !== null]).toEqual(['charged', 'MOI-' + n, true]);
  await admin.keyboard.press('Escape');

  // ---- 14:30: nobody had it; alerted, cannot be charged, borne by the company
  const f2 = await register('14:30', '10', 'وقوف في مكان ممنوع', 'TKT2-' + n);
  same(f2.occurred_at, at('14:30'));
  expect(f2.driver).toBeNull();
  await expect(admin.locator('.toast').last()).toContainText('لم تكن السيارة مسلّمة لأحد');
  await expect(top()).toContainText('لا يمكن الخصم');
  await expect(button('خصم من السائق')).toHaveCount(0);
  const alerted = async () => (await api.get('/alerts?kind=fine_no_driver&limit=200')).some((x) => x.entity_id === f2.id);
  expect(await alerted()).toBe(true);
  await admin.keyboard.press('Escape');
  await admin.locator('#view .chip', { hasText: 'بلا سائق' }).click();
  await settled(admin);
  await admin.locator('#view tbody tr', { hasText: 'TKT2-' + n }).click();
  await button('على الشركة').click();
  await top().locator('[name=reason]').fill('السيارة كانت في الموقف ولم يقدها أحد');
  await button('على الشركة').click(); // the confirmation
  await expect(top()).toContainText('ولم يقدها أحد');
  expect((await fines()).find((x) => x.id === f2.id).status).toBe('company');
  expect(await alerted()).toBe(false);
  await admin.keyboard.press('Escape');

  // ---- 16:00: Omar had it; entered by mistake, cancelled; its ticket number can be entered again
  const f3 = await register('16:00', '20', 'إدخال خاطئ', 'TKT3-' + n);
  expect(f3.driver && f3.driver.id).toBe(omar.id);
  await button('إلغاء').click();
  await top().locator('[name=reason]').fill('رقم المخالفة لسيارة أخرى');
  await button('إلغاء المخالفة').click();
  await expect(top()).toContainText('رقم المخالفة لسيارة أخرى');
  await admin.keyboard.press('Escape');
  const again = await api.post('/fines', { vehicle_id: vehicle.id, occurred_at: at('16:00'), violation: 'تجاوز إشارة', amount: '20', reference_no: 'TKT3-' + n });
  expect(again.driver.id).toBe(omar.id);

  // ---- the vehicle's file lists them; each driver's app shows his own, not the cancelled one
  await admin.goto('/admin.html#/vehicles/' + vehicle.id);
  await settled(admin);
  await expect(admin.locator('#veh-fines [data-fine]')).toHaveCount(4);
  await expect(admin.locator(`#veh-fines [data-fine="${f2.id}"]`)).toContainText('بلا سائق');
  const mine = async (who) => (await (await api.driverPhone(who.id, 'e2e-' + n + '-' + who.employee_number)).call('GET', '/driver/fines'))
    .map((x) => [x.number, x.status, x.deduction && x.deduction.schedule.length]);
  expect(await mine(ali)).toEqual([[f1.number, 'charged', 3]]);
  expect(await mine(omar)).toEqual([[again.number, 'open', null]]);
});
