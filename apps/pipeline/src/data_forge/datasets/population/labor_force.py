"""労働力状態3区分×男女別人口 labor_force family。

正典:
- 軸構造 … labor_force.py
- statsDataId・カバレッジ … docs/distributions/labor_force.md

固有判断:
- 単一 ID で全年・47県固定＝合併なし
- 両表とも実 area 軸を持つため cleaner は 1 個共用
"""

from data_forge.datasets._types import (
    Dataset,
    DatasetEntry,
    ProjectedDataset,
)
from data_forge.sources.estat import labor_force

DATASETS: dict[str, DatasetEntry] = {
    "labor_force_national": Dataset(
        key="labor_force_national",
        source="estat",
        source_params={"stats_data_id": "0003412175"},
        cleaner=labor_force.clean_labor_force,
        stem="census_labor_force_national",
        table_name="labor_force",
        universe="population",
        index_columns=["sex_code", "labor_status_code", "year"],
    ),
    "labor_force_prefecture": Dataset(
        key="labor_force_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003412176"},
        cleaner=labor_force.clean_labor_force,
        stem="census_labor_force_prefecture",
        table_name="labor_force",
        universe="population",
        index_columns=["area_code", "sex_code", "labor_status_code", "year"],
    ),
    # 派生（射影フロー）: 47都道府県のみを area 軸で射影した 1950〜2020 時系列（配布正典）。
    # 地理粒度排他: 全国行は含めず _national_timeseries に分離する。
    "labor_force_prefecture_timeseries": ProjectedDataset(
        key="labor_force_prefecture_timeseries",
        upstreams=["labor_force_prefecture"],
        title="国勢調査 労働力状態3区分×男女別人口 都道府県別時系列（1950年〜2020年 5年間隔）",
        stem="census_labor_force_prefecture_timeseries",
        table_name="labor_force",
        universe="population",
        index_columns=["area_code", "sex_code", "labor_status_code", "year"],
        grain=["area_code", "sex_code", "labor_status_code", "year"],
    ),
    # 派生（射影フロー）: 全国のみ 1950〜2020 時系列（剥離した全国系列）。
    "labor_force_national_timeseries": ProjectedDataset(
        key="labor_force_national_timeseries",
        upstreams=["labor_force_national"],
        title="国勢調査 労働力状態3区分×男女別人口 全国時系列（1950年〜2020年 5年間隔）",
        stem="census_labor_force_national_timeseries",
        table_name="labor_force",
        universe="population",
        index_columns=["area_code", "sex_code", "labor_status_code", "year"],
        grain=["area_code", "sex_code", "labor_status_code", "year"],
    ),
}
