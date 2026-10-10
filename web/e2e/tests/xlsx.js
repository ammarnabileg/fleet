// A minimal .xlsx for the import tests, with no dependency: sheets of rows (text and numbers) as inline strings, no
// styles, in an uncompressed zip. Excel, LibreOffice and openpyxl (what the server reads with) all open it.
const zlib = require('zlib');

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
const MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
const REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';

function column(i) {
  let s = '';
  for (i += 1; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + ((i - 1) % 26)) + s;
  return s;
}

function sheetXml(rows) {
  const body = rows.map((row, r) => `<row r="${r + 1}">${row.map((v, c) => {
    if (v == null || v === '') return '';
    const ref = column(c) + (r + 1);
    return typeof v === 'number' ? `<c r="${ref}"><v>${v}</v></c>` : `<c r="${ref}" t="inlineStr"><is><t>${esc(v)}</t></is></c>`;
  }).join('')}</row>`).join('');
  return `${XML}<worksheet xmlns="${MAIN}"><sheetData>${body}</sheetData></worksheet>`;
}

/** A zip of stored (uncompressed) entries: [{ name, data }]. */
function zip(entries) {
  const out = [], central = [];
  let offset = 0;
  for (const { name, data } of entries) {
    const n = Buffer.from(name, 'utf8'), crc = zlib.crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt16LE(0x0800, 6); // UTF-8 names
    local.writeUInt16LE(0x21, 12); // 1980-01-01
    local.writeUInt32LE(crc, 14); local.writeUInt32LE(data.length, 18); local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(n.length, 26);
    const entry = Buffer.alloc(46);
    entry.writeUInt32LE(0x02014b50, 0); entry.writeUInt16LE(20, 4); entry.writeUInt16LE(20, 6); entry.writeUInt16LE(0x0800, 8);
    entry.writeUInt16LE(0x21, 14);
    entry.writeUInt32LE(crc, 16); entry.writeUInt32LE(data.length, 20); entry.writeUInt32LE(data.length, 24);
    entry.writeUInt16LE(n.length, 28); entry.writeUInt32LE(offset, 42);
    out.push(local, n, data);
    central.push(entry, n);
    offset += 30 + n.length + data.length;
  }
  const dir = Buffer.concat(central), end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(entries.length, 8); end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(dir.length, 12); end.writeUInt32LE(offset, 16);
  return Buffer.concat([...out, dir, end]);
}

/** The workbook: { 'sheet name': [[cell, ...], ...], ... } in order. */
function xlsx(sheets) {
  const names = Object.keys(sheets);
  const part = (name, text) => ({ name, data: Buffer.from(text, 'utf8') });
  return zip([
    part('[Content_Types].xml', `${XML}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">`
      + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      + '<Default Extension="xml" ContentType="application/xml"/>'
      + '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
      + names.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join('')
      + '</Types>'),
    part('_rels/.rels', `${XML}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">`
      + `<Relationship Id="rId1" Type="${REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>`),
    part('xl/workbook.xml', `${XML}<workbook xmlns="${MAIN}" xmlns:r="${REL}"><sheets>`
      + names.map((s, i) => `<sheet name="${esc(s)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join('') + '</sheets></workbook>'),
    part('xl/_rels/workbook.xml.rels', `${XML}<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">`
      + names.map((_, i) => `<Relationship Id="rId${i + 1}" Type="${REL}/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join('')
      + '</Relationships>'),
    ...names.map((s, i) => part(`xl/worksheets/sheet${i + 1}.xml`, sheetXml(sheets[s]))),
  ]);
}

/** The entries of a zip (stored or deflated), by name. */
function unzip(buf) {
  const out = {};
  let i = buf.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06])); // end of central directory
  const count = buf.readUInt16LE(i + 10);
  let p = buf.readUInt32LE(i + 16);
  for (let n = 0; n < count; n++) {
    const method = buf.readUInt16LE(p + 10), size = buf.readUInt32LE(p + 20), nameLen = buf.readUInt16LE(p + 28);
    const extra = buf.readUInt16LE(p + 30), comment = buf.readUInt16LE(p + 32), local = buf.readUInt32LE(p + 42);
    const name = buf.toString('utf8', p + 46, p + 46 + nameLen);
    const start = local + 30 + buf.readUInt16LE(local + 26) + buf.readUInt16LE(local + 28);
    const data = buf.subarray(start, start + size);
    out[name] = method === 8 ? zlib.inflateRawSync(data) : data;
    p += 46 + nameLen + extra + comment;
  }
  return out;
}

const unescape = (s) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, '&');

/** The first sheet of a workbook as rows of cell texts (shared strings, inline strings and numbers). */
function readXlsx(buf) {
  const files = unzip(buf);
  const shared = files['xl/sharedStrings.xml']
    ? [...files['xl/sharedStrings.xml'].toString('utf8').matchAll(/<si>([\s\S]*?)<\/si>/g)]
      .map((m) => unescape([...m[1].matchAll(/<t[^>]*>([\s\S]*?)<\/t>/g)].map((t) => t[1]).join('')))
    : [];
  const sheet = files['xl/worksheets/sheet1.xml'].toString('utf8');
  return [...sheet.matchAll(/<row[^>]*>([\s\S]*?)<\/row>/g)].map((row) => [...row[1].matchAll(/<c ([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)].map((c) => {
    const type = (/t="(\w+)"/.exec(c[1]) || [])[1], body = c[2] || '';
    if (type === 's') return shared[Number(/<v>(\d+)<\/v>/.exec(body)[1])];
    if (type === 'inlineStr') return unescape((/<t[^>]*>([\s\S]*?)<\/t>/.exec(body) || [])[1] || '');
    const v = /<v>([^<]*)<\/v>/.exec(body);
    return v ? (type === 'str' ? unescape(v[1]) : Number(v[1])) : null;
  }));
}

module.exports = { xlsx, readXlsx };
