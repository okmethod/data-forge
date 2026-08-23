"""データセット定義レジストリ。

新しいデータセットの追加は、原則このファイルにエントリを1つ足すだけで済むようにする。
ソース固有の取得・整形処理は sources/ 以下の関数を参照する。

正典の所在（ここには再掲しない＝ドリフト防止）:
- 軸構造（tab/cat コード・年ごとのスキーマ差・全国行の有無・不詳の導出等）
  cleaner モジュール sources/estat/<name>.py の docstring
- statsDataId・e-Stat 原題・年カバレッジ … docs/datasets/<name>.md
- 派生（縫合／射影）フローの汎用意味論 … 下記 StitchedDataset / ProjectedDataset の docstring

本ファイルのコメントは「そのエントリ固有の判断（なぜこの cleaner/join/grain か）」に絞る。

レジストリはファミリー単位のサブ辞書（_POPULATION 等）に分け、末尾の DATASETS で束ねる。
サブ辞書の区切りは cleaner モジュール／table_name のまとまりに対応し、将来のファイル分割の縫い目でもある。

命名規約（family / key / stem / table_name の関係）:
- **family名 ＝ table_name**。粒度（市区町村/都道府県/全国）や来歴（系統A/B・Stitched/Projected）を
  suffix に含めない「その fact の論理名」。カバレッジ年次は名前でなく docs/title で明示する。
- **family : key = 1:N**。key は family名 ＋ 役割/粒度 suffix（_national/_prefecture/_timeseries/_<year> 等）で
  一意化する。同一 fact の別パーティション/別ビュー（全国 base・県 base・縫合・県ロールアップ）が同じ
  table_name を共有する（N:1 のハブ）。**基底 key は table_name と決して一致しない**。
- **key : stem = 1:1**（stem = "census_" ＋ key が慣習・test で一意性を担保）。stem は出力ファイル名＝物理 identity。
- 分類改訂等で「同名では畳めない別 fact」になる場合のみ、**粒度語でない弁別子**で別 family を立てる
  （例: occupation_major12 / occupation_major10）。粒度語（_prefecture 等）を family名に入れると
  key の area suffix と衝突するため避ける。
- family名の閉じた語彙は下記 FAMILIES に集約し、test で全 table_name ∈ FAMILIES を強制する。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from data_forge.sources.estat import (
    age5,
    age5_municipality,
    daynight,
    family_type,
    households,
    industry,
    labor_force,
    occupation,
    population,
)


@dataclass(frozen=True)
class Dataset:
    """1データセットの定義。

    ソース固有の取得パラメータは `source_params` に閉じ込め、
    レジストリ自体はデータソースに依存しない語彙で保つ。
    （例: e-Stat の statsDataId は `source_params={"stats_data_id": ...}`）
    """

    key: str
    source: str  # ソース識別子（"estat" など）
    source_params: dict[str, Any]  # ソース固有の取得パラメータ
    cleaner: Callable[[pl.DataFrame], pl.DataFrame]  # tidy DF → 配布用 DF
    stem: str  # 出力ファイル名の語幹
    table_name: str  # SQLite テーブル名
    index_columns: list[str] = field(default_factory=list)
    # アトム抽出時の市区町村レベルの明示上書き（None なら年から自動判定）。同じ年でも
    # e-Stat 製品ごとに level の意味が違う表（例: age5 旗艦の 2000＝令和型 level4/6）で使う。
    muni_levels: frozenset[int] | None = None


@dataclass(frozen=True)
class StitchedDataset:
    """複数の基底データセットを縫合した派生データセット（複数年を year 軸で結合）。

    各 upstream を fetch→clean した結果（同一スキーマ）を `combine.combine_years` で結合する。
    汎用の依存グラフはまだ作らず具体を表す最小の型。

    default_join は既定の正規化モード（CLI --join で上書き可）:
    - "union" … 各年当時の境界のまま縦積み（生）
    - "aggregate_to_base" … 合併で消えた旧コードを後継自治体へ畳み連続時系列にする（配布正典）
    - "prefecture" … 市区町村アトムを県プレフィックスで束ねる空間集約ビュー
    grain は combine_years の一意性ガードの粒度（既定＝area×sex×year。分類軸が増える fact だけ上書き）。
    preliminary_upstreams は確定集約の**後段**で継ぎ足す速報 upstream で
    `data_status=preliminary` を付与する（provenance.splice_preliminary）。
    空なら来歴列は付かない。
    """

    key: str
    upstreams: list[str]  # 基底 Dataset のキー
    title: str  # 結合表の出典メタ用タイトル
    stem: str
    table_name: str
    index_columns: list[str] = field(default_factory=list)
    default_join: str = "union"
    grain: list[str] = field(default_factory=lambda: ["area_code", "sex_code", "year"])
    preliminary_upstreams: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectedDataset:
    """既製の時系列帳票（e-Stat 時系列データ製品）を area 軸で union するだけの派生。

    StitchedDataset（縫合）と対になる「射影」フロー。
    各 upstream は既に全年を持つ時系列で、disjoint な area パーティションを単純に縦積みする。
    （例: 全国 00000 ＋ 47 都道府県）
    年の縫合・合併畳み込み（area master）・速報 splice は持たない
    （＝combine.combine_years の重機構ではなく combine.union_areas を通る）。
    分類軸が増える fact（例: 年齢区分）は grain を上書きして disjoint 検証の粒度を明示する。
    """

    key: str
    upstreams: list[str]  # 既製時系列の disjoint な area パーティション（基底 Dataset キー）
    title: str
    stem: str
    table_name: str
    index_columns: list[str] = field(default_factory=list)
    grain: list[str] = field(default_factory=lambda: ["area_code", "sex_code", "year"])


# 各サブ辞書・DATASETS・get_dataset で共有するエントリ型。
DatasetEntry = Dataset | StitchedDataset | ProjectedDataset


# ファミリー台帳＝table_name の閉じた語彙（＝出力される論理 fact の一覧）。
# 各エントリの table_name は必ずこの集合の要素（test_datasets で強制）。
# 新 family 追加時のみここに1語足す。命名規約はモジュール docstring を参照。
FAMILIES: frozenset[str] = frozenset(
    {
        "population",  # 男女別人口
        "population_by_age",  # 年齢3区分×男女別人口
        "population_by_age5",  # 年齢5歳階級×男女別人口（市区町村=旗艦／県世紀=companion 同居）
        "daynight_population",  # 昼夜間人口
        "households",  # 世帯の種類別 世帯数・世帯人員
        "family_type",  # 家族類型16区分別 世帯数・世帯人員
        "labor_force",  # 労働力状態3区分×男女別人口
        "industry",  # 産業大分類×男女別就業者数
        "occupation_major12",  # 職業大分類（12区分）×就業者数
        "occupation_major10",  # 職業大分類（旧10区分）×就業者数
    }
)


# === population（男女別人口）================================================
# 軸構造＝population.py docstring／statsDataId 一覧＝docs/datasets/population.md。
# 単年 Dataset（古い順）。cleaner は年（テーブル世代）ごとに別関数で同一8列へ写像する。
_POPULATION: dict[str, DatasetEntry] = {
    "population_1980": Dataset(
        key="population_1980",
        source="estat",
        source_params={"stats_data_id": "0003412413"},
        cleaner=population.clean_1980,
        stem="census_population_1980",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_1985": Dataset(
        key="population_1985",
        source="estat",
        source_params={"stats_data_id": "0003412414"},
        cleaner=population.clean_1985,
        stem="census_population_1985",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_1990": Dataset(
        key="population_1990",
        source="estat",
        source_params={"stats_data_id": "0003412415"},
        cleaner=population.clean_1990,
        stem="census_population_1990",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_1995": Dataset(
        key="population_1995",
        source="estat",
        source_params={"stats_data_id": "0003412416"},
        cleaner=population.clean_1995,
        stem="census_population_1995",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_2000": Dataset(
        key="population_2000",
        source="estat",
        source_params={"stats_data_id": "0003391075"},
        cleaner=population.clean_2000,
        stem="census_population_2000",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_2005": Dataset(
        key="population_2005",
        source="estat",
        source_params={"stats_data_id": "0003408216"},
        cleaner=population.clean_2005,
        stem="census_population_2005",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_2010": Dataset(
        key="population_2010",
        source="estat",
        source_params={"stats_data_id": "0003038587"},
        cleaner=population.clean_2010,
        stem="census_population_2010",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_2015": Dataset(
        key="population_2015",
        source="estat",
        source_params={"stats_data_id": "0003149040"},
        cleaner=population.clean_2015,
        stem="census_population_2015",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_2020": Dataset(
        key="population_2020",
        source="estat",
        source_params={"stats_data_id": "0003445078"},
        cleaner=population.clean_2020,
        stem="census_population_2020",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    # 速報（総人口のみ）。単体では8列を出力し、時系列へは preliminary_upstreams 経由で合流する。
    "population_2025_preliminary": Dataset(
        key="population_2025_preliminary",
        source="estat",
        source_params={"stats_data_id": "0004050397"},
        cleaner=population.clean_2025_preliminary,
        stem="census_population_2025_preliminary",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    # 派生: 男女別人口の時系列（配布正典＝合併畳み込み済み）。2025 速報を preliminary で合流。
    "population_timeseries": StitchedDataset(
        key="population_timeseries",
        upstreams=[
            "population_1980",
            "population_1985",
            "population_1990",
            "population_1995",
            "population_2000",
            "population_2005",
            "population_2010",
            "population_2015",
            "population_2020",
        ],
        title="国勢調査 男女別人口 時系列（1980年・1985年・1990年・1995年・2000年・2005年・2010年・2015年・2020年）",
        stem="census_population_timeseries",
        table_name="population",
        index_columns=["area_code", "sex_code", "year"],
        default_join="aggregate_to_base",
        preliminary_upstreams=["population_2025_preliminary"],
    ),
    # 生（畳み込み無し）版＝census_raw ダッシュボードの合併畳込比較デモ専用。upstreams は上と同じ。
    "population_timeseries_raw": StitchedDataset(
        key="population_timeseries_raw",
        upstreams=[
            "population_1980",
            "population_1985",
            "population_1990",
            "population_1995",
            "population_2000",
            "population_2005",
            "population_2010",
            "population_2015",
            "population_2020",
        ],
        title="国勢調査 男女別人口 時系列（1980年〜2020年・畳み込み無し＝各年当時の境界のまま）",
        stem="census_population_timeseries_raw",
        table_name="population",
        index_columns=["area_code", "sex_code", "year"],
        default_join="union",
    ),
    # 派生（空間軸）: 都道府県別。upstreams は上と同じで default_join=prefecture のみ違える。
    # 世紀 companion（系統B）: 単一 ID「男女別人口 － 全国，都道府県（大正9年～令和2年）」0003410379。
    # 旗艦（市区町村・各回別ID・1980〜）とは別ソースの都道府県 companion（age5 の _prefecture と同型）。
    # 全国と人口集中地区を落とし47県のみ出す（cleaner 参照）。
    "population_prefecture": Dataset(
        key="population_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003410379"},
        cleaner=population.clean_population_prefecture,
        stem="census_population_prefecture",
        table_name="population",
        index_columns=["area_code", "sex_code", "year"],
    ),
    # 派生: 都道府県 世紀 companion の配布正典（1920〜2020 ＋ 2025速報）。
    # 戦略B: 旧・空間rollup 版（市区町村旗艦→県・1980〜）から系統B raw 長期へ張り替え済。
    # 出力シェイプ（47県・全国行なし）は旧版と同一＝ダッシュボードはドロップイン。
    # 単一 upstream を union（year 軸は既に全年揃い）し、後段で 2025速報を splice する
    # （＝preliminary を持つため ProjectedDataset ではなく StitchedDataset(union)）。
    "population_prefecture_timeseries": StitchedDataset(
        key="population_prefecture_timeseries",
        upstreams=["population_prefecture"],
        title="国勢調査 男女別人口 都道府県別時系列（1920年〜2020年 5年間隔 ＋2025速報）",
        stem="census_population_prefecture_timeseries",
        table_name="population",
        index_columns=["area_code", "sex_code", "year"],
        default_join="union",
        preliminary_upstreams=["population_2025_preliminary"],
    ),
}


# === population_by_age（年齢3区分×男女別人口）==============================
# 軸構造＝population.py（clean_population_by_age）／一覧＝docs/datasets/population_by_age.md。
# 全年同型のため cleaner は全年 1 個。年齢不詳は cleaner 側で導出注入する。
_POPULATION_BY_AGE: dict[str, DatasetEntry] = {
    **{
        f"population_by_age_{year}": Dataset(
            key=f"population_by_age_{year}",
            source="estat",
            source_params={"stats_data_id": sid},
            cleaner=population.clean_population_by_age,
            stem=f"census_population_by_age_{year}",
            table_name="population_by_age",
            index_columns=["area_code", "sex_code", "age_class_code"],
        )
        for year, sid in {
            1980: "0003412413",
            1985: "0003412414",
            1990: "0003412415",
            1995: "0003412416",
            2000: "0003412417",
            2005: "0003412418",
            2010: "0003412419",
            2015: "0003412420",
            2020: "0003448299",
        }.items()
    },
    # 派生: 年齢3区分×男女別人口の時系列（配布正典＝合併畳み込み済み）。
    "population_by_age_timeseries": StitchedDataset(
        key="population_by_age_timeseries",
        upstreams=[f"population_by_age_{y}" for y in (1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020)],
        title="国勢調査 年齢3区分×男女別人口 時系列（1980年〜2020年 5年間隔）",
        stem="census_population_by_age_timeseries",
        table_name="population_by_age",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
        grain=["area_code", "sex_code", "age_class_code", "year"],
        default_join="aggregate_to_base",
    ),
    # 世紀 companion（系統B）: 単一 ID「年齢（3区分）別人口 － 全国，都道府県（大正9年～令和2年）」。
    # 旗艦（市区町村・各回別ID・1980〜）とは別ソースの都道府県 companion（age5 の _prefecture と同型）。
    # 本表は男女軸を持たない（総数のみ）。全国は落とし47県のみ出す（cleaner 参照）。
    "population_by_age_prefecture": Dataset(
        key="population_by_age_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003410383"},
        cleaner=population.clean_by_age_prefecture,
        stem="census_population_by_age_prefecture",
        table_name="population_by_age",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
    ),
    # 派生（射影フロー）: 都道府県 世紀 companion の配布正典（1920〜2020・総数のみ）。
    # 旧・空間rollup 版（市区町村旗艦→県・1980〜）から系統B raw 長期へ張り替え済（戦略B）。
    # 出力シェイプ（47県・全国行なし・総数のみ）は旧版と同一＝ダッシュボードはドロップイン。
    "population_by_age_prefecture_timeseries": ProjectedDataset(
        key="population_by_age_prefecture_timeseries",
        upstreams=["population_by_age_prefecture"],
        title="国勢調査 年齢3区分別人口（総数）都道府県別時系列（1920年〜2020年 5年間隔）",
        stem="census_population_by_age_prefecture_timeseries",
        table_name="population_by_age",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
        grain=["area_code", "sex_code", "age_class_code", "year"],
    ),
}


# === daynight_population（昼夜間人口＝従業地・通学地集計）====================
# 軸構造＝daynight.py／一覧＝docs/datasets/daynight_population.md。
# 1990〜2020（1990 が最古。それ以前へ遡れない根拠＝e-Stat 実検索結果は docs 参照）。
# grain は sex ではなく daynight_code。cleaner は全年 1 個。
_DAYNIGHT_POPULATION: dict[str, DatasetEntry] = {
    **{
        f"daynight_population_{year}": Dataset(
            key=f"daynight_population_{year}",
            source="estat",
            source_params={"stats_data_id": sid},
            cleaner=daynight.clean_daynight_population,
            stem=f"census_daynight_population_{year}",
            table_name="daynight_population",
            index_columns=["area_code", "daynight_code"],
        )
        for year, sid in {
            1990: "0003412192",
            1995: "0003412193",
            2000: "0003412194",
            2005: "0003412195",
            2010: "0003412196",
            2015: "0003412197",
            2020: "0004003060",
        }.items()
    },
    # 派生: 昼夜間人口の時系列（配布正典＝合併畳み込み済み）。
    "daynight_population_timeseries": StitchedDataset(
        key="daynight_population_timeseries",
        upstreams=[f"daynight_population_{y}" for y in (1990, 1995, 2000, 2005, 2010, 2015, 2020)],
        title="国勢調査 昼夜間人口（常住地・従業地通学地別人口）時系列（1990年〜2020年 5年間隔）",
        stem="census_daynight_population_timeseries",
        table_name="daynight_population",
        index_columns=["area_code", "daynight_code", "year"],
        grain=["area_code", "daynight_code", "year"],
        default_join="aggregate_to_base",
    ),
    # 派生（空間軸）: 都道府県別。
    "daynight_population_prefecture_timeseries": StitchedDataset(
        key="daynight_population_prefecture_timeseries",
        upstreams=[f"daynight_population_{y}" for y in (1990, 1995, 2000, 2005, 2010, 2015, 2020)],
        title="国勢調査 昼夜間人口（常住地・従業地通学地別人口）都道府県別時系列（1990年〜2020年 5年間隔）",
        stem="census_daynight_population_prefecture_timeseries",
        table_name="daynight_population",
        index_columns=["area_code", "daynight_code", "year"],
        grain=["area_code", "daynight_code", "year"],
        default_join="prefecture",
    ),
}


# === population_by_age5（年齢5歳階級×男女別人口）============================
# 1 family に2系列が同居する（table_name はどちらも bare "population_by_age5"）:
#   (1) 市区町村＝旗艦（系統A・各回別 statsDataId・2010-2020・合併畳込）… _<year> base ＋ _timeseries
#   (2) 全国/都道府県＝世紀 companion（系統B・単一 ID・1920-2020）… _national/_prefecture base ＋ _prefecture_timeseries
# 粒度は key suffix で表し family名（table_name）には持たせない（命名規約＝モジュール docstring）。
# 2010-2020 では両系列の県値が重なる＝物理2重保存せず、系統A→県 rollup==系統B県 を検算オラクル(test)で照合する。

# --- (2) 世紀 companion（系統B）: 単一 ID で一世紀。全国表は area 軸なし→合成（clean_national）。--------------
_POPULATION_BY_AGE5: dict[str, DatasetEntry] = {
    "population_by_age5_national": Dataset(
        key="population_by_age5_national",
        source="estat",
        source_params={"stats_data_id": "0003410380"},
        cleaner=age5.clean_national,
        stem="census_population_by_age5_national",
        table_name="population_by_age5",
        index_columns=["sex_code", "age_class_code", "year"],
    ),
    "population_by_age5_prefecture": Dataset(
        key="population_by_age5_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003410381"},
        cleaner=age5.clean_prefecture,
        stem="census_population_by_age5_prefecture",
        table_name="population_by_age5",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
    ),
    # 派生（射影フロー）: 全国＋47都道府県を area 軸で縦結合した県粒度 1920〜2020 時系列（世紀 companion の配布正典）。
    "population_by_age5_prefecture_timeseries": ProjectedDataset(
        key="population_by_age5_prefecture_timeseries",
        upstreams=["population_by_age5_national", "population_by_age5_prefecture"],
        title="国勢調査 年齢5歳階級×男女別人口 全国・都道府県別時系列（1920年〜2020年 5年間隔）",
        stem="census_population_by_age5_prefecture_timeseries",
        table_name="population_by_age5",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
        grain=["area_code", "sex_code", "age_class_code", "year"],
    ),
}


# --- (1) 市区町村＝旗艦（系統A）: 各回別 statsDataId・市区町村まで。取れる年を year 軸で縫合。--------------------
# 合併畳込あり＝StitchedDataset（aggregate_to_base）。
# nationality 軸あり（総数=1980/85/2000-20・日本人=1990/95/2000-20）＝grain に nationality_code を含める。
# 2000/2005 は各歳表（0000032965/0000033783・同型）から 5歳再掲を抽出。cleaner=age5_municipality。
_POPULATION_BY_AGE5_MUNI_YEARS = (1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020)
_POPULATION_BY_AGE5_MUNI_GRAIN = ["area_code", "sex_code", "nationality_code", "age_class_code", "year"]
# 2000/2005 は各歳の巨大表から 5歳階級の再掲コードだけを拾う。
# 全域(cdCat01=00700)＋5歳コード(cdCat03) にサーバ側絞り込みして行数を抑える（census_source_tables §3-3）。
# 同年の人口時系列製品がlevel3=市区町村なのに対し、
# これらの表は令和型 level4/6 なので muni_levels={4,6} を明示上書きする。
# 2005 は「年齢不詳を除く」表ゆえ不詳(900)コードが無い（2000 は 900 を含む）。
# 1980/1985 も同様に令和型 level4/6 の各歳表（市/区=level4・町村=level6）なので muni_levels={4,6} を
# 明示上書きする（グローバル _MUNI_LEVELS[1980/85]={3} は人口時系列製品向けで、この表には当たらない）。
# 1990/1995 の日本人 5歳階級表 006（0000031405/0000032223）も令和型 level4/6
# （市/区=level4・行政区=level5・町村=level6・level3=支庁の中間集計）。
# グローバル _MUNI_LEVELS[1990/95]={3} のままだと extract_atoms が
# level3 の支庁だけを葉に拾い市区町村フル（level4/6）を全て落とす（日本人カバレッジが 37 コードへ壊れる）ため
# muni_levels={4,6} を明示上書きする。総数版（1990/1995_total＝各歳表00401）は既に {4,6}（下記）。
_AGE5_2000_CODES = ",".join(["T01", *[str(200 + i) for i in range(20)], "500", "900"])
_AGE5_2005_CODES = ",".join(["T01", *[str(200 + i) for i in range(20)], "500"])
_POPULATION_BY_AGE5_MUNI: dict[str, DatasetEntry] = {}
for _year, _sid, _cleaner, _params, _levels in (
    (1980, "0000030127", age5_municipality.clean_1980, {}, {4, 6}),
    (1985, "0000030449", age5_municipality.clean_1985, {}, {4, 6}),
    (1990, "0000031405", age5_municipality.clean_1990, {}, {4, 6}),
    (1995, "0000032223", age5_municipality.clean_1995, {}, {4, 6}),
    (2000, "0000032965", age5_municipality.clean_2000, {"cdCat01": "00700", "cdCat03": _AGE5_2000_CODES}, {4, 6}),
    (2005, "0000033783", age5_municipality.clean_2005, {"cdCat01": "00700", "cdCat03": _AGE5_2005_CODES}, {4, 6}),
    (2010, "0003038591", age5_municipality.clean_2010, {}, None),
    (2015, "0003149862", age5_municipality.clean_2015, {}, None),
    (2020, "0003445162", age5_municipality.clean_2020, {}, None),
):
    _key = f"population_by_age5_{_year}"
    _source_params: dict[str, Any] = {"stats_data_id": _sid}
    if _params:
        _source_params["filters"] = _params
    _POPULATION_BY_AGE5_MUNI[_key] = Dataset(
        key=_key,
        source="estat",
        source_params=_source_params,
        cleaner=_cleaner,
        stem=f"census_population_by_age5_{_year}",
        table_name="population_by_age5",
        index_columns=_POPULATION_BY_AGE5_MUNI_GRAIN,
        muni_levels=frozenset(_levels) if _levels else None,
    )
# 1990/1995 の**総数**（各歳表 00401・国籍軸なし＝nat_const=0）。日本人版（population_by_age5_1990/1995＝
# 5歳階級表 006）とは別ソースで、同年に総数(nat=0)・日本人(nat=1)を別 Dataset で持つ（表形式の非対称＝
# census_source_tables §3-3。2000/2005 は単一表に国籍軸ありで両出しだったのと構造が違う）。令和型 level4/6・
# 巨大各歳表ゆえサーバ側絞り込み（cdCat01=00700・cdCat02=5歳コード〈900不詳あり＝_AGE5_2000_CODES と同一〉）を掛ける。
for _year, _sid in ((1990, "0000031401"), (1995, "0000032219")):
    _key = f"population_by_age5_{_year}_total"
    _POPULATION_BY_AGE5_MUNI[_key] = Dataset(
        key=_key,
        source="estat",
        source_params={
            "stats_data_id": _sid,
            "filters": {"cdCat01": "00700", "cdCat02": _AGE5_2000_CODES},
        },
        cleaner=age5_municipality.clean_1990_1995_total,
        stem=f"census_population_by_age5_{_year}_total",
        table_name="population_by_age5",
        index_columns=_POPULATION_BY_AGE5_MUNI_GRAIN,
        muni_levels=frozenset({4, 6}),
    )
_POPULATION_BY_AGE5_MUNI["population_by_age5_timeseries"] = StitchedDataset(
    key="population_by_age5_timeseries",
    upstreams=[f"population_by_age5_{y}" for y in _POPULATION_BY_AGE5_MUNI_YEARS]
    + ["population_by_age5_1990_total", "population_by_age5_1995_total"],
    title="国勢調査 年齢5歳階級×男女別人口 市区町村別時系列（1980年〜2020年 5年間隔・国籍別・合併補正済み）",
    stem="census_population_by_age5_timeseries",
    table_name="population_by_age5",
    index_columns=_POPULATION_BY_AGE5_MUNI_GRAIN,
    grain=_POPULATION_BY_AGE5_MUNI_GRAIN,
    default_join="aggregate_to_base",
)


# === households（世帯の種類別 世帯数・世帯人員）==============================
# 軸構造＝households.py／一覧＝docs/datasets/households.md。
# 単一 ID に全国＋47都道府県＋全年を含む＝合併なし・射影不要で単独 Dataset 完結（sex 軸なし）。
_HOUSEHOLDS: dict[str, DatasetEntry] = {
    "households": Dataset(
        key="households",
        source="estat",
        source_params={"stats_data_id": "0003410420"},
        cleaner=households.clean_households,
        stem="census_households",
        table_name="households",
        index_columns=["area_code", "household_type_code", "year"],
    ),
}


# === family_type（世帯の家族類型16区分別 世帯数・世帯人員）====================
# 軸構造＝family_type.py／一覧＝docs/datasets/family_type.md。
# households(0003410420) と同型の single-ID fact（全国＋47県＋全年）。分類軸が20コードの4階層ツリー。
_FAMILY_TYPE: dict[str, DatasetEntry] = {
    "family_type": Dataset(
        key="family_type",
        source="estat",
        source_params={"stats_data_id": "0003414255"},
        cleaner=family_type.clean_family_type,
        stem="census_family_type",
        table_name="family_type",
        index_columns=["area_code", "family_type_code", "year"],
    ),
}


# === labor_force（労働力状態3区分×男女別人口）================================
# 軸構造＝labor_force.py／一覧＝docs/datasets/labor_force.md。
# 単一 ID で全年・47県固定＝合併なし。両表とも実 area 軸を持つため cleaner は 1 個共用。
_LABOR_FORCE: dict[str, DatasetEntry] = {
    "labor_force_national": Dataset(
        key="labor_force_national",
        source="estat",
        source_params={"stats_data_id": "0003412175"},
        cleaner=labor_force.clean_labor_force,
        stem="census_labor_force_national",
        table_name="labor_force",
        index_columns=["sex_code", "labor_status_code", "year"],
    ),
    "labor_force_prefecture": Dataset(
        key="labor_force_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003412176"},
        cleaner=labor_force.clean_labor_force,
        stem="census_labor_force_prefecture",
        table_name="labor_force",
        index_columns=["area_code", "sex_code", "labor_status_code", "year"],
    ),
    # 派生（射影フロー）: 全国＋47都道府県を area 軸で縦結合した 1950〜2020 時系列（配布正典）。
    "labor_force_timeseries": ProjectedDataset(
        key="labor_force_timeseries",
        upstreams=["labor_force_national", "labor_force_prefecture"],
        title="国勢調査 労働力状態3区分×男女別人口 全国・都道府県別時系列（1950年〜2020年 5年間隔）",
        stem="census_labor_force_timeseries",
        table_name="labor_force",
        index_columns=["area_code", "sex_code", "labor_status_code", "year"],
        grain=["area_code", "sex_code", "labor_status_code", "year"],
    ),
}


# === industry（産業大分類×男女別就業者数）====================================
# 軸構造＝industry.py／一覧＝docs/datasets/industry.md。
# 全国表は area 軸なし→合成（clean_national）。年カバレッジ非対称（全国のみ 1995/2000）。
_INDUSTRY: dict[str, DatasetEntry] = {
    "industry_national": Dataset(
        key="industry_national",
        source="estat",
        source_params={"stats_data_id": "0003410395"},
        cleaner=industry.clean_national,
        stem="census_industry_national",
        table_name="industry",
        index_columns=["sex_code", "industry_code", "year"],
    ),
    "industry_prefecture": Dataset(
        key="industry_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003410398"},
        cleaner=industry.clean_prefecture,
        stem="census_industry_prefecture",
        table_name="industry",
        index_columns=["area_code", "sex_code", "industry_code", "year"],
    ),
    # 派生（射影フロー）: 全国(1995-2020)＋47都道府県(2005-2020)を area 軸で縦結合。
    # 年カバレッジ非対称でも union は area×分類×year の disjoint で成立する。
    "industry_timeseries": ProjectedDataset(
        key="industry_timeseries",
        upstreams=["industry_national", "industry_prefecture"],
        title="国勢調査 産業大分類×男女別就業者数 全国・都道府県別時系列（全国1995年〜/都道府県2005年〜2020年）",
        stem="census_industry_timeseries",
        table_name="industry",
        index_columns=["area_code", "sex_code", "industry_code", "year"],
        grain=["area_code", "sex_code", "industry_code", "year"],
    ),
}


# === occupation major12（職業大分類・12区分）================================
# 軸構造・呼称 SSoT＝occupation.py／docs/datasets/occupation.md。industry と軸構造完全同型。
# major10 とは大分類が 10↔12 でコード写像不能ゆえ別テーブルにする。
_OCCUPATION_MAJOR12: dict[str, DatasetEntry] = {
    "occupation_major12_national": Dataset(
        key="occupation_major12_national",
        source="estat",
        source_params={"stats_data_id": "0003410408"},
        cleaner=occupation.clean_major12_national,
        stem="census_occupation_major12_national",
        table_name="occupation_major12",
        index_columns=["sex_code", "occupation_code", "year"],
    ),
    "occupation_major12_prefecture": Dataset(
        key="occupation_major12_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003410411"},
        cleaner=occupation.clean_major12_prefecture,
        stem="census_occupation_major12_prefecture",
        table_name="occupation_major12",
        index_columns=["area_code", "sex_code", "occupation_code", "year"],
    ),
    # 派生（射影フロー）: 全国(1995-2020)＋47都道府県(2005-2020)を area 軸で縦結合（年カバレッジ非対称）。
    "occupation_major12_timeseries": ProjectedDataset(
        key="occupation_major12_timeseries",
        upstreams=["occupation_major12_national", "occupation_major12_prefecture"],
        title="国勢調査 職業大分類(12区分)×男女別就業者数 全国・都道府県別時系列（全国1995〜/都道府県2005〜2020）",
        stem="census_occupation_major12_timeseries",
        table_name="occupation_major12",
        index_columns=["area_code", "sex_code", "occupation_code", "year"],
        grain=["area_code", "sex_code", "occupation_code", "year"],
    ),
}


# === occupation major10（職業大分類・10区分／1980延伸）=======================
# 同じ職業軸を分類改訂前へ延伸する別セグメント（呼称 SSoT＝occupation.md）。
# cleaner は major12 と共通本体で class map（OCCUPATION_MAJOR10）だけ差し替える。
_OCCUPATION_MAJOR10: dict[str, DatasetEntry] = {
    "occupation_major10_national": Dataset(
        key="occupation_major10_national",
        source="estat",
        source_params={"stats_data_id": "0003410409"},
        cleaner=occupation.clean_major10_national,
        stem="census_occupation_major10_national",
        table_name="occupation_major10",
        index_columns=["sex_code", "occupation_code", "year"],
    ),
    "occupation_major10_prefecture": Dataset(
        key="occupation_major10_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003410412"},
        cleaner=occupation.clean_major10_prefecture,
        stem="census_occupation_major10_prefecture",
        table_name="occupation_major10",
        index_columns=["area_code", "sex_code", "occupation_code", "year"],
    ),
    # 派生（射影フロー）: 全国(1950-2005)＋47都道府県(1980-2005)を area 軸で縦結合（年カバレッジ非対称）。
    "occupation_major10_timeseries": ProjectedDataset(
        key="occupation_major10_timeseries",
        upstreams=["occupation_major10_national", "occupation_major10_prefecture"],
        title="国勢調査 職業大分類(10区分)×男女別就業者数 全国・都道府県別時系列（全国1950〜/都道府県1980〜2005）",
        stem="census_occupation_major10_timeseries",
        table_name="occupation_major10",
        index_columns=["area_code", "sex_code", "occupation_code", "year"],
        grain=["area_code", "sex_code", "occupation_code", "year"],
    ),
}


# 全サブ辞書を束ねた公開レジストリ。キー重複は許さない（同名 key があれば追加時に気付けるよう assert）。
DATASETS: dict[str, DatasetEntry] = {
    **_POPULATION,
    **_POPULATION_BY_AGE,
    **_DAYNIGHT_POPULATION,
    **_POPULATION_BY_AGE5,
    **_POPULATION_BY_AGE5_MUNI,
    **_HOUSEHOLDS,
    **_FAMILY_TYPE,
    **_LABOR_FORCE,
    **_INDUSTRY,
    **_OCCUPATION_MAJOR12,
    **_OCCUPATION_MAJOR10,
}

_SUBREGISTRIES = (
    _POPULATION,
    _POPULATION_BY_AGE,
    _DAYNIGHT_POPULATION,
    _POPULATION_BY_AGE5,
    _POPULATION_BY_AGE5_MUNI,
    _HOUSEHOLDS,
    _FAMILY_TYPE,
    _LABOR_FORCE,
    _INDUSTRY,
    _OCCUPATION_MAJOR12,
    _OCCUPATION_MAJOR10,
)
if len(DATASETS) != sum(len(sub) for sub in _SUBREGISTRIES):
    raise ValueError("DATASETS: サブ辞書間で key が重複しています")


def get_dataset(key: str) -> DatasetEntry:
    try:
        return DATASETS[key]
    except KeyError:
        available = ", ".join(sorted(DATASETS))
        raise KeyError(f"未知のデータセット: {key!r}（利用可能: {available}）") from None
