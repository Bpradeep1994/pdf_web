import { test, expect } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const BYPASS = { "x-ratelimit-bypass": "ci-test-bypass-9f3a2" };

test("verify-email page verifies a real token (dev flow)", async ({ page, request }) => {
  // register via API, then get a fresh token from resend-verification (dev returns it)
  const email = `ve_${Date.now()}@example.com`;
  const reg = await request.post(`${API}/api/v1/auth/register`, {
    headers: BYPASS,
    data: { email, password: "TestPass123!", full_name: "Verify Me" },
  });
  expect(reg.status()).toBe(201);
  const { access_token } = await reg.json();
  const resend = await request.post(`${API}/api/v1/auth/resend-verification`, {
    headers: { ...BYPASS, Authorization: `Bearer ${access_token}` },
  });
  const { token } = await resend.json();
  expect(token).toBeTruthy(); // dev mode exposes it

  await page.goto(`/verify-email?token=${token}`);
  await expect(page.getByText("Email verified")).toBeVisible({ timeout: 10_000 });

  // reusing the same link fails cleanly
  await page.goto(`/verify-email?token=${token}`);
  await expect(page.getByText("Verification failed")).toBeVisible({ timeout: 10_000 });
});

test("verify-email without token shows error", async ({ page }) => {
  await page.goto("/verify-email");
  await expect(page.getByText("Verification failed")).toBeVisible();
});

test("forgot-password page submits and confirms", async ({ page }) => {
  await page.goto("/forgot-password");
  await expect(page.getByText("Forgot your password?")).toBeVisible();
  await page.getByPlaceholder("you@example.com").fill("someone@example.com");
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByText("Check your inbox")).toBeVisible();
});

test("reset-password page validates and rejects a bad token", async ({ page }) => {
  await page.goto("/reset-password?token=bogus-token");
  await page.getByPlaceholder("••••••••").nth(0).fill("NewPass456!");
  await page.getByPlaceholder("••••••••").nth(1).fill("NewPass456!");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByText(/Invalid or expired token|Reset failed/)).toBeVisible();

  // no token at all → invalid-link state
  await page.goto("/reset-password");
  await expect(page.getByText("Invalid link")).toBeVisible();
});
