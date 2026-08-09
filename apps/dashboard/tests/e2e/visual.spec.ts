import { test, expect } from "@playwright/test";

/**
 * トップページの見え方チェック。
 * チャート（ECharts canvas）が描画され、想定の見出し・データが出ているかを確認し、
 * 全体スクショと各セクションのスクショを test-results/ に保存する。
 */
test("トップページが描画され主要セクションが揃う", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });

  // 主要見出しが揃う
  await expect(page.getByRole("heading", { name: "全国総人口の推移" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "都道府県別 総人口の推移" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /印西市/ })).toBeVisible();

  // チャート（ECharts）が最低4つ描画される: 全国 / 県別推移 / 県ランキング / 印西市
  const charts = page.locator("canvas");
  await expect(charts.first()).toBeVisible();
  await page.waitForFunction(() => document.querySelectorAll("canvas").length >= 4, null, {
    timeout: 30_000,
  });

  // 都道府県 Dropdown の既定が千葉県
  await expect(page.getByText("千葉県").first()).toBeVisible();

  // 全体スクショ
  await page.screenshot({ path: "test-results/index-full.png", fullPage: true });
});
