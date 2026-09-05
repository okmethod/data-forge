# data-forge pipeline

公的データを取得・クレンジングし、利用しやすいデータ形式に精製するパイプライン。

- **パイプライン設計（段構成・派生・依存の向き・seam）**: [docs/pipeline-architecture.md](../../docs/pipeline-architecture.md)
- **収集データカタログ** [docs/sources/](../../docs/sources/) — 精製の取得元（ソース側）の仕様
- **精製データカタログ** [docs/distributions/](../../docs/distributions/) — 本パイプラインが精製・配布するデータセットごとの仕様（出力スキーマ・カバレッジ・検証結果）
- **データ品質保証（保存則・クロスファクト検算・粒度ガード・出典同梱の4ゲート）**: [docs/data-quality-assurance.md](../../docs/data-quality-assurance.md)
- **ライセンス・規約・商用可否・出典表記**: [docs/sources/data-provider-catalog.md](../../docs/sources/data-provider-catalog.md)
  - 出力物には出典表記（citation）を自動埋め込み・自動検証済み

---

## 技術スタック

- **言語 / 実行環境**: Python 3.12+（パッケージ管理: uv）
- **開発ツール**: ruff（Lint / Format）・pytest（Test）・poe（タスクランナー・`[tool.poe.tasks]`）
- **主要ライブラリ**:
  - Polars — DataFrame 処理（クレンジング・合成）
  - httpx — e-Stat API の HTTP クライアント
  - DuckDB — 分析用組込DB への出力
  - python-dotenv / PyYAML — 設定・シークレット・公開スコープ定義の読取

---

## ディレクトリ構成

```text
apps/pipeline/
├── pyproject.toml     # name = "data-forge-pipeline"
├── uv.lock
├── Dockerfile
├── .env               # e-Stat APP ID を配置（非コミット）
│
├── src/data_forge/    # アプリコード（ルーティング・読取・整形）
│   ├── cli.py         # 入口：引数解析＋コマンド dispatch
│   ├── datasets.py    # レジストリ：何を・どの型で作るか（Dataset ＋ 派生2型）
│   │
│   ├── meta.py        # SourceMeta：出典 citation を運ぶソース非依存の出力契約型
│   ├── provenance.py  # data_status：行の確からしさ（確定/速報）を表す来歴語彙
│   ├── config.py      # 設定・パス解決
│   │
│   ├── area/          # 参照層：基準年集約が畳み込む地域マスタ（アトム軸・データセット非依存）
│   ├── sources/       # パイプライン① 取得＋クレンジング（ソース固有）
│   ├── derive/        # パイプライン② 合成（縫合／射影の派生データセット）
│   └── output/        # パイプライン③ 出力（DF→parquet/csv/sqlite/duckdb＋メタ埋め込み）
│
└── tests/             # 単体テスト（外部依存なし）
```

---

## 命名規則

データセットは [src/data_forge/datasets.py](src/data_forge/datasets.py) の**レジストリ**に family 単位で登録する。  
名前は次の4語彙の関係で決まる。

### family / key / stem / table_name

| 語彙           | 意味                                                                  | 例                           |
| -------------- | --------------------------------------------------------------------- | ---------------------------- |
| **family**     | その fact の**簡潔な論理名**。分類軸か標準語彙で端的に                | `age5year`                   |
| **key**        | family ＋ suffix で一意化したレジストリ識別子（family : key = 1:N）   | `age5year_prefecture`        |
| **stem**       | 出力ファイルの物理 identity（key : stem = 1:1）                       | `census_age5year_prefecture` |
| **table_name** | SQLite テーブル名 ＝ family。複数 key が同一 table を共有（N:1 ハブ） | `age5year`                   |

- **family ＝ table_name**：その fact を最も端的に表す簡潔名。**母集団（人口/世帯/就業者）も粒度も来歴も、弁別に不要な共通軸（男女別など）も名前に入れない**。カバレッジ年次は docs / title で示す。
- **母集団は名前でなく `universe` メタ属性で持つ**。同一 universe の fact は `datasets.py` の同じサブ辞書（`_POPULATION` 等）に置き、そこがグループの縫い目になる。
  - 母集団: `population`＝人口 / `households`＝世帯 / `employed`＝就業者
- **基底 key は table_name と一致させない**。必ず suffix を付ける。同一 fact の別パーティション/別ビュー（全国 base・県 base・縫合・県ロールアップ）が同じ table_name を共有する。
- 分類改訂等で「同名では畳めない別 fact」になる時だけ、弁別子で別 family を立てる（例: `occupation_major12` / `occupation_major10`）。
- **stem ＝ `census_` ＋ key**。prefix `census_` はソース系列を表す（現状は国勢調査 `statsCode=00200521` のみ）。将来 別ソース（国土数値情報等）を精製する場合は別 prefix を割り当てる。

### family 一覧

現在の family（＝table_name）は次の10種。  
各 family の出力スキーマ・年カバレッジ・検証結果は [docs/distributions/](../../docs/distributions/) の同名 doc が正典。

