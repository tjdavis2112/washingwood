// The Record Book (#50): Last place history and tally. Expected values come from the invented
// fixture (contract/examples/record-book.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
const { lastPlace } = JSON.parse(fs.readFileSync(path.join(EXAMPLES, "record-book.json"), "utf-8"));
const pts = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const rec_ = (r: { wins: number; losses: number; ties: number }) => (r.ties ? `${r.wins}-${r.losses}-${r.ties}` : `${r.wins}-${r.losses}`);

test("the Record Book nav link opens the section, with the rule-change note", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("link", { name: "Record Book" }).click();
  await expect(page).toHaveURL(/\/record-book\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Record Book");
  await expect(page.getByText("Coming soon", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("rule-change-note")).toContainText("2020");
  await expect(page.getByTestId("rule-change-note")).toContainText("second FLEX");
  for (const name of ["Week", "Season", "All-time", "Streaks", "Last place"]) {
    await expect(page.getByRole("tab", { name, exact: true })).toBeVisible();
  }
});

test("#last-place opens the tab with every Season's Last place, newest first", async ({ page }) => {
  await page.goto("/record-book/#last-place");
  const tab = page.getByRole("tab", { name: "Last place" });
  await expect(tab).toHaveAttribute("aria-selected", "true");
  // On a phone the tab strip scrolls; the linked tab is scrolled fully into view
  const box = (await tab.boundingBox())!;
  expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  const rows = page.getByTestId("last-place-row");
  await expect(rows).toHaveCount(lastPlace.seasons.length);
  for (const [i, r] of lastPlace.seasons.entries()) {
    const row = rows.nth(i);
    await expect(row).toHaveAttribute("data-year", String(r.year));
    await expect(row.getByRole("link", { name: String(r.year), exact: true })).toHaveAttribute("href", `/seasons/${r.year}/`);
    await expect(row.getByRole("link", { name: r.owner.name })).toHaveAttribute("href", `/owners/${r.owner.slug}/`);
    await expect(row).toContainText(r.teamName);
    await expect(row).toContainText(rec_(r.record));
    await expect(row).toContainText(pts(r.pointsFor));
    await expect(row.getByTestId("format-badge")).toHaveText(r.scoringFormat);
  }
  const tally = page.getByTestId("tally-row");
  await expect(tally).toHaveCount(lastPlace.tally.length);
  for (const [i, t] of lastPlace.tally.entries()) {
    await expect(tally.nth(i).getByRole("link", { name: t.owner.name })).toBeVisible();
    await expect(tally.nth(i)).toContainText(t.years.join(", "));
    await expect(tally.nth(i)).toContainText(String(t.count));
  }
});

test("the Punishment link opens that Season's popup", async ({ page }) => {
  const r = lastPlace.seasons[0];
  await page.goto("/record-book/#last-place");
  await page.getByTestId("last-place-row").first().getByTestId("punishment-link").click();
  await expect(page).toHaveURL(new RegExp(`/seasons/${r.year}/#punishment-${r.year}$`));
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(`${r.year} · ${r.owner.name}`);
});

test("the tally sits beside the table on desktop and below it on a phone", async ({ page }, info) => {
  await page.goto("/record-book/#last-place");
  const table = await page.getByRole("table", { name: "Last place by Season" }).boundingBox();
  const tally = await page.getByTestId("last-place-tally").boundingBox();
  if (info.project.name === "desktop") expect(tally!.x).toBeGreaterThan(table!.x + table!.width - 1);
  else expect(tally!.y).toBeGreaterThanOrEqual(table!.y + table!.height);
});

test("the Record Book fits the screen", async ({ page }, info) => {
  await page.goto("/record-book/#last-place");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
  await page.screenshot({ path: path.join(SHOTS, info.project.name, "record-book-last-place.png"), fullPage: true });
});

// Season records and the All-time table (#51)
const book = JSON.parse(fs.readFileSync(path.join(EXAMPLES, "record-book.json"), "utf-8"));
const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
const RECORDS = [
  { id: "season-best-win-pct", key: "bestWinPct", value: (r: any) => pct(r.winPct) },
  { id: "season-worst-win-pct", key: "worstWinPct", value: (r: any) => pct(r.winPct) },
  { id: "season-most-points-for", key: "mostPointsFor", value: (r: any) => pts(r.pointsPerGame), total: (r: any) => pts(r.pointsFor) },
  { id: "season-fewest-points-for", key: "fewestPointsFor", value: (r: any) => pts(r.pointsPerGame), total: (r: any) => pts(r.pointsFor) },
  { id: "season-most-points-against", key: "mostPointsAgainst", value: (r: any) => pts(r.pointsAgainstPerGame), total: (r: any) => pts(r.pointsAgainst) },
];

for (const rec of RECORDS) {
  test(`#${rec.id} opens the Season tab on that record`, async ({ page }) => {
    await page.goto(`/record-book/#${rec.id}`);
    await expect(page.getByRole("tab", { name: "Season", exact: true })).toHaveAttribute("aria-selected", "true");
    const chip = page.locator(`[data-record-chip="${rec.id}"]`);
    await expect(chip).toHaveAttribute("aria-current", "true");
    // On a phone the chip row scrolls; the linked chip is scrolled fully into view
    const box = (await chip.boundingBox())!;
    expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width);
    await expect(page.getByTestId("season-record").filter({ visible: true })).toHaveCount(1);
    const section = page.locator(`#${rec.id}`);
    await expect(section).toBeVisible();
    const expected = book.season[rec.key];
    const rows = section.getByTestId("season-record-row");
    await expect(rows).toHaveCount(expected.length);
    for (const [i, r] of expected.entries()) {
      const row = rows.nth(i);
      await expect(row.getByRole("link", { name: String(r.year), exact: true })).toHaveAttribute("href", `/seasons/${r.year}/`);
      await expect(row.getByRole("link", { name: r.owner.name })).toHaveAttribute("href", `/owners/${r.owner.slug}/`);
      await expect(row).toContainText(r.teamName);
      await expect(row).toContainText(rec_(r.record));
      await expect(row.getByTestId("record-value")).toHaveText(rec.value(r));
      if (rec.total) await expect(row.getByTestId("record-total")).toHaveText(rec.total(r));
      await expect(row.getByTestId("format-badge")).toHaveText(r.scoringFormat);
    }
  });
}

