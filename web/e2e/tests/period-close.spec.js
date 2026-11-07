// Month close: the month's check lists what is left (an expense still waiting for its approval) with a link to it,
// «إقفال الشهر» stays disabled until the check is clean, then the month closes and takes no more entries.
const { test, expect, uid, settled, clearToasts } = require('./fixtures');

// a month long before anything the other specs enter: closing it touches none of them
const MONTH = '2019-06';

test('a month checked, then closed once its check is clean', async ({ admin, api }) => {
  const n = uid();
  const company = await api.post('/companies', { name: { ar: 'شركة الإقفال ' + n, en: 'Close company ' + n } });
  const other = (await api.get('/finance/expense-types')).find((t) => t.code === 'other');
  const e = await api.post('/finance/expenses', {
    company_id: company.id, type_id: other.id, expense_date: MONTH + '-15', amount: '2.500', payment_method: 'bank',
  });
  const top = () => admin.locator('.overlay[data-open]').last();

  await admin.goto('/admin.html#/finance?tab=periods&month=' + MONTH);
  await settled(admin);
  const result = admin.locator('#fin-periods [data-check-result="' + MONTH + '"]');
  await expect(result.locator('[data-problem=pending_expenses]')).toContainText('بانتظار الاعتماد');
  await expect(result.locator('[data-problem=pending_expenses] a')).toHaveAttribute('href', '#/finance?tab=expenses&chip=pending');
  await expect(result.locator('[data-close-month]')).toBeDisabled();
  await expect(admin.locator('#fin-periods [data-periods] tbody tr').first()).toBeVisible(); // the last twelve months

  // the expense decided: the check is clean and the month closes
  await api.post(`/finance/expenses/${e.id}/reject`, { note: 'not this month' });
  await admin.locator('#fin-periods [data-check-pick]').click();
  await expect(result.locator('.banner.success')).toContainText('جاهز للإقفال');
  await expect(result.locator('[data-close-month]')).toBeEnabled();
  await result.locator('[data-close-month]').click();
  await clearToasts(admin);
  await top().getByRole('button', { name: 'إقفال الشهر', exact: true }).click();
  await expect(admin.locator('.toast').last()).toContainText('تم إقفال الشهر');
  await expect(result).toContainText('مقفول');
  await expect(result.locator('[data-close-month]')).toHaveCount(0);

  // closed: an expense dated in it is refused
  await expect(api.post('/finance/expenses', {
    company_id: company.id, type_id: other.id, expense_date: MONTH + '-20', amount: '1', payment_method: 'bank',
  })).rejects.toThrow(/409.*period_closed/);
  // left open again for whoever runs after: the latest closed month reopens with a reason
  const back = await api.post(`/finance/periods/${MONTH}/reopen`, { reason: 'e2e clean-up' });
  expect(back.status).toBe('open');
});
