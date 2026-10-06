// A dialog puts the cursor in its first field when it opens, but never takes it back from a field the user is already
// in: the late focus once moved typing from the name into the code field, and the form refused to save.
const { test, expect } = require('./fixtures');

const open = (page, focusSecond) => page.evaluate(async (second) => {
  const h = window.BT.h;
  const d = window.BT.A.formModal({ title: 'تجربة', body: h`${window.BT.f.input({ name: 'a', label: 'أ' })}${window.BT.f.input({ name: 'b', label: 'ب' })}`, submit: () => true });
  if (second) d.panel.querySelector('[name=b]').focus(); // the user is quicker than the dialog's own focus
  await new Promise((r) => setTimeout(r, 200));
  const active = document.activeElement && document.activeElement.name;
  d.close();
  return active;
}, focusSecond);

test('a dialog never pulls the focus back from the field the user is in', async ({ admin }) => {
  expect(await open(admin, true)).toBe('b');
});

test('a dialog nobody touched puts the cursor in its first field', async ({ admin }) => {
  expect(await open(admin, false)).toBe('a');
});
