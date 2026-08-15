import { test, expect, type Page } from "@playwright/test";

/**
 * 各ページの見え方チェック。
 * チャート（ECharts canvas）が描画され、想定の見出し・データが出ているかを確認し、
 * 全体スクショを test-results/ に保存する。
 * 構成: index=概要ランディング / census=人口 / aging=年齢 / daynight=昼夜間 /
 *       inzai=印西市ケーススタディ（3指標横断）。
 */

// 指定枚数の ECharts canvas が描画されるまで待つ（初回コンパイルが重いページ向けに長め）。
async function waitCharts(page: Page, n: number) {
  await page.waitForFunction((min) => document.querySelectorAll("canvas").length >= min, n, {
    timeout: 45_000,
  });
}

test("トップ（概要ランディング）が描画される", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await waitCharts(page, 1);

  await expect(page.getByRole("heading", { name: "収録データ" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /公開範囲/ })).toBeVisible();
  // 収録データ表から各ページへのリンク
  await expect(page.getByRole("link", { name: "人口", exact: true }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "印西市ケーススタディ" }).first()).toBeVisible();

  await page.screenshot({ path: "test-results/index-full.png", fullPage: true });
});

test("人口ページ（全国→県→サンプル市）が描画される", async ({ page }) => {
  await page.goto("/census", { waitUntil: "networkidle" });
  await waitCharts(page, 4);

  await expect(page.getByRole("heading", { name: "全国：総人口の推移" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "サンプル市：千葉県印西市" })).toBeVisible();
  // 都道府県 Dropdown の既定が千葉県
  await expect(page.getByText("千葉県").first()).toBeVisible();

  await page.screenshot({ path: "test-results/census-full.png", fullPage: true });
});

test("年齢構成ページが描画される", async ({ page }) => {
  await page.goto("/aging", { waitUntil: "networkidle" });
  await waitCharts(page, 6);

  await expect(page.getByRole("heading", { name: "全国：高齢化率の推移" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /5歳階級で見る一世紀/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /高齢化率ランキング/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "サンプル市：千葉県印西市" })).toBeVisible();

  await page.screenshot({ path: "test-results/aging-full.png", fullPage: true });
});

test("昼夜間人口ページが描画される", async ({ page }) => {
  await page.goto("/daynight", { waitUntil: "networkidle" });
  await waitCharts(page, 3);

  await expect(page.getByRole("heading", { name: /昼夜間人口比率ランキング/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "サンプル市：千葉県印西市" })).toBeVisible();

  await page.screenshot({ path: "test-results/daynight-full.png", fullPage: true });
});

test("印西市ケーススタディが描画される", async ({ page }) => {
  await page.goto("/inzai", { waitUntil: "networkidle" });
  await waitCharts(page, 4);

  await expect(page.getByRole("heading", { name: /印西市の人口：3万人/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /全国の中の印西市/ })).toBeVisible();

  await page.screenshot({ path: "test-results/inzai-full.png", fullPage: true });
});
