# data-forge pipeline

公的データを取得・クレンジングし、Parquet / CSV / SQLite へ精製する Python パイプライン（uv + Polars）。

**ライセンス・出典:**

e-Stat のデータを利用。  
出力物には出典表記（`_source_meta` / `*.meta.json` に自動埋め込み済み）を明示すること。  
データソースの商用可否は [docs/data_catalog.md](../../docs/data_catalog.md) を参照。

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
```

---

## データセット

データセットごとの仕様（statsDataId・出力スキーマ・年ごとのスキーマ差・時系列の正規化モード等）は`docs/datasets/` に置く。  
新規追加時は [src/data_forge/datasets.py](src/data_forge/datasets.py) にエントリを足し、対応する `docs/datasets/<name>.md` を用意する。

| データセット群 | 内容                                            | ドキュメント                                                     |
| -------------- | ----------------------------------------------- | ---------------------------------------------------------------- |
| population     | 国勢調査 男女別人口（2005〜2020, 単年＋時系列） | [docs/datasets/population.md](../../docs/datasets/population.md) |

---

## アーキテクチャ

```
cli.py  ─ orchestration（fetch / clean / export / run、基底/派生を判別）
  ├─ datasets.py ─ レジストリ（Dataset / CompositeDataset）
  ├─ sources/estat/ ─ ソース固有層
  │     client.py    … getStatsData 呼び出し・ページング（汎用）
  │     fetch.py     … raw JSON 取得＋ data/raw/ キャッシュ
  │     transform.py … star schema → tidy DF（汎用）＋ extract_meta（出典生成）
  │     population.py … 人口固有クレンジング（clean_population 1本＋年ごと設定で3変種を吸収）
  ├─ combine.py ─ 派生合成層（複数年結合＝時系列化。union/intersection/grid ＋ 粒度ガード）
  ├─ area/ ─ 地域参照層（実装済み・アトム軸スタースキーマ）データセット非依存の地域マスタ（コード軸=JIS。ソース非依存ではない）
  │     atoms.py    … 各年の area 階層 → 「標準的な市区町村」による最finest分割（アトム=fact 層）
  │     events.py   … 実効合併イベント＝parsed ⊕ overrides（old_code/successor_code/year/kind）
  │     mapping.py  … rollup: 施行年≤base_year のイベントを推移閉包で畳み code→base_code
  │     aggregate.py… aggregate_to_base: 各年アトム＋events＋base_year → 基準年へ合併集約（8列）
  │     reconcile.py… 人口保存チェック＋孤児アトム検出＝ area-check / area-orphans（堀の駆動）
  │     history/ingest.py … 廃置分合CSV → 正規化イベント（events_parsed）。列仕様は実物CSVで確定（TODO）
  │     seeds/      … events_overrides の「ひな形」CSV（.example）。実データは data/area/（.gitignore＝堀）
  ├─ io/export.py ─ 出力共通層（DF → parquet / csv / sqlite ＋ メタ埋め込み）
  ├─ meta.py   ─ SourceMeta（ソース非依存）＋ combine_meta（複数ソース束ね）
  └─ config.py ─ 設定・パス解決
