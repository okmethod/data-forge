# data-forge pipeline

公的データを取得・クレンジングし、Parquet / CSV / SQLite / DuckDB へ精製する Python パイプイン（uv + Polars）。

**ライセンス・出典:**

e-Stat のデータを利用。  
出力物には出典表記（`_source_meta` / `*.meta.json` に自動埋め込み済み）を明示すること。  
データソースの商用可否は [docs/datasets/data_catalog.md](../../docs/datasets/data_catalog.md) を参照。

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

## データセット

データセットごとの仕様（statsDataId・出力スキーマ・年ごとのスキーマ差・時系列の正規化モード等）は`docs/datasets/` に置く。
**一覧は [docs/README.md](../../docs/README.md) を正典とする**（ここには再掲しない）。

新規追加時は [src/data_forge/datasets.py](src/data_forge/datasets.py) にエントリを足し、
対応する `docs/datasets/<name>.md` を用意して [docs/README.md](../../docs/README.md) の索引に追記する。

---

## アーキテクチャ

段レベルの俯瞰のみを示す。  
各段の内部ファイルの役割は当該パッケージの `__init__.py` docstring を正典とする。

```text
data_forge/
│   # 入口・レジストリ
├── cli.py          # 入口：引数解析＋コマンド dispatch（本流 fetch/clean/export/run・支援 area-*/estat-search）
├── datasets.py     # レジストリ：何を・どの型で作るか（Dataset ＋ 派生2型）
│
│   # 共有の下地（段に属さず、各段が一方向に参照する中立層）
├── meta.py         # SourceMeta：出典 citation を運ぶソース非依存の出力契約型
├── provenance.py   # data_status：行の確からしさ（確定/速報）を表す来歴語彙
├── config.py       # 設定・パス解決
├── area/           # 参照データ：合併集約の材料（アトム軸・データセット非依存）
│
│   # パイプライン段（取得 → 合成 → 出力）
├── sources/        # ① 取得＋クレンジング（ソース固有）
│   └── estat/
├── derive/         # ② 合成（派生データセット）
└── output/         # ③ 出力（DF→parquet/csv/sqlite/duckdb＋メタ埋め込み）
```

> **派生の2フロー（縫合 / 射影）:** `derive/combine.py` は縫合（`combine_years`）と射影（`union_areas`）の
> 両変換を持ち、`derive.load` が基底 / 縫合（`StitchedDataset`）/ 射影（`ProjectedDataset`）を判別して配線する。
> **縫合**＝各回帳票（年ごと別 statsDataId）を year 軸で結合し合併畳込 等を通す既存フロー。
> **射影**＝e-Stat 既製の時系列帳票（1 ID が全年）を area 軸で union するだけの最小フロー（area master 不要）。

**依存の向きの原則:** `sources/*`（取得）・`output/*`（出力）・`derive/combine`（純変換）・
`area/`（参照）は互いに依存せず、共通型 `meta.py`・共通の出力スキーマにのみ依存する。
とくに `combine`（縦結合）と `area.aggregate`（基準年集約）は相互に依存させず、
`derive/orchestrate` が clean→combine→area.aggregate と順に配線する
（集約を `combine` に埋め込むと合成層が特定の参照データ＝area に縛られ本質軸がブレるため、意図的に分離）。
出典表記（citation）は各ソースが規約に沿って生成する責務を持ち、`output/export` は書き出すだけ（出力層はソース非依存）。

> **`area/` の非依存性の範囲（注意）:** 確実なのは**データセット非依存**（population 固有でない）まで。
> **ソース非依存ではない**——アトム抽出は各ソースの area 表現に依存する（今は e-Stat の area 階層前提）。
> 再利用できるのはコード軸が JIS（全国地方公共団体コード）で揃う範囲で、とくに events（合併の後継）は JIS コードの
> 事実なのでソースをまたいで使い回したい核。メッシュ/小地域/都市雇用圏など別コード体系の統計とは噛み合わない。
> 現状 consumer は population(e-Stat) の1例のみのため非依存は主張せず、e-Stat 前提で作り2例目で検証する。

