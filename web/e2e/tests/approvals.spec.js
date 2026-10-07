// Approval workflows from the panel: the expenses' workflow built in its editor (a person, then a role above 100); a
// small expense approved from the inbox in one step; a large one approved at its first step and moved on to the role;
// its trail shown in the expense itself; a delegation given and cancelled. The workflow is switched off at the end, so
// the other tests keep approving by permission.
const { test, expect, uid, settled, clearToasts } = require('./fixtures');

test('a workflow configured, documents approved step by step from the inbox, and a delegation', async ({ admin, api }) => {
  test.setTimeout(150_000);
  const n = uid();
  const me = await api.get('/auth/me');
  const company = await api.post('/companies', { name: { ar: 'شركة الاعتماد ' + n, en: 'Approvals company ' + n } });
  const fuel = (await api.get('/finance/expense-types')).find((t) => t.code === 'fuel');
  const expense = (amount) => api.post('/finance/expenses', {
    company_id: company.id, type_id: fuel.id, expense_date: new Date().toISOString().slice(0, 10), amount, payment_method: 'treasury',
  });
  const top = () => admin.locator('.overlay[data-open]').last();
  const toast = () => admin.locator('.toast').last();
  const flow = async () => (await api.get('/approvals/workflows')).find((w) => w.process === 'expense');
  try {
    // ---- the workflow built in the editor: the administrator in person, then the management role from 100
    await admin.goto('/admin.html#/approvals?tab=workflows');
    await settled(admin);
    const card = admin.locator('#view [data-flow=expense]');
    await expect(card).toContainText('بالصلاحية');
    await card.locator('[data-edit]').click();
    const m = top();
    await m.locator('[data-add]').click();
    await m.locator('[name=ar_0]').fill('مراجعة المدير');
    await m.locator('[name=en_0]').fill('Manager review');
    await m.locator('[name=kind_0]').selectOption('user');
    await m.locator('[name=user_0]').selectOption(me.public_id);
    await m.locator('[data-add]').click();
    await expect(m.locator('[name=ar_0]')).toHaveValue('مراجعة المدير'); // kept while the form redraws
    await m.locator('[name=ar_1]').fill('اعتماد الإدارة');
    await m.locator('[name=en_1]').fill('Management approval');
    await m.locator('[name=role_1]').selectOption('management');
    await m.locator('[name=min_1]').fill('100');
    await clearToasts(admin);
    await m.getByRole('button', { name: 'حفظ المسار' }).click();
    await expect(toast()).toContainText('حُفظ المسار');
    await expect(card).toContainText('مفعّل');
    await expect(card.locator('li')).toHaveCount(2);
    await expect(card.locator('li').nth(1)).toContainText('100.000');

    // ---- 50.000: one step, approved from the inbox
    const small = await expense('50');
    await admin.goto('/admin.html#/approvals');
    await settled(admin);
    const row = (number) => admin.locator('#view [data-panel=inbox] tbody tr', { hasText: 'EXP-' + number });
    await expect(row(small.number)).toContainText('1/1');
    await row(small.number).click();
    await expect(top()).toContainText('مراجعة المدير');
    await top().getByRole('button', { name: 'اعتماد', exact: true }).click();
    await clearToasts(admin);
    await top().getByRole('button', { name: 'اعتماد', exact: true }).click(); // the confirmation
    await expect(toast()).toContainText('اعتُمد المستند');
    await expect(row(small.number)).toHaveCount(0);
    expect((await api.get('/finance/expenses/' + small.id)).status).toBe('approved');

    // ---- 150.000: the first step here, then it waits for the management role, not for this user
    const big = await expense('150');
    await admin.reload(); // the same address: the inbox is fetched again
    await settled(admin);
    await expect(row(big.number)).toContainText('1/2');
    await row(big.number).click();
    await top().getByRole('button', { name: 'اعتماد', exact: true }).click();
    await top().locator('[name=reason]').fill('الفاتورة مطابقة');
    await clearToasts(admin);
    await top().getByRole('button', { name: 'اعتماد', exact: true }).click();
    await expect(toast()).toContainText('سُجّل قرارك');
    await expect(toast()).toContainText('اعتماد الإدارة');
    await expect(row(big.number)).toHaveCount(0);
    expect((await api.get('/finance/expenses/' + big.id)).status).toBe('pending');

    // ---- the expense itself shows its trail
    await admin.goto('/admin.html#/finance');
    await settled(admin);
    await admin.locator('#view [data-panel=expenses] tbody tr', { hasText: '#' + big.number }).click();
    const trail = top().locator('[data-approvals]');
    await expect(trail).toContainText('مسار الاعتماد');
    await expect(trail).toContainText('الفاتورة مطابقة');
    await expect(trail.locator('[data-step-state=approved]')).toHaveCount(1);
    await expect(trail.locator('[data-step-state=current]')).toContainText('اعتماد الإدارة');
    await admin.keyboard.press('Escape');

    // ---- a delegation while away, then cancelled
    const delegate = await api.post('/users', {
      username: 'deleg' + n, full_name: 'المفوض ' + n, password: 'correct-horse-battery-' + n,
      role_codes: ['management'], all_companies: true, company_ids: [],
    });
    await admin.goto('/admin.html#/approvals?tab=delegations');
    await settled(admin);
    await admin.locator('#view [data-new-delegation]').click();
    await top().locator('[name=delegate]').selectOption(delegate.public_id);
    await top().locator('[name=reason]').fill('إجازة');
    await clearToasts(admin);
    await top().getByRole('button', { name: 'تفويض', exact: true }).click();
    await expect(toast()).toContainText('سُجّل التفويض');
    const given = admin.locator('#view [data-panel=delegations] tbody tr', { hasText: 'المفوض ' + n });
    await expect(given).toContainText('سارٍ');
    await given.locator('[data-row-menu]').click();
    await admin.getByRole('menuitem', { name: 'إلغاء التفويض' }).click();
    await top().getByRole('button', { name: 'إلغاء التفويض' }).click();
    await expect(given).toContainText('ملغى');
  } finally {
    // switched off: the requests under way are cancelled and the other tests approve by permission again
    const w = await flow();
    await api.put('/approvals/workflows/expense', { version: w.version, active: false, steps: [] });
  }
});
