// Run the multi-step use case once and screenshot its answer panel: node scripts/shot-answer.mjs <out.png>
import { chromium } from "playwright-core";
const browser = await chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
await page.goto("http://127.0.0.1:8780/");
await page.locator('button:has-text("Escalation, end to end")').first().click();
await page.locator("button:has-text('Route it')").click();
await page.getByText("The answer", { exact: true }).first().waitFor({ timeout: 300000 });
await page.waitForFunction(() => { const b = [...document.querySelectorAll("button")].find((x) => x.textContent.includes("Route it")); return b && !b.disabled; }, null, { timeout: 300000 });
await page.locator("section").filter({ hasText: "The answer" }).last().screenshot({ path: process.argv[2] });
await browser.close();
