// Playwright text-path E2E against `make run` (plan P4-4: local only). `make e2e` restarts
// DynamoDB Local and reseeds first, so every run starts from the synthetic fixtures. Tests run one
// at a time: the local fake model's script queue is shared by the whole app.

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://localhost:8000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
