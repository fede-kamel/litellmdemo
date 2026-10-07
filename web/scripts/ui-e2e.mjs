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
const sub = (label) => page.locator(`main button:has-text("${label}")`).first().click();
const runUseCase = async (title) => {
  await page.locator(`button:has-text("${title}")`).first().click();
  await page.locator("button:has-text('Route it')").click();
  await page.waitForTimeout(800);
  await page.waitForFunction(() => { const b = [...document.querySelectorAll("button")].find((x) => x.textContent.includes("Route it")); return b && !b.disabled; }, null, { timeout: 300000 });
};
const runAndWait = async () => {
  await page.locator("button:has-text('Run through the gateway')").click();
  return page.locator("text=/Answer ·/").first().waitFor({ timeout: 240000 }).then(() => true, () => false);
};

try {
  await page.goto("http://127.0.0.1:8780/", { waitUntil: "networkidle" });
  check("the gateway in use is shown", await visible("gateway: primary") || await visible("gateway: fallback"));
  check("the OCI session countdown is shown", await visible("OCI session"));

  // Ask and explain: any prompt, in the OpenShell sandbox, through LiteLLM, and why
  check("the three stages are shown", await visible("OpenShell sandbox") && await visible("LiteLLM AI Gateway") && await visible("OCI Generative AI"));
  await page.locator("textarea").fill("Draft a short, polite reply to a customer who was charged twice in September, explaining the refund steps.");
  await page.locator("button:has-text('Route it')").click();
  check("a typed request is answered", await visible("The answer", 300000));
  check("LiteLLM's key check names the agent's virtual key", await visible("openshell-agent"));
  check("the sandbox's network decisions are shown", await visible("ALLOWED POST", 30000));
  check("the route is explained from LiteLLM's decision", await visible("decided inside LiteLLM") && await visible("likely", 30000) && await visible("Where that", 30000));
  await page.locator("button:has-text('Show the details')").click();
  check("the details show every check and precedent", await visible("Image rule") && await visible("Most similar requests") && await page.locator("text=/similarity 0\\.\\d\\d/").count() >= 3);
  await shot("00-ask");
  await page.locator("button:has-text('Try to escape')").click();
  check("the sandbox refuses OCI, a vendor and the admin API", await visible("REFUSED", 120000) && (await page.locator("text=/REFUSED/").count()) >= 3);
  await shot("00-ask-escape");
  check("the console streams LiteLLM and OpenShell lines", await page.locator("text=/key=openshell-agent|ALLOWED/").count() > 0 || await visible("route=", 20000));
  await page.locator("button:has-text('sample: an invoice photo')").click();
  await page.locator("img[alt='attached']").waitFor({ timeout: 15000 });
  await page.locator("button:has-text('Route it')").click();
  check("an attached image is routed by the image rule", await visible("carries an image", 300000));
  await shot("00-ask-image");
  await page.locator("button[title='remove the image']").click();
  await page.locator("textarea").fill("Bonjour, comment puis-je télécharger ma facture du mois dernier ?");
  await page.locator("button:has-text('Route it')").click();
  check("a French request is explained by the language rule", await visible("written in French", 300000));
  await shot("00-ask-french");

  // the use cases, from their chips on the same screen
  check("the use cases are on the demo screen", await visible("Use cases:") && await visible("Customer support") && await visible("Coding assistant"));
  await runUseCase("Escalation with SLA credits");
  check("a hard support request answers, with every model call", await visible("This run") && await page.locator("text=/model calls?, each routed by LiteLLM/").count() > 0);
  check("the route map shows the route", await page.locator("svg text").filter({ hasText: /SIMPLE|MEDIUM|REASONING/ }).count() > 0);
  await shot("02-escalation");
  await page.locator("section").filter({ hasText: "each routed by LiteLLM" }).first().screenshot({ path: `${out}/02-this-run.png` });
  await runUseCase("Escalation, end to end");
  check("the multi-step agent plans, then routes every task", await visible("tasks, each routed by LiteLLM on its own", 300000)
    && await page.locator('[data-testid="plan"] li').count() >= 3);
  await shot("06-plan");
  await page.locator("section").filter({ hasText: "each routed by LiteLLM on its own" }).first().screenshot({ path: `${out}/06-plan-panel.png` });
  await runUseCase("Japanese request");
  check("the language rule decided the Japanese request", await visible("written in Japanese", 30000));
  await shot("03-multilingual");
  await runUseCase("Read an invoice photo");
  check("the image rule routed the invoice photo", await visible("carries an image", 30000));
  await shot("04-vision");
  await runUseCase("A deployment fails");
  check("the failing deployment still answers, through a fallback", await visible("fallback ×", 30000));
  await shot("05-fallback");

  await tab("Under the hood");
  await sub("Compare routers");
  await page.locator("button:has-text('Send to all three')").click();
  check("the three routers answer", await visible("Built-in heuristic", 240000) && (await page.getByText("right route", { exact: true }).count()) + (await page.getByText("different route", { exact: true }).count()) === 3);
  await shot("06-compare");
  // for the deck: the three routers' answers, without the header and the console
  await page.screenshot({ path: `${out}/06-compare-crop.png`, clip: { x: 0, y: 60, width: 1600, height: 745 } });

  await sub("The classifier");
  check("the classifier view shows held-out quality and cost", await visible("unseen prompts") && await visible("always the reasoning models"));
  check("the dial shows every quality bar", await visible("Every quality bar"));
  await shot("07-classifier");

  await sub("The gateway");
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
