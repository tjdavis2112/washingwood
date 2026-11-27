// Season → Draft tab (#25): the draft board. Desktop shows the grid (columns = Draft slots, rows =
// rounds); phones show a list grouped by round. Expected values come from the invented fixtures.
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
type Pick = {
  overall: number;
  round: number;
  roundPick: number;
  owner: { slug: string; name: string };
  player: { name: string; position: string; nflTeam: string | null } | null;
};
const draftOf = (year: number) =>
  JSON.parse(fs.readFileSync(path.join(EXAMPLES, "seasons", `${year}.json`), "utf-8")).draft as {
    type: string;
    rounds: number;
    order: { slot: number; owner: { slug: string; name: string }; teamName: string }[];
    picks: Pick[];
    note: string | null;
  };
const pickLabel = (p: Pick) => `${p.round}.${String(p.roundPick).padStart(2, "0")}`;

async function openDraft(page: Page, year: number) {
  await page.goto(`/seasons/${year}/#draft`);
  const panel = page.getByRole("tabpanel", { name: "Draft" });
  await expect(panel).toBeVisible();
  return panel;
}

for (const year of [2018, 2020]) {
  const draft = draftOf(year);

  test(`${year}: every Pick shows its round.pick, Player, position and NFL team`, async ({ page }, info) => {
    const panel = await openDraft(page, year);
    const isPhone = info.project.name === "phone";
    const cells = panel.getByTestId(isPhone ? "draft-row" : "draft-cell");
    await expect(cells).toHaveCount(draft.picks.length);
    for (const p of [draft.picks[0], draft.picks[draft.order.length], draft.picks[draft.picks.length - 1]]) {
      const cell = panel.locator(`[data-testid="${isPhone ? "draft-row" : "draft-cell"}"][data-overall="${p.overall}"]`);
      await expect(cell).toContainText(pickLabel(p));
      if (p.player) {
        await expect(cell).toContainText(p.player.name);
        await expect(cell).toContainText(p.player.position);
        if (p.player.nflTeam) await expect(cell).toContainText(p.player.nflTeam);
      } else {
        await expect(cell).toContainText("Not recorded");
      }
      if (isPhone) await expect(cell.getByRole("link", { name: p.owner.name })).toBeVisible();
    }
  });

  test(`${year}: the board fits the page, wide grids scroll inside their own box`, async ({ page }, info) => {
    await openDraft(page, year);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(SHOTS, info.project.name, `seasons-${year}-draft.png`), fullPage: true });
  });
}

test("desktop grid: one column per Draft slot with the Owner linked, and the snake reverses round 2", async ({
  page,
}, info) => {
  test.skip(info.project.name !== "desktop", "the grid is the desktop layout");
  const draft = draftOf(2020);
  const panel = await openDraft(page, 2020);
  const grid = panel.getByRole("table", { name: "Draft board" });
  await expect(grid).toBeVisible();
  await expect(panel.getByTestId("draft-list")).toBeHidden();
  const headers = grid.locator("thead th");
  await expect(headers).toHaveCount(draft.order.length + 1);
  for (const o of draft.order) {
    const th = headers.nth(o.slot);
    await expect(th).toContainText(o.teamName);
    await expect(th.getByRole("link", { name: o.owner.name })).toHaveAttribute("href", `/owners/${o.owner.slug}/`);
  }
  // Row 2 runs right to left: slot 1's second Pick is the last of round 2, in column 1
  const n = draft.order.length;
  const round2 = grid.locator("tbody tr").nth(1).getByTestId("draft-cell");
  await expect(round2.first()).toHaveAttribute("data-overall", String(2 * n));
  await expect(round2.last()).toHaveAttribute("data-overall", String(n + 1));
});

test("phone list: Picks grouped by round, in pick order", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "the round list is the phone layout");
  const draft = draftOf(2020);
  const panel = await openDraft(page, 2020);
  await expect(panel.getByRole("table", { name: "Draft board" })).toBeHidden();
  const round2 = panel.getByRole("group", { name: "Round 2" }).getByTestId("draft-row");
  await expect(round2).toHaveCount(draft.order.length);
  await expect(round2.first()).toHaveAttribute("data-overall", String(draft.order.length + 1));
});

test("an offline Draft shows its note; a snake Draft shows none", async ({ page }) => {
  const offline = draftOf(2018);
  let panel = await openDraft(page, 2018);
  await expect(panel.getByTestId("draft-note")).toHaveText(offline.note!);
  await expect(panel).toContainText("offline");
  panel = await openDraft(page, 2020);
  await expect(panel.getByTestId("draft-note")).toHaveCount(0);
  await expect(panel).toContainText("snake");
});
