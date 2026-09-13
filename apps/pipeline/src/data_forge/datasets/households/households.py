"""世帯の種類別 世帯数・世帯人員 households family（回次跨マクロ＋市区町村ミクロ）。

正典:
- 軸構造 … households.py（マクロ）・households_municipality.py（ミクロ）
- statsDataId・カバレッジ … docs/distributions/households.md

固有判断:
- 1 family に2系列が同居（table_name はどちらも bare "households"）:
    (1) 全国/都道府県＝回次跨マクロ（単一 ID・1960-2020）… 地理粒度排他で national/prefecture を scope 分離
    (2) 市区町村＝ミクロ（回次別・各回別 statsDataId・1985-2020・合併畳込）… _<year> base ＋ _timeseries
- マクロは単一 ID に全国＋47都道府県が同居＝合併なし・射影不要（scope 分岐・同一 ID＝fetch キャッシュ共有）
- 世帯人員(household_members)は 2015/2020 のミクロ表のみ取れる＝非対称同居（他年は null。household_type 軸は不変）
- 2010-2020 は両系列の県値が重なる＝物理2重保存せず、回次別→県 rollup==回次跨県 を検算オラクル(crossfact)で照合
"""

import functools
from typing import Any

from data_forge.datasets._types import (
    Dataset,
    DatasetEntry,
    StitchedDataset,
)
from data_forge.sources.estat import households, households_municipality

# --- (1) 回次跨マクロ（単一 ID・全国/都道府県）: scope 分岐で地理粒度排他に分離。--------------------------
_HOUSEHOLDS: dict[str, DatasetEntry] = {
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


# --- (2) 市区町村＝ミクロ（回次別）: 各回別 statsDataId・市区町村まで。取れる年を year 軸で縫合。----------------
# 合併畳込あり＝StitchedDataset（aggregate_to_base）。household_type 軸を grain に含める。
# 1980 は「一般/施設」体系の市区町村世帯数表が無く欠＝1985 始まり（docs/sources/estat-census-catalog.md）。
# 世帯人員は 2015/2020 のみ（非対称同居・cleaner が他年は null 注入）。
_HOUSEHOLDS_MUNI_YEARS = (1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020)
_HOUSEHOLDS_MUNI_GRAIN = ["area_code", "household_type_code", "year"]
# 1985-2005 の各回表は令和型 level4/6（市/区=level4・町村=level6）だが、グローバル _MUNI_LEVELS[1985..2005]={3}
# は人口時系列製品向けで当たらない。省くと extract_atoms が level3（郡/支庁の中間集計）を葉に拾い市区町村フルに
# 達しないため muni_levels={4,6} を明示上書きする（age5year ミクロと同じ理由）。2010-2020 はグローバル既定 {4,6}。
_HOUSEHOLDS_MUNI: dict[str, DatasetEntry] = {}
for _year, _sid, _cleaner, _levels in (
    (1985, "0000030448", households_municipality.clean_1985, {4, 6}),
    (1990, "0000031400", households_municipality.clean_1990, {4, 6}),
    (1995, "0000032218", households_municipality.clean_1995, {4, 6}),
    (2000, "0000032964", households_municipality.clean_2000, {4, 6}),
    (2005, "0000033786", households_municipality.clean_2005, {4, 6}),
    (2010, "0003038587", households_municipality.clean_2010, None),
    (2015, "0003149040", households_municipality.clean_2015, None),
    (2020, "0003445098", households_municipality.clean_2020, None),
):
    _key = f"households_municipality_{_year}"
    _source_params: dict[str, Any] = {"stats_data_id": _sid}
    _HOUSEHOLDS_MUNI[_key] = Dataset(
        key=_key,
        source="estat",
        source_params=_source_params,
        cleaner=_cleaner,
        stem=f"census_households_municipality_{_year}",
        table_name="households",
        universe="households",
        index_columns=_HOUSEHOLDS_MUNI_GRAIN,
        muni_levels=frozenset(_levels) if _levels else None,
    )
_HOUSEHOLDS_MUNI["households_municipality_timeseries"] = StitchedDataset(
    key="households_municipality_timeseries",
    upstreams=[f"households_municipality_{y}" for y in _HOUSEHOLDS_MUNI_YEARS],
    title="国勢調査 世帯の種類別 世帯数・世帯人員 市区町村別時系列（1985年〜2020年・合併補正済み）",
    stem="census_households_municipality_timeseries",
    table_name="households",
    universe="households",
    index_columns=_HOUSEHOLDS_MUNI_GRAIN,
    grain=_HOUSEHOLDS_MUNI_GRAIN,
    default_join="aggregate_to_base",
)


DATASETS: dict[str, DatasetEntry] = {**_HOUSEHOLDS, **_HOUSEHOLDS_MUNI}
