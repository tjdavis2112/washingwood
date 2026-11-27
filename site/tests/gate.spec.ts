// The passphrase gate (ADR-0006), seen from a browser with no cookie.
import path from "node:path";
import { expect, request, test } from "@playwright/test";
import { OTHER_SESSION_KEY, PASSPHRASE, ROTATED_PASSPHRASE, SESSION_KEY, signIn } from "./gate-config";
import { type Server, portsFor, startServer } from "./servers";

test.use({ storageState: { cookies: [], origins: [] } });

test.describe("without the cookie", () => {
  test("pages redirect to the landing screen", async ({ page }) => {
    for (const path of ["/", "/seasons/", "/seasons/2020/", "/owners/", "/no-such-page/"]) {
      await page.goto(path);
      await expect(page, path).toHaveURL(/\/enter\/$/);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText("Washingwood Fantasy Football");
    }
  });

  test("site data, images and built assets are refused", async ({ request }) => {
    for (const path of ["/league.json", "/data/league.json", "/images/punishment.jpg", "/_astro/anything.css", "/_astro/x.js"]) {
      const res = await request.get(path, { maxRedirects: 0 });
      expect(res.status(), path).toBe(401);
    }
  });

  test("the landing screen carries no league data and no nav", async ({ page }) => {
    await page.goto("/enter/");
    await expect(page.locator("body")).not.toContainText("Ines Dorrow");
    await expect(page.getByRole("navigation")).toHaveCount(0);
  });

  test("robots.txt is served and disallows everything", async ({ request }) => {
    const res = await request.get("/robots.txt");
    expect(res.status()).toBe(200);
    expect(await res.text()).toMatch(/User-agent: \*\s+Disallow: \//);
  });
});

test("every response carries noindex, no-framing and no-shared-cache headers", async ({ request, page }) => {
  const anon = [
    await request.get("/enter/"),
    await request.get("/", { maxRedirects: 0 }),
    await request.get("/_astro/x.js"),
    await request.get("/robots.txt"),
    await request.post("/enter/", { form: { passphrase: "nope" }, maxRedirects: 0 }),
  ];
  await signIn(page, PASSPHRASE);
  const authed = [await page.request.get("/seasons/"), await page.request.get("/no-such-page/")];
  expect(authed.map((r) => r.status())).toEqual([200, 404]);

  for (const res of [...anon, ...authed]) {
    const h = res.headers();
    expect(h["x-robots-tag"], res.url()).toBe("noindex, nofollow");
    expect(h["x-frame-options"], res.url()).toBe("DENY");
    expect(h["content-security-policy"], res.url()).toContain("frame-ancestors 'none'");
    expect(h["cache-control"], res.url()).toMatch(/private/);
  }
});

test("a wrong passphrase shows a clear error and sets no cookie", async ({ page }) => {
  await signIn(page, "definitely not it");
  await expect(page.getByRole("alert")).toHaveText("That passphrase isn't right. Try again.");
  expect(await page.context().cookies()).toEqual([]);
  await page.goto("/");
  await expect(page).toHaveURL(/\/enter\/$/);
});

test("the right passphrase sets a year-long, locked-down cookie and opens Home", async ({ page }) => {
  await signIn(page, PASSPHRASE);
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("region", { name: "Champion" })).toContainText("Ines Dorrow");

  const [cookie] = await page.context().cookies();
  // __Host- prefix: browsers only accept it Secure, Path=/ and with no Domain, so a subdomain can't plant one
  expect(cookie.name.startsWith("__Host-")).toBe(true);
  expect(cookie).toMatchObject({ httpOnly: true, secure: true, sameSite: "Lax", path: "/" });
  const days = (cookie.expires - Date.now() / 1000) / 86400;
  expect(days).toBeGreaterThan(360);
  expect(days).toBeLessThan(370);
  expect(cookie.value).not.toContain(PASSPHRASE);
});

