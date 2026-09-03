/**
 * Rasterises a receipt for the printer, and reports what the font actually covered.
 *
 * THIS IS THE PRINTER PATH'S RENDERING ENGINE, not a test probe. A thermal printer's own
 * font ROM covers code pages and not Ethiopic, so for Amharic the HOST has to rasterise
 * and send the result as a bitmap. The bytes this produces are the bytes that become the
 * ESC/POS raster the printer prints; nothing renders the receipt a second time.
 *
 * It decides nothing, in the same way tests/m2c/render_probe.mjs decides nothing: it
 * renders, reads pixels, and prints numbers. Every assertion lives in tests/m4c, because
 * a renderer that judged its own output could be adjusted until it approved of itself.
 *
 * THE FONT IS THE VENDORED ONE OR THERE IS NO RENDER. print/fonts/ ships Noto Sans
 * Ethiopic because no Ethiopic font exists on the build container or on either CI runner,
 * and because a receipt's glyphs must not depend on what happened to be installed on the
 * machine that printed it. This file loads that file by path, waits for it, and FAILS
 * rather than letting Chromium quietly satisfy a missing glyph from a system font — which
 * is the failure that would otherwise pass on a developer's laptop and print boxes in an
 * outlet.
 *
 * HOW COVERAGE IS MEASURED, AND WHY IT NEEDS NO KNOWLEDGE OF WHAT .notdef LOOKS LIKE.
 * Each character is drawn twice: once in the vendored family, once in a family that does
 * not exist anywhere. The second is pure fallback — whatever the system does with a font
 * it cannot find. If the two bitmaps are IDENTICAL, the vendored font contributed nothing
 * for that character: either it lacks the glyph and the system supplied one, or neither
 * has it and both drew the same .notdef box. Either way it is not the vendored font's
 * glyph, and either way a customer is holding something the build did not intend. If the
 * bitmaps DIFFER, the vendored font drew it.
 *
 * That comparison is why this needs no hardcoded picture of a box, and why it keeps
 * working when Chromium changes what its last-resort glyph looks like.
 */
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';

const [, , documentPath, fontPath, dotsWide] = process.argv;

const WIDTH = Number.parseInt(dotsWide, 10);
if (!Number.isInteger(WIDTH) || WIDTH < 8 || WIDTH % 8 !== 0) {
  // A width that is not a whole number of bytes would make the packing below silently
  // drop the remainder of every row. Refuse rather than print a receipt missing its
  // right-hand edge.
  console.log(JSON.stringify({ error: 'RASTER_WIDTH_INVALID', detail: String(dotsWide) }));
  process.exit(1);
}

const doc = JSON.parse(readFileSync(documentPath, 'utf8'));

// THE FONT IS PASSED AS BYTES, NOT AS A URL. A file:// url is refused by Chromium — the
// page has no origin to fetch it from — and, more importantly, a url is a request that
// something else could answer. Reading the file here and constructing the FontFace from
// the buffer means the glyphs come from THIS FILE, with no resolution step in between
// that a host font could win.
const fontBase64 = readFileSync(fontPath).toString('base64');

