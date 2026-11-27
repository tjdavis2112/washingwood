// Season page: final standings, the Scoring format tab and the Coming soon tabs (#8; Draft since #25).
// Expected values come from the invented fixture documents the site is built from.
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const seasonDoc = (year: number) =>
  JSON.parse(fs.readFileSync(path.join(EXAMPLES, "seasons", `${year}.json`), "utf-8"));
const points = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const record = (r: { wins: number; losses: number; ties: number }) => `${r.wins}-${r.losses}-${r.ties}`;

for (const year of [2018, 2020]) {
  const doc = seasonDoc(year);

  test(`${year}: standings list every Franchise in final order with every column`, async ({ page }) => {
    await page.goto(`/seasons/${year}/`);
    const table = page.getByRole("table", { name: "Final standings" });
    await expect(table.getByRole("columnheader")).toHaveText(["#", "Owner", "Team", "W-L-T", "PF", "PA", "Seed"]);

    const rows = table.getByRole("row").filter({ has: page.getByRole("cell") });
    await expect(rows).toHaveCount(doc.teamCount);
    for (const [i, s] of doc.standings.entries()) {
      await expect(rows.nth(i).getByRole("cell")).toHaveText([
        String(s.rank),
        s.owner.name,
        s.teamName,
        record(s.record),
        points(s.pointsFor),
        points(s.pointsAgainst),
        String(s.playoffSeed),
      ]);
    }
  });

  test(`${year}: the Scoring format tab shows the label, key values and roster slots`, async ({ page }, info) => {
    await page.goto(`/seasons/${year}/`);
    await page.getByRole("tab", { name: "Scoring format" }).click();
    const panel = page.getByRole("tabpanel", { name: "Scoring format" });
    const sf = doc.scoringFormat;
    await expect(panel.getByRole("heading", { level: 2 })).toHaveText(sf.label);
    for (const kv of sf.keyValues) {
      await expect(panel.getByRole("row", { name: new RegExp(`^${kv.label}\\b`) })).toContainText(String(kv.points));
    }
    for (const slot of sf.rosterSlots) {
      await expect(panel.getByRole("listitem").filter({ hasText: slot.slot }).first()).toContainText(String(slot.count));
    }
    await expect(page).toHaveURL(/#scoring$/);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    const shots = path.resolve(import.meta.dirname, "../test-results/screenshots", info.project.name);
    await page.screenshot({ path: path.join(shots, `seasons-${year}-scoring.png`), fullPage: true });
  });
}

test("Rosters and Transactions tabs say Coming soon", async ({ page }) => {
  await page.goto("/seasons/2020/");
  await expect(page.getByRole("tab")).toHaveText(["Results", "Scoring format", "Rosters", "Draft", "Transactions"]);
  for (const name of ["Rosters", "Transactions"]) {
    await page.getByRole("tab", { name }).click();
    const panel = page.getByRole("tabpanel", { name });
    await expect(panel).toBeVisible();
    await expect(panel).toContainText("Coming soon");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("2020 Season");
    await expect(page.getByRole("table", { name: "Final standings" })).toBeHidden();
  }
});

test("tabs work from the keyboard and open from a link", async ({ page }) => {
  await page.goto("/seasons/2020/#scoring");
  await expect(page.getByRole("tab", { name: "Scoring format" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tabpanel", { name: "Scoring format" })).toBeVisible();

  await page.getByRole("tab", { name: "Scoring format" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Rosters" })).toBeFocused();
  await expect(page.getByRole("tab", { name: "Rosters" })).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Home");
  await expect(page.getByRole("tab", { name: "Results" })).toHaveAttribute("aria-selected", "true");
});

test("on a phone, the standings table scrolls inside its own box, not the page", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "phone-width behaviour");
  await page.goto("/seasons/2020/");
  const box = page.getByTestId("standings-scroll");
  const [scrollW, clientW] = await box.evaluate((el) => [el.scrollWidth, el.clientWidth]);
  expect(scrollW).toBeGreaterThan(clientW);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
