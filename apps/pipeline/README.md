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
  ├─ io/export.py ─ 出力共通層（DF → parquet / csv / sqlite ＋ メタ埋め込み）
  ├─ meta.py   ─ SourceMeta（ソース非依存）＋ combine_meta（複数ソース束ね）
  └─ config.py ─ 設定・パス解決
```

**依存の向きの原則:** `sources/*`（ソース固有）・`io/*`（出力）・`combine.py`（合成）は
互いに依存せず、共通型 `meta.py`・共通の出力スキーマにのみ依存する。出典表記（citation）は
各ソースが規約に沿って生成する責務を持ち、`io/export` は書き出すだけ（出力層はソース非依存）。

**拡張の接ぎ目（seam）:**

| やりたいこと                | 触る場所                                                              |
| --------------------------- | --------------------------------------------------------------------- |
| e-Stat の別データセット追加 | `sources/estat/` に `cleaner` を1つ書き、`datasets.py` に1エントリ    |
| データセット固有パラメータ  | `Dataset.source_params`（ソース語彙をここに閉じ込める）               |
| 出典メタの項目追加          | `meta.py` の `SourceMeta` / 各ソースの `extract_meta`                 |
| 複数年/複数表の結合         | `datasets.py` に `CompositeDataset` を1エントリ（`combine` を再利用） |

### 拡張方針（ロードマップ）

原則は **「実例が2つ揃ってから抽象化する」**（対応する実作業とセットで導入し、逆依存など明確な欠陥だけ前倒し）。

| Phase | トリガー            | 対応内容                                                                                                                                |
| ----- | ------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | 2つ目のデータセット | 地域コード正規化の共通層／年度パラメータ化／バリデーション規則                                                                          |
| **2** | 2つ目のデータソース | `Source` プロトコル確定＋ `cli.py` を registry dispatch へ。併せて各ソースの生レスポンスを Pydantic で検証／設定は pydantic-settings 化 |
| **3** | D1 / R2 配信        | Exporter レジストリ化（フォーマットと transport の分離）                                                                                |
| **4** | データセット合成    | ✅ `CompositeDataset` + `combine.py` で着手済み（複数年結合）。汎用の依存グラフ化は3例目が出てから                                      |

**Phase 1 の実地知見:** 同名「男女別人口」でも 2015 と 2020 で e-Stat のスキーマ設計が全く異なった
（tab軸の有無・男女軸の位置）。そのため「入力パースの共通化」ではなく **年ごとの cleaner が
共通の出力スキーマへ写像し、結合層（`combine.py`）で地域正規化する**構成に落ち着いた。
crosswalk（合併の後継自治体への集約）は外部データが要るため、実需が出るまで未着手（現状は
`union`/`intersection`/`grid` の3モードで対応）。
