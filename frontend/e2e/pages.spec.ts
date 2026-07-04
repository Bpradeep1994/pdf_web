import { test, expect } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const BYPASS = { "x-ratelimit-bypass": "ci-test-bypass-9f3a2" };

const PDF = Buffer.from(
  "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n" +
  "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" +
  "3 0 obj<</Type/Page/MediaBox[0 0 400 400]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF");

test.setTimeout(60_000);

test("page menu: add, duplicate, rotate, move, extract, delete from thumbnails", async ({ page, context }) => {
  await page.goto("/register");
  await page.getByPlaceholder("Jane Smith").fill("Pages Tester");
  await page.getByPlaceholder("you@example.com").fill(`pg_${Date.now()}@example.com`);
  const pw = page.getByPlaceholder("••••••••");
  await pw.nth(0).fill("TestPass123!");
  await pw.nth(1).fill("TestPass123!");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
  const token = (await context.cookies()).find((c) => c.name === "access_token")!.value;
  const up = await page.request.post(`${API}/api/v1/documents`, {
    headers: { ...BYPASS, Authorization: `Bearer ${token}` },
    multipart: { file: { name: "pages.pdf", mimeType: "application/pdf", buffer: PDF } },
  });
  const id = (await up.json()).id;

  await page.goto(`/editor/${id}`);
  await expect(page.getByText("1 / 1")).toBeVisible({ timeout: 15_000 });

  const openMenu = async (p: number) => {
    await page.getByTitle(`Page ${p} actions`).click({ force: true }); // hover-revealed
  };

  // add blank page after page 1 → 2 pages
  await openMenu(1);
  await page.getByRole("button", { name: "Add blank page after" }).click();
  await expect(page.getByText("Blank page added")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("1 / 2")).toBeVisible({ timeout: 15_000 });

  // duplicate page 1 → 3 pages
  await openMenu(1);
  await page.getByRole("button", { name: "Duplicate page" }).click();
  await expect(page.getByText("Page duplicated")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/\/ 3/)).toBeVisible({ timeout: 15_000 });

  // rotate page 1
  await openMenu(1);
  await page.getByRole("button", { name: "Rotate 90°" }).click();
  await expect(page.getByText("Page rotated")).toBeVisible({ timeout: 15_000 });

  // move page 2 up (rearrange)
  await openMenu(2);
  await page.getByRole("button", { name: "Move up" }).click();
  await expect(page.getByText("Page moved up")).toBeVisible({ timeout: 15_000 });

  // extract page 1 to a new document
  await openMenu(1);
  await page.getByRole("button", { name: "Extract to new PDF" }).click();
  await expect(page.getByText(/Extracted to a new document/)).toBeVisible({ timeout: 15_000 });

  // delete page 3 → back to 2 pages
  await openMenu(3);
  await page.getByRole("button", { name: "Delete page" }).click();
  await expect(page.getByText("Page deleted")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/\/ 2/)).toBeVisible({ timeout: 15_000 });
});
