import { test, expect } from "@playwright/test";

test("landing page renders hero + nav", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Every PDF tool you need")).toBeVisible();
  await expect(page.getByRole("link", { name: "Get started" }).first()).toBeVisible();
});

test("pricing page lists plans", async ({ page }) => {
  await page.goto("/pricing");
  await expect(page.getByText("transparent pricing")).toBeVisible();
  await expect(page.getByText("Business")).toBeVisible();
});

test("login page renders", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText("Welcome back")).toBeVisible();
});

test("register → dashboard happy path", async ({ page }) => {
  await page.goto("/register");
  const email = `e2e_${Date.now()}@example.com`;
  await page.getByPlaceholder("Jane Smith").fill("E2E User");
  await page.getByPlaceholder("you@example.com").fill(email);
  const pw = page.getByPlaceholder("••••••••");
  await pw.nth(0).fill("TestPass123!");
  await pw.nth(1).fill("TestPass123!");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
});
