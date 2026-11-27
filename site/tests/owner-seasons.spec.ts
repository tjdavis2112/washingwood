// The Owner page's season-by-season table (#15). Expected values come from the invented fixture
// documents (contract/examples/owners/<slug>.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

type Row = {
  year: number;
  teamName: string;
  record: { wins: number; losses: number; ties: number };
  pointsFor: number;
  pointsAgainst: number;
  playoffSeed: number;
  finalRank: number;
  podiumPlace: 1 | 2 | 3 | null;
  isLastPlace: boolean;
};
type OwnerDoc = { owner: { slug: string; name: string }; seasons: Row[] };
const DIR = path.resolve(import.meta.dirname, "../../contract/examples/owners");
const OWNERS = fs.readdirSync(DIR).map((f) => JSON.parse(fs.readFileSync(path.join(DIR, f), "utf-8")) as OwnerDoc);

const points = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const ordinal = (n: number) =>
  `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
const MEDAL = { 1: "Champion", 2: "Runner-up", 3: "3rd place" } as const;
const finish = (r: Row) => (r.podiumPlace ? MEDAL[r.podiumPlace] : r.isLastPlace ? `${ordinal(r.finalRank)}Last place` : ordinal(r.finalRank));

test("the fixture has an Owner with both a Podium finish and a Last place", () => {
  expect(OWNERS.some((o) => o.seasons.some((s) => s.podiumPlace) && o.seasons.some((s) => s.isLastPlace))).toBe(true);
});

for (const o of OWNERS) {
  test(`${o.owner.slug}: every Season newest first, with finish markers and Season links`, async ({ page }) => {
    await page.goto(`/owners/${o.owner.slug}/`);
    const table = page.getByRole("table", { name: "Season by season" });
    const rows = table.locator("tbody tr");
    await expect(rows).toHaveCount(o.seasons.length);
    for (const [i, s] of o.seasons.entries()) {
      const cells = rows.nth(i).locator("th, td");
      await expect(cells).toHaveText([
        String(s.year),
        s.teamName,
        `${s.record.wins}-${s.record.losses}-${s.record.ties}`,
        points(s.pointsFor),
        points(s.pointsAgainst),
        String(s.playoffSeed),
        finish(s),
      ]);
      await expect(rows.nth(i).getByRole("link", { name: String(s.year) })).toHaveAttribute("href", `/seasons/${s.year}/`);
    }
  });
}

test("a Season link opens that Season page", async ({ page }) => {
  const o = OWNERS.find((x) => x.seasons.length > 1)!;
  const s = o.seasons[o.seasons.length - 1];
  await page.goto(`/owners/${o.owner.slug}/`);
  await page.getByRole("table", { name: "Season by season" }).getByRole("link", { name: String(s.year) }).click();
  await expect(page).toHaveURL(new RegExp(`/seasons/${s.year}/$`));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(`${s.year} Season`);
});

test("on a phone, the season table scrolls inside its own box, not the page", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "phone-width behaviour");
  await page.goto(`/owners/${OWNERS[0].owner.slug}/`);
  const box = page.getByTestId("owner-seasons-scroll");
  const [scrollW, clientW] = await box.evaluate((el) => [el.scrollWidth, el.clientWidth]);
  expect(scrollW).toBeGreaterThan(clientW);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
