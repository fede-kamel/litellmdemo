// Record the demo's beats as videos, for a talk where the live path is slow or down:
//   LITELLMDEMO_APP=https://<host> node web/scripts/record-demo.mjs [outdir]
//   ONLY=invoice LITELLMDEMO_APP=https://<host> node web/scripts/record-demo.mjs   (one beat)
// One .webm per beat in outdir (default ../out/videos), and an .mp4 beside it when ffmpeg is on the PATH
// (PowerPoint and Keynote play the .mp4). Each beat opens the control room fresh, runs a use case the way
// a click does, and lingers on the decision, the agent trace and the sandbox console.
import { execFileSync } from "node:child_process";
import { mkdirSync, renameSync } from "node:fs";
import { chromium } from "playwright-core";

const [, , out = "../out/videos"] = process.argv;
const BASE = process.env.LITELLMDEMO_APP ?? "http://127.0.0.1:8780";
const ONLY = process.env.ONLY ?? "";
mkdirSync(out, { recursive: true });

const look = (page, ms) => page.waitForTimeout(ms);
const detail = (page, label) => page.locator(`main button:has-text("${label}")`).first().click();
const useCase = async (page, title) => {
  await page.locator(`button:has-text("${title}")`).first().click();
  await look(page, 1500);
  await page.locator("button:has-text('Route it')").click();
  await look(page, 800);
  await page.waitForFunction(() => { const b = [...document.querySelectorAll("button")].find((x) => x.textContent.includes("Route it")); return b && !b.disabled; }, null, { timeout: 300000 });
};

const BEATS = [
  ["01-billing-dispute", async (page) => {   // beat 1: the request, the decision, the answer, then every call and the sandbox console
    await useCase(page, "Billing dispute"); await look(page, 6000);
    await detail(page, "Every call"); await look(page, 6000);
    await detail(page, "Sandbox console"); await look(page, 6000);
  }],
  ["02-premium-lane", async (page) => {   // beat 2: the same kind of request with a premium tag takes another lane, no classifier
    await useCase(page, "Same request, premium contract"); await look(page, 7000);
  }],
  ["03-invoice-photo-to-reply", async (page) => {   // beat 3: a planner splits the job; LiteLLM routes every task on its own
    await useCase(page, "Invoice photo to reply"); await look(page, 7000);
    await detail(page, "Every call"); await look(page, 9000);
  }],
  ["04-try-to-escape", async (page) => {   // beat 4: OCI, a vendor and the admin API, all refused; the key's models and budget
    await page.locator("header button:has-text('Safety')").click(); await look(page, 4000);
    await page.getByRole("button", { name: "Try to escape" }).filter({ visible: true }).first().click();
    await page.getByText("REFUSED", { exact: false }).filter({ visible: true }).first().waitFor({ timeout: 120000 });
    await look(page, 8000);
  }],
  ["05-deployment-fails", async (page) => {   // beat 5: a failing deployment, and the answer still arrives from the next group
    await useCase(page, "A deployment fails"); await look(page, 7000);
  }],
  ["06-japanese-request", async (page) => {   // the language rule, Cohere, two calls
    await useCase(page, "Japanese request"); await look(page, 7000);
  }],
  ["07-debug-a-race-condition", async (page) => {   // code goes to Codex on OCI's Responses API
    await useCase(page, "Debug a race condition"); await look(page, 7000);
    await detail(page, "Every call"); await look(page, 5000);
  }],
  ["08-compare-routers", async (page) => {   // the same request through LiteLLM's heuristic, its LLM classifier and the trained ladder
    await page.locator('nav button:has-text("How the router decides")').click(); await look(page, 1500);
    await page.locator('main button:has-text("Compare routers")').first().click(); await look(page, 2500);
    await page.locator("button:has-text('Send to all three')").click();
    await page.getByText("Built-in heuristic", { exact: false }).first().waitFor({ timeout: 240000 });
    await look(page, 9000);
  }],
];

const ffmpeg = (() => { try { execFileSync("ffmpeg", ["-version"], { stdio: "ignore" }); return true; } catch { return false; } })();
const browser = await chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
let failed = 0;
for (const [name, beat] of BEATS) {
  if (ONLY && !name.includes(ONLY)) continue;
  const started = Date.now();
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 }, recordVideo: { dir: out, size: { width: 1600, height: 1000 } } });
  const page = await context.newPage();
  let ok = true;
  try {
    await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
    await look(page, 2000);
    await beat(page);
    await look(page, 1000);
  } catch (err) {
    ok = false; failed += 1;
    console.log(`FAIL  ${name}  ${String(err).split("\n")[0]}`);
  }
  const video = page.video();
  await context.close();
  const webm = `${out}/${name}.webm`;
  renameSync(await video.path(), webm);
  let note = `${((Date.now() - started) / 1000).toFixed(0)}s`;
  if (ok && ffmpeg) {
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", webm, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", `${out}/${name}.mp4`]);
    note += ", mp4";
  }
  if (ok) console.log(`OK    ${name}  (${note})`);
}
await browser.close();
console.log(`\n${failed ? "VIDEOS INCOMPLETE" : "VIDEOS OK"} (${BEATS.filter(([n]) => !ONLY || n.includes(ONLY)).length - failed} recorded) in ${out}`);
process.exit(failed ? 1 : 0);
