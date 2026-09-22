"""家族類型16区分別 世帯数・世帯人員 family_type family（回次跨マクロ＋市区町村ミクロ）。

正典:
- 軸構造 … family_type.py（マクロ）・family_type_municipality.py（ミクロ）
- statsDataId・カバレッジ … docs/distributions/family_type.md

固有判断:
- 1 family に2系列が同居（table_name はどちらも bare "family_type"）:
    (1) 全国/都道府県＝回次跨マクロ（単一 ID・1995-2020）… households(0003410420) と同型の single-ID fact。
        地理粒度排他で cleaner の scope により全国/都道府県を別 Dataset に分離（fetch はキャッシュ共有）
    (2) 市区町村＝ミクロ（回次別・各回別 statsDataId・合併畳込）… _<year> base ＋ _timeseries
- 市区町村版は家族類型に別軸（世帯人員 等）が交差する重い表を「総数」で周辺化＝家族類型×area を復元
- 家族類型のコード体系が年で違う（マクロ 100〜290 / 市区町村 0/1/11…）＝cleaner が写像して縫合
"""

import functools
from typing import Any

from data_forge.datasets._types import (
    Dataset,
    DatasetEntry,
    StitchedDataset,
)
from data_forge.sources.estat import family_type, family_type_municipality

# --- (1) 回次跨マクロ（単一 ID・全国/都道府県）: scope 分岐で地理粒度排他に分離。--------------------------
_FAMILY_TYPE: dict[str, DatasetEntry] = {
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


# --- (2) 市区町村＝ミクロ（回次別）: 各回別 statsDataId・市区町村まで。取れる年を year 軸で縫合。----------------
# 合併畳込あり＝StitchedDataset（aggregate_to_base）。family_type 軸を grain に含める。
# 世帯人員は 2020 の軽量表（0003445080）には無い＝cleaner が null 注入（households ミクロと同じ非対称同居）。
# muni_levels は 2020 表が level4=市/6=町村（5=政令市の区は重複ゆえ既定が除外）＝グローバル既定 {4,6} で当たる。
_FAMILY_TYPE_MUNI_YEARS = (2020,)
_FAMILY_TYPE_MUNI_GRAIN = ["area_code", "family_type_code", "year"]
_FAMILY_TYPE_MUNI: dict[str, DatasetEntry] = {}
for _year, _sid, _cleaner, _levels in (
    (2020, "0003445080", family_type_municipality.clean_2020, None),
):
    _key = f"family_type_municipality_{_year}"
    _source_params: dict[str, Any] = {"stats_data_id": _sid}
    _FAMILY_TYPE_MUNI[_key] = Dataset(
        key=_key,
        source="estat",
        source_params=_source_params,
        cleaner=_cleaner,
        stem=f"census_family_type_municipality_{_year}",
        table_name="family_type",
        universe="households",
        index_columns=_FAMILY_TYPE_MUNI_GRAIN,
        muni_levels=frozenset(_levels) if _levels else None,
    )
_FAMILY_TYPE_MUNI["family_type_municipality_timeseries"] = StitchedDataset(
    key="family_type_municipality_timeseries",
    upstreams=[f"family_type_municipality_{y}" for y in _FAMILY_TYPE_MUNI_YEARS],
    title="国勢調査 世帯の家族類型（16区分）別 一般世帯数 市区町村別時系列（2020年・合併補正済み）",
    stem="census_family_type_municipality_timeseries",
    table_name="family_type",
    universe="households",
    index_columns=_FAMILY_TYPE_MUNI_GRAIN,
    grain=_FAMILY_TYPE_MUNI_GRAIN,
    default_join="aggregate_to_base",
)


DATASETS: dict[str, DatasetEntry] = {**_FAMILY_TYPE, **_FAMILY_TYPE_MUNI}
