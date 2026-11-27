// Season pages: the trophy-case Podium, Last place and the Punishment popup.
// Expected values come from the invented fixture documents the site is built from.
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const EXAMPLES = path.resolve(import.meta.dirname, "../../contract/examples");
const seasonDoc = (year: number) =>
  JSON.parse(fs.readFileSync(path.join(EXAMPLES, "seasons", `${year}.json`), "utf-8"));
const record = (r: { wins: number; losses: number; ties: number }) =>
  r.ties ? `${r.wins}-${r.losses}-${r.ties}` : `${r.wins}-${r.losses}`;

test("Home links to every Season's page", async ({ page }) => {
  await page.goto("/");
  const seasons = page.getByRole("region", { name: "Seasons" }).getByRole("link");
  await expect(seasons).toHaveText([/2020/, /2018/]);
  await seasons.filter({ hasText: "2018" }).click();
  await expect(page).toHaveURL(/\/seasons\/2018\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("2018 Season");
});

for (const year of [2018, 2020]) {
  const doc = seasonDoc(year);

  test(`${year}: the Podium shows each place's Owner, team and record, Champion raised in the center`, async ({
    page,
  }) => {
    await page.goto(`/seasons/${year}/`);
    await expect(page.getByText(`${doc.teamCount} teams`)).toBeVisible();
    const podium = page.getByRole("region", { name: "Podium" });

    const spots = [];
    for (const p of doc.podium) {
      const spot = podium.getByRole("listitem").filter({ hasText: p.owner.name });
      await expect(spot).toContainText(["1st", "2nd", "3rd"][p.place - 1]);
      await expect(spot).toContainText(p.teamName);
      await expect(spot).toContainText(record(p.record));
      spots.push(await spot.boundingBox());
    }
    const [first, second, third] = spots.map((b) => b!);
    // Trophy case: 1st in the middle and higher than 2nd (left) and 3rd (right)
    expect(second.x).toBeLessThan(first.x);
    expect(first.x).toBeLessThan(third.x);
    expect(first.y).toBeLessThan(second.y);
    expect(first.y).toBeLessThan(third.y);
  });

  test(`${year}: Last place shows the Owner, team and record`, async ({ page }) => {
    await page.goto(`/seasons/${year}/`);
    const last = page.getByRole("region", { name: "Last place" });
    await expect(last).toContainText(doc.lastPlace.owner.name);
    await expect(last).toContainText(doc.lastPlace.teamName);
    await expect(last).toContainText(record(doc.lastPlace.record));
  });
}

test("the Punishment popup opens with its placeholder and closes again", async ({ page }, info) => {
  await page.goto("/seasons/2020/");
  await page.getByRole("button", { name: "Punishment" }).click();
  const dialog = page.getByRole("dialog", { name: "Punishment" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Punishment details coming soon");
  // Slots for the content that arrives later
  await expect(dialog.getByTestId("punishment-picture")).toBeVisible();
  await expect(dialog.getByTestId("punishment-title")).toBeVisible();
  await expect(dialog.getByTestId("punishment-description")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.screenshot({
    path: path.resolve(import.meta.dirname, "../test-results/screenshots", info.project.name, "punishment-popup.png"),
  });

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await page.getByRole("button", { name: "Punishment" }).click();
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
});

test("a Season that isn't in the data is a 404", async ({ page }) => {
  const res = await page.goto("/seasons/2019/");
  expect(res?.status()).toBe(404);
});
