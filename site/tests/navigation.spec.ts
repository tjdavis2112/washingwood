import { expect, test } from "@playwright/test";
import { ALL_PAGES, COMING_SOON, NAV } from "./pages";

for (const path of ALL_PAGES) {
  test(`navigation is on ${path}`, async ({ page }) => {
    const res = await page.goto(path);
    expect(res?.status()).toBe(200);
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link")).toHaveText(NAV);
  });
}

for (const [path, label] of Object.entries(COMING_SOON)) {
  test(`${label} nav link opens its Coming soon page`, async ({ page }) => {
    await page.goto("/");
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${path}$`));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(label);
    await expect(page.getByText("Coming soon", { exact: true })).toBeVisible();
  });
}

test("Seasons lists every Season newest first with its team count, linking to each Season page", async ({ page }) => {
  await page.goto("/seasons/");
  const links = page.getByRole("main").getByRole("link");
  await expect(links).toHaveText([/2020.*12 teams/, /2018.*10 teams/]);
  await links.last().click();
  await expect(page).toHaveURL(/\/seasons\/2018\/$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("2018 Season");
});

test("an unknown path is a real 404, not Home", async ({ page }) => {
  const res = await page.goto("/no-such-page/");
  expect(res?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Page not found");
});
