// Rivalry grid and Rivalry pages (#39). Expected values come from the invented fixtures
// (contract/examples/matchups.json, rivalries/*.json, owners/*.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
const read = (rel: string) => JSON.parse(fs.readFileSync(path.join(EXAMPLES, rel), "utf-8"));
const grid = read("matchups.json").rivalryGrid as {
  owners: { slug: string; name: string }[];
  records: { owner: string; opponent: string; wins: number; losses: number; ties: number }[];
};
const PAIRS = fs.readdirSync(path.join(EXAMPLES, "rivalries")).map((f) => f.replace(/\.json$/, ""));
const recordText = (r: { wins: number; losses: number; ties: number }) => (r.ties ? `${r.wins}-${r.losses}-${r.ties}` : `${r.wins}-${r.losses}`);
const rec = (r: { wins: number; losses: number; ties: number }) => `${r.wins}-${r.losses}-${r.ties}`;

test("desktop grid: one cell per pair and direction, linking to the Rivalry page", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "the matrix is the desktop layout");
  await page.goto("/matchups/");
  const cells = page.getByTestId("rivalry-grid").getByTestId("grid-cell");
  await expect(cells).toHaveCount(grid.records.length);
  const r = grid.records[0];
  const cell = page.locator(`[data-testid="grid-cell"][data-owner="${r.owner}"][data-opponent="${r.opponent}"]`);
  await expect(cell).toHaveText(recordText(r));
  await cell.click();
  await expect(page).toHaveURL(new RegExp(`/matchups/${[r.owner, r.opponent].sort().join("-vs-")}/$`));
  await expect(page.getByTestId("meetings")).toBeVisible();
});

test("phone picker: choosing an Owner shows that Owner's rivalries", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the picker is the phone layout");
  await page.goto("/matchups/");
  const section = page.getByTestId("rivalry-grid");
  await expect(section.getByRole("table", { name: "Rivalry grid" })).toBeHidden();
  const last = grid.owners[grid.owners.length - 1];
  await section.getByRole("combobox").selectOption(last.slug);
  const list = section.getByRole("list", { name: `${last.name}'s rivalries` });
  await expect(list).toBeVisible();
  const mine = grid.records.filter((r) => r.owner === last.slug);
  await expect(list.getByRole("listitem")).toHaveCount(mine.length);
  await expect(section.getByRole("list", { name: `${grid.owners[0].name}'s rivalries` })).toBeHidden();
});

for (const pair of PAIRS.slice(0, 6)) {
  test(`${pair}: the Rivalry page shows records, meetings and every game`, async ({ page }) => {
    const doc = read(`rivalries/${pair}.json`);
    await page.goto(`/matchups/${pair}/`);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(`${doc.sides[0].owner.name} vs ${doc.sides[1].owner.name}`);
    await expect(page.getByTestId("meetings")).toHaveText(String(doc.meetings));
    const sides = page.getByTestId("rivalry-side");
    for (const [i, s] of doc.sides.entries()) {
      await expect(sides.nth(i)).toContainText(rec(s.regularSeason));
      await expect(sides.nth(i)).toContainText(rec(s.playoffs));
    }
    const games = page.getByTestId("rivalry-game");
    await expect(games).toHaveCount(doc.games.length);
    const notInRecord = doc.games.filter((g: { inRecord: boolean }) => !g.inRecord).length;
    await expect(page.locator('[data-testid="rivalry-game"][data-in-record="false"]')).toHaveCount(notInRecord);
  });
}

test("a pair with a Third-place or consolation game marks it not in the record", async ({ page }) => {
  const pair = PAIRS.find((p) => read(`rivalries/${p}.json`).games.some((g: { inRecord: boolean }) => !g.inRecord))!;
  await page.goto(`/matchups/${pair}/`);
  await expect(page.locator('[data-testid="rivalry-game"][data-in-record="false"]').first()).toContainText("not in record");
});

test("the Owner page's head-to-head rows link to the Rivalry page", async ({ page }) => {
  const slug = grid.owners[0].slug;
  const owner = read(`owners/${slug}.json`);
  await page.goto(`/owners/${slug}/`);
  const links = page.getByTestId("rivalry-link");
  await expect(links).toHaveCount(owner.headToHead.length);
  const opp = owner.headToHead[0].opponent.slug;
  await links.first().click();
  await expect(page).toHaveURL(new RegExp(`/matchups/${[slug, opp].sort().join("-vs-")}/$`));
  await expect(page.getByTestId("meetings")).toHaveText(String(owner.headToHead[0].meetings));
});

test("the grid and a Rivalry page fit the screen", async ({ page }, info) => {
  for (const [url, name] of [["/matchups/", "matchups-rivalries"], [`/matchups/${PAIRS[0]}/`, "rivalry-page"]]) {
    await page.goto(url);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `${url} is wider than the viewport`).toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(SHOTS, info.project.name, `${name}.png`), fullPage: true });
  }
});
