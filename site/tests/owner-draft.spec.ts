// Owner → Draft tab (#26): a first-round strip and every Pick per Season, newest first, each Season
// linking to its draft board. Expected values come from the invented fixture Owner documents.
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const SHOTS = path.resolve(import.meta.dirname, "../test-results/screenshots");
type Player = { name: string; position: string; nflTeam: string | null };
type OwnerDraft = {
  year: number;
  teamName: string;
  slot: number;
  picks: { overall: number; round: number; roundPick: number; player: Player | null }[];
};
const owners = fs
  .readdirSync(path.join(EXAMPLES, "owners"))
  .map((f) => JSON.parse(fs.readFileSync(path.join(EXAMPLES, "owners", f), "utf-8")))
  .map((d) => ({ owner: d.owner as { slug: string; name: string }, draft: d.draft as OwnerDraft[] }));
const pickLabel = (p: { round: number; roundPick: number }) => `${p.round}.${String(p.roundPick).padStart(2, "0")}`;

async function openDraft(page: Page, slug: string) {
  await page.goto(`/owners/${slug}/#draft`);
  const panel = page.getByRole("tabpanel", { name: "Draft" });
  await expect(panel).toBeVisible();
  return panel;
}

for (const { owner, draft } of owners) {
  test(`${owner.slug}: first-round strip and Picks by Season, newest first`, async ({ page }) => {
    const panel = await openDraft(page, owner.slug);
    const strip = panel.getByTestId("first-round-pick");
    await expect(strip).toHaveCount(draft.length);
    const seasons = panel.getByTestId("owner-draft-season");
    await expect(seasons).toHaveCount(draft.length);
    for (const [i, d] of draft.entries()) {
      const first = d.picks[0];
      await expect(strip.nth(i)).toHaveAttribute("data-year", String(d.year));
      await expect(strip.nth(i)).toContainText(pickLabel(first));
      await expect(strip.nth(i)).toContainText(first.player ? first.player.name : "Not recorded");

      const season = seasons.nth(i);
      await expect(season).toHaveAttribute("data-year", String(d.year));
      await expect(season).toContainText(`${d.teamName} · Slot ${d.slot}`);
      const picks = season.getByTestId("owner-pick");
      await expect(picks).toHaveCount(d.picks.length);
      for (const [j, p] of d.picks.entries()) {
        await expect(picks.nth(j)).toContainText(pickLabel(p));
        if (p.player) {
          await expect(picks.nth(j)).toContainText(p.player.name);
          await expect(picks.nth(j)).toContainText(p.player.position);
        } else {
          await expect(picks.nth(j)).toContainText("Not recorded");
        }
      }
    }
  });
}

test("a Season heading opens that Season's draft board", async ({ page }) => {
  const { owner, draft } = owners.find((o) => o.draft.length > 1)!;
  const panel = await openDraft(page, owner.slug);
  await panel.getByRole("link", { name: String(draft[0].year), exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/seasons/${draft[0].year}/#draft$`));
  await expect(page.getByRole("tabpanel", { name: "Draft" })).toBeVisible();
});

test("an unrecorded Pick reads Not recorded on the Owner's tab", async ({ page }) => {
  const withGap = owners.find((o) => o.draft.some((d) => d.picks.some((p) => p.player === null)))!;
  const panel = await openDraft(page, withGap.owner.slug);
  await expect(panel.getByText("Not recorded").first()).toBeVisible();
});

test("the Draft tab fits the page", async ({ page }, info) => {
  const { owner } = owners.find((o) => o.draft.length > 1)!;
  await openDraft(page, owner.slug);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, "page is wider than the viewport").toBeLessThanOrEqual(0);
  await page.screenshot({ path: path.join(SHOTS, info.project.name, `owners-${owner.slug}-draft.png`), fullPage: true });
});

// --- Draft grades on the Owner tab (#29) ---

const ord = (n: number) => {
  const tail = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${tail}`;
};
const signedValue = (v: number) => (v > 0 ? `+${v}` : v < 0 ? `−${Math.abs(v)}` : "0");
const graded = fs
  .readdirSync(path.join(EXAMPLES, "owners"))
  .map((f) => JSON.parse(fs.readFileSync(path.join(EXAMPLES, "owners", f), "utf-8")))
  .find((d) => d.draft.length > 1);

test("each Season shows the Owner's Draft grade, and each Pick its value", async ({ page }) => {
  const panel = await openDraft(page, graded.owner.slug);
  const seasons = panel.getByTestId("owner-draft-season");
  for (const [i, d] of graded.draft.entries()) {
    await expect(seasons.nth(i).getByTestId("owner-draft-grade")).toContainText(`${ord(d.grade.rank)} of ${d.grade.of}`);
    await expect(seasons.nth(i).getByTestId("owner-draft-grade")).toContainText(signedValue(d.grade.total));
    const p = d.picks.find((x: { valueOverSlot: number | null }) => x.valueOverSlot !== null);
    const row = seasons.nth(i).locator(`[data-testid="owner-pick"][data-overall="${p.overall}"]`);
    await expect(row.getByTestId("pick-value")).toHaveText(signedValue(p.valueOverSlot));
    await expect(row).toContainText(`${p.points.toFixed(1)} pts`);
  }
});
