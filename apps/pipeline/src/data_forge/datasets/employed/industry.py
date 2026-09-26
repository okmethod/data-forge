"""産業大分類×男女別就業者数 industry family。

正典:
- 軸構造 … industry.py
- statsDataId・カバレッジ … docs/distributions/industry.md

固有判断:
- 全国表は area 軸なし→合成（clean_national）
- 年カバレッジ非対称（全国のみ 1995/2000）
"""

from data_forge.datasets._types import (
    Dataset,
    DatasetEntry,
    ProjectedDataset,
    StitchedDataset,
)
from data_forge.sources.estat import industry, industry_municipality

_INDUSTRY: dict[str, DatasetEntry] = {
    "industry_national": Dataset(
        key="industry_national",
        source="estat",
        source_params={"stats_data_id": "0003410395"},
        cleaner=industry.clean_national,
        stem="census_industry_national",
        table_name="industry",
        universe="employed",
        index_columns=["sex_code", "industry_code", "year"],
    ),
    "industry_prefecture": Dataset(
        key="industry_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003410398"},
        cleaner=industry.clean_prefecture,
        stem="census_industry_prefecture",
        table_name="industry",
        universe="employed",
        index_columns=["area_code", "sex_code", "industry_code", "year"],
    ),
    # 派生（射影フロー）: 47都道府県のみ(2005-2020)を area 軸で射影。
    # 地理粒度排他: 全国行は含めず _national_timeseries に分離する。
    "industry_prefecture_timeseries": ProjectedDataset(
        key="industry_prefecture_timeseries",
        upstreams=["industry_prefecture"],
        title="国勢調査 産業大分類×男女別就業者数 都道府県別時系列（2005年〜2020年）",
        stem="census_industry_prefecture_timeseries",
        table_name="industry",
        universe="employed",
        index_columns=["area_code", "sex_code", "industry_code", "year"],
        grain=["area_code", "sex_code", "industry_code", "year"],
    ),
    # 派生（射影フロー）: 全国のみ(1995-2020) 時系列（剥離した全国系列）。
    "industry_national_timeseries": ProjectedDataset(
        key="industry_national_timeseries",
        upstreams=["industry_national"],
        title="国勢調査 産業大分類×男女別就業者数 全国時系列（1995年〜2020年）",
        stem="census_industry_national_timeseries",
        table_name="industry",
        universe="employed",
        index_columns=["area_code", "sex_code", "industry_code", "year"],
        grain=["area_code", "sex_code", "industry_code", "year"],
    ),
}


# --- 市区町村＝ミクロ（回次別）: 各回別 statsDataId・市区町村まで。取れる年を year 軸で縫合。--------------
# 合併畳込あり＝StitchedDataset（aggregate_to_base）。着手＝2015（軽量2次元 marginal・20区分A-T）。
# muni_levels: 2015 は令和型 level4/6 でグローバル既定と一致＝上書き不要。
# ★2020/2010/1995-2005 は着手順に追加（2020=純カウント marginal 廃止で復元要・2010=多次元のみ・
#   1995-2005=15/19区分の分類断層で別マップ／別セグメント判断）。
_INDUSTRY_MUNI_GRAIN = ["area_code", "sex_code", "industry_code", "year"]
_INDUSTRY_MUNI: dict[str, DatasetEntry] = {
    "industry_municipality_2015": Dataset(
        key="industry_municipality_2015",
        source="estat",
        source_params={"stats_data_id": "0003175084"},
        cleaner=industry_municipality.clean_2015,
        stem="census_industry_municipality_2015",
        table_name="industry",
        universe="employed",
        index_columns=_INDUSTRY_MUNI_GRAIN,
    ),
    "industry_municipality_timeseries": StitchedDataset(
        key="industry_municipality_timeseries",
        upstreams=["industry_municipality_2015"],
        title="国勢調査 産業大分類×男女別就業者数 市区町村別時系列（2015年・合併補正済み）",
        stem="census_industry_municipality_timeseries",
        table_name="industry",
        universe="employed",
        index_columns=_INDUSTRY_MUNI_GRAIN,
        grain=_INDUSTRY_MUNI_GRAIN,
        default_join="aggregate_to_base",
    ),
}


DATASETS: dict[str, DatasetEntry] = {**_INDUSTRY, **_INDUSTRY_MUNI}
