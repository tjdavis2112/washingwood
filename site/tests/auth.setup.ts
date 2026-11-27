import { test as setup } from "@playwright/test";
import { AUTH_STATE, PASSPHRASE, signInAndExpectHome } from "./gate-config";

setup("sign in through the landing screen", async ({ page }) => {
  await signInAndExpectHome(page, PASSPHRASE);
  await page.context().storageState({ path: AUTH_STATE });
});
