"""男女別人口 population family。

正典:
- 軸構造 … population.py
- statsDataId・カバレッジ … docs/distributions/population.md

固有判断:
- 単年 Dataset（古い順）
- cleaner は年（テーブル世代）ごとに別関数で同一8列へ写像する
"""

from data_forge.datasets._types import (
    Dataset,
    DatasetEntry,
    StitchedDataset,
)
from data_forge.sources.estat import population

DATASETS: dict[str, DatasetEntry] = {
    "population_municipality_1980": Dataset(
        key="population_municipality_1980",
        source="estat",
        source_params={"stats_data_id": "0003412413"},
        cleaner=population.clean_1980,
        stem="census_population_municipality_1980",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_municipality_1985": Dataset(
        key="population_municipality_1985",
        source="estat",
        source_params={"stats_data_id": "0003412414"},
        cleaner=population.clean_1985,
        stem="census_population_municipality_1985",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_municipality_1990": Dataset(
        key="population_municipality_1990",
        source="estat",
        source_params={"stats_data_id": "0003412415"},
        cleaner=population.clean_1990,
        stem="census_population_municipality_1990",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_municipality_1995": Dataset(
        key="population_municipality_1995",
        source="estat",
        source_params={"stats_data_id": "0003412416"},
        cleaner=population.clean_1995,
        stem="census_population_municipality_1995",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_municipality_2000": Dataset(
        key="population_municipality_2000",
        source="estat",
        source_params={"stats_data_id": "0003391075"},
        cleaner=population.clean_2000,
        stem="census_population_municipality_2000",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_municipality_2005": Dataset(
        key="population_municipality_2005",
        source="estat",
        source_params={"stats_data_id": "0003408216"},
        cleaner=population.clean_2005,
        stem="census_population_municipality_2005",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_municipality_2010": Dataset(
        key="population_municipality_2010",
        source="estat",
        source_params={"stats_data_id": "0003038587"},
        cleaner=population.clean_2010,
        stem="census_population_municipality_2010",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_municipality_2015": Dataset(
        key="population_municipality_2015",
        source="estat",
        source_params={"stats_data_id": "0003149040"},
        cleaner=population.clean_2015,
        stem="census_population_municipality_2015",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code"],
    ),
    "population_municipality_2020": Dataset(
        key="population_municipality_2020",
        source="estat",
        source_params={"stats_data_id": "0003445078"},
        cleaner=population.clean_2020,
        stem="census_population_municipality_2020",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code"],
    ),
    # 速報（総人口のみ）。単体では8列を出力し、時系列へは preliminary_upstreams 経由で合流する。
    "population_municipality_2025_preliminary": Dataset(
        key="population_municipality_2025_preliminary",
        source="estat",
        source_params={"stats_data_id": "0004050397"},
        cleaner=population.clean_2025_preliminary,
        stem="census_population_municipality_2025_preliminary",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code"],
    ),
    # 派生: 男女別人口の時系列（配布正典＝合併畳み込み済み）。2025 速報を preliminary で合流。
    "population_municipality_timeseries": StitchedDataset(
        key="population_municipality_timeseries",
        upstreams=[
            "population_municipality_1980",
            "population_municipality_1985",
            "population_municipality_1990",
            "population_municipality_1995",
            "population_municipality_2000",
            "population_municipality_2005",
            "population_municipality_2010",
            "population_municipality_2015",
            "population_municipality_2020",
        ],
        title="国勢調査 男女別人口 時系列（1980年・1985年・1990年・1995年・2000年・2005年・2010年・2015年・2020年）",
        stem="census_population_municipality_timeseries",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code", "year"],
        default_join="aggregate_to_base",
        preliminary_upstreams=["population_municipality_2025_preliminary"],
    ),
    # 生（畳み込み無し）版＝census_raw ダッシュボードの合併畳込比較デモ専用。upstreams は上と同じ。
    "population_municipality_timeseries_raw": StitchedDataset(
        key="population_municipality_timeseries_raw",
        upstreams=[
            "population_municipality_1980",
            "population_municipality_1985",
            "population_municipality_1990",
            "population_municipality_1995",
            "population_municipality_2000",
            "population_municipality_2005",
            "population_municipality_2010",
            "population_municipality_2015",
            "population_municipality_2020",
        ],
        title="国勢調査 男女別人口 時系列（1980年〜2020年・畳み込み無し＝各年当時の境界のまま）",
        stem="census_population_municipality_timeseries_raw",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code", "year"],
        default_join="union",
    ),
    # 派生（空間軸）: 都道府県別。upstreams は上と同じで default_join=prefecture のみ違える。
    # 世紀マクロ（回次跨）: 単一 ID「男女別人口 － 全国，都道府県（大正9年～令和2年）」0003410379。
    # ミクロ（市区町村・各回別ID・1980〜）とは別ソースの都道府県マクロ（age5 の _prefecture と同型）。
    # 全国と人口集中地区を落とし47県のみ出す（cleaner 参照）。
    "population_prefecture": Dataset(
        key="population_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003410379"},
        cleaner=population.clean_population_prefecture,
        stem="census_population_prefecture",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code", "year"],
    ),
    # 派生: 都道府県 世紀マクロ の配布正典（1920〜2020 ＋ 2025速報）。
    # 戦略B: 旧・空間rollup 版（市区町村ミクロ→県・1980〜）から回次跨 raw 長期へ張り替え済。
    # 出力シェイプ（47県・全国行なし）は旧版と同一＝ダッシュボードはドロップイン。
    # 単一 upstream を union（year 軸は既に全年揃い）し、後段で 2025速報を splice する
    # （＝preliminary を持つため ProjectedDataset ではなく StitchedDataset(union)）。
    "population_prefecture_timeseries": StitchedDataset(
        key="population_prefecture_timeseries",
        upstreams=["population_prefecture"],
        title="国勢調査 男女別人口 都道府県別時系列（1920年〜2020年 5年間隔 ＋2025速報）",
        stem="census_population_prefecture_timeseries",
        table_name="population",
        universe="population",
        index_columns=["area_code", "sex_code", "year"],
        default_join="union",
        preliminary_upstreams=["population_municipality_2025_preliminary"],
    ),
}
