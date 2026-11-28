// The Owner page (#14): header, trophy case, career summary and Coming soon tabs (Draft since #26). Expected values
// come from the invented fixture documents (contract/examples/owners/<slug>.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

type Record = { wins: number; losses: number; ties: number };
type OwnerDoc = {
  owner: { slug: string; name: string };
  currentTeamName: string;
  firstSeason: number;
  lastSeason: number;
  isFormer: boolean;
  trophies: { titles: number[]; runnerUps: number[]; thirds: number[] };
  career: {
    regularSeason: Record;
    playoffs: Record;
    avgPointsFor: number;
    avgPointsAgainst: number;
    playoffAppearances: number[];
    lastPlaces: number[];
  };
  seasons: unknown[];
};
const DIR = path.resolve(import.meta.dirname, "../../contract/examples/owners");
const OWNERS = fs
  .readdirSync(DIR)
  .map((f) => JSON.parse(fs.readFileSync(path.join(DIR, f), "utf-8")) as OwnerDoc);

const span = (o: OwnerDoc) => (o.firstSeason === o.lastSeason ? String(o.firstSeason) : `${o.firstSeason}–${o.lastSeason}`);
const record = (r: Record) => (r.ties ? `${r.wins}-${r.losses}-${r.ties}` : `${r.wins}-${r.losses}`);
const points = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

test("the fixture covers an Owner with a Third-place finish, one with no trophies, and a former Owner", () => {
  const t = (o: OwnerDoc) => o.trophies;
  expect(OWNERS.some((o) => t(o).thirds.length)).toBe(true);
  expect(OWNERS.some((o) => !t(o).titles.length && !t(o).runnerUps.length && !t(o).thirds.length)).toBe(true);
  expect(OWNERS.some((o) => o.isFormer)).toBe(true);
});

for (const o of OWNERS) {
  test(`${o.owner.slug}: header, trophy case and career summary`, async ({ page }) => {
    await page.goto(`/owners/${o.owner.slug}/`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(o.owner.name);
    const header = page.getByRole("main").locator("header").first();
    await expect(header).toContainText(o.currentTeamName);
    await expect(header).toContainText(span(o));
    if (o.isFormer) await expect(header).toContainText("Former Owner");
    else await expect(header).not.toContainText("Former Owner");

    const trophyCase = page.getByRole("region", { name: "Trophy case" });
    const { titles, runnerUps, thirds } = o.trophies;
    if (!titles.length && !runnerUps.length && !thirds.length) {
      await expect(trophyCase).toContainText("No Podium finishes");
    } else {
      for (const [name, years] of [
        ["Titles", titles],
        ["Runner-up finishes", runnerUps],
        ["Third-place finishes", thirds],
      ] as const) {
        await expect(trophyCase.getByRole("list", { name }).getByRole("listitem")).toHaveText(years.map(String));
      }
    }

    const career = page.getByRole("region", { name: "Career" });
    const c = o.career;
    const expected = [
      ["Regular season", record(c.regularSeason)],
      ["Playoffs", record(c.playoffs)],
      ["Playoff appearances", `${c.playoffAppearances.length} of ${o.seasons.length}`],
      ["Avg points for", points(c.avgPointsFor)],
      ["Avg points against", points(c.avgPointsAgainst)],
      ["Last place finishes", String(c.lastPlaces.length)],
    ];
    await expect(career.locator("dt")).toHaveText(expected.map(([label]) => label));
    await expect(career.locator("dd")).toHaveText(expected.map(([, value]) => value));
  });
}

test("the Rosters tab says Coming soon, and tabs work from the keyboard", async ({ page }) => {
  const o = OWNERS[0];
  await page.goto(`/owners/${o.owner.slug}/`);
  const tabs = page.getByRole("tablist", { name: `${o.owner.name} sections` }).getByRole("tab");
  await expect(tabs).toHaveText(["Career", "Rosters", "Draft", "Transactions"]);
  for (const name of ["Rosters"]) {
    await tabs.filter({ hasText: name }).click();
    const panel = page.getByRole("tabpanel", { name });
    await expect(panel.getByRole("heading", { name })).toBeVisible();
    await expect(panel.getByText("Coming soon", { exact: true })).toBeVisible();
  }
  await tabs.filter({ hasText: "Transactions" }).focus();
  await page.keyboard.press("Home");
  await expect(page.getByRole("tabpanel", { name: "Career" })).toBeVisible();
});
