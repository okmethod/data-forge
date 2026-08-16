"""データセット定義レジストリ。

新しいデータセット（統計表）の追加は、原則このファイルにエントリを
1つ足すだけで済むようにする。ソース固有の取得・整形処理は
sources/ 以下の関数を参照する。
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from data_forge.sources.estat import age5, daynight, households, population


@dataclass(frozen=True)
class Dataset:
    """1データセットの定義。

    ソース固有の取得パラメータは `source_params` に閉じ込め、レジストリ自体は
    データソースに依存しない語彙で保つ（例: e-Stat の statsDataId は
    `source_params={"stats_data_id": ...}`）。
    """

    key: str
    source: str  # ソース識別子（"estat" など）
    source_params: dict[str, Any]  # ソース固有の取得パラメータ
    cleaner: Callable[[pl.DataFrame], pl.DataFrame]  # tidy DF → 配布用 DF
    stem: str  # 出力ファイル名の語幹
    table_name: str  # SQLite テーブル名
    index_columns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StitchedDataset:
    """複数の基底データセットを合成した派生データセット（例: 複数年結合）。

    `upstreams` は基底 Dataset のキー。各 upstream を fetch→clean した結果
    （同一スキーマ）を `combine.combine_years` で結合する。汎用の依存グラフは
    まだ作らず、具体1件のみを表す最小の型（実例が2つ揃ったら再検討）。
    """

    key: str
    upstreams: list[str]  # 基底 Dataset のキー
    title: str  # 結合表の出典メタ用タイトル
    stem: str
    table_name: str
    index_columns: list[str] = field(default_factory=list)
    default_join: str = "union"  # 既定の正規化モード（CLI --join で上書き可）
    # 結合の粒度（combine_years の一意性ガード用）。既定＝area×sex×year。
    # 分類軸が増える fact（例: 年齢区分）だけ明示的に上書きする。
    grain: list[str] = field(default_factory=lambda: ["area_code", "sex_code", "year"])
    # 速報 upstream（基底 Dataset キー）。確定 upstream を集約し終えた**後段**で継ぎ足し、
    # `data_status=preliminary` を付与する（provenance.splice_preliminary）。
    # 最新境界＝合併 rollup 不要なので集約機械を通さず、area 集約を無改修に保つ。
    # 空なら来歴列は付かず既存出力と同一（＝速報が出た fact だけ column が生える）。
    preliminary_upstreams: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectedDataset:
    """既製の時系列帳票（e-Stat 時系列データ製品）を area 軸で union するだけの派生。

    StitchedDataset（縫合）と対になる「射影」フロー。各 upstream は既に全年を持つ時系列で、
    disjoint な area パーティション（例: 全国 00000 ＋ 47 都道府県）を単純に縦積みする。
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