const browser = await chromium.launch({ args: ['--font-render-hinting=none'] });
try {
  const page = await browser.newPage({ viewport: { width: WIDTH, height: 200 } });

  const measured = await page.evaluate(async ({ doc, fontBase64, WIDTH }) => {
    const FAMILY = 'VendoredReceipt';
    // A family name nothing can resolve. Drawing in it is what the platform does with a
    // font it does not have, which is exactly the baseline the coverage test needs.
    const ABSENT_FAMILY = 'NoSuchFamily-2f9d41c8';
    const SIZE = 24;

    const raw = Uint8Array.from(atob(fontBase64), (c) => c.charCodeAt(0));
    const face = new FontFace(FAMILY, raw.buffer);
    let loaded = false;
    try {
      await face.load();
      document.fonts.add(face);
      loaded = document.fonts.check(`${SIZE}px ${FAMILY}`);
    } catch (e) {
      return { fontLoaded: false, fontError: String(e && e.message ? e.message : e) };
    }
    if (!loaded) return { fontLoaded: false, fontError: 'the face loaded and did not register' };

    const cell = document.createElement('canvas');
    cell.width = SIZE * 2;
    cell.height = SIZE * 2;
    const cx = cell.getContext('2d', { willReadFrequently: true });

    /** The ink of one character in one family, as a stable digest and a pixel count. */
    const stamp = (ch, family) => {
      cx.fillStyle = '#fff';
      cx.fillRect(0, 0, cell.width, cell.height);
      cx.fillStyle = '#000';
      cx.font = `${SIZE}px "${family}"`;
      cx.textBaseline = 'alphabetic';
      cx.fillText(ch, 2, SIZE + 4);
      const d = cx.getImageData(0, 0, cell.width, cell.height).data;
      let h = 0x811c9dc5;
      let ink = 0;
      for (let i = 0; i < d.length; i += 4) {
        const on = d[i] < 128 ? 1 : 0;
        ink += on;
        h ^= on;
        h = Math.imul(h, 0x01000193) >>> 0;
      }
      return { hash: h >>> 0, ink };
    };

    const characters = [...new Set([...doc.lines.map((l) => l.text).join('')])]
      .filter((ch) => ch.trim() !== '')
      .sort();

    const coverage = characters.map((ch) => {
      const vendored = stamp(ch, FAMILY);
      const fallback = stamp(ch, ABSENT_FAMILY);
      return {
        codepoint: ch.codePointAt(0),
        character: ch,
        // The vendored font drew something the platform's fallback did not.
        drawnByTheVendoredFont: vendored.hash !== fallback.hash,
        inkPixels: vendored.ink,
        fallbackInkPixels: fallback.ink,
      };
    });

    // ---- the receipt itself, at printer width, one bit per dot -------------
    const LINE_HEIGHT = 30;
    const height = Math.max(LINE_HEIGHT * doc.lines.length, LINE_HEIGHT);
    const sheet = document.createElement('canvas');
    sheet.width = WIDTH;
    sheet.height = height;
    const sx = sheet.getContext('2d', { willReadFrequently: true });
    sx.fillStyle = '#fff';
    sx.fillRect(0, 0, WIDTH, height);
    sx.fillStyle = '#000';
    sx.textBaseline = 'alphabetic';

    doc.lines.forEach((line, i) => {
      sx.font = `${line.emphasis ? 'bold ' : ''}${SIZE}px "${FAMILY}"`;
      const y = LINE_HEIGHT * i + SIZE;
      if (line.align === 'right') {
        sx.textAlign = 'right';
        sx.fillText(line.text, WIDTH - 4, y);
      } else if (line.align === 'centre') {
        sx.textAlign = 'center';
        sx.fillText(line.text, WIDTH / 2, y);
      } else {
        sx.textAlign = 'left';
        sx.fillText(line.text, 4, y);
      }
    });

    // Threshold to one bit per dot, MSB first, which is the order ESC/POS raster mode
    // expects. A thermal head has no grey: every dot is burned or it is not, so the
    // threshold belongs here rather than in the printer.
    const px = sx.getImageData(0, 0, WIDTH, height).data;
    const rowBytes = WIDTH / 8;
    const bits = new Uint8Array(rowBytes * height);
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < WIDTH; x += 1) {
        const o = (y * WIDTH + x) * 4;
        const luma = (px[o] * 299 + px[o + 1] * 587 + px[o + 2] * 114) / 1000;
        if (luma < 128) bits[y * rowBytes + (x >> 3)] |= 0x80 >> (x & 7);
      }
    }
    let binary = '';
    for (const b of bits) binary += String.fromCharCode(b);

    return {
      fontLoaded: true,
      width: WIDTH,
      height,
      rowBytes,
      bitsBase64: btoa(binary),
      coverage,
    };
  }, { doc, fontBase64, WIDTH });

  console.log(JSON.stringify(measured));
} finally {
  await browser.close();
}
