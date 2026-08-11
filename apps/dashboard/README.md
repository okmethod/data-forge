# data-forge dashboard

[Evidence](https://evidence.dev/) による可視化ダッシュボード。  
SQL + Markdown で記述し、静的サイト（`build/`）を生成する。  
将来的に Cloudflare Pages 等へ配信する想定。

## データソース

`apps/pipeline` が出力した SQLite を参照する（**非コミット**。ローカルにパイプライン出力が必要）。
パスはソースディレクトリ基準の相対（Evidence sqlite コネクタ仕様）。

| ソース                                                     | 参照先 SQLite                                  | 内容                                        |
| ---------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------- |
| [census](sources/census/connection.yaml)                   | `census_population_timeseries.sqlite`          | 男女別人口 時系列（1980〜2020・合併畳込済） |
| [census_raw](sources/census_raw/connection.yaml)           | `census_population_timeseries_raw.sqlite`      | 上記人口の**畳み込み無し（生）**版・比較用  |
| [census_age](sources/census_age/connection.yaml)           | `census_population_by_age_timeseries.sqlite`   | 年齢3区分×男女別人口 時系列（1980〜2020）   |
| [census_daynight](sources/census_daynight/connection.yaml) | `census_daynight_population_timeseries.sqlite` | 昼夜間人口 時系列（1990〜2020）             |

各ソースの `.sql` は **都道府県粒度まで畳んだ結果のみ**を材料化する（Evidence はソースの結果 parquet を
公開ビルドへ丸ごと同梱するため、市区町村グレインを流出させない）。

### SQLite の生成

時系列3表は**合併畳み込み済み（`--join aggregate_to_base`）**で出力する。  
既定の `export`（=`union`＝生）だと、市制施行や合併で消えた旧コードが畳まれず、サンプル市の連続時系列が作れない。  
（例: 印西市 12231 は 1996年の市制施行前が別コードのため union では 2000年以降しか出ない）

```bash
cd apps/pipeline
uv run data-forge export population_timeseries          --join aggregate_to_base  # census_population_timeseries.sqlite
uv run data-forge export population_by_age_timeseries   --join aggregate_to_base  # census_population_by_age_timeseries.sqlite
uv run data-forge export daynight_population_timeseries --join aggregate_to_base  # census_daynight_population_timeseries.sqlite
```

`census_raw`（畳み込み有り/無しの比較デモ専用）の SQLite は上記とは別に、生（`union`）版を作って退避する:

```bash
uv run data-forge export population_timeseries                # union(生)
cp ../../data/processed/census_population_timeseries.sqlite \
   ../../data/processed/census_population_timeseries_raw.sqlite
uv run data-forge export population_timeseries --join aggregate_to_base  # 畳込済を復元（census 用に戻す）
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
├── pages/                     # ダッシュボードのページ（.md）
├── sources/census/            # 男女別人口（SQLite コネクタ定義とクエリ）
├── sources/census_raw/        # 人口の畳み込み無し（生）版・比較用
├── sources/census_age/        # 年齢3区分×男女別人口
├── sources/census_daynight/   # 昼夜間人口
└── evidence.config.yaml
```
