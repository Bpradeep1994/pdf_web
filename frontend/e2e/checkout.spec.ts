import { test, expect } from "@playwright/test";

test("checkout form adapts to the selected payment provider", async ({ page }) => {
  // register → authed session
  await page.goto("/register");
  await page.getByPlaceholder("Jane Smith").fill("Checkout Tester");
  await page.getByPlaceholder("you@example.com").fill(`co_${Date.now()}@example.com`);
  const pw = page.getByPlaceholder("••••••••");
  await pw.nth(0).fill("TestPass123!");
  await pw.nth(1).fill("TestPass123!");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

  await page.goto("/billing/checkout?plan=business&interval=monthly");
  const cardInput = page.getByPlaceholder("4242 4242 4242 4242");

  // default = Stripe → card fields visible
  await expect(cardInput).toBeVisible();

  // UPI provider → UPI ID input, works with any UPI app, no card fields
  await page.getByRole("button", { name: "UPI", exact: true }).click();
  await expect(cardInput).toBeHidden();
  await expect(page.getByPlaceholder("yourname@upi")).toBeVisible();
  await expect(page.getByText(/any UPI app \(Google Pay, PhonePe, Paytm, BHIM…\)/)).toBeVisible();

  // Apple Pay → same, branded
  await page.getByRole("button", { name: "Apple Pay", exact: true }).click();
  await expect(cardInput).toBeHidden();
  await expect(page.getByText("your saved Apple Pay payment method")).toBeVisible();

  // PayPal → paypal panel
  await page.getByRole("button", { name: "PayPal", exact: true }).click();
  await expect(cardInput).toBeHidden();
  await expect(page.getByText(/complete payment via PayPal/)).toBeVisible();

  // Razorpay → UPI method shows UPI ID input; netbanking shows bank picker
  await page.getByRole("button", { name: "Razorpay", exact: true }).click();
  await expect(cardInput).toBeVisible(); // razorpay defaults to card
  // .last() → the method-row UPI button (the provider row also has a "UPI" button)
  await page.getByRole("button", { name: "UPI", exact: true }).last().click();
  await expect(cardInput).toBeHidden();
  await expect(page.getByPlaceholder("yourname@upi")).toBeVisible();
  await page.getByRole("button", { name: "Net Banking", exact: true }).click();
  await expect(page.getByText(/redirected to HDFC Bank/)).toBeVisible();

  // back to Stripe → card fields return
  await page.getByRole("button", { name: "Card (Stripe)", exact: true }).click();
  await expect(cardInput).toBeVisible();

  // ── expired card is rejected before any OTP is sent ──
  await cardInput.fill("4242 4242 4242 4242");
  await page.getByPlaceholder("MM / YY").fill("01/20");   // long past
  await page.getByPlaceholder("CVC").fill("123");
  await page.getByRole("button", { name: /^Pay \$/ }).click();
  await expect(page.getByText("Card expired — check the expiry date")).toBeVisible();
  await expect(page.getByText("Verify your payment")).toHaveCount(0); // never reached OTP

  // valid future expiry proceeds to the OTP step
  await page.getByPlaceholder("MM / YY").fill("12/29");
  await page.getByRole("button", { name: /^Pay \$/ }).click();
  await expect(page.getByText("Verify your payment")).toBeVisible({ timeout: 15_000 });
});
