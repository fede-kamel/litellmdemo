// Click through the control room in a real browser and check what each screen says:
//   node scripts/ui-e2e.mjs [outdir]          (web app on 127.0.0.1:8780, gateway on 4000)
// Ends with "UI E2E OK (n/n)". Screenshots of every step go to outdir.
import { mkdirSync } from "node:fs";
import { chromium } from "playwright-core";

const [, , out = "../out/ui-e2e"] = process.argv;
mkdirSync(out, { recursive: true });
const results = [];
const check = (name, ok, detail = "") => { results.push(ok); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`); };

const browser = await chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
const shot = (name) => page.screenshot({ path: `${out}/${name}.png` });
const visible = (text, timeout = 15000) => page.getByText(text, { exact: false }).first().waitFor({ timeout }).then(() => true, () => false);
const tab = (label) => page.locator(`nav button:has-text("${label}")`).click();
const scenario = (title) => page.locator(`aside button:has-text("${title}")`).click();
const runAndWait = async () => {
  await page.locator("button:has-text('Run through the gateway')").click();
  return page.locator("text=/Answer ·/").first().waitFor({ timeout: 240000 }).then(() => true, () => false);
};

try {
  await page.goto("http://127.0.0.1:8780/", { waitUntil: "networkidle" });
  check("control room loads the use cases", await visible("Customer support") && await visible("Coding assistant"));
  await shot("01-control-room");

  await scenario("Escalation with SLA credits");
  check("a hard support request answers", await runAndWait());
  check("route trace shows the route and the criterion", await visible("decided by") && await page.locator("text=/REASONING|COMPLEX/").count() > 0);
  check("the OCI model that answered is shown", await page.locator("text=/gemini|grok|gpt|llama|o3/").count() > 0);
  await shot("02-escalation");

  await scenario("Japanese request");
  check("a Japanese request answers", await runAndWait());
  check("the language rule decided it", await visible("rule: language (ja)"));
  await shot("03-multilingual");

  await scenario("Read an invoice photo");
  check("an image request answers", await runAndWait());
  check("the image rule routed it to VISION", await visible("rule: image"));
  await shot("04-vision");

  await scenario("A deployment fails");
  check("the failing deployment still answers", await runAndWait());
  check("the trace shows the fallback", await visible("fallback ×"));
  await shot("05-fallback");

  await tab("Compare routers");
  await page.locator("button:has-text('Send to all three')").click();
  check("the three routers answer", await visible("Built-in heuristic", 240000) && (await page.getByText("right route", { exact: true }).count()) + (await page.getByText("different route", { exact: true }).count()) === 3);
  await shot("06-compare");

  await tab("The classifier");
  check("the classifier view shows held-out accuracy", await visible("unseen prompts"));
  check("the policy comparison is shown", await visible("always COMPLEX"));
  await shot("07-classifier");

  await tab("The gateway");
  check("the gateway view lists the routes", await visible("oci-multilingual") && await visible("Who classifies"));
  await shot("08-gateway");
} catch (err) {
  check("no exception", false, String(err).split("\n")[0]);
  await shot("error").catch(() => {});
}
await browser.close();
const passed = results.filter(Boolean).length;
console.log(`\n${passed === results.length ? "UI E2E OK" : "UI E2E FAILED"} (${passed}/${results.length})`);
process.exit(passed === results.length ? 0 : 1);
