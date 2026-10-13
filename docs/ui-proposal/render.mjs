// Render the mockup to PNG: node docs/ui-proposal/render.mjs  (uses the web app's playwright-core and the installed Chrome)
import { chromium } from "../../web/node_modules/playwright-core/index.mjs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
const here = dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 }, deviceScaleFactor: 2 });
await page.goto("file://" + join(here, "stage.html"));
await page.waitForTimeout(300);
await page.screenshot({ path: join(here, "stage.png") });
await browser.close();
console.log("wrote", join(here, "stage.png"));
