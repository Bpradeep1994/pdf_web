import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// WCAG 2.1 A/AA automated accessibility checks on the key public + authed pages.
// Gates on serious/critical violations (the ones that actually block users);
// minor/moderate are reported but not failed, to avoid noise on an existing UI.

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function scan(page: any) {
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  const blocking = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical");
  if (blocking.length) {
    console.log("Blocking a11y violations:",
      blocking.map((v) => `${v.id} (${v.impact}) x${v.nodes.length}`).join(", "));
  }
  return blocking;
}

test("landing page has no serious/critical a11y violations", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Translate PDF")).toBeVisible();
  expect(await scan(page)).toEqual([]);
});

test("login page has no serious/critical a11y violations", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  expect(await scan(page)).toEqual([]);
});

test("register page has no serious/critical a11y violations", async ({ page }) => {
  await page.goto("/register");
  await expect(page.getByRole("button", { name: /create account/i })).toBeVisible();
  expect(await scan(page)).toEqual([]);
});

test("pricing page has no serious/critical a11y violations", async ({ page }) => {
  await page.goto("/pricing");
  expect(await scan(page)).toEqual([]);
});

test("dashboard (authed) has no serious/critical a11y violations", async ({ page }) => {
  await page.goto("/register");
  await page.getByPlaceholder("Jane Smith").fill("A11y Tester");
  await page.getByPlaceholder("you@example.com").fill(`a11y_${Date.now()}@example.com`);
  const pw = page.getByPlaceholder("••••••••");
  await pw.nth(0).fill("TestPass123!");
  await pw.nth(1).fill("TestPass123!");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "My documents" })).toBeVisible();
  expect(await scan(page)).toEqual([]);
});
