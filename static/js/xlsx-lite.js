/*
 * Minimal .xlsx reader/writer with no dependencies, so Excel import/export
 * works with no internet connection (a CDN spreadsheet library can't be
 * fetched offline, and pulling one into the app shell would be a big
 * precache for a small feature).
 *
 *  write(rows, sheetName) -> Uint8Array   a valid single-sheet workbook
 *  read(arrayBuffer)      -> Promise<string[][]>   the FIRST worksheet as text
 *
 * Deliberately small: text and numbers only, one sheet, no styles. Reading
 * understands shared strings, inline strings and cached formula results, and
 * inflates with the browser's built-in DecompressionStream. Files that are
 * encrypted, ZIP64, or expand past a sanity limit are refused with a plain
 * message rather than half-read.
 */
const XlsxLite = (function () {
    const enc = new TextEncoder();
    const dec = new TextDecoder("utf-8");
    const MAX_UNCOMPRESSED = 30 * 1024 * 1024;

    // ---- zip (store-only writer) ----------------------------------------
    let crcTable = null;
    function crc32(bytes) {
        if (!crcTable) {
            crcTable = new Uint32Array(256);
            for (let n = 0; n < 256; n++) {
                let c = n;
                for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
                crcTable[n] = c >>> 0;
            }
        }
        let crc = 0xffffffff;
        for (let i = 0; i < bytes.length; i++) crc = crcTable[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
        return (crc ^ 0xffffffff) >>> 0;
    }

    function zipStore(files) {
        const chunks = [];
        const central = [];
        let offset = 0;
        const u16 = (n) => new Uint8Array([n & 255, (n >>> 8) & 255]);
        const u32 = (n) => new Uint8Array([n & 255, (n >>> 8) & 255, (n >>> 16) & 255, (n >>> 24) & 255]);
        const push = (...parts) => { for (const p of parts) { chunks.push(p); offset += p.length; } };
        for (const f of files) {
            const name = enc.encode(f.name);
            const crc = crc32(f.data);
            const localOffset = offset;
            push(u32(0x04034b50), u16(20), u16(0x0800), u16(0), u16(0), u16(0x21), u32(crc), u32(f.data.length), u32(f.data.length), u16(name.length), u16(0), name, f.data);
            central.push({ name, crc, size: f.data.length, localOffset });
        }
        const cdStart = offset;
        for (const c of central) {
            push(u32(0x02014b50), u16(20), u16(20), u16(0x0800), u16(0), u16(0), u16(0x21), u32(c.crc), u32(c.size), u32(c.size), u16(c.name.length), u16(0), u16(0), u16(0), u16(0), u32(0), u32(c.localOffset), c.name);
        }
        const cdSize = offset - cdStart;
        push(u32(0x06054b50), u16(0), u16(0), u16(central.length), u16(central.length), u32(cdSize), u32(cdStart), u16(0));
        const out = new Uint8Array(offset);
        let pos = 0;
        for (const c of chunks) { out.set(c, pos); pos += c.length; }
        return out;
    }

    // ---- writer -----------------------------------------------------------
    function xmlEsc(s) {
        return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")
            // characters XML 1.0 forbids would make Excel refuse the file
            .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
    }

    function colName(i) {
        let s = "";
        for (i += 1; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + ((i - 1) % 26)) + s;
        return s;
    }

    function write(rows, sheetName) {
        let sheetRows = "";
        rows.forEach((row, r) => {
            let cells = "";
            row.forEach((v, c) => {
                if (v === null || v === undefined || v === "") return;
                const ref = colName(c) + (r + 1);
                if (typeof v === "number" && Number.isFinite(v)) cells += `<c r="${ref}"><v>${v}</v></c>`;
                else {
                    let text = String(v);
                    // Never let user text be interpreted as a formula.
                    if (/^[=+@]/.test(text) || (/^-/.test(text) && !/^-?\d+(\.\d+)?$/.test(text))) text = "'" + text;
                    cells += `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${xmlEsc(text)}</t></is></c>`;
                }
            });
            sheetRows += `<row r="${r + 1}">${cells}</row>`;
        });
        const name = xmlEsc((sheetName || "Sheet1").replace(/[\\/?*[\]:]/g, " ").slice(0, 31) || "Sheet1");
        const files = [
            ["[Content_Types].xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>`],
            ["_rels/.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`],
            ["xl/workbook.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${name}" sheetId="1" r:id="rId1"/></sheets></workbook>`],
            ["xl/_rels/workbook.xml.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`],
            ["xl/worksheets/sheet1.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${sheetRows}</sheetData></worksheet>`],
        ].map(([n, t]) => ({ name: n, data: enc.encode(t) }));
        return zipStore(files);
    }

    // ---- reader -----------------------------------------------------------
    async function inflateRaw(bytes) {
        if (typeof DecompressionStream === "undefined") {
            throw new Error("This browser can't open .xlsx files offline — save the sheet as CSV instead.");
        }
        const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
        const reader = stream.getReader();
        const parts = [];
        let total = 0;
        for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            total += value.length;
            if (total > MAX_UNCOMPRESSED) throw new Error("That spreadsheet is too large to import.");
            parts.push(value);
        }
        const out = new Uint8Array(total);
        let pos = 0;
        for (const p of parts) { out.set(p, pos); pos += p.length; }
        return out;
    }

    function readZipEntries(buf) {
        const v = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
        let eocd = -1;
        for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65557); i--) {
            if (v.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
        }
        if (eocd < 0) throw new Error("That file isn't a valid .xlsx workbook.");
        const count = v.getUint16(eocd + 10, true);
        let p = v.getUint32(eocd + 16, true);
        if (count === 0xffff || p === 0xffffffff) throw new Error("That workbook uses a format we can't read offline — save it as CSV instead.");
        const entries = {};
        for (let i = 0; i < count; i++) {
            if (v.getUint32(p, true) !== 0x02014b50) throw new Error("That file isn't a valid .xlsx workbook.");
            const flags = v.getUint16(p + 8, true);
            const method = v.getUint16(p + 10, true);
            const csize = v.getUint32(p + 20, true);
            const nameLen = v.getUint16(p + 28, true), extraLen = v.getUint16(p + 30, true), commentLen = v.getUint16(p + 32, true);
            const local = v.getUint32(p + 42, true);
            const name = dec.decode(buf.subarray(p + 46, p + 46 + nameLen));
            if (flags & 1) throw new Error("That workbook is password-protected.");
            entries[name] = { method, csize, local };
            p += 46 + nameLen + extraLen + commentLen;
        }
        return { entries, v };
    }

    async function entryText(buf, zip, name) {
        const e = zip.entries[name];
        if (!e) return null;
        const v = zip.v;
        const nameLen = v.getUint16(e.local + 26, true), extraLen = v.getUint16(e.local + 28, true);
        const start = e.local + 30 + nameLen + extraLen;
        const raw = buf.subarray(start, start + e.csize);
        if (e.method === 0) return dec.decode(raw);
        if (e.method === 8) return dec.decode(await inflateRaw(raw));
        throw new Error("That workbook uses an unsupported compression method.");
    }

    function xmlUnesc(s) {
        return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'")
            .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(+n)).replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
            .replace(/&amp;/g, "&");
    }

    function textOf(xml) {
        let out = "";
        const re = /<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g;
        let m;
        while ((m = re.exec(xml))) out += xmlUnesc(m[1]);
        return out;
    }

    function colIndex(ref) {
        const letters = /^[A-Z]+/.exec(ref)[0];
        let n = 0;
        for (const ch of letters) n = n * 26 + (ch.charCodeAt(0) - 64);
        return n - 1;
    }

    async function read(arrayBuffer) {
        const buf = new Uint8Array(arrayBuffer);
        const zip = readZipEntries(buf);
        let sheetName = null;
        // First worksheet, by workbook order when we can tell, else by name.
        const wb = await entryText(buf, zip, "xl/workbook.xml");
        const rels = await entryText(buf, zip, "xl/_rels/workbook.xml.rels");
        if (wb && rels) {
            const first = /<sheet\b[^>]*\br:id="([^"]+)"/.exec(wb);
            if (first) {
                const rel = new RegExp(`<Relationship\\b[^>]*\\bId="${first[1]}"[^>]*>`).exec(rels);
                const target = rel && /\bTarget="([^"]+)"/.exec(rel[0]);
                if (target) sheetName = target[1].startsWith("/") ? target[1].slice(1) : "xl/" + target[1].replace(/^\.\//, "");
            }
        }
        if (!sheetName || !zip.entries[sheetName]) {
            sheetName = Object.keys(zip.entries).filter((n) => /^xl\/worksheets\/sheet\d+\.xml$/.test(n)).sort()[0];
        }
        if (!sheetName) throw new Error("No worksheet found in that file.");

        const shared = [];
        const ssXml = await entryText(buf, zip, "xl/sharedStrings.xml");
        if (ssXml) {
            const re = /<si\b[^>]*>([\s\S]*?)<\/si>/g;
            let m;
            while ((m = re.exec(ssXml))) shared.push(textOf(m[1]));
        }

        const sheet = await entryText(buf, zip, sheetName);
        const rows = [];
        const rowRe = /<row\b[^>]*\/>|<row\b[^>]*>([\s\S]*?)<\/row>/g;
        let rm;
        while ((rm = rowRe.exec(sheet))) {
            const cells = [];
            const cellRe = /<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g;
            let cm;
            const body = rm[1] || "";
            while ((cm = cellRe.exec(body))) {
                const attrs = cm[1], inner = cm[2] || "";
                const ref = /\br="([A-Z]+\d+)"/.exec(attrs);
                if (!ref) continue;
                const type = (/\bt="([^"]+)"/.exec(attrs) || [])[1];
                const vMatch = /<v>([\s\S]*?)<\/v>/.exec(inner);
                let value = "";
                if (type === "s") value = vMatch ? shared[parseInt(vMatch[1], 10)] || "" : "";
                else if (type === "inlineStr") value = textOf(inner);
                else if (type === "str") value = vMatch ? xmlUnesc(vMatch[1]) : "";
                else if (vMatch) value = xmlUnesc(vMatch[1]);
                cells[colIndex(ref[1])] = value;
            }
            for (let i = 0; i < cells.length; i++) if (cells[i] === undefined) cells[i] = "";
            rows.push(cells);
        }
        return rows;
    }

    const api = { write, read, crc32 };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    return api;
})();
