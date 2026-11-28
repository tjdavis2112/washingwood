// Hall of Fame (#73, #74): Inductee cards grouped by Season, newest first. Expected values come from the invented
// fixture (contract/examples/hall-of-fame.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
const { inductees } = JSON.parse(fs.readFileSync(path.join(EXAMPLES, "hall-of-fame.json"), "utf-8"));
const pts = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
// Each lane's badge label and how its value is written: Points over expected is whole points
const LANES: Record<string, { label: string; value: (v: number) => string }> = {
  dominant: { label: "Dominant", value: (v) => `+${pts(v)}` },
  overachiever: { label: "Overachiever", value: (v) => `+${v}` },
  waiver_legend: { label: "Waiver legend", value: (v) => `+${pts(v)}` },
};

test("the Hall of Fame nav link opens the section, which explains how Players get in", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("link", { name: "Hall of Fame" }).click();
  await expect(page).toHaveURL(/\/hall-of-fame\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Hall of Fame");
  await expect(page.getByText("Coming soon", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("induction-note")).toContainText("fixed bar");
  for (const measure of ["Points above replacement", "Points over expected", "Value added"]) {
    await expect(page.getByTestId("induction-note")).toContainText(measure);
  }
});

test("every Inductee is a gold card, grouped by Season newest first", async ({ page }, info) => {
  await page.goto("/hall-of-fame/");
  const years = [...new Set(inductees.map((i: { year: number }) => i.year))];
  expect(years).toEqual([...years].sort((a, b) => Number(b) - Number(a)));
  const groups = page.getByTestId("inductee-season");
  await expect(groups).toHaveCount(years.length);
  for (const [n, y] of years.entries()) {
    await expect(groups.nth(n)).toHaveAttribute("data-year", String(y));
    await expect(groups.nth(n).getByRole("heading", { level: 2 }).getByRole("link")).toHaveAttribute("href", `/seasons/${y}/`);
  }

  const cards = page.getByTestId("inductee-card");
  await expect(cards).toHaveCount(inductees.length);
  for (const [n, i] of inductees.entries()) {
    const card = cards.nth(n);
    await expect(card).toHaveAttribute("data-year", String(i.year));
    await expect(card.getByRole("link", { name: String(i.year), exact: true })).toHaveAttribute("href", `/seasons/${i.year}/`);
    await expect(card.getByTestId("format-badge")).toHaveText(i.scoringFormat);
    await expect(card.getByTestId("inductee-name")).toHaveText(i.name);
    await expect(card.getByTestId("inductee-position")).toHaveText(i.nflTeam ? `${i.position} · ${i.nflTeam}` : i.position);
    await expect(card.getByRole("link", { name: i.owner.name })).toHaveAttribute("href", `/owners/${i.owner.slug}/`);
    await expect(card).toContainText(i.teamName);
    const lanes = card.getByTestId("inductee-lane");
    await expect(lanes).toHaveCount(i.lanes.length);
    for (const [k, lane] of i.lanes.entries()) {
      await expect(lanes.nth(k)).toHaveAttribute("data-lane", lane.lane);
      await expect(lanes.nth(k)).toContainText(LANES[lane.lane].label);
      await expect(lanes.nth(k).getByTestId("lane-value")).toHaveText(LANES[lane.lane].value(lane.value));
    }
    // No Season points in the Archive (a Waiver legend can have none): a dash for points and finish
    await expect(card.getByTestId("inductee-points")).toHaveText(i.points === null ? "—" : pts(i.points));
    await expect(card.getByTestId("inductee-finish")).toHaveText(i.positionalFinish === null ? "—" : `${i.position}${i.positionalFinish}`);
    // Plain gold border, no effects yet (#76)
    const border = await card.evaluate((el) => getComputedStyle(el).borderTopColor);
    expect(border).toBe("rgb(212, 175, 55)");
  }

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
  await page.screenshot({ path: path.join(SHOTS, `hall-of-fame-${info.project.name}.png`), fullPage: true });
});

test("a multi-lane card shows every badge inside the card, credited to its first lane's Owner", async ({ page }, info) => {
  await page.goto("/hall-of-fame/");
  const multi = inductees.filter((i: { lanes: unknown[] }) => i.lanes.length > 1);
  expect(multi.length, "the example has multi-lane Inductees").toBeGreaterThan(0);
  const cards = page.getByTestId("inductee-card");
  for (const i of multi) {
    const card = cards.filter({ has: page.getByTestId("inductee-name").getByText(i.name, { exact: true }) });
    await expect(card).toHaveCount(1);
    await expect(card.getByRole("link", { name: i.owner.name })).toHaveAttribute("href", `/owners/${i.lanes[0].owner.slug}/`);
    const box = (await card.boundingBox())!;
    const badges = card.getByTestId("inductee-lane");
    await expect(badges).toHaveCount(i.lanes.length);
    for (let k = 0; k < i.lanes.length; k++) {
      await expect(badges.nth(k)).toBeVisible();
      const b = (await badges.nth(k).boundingBox())!;
      expect(b.x, `${i.name} badge ${k} spills left`).toBeGreaterThanOrEqual(box.x);
      expect(b.x + b.width, `${i.name} badge ${k} spills right`).toBeLessThanOrEqual(box.x + box.width + 0.5);
    }
  }
  // A two-lane card whose lanes name different Owners
  const split = multi.find((i: { lanes: { owner: { slug: string } }[] }) => new Set(i.lanes.map((l) => l.owner.slug)).size > 1);
  expect(split, "the example has a two-lane Inductee whose lanes name different Owners").toBeTruthy();
  const card = cards.filter({ has: page.getByTestId("inductee-name").getByText(split.name, { exact: true }) });
  await card.scrollIntoViewIfNeeded();
  await card.screenshot({ path: path.join(SHOTS, `hall-of-fame-multi-lane-${info.project.name}.png`) });
});

test("every link on the Hall of Fame page resolves", async ({ page }) => {
  await page.goto("/hall-of-fame/");
  const hrefs = await page.locator("main a[href^='/']").evaluateAll((as) => [...new Set(as.map((a) => a.getAttribute("href")!))]);
  expect(hrefs.length).toBeGreaterThan(0);
  for (const href of hrefs) {
    const res = await page.request.get(href);
    expect(res.status(), href).toBe(200);
  }
});

// The card back (#75): moments for the credited Owner's team, the other lanes' Owners, and the Owner's note or
// its placeholder. It sits below the front with no flip yet (#76).
type Moments = {
  bestWeek: { week: number; points: number; opponent: { slug: string; name: string }; result: "win" | "loss" | "tie" } | null;
  playoffPoints: number | null; championshipPoints: number | null;
  finish: { finalRank: number; playoffSeed: number; madePlayoffs: boolean }; weeksStarted: number;
};
const ord = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
const bestWeek = (b: Moments["bestWeek"]) =>
  b === null ? "—" : `${pts(b.points)} in Week ${b.week}, ${{ win: "a win over", loss: "a loss to", tie: "a tie with" }[b.result]} ${b.opponent.name}`;
const finish = ({ finalRank, playoffSeed, madePlayoffs }: Moments["finish"]) =>
  ({ 1: "Champion", 2: "Runner-up", 3: "3rd place" } as Record<number, string>)[finalRank] ??
  (madePlayoffs ? `Playoffs, No. ${playoffSeed} seed` : `Missed the playoffs, ${ord(playoffSeed)} in the regular season`);
const playoffs = (m: Moments) =>
  m.playoffPoints === null ? "—" : `${pts(m.playoffPoints)}${m.championshipPoints === null ? "" : ` (${pts(m.championshipPoints)} in the final)`}`;

test("every card back shows its moments, the other lanes' Owners and the Owner's note or its placeholder", async ({ page }, info) => {
  await page.goto("/hall-of-fame/");
  const cards = page.getByTestId("inductee-card");
  for (const [n, i] of inductees.entries()) {
    const back = cards.nth(n).getByTestId("card-back");
    await expect(back).toBeVisible();
    const m: Moments = i.moments;
    await expect(back.getByTestId("moment-best-week")).toHaveText(bestWeek(m.bestWeek));
    if (m.bestWeek) await expect(back.getByTestId("moment-best-week").getByRole("link")).toHaveAttribute("href", `/owners/${m.bestWeek.opponent.slug}/`);
    await expect(back.getByTestId("moment-playoffs")).toHaveText(playoffs(m));
    await expect(back.getByTestId("moment-finish")).toHaveText(finish(m.finish));
    await expect(back.getByTestId("moment-weeks-started")).toHaveText(String(m.weeksStarted));
    // The other lanes' Owners: every lane crediting someone else, by lane
    const others = i.lanes.filter((l: { owner: { slug: string } }) => l.owner.slug !== i.owner.slug);
    const rows = back.getByTestId("other-owner");
    await expect(rows).toHaveCount(others.length);
    for (const [k, lane] of others.entries()) {
      await expect(rows.nth(k)).toHaveText(`${LANES[lane.lane].label}: ${lane.owner.name}`);
      await expect(rows.nth(k).getByRole("link")).toHaveAttribute("href", `/owners/${lane.owner.slug}/`);
    }
    if (i.ownerNote === null) {
      await expect(back.getByTestId("owner-note")).toHaveCount(0);
      await expect(back.getByTestId("owner-note-placeholder")).toHaveText("Owner's note coming soon");
    } else {
      await expect(back.getByTestId("owner-note")).toContainText(i.ownerNote);
      await expect(back.getByTestId("owner-note")).toContainText(i.owner.name);
      await expect(back.getByTestId("owner-note-placeholder")).toHaveCount(0);
    }
    // Inside the card, below the front
    const card = (await cards.nth(n).boundingBox())!;
    const box = (await back.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(card.x);
    expect(box.x + box.width).toBeLessThanOrEqual(card.x + card.width + 0.5);
    const front = (await cards.nth(n).getByTestId("inductee-lane").last().boundingBox())!;
    expect(box.y, `${i.name}: the back sits below the front`).toBeGreaterThan(front.y + front.height);
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);

  // One card with a note and other lanes' Owners, one with the placeholder
  const noted = inductees.find((i: { ownerNote: string | null }) => i.ownerNote !== null);
  const pending = inductees.find((i: { ownerNote: string | null; lanes: unknown[] }) => i.ownerNote === null && i.lanes.length > 1);
  expect(noted && pending, "the example has a card with a note and a multi-lane card without one").toBeTruthy();
  for (const [label, i] of [["note", noted], ["placeholder", pending]] as const) {
    const card = cards.filter({ has: page.getByTestId("inductee-name").getByText(i.name, { exact: true }) });
    await card.scrollIntoViewIfNeeded();
    await card.screenshot({ path: path.join(SHOTS, `hall-of-fame-card-back-${label}-${info.project.name}.png`) });
  }
});
