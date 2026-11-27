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
    await expect(explainer.getByText("Value over slot", { exact: true })).toBeHidden();
    await explainer.getByText("How the grades work").click();
    for (const term of ["Season points", "Positional finish (e.g. RB3)", "Value over slot", "Draft grade", "Colors"]) {
      await expect(explainer.getByText(term, { exact: true })).toBeVisible();
    }
    await expect(explainer).toContainText("+6");
    await expect(explainer.getByText("Best drafters", { exact: true })).toHaveCount(v.bestDrafters ? 1 : 0);
  });
}
