import { test, expect } from "@playwright/test";

test.setTimeout(60_000);

const PDF = Buffer.from(
  "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n" +
  "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" +
  "3 0 obj<</Type/Page/MediaBox[0 0 400 400]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF");

test("translate: landing tile → tool page → backend round-trip", async ({ page }) => {
  // landing page advertises the tool
  await page.goto("/");
  await expect(page.getByText("Translate PDF")).toBeVisible();

  // authed tool page with language pickers
  await page.goto("/register");
  await page.getByPlaceholder("Jane Smith").fill("Translate Tester");
  await page.getByPlaceholder("you@example.com").fill(`tr_${Date.now()}@example.com`);
  const pw = page.getByPlaceholder("••••••••");
  await pw.nth(0).fill("TestPass123!");
  await pw.nth(1).fill("TestPass123!");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

  await page.goto("/tools/translate");
  await page.setInputFiles('input[type="file"]', { name: "doc.pdf", mimeType: "application/pdf", buffer: PDF });
  await expect(page.getByLabel("Source language")).toBeVisible();
  await expect(page.getByLabel("Target language")).toBeVisible();
  await expect(page.getByLabel("Target language").locator("option", { hasText: "Hindi" })).toHaveCount(1);
  await expect(page.getByLabel("Target language").locator("option", { hasText: "Telugu" })).toHaveCount(1);

  // blank PDF → the backend's "run OCR first" message must surface in the UI
  await page.getByRole("button", { name: "Translate", exact: true }).click();
  await expect(page.getByText(/No extractable text/)).toBeVisible({ timeout: 20_000 });
});

test("HTML to PDF tool converts an uploaded .html file", async ({ page }) => {
  await page.goto("/register");
  await page.getByPlaceholder("Jane Smith").fill("Conv Tester");
  await page.getByPlaceholder("you@example.com").fill(`cvt_${Date.now()}@example.com`);
  const pw = page.getByPlaceholder("••••••••");
  await pw.nth(0).fill("TestPass123!");
  await pw.nth(1).fill("TestPass123!");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

  // tool is listed on the hub
  await page.goto("/tools");
  await expect(page.getByText("HTML to PDF")).toBeVisible();
  await page.getByText("HTML to PDF").click();
  await expect(page).toHaveURL(/\/tools\/html-to-pdf/);

  await page.setInputFiles('input[type="file"]', {
    name: "page.html", mimeType: "text/html",
    buffer: Buffer.from("<html><body><h1>Hello HTML</h1><p>PDF me.</p></body></html>"),
  });
  await page.getByRole("button", { name: "Convert to PDF" }).click();
  // LibreOffice cold-start can take a while right after a container restart
  await expect(page.getByRole("link", { name: /\.pdf|Download/i }).first()).toBeVisible({ timeout: 60_000 });
});
