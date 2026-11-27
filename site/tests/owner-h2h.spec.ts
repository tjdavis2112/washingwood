// The Owner page's head-to-head table (#16). Expected values come from the invented fixture
// documents (contract/examples/owners/<slug>.json).
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

type Record = { wins: number; losses: number; ties: number };
type Row = { opponent: { slug: string; name: string }; regularSeason: Record; playoffs: Record; meetings: number };
type OwnerDoc = { owner: { slug: string; name: string }; isFormer: boolean; headToHead: Row[] };
const DIR = path.resolve(import.meta.dirname, "../../contract/examples/owners");
const OWNERS = fs.readdirSync(DIR).map((f) => JSON.parse(fs.readFileSync(path.join(DIR, f), "utf-8")) as OwnerDoc);
const record = (r: Record) => `${r.wins}-${r.losses}-${r.ties}`;

test("the fixture has a former Owner as someone's opponent and a playoff meeting", () => {
  const former = new Set(OWNERS.filter((o) => o.isFormer).map((o) => o.owner.slug));
  const rows = OWNERS.flatMap((o) => o.headToHead);
  expect(rows.some((h) => former.has(h.opponent.slug))).toBe(true);
  expect(rows.some((h) => h.playoffs.wins + h.playoffs.losses + h.playoffs.ties > 0)).toBe(true);
});

for (const o of OWNERS) {
  test(`${o.owner.slug}: every opponent in meetings order with regular-season and playoff records`, async ({ page }) => {
    await page.goto(`/owners/${o.owner.slug}/`);
    const rows = page.getByRole("table", { name: "Head-to-head" }).locator("tbody tr");
    await expect(rows).toHaveCount(o.headToHead.length);
    for (const [i, h] of o.headToHead.entries()) {
      await expect(rows.nth(i).locator("th, td")).toHaveText([
        h.opponent.name,
        String(h.meetings),
        record(h.regularSeason),
        record(h.playoffs),
      ]);
      await expect(rows.nth(i).getByRole("link", { name: h.opponent.name })).toHaveAttribute(
        "href",
        `/owners/${h.opponent.slug}/`,
      );
    }
  });
}

test("an opponent link opens that Owner's page", async ({ page }) => {
  const o = OWNERS.find((x) => x.headToHead.length > 0)!;
  const h = o.headToHead[0];
  await page.goto(`/owners/${o.owner.slug}/`);
  await page.getByRole("table", { name: "Head-to-head" }).getByRole("link", { name: h.opponent.name }).click();
  await expect(page).toHaveURL(new RegExp(`/owners/${h.opponent.slug}/$`));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(h.opponent.name);
});

test("on a phone, the whole head-to-head table fits without scrolling", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "phone-width behaviour");
  await page.goto(`/owners/${OWNERS[0].owner.slug}/`);
  const box = page.getByTestId("h2h-scroll");
  const [scrollW, clientW] = await box.evaluate((el) => [el.scrollWidth, el.clientWidth]);
  expect(scrollW).toBeLessThanOrEqual(clientW);
  // Headers are uppercased by CSS, and the long forms are hidden on phones
  const headers = page.getByRole("table", { name: "Head-to-head" }).locator("thead th");
  await expect(headers).toHaveText([/^opponent$/i, /^met$/i, /^reg\.$/i, /^playoffs$/i], { useInnerText: true });
});