test("picking a Season record chip shows it and updates the hash", async ({ page }) => {
  await page.goto("/record-book/#season");
  await expect(page.locator("#season-best-win-pct")).toBeVisible();
  await page.getByRole("link", { name: "Fewest points", exact: true }).click();
  await expect(page).toHaveURL(/#season-fewest-points-for$/);
  await expect(page.locator("#season-fewest-points-for")).toBeVisible();
  await expect(page.locator("#season-best-win-pct")).toBeHidden();
});

const ALL_TIME = [
  { label: "Wins", stat: "wins", sort: (r: any) => r.record.wins, show: (r: any) => rec_(r.record) },
  { label: "Win %", stat: "win-pct", sort: (r: any) => r.winPct, show: (r: any) => pct(r.winPct) },
  { label: "Points for", stat: "points-for", sort: (r: any) => r.pointsFor, show: (r: any) => pts(r.pointsFor) },
  { label: "Points per game", stat: "points-per-game", sort: (r: any) => r.pointsPerGame, show: (r: any) => pts(r.pointsPerGame) },
  { label: "Last places", stat: "last-places", sort: (r: any) => r.lastPlaces, show: (r: any) => String(r.lastPlaces) },
];

test("picking an All-time stat re-sorts the table; a phone shows only rank, Owner and that stat", async ({ page }, info) => {
  await page.goto("/record-book/#all-time");
  const rows = page.getByTestId("all-time-row");
  await expect(rows).toHaveCount(book.allTime.length);
  for (const s of ALL_TIME) {
    await page.getByRole("button", { name: s.label, exact: true }).click();
    await expect(page.getByRole("button", { name: s.label, exact: true })).toHaveAttribute("aria-pressed", "true");
    const expected = [...book.allTime].sort((a, b) => s.sort(b) - s.sort(a) || a.owner.name.localeCompare(b.owner.name));
    await expect(rows.locator("a")).toHaveText(expected.map((r) => r.owner.name));
    for (const [i, r] of expected.entries()) {
      const row = rows.nth(i);
      await expect(row.getByTestId("all-time-rank")).toHaveText(String(i + 1));
      await expect(row.locator(`[data-stat="${s.stat}"]`)).toHaveText(s.show(r));
      await expect(row.locator(`[data-stat="${s.stat}"]`)).toBeVisible();
      // Rank, Owner and the picked stat; desktop also shows Seasons and the other four stats
      await expect(row.locator("td:visible")).toHaveCount(info.project.name === "desktop" ? 8 : 3);
    }
  }
});

// One test per hash: goto() with only the hash changed doesn't reload the page
for (const hash of ["season-most-points-for", "all-time"]) {
  test(`#${hash} fits the screen with its chips in view`, async ({ page }, info) => {
    await page.goto(`/record-book/#${hash}`);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `#${hash} is wider than the viewport`).toBeLessThanOrEqual(0);
    // The chip row isn't hidden under the sticky header when a link opens the page part-way down
    const chips = page.locator(hash === "all-time" ? "[data-stat-button]" : "[data-record-chip]").first();
    await expect(chips).toBeInViewport();
    const header = (await page.locator("header").first().boundingBox())!;
    expect((await chips.boundingBox())!.y).toBeGreaterThanOrEqual(header.y + header.height);
    await page.screenshot({ path: path.join(SHOTS, info.project.name, `record-book-${hash}.png`), fullPage: true });
  });
}
