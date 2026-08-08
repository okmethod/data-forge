# data-forge dashboard

[Evidence](https://evidence.dev/) による可視化ダッシュボード。  
SQL + Markdown で記述し、静的サイト（`build/`）を生成する。  
将来的に Cloudflare Pages 等へ配信する想定。

## データソース

`apps/pipeline` が出力した SQLite を参照する。

- 定義: [sources/census/connection.yaml](sources/census/connection.yaml)
- 参照先: `data/processed/census_population_2020.sqlite`（**非コミット**。ローカルにパイプライン出力が必要）
- パスはソースディレクトリ基準の相対（Evidence sqlite コネクタ仕様）

## 使い方

```bash
cd apps/dashboard
npm install          # 初回のみ
npm run sources      # SQLite からデータを取り込み（.evidence/ にキャッシュ）
npm run dev          # ローカル開発サーバ（ブラウザ自動起動）
npm run build        # 静的サイトを build/ に出力
npm run build:strict # クエリ/描画エラーを失敗扱いにしてビルド（CI 向け）
```

データソースを更新したら `npm run sources` を再実行する。

## 構成

```
apps/dashboard/
├── pages/            # ダッシュボードのページ（.md）
├── sources/census/   # SQLite コネクタ定義とクエリ
└── evidence.config.yaml
```
