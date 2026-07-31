// Layout IR -> .pptx renderer (PptxGenJS sidecar).
//
// Protocol: reads ONE JSON job from stdin:
//   { out_path, theme, slides: [ LayoutIR, ... ] }
// Writes ONE JSON result to stdout:
//   { ok: true, out_path, slide_count }  |  { ok: false, error, stack }
//
// PptxGenJS pitfalls handled here (the adapter layer owns these, not the IR):
//  - hex colors carry NO leading '#'
//  - every addText/addShape gets a FRESH options object (PptxGenJS mutates options)
//  - bullets use { bullet: true } with explicit breakLine, never unicode bullet glyphs
//  - margin: 0 on text boxes so alignment matches the computed geometry

import pptxgen from "pptxgenjs";

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (c) => (data += c));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

const hex = (c, fallback) => {
  const v = (c || fallback || "000000").toString();
  return v.startsWith("#") ? v.slice(1) : v;
};

function textOpts(el) {
  const s = el.style || {};
  return {
    x: el.x, y: el.y, w: el.w, h: el.h,
    margin: 0,
    fontFace: s.fontFace || "Aptos",
    fontSize: s.fontSize || 14,
    bold: !!s.bold,
    color: hex(s.color, "1F2937"),
    align: s.align || "left",
    valign: s.valign || "top",
  };
}

function addText(slide, el) {
  slide.addText(String((el.content || {}).text || ""), textOpts(el));
}

function addBullets(slide, el) {
  const items = ((el.content || {}).items) || [];
  const runs = items.map((t) => ({
    text: String(t),
    options: { bullet: true, breakLine: true },
  }));
  slide.addText(runs.length ? runs : [{ text: "" }], textOpts(el));
}

function addShape(slide, el, pptx) {
  const s = el.style || {};
  const shapeType =
    s.shape === "roundRect" ? pptx.ShapeType.roundRect : pptx.ShapeType.rect;
  const opts = { x: el.x, y: el.y, w: el.w, h: el.h };
  if (s.fill) opts.fill = { color: hex(s.fill) };
  if (s.line) opts.line = { color: hex(s.line), width: 1 };
  slide.addShape(shapeType, opts);
}

async function main() {
  const raw = await readStdin();
  const job = JSON.parse(raw);
  const pptx = new pptxgen();
  pptx.defineLayout({ name: "PPTGEN_WIDE", width: 13.333, height: 7.5 });
  pptx.layout = "PPTGEN_WIDE";

  const bg = hex((job.theme?.colors || {}).background, "FFFFFF");
  for (const ir of job.slides || []) {
    const slide = pptx.addSlide();
    slide.background = { color: bg };
    for (const el of ir.elements || []) {
      // shapes first so text/bullets layer above their card/callout backgrounds
      if (el.type === "shape") addShape(slide, el, pptx);
    }
    for (const el of ir.elements || []) {
      if (el.type === "text") addText(slide, el);
      else if (el.type === "bullets") addBullets(slide, el);
    }
  }

  await pptx.writeFile({ fileName: job.out_path });
  process.stdout.write(
    JSON.stringify({ ok: true, out_path: job.out_path, slide_count: (job.slides || []).length })
  );
}

main().catch((err) => {
  process.stdout.write(
    JSON.stringify({ ok: false, error: String(err && err.message || err), stack: err && err.stack })
  );
  process.exitCode = 1;
});
