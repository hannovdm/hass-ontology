import { defineConfig, devices } from "@playwright/test";

const useHomeAssistant = Boolean(process.env.HA_URL);

export default defineConfig({
  testDir: ".",
  testMatch: "**/*.spec.js",
  fullyParallel: false,
  reporter: "list",
  use: {
    baseURL: process.env.HA_URL || "http://127.0.0.1:4173",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: useHomeAssistant
    ? undefined
    : {
        command: "node fixture-server.js",
        url: "http://127.0.0.1:4173/tests/browser/graph-fixture.html",
        reuseExistingServer: true,
      },
  projects: [
    {
      name: "desktop-chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "mobile-chromium",
      use: { ...devices["Pixel 5"], viewport: { width: 390, height: 844 } },
    },
  ],
});