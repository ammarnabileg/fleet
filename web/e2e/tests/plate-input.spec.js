// A plate is typed in two boxes with the slash fixed between them (18/23456): Arabic digits become Latin, typing the
// slash or two digits moves to the number, a pasted "18 / 23456" fills both, and the saved plate is code/number.
const { test, expect, uid } = require('./fixtures');

test('the vehicle form keeps the plate\'s slash fixed between its two parts', async ({ admin }) => {
  const n = uid();
  const num = String(10000 + (Number(n.slice(-4)) || 1)).slice(-5);
  await admin.goto('/admin.html#/vehicles');
  await admin.getByRole('button', { name: 'إضافة سيارة' }).click();
  const dlg = admin.locator('.overlay[data-open]').last();
  const code = dlg.locator('[data-plate-part=code]'), part = dlg.locator('[data-plate-part=num]');
  await expect(dlg.locator('.plate-slash')).toHaveText('/');
  await code.pressSequentially('٤٢'); // Arabic digits, two of them: on to the number
  await expect(code).toHaveValue('42');
  await expect(part).toBeFocused();
  await part.pressSequentially('ab' + num);
  await expect(part).toHaveValue(num); // digits only
  await expect(dlg.locator('input[type=hidden][name=plate_number]')).toHaveValue('42/' + num);
  await part.fill('');
  await part.press('Backspace'); // empty number: back to the code
  await expect(code).toBeFocused();
  await code.fill('');
  await code.pressSequentially('7/');
  await expect(part).toBeFocused(); // the slash typed moves on too
  await expect(code).toHaveValue('7');
  await part.pressSequentially(num);
  await expect(dlg.locator('input[type=hidden][name=plate_number]')).toHaveValue('7/' + num);
});
