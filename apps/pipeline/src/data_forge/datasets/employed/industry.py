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
# muni_levels: 2010/2015/2020 は level4/6（2010 は旧市町村 level7 も）＝グローバル既定と一致。
#   2005 のみグローバル既定 {3} が当たらず level4/6 を明示上書き（下記 Dataset 参照）。
# 純カウントの軽量2次元表は 2010/2020 に無く、多次元クロス表の総数スライスで産業marginalを復元する:
#   2020=産業×職業(0003450542)の職業総数(cdCat03='0')・2010=産業×従業上の地位(0003052127)の地位総数
#   (cdCat03='000')＋DID全域(cdCat01='00710')。2020 表は産業総数スライスで occupation 2020 にも使える。
# 2005（0003010959）は 2015 同型の軽量2次元 marginal＝新産業分類特別集計で 20区分に組み替え済み。
# ★1995/2000（15区分）は着手順に追加（分類断層で別マップ／別セグメント判断）。
_INDUSTRY_MUNI_GRAIN = ["area_code", "sex_code", "industry_code", "year"]
_INDUSTRY_MUNI: dict[str, DatasetEntry] = {
    "industry_municipality_2005": Dataset(
        key="industry_municipality_2005",
        source="estat",
        source_params={"stats_data_id": "0003010959"},  # 軽量2次元 marginal＝絞り不要
        cleaner=industry_municipality.clean_2005,
        stem="census_industry_municipality_2005",
        table_name="industry",
        universe="employed",
        index_columns=_INDUSTRY_MUNI_GRAIN,
        # この表は令和型 level4/6（市/特別区=4・町村=6）だがグローバル既定 {3}（人口時系列製品向け）が
        # 当たらず、明示上書きしないと東京23区以外が葉に採られず縫合で全滅する（family_type 2005 と同じ理由）。
        muni_levels=frozenset({4, 6}),
    ),
    "industry_municipality_2010": Dataset(
        key="industry_municipality_2010",
        source="estat",
        # 産業×従業上の地位クロス表（旧市町村 level7 あり）。DID全域×地位総数に絞って産業marginalだけ取得する。
        source_params={"stats_data_id": "0003052127", "filters": {"cdCat01": "00710", "cdCat03": "000"}},
        cleaner=industry_municipality.clean_2010,
        stem="census_industry_municipality_2010",
        table_name="industry",
        universe="employed",
        index_columns=_INDUSTRY_MUNI_GRAIN,
    ),
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
    "industry_municipality_2020": Dataset(
        key="industry_municipality_2020",
        source="estat",
        # 産業×職業クロス表。職業総数(cdCat03='0')に絞って産業marginalだけ取得する（巨大表の転送抑制）。
        source_params={"stats_data_id": "0003450542", "filters": {"cdCat03": "0"}},
        cleaner=industry_municipality.clean_2020,
        stem="census_industry_municipality_2020",
        table_name="industry",
        universe="employed",
        index_columns=_INDUSTRY_MUNI_GRAIN,
    ),
    "industry_municipality_timeseries": StitchedDataset(
        key="industry_municipality_timeseries",
        upstreams=[
            "industry_municipality_2005",
            "industry_municipality_2010",
            "industry_municipality_2015",
            "industry_municipality_2020",
        ],
        title="国勢調査 産業大分類×男女別就業者数 市区町村別時系列（2005・2010・2015・2020年・合併補正済み）",
        stem="census_industry_municipality_timeseries",
        table_name="industry",
        universe="employed",
        index_columns=_INDUSTRY_MUNI_GRAIN,
        grain=_INDUSTRY_MUNI_GRAIN,
        default_join="aggregate_to_base",
    ),
}


DATASETS: dict[str, DatasetEntry] = {**_INDUSTRY, **_INDUSTRY_MUNI}
