// "How the grades work" (DraftExplainer): on every Draft view, collapsed until opened.
import { expect, test } from "@playwright/test";

const VIEWS = [
  { name: "Season Draft tab", url: "/seasons/2020/#draft", panel: true, bestDrafters: false },
  { name: "Owner Draft tab", url: "/owners/quinn-harrow/#draft", panel: true, bestDrafters: false },
  { name: "Draft section", url: "/draft/", panel: false, bestDrafters: true },
];

for (const v of VIEWS) {
  test(`${v.name} explains how the grades work`, async ({ page }) => {
    await page.goto(v.url);
    const scope = v.panel ? page.getByRole("tabpanel", { name: "Draft" }) : page.locator("main");
    const explainer = scope.getByTestId("draft-explainer");
    await expect(explainer).toHaveCount(1);
    await expect(explainer.getByText("Points over expected", { exact: true })).toBeHidden();
    await explainer.getByText("How the grades work").click();
    const terms = ["Season points", "Positional finish (e.g. RB3)", "Replacement level", "Points over expected", "Draft grade", "Colors"];
    for (const term of terms) {
      await expect(explainer.getByText(term, { exact: true })).toBeVisible();
    }
    await expect(explainer).toContainText("+140");
    // The /draft page also explains its Steals list and Best drafters
    for (const term of ["Value over slot", "Best drafters"]) {
      await expect(explainer.getByText(term, { exact: true })).toHaveCount(v.bestDrafters ? 1 : 0);
    }
  });
}
