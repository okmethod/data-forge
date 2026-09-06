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
)
from data_forge.sources.estat import industry

DATASETS: dict[str, DatasetEntry] = {
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
