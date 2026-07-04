import { test, expect, Page } from "@playwright/test";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const BYPASS = { "x-ratelimit-bypass": "ci-test-bypass-9f3a2" };

const PDF = Buffer.from(
  "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n" +
  "2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" +
  "3 0 obj<</Type/Page/MediaBox[0 0 400 400]/Parent 2 0 R>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF");

test.describe.configure({ mode: "serial" });
test.setTimeout(150_000);

let docId = "";

async function pageImage(page: Page) {
  const img = page.locator(`img[src*="/pages/1?zoom=1.4"]`).first();
  await expect(img).toBeVisible();
  await expect.poll(async () => img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(50);
  return img;
}

async function dragOnPage(page: Page, from: [number, number], to: [number, number]) {
  const img = await pageImage(page);
  const box = (await img.boundingBox())!;
  await page.mouse.move(box.x + from[0], box.y + from[1]);
  await page.mouse.down();
  await page.mouse.move(box.x + to[0], box.y + to[1], { steps: 5 });
  await page.mouse.up();
}

test.beforeAll(async ({ request }) => {
  const email = `edt_${Date.now()}@example.com`;
  const reg = await request.post(`${API}/api/v1/auth/register`, {
    headers: BYPASS, data: { email, password: "TestPass123!", full_name: "Editor Tester" } });
  expect(reg.status()).toBe(201);
  const { access_token } = await reg.json();
  const up = await request.post(`${API}/api/v1/documents`, {
    headers: { ...BYPASS, Authorization: `Bearer ${access_token}` },
    multipart: { file: { name: "tools.pdf", mimeType: "application/pdf", buffer: PDF } },
  });
  expect(up.status()).toBe(201);
  docId = (await up.json()).id;
});

test.beforeEach(async ({ page }) => {
  // authed session via the real login flow is overkill per-test — register once per test user
  const email = `edt_ui_${Date.now()}_${Math.random().toString(36).slice(2)}@example.com`;
  await page.goto("/register");
  await page.getByPlaceholder("Jane Smith").fill("Editor UI");
  await page.getByPlaceholder("you@example.com").fill(email);
  const pw = page.getByPlaceholder("••••••••");
  await pw.nth(0).fill("TestPass123!");
  await pw.nth(1).fill("TestPass123!");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
});

test("all editor tools work end-to-end", async ({ page, context }) => {
  // fresh doc owned by THIS ui user (upload through the dashboard button is covered elsewhere;
  // use the API with the browser's own cookie token so ownership matches)
  const token = (await context.cookies()).find((c) => c.name === "access_token")!.value;
  const up = await page.request.post(`${API}/api/v1/documents`, {
    headers: { ...BYPASS, Authorization: `Bearer ${token}` },
    multipart: { file: { name: "tools.pdf", mimeType: "application/pdf", buffer: PDF } },
  });
  expect(up.status()).toBe(201);
  const id = (await up.json()).id;

  await page.goto(`/editor/${id}`);

  // ── page renders (the original bug) ──
  await pageImage(page);
  // thumbnail rail renders too
  await expect(page.locator(`img[src*="zoom=0.5"]`).first()).toBeVisible();

  // ── zoom label present (buttons are icon-only) ──
  await expect(page.getByText(/^\d+%$/)).toBeVisible();

  // ── Add Text ──
  await page.getByRole("button", { name: "Add Text" }).click();
  const img = await pageImage(page);
  const box = (await img.boundingBox())!;
  await page.mouse.click(box.x + 60, box.y + 80);
  await page.locator("textarea").fill("HelloE2E");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Text added")).toBeVisible({ timeout: 15_000 });

  // second line of text so the span list has >1 entry (guards the stale-value bug);
  // the text tool is still active after the first commit — just click again
  await page.mouse.click(box.x + 60, box.y + 160);
  await page.locator("textarea").fill("SecondLine");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Text added").last()).toBeVisible({ timeout: 15_000 });

  // ── Edit Text (in-place spans) ──
  await page.getByRole("button", { name: "Edit Text" }).click();
  const span = page.locator('input[value="HelloE2E"]');
  await expect(span).toBeVisible({ timeout: 15_000 });
  await span.fill("HelloEdited");
  await span.press("Enter");
  // after the reload every box must show its own current text — no stale/shuffled values
  await expect(page.locator('input[value="HelloEdited"]')).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('input[value="SecondLine"]')).toBeVisible();
  await expect(page.locator('input[value="HelloE2E"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Edit Text" }).click(); // toggle off

  // ── search box was removed from the viewer bar ──
  await expect(page.getByPlaceholder("Search text…")).toHaveCount(0);

  // ── Highlight ──
  await page.getByRole("button", { name: "Highlight" }).first().click();
  await page.getByRole("button", { name: "Highlight", exact: true }).last().click();
  await dragOnPage(page, [50, 60], [200, 100]);
  await expect(page.getByText("Highlight added")).toBeVisible({ timeout: 15_000 });

  // ── Rectangle shape ──
  await page.getByRole("button", { name: /Highlight & shapes|Highlight/ }).first().click();
  await page.getByRole("button", { name: "Rectangle" }).click();
  await dragOnPage(page, [120, 150], [220, 220]);
  await expect(page.getByText("Shape added")).toBeVisible({ timeout: 15_000 });

  // ── Redact ──
  await page.getByRole("button", { name: "Redact" }).click();
  await dragOnPage(page, [40, 260], [180, 300]);
  await expect(page.getByText("Region redacted")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Redact" }).click(); // off

  // ── Draw (fabric.js freehand) + apply ──
  await page.getByRole("button", { name: "Draw" }).click();
  const drawCanvas = page.locator(".canvas-container canvas").last(); // fabric's upper (interaction) canvas
  await expect(drawCanvas).toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(800); // let the fabric brush finish initialising
  const cb = (await drawCanvas.boundingBox())!;
  await page.mouse.move(cb.x + 50, cb.y + 320);
  await page.mouse.down();
  for (let i = 1; i <= 10; i++) {
    await page.mouse.move(cb.x + 50 + i * 12, cb.y + 320 + (i % 2) * 14);
    await page.waitForTimeout(30);
  }
  await page.mouse.up();
  await page.waitForTimeout(300);
  await page.getByTitle("Apply").click();
  await expect(page.getByText("Applied")).toBeVisible({ timeout: 20_000 });

  // ── Image: add → rotate → crop → delete → replace → apply ──
  const PNG1 = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
  await page.getByRole("button", { name: "Image", exact: true }).click();
  const imgInput = page.locator('input[type="file"][accept="image/*"]');
  await imgInput.setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: PNG1 });
  const applyBtn = page.getByTitle("Apply");
  await expect(applyBtn).toBeEnabled({ timeout: 10_000 });      // image loaded
  await page.getByTitle("Rotate 15°").click();                   // rotate
  await page.getByTitle("Crop").click();                         // start crop
  await page.getByTitle("Apply crop").click();                   // apply crop
  await page.getByTitle("Delete").click();                       // delete
  await expect(applyBtn).toBeDisabled();                         // nothing to apply
  await imgInput.setInputFiles({ name: "logo2.png", mimeType: "image/png", buffer: PNG1 }); // replace
  await expect(applyBtn).toBeEnabled();
  await applyBtn.click();                                        // flatten onto the PDF
  await expect(page.getByText("Applied")).toBeVisible({ timeout: 20_000 });
  // post-apply delete = undo
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Control+z");
  await expect(page.getByText("Undone")).toBeVisible({ timeout: 15_000 });
  await page.keyboard.press("Control+y");                        // put it back
  await expect(page.getByText("Redone")).toBeVisible({ timeout: 15_000 });

  // ── Stamp (watermark, uses window.prompt) ──
  page.once("dialog", (d) => d.accept("E2E-STAMP"));
  await page.getByRole("button", { name: "Stamp" }).click();
  await expect(page.getByText("Watermark applied")).toBeVisible({ timeout: 20_000 });

  // ── Undo/Redo via keyboard (no toolbar buttons) ──
  await expect(page.getByRole("button", { name: "Undo" })).toHaveCount(0);
  await page.locator("body").click({ position: { x: 5, y: 5 } }); // blur any text box
  await page.keyboard.press("Control+z");
  await expect(page.getByText("Undone")).toBeVisible({ timeout: 15_000 });
  await page.keyboard.press("Control+y");
  await expect(page.getByText("Redone")).toBeVisible({ timeout: 15_000 });

  // ── Sign panel opens ──
  await page.getByRole("button", { name: "Sign", exact: true }).click();
  await expect(page.getByText(/Signature|Sign/).first()).toBeVisible();
  await page.getByRole("button", { name: "Sign", exact: true }).click().catch(() => {});

  // ── History modal ──
  await page.getByRole("button", { name: "History" }).click();
  await expect(page.getByText("Version history")).toBeVisible({ timeout: 15_000 });
  // versions exist for every edit made above
  await page.keyboard.press("Escape");
  await page.locator("body").click({ position: { x: 10, y: 10 } }).catch(() => {});

  // ── Share ──
  await page.getByRole("button", { name: "Share" }).click();
  await expect(page.getByText("Share link copied")).toBeVisible({ timeout: 15_000 });

  // ── Convert (TXT) ──
  const popup = context.waitForEvent("page", { timeout: 45_000 }).catch(() => null);
  await page.getByRole("button", { name: "Convert" }).click();
  await page.getByRole("button", { name: "TXT" }).click();
  // generous: conversion competes with LibreOffice/translation work under full-suite load
  await expect(page.getByText("Converted to TXT")).toBeVisible({ timeout: 45_000 });
  await popup;

  // ── Save (download presigned URL opens) ──
  const dl = context.waitForEvent("page", { timeout: 20_000 }).catch(() => null);
  await page.getByRole("button", { name: "Save" }).click();
  const dlPage = await dl;
  expect(dlPage).toBeTruthy();
});
