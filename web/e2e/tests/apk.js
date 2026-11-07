// A minimal APK for the tests: a zip (stored, no compression) holding AndroidManifest.xml in Android's binary XML
// with <manifest package versionCode versionName> only. Enough for the server's reader, not for a phone.
// The same layout as backend/app/modules/app_updates/apk.py build_manifest.

function u16(n) { const b = Buffer.alloc(2); b.writeUInt16LE(n); return b; }
function u32(n) { const b = Buffer.alloc(4); b.writeUInt32LE(n >>> 0); return b; }
const NONE = 0xffffffff;

function manifest(pkg, versionCode, versionName) {
  const strs = ['versionCode', 'versionName', 'package', 'manifest', 'http://schemas.android.com/apk/res/android', 'android', versionName, pkg];
  const enc = strs.map((s) => Buffer.concat([u16(s.length), Buffer.from(s, 'utf16le'), Buffer.alloc(2)]));
  let data = Buffer.concat(enc);
  data = Buffer.concat([data, Buffer.alloc((4 - (data.length % 4)) % 4)]);
  const offsets = []; let o = 0;
  for (const e of enc) { offsets.push(o); o += e.length; }
  const start = 28 + 4 * strs.length;
  const pool = Buffer.concat([u16(1), u16(28), u32(start + data.length), u32(strs.length), u32(0), u32(0), u32(start), u32(0), ...offsets.map(u32), data]);
  const resmap = Buffer.concat([u16(0x180), u16(8), u32(16), u32(0x0101021b), u32(0x0101021c)]);
  const attr = (ns, name, raw, type, d) => Buffer.concat([u32(ns), u32(name), u32(raw), u16(8), Buffer.from([0, type]), u32(d)]);
  const attrs = Buffer.concat([attr(4, 0, NONE, 0x10, versionCode), attr(4, 1, 6, 0x03, 6), attr(NONE, 2, 7, 0x03, 7)]);
  const body = Buffer.concat([u32(NONE), u32(3), u16(20), u16(20), u16(3), u16(0), u16(0), u16(0), attrs]);
  const node = (type, size, extra) => Buffer.concat([u16(type), u16(16), u32(size), u32(1), u32(NONE), extra]);
  const chunks = Buffer.concat([
    pool, resmap,
    node(0x100, 24, Buffer.concat([u32(5), u32(4)])),
    node(0x102, 16 + body.length, body),
    node(0x103, 24, Buffer.concat([u32(NONE), u32(3)])),
    node(0x101, 24, Buffer.concat([u32(5), u32(4)])),
  ]);
  return Buffer.concat([u16(3), u16(8), u32(8 + chunks.length), chunks]);
}

const TABLE = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
function crc32(buf) { let c = 0xffffffff; for (const b of buf) c = TABLE[(c ^ b) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; }

function zip(files) {
  const locals = []; const centrals = []; let offset = 0;
  for (const [name, content] of files) {
    const n = Buffer.from(name); const crc = crc32(content);
    const common = Buffer.concat([u16(20), u16(0), u16(0), u16(0), u16(0), u32(crc), u32(content.length), u32(content.length), u16(n.length), u16(0)]);
    const local = Buffer.concat([u32(0x04034b50), common, n, content]);
    centrals.push(Buffer.concat([u32(0x02014b50), u16(20), common, u16(0), u16(0), u16(0), u32(0), u32(offset), n]));
    locals.push(local); offset += local.length;
  }
  const cd = Buffer.concat(centrals);
  const end = Buffer.concat([u32(0x06054b50), u16(0), u16(0), u16(files.length), u16(files.length), u32(cd.length), u32(offset), u16(0)]);
  return Buffer.concat([...locals, cd, end]);
}

function apk(pkg, versionCode, versionName) {
  return zip([['AndroidManifest.xml', manifest(pkg, versionCode, versionName)], ['classes.dex', Buffer.from('dex\n035\0')]]);
}

module.exports = { apk };