test.describe("when the secrets change", () => {
  test.describe.configure({ mode: "serial" });
  let rotated: Server, otherKey: Server, noKey: Server;

  test.beforeAll(async ({}, info) => {
    test.setTimeout(120_000);
    const [a, b, c] = portsFor(info.project.name);
    // Same build, different Cloudflare secrets
    [rotated, otherKey, noKey] = await Promise.all([
      startServer(a, { SITE_PASSPHRASE: ROTATED_PASSPHRASE, SESSION_KEY }),
      startServer(b, { SITE_PASSPHRASE: PASSPHRASE, SESSION_KEY: OTHER_SESSION_KEY }),
      startServer(c, { SITE_PASSPHRASE: PASSPHRASE }),
    ]);
  });

  test.afterAll(() => {
    for (const s of [rotated, otherKey, noKey]) s?.stop();
  });

  const asBrowser = (cookie: string) => ({ headers: { cookie, accept: "text/html" }, maxRedirects: 0 });

  test("rotating the passphrase rejects existing cookies; only the new passphrase works", async ({ page }) => {
    await signIn(page, PASSPHRASE); // cookie issued under the old passphrase
    const [old] = await page.context().cookies();

    const ctx = await request.newContext({ baseURL: rotated.url });
    const withOld = await ctx.get("/", asBrowser(`${old.name}=${old.value}`));
    expect(withOld.status()).toBe(302);
    expect(withOld.headers()["location"]).toMatch(/\/enter\/$/);

    expect((await ctx.post("/enter/", { form: { passphrase: PASSPHRASE }, maxRedirects: 0 })).status()).toBe(401);
    const newPhrase = await ctx.post("/enter/", { form: { passphrase: ROTATED_PASSPHRASE }, maxRedirects: 0 });
    expect(newPhrase.status()).toBe(303);

    // Control: a cookie issued under the new secret does get in
    const fresh = newPhrase.headers()["set-cookie"].split(";")[0];
    expect((await ctx.get("/", asBrowser(fresh))).status()).toBe(200);
  });

  test("the cookie depends on SESSION_KEY, not only the passphrase", async ({ page }) => {
    // Same passphrase, different SESSION_KEY: a different cookie, and each server rejects the other's.
    // So a stolen cookie can't be used to guess the passphrase offline without SESSION_KEY.
    await signIn(page, PASSPHRASE);
    const [mine] = await page.context().cookies();

    const ctx = await request.newContext({ baseURL: otherKey.url });
    const theirs = await ctx.post("/enter/", { form: { passphrase: PASSPHRASE }, maxRedirects: 0 });
    expect(theirs.status()).toBe(303);
    const theirCookie = theirs.headers()["set-cookie"].split(";")[0];

    expect(theirCookie).not.toBe(`${mine.name}=${mine.value}`);
    expect((await ctx.get("/", asBrowser(`${mine.name}=${mine.value}`))).status()).toBe(302);
    expect((await page.request.get("/", asBrowser(theirCookie))).status()).toBe(302);
  });

  test("a missing SESSION_KEY fails closed", async () => {
    const ctx = await request.newContext({ baseURL: noKey.url });
    for (const res of [
      await ctx.get("/", { maxRedirects: 0 }),
      await ctx.get("/enter/"),
      await ctx.post("/enter/", { form: { passphrase: PASSPHRASE }, maxRedirects: 0 }),
    ]) {
      expect(res.status(), res.url()).toBe(503);
      expect(res.headers()["set-cookie"]).toBeUndefined();
    }
  });
});

test("the landing screen fits the screen, before and after a wrong passphrase", async ({ page }, info) => {
  const shots = path.resolve(import.meta.dirname, "../test-results/screenshots", info.project.name);
  for (const [name, wrong] of [["enter", false], ["enter-error", true]] as const) {
    if (wrong) {
      await signIn(page, "definitely not it");
      await expect(page.getByRole("alert")).toBeVisible();
    } else {
      await page.goto("/enter/");
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
    await expect(page.getByRole("button", { name: "Enter" })).toBeInViewport();
    await page.screenshot({ path: path.join(shots, `${name}.png`), fullPage: true });
  }
});
