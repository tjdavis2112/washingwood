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
  { id: "season-most-bench-points", key: "mostBenchPoints", value: (r: any) => pts(r.benchPoints) },
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
  { label: "Bench points", stat: "bench-points", sort: (r: any) => r.benchPoints ?? -1, show: (r: any) => (r.benchPoints === null ? "—" : pts(r.benchPoints)) },
  { label: "Win streak", stat: "win-streak", sort: (r: any) => r.longestWinStreak, show: (r: any) => String(r.longestWinStreak) },
  { label: "Loss streak", stat: "loss-streak", sort: (r: any) => r.longestLossStreak, show: (r: any) => String(r.longestLossStreak) },
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
      // Rank, Owner and the picked stat; desktop also shows Seasons and the other seven stats
      await expect(row.locator("td:visible")).toHaveCount(info.project.name === "desktop" ? 11 : 3);
    }
  }
});

// One test per hash: goto() with only the hash changed doesn't reload the page
for (const hash of ["week-most-bench-points", "season-most-points-for", "all-time", "streaks"]) {
  test(`#${hash} fits the screen with its chips in view`, async ({ page }, info) => {
    await page.goto(`/record-book/#${hash}`);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `#${hash} is wider than the viewport`).toBeLessThanOrEqual(0);
    // The chip row isn't hidden under the sticky header when a link opens the page part-way down
    if (hash !== "streaks") {
      const chips = page.locator(hash === "all-time" ? "[data-stat-button]" : "[data-record-chip]:visible").first();
      await expect(chips).toBeInViewport();
      const header = (await page.locator("header").first().boundingBox())!;
      expect((await chips.boundingBox())!.y).toBeGreaterThanOrEqual(header.y + header.height);
    }
    await page.screenshot({ path: path.join(SHOTS, info.project.name, `record-book-${hash}.png`), fullPage: true });
  });
}

// Week records (#52)
const WEEK = [
  { id: "week-most-points-in-loss", key: "mostPointsInLoss", value: (r: any) => pts(r.team.score) },
  { id: "week-fewest-points-in-win", key: "fewestPointsInWin", value: (r: any) => pts(r.team.score) },
  { id: "week-most-bench-points", key: "mostBenchPoints", value: (r: any) => pts(r.benchPoints) },
];
const RESULT: Record<string, string> = { win: "W", loss: "L", tie: "T" };
const boxPath = (r: any) => `/matchups/${r.year}/${r.week}/${[r.team.owner.slug, r.opponent.owner.slug].sort().join("-vs-")}/`;

for (const rec of WEEK) {
  test(`#${rec.id} opens the Week tab on that record`, async ({ page }) => {
    await page.goto(`/record-book/#${rec.id}`);
    await expect(page.getByRole("tab", { name: "Week", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(`[data-record-chip="${rec.id}"]`)).toHaveAttribute("aria-current", "true");
    await expect(page.getByTestId("week-record").filter({ visible: true })).toHaveCount(1);
    const expected = book.week[rec.key];
    const rows = page.locator(`#${rec.id}`).getByTestId("week-record-row");
    await expect(rows).toHaveCount(expected.length);
    for (const [i, r] of expected.entries()) {
      const row = rows.nth(i);
      await expect(row.getByRole("link", { name: String(r.year), exact: true })).toHaveAttribute("href", `/seasons/${r.year}/`);
      await expect(row.getByRole("rowheader")).toContainText(`Week ${r.week}`);
      await expect(row.getByRole("link", { name: r.team.owner.name, exact: true })).toHaveAttribute("href", `/owners/${r.team.owner.slug}/`);
      await expect(row.getByRole("link", { name: r.opponent.owner.name, exact: true })).toHaveAttribute("href", `/owners/${r.opponent.owner.slug}/`);
      await expect(row.getByTestId("record-value")).toHaveText(rec.value(r));
      const box = row.getByTestId("box-score-link");
      await expect(box).toHaveText(`${RESULT[r.result]} ${pts(r.team.score)}–${pts(r.opponent.score)}`);
      await expect(box).toHaveAttribute("href", boxPath(r));
      await expect(row.getByTestId("format-badge")).toHaveText(r.scoringFormat);
    }
  });
}

test("a Week row's Box score link opens that Box score", async ({ page }) => {
  const r = book.week.mostPointsInLoss[0];
  await page.goto("/record-book/#week-most-points-in-loss");
  await page.locator("#week-most-points-in-loss").getByTestId("box-score-link").first().click();
  await expect(page).toHaveURL(new RegExp(`${boxPath(r)}$`));
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText(r.team.owner.name).first()).toBeVisible();
});

for (const [tab, label] of [["highest", "Highest scores"], ["lowest", "Lowest scores"], ["blowouts", "Blowouts"], ["closest", "Closest games"], ["upsets", "Playoff upsets"]]) {
  test(`the Week tab links to the Matchups ${label} leaderboard`, async ({ page }) => {
    await page.goto("/record-book/#week");
    await page.getByTestId("matchups-links").getByRole("link", { name: label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/matchups/#${tab}$`));
    await expect(page.getByRole("tab", { name: label, exact: true })).toHaveAttribute("aria-selected", "true");
  });
}

// Streaks (#53)
const spot = (w: { year: number; week: number }) => `${w.year} \u00b7 Wk ${w.week}`;

test("#streaks opens the tab with the longest winning and losing Streaks", async ({ page }) => {
  await page.goto("/record-book/#streaks");
  await expect(page.getByRole("tab", { name: "Streaks", exact: true })).toHaveAttribute("aria-selected", "true");
  for (const kind of ["wins", "losses"]) {
    const expected = book.streaks[kind];
    const rows = page.getByTestId(`streaks-${kind}`).getByTestId("streak-row");
    await expect(rows).toHaveCount(expected.length);
    for (const [i, r] of expected.entries()) {
      const row = rows.nth(i);
      await expect(row.getByRole("link", { name: r.owner.name, exact: true })).toHaveAttribute("href", `/owners/${r.owner.slug}/`);
      await expect(row.getByTestId("streak-length")).toHaveText(String(r.length));
      await expect(row.getByTestId("streak-start")).toHaveText(spot(r.start));
      await expect(row.getByTestId("streak-end")).toHaveText(spot(r.end));
      await expect(row.getByTestId("streak-active")).toHaveCount(r.active ? 1 : 0);
    }
  }
});

test("the two Streak tables sit side by side on desktop and stacked on a phone", async ({ page }, info) => {
  await page.goto("/record-book/#streaks");
  const wins = (await page.getByTestId("streaks-wins").boundingBox())!;
  const losses = (await page.getByTestId("streaks-losses").boundingBox())!;
  if (info.project.name === "desktop") expect(losses.x).toBeGreaterThan(wins.x + wins.width - 1);
  else expect(losses.y).toBeGreaterThanOrEqual(wins.y + wins.height);
  // Both fit the viewport, with every Active label in view (no sideways scrolling to find it)
  for (const box of [wins, losses]) expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  for (const label of await page.getByTestId("streak-active").all()) {
    const b = (await label.boundingBox())!;
    expect(b.x + b.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  }
});
