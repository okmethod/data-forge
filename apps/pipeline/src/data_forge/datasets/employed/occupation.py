"""職業大分類×就業者数 occupation family（12区分＋旧10区分の2 family を同居）。

正典:
- 軸構造・呼称 … occupation.py
- statsDataId・カバレッジ … docs/distributions/occupation.md

固有判断:
- industry と軸構造完全同型
- major12 と major10 は大分類 10↔12 でコード写像不能ゆえ別テーブル（別 family）
- cleaner は共通本体で class map（OCCUPATION_MAJOR10）だけ差し替える
"""

from data_forge.datasets._types import (
    Dataset,
    DatasetEntry,
    ProjectedDataset,
    StitchedDataset,
)
from data_forge.sources.estat import occupation, occupation_municipality

# --- major12（職業大分類・12区分）---
_OCCUPATION_MAJOR12: dict[str, DatasetEntry] = {
    "occupation_major12_national": Dataset(
        key="occupation_major12_national",
        source="estat",
        source_params={"stats_data_id": "0003410408"},
        cleaner=occupation.clean_major12_national,
        stem="census_occupation_major12_national",
        table_name="occupation_major12",
        universe="employed",
        index_columns=["sex_code", "occupation_code", "year"],
    ),
    "occupation_major12_prefecture": Dataset(
        key="occupation_major12_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003410411"},
        cleaner=occupation.clean_major12_prefecture,
        stem="census_occupation_major12_prefecture",
        table_name="occupation_major12",
        universe="employed",
        index_columns=["area_code", "sex_code", "occupation_code", "year"],
    ),
    # 派生（射影フロー）: 47都道府県のみ(2005-2020)を area 軸で射影。
    # 地理粒度排他: 全国行は含めず _national_timeseries に分離する。
    "occupation_major12_prefecture_timeseries": ProjectedDataset(
        key="occupation_major12_prefecture_timeseries",
        upstreams=["occupation_major12_prefecture"],
        title="国勢調査 職業大分類(12区分)×男女別就業者数 都道府県別時系列（2005年〜2020年）",
        stem="census_occupation_major12_prefecture_timeseries",
        table_name="occupation_major12",
        universe="employed",
        index_columns=["area_code", "sex_code", "occupation_code", "year"],
        grain=["area_code", "sex_code", "occupation_code", "year"],
    ),
    # 派生（射影フロー）: 全国のみ(1995-2020) 時系列（剥離した全国系列）。
    "occupation_major12_national_timeseries": ProjectedDataset(
        key="occupation_major12_national_timeseries",
        upstreams=["occupation_major12_national"],
        title="国勢調査 職業大分類(12区分)×男女別就業者数 全国時系列（1995年〜2020年）",
        stem="census_occupation_major12_national_timeseries",
        table_name="occupation_major12",
        universe="employed",
        index_columns=["area_code", "sex_code", "occupation_code", "year"],
        grain=["area_code", "sex_code", "occupation_code", "year"],
    ),
}


# --- major10（職業大分類・旧10区分／1980延伸）: 同じ職業軸を分類改訂前へ延伸する別セグメント。---
_OCCUPATION_MAJOR10: dict[str, DatasetEntry] = {
    "occupation_major10_national": Dataset(
        key="occupation_major10_national",
        source="estat",
        source_params={"stats_data_id": "0003410409"},
        cleaner=occupation.clean_major10_national,
        stem="census_occupation_major10_national",
        table_name="occupation_major10",
        universe="employed",
        index_columns=["sex_code", "occupation_code", "year"],
    ),
    "occupation_major10_prefecture": Dataset(
        key="occupation_major10_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003410412"},
        cleaner=occupation.clean_major10_prefecture,
        stem="census_occupation_major10_prefecture",
        table_name="occupation_major10",
        universe="employed",
        index_columns=["area_code", "sex_code", "occupation_code", "year"],
    ),
    # 派生（射影フロー）: 47都道府県のみ(1980-2005)を area 軸で射影。
    # 地理粒度排他: 全国行は含めず _national_timeseries に分離する。
    "occupation_major10_prefecture_timeseries": ProjectedDataset(
        key="occupation_major10_prefecture_timeseries",
        upstreams=["occupation_major10_prefecture"],
        title="国勢調査 職業大分類(10区分)×男女別就業者数 都道府県別時系列（1980年〜2005年）",
        stem="census_occupation_major10_prefecture_timeseries",
        table_name="occupation_major10",
        universe="employed",
        index_columns=["area_code", "sex_code", "occupation_code", "year"],
        grain=["area_code", "sex_code", "occupation_code", "year"],
    ),
    # 派生（射影フロー）: 全国のみ(1950-2005) 時系列（剥離した全国系列）。
    "occupation_major10_national_timeseries": ProjectedDataset(
        key="occupation_major10_national_timeseries",
        upstreams=["occupation_major10_national"],
        title="国勢調査 職業大分類(10区分)×男女別就業者数 全国時系列（1950年〜2005年）",
        stem="census_occupation_major10_national_timeseries",
        table_name="occupation_major10",
        universe="employed",
        index_columns=["area_code", "sex_code", "occupation_code", "year"],
        grain=["area_code", "sex_code", "occupation_code", "year"],
    ),
}


