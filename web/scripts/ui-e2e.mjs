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
  check("the gateway in use is shown", await visible("gateway: primary") || await visible("gateway: fallback"));

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
  await page.locator("textarea").fill("Bonjour, comment puis-je télécharger ma facture du mois dernier ?");
  await page.locator("button:has-text('Route it')").click();
  check("a French request is explained by the language rule", await visible("written in French", 300000));
  await shot("00-ask-french");

  await tab("Control room");
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

  await tab("Classifier");
  check("the classifier view shows held-out quality and cost", await visible("unseen prompts") && await visible("always the reasoning models"));
  check("the dial shows every quality bar", await visible("Every quality bar"));
  await shot("07-classifier");

  await tab("Gateway");
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
