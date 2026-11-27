// The Owners index (#13). Expected values come from the invented fixture document
// (contract/examples/owners.json) the site is built from.
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

type Entry = {
  owner: { slug: string; name: string };
  currentTeamName: string;
  firstSeason: number;
  lastSeason: number;
  isFormer: boolean;
  titles: number[];
  runnerUps: number[];
  regularSeason: { wins: number; losses: number; ties: number };
};
const OWNERS = JSON.parse(
  fs.readFileSync(path.resolve(import.meta.dirname, "../../contract/examples/owners.json"), "utf-8"),
).owners as Entry[];
const span = (e: Entry) => (e.firstSeason === e.lastSeason ? String(e.firstSeason) : `${e.firstSeason}–${e.lastSeason}`);
const record = ({ wins, losses, ties }: Entry["regularSeason"]) => (ties ? `${wins}-${losses}-${ties}` : `${wins}-${losses}`);

const GROUPS = [
  { name: "Current Owners", entries: OWNERS.filter((e) => !e.isFormer) },
  { name: "Former Owners", entries: OWNERS.filter((e) => e.isFormer) },
];

test("the fixture has current and former Owners", () => {
  expect(GROUPS.every((g) => g.entries.length > 0)).toBe(true);
});

for (const group of GROUPS) {
  test(`${group.name} are listed in pipeline order with team, span, trophies and record`, async ({ page }) => {
    await page.goto("/owners/");
    const section = page.getByRole("region", { name: group.name, exact: true });
    const cards = section.getByRole("link");
    await expect(cards.getByRole("heading")).toHaveText(group.entries.map((e) => e.owner.name));

    for (const [i, e] of group.entries.entries()) {
      const card = cards.nth(i);
      await expect(card).toHaveAttribute("href", `/owners/${e.owner.slug}/`);
      await expect(card).toContainText(e.currentTeamName);
      await expect(card).toContainText(span(e));
      await expect(card).toContainText(record(e.regularSeason));
      await expect(card.getByRole("list", { name: "Titles" }).getByRole("listitem")).toHaveText(e.titles.map(String));
      await expect(card.getByRole("list", { name: "Runner-up finishes" }).getByRole("listitem")).toHaveText(
        e.runnerUps.map(String),
      );
    }
  });
}

test("the Owners nav link opens the index, and a card opens that Owner's page", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Owners", exact: true }).click();
  await expect(page).toHaveURL(/\/owners\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Owners");

  const first = OWNERS[0];
  await page.getByRole("link", { name: new RegExp(first.owner.name) }).click();
  await expect(page).toHaveURL(new RegExp(`/owners/${first.owner.slug}/$`));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(first.owner.name);
  await expect(page.getByRole("main")).toContainText(first.currentTeamName);
});

test("every Owner in the index has a page", async ({ page }) => {
  for (const e of OWNERS) {
    const res = await page.goto(`/owners/${e.owner.slug}/`);
    expect(res?.status(), e.owner.slug).toBe(200);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(e.owner.name);
  }
});
