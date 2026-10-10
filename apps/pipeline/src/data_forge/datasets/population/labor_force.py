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
    StitchedDataset,
)
from data_forge.sources.estat import labor_force, labor_force_municipality

_LABOR_FORCE: dict[str, DatasetEntry] = {
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


# --- 市区町村＝ミクロ（回次別）: 各回別 statsDataId・市区町村まで。取れる年を year 軸で縫合。--------------
# 合併畳込あり＝StitchedDataset。着手＝2015（軽量2次元 marginal・不詳は直接コードあり＝導出注入なし）。
# muni_levels は令和型既定 {4,6}（2005 のみ既定 {3} が当たらず明示上書き）。クロスの総数スライスで marginal を復元:
#   2020=0003450558（労働力状態×年齢×男女・全市区町村版）の年齢総数(cdCat02='00')スライス
#   2010=0003052121（労働力状態×年齢×男女）の年齢総数(cdCat03='000')×DID全域(cdCat01='00710')スライス
#   2005=0000033948（配偶関係×男女×年齢×労働力状態）の配偶総数(cdCat02='000')×年齢総数(cdCat04='515')
#        ×全域(cdCat01='00700')スライス。2005 は不詳独立コード無し＝総数−労働力−非労働力で 999 導出注入。
# ★1950-2000 は着手順に追加。
_LABOR_FORCE_MUNI_GRAIN = ["area_code", "sex_code", "labor_status_code", "year"]
_LABOR_FORCE_MUNI: dict[str, DatasetEntry] = {
    "labor_force_municipality_2005": Dataset(
        key="labor_force_municipality_2005",
        source="estat",
        # 配偶関係×男女×年齢×労働力状態クロス。配偶総数×年齢総数×全域に絞って労働力状態marginalを取得する。
        source_params={
            "stats_data_id": "0000033948",
            "filters": {"cdCat02": "000", "cdCat04": "515", "cdCat01": "00700"},
        },
        cleaner=labor_force_municipality.clean_2005,
        stem="census_labor_force_municipality_2005",
        table_name="labor_force",
        universe="population",
        index_columns=_LABOR_FORCE_MUNI_GRAIN,
        # 2005 のグローバル既定 leaf {3} が当たらず東京23区以外が全滅するため明示上書き（industry 2005 と同じ）。
        muni_levels=frozenset({4, 6}),
    ),
    "labor_force_municipality_2010": Dataset(
        key="labor_force_municipality_2010",
        source="estat",
        # 労働力状態×年齢×男女クロス。年齢総数×DID全域に絞って労働力状態marginalだけ取得する。
        source_params={"stats_data_id": "0003052121", "filters": {"cdCat03": "000", "cdCat01": "00710"}},
        cleaner=labor_force_municipality.clean_2010,
        stem="census_labor_force_municipality_2010",
        table_name="labor_force",
        universe="population",
        index_columns=_LABOR_FORCE_MUNI_GRAIN,
    ),
    "labor_force_municipality_2015": Dataset(
        key="labor_force_municipality_2015",
        source="estat",
        source_params={"stats_data_id": "0003174622"},
        cleaner=labor_force_municipality.clean_2015,
        stem="census_labor_force_municipality_2015",
        table_name="labor_force",
        universe="population",
        index_columns=_LABOR_FORCE_MUNI_GRAIN,
    ),
    "labor_force_municipality_2020": Dataset(
        key="labor_force_municipality_2020",
        source="estat",
        # 労働力状態×年齢×男女クロス。年齢総数に絞って労働力状態marginalだけ取得する。
        # 全市区町村版 0003450558 を採る（姉妹表 0003450579 は人口集中地区=DID 限定で全域をカバーしない）。
        source_params={"stats_data_id": "0003450558", "filters": {"cdCat02": "00"}},
        cleaner=labor_force_municipality.clean_2020,
        stem="census_labor_force_municipality_2020",
        table_name="labor_force",
        universe="population",
        index_columns=_LABOR_FORCE_MUNI_GRAIN,
    ),
    "labor_force_municipality_timeseries": StitchedDataset(
        key="labor_force_municipality_timeseries",
        upstreams=[
            "labor_force_municipality_2005",
            "labor_force_municipality_2010",
            "labor_force_municipality_2015",
            "labor_force_municipality_2020",
        ],
        title="国勢調査 労働力状態×男女別人口 市区町村別時系列（2005・2010・2015・2020年・合併補正済み）",
        stem="census_labor_force_municipality_timeseries",
        table_name="labor_force",
        universe="population",
        index_columns=_LABOR_FORCE_MUNI_GRAIN,
        grain=_LABOR_FORCE_MUNI_GRAIN,
        default_join="aggregate_to_base",
    ),
}


DATASETS: dict[str, DatasetEntry] = {**_LABOR_FORCE, **_LABOR_FORCE_MUNI}
