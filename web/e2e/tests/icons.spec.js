// Every icon the live pages name is drawn: a missing one shows as an empty square, and only on the screen that names it,
// so most are never opened by another test (two in the settings and an invoice banner were found this way).
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

const PUBLIC = path.join(__dirname, '..', '..', 'public');
const LIVE = ['admin.html', 'center.html', 'login.html', 'activate.html'];
const NAMED = [
  /\bicon\(\s*'([a-z0-9-]+)'/g, // icon('name', 16)
  /\bicon:\s*'([a-z0-9-]+)'/g, // { icon: 'name' }
  /\bBT\.empty\(\s*'([a-z0-9-]+)'/g, // BT.empty('name', title)
  /\[\s*'[^']*[؀-ۿ][^']*'\s*,\s*'([a-z0-9-]+)'\s*,/g, // ['label', 'name', 'btn-…', …]; not ['label', 'route'] crumbs
  /\[\s*'#\/[^']*'\s*,\s*'([a-z0-9-]+)'/g, // ['#/route', 'name', 'label']
];

test('every icon named by the live pages exists', () => {
  const icons = fs.readFileSync(path.join(PUBLIC, 'assets/js/icons.js'), 'utf8');
  const defined = new Set([...icons.matchAll(/^ {2}'([a-z0-9-]+)':/gm)].map((m) => m[1]));
  const scripts = new Set();
  for (const page of LIVE) {
    const html = fs.readFileSync(path.join(PUBLIC, page), 'utf8');
    for (const m of html.matchAll(/src="(assets\/js\/[^"?]+\.js)/g)) scripts.add(m[1]);
  }
  expect(scripts.size).toBeGreaterThan(10);
  const missing = [];
  for (const file of scripts) {
    if (file.endsWith('icons.js')) continue;
    const src = fs.readFileSync(path.join(PUBLIC, file), 'utf8');
    for (const re of NAMED) for (const m of src.matchAll(re)) if (!defined.has(m[1])) missing.push(`${file}: ${m[1]}`);
  }
  expect(missing).toEqual([]);
});
