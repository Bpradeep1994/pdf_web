import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    headless: true,
    // The whole suite runs from one IP; bypass the gateway rate limiter so
    // back-to-back tests don't 429 each other (token must match the gateway env).
    extraHTTPHeaders: { "x-ratelimit-bypass": process.env.RATE_LIMIT_BYPASS_TOKEN || "ci-test-bypass-9f3a2" },
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    // Mobile viewport + touch (same engine, no extra browser download).
    // User journeys only — editor drag/draw interactions are desktop-first.
    {
      name: "mobile-chrome",
      use: { ...devices["Pixel 7"] },
      testMatch: /(smoke|checkout|email-flows)\.spec\.ts/,
    },
  ],
});
