# data-forge dashboard

[Evidence](https://evidence.dev/) による可視化ダッシュボード。  
SQL + Markdown で記述し、静的サイト（`build/`）を生成する。  
将来的に Cloudflare Pages 等へ配信する想定。

## データソース

`apps/pipeline` が出力した SQLite を参照する（**非コミット**。ローカルにパイプライン出力が必要）。
パスはソースディレクトリ基準の相対（Evidence sqlite コネクタ仕様）。

ソースは**粒度**で対称に分かれる（Evidence は「1コネクタ=1 SQLite」のため fact×粒度でディレクトリを割る）:

- `*_prefecture` … **都道府県粒度**。県集約まで済ませた export。`.sql` は素の射影のみ。
- `*_city` … **サンプル市区町村（印西市）粒度**。市区町村粒度の時系列から対象市区町村だけを抽出したもの。Evidence は結果 parquet を公開ビルドへ丸ごと同梱するため、公開範囲のみを抽出している。

| ソース                                                                           | 参照先 SQLite                                             | 内容                                          |
| -------------------------------------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------- |
| [census_prefecture](sources/census_prefecture/connection.yaml)                   | `census_population_prefecture_timeseries.sqlite`          | 都道府県別 男女別人口（1980〜2020）           |
| [census_age_prefecture](sources/census_age_prefecture/connection.yaml)           | `census_population_by_age_prefecture_timeseries.sqlite`   | 都道府県別 年齢3区分×男女別人口（1980〜2020） |
| [census_daynight_prefecture](sources/census_daynight_prefecture/connection.yaml) | `census_daynight_population_prefecture_timeseries.sqlite` | 都道府県別 昼夜間人口（1990〜2020）           |
| [census_city](sources/census_city/connection.yaml)                               | `census_population_timeseries.sqlite`                     | サンプル市 男女別人口（合併畳み込み済）       |
| [census_city_raw](sources/census_city_raw/connection.yaml)                       | `census_population_timeseries_raw.sqlite`                 | サンプル市 合併畳み込み無し版（比較用）       |
| [census_age_city](sources/census_age_city/connection.yaml)                       | `census_population_by_age_timeseries.sqlite`              | サンプル市 年齢3区分×男女別人口               |
| [census_daynight_city](sources/census_daynight_city/connection.yaml)             | `census_daynight_population_timeseries.sqlite`            | サンプル市 昼夜間人口                         |

### SQLite の生成

県粒度3表は `--join prefecture`（既定）で市区町村アトムを県へ集約して出力する。市区町村粒度3表は既定で
**合併畳み込み済み（`default_join="aggregate_to_base"`）**＝市制施行や合併で消えた旧コードを後継自治体へ
畳むため、サンプル市の連続時系列を作れる（例: 印西市 12231 は 1996年の市制施行前が別コードだが、
畳み込みで 1980年から連続に）。

```bash
cd apps/pipeline
# 都道府県粒度（county rollup）
uv run data-forge export population_prefecture_timeseries          # census_population_prefecture_timeseries.sqlite
uv run data-forge export population_by_age_prefecture_timeseries   # census_population_by_age_prefecture_timeseries.sqlite
uv run data-forge export daynight_population_prefecture_timeseries # census_daynight_population_prefecture_timeseries.sqlite
# 市区町村粒度（サンプル市抽出の材料。畳込済）
uv run data-forge export population_timeseries           # census_population_timeseries.sqlite
uv run data-forge export population_by_age_timeseries    # census_population_by_age_timeseries.sqlite
uv run data-forge export daynight_population_timeseries  # census_daynight_population_timeseries.sqlite
# 畳み込み有り/無しの比較デモ専用（生 union 版）
uv run data-forge export population_timeseries_raw       # census_population_timeseries_raw.sqlite
```

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
├── pages/                              # ダッシュボードのページ（.md）
├── sources/census_prefecture/         # 都道府県別 男女別人口
├── sources/census_age_prefecture/     # 都道府県別 年齢3区分×男女別人口
├── sources/census_daynight_prefecture/# 都道府県別 昼夜間人口
├── sources/census_city/               # サンプル市 男女別人口
├── sources/census_city_raw/           # サンプル市 合併畳み込み無し版（比較用）
├── sources/census_age_city/           # サンプル市 年齢3区分×男女別人口
├── sources/census_daynight_city/      # サンプル市 昼夜間人口
└── evidence.config.yaml
```
