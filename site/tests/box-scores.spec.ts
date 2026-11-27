// Box score pages (#40) and the links into them. Expected values come from the invented fixtures
// (contract/examples/box-scores/<year>.json, matchups.json, rivalries/*.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
const read = (rel: string) => JSON.parse(fs.readFileSync(path.join(EXAMPLES, rel), "utf-8"));
const pts = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
type Side = { owner: { slug: string; name: string }; teamName: string; score: number; projected: number; weeks: { week: number; starters: { name: string; points: number | null }[]; bench: unknown[] }[] };
type Box = { matchupPeriod: number; weeks: number[]; kind: string; home: Side; away: Side; winner: string | null };
const boxPath = (year: number, m: Box) =>
  `/matchups/${year}/${m.weeks[0]}/${[m.home.owner.slug, m.away.owner.slug].sort().join("-vs-")}/`;

async function expectBoxScore(page: Page, m: Box) {
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Box score");
  const board = page.getByTestId("scoreboard-side");
  await expect(board.nth(0)).toContainText(m.home.owner.name);
  await expect(board.nth(0)).toContainText(pts(m.home.score));
  await expect(board.nth(1)).toContainText(m.away.owner.name);
  await expect(board.nth(1)).toContainText(pts(m.away.score));
}

for (const year of [2018, 2020]) {
  const doc = read(`box-scores/${year}.json`) as { matchups: Box[] };
  const m = doc.matchups[0];

  test(`${year}: a Box score shows both lineups, starters then bench, with totals`, async ({ page }) => {
    await page.goto(boxPath(year, m));
    await expectBoxScore(page, m);
    for (const side of [m.home, m.away]) {
      const lineup = page.locator(`[data-testid="lineup"][data-owner="${side.owner.slug}"]`);
      await expect(lineup).toHaveCount(m.weeks.length);
      const w = side.weeks[0];
      await expect(lineup.first().getByTestId("starter")).toHaveCount(w.starters.length);
      await expect(lineup.first().getByTestId("bench")).toHaveCount(w.bench.length);
      await expect(lineup.first().getByTestId("starter").first()).toContainText(w.starters[0].name);
    }
  });
}

test("a two-week round shows each Week's lineup", async ({ page }) => {
  const doc = read("box-scores/2018.json") as { matchups: Box[] };
  const m = doc.matchups.find((x) => x.weeks.length > 1)!;
  await page.goto(boxPath(2018, m));
  await expectBoxScore(page, m);
  await expect(page.locator(`[data-testid="lineup"][data-owner="${m.home.owner.slug}"]`)).toHaveCount(2);
  await expect(page.getByRole("region", { name: `Week ${m.weeks[1]}` })).toBeVisible();
});

test("Season weekly results link to the Box score", async ({ page }) => {
  await page.goto("/seasons/2020/");
  const links = page.getByTestId("weekly-grid").getByTestId("box-score-link");
  const doc = read("box-scores/2020.json") as { matchups: Box[] };
  await expect(links).toHaveCount(doc.matchups.length);
  await links.first().click();
  await expectBoxScore(page, doc.matchups[0]);
});

test("the bracket links to its Box scores, the Third-place game included", async ({ page }) => {
  await page.goto("/seasons/2020/");
  const bracket = page.getByRole("region", { name: "Playoff bracket" });
  const season = read("seasons/2020.json");
  const played = season.bracket.rounds.flatMap((r: { matchups: { isBye: boolean }[] }) => r.matchups).filter((g: { isBye: boolean }) => !g.isBye).length + 1;
  await expect(bracket.getByTestId("box-score-link")).toHaveCount(played);
  await bracket.getByTestId("box-score-link").last().click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Box score");
  await expect(page.getByText("Third-place game")).toBeVisible();
});

test("leaderboard rows and Rivalry games link to Box scores", async ({ page }) => {
  await page.goto("/matchups/");
  const top = read("matchups.json").leaderboards.blowouts[0];
  await page.getByTestId("board-blowouts").getByTestId("box-score-link").first().click();
  await expect(page).toHaveURL(new RegExp(`/matchups/${top.year}/${top.weeks[0]}/`));
  await expect(page.getByTestId("scoreboard")).toContainText(pts(top.winner.score));

  await page.goto("/matchups/abel-trice-vs-cass-imber/");
  const rivalry = read("rivalries/abel-trice-vs-cass-imber.json");
  await expect(page.getByTestId("box-score-link")).toHaveCount(rivalry.games.length);
  await page.getByTestId("box-score-link").first().click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Box score");
});

test("a Box score page fits the screen", async ({ page }, info) => {
  const doc = read("box-scores/2018.json") as { matchups: Box[] };
  for (const [m, name] of [[doc.matchups[0], "box-score"], [doc.matchups.find((x) => x.weeks.length > 1)!, "box-score-two-week"]] as const) {
    await page.goto(boxPath(2018, m));
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(SHOTS, info.project.name, `${name}.png`), fullPage: true });
  }
});
