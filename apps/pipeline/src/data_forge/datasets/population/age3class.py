"""年齢3区分×男女別人口 age3class family。

正典:
- 軸構造 … population.py（clean_age3class）
- statsDataId・カバレッジ … docs/distributions/age3class.md

固有判断:
- 全年同型のため cleaner は全年 1 個
- 年齢不詳は cleaner 側で導出注入する
"""

from data_forge.datasets._types import (
    Dataset,
    DatasetEntry,
    ProjectedDataset,
    StitchedDataset,
)
from data_forge.sources.estat import population

DATASETS: dict[str, DatasetEntry] = {
    **{
        f"age3class_municipality_{year}": Dataset(
            key=f"age3class_municipality_{year}",
            source="estat",
            source_params={"stats_data_id": sid},
            cleaner=population.clean_population_by_age,
            stem=f"census_age3class_municipality_{year}",
            table_name="age3class",
            universe="population",
            index_columns=["area_code", "sex_code", "age_class_code"],
        )
        for year, sid in {
            1980: "0003412413",
            1985: "0003412414",
            1990: "0003412415",
            1995: "0003412416",
            2000: "0003412417",
            2005: "0003412418",
            2010: "0003412419",
            2015: "0003412420",
            2020: "0003448299",
        }.items()
    },
    # 派生: 年齢3区分×男女別人口の時系列（配布正典＝合併畳み込み済み）。
    "age3class_municipality_timeseries": StitchedDataset(
        key="age3class_municipality_timeseries",
        upstreams=[f"age3class_municipality_{y}" for y in (1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020)],
        title="国勢調査 年齢3区分×男女別人口 時系列（1980年〜2020年 5年間隔）",
        stem="census_age3class_municipality_timeseries",
        table_name="age3class",
        universe="population",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
        grain=["area_code", "sex_code", "age_class_code", "year"],
        default_join="aggregate_to_base",
    ),
    # 世紀マクロ（回次跨）: 単一 ID「年齢（3区分）別人口 － 全国，都道府県（大正9年～令和2年）」。
    # ミクロ（市区町村・各回別ID・1980〜）とは別ソースの都道府県マクロ（age5 の _prefecture と同型）。
    # 本表は男女軸を持たない（総数のみ）。全国は落とし47県のみ出す（cleaner 参照）。
    "age3class_prefecture": Dataset(
        key="age3class_prefecture",
        source="estat",
        source_params={"stats_data_id": "0003410383"},
        cleaner=population.clean_by_age_prefecture,
        stem="census_age3class_prefecture",
        table_name="age3class",
        universe="population",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
    ),
    # 派生（射影フロー）: 都道府県 世紀マクロ の配布正典（1920〜2020・総数のみ）。
    # 旧・空間rollup 版（市区町村ミクロ→県・1980〜）から回次跨 raw 長期へ張り替え済（戦略B）。
    # 出力シェイプ（47県・全国行なし・総数のみ）は旧版と同一＝ダッシュボードはドロップイン。
    "age3class_prefecture_timeseries": ProjectedDataset(
        key="age3class_prefecture_timeseries",
        upstreams=["age3class_prefecture"],
        title="国勢調査 年齢3区分別人口（総数）都道府県別時系列（1920年〜2020年 5年間隔）",
        stem="census_age3class_prefecture_timeseries",
        table_name="age3class",
        universe="population",
        index_columns=["area_code", "sex_code", "age_class_code", "year"],
        grain=["area_code", "sex_code", "age_class_code", "year"],
    ),
}
