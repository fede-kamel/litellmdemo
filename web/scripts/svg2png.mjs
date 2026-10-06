// Render SVG files to PNG with headless Chrome: node scripts/svg2png.mjs <scale> <in.svg> [<in2.svg> ...]
import { chromium } from "playwright-core";
import { readFileSync } from "node:fs";
const [, , scale, ...files] = process.argv;
const browser = await chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
for (const file of files) {
  const svg = readFileSync(file, "utf8");
  const m = svg.match(/<svg[^>]*\swidth="([\d.]+)"[^>]*\sheight="([\d.]+)"/);
  const [w, h] = m ? [Number(m[1]), Number(m[2])] : [1000, 1000];
  const page = await browser.newPage({ viewport: { width: Math.ceil(w), height: Math.ceil(h) }, deviceScaleFactor: Number(scale) });
  await page.setContent(`<html><body style="margin:0;background:transparent">${svg}</body></html>`);
  await page.locator("svg").first().screenshot({ path: file.replace(/\.svg$/, ".png"), omitBackground: true });
  await page.close();
  console.log("rendered", file.replace(/\.svg$/, ".png"));
}
await browser.close();
