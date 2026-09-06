"""昼夜間人口 daynight family。

正典:
- 軸構造 … daynight.py
- statsDataId・カバレッジ … docs/distributions/daynight.md

固有判断:
- 1990〜2020（1990 が最古・それ以前へ遡れない根拠は docs 参照）
- grain は sex ではなく daynight_code
- cleaner は全年 1 個
"""

from data_forge.datasets._types import (
    Dataset,
    DatasetEntry,
    StitchedDataset,
)
from data_forge.sources.estat import daynight

DATASETS: dict[str, DatasetEntry] = {
    **{
        f"daynight_municipality_{year}": Dataset(
            key=f"daynight_municipality_{year}",
            source="estat",
            source_params={"stats_data_id": sid},
            cleaner=daynight.clean_daynight_population,
            stem=f"census_daynight_municipality_{year}",
            table_name="daynight",
            universe="population",
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
    "daynight_municipality_timeseries": StitchedDataset(
        key="daynight_municipality_timeseries",
        upstreams=[f"daynight_municipality_{y}" for y in (1990, 1995, 2000, 2005, 2010, 2015, 2020)],
        title="国勢調査 昼夜間人口（常住地・従業地通学地別人口）時系列（1990年〜2020年 5年間隔）",
        stem="census_daynight_municipality_timeseries",
        table_name="daynight",
        universe="population",
        index_columns=["area_code", "daynight_code", "year"],
        grain=["area_code", "daynight_code", "year"],
        default_join="aggregate_to_base",
    ),
    # 派生（空間軸）: 都道府県別。
    "daynight_prefecture_timeseries": StitchedDataset(
        key="daynight_prefecture_timeseries",
        upstreams=[f"daynight_municipality_{y}" for y in (1990, 1995, 2000, 2005, 2010, 2015, 2020)],
        title="国勢調査 昼夜間人口（常住地・従業地通学地別人口）都道府県別時系列（1990年〜2020年 5年間隔）",
        stem="census_daynight_prefecture_timeseries",
        table_name="daynight",
        universe="population",
        index_columns=["area_code", "daynight_code", "year"],
        grain=["area_code", "daynight_code", "year"],
        default_join="prefecture",
    ),
}
