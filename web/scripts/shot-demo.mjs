// Run one use case in the browser and save full-page screenshots: node scripts/shot-demo.mjs <outdir> "<use case title>" [mode]
import { chromium } from "playwright-core";
const [, , out, title, mode] = process.argv;
const browser = await chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1.5 });
await page.goto("http://127.0.0.1:8780/", { waitUntil: "networkidle" });
await page.screenshot({ path: `${out}/0-start.png` });
await page.locator(`aside button:has-text("${title}")`).first().click();
if (mode) await page.locator(`[role=radio]:has-text("${mode}")`).click();
await page.locator("button:has-text('Route it')").click();
await page.waitForTimeout(800);
await page.waitForFunction(() => { const b = [...document.querySelectorAll("button")].find((x) => x.textContent.includes("Route it")); return b && !b.disabled; }, null, { timeout: 300000 });
await page.screenshot({ path: `${out}/1-done.png`, fullPage: true });
await browser.close();
