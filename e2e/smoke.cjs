/*
 * WebPuente browser smoke test (Playwright). It registers a throw-away account, walks through the whole workflow
 * (import, match, review, quality, export, logout/login) and DELETES the account at the end.
 *
 * Use:   npm install --no-save playwright && npx playwright install chromium
 *        E2E_BASE=http://localhost:5173 node e2e/smoke.cjs
 * Live:  E2E_BASE=https://YOUR-SITE.vercel.app node e2e/smoke.cjs   (creates and removes a test account on the live site)
 * Output: PASS/FAIL lines, screenshots + downloaded files in ./e2e/output (git-ignored). Exit code 1 if anything failed.
 */
const { chromium } = require("playwright");
const fs = require("fs");
const OUT = require("path").join(__dirname, "output");
fs.mkdirSync(OUT, { recursive: true });
const SHOTS = OUT;
const email = `e2e${Date.now()}@example.com`;
const PASS = "Correct-Horse-Battery-9";
const OLD = ["about", "contact", "products/running-shoes", "blog/best-running-shoes", "blog/trail-guide", "legacy/zzz-unrelated"].map((p) => `https://old.example.com/${p}`).join("\n");
const NEW = ["about", "contact-us", "shop/running-shoes", "journal/best-running-shoes-2024", "journal/trail-guide", ""].map((p) => `https://new.example.com/${p}`).join("\n");
const steps = [];
const seen = async (loc) => { try { await loc.first().waitFor({ timeout: 10000 }); return true; } catch { return false; } };
const ok = (name, cond, extra = "") => { steps.push([cond ? "PASS" : "FAIL", name, extra]); console.log(cond ? "PASS" : "FAIL", name, extra); };

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
  const page = await ctx.newPage();
  const consoleErrors = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("pageerror", (e) => consoleErrors.push("pageerror: " + e.message));
  const B = (process.env.E2E_BASE || "http://localhost:5173").replace(/\/+$/, "");
  const tab = (n) => page.getByRole("navigation", { name: "Project sections" }).getByRole("link", { name: n, exact: true });
  try {
    // guard: unauthenticated visit redirects to login
    await page.goto(B + "/projects");
    await page.waitForURL("**/login");
    ok("unauthenticated user is sent to login", true);

    // register
    await page.goto(B + "/register");
    await page.getByLabel("First name").fill("Ada");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(PASS);
    await page.getByLabel("Confirm password").fill(PASS);
    await page.getByRole("button", { name: "Create account" }).click();
    await page.waitForURL("**/dashboard");
    await page.getByText("No projects yet").waitFor();
    ok("register + land on dashboard", true);

    // reload keeps the session (refresh token flow)
    await page.reload();
    await page.waitForSelector("text=Dashboard");
    ok("session survives page reload", page.url().endsWith("/dashboard"));

    // create project
    await page.goto(B + "/projects");
    await page.getByRole("button", { name: "New project" }).first().click();
    await page.getByLabel("Project name").fill("E2E site move");
    await page.getByLabel("Old website address").fill("https://old.example.com");
    await page.getByLabel("New website address").fill("https://new.example.com");
    await page.getByRole("button", { name: "Create project" }).click();
    await page.waitForURL("**/import");
    ok("project created, redirected to import", true);

    // import old (paste)
    await page.getByLabel("…or paste URLs (one per line)").fill(OLD);
    await page.getByRole("button", { name: "Preview" }).click();
    await page.getByText("Check the columns").waitFor();
    await page.getByRole("button", { name: /Import 6 rows as old URLs/ }).click();
    await page.getByText("Import finished").waitFor();
    ok("old URLs imported (paste)", await page.getByText("6 added").isVisible());

    // import new via file upload
    fs.writeFileSync(SHOTS + "/new.csv", "URL,Title\n" + NEW.split("\n").map((u, i) => `${u},${["About us", "Contact", "Running shoes", "Best running shoes 2024", "Trail guide", "Home"][i]}`).join("\n") + "\n");
    await page.getByLabel("Which list is this?").selectOption("new");
    await page.setInputFiles("#file", SHOTS + "/new.csv");
    await page.getByRole("button", { name: "Preview" }).click();
    await page.getByText("Check the columns").waitFor();
    await page.getByRole("button", { name: /Import 6 rows as new URLs/ }).click();
    await page.getByText("6 added").waitFor();
    ok("new URLs imported (CSV upload with titles)", true);
    await page.screenshot({ path: SHOTS + "/01-import.png" });

    // analyze
    await tab("Overview").click();
    await page.getByRole("button", { name: "Find matches" }).click();
    await page.getByText("Match confidence").waitFor({ timeout: 30000 });
    ok("analysis finished and dashboard shows real counts", await page.getByText("Waiting for review").isVisible());
    await page.screenshot({ path: SHOTS + "/02-overview.png", fullPage: true });

    // review
    await tab("Review").click();
    await page.getByText("https://old.example.com/about").first().waitFor();
    const rowCount = await page.locator("tbody tr").count();
    ok("review lists 6 rows, none auto-approved", rowCount === 6 && (await page.locator("tbody").getByText("Approved", { exact: true }).count()) === 0, `rows=${rowCount}`);
    await page.getByLabel("Approve https://old.example.com/about").click();
    await page.getByText("Approved.").first().waitFor();
    ok("approve a row", await seen(page.locator("tbody tr", { hasText: "old.example.com/about" }).first().getByText("Approved", { exact: true })));

    // bulk approve
    await page.getByLabel("Select all rows on this page").check();
    await page.getByRole("button", { name: /Approve…/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Approve", exact: true }).click();
    await page.getByText(/updated/).first().waitFor();
    ok("bulk approve asked for confirmation and reported skips", true);

    // details panel
    await page.getByLabel("Select all rows on this page").uncheck().catch(() => {});
    await page.locator("tbody tr", { hasText: "zzz-unrelated" }).getByRole("button", { name: "Details" }).click();
    await page.getByRole("dialog").getByText("No destination yet").waitFor();
    await page.getByRole("button", { name: "Choose another destination…" }).click();
    await page.getByLabel("…or type any destination URL").fill("https://new.example.com/archive");
    await page.getByRole("button", { name: "Use", exact: true }).last().click();
    await page.getByText("Destination saved and approved.").waitFor();
    ok("manual destination assigned", true);
    await page.screenshot({ path: SHOTS + "/03-detail.png" });
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");

    // quality
    await tab("Quality").click();
    await page.getByRole("button", { name: /Run checks|Check again/ }).click();
    await page.getByText("Last checked").waitFor();
    await page.getByText(/You changed decisions/).waitFor({ state: "detached", timeout: 10000 });
    ok("quality checks ran and 'cannot know' list shown", await page.getByText("What these checks cannot tell you").isVisible());
    await page.screenshot({ path: SHOTS + "/04-quality.png", fullPage: true });

    // export csv + nginx
    await tab("Export").click();
    const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Create and download" }).click()]);
    const csvPath = SHOTS + "/" + dl.suggestedFilename();
    await dl.saveAs(csvPath);
    const csv = fs.readFileSync(csvPath, "utf8");
    ok("CSV downloaded with approved rows only", csv.includes("old.example.com/about") && csv.includes("new.example.com/archive"), dl.suggestedFilename());
    await page.getByLabel(/Nginx map/).check();
    const [dl2] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Create and download" }).click()]);
    await dl2.saveAs(SHOTS + "/" + dl2.suggestedFilename());
    ok("nginx map downloaded", fs.readFileSync(SHOTS + "/" + dl2.suggestedFilename(), "utf8").includes("map $request_uri"));
    await page.screenshot({ path: SHOTS + "/05-export.png", fullPage: true });

    // activity
    await tab("Activity").click();
    ok("audit log shows decisions", await seen(page.getByText("mapping.approved")));

    // persistence: new context logs in again and sees the same data
    await page.getByRole("button", { name: "Sign out" }).first().click();
    await page.waitForURL("**/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(PASS);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL("**/dashboard");
    ok("logout then login again; dashboard shows saved data", await seen(page.getByText("E2E site move")));
    await page.screenshot({ path: SHOTS + "/06-dashboard.png", fullPage: true });

    // wrong password message is generic
    await page.getByRole("button", { name: "Sign out" }).first().click();
    await page.waitForURL("**/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("wrong-password-123");
    await page.getByRole("button", { name: "Sign in" }).click();
    ok("wrong password shows a generic message", await seen(page.getByText("Incorrect email or password.")));

    // mobile viewport check
    await page.setViewportSize({ width: 390, height: 800 });
    await page.getByLabel("Password").fill(PASS);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL("**/dashboard");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    ok("no horizontal page scroll at phone width", !overflow);
    await page.screenshot({ path: SHOTS + "/07-mobile.png" });

    // clean up: delete the account via the UI
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(B + "/profile");
    await page.getByRole("button", { name: "Delete my account…" }).click();
    await page.getByRole("dialog").getByLabel("Password").fill(PASS);
    await page.getByRole("button", { name: "Delete everything" }).click();
    await page.waitForURL("**/login");
    ok("account deleted (cleanup)", true);
  } catch (e) {
    ok("UNEXPECTED ERROR", false, e.message.split("\n")[0]);
    await page.screenshot({ path: SHOTS + "/error.png", fullPage: true }).catch(() => {});
  }
  const relevant = consoleErrors.filter((t) => !/401|403|404|409|429|Failed to load resource/.test(t));
  ok("no unexpected browser console errors", relevant.length === 0, relevant.slice(0, 3).join(" | "));
  await browser.close();
  process.exit(steps.some((s) => s[0] === "FAIL") ? 1 : 0);
})();
