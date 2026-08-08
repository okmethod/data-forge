# data-forge pipeline

公的データを取得・クレンジングし、Parquet / CSV / SQLite へ精製する Python パイプライン（uv + Polars）。

**ライセンス・出典:**

e-Stat のデータを利用。  
出力物には出典表記（`_source_meta` / `*.meta.json` に自動埋め込み済み）を明示すること。  
データソースの商用可否は [docs/sources/catalog.md](../../docs/sources/catalog.md) を参照。

---

## 使い方

取得（Fetch）→ 精製（Clean）→ 出力（Export）を独立ステップとして提供する。

```bash
# セットアップ
cd apps/pipeline
uv sync --extra dev

# .env の ESTAT_APP_ID に e-Stat のアプリケーションIDを設定
cp .env.example .env

# 生データ取得（data/raw/ にキャッシュ）
uv run poe fetch population

# 書き出さず、クレンジング結果の先頭のみ表示（確認用）
uv run poe clean population

# 取得→クレンジング→出力（data/processed/ に保存）
uv run poe run population

# キャッシュを無視して再取得
uv run poe run population --refresh

# 開発タスク
uv run poe check   # lint + test（CI相当）
# その他については pyproject.toml の [tool.poe.tasks] 参照。
```

---

## データセット

| キー         | 内容                                                  | statsDataId | 出典                       |
| ------------ | ----------------------------------------------------- | ----------- | -------------------------- |
| `population` | 国勢調査 男女別人口（全国/都道府県/市区町村, 2020年） | 0003445078  | 政府統計の総合窓口(e-Stat) |

新規データセットの追加は [src/data_forge/datasets.py](src/data_forge/datasets.py) にエントリを足す。

### population の出力スキーマ

| 列           | 型   | 説明                                                                          |
| ------------ | ---- | ----------------------------------------------------------------------------- |
| `area_code`  | str  | 地域コード（JIS）                                                             |
| `area_name`  | str  | 地域名                                                                        |
| `area_level` | int  | 階層（1=全国 / 2=都道府県 / 4=市 / 5=政令市の区 / 6=市区町村 / 7=旧市区町村） |
| `sex_code`   | str  | 男女コード（0=総数 / 1=男 / 2=女）                                            |
| `sex`        | str  | 男女名称                                                                      |
| `year`       | int  | 調査年                                                                        |
| `population` | int  | 人口（欠損は null）                                                           |
| `is_current` | bool | 現存自治体か（level 7=旧市区町村は false）                                    |

### 出力ファイル

| ファイル                           | 用途                                                        |
| ---------------------------------- | ----------------------------------------------------------- |
| `census_population_2020.parquet`   | 分析・BOOTH配布                                             |
| `census_population_2020.csv`       | 汎用共有                                                    |
| `census_population_2020.sqlite`    | Cloudflare D1 配信（`population` テーブル＋`_source_meta`） |
| `census_population_2020.meta.json` | 出典メタ（サイドカー）                                      |

---

## アーキテクチャ

```
cli.py  ─ orchestration（fetch / clean / export / run）
  ├─ datasets.py ─ レジストリ（Dataset: source / source_params / cleaner / 出力設定）
  ├─ sources/estat/ ─ ソース固有層
  │     client.py    … getStatsData 呼び出し・ページング（汎用）
  │     fetch.py     … raw JSON 取得＋ data/raw/ キャッシュ
  │     transform.py … star schema → tidy DF（汎用）＋ extract_meta（出典生成）
  │     population.py … 人口テーブル固有のクレンジング
  ├─ io/export.py ─ 出力共通層（DF → parquet / csv / sqlite ＋ メタ埋め込み）
  ├─ meta.py   ─ SourceMeta（出典メタ・ソース非依存の共通型）
  └─ config.py ─ 設定・パス解決
```

**依存の向きの原則:** `sources/*`（ソース固有）と `io/*`（出力）は互いに依存せず、
共通型 `meta.py` にのみ依存する。出典表記（citation）は各ソースが利用規約に沿って
生成する責務を持ち、`io/export` はそれを書き出すだけ（出力層はソース非依存）。

**拡張の接ぎ目（seam）:**

| やりたいこと                | 触る場所                                                           |
| --------------------------- | ------------------------------------------------------------------ |
| e-Stat の別データセット追加 | `sources/estat/` に `cleaner` を1つ書き、`datasets.py` に1エントリ |
| データセット固有パラメータ  | `Dataset.source_params`（ソース語彙をここに閉じ込める）            |
| 出典メタの項目追加          | `meta.py` の `SourceMeta` / 各ソースの `extract_meta`              |

### 拡張方針（ロードマップ）

原則は **「実例が2つ揃ってから抽象化する」**（対応する実作業とセットで導入し、逆依存など明確な欠陥だけ前倒し）。

| Phase | トリガー            | 対応内容                                                                                                                                |
| ----- | ------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | 2つ目のデータセット | 地域コード正規化の共通層／年度パラメータ化／バリデーション規則                                                                          |
| **2** | 2つ目のデータソース | `Source` プロトコル確定＋ `cli.py` を registry dispatch へ。併せて各ソースの生レスポンスを Pydantic で検証／設定は pydantic-settings 化 |
| **3** | D1 / R2 配信        | Exporter レジストリ化（フォーマットと transport の分離）                                                                                |
| **4** | データセット合成    | 派生データセット（依存グラフ）のモデル化                                                                                                |
