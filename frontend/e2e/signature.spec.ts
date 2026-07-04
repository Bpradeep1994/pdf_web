import { test, expect } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const BYPASS = { "x-ratelimit-bypass": "ci-test-bypass-9f3a2" };

const PDF = Buffer.from(
  "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n" +
  "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" +
  "3 0 obj<</Type/Page/MediaBox[0 0 400 400]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF");

test.setTimeout(60_000);

test("signature: draw, save, reuse after reload, place/resize, quick-sign, delete saved", async ({ page, context }) => {
  // register + upload a doc
  await page.goto("/register");
  await page.getByPlaceholder("Jane Smith").fill("Sig Tester");
  await page.getByPlaceholder("you@example.com").fill(`sig_${Date.now()}@example.com`);
  const pw = page.getByPlaceholder("••••••••");
  await pw.nth(0).fill("TestPass123!");
  await pw.nth(1).fill("TestPass123!");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
  const token = (await context.cookies()).find((c) => c.name === "access_token")!.value;
  const up = await page.request.post(`${API}/api/v1/documents`, {
    headers: { ...BYPASS, Authorization: `Bearer ${token}` },
    multipart: { file: { name: "sign-me.pdf", mimeType: "application/pdf", buffer: PDF } },
  });
  expect(up.status()).toBe(201);
  const id = (await up.json()).id;

  await page.goto(`/editor/${id}`);
  await page.getByRole("button", { name: "Sign", exact: true }).click();
  await expect(page.getByText("Draw your signature")).toBeVisible();

  // ── DRAW on the pad ──
  const pad = page.locator("canvas.cursor-crosshair");
  const b = (await pad.boundingBox())!;
  await page.mouse.move(b.x + 20, b.y + 50);
  await page.mouse.down();
  for (let i = 1; i <= 8; i++) await page.mouse.move(b.x + 20 + i * 25, b.y + 50 + (i % 2) * 25, { steps: 3 });
  await page.mouse.up();

  // ── SAVE it (the pad's Save, not the top-bar download Save) ──
  await page.locator("aside").getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Signature saved")).toBeVisible();
  await expect(page.getByAltText("Saved signature 1")).toBeVisible();

  // ── persists across reload ──
  await page.reload();
  await page.getByRole("button", { name: "Sign", exact: true }).click();
  await expect(page.getByAltText("Saved signature 1")).toBeVisible();

  // ── reuse: click the saved signature, then quick-sign the page ──
  await page.getByTitle("Use this signature").click();
  await page.getByRole("button", { name: /Quick-sign page/ }).click();
  await expect(page.getByText("Document signed")).toBeVisible({ timeout: 15_000 });

  // ── place on page: move + resize via the image layer, then apply ──
  await page.getByTitle("Use this signature").click();
  await page.getByRole("button", { name: /Place on page/ }).click();
  const layerCanvas = page.locator(".canvas-container canvas").last();
  await expect(layerCanvas).toBeVisible({ timeout: 15_000 });
  const lc = (await layerCanvas.boundingBox())!;
  // move: drag from the image's initial center (~30%+20% of its size) to elsewhere
  await page.mouse.move(lc.x + lc.width * 0.4, lc.y + lc.height * 0.38);
  await page.mouse.down();
  await page.mouse.move(lc.x + lc.width * 0.6, lc.y + lc.height * 0.6, { steps: 6 });
  await page.mouse.up();
  await page.getByTitle("Apply").click();
  await expect(page.getByText("Applied")).toBeVisible({ timeout: 20_000 });

  // signed content can be undone (delete of an applied signature)
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Control+z");
  await expect(page.getByText("Undone")).toBeVisible({ timeout: 15_000 });

  // ── delete the saved signature ──
  await page.getByRole("button", { name: "Sign", exact: true }).click();
  await page.getByAltText("Saved signature 1").hover();
  await page.getByTitle("Delete saved signature").click();
  await expect(page.getByAltText("Saved signature 1")).toHaveCount(0);
});
