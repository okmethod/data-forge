"""世帯の種類別 世帯数・世帯人員 households family。

正典:
- 軸構造 … households.py
- statsDataId・カバレッジ … docs/distributions/households.md

固有判断:
- 単一 ID に全国＋47都道府県＋全年を含む＝合併なし・射影不要
- 地理粒度排他で cleaner の scope により全国/都道府県を別 Dataset に分離（同一 ID＝fetch はキャッシュ共有）
"""

import functools

from data_forge.datasets._types import (
    Dataset,
    DatasetEntry,
)
from data_forge.sources.estat import households

DATASETS: dict[str, DatasetEntry] = {
    "households_prefecture_timeseries": Dataset(
        key="households_prefecture_timeseries",
        source="estat",
        source_params={"stats_data_id": "0003410420"},
        cleaner=functools.partial(households.clean_households, scope="prefecture"),
        stem="census_households_prefecture_timeseries",
        table_name="households",
        universe="households",
        index_columns=["area_code", "household_type_code", "year"],
    ),
    "households_national_timeseries": Dataset(
        key="households_national_timeseries",
        source="estat",
        source_params={"stats_data_id": "0003410420"},
        cleaner=functools.partial(households.clean_households, scope="national"),
        stem="census_households_national_timeseries",
        table_name="households",
        universe="households",
        index_columns=["area_code", "household_type_code", "year"],
    ),
}
