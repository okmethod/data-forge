"""年齢5歳階級×男女別人口 age5year family（世紀マクロ＋市区町村ミクロ）。

正典:
- 軸構造 … age5year.py（マクロ）・age5year_municipality.py（ミクロ）
- statsDataId・カバレッジ … docs/distributions/age5year.md

固有判断:
- 1 family に2系列が同居（table_name はどちらも bare "age5year"）:
    (1) 市区町村＝ミクロ（回次別・各回別 statsDataId・2010-2020・合併畳込）… _<year> base ＋ _timeseries
    (2) 全国/都道府県＝世紀マクロ（回次跨・別 ID・1920-2020）… _national/_prefecture base
        ＋地理粒度排他で _national_timeseries / _prefecture_timeseries を別配布へ射影分離
- 粒度は key suffix で表し family名（table_name）には持たせない（命名規約＝モジュール docstring）
- 2010-2020 は両系列の県値が重なる＝物理2重保存せず、回次別→県 rollup==回次跨県 を検算オラクル(test)で照合
"""

from typing import Any

from data_forge.datasets._types import (
    Dataset,
    DatasetEntry,
    ProjectedDataset,
    StitchedDataset,
)
from data_forge.sources.estat import age5year, age5year_municipality

# --- (2) 世紀マクロ（回次跨）: 単一 ID で一世紀。全国表は area 軸なし→合成（clean_national）。--------------
_AGE5YEAR: dict[str, DatasetEntry] = {
    "age5year_national": Dataset(
        key="age5year_national",
        source="estat",
        source_params={"stats_data_id": "0003410380"},
        cleaner=age5year.clean_national,
        stem="census_age5year_national",
        table_name="age5year",
        universe="population",
        index_columns=["sex_code", "age_class_code", "year"],
    ),
    "age5year_prefecture": Dataset(
        key="age5year_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003410381"},
        cleaner=age5year.clean_prefecture,
        stem="census_age5year_prefecture",
        table_name="age5year",
        universe="population",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
    ),
    # 派生（射影フロー）: 47都道府県のみを area 軸で射影した県粒度 1920〜2020 時系列（世紀マクロ の配布正典）。
    # 地理粒度排他: 全国行は含めず _national_timeseries に分離する。
    "age5year_prefecture_timeseries": ProjectedDataset(
        key="age5year_prefecture_timeseries",
        upstreams=["age5year_prefecture"],
        title="国勢調査 年齢5歳階級×男女別人口 都道府県別時系列（1920年〜2020年 5年間隔）",
        stem="census_age5year_prefecture_timeseries",
        table_name="age5year",
        universe="population",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
        grain=["area_code", "sex_code", "age_class_code", "year"],
    ),
    # 派生（射影フロー）: 全国のみ 1920〜2020 時系列（_prefecture から剥離した全国系列）。
    "age5year_national_timeseries": ProjectedDataset(
        key="age5year_national_timeseries",
        upstreams=["age5year_national"],
        title="国勢調査 年齢5歳階級×男女別人口 全国時系列（1920年〜2020年 5年間隔）",
        stem="census_age5year_national_timeseries",
        table_name="age5year",
        universe="population",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
        grain=["area_code", "sex_code", "age_class_code", "year"],
    ),
}