**拡張の接ぎ目（seam）:**

| やりたいこと                | 触る場所                                                                                                               |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| e-Stat の別データセット追加 | `sources/estat/` に `cleaner` を1つ書き、`datasets.py` に1エントリ                                                     |
| データセット固有パラメータ  | `Dataset.source_params`（ソース語彙をここに閉じ込める）                                                                |
| 出典メタの項目追加          | `meta.py` の `SourceMeta` / 各ソースの `extract_meta`                                                                  |
| 複数年を結合（縫合）        | `datasets.py` に `StitchedDataset` を1エントリ（`combine_years` を再利用）                                             |
| 既製の時系列を取込（射影）  | `datasets.py` に `ProjectedDataset` を1エントリ（`union_areas` を再利用）                                              |
| 合併の後継対応を追加/修正   | `data/area/events_overrides.csv` に1行足す（`area-orphans`/`area-check` で支援。コード変更不要）                       |
| 地域正規化した時系列を出す  | `area.aggregate.aggregate_to_base` に `events`・`base_year` を渡す（既存 union 等は生モードで併存）                    |
| 畳む/畳まないを固定せず出す | `--join crosswalk`＝`attach_crosswalk` で `base_code`/`base_name` 列を同梱（利用者が `GROUP BY base_code` で任意集約） |

### 拡張方針（ロードマップ）

原則は **「実例が2つ揃ってから抽象化する」**（対応する実作業とセットで導入し、逆依存など明確な欠陥だけ前倒し）。

| Phase | トリガー            | 対応内容                                                                                                                                                   |
| ----- | ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | 2つ目のデータセット | 地域コード正規化の共通層／年度パラメータ化／バリデーション規則                                                                                             |
| **2** | 2つ目のデータソース | `Source` プロトコル確定＋ `cli.py` を registry dispatch へ。併せて各ソースの生レスポンスを Pydantic で検証／設定は pydantic-settings 化                    |
| **3** | D1 / R2 配信        | Exporter レジストリ化（フォーマットと transport の分離）                                                                                                   |
| **4** | データセット合成    | ✅ 派生2型（`StitchedDataset` 縫合 / `ProjectedDataset` 射影）＋ `derive/`（`combine_years`/`union_areas`）で着手済み。汎用の依存グラフ化は3例目が出てから |

> **直近の着手確定タスク（トリガー待ちではない）:** 地域マスタ（アトム軸スタースキーマ）による**合併集約**。
> これは新 Phase ではなく **Phase 4（データセット合成）の深化**——`combine` の正規化モードを
> アトム fact＋合併 events＋`base_year` で一段賢くするもの。この表は「実例2つで抽象化する候補」を並べる場だが、
> これは実需が確定済みのため表外に置く。**実装済み**（`area/` 層＋`--join aggregate_to_base`。
> ただし廃置分合CSVの実物での列確定と events 投入は残作業。詳細: docs/datasets/area_master.md）。

**Phase 1 の実地知見:** 同名「男女別人口」でも 2015 と 2020 で e-Stat のスキーマ設計が全く異なった
（tab軸の有無・男女軸の位置）。そのため「入力パースの共通化」ではなく **年ごとの cleaner が
共通の出力スキーマへ写像し、結合層（`derive/combine.py`）で地域正規化する**構成に落ち着いた。
crosswalk（合併の後継自治体への集約）は Phase 4 の深化として実装済み。fact は各年の「標準的な
市区町村」による最finest分割（アトム）に固定し、外部データが要るのは合併の後継対応（events）のみ
——parsed（廃置分合CSV）で埋め、埋まらない箇所だけを人手 overrides（堀）に閉じ込める
（`area/seeds/` にひな形）。集約は既存3モードと併存する第4の正規化
（`--join aggregate_to_base`）として提供する。さらに、畳む/畳まないを配布時に固定しない
`--join crosswalk`（後継コード `base_code` を同梱し利用者の集約へ委譲）を第5モードとして併存させる
（`aggregate_to_base` = crosswalk を `base_code` で `GROUP BY` した確定ビュー、と再定義）。