| family (=table_name) | universe   | 分類軸                     | 地理粒度           |
| -------------------- | ---------- | -------------------------- | ------------------ |
| `population`         | population | 男女                       | 全国〜市区町村     |
| `age3class`          | population | 年齢(3区分), 男女          | 全国〜市区町村     |
| `age5year`           | population | 年齢(5歳階級), 男女, 国籍  | 全国〜市区町村     |
| `daynight`           | population | 昼夜                       | 都道府県〜市区町村 |
| `households`         | households | 世帯の種類                 | 全国〜都道府県     |
| `family_type`        | households | 家族類型(16区分)           | 全国〜都道府県     |
| `labor_force`        | population | 労働力状態(3区分), 男女    | 全国〜都道府県     |
| `industry`           | employed   | 産業大分類, 男女           | 全国〜都道府県     |
| `occupation_major12` | employed   | 職業大分類(12区分), 男女   | 全国〜都道府県     |
| `occupation_major10` | employed   | 職業大分類(旧10区分), 男女 | 全国〜都道府県     |

> 母集団を名前から外し `universe` メタに追い出したことで table_name は簡潔になり、ダッシュボードの page 名（`age_3class` / `daynight` 等）ともほぼ一致する。  
> 名前だけでは母集団が見えないが、`universe` 属性とサブ辞書構造で補完する。本プロジェクトは 1 fact = 1 SQLite なので SQL 文脈でも母集団は自明。

### suffix の軸（key = family ＋ suffix。地理 × 時間は直交して連結）

- **地理粒度（必須・明示）**: `_municipality`（市区町村）／ `_prefecture`（都道府県）／ `_national`（全国）。各粒度は**排他**＝全国行は `_national` のみに置き `_prefecture` に混ぜない。**無印は使わない**＝どの粒度かを名前で常に自明にする。市区町村帳票が存在しない fact は `_national` / `_prefecture` のみを持つ。
- **時間軸**: `_<year>`（単年断面, 例 `_1980`）／ `_timeseries`（全回時系列の配布最終形）／ 省略（最新回の単一断面のみ）
- **variant（特殊時のみ）**: `_raw`（畳込無しデモ）／ `_<year>_preliminary`（速報単独）
- **連結順序**: `family` → `_<地理>` → `_<時間>` → `_<variant>` の順（各軸は省略可・独立）
- 連結例: `age5year_municipality_timeseries` ／ `age5year_prefecture_timeseries` ／ `households_prefecture_timeseries` ／ `population_municipality_timeseries_raw`

> **全国行の同梱禁止（排他粒度）**: `_prefecture_timeseries` は都道府県のみ・全国行を含めない。
> 全国は `_national`（例: `_national_timeseries`）に分離する。1帳票に全国＋県が混在する single-ID fact（`households` / `family_type` 等）も、配布時に全国＝`_national` / 県＝`_prefecture` へ分離し、単独名 `households` は使わない（**基底 key ≠ table_name を徹底**）。
> ダッシュで全国基準線が要る場合は `_national` と union する。

family 名の閉じた語彙は `datasets.py` の `FAMILIES` に集約し、`test` が全 table_name ∈ FAMILIES を強制する。

---

## 使い方

取得（Fetch）→ クレンジング（Clean）→ 出力（Export）を独立ステップとして提供する。

```bash
# セットアップ
cd apps/pipeline
uv sync --extra dev

# .env の ESTAT_APP_ID に e-Stat のアプリケーションIDを設定
# （ID は各自 https://www.e-stat.go.jp/api/ で取得。第三者提供禁止のためコミット不可）
cp .env.example .env

# 生データ取得（data/raw/ にキャッシュ）
uv run poe fetch population_2020

# 書き出さず、クレンジング結果の先頭のみ表示（確認用）
uv run poe clean population_2020

# 取得→クレンジング→出力（data/processed/ に保存）
uv run poe run population_2020

# キャッシュを無視して再取得
uv run poe run population_2020 --refresh

# 開発タスク
uv run poe check   # lint + test（CI相当）
# その他については pyproject.toml の [tool.poe.tasks] 参照。

# 探索: 帳票（statsDataId）を e-Stat から検索する（データセット非依存。詳細は --help）
uv run data-forge estat-search --word 年齢 --limit 50
```

---

## データセット新規追加時の流れ

1. **cleaner を書く** — `sources/` に、その帳票の軸差を吸収して共通の出力スキーマへ写像する関数を追加。既存 cleaner の設定パラメータで足りる場合は不要。
2. **レジストリに登録** — `src/data_forge/datasets.py` にエントリを追加（単年=`Dataset` / 縫合=`StitchedDataset` / 射影=`ProjectedDataset`）。cleaner・statsDataId・join・grain をここで結線する。
3. **仕様ドキュメントを用意** — `docs/distributions/<name>.md` を新設（statsDataId・出力スキーマ・年ごとのスキーマ差）し、[docs/README.md](../../docs/README.md) の索引に1行追記。
4. **テスト・検証を追加** — cleaner／派生ロジックの単体テストを `tests/` に追加（外部依存なし）。保存則・クロスファクト検算など横断検証の方針は [docs/data-quality-assurance.md](../../docs/data-quality-assurance.md) が正典。
5. **動作確認** — `uv run poe run <key>` で取得〜出力を通し、`uv run poe check`（lint + test）を通す。
