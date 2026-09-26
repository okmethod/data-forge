"""国勢調査 労働力状態×男女別人口 市区町村版（labor_force のミクロ系列）のクレンジング。

各回の就業状態等基本集計（回次別）の市区町村「労働力状態」表。同じ table_name "labor_force" に
同居する全国／都道府県の回次跨マクロ（単一 ID・labor_force.py）と対をなし、市区町村まで下りる。
着手＝2015（0003174622・唯一「男女×労働力状態×市区町村」の軽量2次元 marginal が揃う年）。

**帳票の事実は docs/sources/estat-census-catalog.md「労働力状態」節が正典**
（ここには再掲しない＝ドリフト防止）。

Note（実装判断のみ）:
- **労働力状態コードが年で違う**: 市区町村版（2015=cat02・0000/0010/0020…）はマクロの労働力状態コード
  （100〜140＋不詳999＝labor_force.LABOR_STATUS）と別体系。年別マップでマクロコードへ写像して縫合する。
- **不詳は直接コードあり＝導出注入しない**: マクロ（labor_force.py）は不詳を 総数−労働力人口−非労働力人口 で
  導出注入するが、市区町村版 2015 は不詳(cat02 "0170")を独立コードで持つ＝そのまま 999 へ写像する
  （就業者120/完全失業者130 は労働力人口110 の再掲なので周辺に含めても保存はマクロと同じく閉じる）。
- **周辺のみ**: 非労働力の内訳（家事/通学/その他 lv2）・就業者の内訳（主に仕事等 lv3）・労働力率(%)行は
  マップ非収載＝自動除外。
- **合併畳込（aggregate_to_base）は共有インフラに委ね**、clean は全 area level を素直に出す。

出力スキーマ10列（labor_force.py マクロと同一・測度列は population）。列は _finalize の select が正典。
grain＝area×sex×labor_status×year。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.labor_force import _LABOR_UNKNOWN, LABOR_STATUS
from data_forge.sources.estat.transform import (
    SEX_MUNI,
    area_passthrough_cols,
    code_name_cols,
    exclude_imputed_version_expr,
    int_value_expr,
    year_from_time_code_expr,
)

# 表章項目(tab): "4"=15歳以上人口（2015 市区町村版）。労働力率(%)は率行(cat02 0180)で別＝採らない。
_TAB_POPULATION = "4"

# 労働力状態_2015（cat02）→ マクロ labor_force.LABOR_STATUS の鍵（100〜140）＋不詳(999)。
# 非労働力内訳(0140/0150/0160)・就業者内訳(0030-0060)・労働力率(0180)はマップ非収載＝自動除外。
_LF_2015 = {
    "0000": "100",  # 総数
    "0010": "110",  # 労働力人口
    "0020": "120",  # 就業者（労働力人口の再掲）
    "0120": "130",  # 完全失業者（労働力人口の再掲）
    "0130": "140",  # 非労働力人口
    "0170": _LABOR_UNKNOWN[0],  # 労働力状態「不詳」（直接コードあり＝導出注入しない）
}

# labor_status_code → 名称（マクロ LABOR_STATUS ＋ 不詳）。
_LF_NAME = {**LABOR_STATUS, _LABOR_UNKNOWN[0]: _LABOR_UNKNOWN[1]}


def _finalize(df: pl.DataFrame, *, lf_col: str, lf_map: dict[str, str], sex_col: str) -> pl.DataFrame:
    """労働力状態コード（ソース）を持つ tidy を配布用10列へ写像する（年別マップ差し替えで共用）。"""
    return (
        df.filter(pl.col(lf_col).is_in(list(lf_map)))
        .filter(pl.col(sex_col).is_in(list(SEX_MUNI)))
        .filter(exclude_imputed_version_expr())
        .select(
            *area_passthrough_cols(),
            *code_name_cols(sex_col, SEX_MUNI, "sex"),
            pl.col(lf_col).replace_strict(lf_map).alias("labor_status_code"),
            pl.col(lf_col).replace_strict(lf_map).replace_strict(_LF_NAME).alias("labor_status"),
            year_from_time_code_expr(),
            int_value_expr().alias("population"),
        )
        .with_columns(is_current_expr())
        .sort("area_code", "sex_code", "labor_status_code", "year")
    )


def clean_2015(tidy: pl.DataFrame) -> pl.DataFrame:
    """2015（0003174622）用。労働力状態=cat02・男女=cat04・tab=4（人口）・area=level4/6。"""
    return _finalize(
        tidy.filter(pl.col("tab_code") == _TAB_POPULATION),
        lf_col="cat02_code",
        lf_map=_LF_2015,
        sex_col="cat04_code",
    )
