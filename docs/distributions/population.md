# population — 国勢調査 男女別人口

国勢調査（e-Stat）の男女別人口を、全国／都道府県／市区町村の粒度で精製したデータセット群。
単年のクロスセクションと、それらを結合した時系列（派生データセット）を提供する。

- パイプラインの使い方は [apps/pipeline/README.md](../../apps/pipeline/README.md)、全体設計は [docs/pipeline-architecture.md](../pipeline-architecture.md) を参照。
- データソースの利用規約・商用可否は [data-provider-catalog.md](../sources/data-provider-catalog.md) を参照。ソース帳票の全体像は収集データカタログ [estat-census-catalog.md](../sources/estat-census-catalog.md)。

---

## データセット一覧

| キー                               | 内容                                                         | statsDataId |
| ---------------------------------- | ------------------------------------------------------------ | ----------- |
| `population_1980`                  | 男女別人口（全国/都道府県/市区町村, 1980年）                 | 0003412413  |
| `population_1985`                  | 男女別人口（全国/都道府県/市区町村, 1985年）                 | 0003412414  |
| `population_1990`                  | 男女別人口（全国/都道府県/市区町村, 1990年）                 | 0003412415  |
| `population_1995`                  | 男女別人口（全国/都道府県/市区町村, 1995年）                 | 0003412416  |
| `population_2000`                  | 男女別人口（全国/都道府県/市区町村, 2000年）                 | 0003391075  |
| `population_2005`                  | 男女別人口（全国/都道府県/市区町村, 2005年）                 | 0003408216  |
| `population_2010`                  | 男女別人口（全国/都道府県/市区町村, 2010年）                 | 0003038587  |
| `population_2015`                  | 男女別人口（全国/都道府県/市区町村, 2015年）                 | 0003149040  |
| `population_2020`                  | 男女別人口（全国/都道府県/市区町村, 2020年）                 | 0003445078  |
| `population_2025_preliminary`      | 男女別人口 **速報**（人口速報集計, 2025年）                  | 0004050397  |
| `population_timeseries`            | 男女別人口の時系列（1980〜2020確定＋2025速報, 派生）         | 合成        |
| `population_prefecture`            | 男女別人口 都道府県 世紀マクロ（回次跨帳票・1920〜2020）     | 0003410379  |
| `population_prefecture_timeseries` | 都道府県 世紀マクロ の配布正典（1920〜2020＋2025速報, 派生） | 合成        |

出典はいずれも「政府統計の総合窓口(e-Stat)」。

> **都道府県 世紀マクロ（1920〜）**：`population_prefecture_timeseries` は回次跨帳票
> **0003410379「男女別人口及び人口性比 － 全国，都道府県（大正9年～令和2年）」** から独立取得する
> （5歳階級の `population_by_age5_prefecture` と同型）。出力シェイプは 47都道府県・全国行なし
> （全国は Σ県で復元）・2025速報を splice。1980-2020 の重複年は市区町村ミクロの県 rollup と一致する
> （唯一の差＝東京都1980 の +37人＝特別区部の区未定分。回次跨帳票側が区未定分を含む正しい県総数）。

```bash
uv run poe run population_2020         # 2020 単年
uv run poe run population_timeseries   # 1980〜2020 時系列
```

---

## 出力スキーマ

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

### 出力ファイル（`data/processed/<stem>.*`）

| 拡張子       | 用途                                                        |
| ------------ | ----------------------------------------------------------- |
| `.parquet`   | 分析・配布                                                  |
| `.csv`       | 汎用共有                                                    |
| `.sqlite`    | Cloudflare D1 配信（`population` テーブル＋`_source_meta`） |
| `.duckdb`    | 分析用組込DB（`population` テーブル＋`_source_meta`）       |
| `.meta.json` | 出典メタ（サイドカー）                                      |

---

## 年ごとのスキーマ差

