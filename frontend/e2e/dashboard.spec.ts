import { test, expect } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const BYPASS = { "x-ratelimit-bypass": "ci-test-bypass-9f3a2" };

const PDF = Buffer.from(
  "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n" +
  "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" +
  "3 0 obj<</Type/Page/MediaBox[0 0 400 400]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF");

test("dashboard: profile, recent files, storage, subscription, search", async ({ page, context }) => {
  // register through the real UI
  const name = "Dash Tester";
  await page.goto("/register");
  await page.getByPlaceholder("Jane Smith").fill(name);
  await page.getByPlaceholder("you@example.com").fill(`dash_${Date.now()}@example.com`);
  const pw = page.getByPlaceholder("••••••••");
  await pw.nth(0).fill("TestPass123!");
  await pw.nth(1).fill("TestPass123!");
  await page.getByRole("button", { name: /create account/i }).click();

  // ── 1. dashboard loads ──
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "My documents" })).toBeVisible();

  // ── 2. user profile (sidebar: name/initial) + 5. subscription status (plan badge) ──
  await expect(page.getByText(name)).toBeVisible();
  await expect(page.getByText(/^free$/i)).toBeVisible(); // new accounts start on the free plan

  // upload two files via API with the browser's own session
  const token = (await context.cookies()).find((c) => c.name === "access_token")!.value;
  for (const fname of ["alpha-report.pdf", "beta-invoice.pdf"]) {
    const r = await page.request.post(`${API}/api/v1/documents`, {
      headers: { ...BYPASS, Authorization: `Bearer ${token}` },
      multipart: { file: { name: fname, mimeType: "application/pdf", buffer: PDF } },
    });
    expect(r.status()).toBe(201);
  }
  await page.reload();

  // ── 3. recent files: both appear, newest first ──
  await expect(page.getByText("alpha-report.pdf")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("beta-invoice.pdf")).toBeVisible();
  const titles = await page.locator(".grid p.text-sm.font-medium").allTextContents();
  expect(titles[0]).toBe("beta-invoice.pdf"); // uploaded last → listed first
  await expect(page.getByText(/2 files/)).toBeVisible();

  // ── 4. storage usage indicator reflects the uploads ──
  const usageText = page.getByTestId("storage-usage");
  await expect(usageText).toBeVisible();
  await expect(usageText).toContainText(/of 100 MB used/); // free-plan limit
  await expect(usageText).not.toContainText(/^\s*·\s*0 B/); // non-zero after uploads

  // ── 6. search filters the grid ──
  await page.getByPlaceholder("Search documents…").fill("alpha");
  await expect(page.getByText("alpha-report.pdf")).toBeVisible();
  await expect(page.getByText("beta-invoice.pdf")).toBeHidden();
  await expect(page.getByText(/1 file(?!s)/)).toBeVisible();
  await page.getByPlaceholder("Search documents…").fill("zzz-no-match");
  await expect(page.getByText("No documents here yet")).toBeVisible();
});
