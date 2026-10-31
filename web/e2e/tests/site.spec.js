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
  await expect(page.locator('header [data-name-ar]')).toHaveText('شركة التجربة ' + n);
  await expect(page.locator('header [data-name-en]')).toHaveText(('Test company ' + n).toUpperCase());
  await expect(page.locator('[data-tagline]')).toHaveText('نوصّل في كل الكويت');
  await expect(page.locator('[data-services]')).toContainText('خدمة ' + n);
  await expect(page.locator('[data-info]')).toContainText('+96512345678');

  // no way to reply: refused on the page, nothing sent
  await page.locator('#name').fill('زائر ' + n);
  await page.locator('#phone').fill('');
  await page.locator('#message').fill('عايز أعرف تفاصيل الشغل');
  await page.locator('#phone').evaluate((e) => e.removeAttribute('required'));
  await page.getByRole('button', { name: /إرسال الاستفسار/ }).click();
  await expect(page.locator('#feedback')).toContainText('رقم هاتفك');
  await page.locator('#phone').fill('+96555555555');
  await page.getByRole('button', { name: /إرسال الاستفسار/ }).click();
  await expect(page.locator('#feedback')).toContainText('وصلنا استفسارك');
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
