// The company's public site (الموقع التعريفي): its words edited in the panel show on the public page at once, in
// Arabic and English; a visitor's message from the contact form reaches the panel's messages and is handled there.
const { test, expect, uid, settled } = require('./fixtures');

test('edited in the panel, shown on the public page, a visitor\'s message handled in the panel', async ({ admin, browser }) => {
  const n = uid();
  await admin.goto('/admin.html#/site');
  await settled(admin);
  const form = admin.locator('[data-site-form]');
  await form.locator('[name="company_name.ar"]').fill('شركة التجربة ' + n);
  await form.locator('[name="company_name.en"]').fill('Test company ' + n);
  await form.locator('[name="tagline.ar"]').fill('نوصّل في كل الكويت');
  await form.locator('[name=phone]').fill('+96512345678');
  await form.getByRole('button', { name: 'إضافة خدمة' }).click();
  const last = form.locator('[data-service]').last();
  await last.locator('[name="svc_title.ar"]').fill('خدمة ' + n);
  await last.locator('[name="svc_title.en"]').fill('Service ' + n);
  await form.getByRole('button', { name: 'حفظ' }).click();
  await expect(admin.locator('.toast').last()).toContainText('اتحفظ');

  // a visitor: no session, the public page
  const ctx = await browser.newContext({ locale: 'ar-KW' });
  const page = await ctx.newPage();
  await page.goto('/site.html');
  await expect(page.locator('h1[data-name]')).toHaveText('شركة التجربة ' + n);
  await expect(page.locator('[data-tagline]')).toHaveText('نوصّل في كل الكويت');
  await expect(page.locator('[data-services]')).toContainText('خدمة ' + n);
  await expect(page.locator('[data-info]')).toContainText('+96512345678');
  await page.locator('[data-lang-btn]').click();
  await expect(page.locator('h1[data-name]')).toHaveText('Test company ' + n);
  await expect(page.locator('[data-services]')).toContainText('Service ' + n);
  await page.locator('[data-lang-btn]').click();

  // no way to reply: refused on the page, nothing sent
  await page.locator('[name=name]').fill('زائر ' + n);
  await page.locator('[name=message]').fill('عايز أعرف تفاصيل الشغل');
  await page.getByRole('button', { name: 'إرسال' }).click();
  await expect(page.locator('[data-result]')).toContainText('رقم تليفون أو إيميل');
  await page.locator('[name=phone]').fill('+96555555555');
  await page.getByRole('button', { name: 'إرسال' }).click();
  await expect(page.locator('[data-result]')).toContainText('وصلتنا رسالتك');
  await ctx.close();

  await admin.goto('/admin.html#/site?tab=messages');
  await settled(admin);
  const card = admin.locator('[data-message]').filter({ hasText: 'زائر ' + n });
  await expect(card).toContainText('عايز أعرف تفاصيل الشغل');
  await expect(card).toContainText('+96555555555');
  await card.getByRole('button', { name: 'تمت المعالجة' }).click();
  await expect(admin.locator('[data-message]').filter({ hasText: 'زائر ' + n })).toHaveCount(0); // gone from «جديدة»
  await admin.locator('[data-status=done]').click();
  await expect(admin.locator('[data-message]').filter({ hasText: 'زائر ' + n })).toContainText('تمت المعالجة');
});
