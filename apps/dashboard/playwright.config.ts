import { defineConfig, devices } from "@playwright/test";

/**
 * Evidence ダッシュボードの見え方チェック用 E2E 設定。
 * webServer で Evidence dev を専用ポート起動し、tests/e2e のスクショ/描画確認を回す。
 * （参考: okmethod/ygo-solitaire の playwright.config.ts を Evidence 向けに調整）
 */
const PORT = 5174;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: "html",
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "on-first-retry",
    // Evidence の描画は横長を想定。チャートが潰れないデスクトップ幅で撮る。
    viewport: { width: 1440, height: 900 },
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: {
    // Evidence dev は初回にソース評価＋Vite 起動で時間がかかるため timeout を長めに。
    command: `npx evidence dev --port ${PORT}`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 180 * 1000,
  },
});
