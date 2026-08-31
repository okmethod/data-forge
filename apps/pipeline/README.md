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

データセットは [src/data_forge/datasets.py](src/data_forge/datasets.py) の**レジストリ**に family 単位で登録する。名前は次の4語彙の関係で決まり、`test` が整合を強制する。

### family / key / stem / table_name

| 語彙           | 意味                                                                        | 例                                     |
| -------------- | --------------------------------------------------------------------------- | -------------------------------------- |
| **family**     | その fact の論理名 ＝ `table_name`。粒度・来歴は含めない                    | `population_by_age5`                   |
| **key**        | family ＋ suffix で一意化したレジストリ識別子（family : key = 1:N）         | `population_by_age5_prefecture`        |
| **stem**       | 出力ファイル名＝物理 identity。`"census_" + key` が慣習（key : stem = 1:1） | `census_population_by_age5_prefecture` |
| **table_name** | SQLite テーブル名 ＝ family。複数 key が同一 table を共有（N:1 ハブ）       | `population_by_age5`                   |

- **family ＝ table_name**：粒度（市区町村/都道府県/全国）も来歴（回次別/回次跨・Stitched/Projected）も名前に入れない。カバレッジ年次は名前でなく docs / title で示す。
- **基底 key は table_name と一致させない**（必ず suffix を付ける）。同一 fact の別パーティション/別ビュー（全国 base・県 base・縫合・県ロールアップ）が同じ table_name を共有する。
- 分類改訂等で「同名では畳めない別 fact」になる時だけ、**粒度語でない弁別子**で別 family を立てる（例: `occupation_major12` / `occupation_major10`）。粒度語（`_prefecture` 等）を family 名に入れると key の area suffix と衝突するため避ける。

### suffix の軸（key = family ＋ suffix。地理 × 時間は直交して連結）

- **地理粒度**: `_national`（全国のみ）／ `_prefecture`（全国＋都道府県）／ **無印**（＝その fact の基底＝最細粒度）
- **時間軸**: `_<year>`（単年, 例 `_1980`）／ `_timeseries`（全回時系列）／ `_raw`（畳込無しデモ）／ `_<year>_preliminary`（速報単独）
- 連結例: `population_by_age5_prefecture_timeseries`

> ⚠️ **既知の未統一論点**: 無印の意味が family 群で揺れている。`population`・`population_by_age(5)` 系は市区町村が基底なので**無印**、就業系（`labor_force` / `industry` / `occupation`）は市区町村帳票が無く全国/県が基底のため `_national` / `_prefecture` を**必ず明示**する。統一するなら `_municipality` を明示して無印を廃止し、全 family で地理粒度を明示に揃える。

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
