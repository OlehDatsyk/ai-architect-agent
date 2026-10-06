// Screenshots and an accessibility audit of the running app (frontend on :5173 by default).
//
//   cd tools/visual-check && npm install && npm run check -- [base-url] [output-dir]
//
// Uses @sparticuz/chromium, a headless Chromium shipped inside an npm package, so it works on
// machines where browser downloads are blocked. Opens the first saved project, if there is one.
// Exits non-zero if axe-core finds accessibility violations or the page scrolls sideways.
import chromium from "@sparticuz/chromium";
import puppeteer from "puppeteer-core";
import { readFileSync, mkdirSync } from "node:fs";

const base = process.argv[2] ?? "http://127.0.0.1:5173";
const out = process.argv[3] ?? "screenshots";
mkdirSync(out, { recursive: true });
const axeSource = readFileSync(new URL("./node_modules/axe-core/axe.min.js", import.meta.url), "utf8");
const browser = await puppeteer.launch({ executablePath: await chromium.executablePath(), args: chromium.args, headless: true });
let problems = 0;

async function audit(page, label) {
  await page.evaluate(axeSource);
  const result = await page.evaluate(() => window.axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "best-practice"] }));
  console.log(`accessibility (${label}): ${result.violations.length} violation types`);
  for (const v of result.violations) console.log(`  [${v.impact}] ${v.id}: ${v.help} (${v.nodes.length})`);
  problems += result.violations.length;
}

for (const [label, viewport] of [["desktop", { width: 1440, height: 900 }], ["mobile", { width: 390, height: 844, isMobile: true, hasTouch: true }]]) {
  const page = await browser.newPage();
  await page.setViewport(viewport);
  await page.goto(base, { waitUntil: "networkidle0" });
  await page.waitForFunction(() => document.body.innerText.includes("Connected"), { timeout: 20000 });
  await page.screenshot({ path: `${out}/${label}-start.png` });
  await audit(page, `${label}, start`);
  const open = await page.$('button[aria-label^="Open "]');
  if (open) {
    await open.click();
    await page.waitForSelector("article");
    await page.waitForNetworkIdle({ idleTime: 500 });
    await page.screenshot({ path: `${out}/${label}-project.png`, fullPage: true });
    await audit(page, `${label}, project`);
  }
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  if (width > viewport.width) { console.log(`${label}: page scrolls sideways (${width}px)`); problems += 1; }
  await page.close();
}
await browser.close();
console.log(problems ? `${problems} problem(s) found` : "No problems found");
process.exit(problems ? 1 : 0);
