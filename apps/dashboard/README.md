# data-forge dashboard

[Evidence](https://evidence.dev/) による可視化ダッシュボード。  
SQL + Markdown で記述し、静的サイト（`build/`）を生成する。  
静的サイトを Cloudflare Pages へ、DuckDB-WASM のみ R2 から配信する。

公開URL: https://data-forge-dashboard.pages.dev/

---

## ディレクトリ構成

```text
apps/dashboard/
├── pages/                # ダッシュボードのページ（.md）
├── sources/              # Evidence データソース（fact×粒度で分割）
├── scripts/
│   └── offload-wasm.mjs  # deploy 前に DuckDB-WASM を R2 へ退避（25MiB 制限回避）
├── public_scope.yaml     # 公開範囲ポリシー（SSoT。検査は pipeline の public-scope-check）
├── r2-cors.json          # R2 バケットの CORS 設定
├── wrangler.toml         # Cloudflare Pages デプロイ設定
└── evidence.config.yaml
```

---

## データソース

`apps/pipeline` が精製した **parquet** を参照する（**非コミット**。ローカルにパイプライン出力が必要）。
各ソースは `type: duckdb` で、読取先は `.sql` の `read_parquet('../../data/processed/<stem>.parquet')` が持つ（パスは Evidence プロジェクトルート＝`apps/dashboard` 基準）。
出典メタは同梱の `<stem>.meta.json` を `read_json` で読む（各ソースの `source_meta.sql`）。

ソースは **fact × 粒度** で対称に分かれる（1ソース＝1論理テーブル）:

- `*_prefecture` … **都道府県粒度**。県集約まで済ませた精製系列。`.sql` は素の射影のみ。
- `*_municipality` … **サンプル市区町村（印西市）粒度**。市区町村系列から公開範囲だけを `where area_code in (...)` で抽出（Evidence は結果 parquet を公開ビルドへ丸ごと同梱するため）。
- 粒度 suffix を持たない fact（`census_households` / `census_industry` 等の世帯・就業系）は、排他粒度で分離された **全国（`_national`）＋都道府県（`_prefecture`）の2 parquet を `.sql` 内で `union all`** し、「全国(00000)＋47県」の1論理テーブルへ合成する（全国はベースライン。pipeline README §命名規則「全国行の同梱禁止（排他粒度）」に対応）。

各 fact の**出力スキーマ・年カバレッジ・出典**は [docs/distributions/](../../docs/distributions/) と [apps/pipeline/README.md](../pipeline/README.md) の命名規則が正典。
下表は**ダッシュ固有の合成**＝「どの精製 stem を・どう組んで・どのページに出すか」の地図（スキーマ等は重複させず上記へ委譲）:

| ソース (`sources/`)                  | 参照 stem（`data/processed/*.parquet`）                                                | 合成                            | 主な表示ページ    |
| ------------------------------------ | -------------------------------------------------------------------------------------- | ------------------------------- | ----------------- |
| `census_population_prefecture`       | `census_population_prefecture_timeseries`                                              | 素の射影（県）                  | population, inzai |
| `census_population_municipality`     | `census_population_municipality_timeseries`                                            | サンプル市抽出                  | population, inzai |
| `census_population_municipality_raw` | `census_population_municipality_timeseries_raw`                                        | サンプル市抽出（畳込無=比較用） | population        |
| `census_age3class_prefecture`        | `census_age3class_prefecture_timeseries`                                               | 素の射影（県）                  | age_3class        |
| `census_age3class_municipality`      | `census_age3class_municipality_timeseries`                                             | サンプル市抽出                  | age_3class, inzai |
| `census_age5year_municipality`       | `census_age5year_municipality_timeseries`                                              | サンプル市抽出（国籍軸）        | age_5year         |
| `census_daynight_prefecture`         | `census_daynight_prefecture_timeseries`                                                | 素の射影（県）                  | daynight          |
| `census_daynight_municipality`       | `census_daynight_municipality_timeseries`                                              | サンプル市抽出                  | daynight, inzai   |
| `census_age5year_prefecture`         | `census_age5year_national_timeseries` ＋ `census_age5year_prefecture_timeseries`       | `union`（全国＋県）             | age_5year         |
| `census_households`                  | `census_households_national_timeseries` ＋ `census_households_prefecture_timeseries`   | `union`（全国＋県）             | households        |
| `census_family_type`                 | `census_family_type_national_timeseries` ＋ `census_family_type_prefecture_timeseries` | `union`（全国＋県）             | family_type       |
| `census_labor_force`                 | `census_labor_force_national_timeseries` ＋ `census_labor_force_prefecture_timeseries` | `union`（全国＋県）             | labor_force       |
| `census_industry`                    | `census_industry_national_timeseries` ＋ `census_industry_prefecture_timeseries`       | `union`（全国＋県）             | industry          |
| `census_occupation_major10`          | `census_occupation_major10_national_timeseries` ＋ `..._prefecture_timeseries`         | `union`（全国＋県）             | occupation        |
| `census_occupation_major12`          | `census_occupation_major12_national_timeseries` ＋ `..._prefecture_timeseries`         | `union`（全国＋県）             | occupation        |

> 出典メタは各ソースの `source_meta.sql` が `<stem>.meta.json` を `read_json` で読む（`union` ソースは全国＋県の2 meta を集約・単一 ID は重複排除）。

### parquet の生成

パイプラインで各データセットを `run`（取得→クレンジング→出力）すると、`data/processed/` に `<stem>.parquet` / `<stem>.meta.json`（＋ csv / sqlite / duckdb）が生成される。
市区町村粒度は既定で**合併畳み込み済み`default_join="aggregate_to_base"`）**＝消えた旧コードを後継自治体へ畳むため、サンプル市の連続時系列を作れる（例: 印西市 12231 は 1996年の市制施行前が別コードだが畳み込みで 1980年から連続に）。
データセット一覧と実行方法は [apps/pipeline/README.md](../pipeline/README.md) が正典。

```bash
cd apps/pipeline
uv run poe run <dataset_key>   # 例: population_prefecture_timeseries / age5year_national_timeseries
```

---

## 使い方

```bash
cd apps/dashboard
npm install          # 初回のみ
npm run sources      # parquet からデータを取り込み（.evidence/ にキャッシュ）
npm run dev          # ローカル開発サーバ（ブラウザ自動起動）
npm run build        # 静的サイトを build/ に出力
npm run build:strict # クエリ/描画エラーを失敗扱いにしてビルド（CI 向け）
```

データソースを更新したら `npm run sources` を再実行する。

---

## デプロイ（Cloudflare Pages）

静的サイト（`build/`）を Cloudflare Pages へ手元から直接アップする（CI は使わない）。
デプロイ設定は [wrangler.toml](wrangler.toml)（プロジェクト名・出力先 `build/`）が正典。

```bash
cd apps/dashboard
npm install                # 初回のみ（wrangler を含む devDependencies を取得）
npx wrangler login         # 初回のみ（Cloudflare 認証）
npm run deploy             # predeploy が自動で走る → build → 流出ゲート → wasm退避 → deploy
```

`npm run deploy` は npm の `predeploy` フックにより、必ず以下の順で実行される:

1. `build:strict` — クエリ/描画エラーを失敗扱いにして `build/` を再生成
2. `check:leak` — **流出ゲート**（下記「公開範囲ポリシー」参照）。1件でも違反があれば非ゼロ終了しデプロイを中断する。
3. `offload:wasm` — **DuckDB-WASM を R2 へ退避**（下記「DuckDB-WASM の R2 退避」参照）
4. `wrangler pages deploy` — Pages へアップロード

### DuckDB-WASM の R2 退避（Cloudflare 25MiB 制限の回避）

Evidence がブラウザ用に同梱する DuckDB-WASM（`duckdb-eh` / `duckdb-mvp`）は各 33〜38MiB で、Cloudflare Pages / Workers の **1ファイル 25MiB 上限**を超えて deploy が弾かれる。
これを回避するため [scripts/offload-wasm.mjs](scripts/offload-wasm.mjs) が deploy 直前に wasm を R2 へ退避する。
仕組みの詳細は同ファイル冒頭参照。

R2 公開URLは同スクリプトの `R2_PUBLIC_BASE` 既定値に焼き込み済み（非機密・バケット単位で不変）のため、通常のデプロイに env 設定は不要。以下は別バケットで一から構築する場合のみ:

```bash
# Cloudflare ダッシュボードで R2 を有効化した後
npx wrangler r2 bucket create <bucket>
npx wrangler r2 bucket dev-url enable <bucket>          # 表示された https://pub-*.r2.dev を既定値へ反映
npx wrangler r2 bucket cors set <bucket> --file r2-cors.json
# offload-wasm.mjs の R2_PUBLIC_BASE 既定値を上記URLに、必要なら R2_BUCKET 既定値も更新すること
```

- CORS 設定は [r2-cors.json](r2-cors.json)（public wasm なので GET/HEAD を全 Origin 許可）。
- 別バケットを一時利用するだけなら env `R2_PUBLIC_BASE` / `R2_BUCKET` で既定値を上書きできる。

### 公開範囲ポリシー（SSoT）

公開ビルドに載せてよい地域粒度は [public_scope.yaml](public_scope.yaml) が**唯一の定義**。
`allow_municipalities` に列挙した市区町村コード（＋県 `XX000`・全国 `00000`）だけを公開範囲とする。

- Evidence は各 `sources/*.sql` の結果 parquet を `build/data` へ丸ごと同梱するため、絞り込みを誤ると公開対象外の市区町村が流出し得る。そこで **SQL 側の `where area_code in (...)` は「ポリシーに適合すべき実装」**と位置づけ、真の定義はこの YAML に一元化している。
- 流出ゲートは pipeline の `data-forge public-scope-check` が担う（実装 `apps/pipeline/src/data_forge/public_scope.py`、テスト `apps/pipeline/tests/test_public_scope.py`）。`build/data/**/*.parquet` を走査し、この YAML と照合する（判定ルール＝5桁かつ末尾3桁≠000 の市区町村粒度コードが `allow_municipalities` 以外に無いこと）。ゲートはルールの写しを持たず YAML を読むだけなので、定義と検査がドリフトしない。
- **公開範囲を変えるときは `allow_municipalities` を編集する**。SQL 側が追随していなければゲートが検出する。
- 単体実行は `npm run check:leak`（要ビルド済 `build/`）＝pipeline の uv 環境でコマンドを呼ぶ薄いラッパー。