**同名「男女別人口」でも年で e-Stat のスキーマ設計が全く異なる（4変種）。**
型名（第3型 / 平成型 / 令和型）の**定義は帳票カタログが正典**（[estat-census-catalog.md](../sources/estat-census-catalog.md#男女別人口)）。本表は各年の**男女コード実値**を持つ。

| 年                  | 型               | 男女の在り処                                                                                                                                                              |
| ------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1980/1985/1990/1995 | 年齢3区分×男女型 | `cat02`=男女（100/110/120）。別に年齢3区分(`cat01`)・表章項目(`tab`)を持つため `tab`=020(人口)・`cat01`=100(年齢総数) で絞る。**全国行が無い**ため 47都道府県合計から復元 |
| 2000/2005           | 第3型            | `cat01`（人口\_総数/男/女=100/110/120）。2000表(0003391075)は2005表と同一ファミリー                                                                                       |
| 2010/2015           | 平成型           | `cat02`（2010=000/001/002・2015=010/020/030）                                                                                                                             |
| 2020                | 令和型           | `cat01`=男女（0/1/2）                                                                                                                                                     |

パース差は **1つのパラメータ化 cleaner `clean_population`（男女を持つ軸・コード対応・事前フィルタ）**
に集約し、年ごとの違いは設定だけで吸収する（year 関数を増やさない）。
**正規化の契約は「入力パースの共有」ではなく「共通の出力スキーマへの写像」。**
実装は [src/data_forge/sources/estat/population.py](../../apps/pipeline/src/data_forge/sources/estat/population.py)。

---

## 派生データセット（複数年結合）の正規化モード

年をまたぐと市町村合併・市部/郡部・人口集中地区などで地域集合が年ごとに変わる。
`population_timeseries` は結合時の地域正規化を `--join` で選べる。**既定は配布正典の `aggregate_to_base`（合併畳み込み済み）**。
生（畳み込み無し）版が必要なら専用データセット `population_timeseries_raw`（既定 `union`）を使う。

```bash
uv run data-forge run population_timeseries                      # 既定=aggregate_to_base（畳込済）
uv run data-forge run population_timeseries_raw                  # 生（union）版・比較デモ用
uv run data-forge run population_timeseries --join intersection  # 共通地域のみ
uv run data-forge run population_timeseries --join grid          # 欠損をnull行で明示
```

| モード         | 意味                                                           | 例（2005〜2020, 行数） |
| -------------- | -------------------------------------------------------------- | ---------------------- |
| `union`        | 全部表示。ある年にしか無い地域もその年の行として残す（縦積み） | 50,760                 |
| `intersection` | 共通のみ。全年に存在する area_code だけ残す（比較可能な地域）  | 44,844                 |
| `grid`         | 欠損明示。area×year×sex の全格子。無い (area,year) は null 行  | 55,284                 |

> 二重計上防止のため、結合時に (`area_code`, `sex_code`, `year`) の重複を検出したら
> `combine.combine_years` が明確に失敗する（年次 cleaner の分類軸取りこぼしを早期検知）。

> **合併を畳む集約は別モード:** union/intersection/grid は「生」の簡易オプション。市町村合併を
> またいで正しく畳んだ連続時系列（`--join aggregate_to_base` / `crosswalk`）は共有ディメンションの
> [area_master.md](area_master.md) を参照。

---

## 速報値の扱い（`data_status` 来歴列）

国勢調査は調査年の翌年に**速報**（人口速報集計＝総人口・世帯数のみ）が出て、確定は年齢別・
昼夜間などが段階リリースされる。速報→確定で数値が微修正される（不詳の補完差）。

方針は **「速報を確定系列に素で混ぜない」**。速報は独立の基底データセット
（例 `population_2025_preliminary`）として先行取込し、時系列へ合成する際は**汎用の来歴列
`data_status` で暫定を明示**する。確定が出たら正典系列へ統合し、速報は破棄する。

| 値            | 意味                               |
| ------------- | ---------------------------------- |
| `confirmed`   | 確定値（既定。過去の確定集計）     |
| `preliminary` | 速報値（後で確定へ置換される暫定） |

- **列は速報が乗った fact にだけ生える**（速報 upstream が無い時は列自体が付かず既存出力と同一）。現状 `population_timeseries` / `population_prefecture_timeseries` が 2025 速報を含み `data_status` を持つ。
- 速報は最新境界＝合併 rollup 不要なので、確定を集約し終えた**後段**で継ぎ足す（`provenance.splice_preliminary`）。area 集約（共有ディメンション）は無改修。
- **area scope 自動追従**: 速報表は全国/県/市区町村が混在するが、splice 前に確定ビューに既に在る `area_code` へ intersection scoping する。よって県ビューには県行だけ、市区町村ビューには市区町村行だけが残る（レベル混在・二重計上を防ぐ）。2020→2025 の境界変更で確定側に無い 2025 コードは coverage gap として落ちる（市区町村ビューで全国比 約99.85%、過大計上ではない）。
- **配布物の利用者は `data_status` を必読**。この列を無視すると速報行を確定と誤認する。
- 実装: 来歴語彙・検証・splice は [src/data_forge/provenance.py](../../apps/pipeline/src/data_forge/provenance.py)、合成配線は `StitchedDataset.preliminary_upstreams` と `derive._splice_preliminary`。

> 速報は令和7年国勢調査「人口速報集計」（statsDataId `0004050397`、2020 と同型の令和型）。
> 単体 `population_2025_preliminary` は全国/県/市区町村の8列（`data_status` 無し）を出力する。
> カバレッジの不揃い（速報は総人口のみ・年齢別/昼夜間に2025は無い）は既存前提どおり特別視しない（fact ごとの年スパン差＝`grid` の null 機構で表現）。確定が出たら正典系列へ統合し速報は破棄する。

---

## 地域マスタ（合併をまたぐ集約）

年をまたぐと市町村合併・政令市移行で地域集合が変わるため、実用グレードの連続時系列には**地域マスタ（アトム軸スタースキーマ）** が必要になる。これは総人口に限らず全ファクトが共有する**conformed dimension** なので、設計・運用は独立の正典 [area_master.md](area_master.md) にまとめた（`population_timeseries --join aggregate_to_base / crosswalk`、人口保存・孤児検証、堀＝overrides 運用など）。