# --- 市区町村＝ミクロ（回次別）: major12 に同居（2010/2015/2020 は 12区分で major12 と同ツリー）。----------
# 合併畳込あり＝StitchedDataset。着手＝2015（軽量2次元 marginal）。muni_levels は令和型既定 {4,6}。
# 2020/2010 は多次元クロス表の総数スライスで職業marginalを復元する（industry 市区町村と同手法）:
#   2020=産業×職業(0003450542・industry 2020 と同一表)の産業総数(cdCat02='0')スライス
#   2010=産業×職業×従業上の地位(0003067223)の産業総数(cdCat04='000')×地位総数(cdCat02='000')スライス
# 2005 は職業新分類の軽量2次元 marginal(0003024287)で、新分類は 12区分＝マクロ major12 と同ツリー
# （旧大分類 major10 は参考表 0003410412 のみ＝市区町村版は無い）。ミクロ major12 は 2005 始まり。
_OCCUPATION_MUNI_GRAIN = ["area_code", "sex_code", "occupation_code", "year"]
_OCCUPATION_MUNI: dict[str, DatasetEntry] = {
    "occupation_major12_municipality_2005": Dataset(
        key="occupation_major12_municipality_2005",
        source="estat",
        source_params={"stats_data_id": "0003024287"},  # 職業新分類×男女 市区町村＝軽量2次元 marginal
        cleaner=occupation_municipality.clean_2005,
        stem="census_occupation_major12_municipality_2005",
        table_name="occupation_major12",
        universe="employed",
        index_columns=_OCCUPATION_MUNI_GRAIN,
        # 2005 のグローバル既定 leaf {3}（人口時系列製品向け）が当たらず、明示上書きしないと東京23区以外が
        # 葉に採られず縫合で全滅する（industry_municipality_2005 と同じ理由）。
        muni_levels=frozenset({4, 6}),
    ),
    "occupation_major12_municipality_2010": Dataset(
        key="occupation_major12_municipality_2010",
        source="estat",
        # 産業×職業×従業上の地位クロス。産業総数×地位総数に絞って職業marginalだけ取得する。
        source_params={"stats_data_id": "0003067223", "filters": {"cdCat04": "000", "cdCat02": "000"}},
        cleaner=occupation_municipality.clean_2010,
        stem="census_occupation_major12_municipality_2010",
        table_name="occupation_major12",
        universe="employed",
        index_columns=_OCCUPATION_MUNI_GRAIN,
    ),
    "occupation_major12_municipality_2015": Dataset(
        key="occupation_major12_municipality_2015",
        source="estat",
        source_params={"stats_data_id": "0003176482"},
        cleaner=occupation_municipality.clean_2015,
        stem="census_occupation_major12_municipality_2015",
        table_name="occupation_major12",
        universe="employed",
        index_columns=_OCCUPATION_MUNI_GRAIN,
    ),
    "occupation_major12_municipality_2020": Dataset(
        key="occupation_major12_municipality_2020",
        source="estat",
        # 産業×職業クロス（industry 2020 と同一表）。職業marginalは産業総数(cat02='0')スライスで復元。
        source_params={"stats_data_id": "0003450542", "filters": {"cdCat02": "0"}},
        cleaner=occupation_municipality.clean_2020,
        stem="census_occupation_major12_municipality_2020",
        table_name="occupation_major12",
        universe="employed",
        index_columns=_OCCUPATION_MUNI_GRAIN,
    ),
    "occupation_major12_municipality_timeseries": StitchedDataset(
        key="occupation_major12_municipality_timeseries",
        upstreams=[
            "occupation_major12_municipality_2005",
            "occupation_major12_municipality_2010",
            "occupation_major12_municipality_2015",
            "occupation_major12_municipality_2020",
        ],
        title="国勢調査 職業大分類(12区分)×男女別就業者数 市区町村別時系列（2005・2010・2015・2020年・合併補正済み）",
        stem="census_occupation_major12_municipality_timeseries",
        table_name="occupation_major12",
        universe="employed",
        index_columns=_OCCUPATION_MUNI_GRAIN,
        grain=_OCCUPATION_MUNI_GRAIN,
        default_join="aggregate_to_base",
    ),
}


DATASETS: dict[str, DatasetEntry] = {**_OCCUPATION_MAJOR12, **_OCCUPATION_MAJOR10, **_OCCUPATION_MUNI}
