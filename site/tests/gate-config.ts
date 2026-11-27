// Test-only secrets (invented). The real ones are Cloudflare secrets: SITE_PASSPHRASE and SESSION_KEY.
import { expect, type Page } from "@playwright/test";

export const PASSPHRASE = "test-only stapler orbit 42";
export const SESSION_KEY = "test-only-session-key-0123456789abcdef";
export const ROTATED_PASSPHRASE = "test-only rotated lantern 77";
export const OTHER_SESSION_KEY = "test-only-other-session-key-fedcba9876543210";
export const PORT = 8788;
export const AUTH_STATE = "test-results/.auth/state.json";
export const LANDING = "/enter/";

export async function signIn(page: Page, phrase: string) {
  await page.goto(LANDING);
  await page.getByLabel("Passphrase").fill(phrase);
  await page.getByRole("button", { name: "Enter" }).click();
}

export async function signInAndExpectHome(page: Page, phrase: string) {
  await signIn(page, phrase);
  await expect(page).toHaveURL(/\/$/);
}
