// Absence requests (طلب التغيب): a driver asks for sick leave from the app with his medical certificate, the office
// sees the computed pay split and approves it, and he sees the decision; a leave type's default edited in the panel;
// the follow-up alert of an old request opens the request, which the office marks followed up.
const { test, expect, uid, phone, settled, clearToasts } = require('./fixtures');

const day = (back) => new Date(Date.now() + 3 * 3600e3 - back * 86400e3).toISOString().slice(0, 10); // Kuwait date

async function driverWithPhone(api, n, years) {
  const company = await api.post('/companies', { name: { ar: 'شركة التغيب ' + n, en: 'Absence co ' + n } });
  const driver = await api.post('/employees', {
    employee_number: 'LV' + n, name: { ar: 'سائق التغيب ' + n, en: 'Absence driver ' + n },
    company_id: company.id, is_driver: true, phone: phone(), hire_date: day(Math.round(years * 365.25)),
  });
  return { driver, app: await api.driverPhone(driver.id, 'e2e-leave-' + n) };
}

test('sick leave requested from the app, its pay split shown and approved in the panel', async ({ admin, api }) => {
  const n = uid();
  const { driver, app } = await driverWithPhone(api, n, 3);
  const view = await app.call('GET', '/driver/leaves');
  expect(view.types.map((t) => t.code)).toContain('sick');
  const pre = await app.call('POST', '/driver/leaves/preview', { kind: 'sick', date_from: day(-1), date_to: day(-20) });
  expect(pre.split).toEqual([{ days: 15, pay_percent: 100 }, { days: 5, pay_percent: 75 }]);
  const leave = await app.call('POST', '/driver/leaves', {
    client_ref: require('crypto').randomUUID(), kind: 'sick', date_from: day(-1), date_to: day(-20),
    reason: 'التهاب ' + n, file_sha256: await app.photo('upload'),
  });
  expect(leave.status).toBe('pending');
  const top = () => admin.locator('.overlay[data-open]').last();

  await admin.goto('/admin.html#/attendance?tab=leaves&leave=' + leave.id);
  await settled(admin);
  const drawer = top();
  await expect(drawer).toContainText(driver.name.ar);
  await expect(drawer.locator('[data-split]')).toContainText('15 يوم مدفوعة');
  await expect(drawer.locator('[data-split]')).toContainText('بـ 75%');
  await expect(drawer).toContainText('طلب من التطبيق');
  await expect(drawer.locator('[data-balance=sick]')).toHaveCount(1);
  await expect(drawer.getByRole('link', { name: /فتح/ })).toHaveCount(1); // the certificate
  await clearToasts(admin);
  await drawer.getByRole('button', { name: 'اعتماد', exact: true }).click();
  await top().getByRole('button', { name: 'اعتماد', exact: true }).click();
  await expect(admin.locator('.toast').last()).toContainText('اعتُمد الطلب');
  await expect(top()).toContainText('معتمدة');
  const mine = await app.call('GET', '/driver/leaves');
  expect(mine.requests.map((r) => [r.id, r.status])).toEqual([[leave.id, 'approved']]);
  const notices = await app.call('GET', '/driver/notifications');
  expect(notices.items[0].kind).toBe('leave_approved');
});

test('a leave type default edited in the panel', async ({ admin, api }) => {
  const top = () => admin.locator('.overlay[data-open]').last();
  await admin.goto('/admin.html#/attendance?tab=types');
  await settled(admin);
  await expect(admin.locator('#view [data-legal]')).toContainText('قيم افتراضية حسب قانون العمل');
  const row = admin.locator('#view [data-types] tr[data-type=bereavement]');
  await expect(row).toContainText('Art. 76');
  await row.locator('[data-type-edit]').click();
  const m = top();
  await m.locator('[name=max_per_occurrence]').fill('4');
  await m.locator('[name=tiers]').fill('4:100');
  await m.locator('button[type=submit]').click();
  await expect(m).toBeHidden();
  await expect(row).toContainText('للمرة 4');
  const t = (await api.get('/leave-types')).find((x) => x.code === 'bereavement');
  expect([t.max_per_occurrence, t.tiers]).toEqual([4, [{ days: 4, pay_percent: 100 }]]);
  await api.put('/leave-types/bereavement', { version: t.version, max_per_occurrence: 3, tiers: [{ days: 3, pay_percent: 100 }] });
});

test('the follow-up alert opens the request, which is marked followed up', async ({ admin, api }) => {
  const n = uid();
  const top = () => admin.locator('.overlay[data-open]').last();
  // ---- the setting, from the settings page
  await admin.goto('/admin.html#/settings?tab=system');
  await settled(admin);
  const form = admin.locator('#view form[data-sec=leaves]');
  await form.locator('[name=absence_followup_days]').fill('10');
  await clearToasts(admin);
  await form.locator('button[type=submit]').click();
  await expect(admin.locator('.toast').last()).toContainText('تم حفظ');
  try {
    const { driver, app } = await driverWithPhone(api, n, 2);
    // the follow-up counted from twelve days ago: past the ten days, the alert is raised
    const leave = await app.call('POST', '/driver/leaves', {
      client_ref: require('crypto').randomUUID(), kind: 'unpaid', date_from: day(-30), date_to: day(-31), followup_from: day(12),
    });
    expect(leave.followup_from).toBe(day(12));
    const alerts = await api.get('/alerts?limit=200');
    expect(alerts.filter((a) => a.kind === 'absence_followup' && a.entity_id === leave.id)).toHaveLength(1);

    await admin.goto('/admin.html#/alerts');
    await admin.reload();
    await settled(admin);
    const row = admin.locator('#alerts-table tbody tr', { hasText: driver.name.ar }).filter({ hasText: 'متابعة طلب تغيب' });
    await expect(row).toHaveCount(1);
    await row.locator('[data-action="alert-open"]').click(); // «فتح الطلب»
    const drawer = top();
    await expect(drawer).toContainText(driver.name.ar);
    await expect(drawer.locator('[data-followup-from]')).toHaveCount(1);
    await drawer.getByRole('button', { name: 'تمت المتابعة' }).click();
    await clearToasts(admin);
    await top().getByRole('button', { name: 'تمت المتابعة' }).click();
    await expect(admin.locator('.toast').last()).toContainText('سُجّلت المتابعة');
    const open = await api.get('/alerts?limit=200');
    expect(open.filter((a) => a.kind === 'absence_followup' && a.entity_id === leave.id)).toEqual([]);
    expect((await api.get('/leaves/' + leave.id)).followed_up_at).not.toBeNull();
  } finally {
    const cur = (await api.get('/settings')).leaves;
    await api.put('/settings/leaves', { version: cur.version, value: { ...cur.value, absence_followup_days: 55 } });
  }
});
