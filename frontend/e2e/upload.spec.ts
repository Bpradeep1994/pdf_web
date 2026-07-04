import { test, expect } from "@playwright/test";

const PDF = Buffer.from(
  "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n" +
  "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" +
  "3 0 obj<</Type/Page/MediaBox[0 0 400 400]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF");

async function registerAndOpenUpload(page: any) {
  await page.goto("/register");
  await page.getByPlaceholder("Jane Smith").fill("Upload Tester");
  await page.getByPlaceholder("you@example.com").fill(`upl_${Date.now()}@example.com`);
  const pw = page.getByPlaceholder("••••••••");
  await pw.nth(0).fill("TestPass123!");
  await pw.nth(1).fill("TestPass123!");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
  await page.getByRole("button", { name: "Upload PDF" }).click();
  await expect(page.getByText("Upload PDF files")).toBeVisible();
}

test("upload: single PDF via file picker", async ({ page }) => {
  await registerAndOpenUpload(page);
  await page.setInputFiles('input[type="file"]', { name: "report.pdf", mimeType: "application/pdf", buffer: PDF });
  await expect(page.getByText("report.pdf")).toBeVisible();
  await page.getByRole("button", { name: /Upload 1 file/ }).click();
  await expect(page.getByText(/1 file\(s\) uploaded/)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("report.pdf")).toBeVisible(); // now on the dashboard grid
});

test("upload: multiple PDFs in one batch", async ({ page }) => {
  await registerAndOpenUpload(page);
  await page.setInputFiles('input[type="file"]', [
    { name: "a.pdf", mimeType: "application/pdf", buffer: PDF },
    { name: "b.pdf", mimeType: "application/pdf", buffer: PDF },
    { name: "c.pdf", mimeType: "application/pdf", buffer: PDF },
  ]);
  await expect(page.getByText("a.pdf")).toBeVisible();
  await expect(page.getByText("c.pdf")).toBeVisible();
  await page.getByRole("button", { name: /Upload 3 file/ }).click();
  await expect(page.getByText(/3 file\(s\) uploaded/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/3 files/)).toBeVisible(); // dashboard count
});

test("upload: non-PDF (ZIP/Word) is rejected with a message, not silently", async ({ page }) => {
  await registerAndOpenUpload(page);
  // dropzone accept filters by type; setInputFiles bypasses the OS dialog, so react-dropzone
  // routes the wrong type into the `rejected` list → our toast fires
  await page.setInputFiles('input[type="file"]', [
    { name: "archive.zip", mimeType: "application/zip", buffer: Buffer.from("PK\x03\x04zip") },
    { name: "letter.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: Buffer.from("PK\x03\x04doc") },
  ]);
  await expect(page.getByText(/Only PDF files are allowed/)).toBeVisible({ timeout: 10_000 });
  // nothing queued
  await expect(page.getByRole("button", { name: /Upload\s+file/ })).toBeDisabled();
});