```

**依存の向きの原則:** `sources/*`（ソース固有）・`io/*`（出力）・`combine.py`（合成）・
`area/`（地域参照）は互いに依存せず、共通型 `meta.py`・共通の出力スキーマにのみ依存する。
とくに `combine`（縦結合）と `area.aggregate`（基準年集約）は相互に依存させず、
オーケストレーション（`cli.py`）が clean→combine→area.aggregate と順に配線する
（集約を `combine` に埋め込むと合成層が特定の参照データ＝area に縛られ本質軸がブレるため、意図的に分離）。
出典表記（citation）は各ソースが規約に沿って生成する責務を持ち、`io/export` は書き出すだけ（出力層はソース非依存）。

> **`area/` の非依存性の範囲（注意）:** 確実なのは**データセット非依存**（population 固有でない）まで。
> **ソース非依存ではない**——アトム抽出は各ソースの area 表現に依存する（今は e-Stat の area 階層前提）。
> 再利用できるのはコード軸が JIS（全国地方公共団体コード）で揃う範囲で、とくに events（合併の後継）は JIS コードの
> 事実なのでソースをまたいで使い回したい核。メッシュ/小地域/都市雇用圏など別コード体系の統計とは噛み合わない。
> 現状 consumer は population(e-Stat) の1例のみのため非依存は主張せず、e-Stat 前提で作り2例目で検証する。

**拡張の接ぎ目（seam）:**

| やりたいこと                | 触る場所                                                                                            |
| --------------------------- | --------------------------------------------------------------------------------------------------- |
| e-Stat の別データセット追加 | `sources/estat/` に `cleaner` を1つ書き、`datasets.py` に1エントリ                                  |
| データセット固有パラメータ  | `Dataset.source_params`（ソース語彙をここに閉じ込める）                                             |
| 出典メタの項目追加          | `meta.py` の `SourceMeta` / 各ソースの `extract_meta`                                               |
| 複数年/複数表の結合         | `datasets.py` に `CompositeDataset` を1エントリ（`combine` を再利用）                               |
| 合併の後継対応を追加/修正   | `data/area/events_overrides.csv` に1行足す（`area-orphans`/`area-check` で支援。コード変更不要）    |
| 地域正規化した時系列を出す  | `area.aggregate.aggregate_to_base` に `events`・`base_year` を渡す（既存 union 等は生モードで併存） |

### 拡張方針（ロードマップ）

原則は **「実例が2つ揃ってから抽象化する」**（対応する実作業とセットで導入し、逆依存など明確な欠陥だけ前倒し）。

| Phase | トリガー            | 対応内容                                                                                                                                |
| ----- | ------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | 2つ目のデータセット | 地域コード正規化の共通層／年度パラメータ化／バリデーション規則                                                                          |
| **2** | 2つ目のデータソース | `Source` プロトコル確定＋ `cli.py` を registry dispatch へ。併せて各ソースの生レスポンスを Pydantic で検証／設定は pydantic-settings 化 |
| **3** | D1 / R2 配信        | Exporter レジストリ化（フォーマットと transport の分離）                                                                                |
| **4** | データセット合成    | ✅ `CompositeDataset` + `combine.py` で着手済み（複数年結合）。汎用の依存グラフ化は3例目が出てから                                      |

> **直近の着手確定タスク（トリガー待ちではない）:** 地域マスタ（アトム軸スタースキーマ）による**合併集約**。
> これは新 Phase ではなく **Phase 4（データセット合成）の深化**——`combine` の正規化モードを
> アトム fact＋合併 events＋`base_year` で一段賢くするもの。この表は「実例2つで抽象化する候補」を並べる場だが、
> これは実需が確定済みのため表外に置く。**実装済み**（`area/` 層＋`--join aggregate_to_base`。
> ただし廃置分合CSVの実物での列確定と events 投入は残作業。詳細: docs/datasets/population.md）。

**Phase 1 の実地知見:** 同名「男女別人口」でも 2015 と 2020 で e-Stat のスキーマ設計が全く異なった
（tab軸の有無・男女軸の位置）。そのため「入力パースの共通化」ではなく **年ごとの cleaner が
共通の出力スキーマへ写像し、結合層（`combine.py`）で地域正規化する**構成に落ち着いた。
crosswalk（合併の後継自治体への集約）は Phase 4 の深化として実装済み。fact は各年の「標準的な
市区町村」による最finest分割（アトム）に固定し、外部データが要るのは合併の後継対応（events）のみ
——parsed（廃置分合CSV）で埋め、埋まらない箇所だけを人手 overrides（堀）に閉じ込める
（`area/seeds/` にひな形）。集約は既存3モードと併存する第4の正規化
（`--join aggregate_to_base`）として提供する。