DATASETS: dict[str, Dataset | StitchedDataset | ProjectedDataset] = {
    # 単年（古い順）。同名でも e-Stat の軸設計は年（テーブル世代）で異なり、
    # 年ごとの cleaner が同一8列スキーマへ写像する。
    # （構造差の詳細は population.py / docs 参照）
    # 1980/1985/1990/1995（0003412413/414/415/416）は同型の「年齢3区分,男女別人口」ファミリー:
    # 男女=cat02・tab=020/cat01=100 で絞り、全国行が無いため 47都道府県合計から復元する。
    # （共通 cleaner _clean_age3class_table）
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
    # 2000/2005（0003391075/0003408216）は同一ファミリー: cat01に測定項目＋男女が融合
    # （100/110/120）・DID軸なし・area level3=市区町村。clean_2000 は 2005 と同設定。
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
    # 2010/2015（0003038587/0003149040）は平成型: tab軸なし・cat01=全域/DID・
    # cat02に表章事項＋男女が統合（コード体系は年で異なる）。全域のみ採用。
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
    # 2020（0003445078）は令和型: tab=人口・cat01=男女(0/1/2)。
    "population_2020": Dataset(
        key="population_2020",
        source="estat",
        source_params={"stats_data_id": "0003445078"},
        cleaner=population.clean_2020,
        stem="census_population_2020",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    # 速報: 令和7年国勢調査 人口速報集計「男女別人口」(0004050397)。2020 と同型の令和型。
    # 総人口のみ（年齢別/昼夜間は速報に無い）。単体では全国/県/市区町村の8列を出力し、
    # 時系列へは preliminary_upstreams 経由で data_status=preliminary として合流する。
    "population_2025_preliminary": Dataset(
        key="population_2025_preliminary",
        source="estat",
        source_params={"stats_data_id": "0004050397"},
        cleaner=population.clean_2025_preliminary,
        stem="census_population_2025_preliminary",
        table_name="population",
        index_columns=["area_code", "sex_code"],
    ),
    # 派生: 1980〜2020 を結合した男女別人口の時系列テーブル。
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
        # 配布正典＝合併畳み込み済み（市制施行・合併で消えた旧コードを後継自治体へ畳み、
        # サンプル市の連続時系列を作れる）。生（union）版は population_timeseries_raw で別出し。
        default_join="aggregate_to_base",
        # 2025 速報を合流（data_status=preliminary）。
        # 速報の全国/県行は splice 前に確定ビューの area_code へ intersection scoping され、市区町村行のみ残る。
        preliminary_upstreams=["population_2025_preliminary"],
    ),
    # 生（畳み込み無し）版。census_raw ダッシュボード＝合併畳込有無の比較デモ専用。
    # population_timeseries と upstreams は同じで stem/既定 join だけ違える（cp 往復を排除）。
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
    # 派生（空間軸）: 都道府県別の男女別人口 時系列。upstreams は population_timeseries と同じで
    # default_join だけ prefecture に振り、市区町村アトムを県プレフィックスで束ねる（events 非依存）。
    # これは新 base fact ではなく派生ビュー（正典＝市区町村粒度は不変）。stem を分けて上書き衝突を回避。
    "population_prefecture_timeseries": StitchedDataset(
        key="population_prefecture_timeseries",
        upstreams=[f"population_{y}" for y in (1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020)],
        title="国勢調査 男女別人口 都道府県別時系列（1980年〜2020年 5年間隔）",
        stem="census_population_prefecture_timeseries",
        table_name="population",
        index_columns=["area_code", "sex_code", "year"],
        default_join="prefecture",
        # 2025 速報を合流。速報の県行(01000 等)が確定の県ビューへ intersection scoping で残る。
        # （県境は不変なので合併 rollup 問題なし＝ダッシュボードが使う粒度）
        preliminary_upstreams=["population_2025_preliminary"],
    ),
    # === population_by_age（年齢3区分×男女別人口）=============================
    # 時系列ファミリー「年齢（3区分），男女別人口及び年齢別割合」(413〜420 / 0003448299)。
    # 全年同型（tab=020/cat01=年齢/cat02=男女・全国行なし）なので cleaner は全年 1 個
    # （population.clean_population_by_age）。年齢不詳は総数−3区分で導出注入する。
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
    # 派生: 1980〜2020 を結合した年齢3区分×男女別人口の時系列テーブル。
    "population_by_age_timeseries": StitchedDataset(
        key="population_by_age_timeseries",
        upstreams=[f"population_by_age_{y}" for y in (1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020)],
        title="国勢調査 年齢3区分×男女別人口 時系列（1980年〜2020年 5年間隔）",
        stem="census_population_by_age_timeseries",
        table_name="population_by_age",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
        grain=["area_code", "sex_code", "age_class_code", "year"],
        # 配布正典＝合併畳み込み済み（population_timeseries と同じ理由）。
        default_join="aggregate_to_base",
    ),
    # 派生（空間軸）: 都道府県別の年齢3区分×男女別人口 時系列（population_prefecture と同型）。
    "population_by_age_prefecture_timeseries": StitchedDataset(
        key="population_by_age_prefecture_timeseries",
        upstreams=[f"population_by_age_{y}" for y in (1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020)],
        title="国勢調査 年齢3区分×男女別人口 都道府県別時系列（1980年〜2020年 5年間隔）",
        stem="census_population_by_age_prefecture_timeseries",
        table_name="population_by_age",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
        grain=["area_code", "sex_code", "age_class_code", "year"],
        default_join="prefecture",
    ),
    # === daynight_population（昼夜間人口＝従業地・通学地集計）====================
    # 時系列ファミリー「常住地又は従業地・通学地別人口（夜間人口・昼間人口）」
    # （statsDataId 0003412192〜197 / 0004003060、1990〜2020）。年齢3区分ファミリーの
    # 同世代・直前連番で area 軸同型（JIS コード・全国行あり）。cat01=100(夜間)/180(昼間) の
    # 2総数のみ採り grain に daynight_code を持つ（sex 軸なし）。cleaner は全年 1 個。
    # area 集約の `*_code` 自動判別が sex/age 以外の軸でも無改修で乗るかの3例目。
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
    # 派生: 1990〜2020 を結合した昼夜間人口の時系列テーブル（1980/1985 は該当表なし）。
    "daynight_population_timeseries": StitchedDataset(
        key="daynight_population_timeseries",
        upstreams=[f"daynight_population_{y}" for y in (1990, 1995, 2000, 2005, 2010, 2015, 2020)],
        title="国勢調査 昼夜間人口（常住地・従業地通学地別人口）時系列（1990年〜2020年 5年間隔）",
        stem="census_daynight_population_timeseries",
        table_name="daynight_population",
        index_columns=["area_code", "daynight_code", "year"],
        grain=["area_code", "daynight_code", "year"],
        # 配布正典＝合併畳み込み済み（population_timeseries と同じ理由）。
        default_join="aggregate_to_base",
    ),
    # 派生（空間軸）: 都道府県別の昼夜間人口 時系列（population_prefecture と同型）。
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
    # === population_by_age5（年齢5歳階級×男女別人口）============================
    # 時系列データ製品「年齢（5歳階級），男女別人口及び人口性比」（全国 0003410380 /
    # 都道府県 0003410381、1920〜2020）。population_by_age（3区分）と違い年ごとの連番ではなく
    # 単一 ID で一世紀を提供＝cleaner は各表 1 個・合併なし＝area master 不要の低コスト fact。
    # 2表は軸同型で差は「全国表は area 軸なし→合成／全国のみ85+を細分」だけ（age5.py 参照）。
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
    # 派生（射影フロー）: 全国＋47都道府県を area 軸で縦結合した 1920〜2020 の 5歳階級時系列（配布正典）。
    # 各 upstream が既に全年を持つ既製時系列＝結合軸は year ではなく area（disjoint な 00000＋47県）で
    # 単純 union するだけ（合併 rollup 不要＝area master を通さない）。grain に age_class_code を持つ。
    "population_by_age5_timeseries": ProjectedDataset(
        key="population_by_age5_timeseries",
        upstreams=["population_by_age5_national", "population_by_age5_prefecture"],
        title="国勢調査 年齢5歳階級×男女別人口 全国・都道府県別時系列（1920年〜2020年 5年間隔）",
        stem="census_population_by_age5_timeseries",
        table_name="population_by_age5",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
        grain=["area_code", "sex_code", "age_class_code", "year"],
    ),
    # === households（世帯の種類別 世帯数・世帯人員）==============================
    # 時系列データ製品「世帯の種類別世帯数及び世帯人員 － 全国，都道府県」(0003410420、
    # その1＝一般世帯及び施設等の世帯・1960〜2020)。単一 ID に全国(level1)＋47都道府県(level2)＋
    # 全年を含む＝合併なし＝area master 不要。全国も県も同一 ID なので age5 のような射影も不要で
    # cleaner 1 個の単独 Dataset で完結する。sex 軸なし・分類軸=世帯の種類(総数/一般/施設)、
    # 世帯数と世帯人員の2測定量を1行に横並べ（1世帯当たり人員は導出可能ゆえ持たない）。
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


def get_dataset(key: str) -> Dataset | StitchedDataset | ProjectedDataset:
    try:
        return DATASETS[key]
    except KeyError:
        available = ", ".join(sorted(DATASETS))
        raise KeyError(f"未知のデータセット: {key!r}（利用可能: {available}）") from None