# --- (1) 市区町村＝ミクロ（回次別）: 各回別 statsDataId・市区町村まで。取れる年を year 軸で縫合。--------------------
# 合併畳込あり＝StitchedDataset（aggregate_to_base）。
# nationality 軸あり（総数=1980/85/2000-20・日本人=1990/95/2000-20）＝grain に nationality_code を含める。
# 2000/2005 は各歳表（0000032965/0000033783・同型）から 5歳再掲を抽出。cleaner=age5_municipality。
_AGE5YEAR_MUNI_YEARS = (1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020)
_AGE5YEAR_MUNI_GRAIN = ["area_code", "sex_code", "nationality_code", "age_class_code", "year"]
# 2000/2005 は各歳の巨大表から 5歳階級の再掲コードだけを拾う。
# 全域(cdCat01=00700)＋5歳コード(cdCat03) にサーバ側絞り込みして行数を抑える
# （sources/estat-census-catalog.md「年齢（5歳階級）」節）。
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
_AGE5YEAR_MUNI: dict[str, DatasetEntry] = {}
for _year, _sid, _cleaner, _params, _levels in (
    (1980, "0000030127", age5year_municipality.clean_1980, {}, {4, 6}),
    (1985, "0000030449", age5year_municipality.clean_1985, {}, {4, 6}),
    (1990, "0000031405", age5year_municipality.clean_1990, {}, {4, 6}),
    (1995, "0000032223", age5year_municipality.clean_1995, {}, {4, 6}),
    (2000, "0000032965", age5year_municipality.clean_2000, {"cdCat01": "00700", "cdCat03": _AGE5_2000_CODES}, {4, 6}),
    (2005, "0000033783", age5year_municipality.clean_2005, {"cdCat01": "00700", "cdCat03": _AGE5_2005_CODES}, {4, 6}),
    (2010, "0003038591", age5year_municipality.clean_2010, {}, None),
    (2015, "0003149862", age5year_municipality.clean_2015, {}, None),
    (2020, "0003445162", age5year_municipality.clean_2020, {}, None),
):
    _key = f"age5year_municipality_{_year}"
    _source_params: dict[str, Any] = {"stats_data_id": _sid}
    if _params:
        _source_params["filters"] = _params
    _AGE5YEAR_MUNI[_key] = Dataset(
        key=_key,
        source="estat",
        source_params=_source_params,
        cleaner=_cleaner,
        stem=f"census_age5year_municipality_{_year}",
        table_name="age5year",
        universe="population",
        index_columns=_AGE5YEAR_MUNI_GRAIN,
        muni_levels=frozenset(_levels) if _levels else None,
    )
# 1990/1995 の**総数**（各歳表 00401・国籍軸なし＝nat_const=0）。日本人版（age5year_municipality_1990/1995＝
# 5歳階級表 006）とは別ソースで、同年に総数(nat=0)・日本人(nat=1)を別 Dataset で持つ（表形式の非対称＝
# sources/estat-census-catalog.md「年齢（5歳階級）」節。2000/2005 は単一表に国籍軸ありで両出しだったのと
# 構造が違う）。令和型 level4/6・
# 巨大各歳表ゆえサーバ側絞り込み（cdCat01=00700・cdCat02=5歳コード〈900不詳あり＝_AGE5_2000_CODES と同一〉）を掛ける。
for _year, _sid in ((1990, "0000031401"), (1995, "0000032219")):
    _key = f"age5year_municipality_{_year}_total"
    _AGE5YEAR_MUNI[_key] = Dataset(
        key=_key,
        source="estat",
        source_params={
            "stats_data_id": _sid,
            "filters": {"cdCat01": "00700", "cdCat02": _AGE5_2000_CODES},
        },
        cleaner=age5year_municipality.clean_1990_1995_total,
        stem=f"census_age5year_municipality_{_year}_total",
        table_name="age5year",
        universe="population",
        index_columns=_AGE5YEAR_MUNI_GRAIN,
        muni_levels=frozenset({4, 6}),
    )
_AGE5YEAR_MUNI["age5year_municipality_timeseries"] = StitchedDataset(
    key="age5year_municipality_timeseries",
    upstreams=[f"age5year_municipality_{y}" for y in _AGE5YEAR_MUNI_YEARS]
    + ["age5year_municipality_1990_total", "age5year_municipality_1995_total"],
    title="国勢調査 年齢5歳階級×男女別人口 市区町村別時系列（1980年〜2020年 5年間隔・国籍別・合併補正済み）",
    stem="census_age5year_municipality_timeseries",
    table_name="age5year",
    universe="population",
    index_columns=_AGE5YEAR_MUNI_GRAIN,
    grain=_AGE5YEAR_MUNI_GRAIN,
    default_join="aggregate_to_base",
)


DATASETS: dict[str, DatasetEntry] = {**_AGE5YEAR, **_AGE5YEAR_MUNI}
