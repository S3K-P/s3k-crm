import { defineConfig, devices } from '@playwright/test';

/* ============================================================
   END-TO-END CONFIGURATION

   These tests drive a real browser against a real Next.js server
   talking to a real API and a real database. Nothing is mocked,
   because the things worth covering here — that a session
   survives a reload, that a rep and a manager see different
   numbers on the same screen — are exactly the things a mock
   would assert into existence.

   The suite seeds its own tenant through the public API in
   `global-setup.ts`, so it needs no fixture database and can run
   against any environment that will accept a signup.
   ============================================================ */

/** The app under test. Overridden in CI, where the server is started for us. */
const BASE_URL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3100';

/** The API the app talks to. Must match what the frontend was built with. */
const API_URL = process.env.E2E_API_URL ?? 'http://127.0.0.1:8100';

export default defineConfig({
  testDir: './e2e',
  // Every spec seeds through one shared tenant, and several assert on list
  // contents. Running files in parallel would have them writing records into
  // each other's assertions.
  workers: 1,
  fullyParallel: false,
  // A test that only passes on the second attempt is a test that has told you
  // something; CI gets one retry to absorb genuine network flake, and locally
  // a failure should stay failed.
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [['github'], ['list']] : [['list']],

  globalSetup: './e2e/global-setup.ts',

  use: {
    baseURL: BASE_URL,
    // Kept only for failures: an artefact per passing test is noise nobody opens.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Video needs a separate ffmpeg binary. CI installs it with the browser;
    // a developer machine that cannot reach the Playwright CDN would otherwise
    // fail every test on the recorder rather than on the assertion, which is
    // the least useful failure available. The trace above already carries
    // screenshots and a DOM snapshot per step.
    video: process.env.CI ? 'retain-on-failure' : 'off',
  },

  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Playwright's bundled Chromium by default. `PLAYWRIGHT_CHANNEL=chrome`
        // falls back to a locally installed Chrome, which is what makes the
        // suite runnable on a machine that cannot reach the Playwright CDN.
        // CI leaves this unset so it tests the pinned browser.
        ...(process.env.PLAYWRIGHT_CHANNEL
          ? { channel: process.env.PLAYWRIGHT_CHANNEL }
          : {}),
      },
    },
  ],

  metadata: { apiUrl: API_URL },
});
