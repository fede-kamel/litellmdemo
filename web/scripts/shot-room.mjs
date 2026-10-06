// Screenshot the control room after running one scenario:  node scripts/shot-room.mjs "<scenario title>" out.png
import { chromium } from "playwright-core";
const [, , title = "Escalation with SLA credits", out = "../out/room.png"] = process.argv;
const b = await chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
const p = await b.newPage({ viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 2 });
await p.goto("http://127.0.0.1:8780/", { waitUntil: "networkidle" });
await p.locator(`aside button:has-text("${title}")`).click();
await p.locator("button:has-text('Run through the gateway')").click();
await p.locator("text=/Answer ·/").first().waitFor({ timeout: 240000 });
await p.waitForTimeout(800);
await p.screenshot({ path: out });
await b.close();
console.log("shot", out);
