import { expect, test } from "@playwright/test";

// Values from contract/examples/league.json (invented)
test("Home shows the current Champion: Owner, team name and year", async ({ page }) => {
  await page.goto("/");
  const banner = page.getByRole("region", { name: "Champion" });
  await expect(banner).toContainText("Ines Dorrow");
  await expect(banner).toContainText("Dorrow Drakes");
  await expect(banner).toContainText("2020");
});

test("the Champion banner opens that Season's page", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("region", { name: "Champion" }).getByRole("link").click();
  await expect(page).toHaveURL(/\/seasons\/2020\/$/);
});
