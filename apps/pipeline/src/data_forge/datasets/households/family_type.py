"""家族類型16区分別 世帯数・世帯人員 family_type family。

正典:
- 軸構造 … family_type.py
- statsDataId・カバレッジ … docs/distributions/family_type.md

固有判断:
- households(0003410420) と同型の single-ID fact（全国＋47県＋全年）。分類軸が20コードの4階層ツリー
- 地理粒度排他で cleaner の scope により全国/都道府県を別 Dataset に分離（fetch はキャッシュ共有）
"""

import functools

from data_forge.datasets._types import (
    Dataset,
    DatasetEntry,
)
from data_forge.sources.estat import family_type

DATASETS: dict[str, DatasetEntry] = {
    "family_type_prefecture_timeseries": Dataset(
        key="family_type_prefecture_timeseries",
        source="estat",
        source_params={"stats_data_id": "0003414255"},
        cleaner=functools.partial(family_type.clean_family_type, scope="prefecture"),
        stem="census_family_type_prefecture_timeseries",
        table_name="family_type",
        universe="households",
        index_columns=["area_code", "family_type_code", "year"],
    ),
    "family_type_national_timeseries": Dataset(
        key="family_type_national_timeseries",
        source="estat",
        source_params={"stats_data_id": "0003414255"},
        cleaner=functools.partial(family_type.clean_family_type, scope="national"),
        stem="census_family_type_national_timeseries",
        table_name="family_type",
        universe="households",
        index_columns=["area_code", "family_type_code", "year"],
    ),
}
