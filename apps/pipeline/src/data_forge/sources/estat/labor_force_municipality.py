"""国勢調査 労働力状態×男女別人口 市区町村版（labor_force のミクロ系列）のクレンジング。

各回の就業状態等基本集計（回次別）の市区町村「労働力状態」表。同じ table_name "labor_force" に
同居する全国／都道府県の回次跨マクロ（単一 ID・labor_force.py）と対をなし、市区町村まで下りる。
着手＝2015（0003174622・唯一「男女×労働力状態×市区町村」の軽量2次元 marginal が揃う年）。
2020/2010 は労働力状態×年齢クロス表の年齢総数スライスで marginal を復元する。
2005 は配偶関係×男女×年齢×労働力状態クロス（0000033948）の配偶総数×年齢総数×全域スライスで復元する。

**帳票の事実は docs/sources/estat-census-catalog.md「労働力状態」節が正典**
（ここには再掲しない＝ドリフト防止）。

Note（実装判断のみ）:
- **労働力状態コードが年で違う**: 市区町村版（2015=cat02・0000/0010/0020…）はマクロの労働力状態コード
  （100〜140＋不詳999＝labor_force.LABOR_STATUS）と別体系。年別マップでマクロコードへ写像して縫合する。
- **不詳の扱いは年で2系統**: 2015/2010/2020 は不詳を独立コード（2015 cat02 "0170"・2010 cat02 "017"・
  2020 cat03 "3"）で持つ＝そのまま 999 へ写像し導出注入しない。2005（0000033948）は不詳の独立コードが無く
  総数に内包されるため、マクロ（labor_force.py）と同じく 総数−労働力人口−非労働力人口 で 999 を導出注入する
  （_inject_labor_unknown を再利用）。就業者120/完全失業者130 は労働力人口110 の再掲だが L1 は code 別突合ゆえ無害。
- **多次元クロスからの marginal 復元（2020/2010）**: 軽量2次元表は 2020/2010 に無く、労働力状態×年齢クロスの
  年齢総数スライスで労働力状態marginalを復元する。2020＝0003450558（労働力状態×年齢×男女・全市区町村版。
  姉妹表 0003450579 は人口集中地区=DID 限定で全域を欠くため不採用）の年齢総数
  （cat02='00'）スライス（filters cdCat02='00'）。2010＝0003052121（労働力状態×年齢×男女）の年齢総数
  （cat03='000'）×DID全域（cat01='00710'）スライス（filters cdCat03='000'・cdCat01='00710'）。
- **軸コードが年で違う**: 労働力状態=2015 cat02（4桁）／2020 cat03（1桁）／2010 cat02（3桁）／2005 cat05（3桁）、
  男女=2015 cat04 SEX_MUNI（4桁）／2020 cat01 SEX_MUNI_2020（1桁）／2010・2005 SEX_MUNI_2010（3桁）で年別マップ。
- **周辺のみ**: 非労働力の内訳（家事/通学/その他 lv2）・就業者の内訳（主に仕事等 lv3）・労働力率(%)行は
  マップ非収載＝自動除外。
- **合併畳込（aggregate_to_base）は共有インフラに委ね**、clean は全 area level を素直に出す。

出力スキーマ10列（labor_force.py マクロと同一・測度列は population）。列は _finalize の select が正典。
grain＝area×sex×labor_status×year。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.labor_force import _LABOR_UNKNOWN, LABOR_STATUS, _inject_labor_unknown
from data_forge.sources.estat.transform import (
    SEX_MUNI,
    SEX_MUNI_2010,
    SEX_MUNI_2020,
    area_passthrough_cols,
    code_name_cols,
    exclude_imputed_version_expr,
    int_value_expr,
    year_from_time_code_expr,
)

# 表章項目(tab): "4"=15歳以上人口（2015 市区町村版）。労働力率(%)は率行(cat02 0180)で別＝採らない。
# 2020="2020_01"（人口）・2010="320"（15歳以上人口）。
_TAB_POPULATION = "4"
_TAB_POPULATION_2020 = "2020_01"
_TAB_POPULATION_2010 = "320"
# 2010 表は全域(00710)／人口集中地区(00711) の DID 軸を持つ＝全域で潰す（industry 2010 と同型）。
_DID_WHOLE_2010 = "00710"

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

# 労働力状態_2020（cat03）→ 同上。就業者内訳(111-114 lv3)・非労働力内訳(21/22/23 lv2)はマップ非収載＝除外。
_LF_2020 = {
    "0": "100",  # 総数
    "1": "110",  # 労働力人口
    "11": "120",  # 就業者（労働力人口の再掲・lv2）
    "12": "130",  # 完全失業者（労働力人口の再掲・lv2）
    "2": "140",  # 非労働力人口
    "3": _LABOR_UNKNOWN[0],  # 労働力状態「不詳」
}

# 労働力状態_2010（cat02）→ 同上。就業者内訳(003-006 lv3)・非労働力内訳(014/015/016 lv2)はマップ非収載＝除外。
_LF_2010 = {
    "000": "100",  # 総数
    "001": "110",  # 労働力人口
    "002": "120",  # 就業者（労働力人口の再掲・lv2）
    "012": "130",  # 完全失業者（労働力人口の再掲・lv2）
    "013": "140",  # 非労働力人口
    "017": _LABOR_UNKNOWN[0],  # 労働力状態「不詳」
}

# labor_status_code → 名称（マクロ LABOR_STATUS ＋ 不詳）。
_LF_NAME = {**LABOR_STATUS, _LABOR_UNKNOWN[0]: _LABOR_UNKNOWN[1]}


def _finalize(
    df: pl.DataFrame,
    *,
    lf_col: str,
    lf_map: dict[str, str],
    sex_col: str,
    sex_map: dict[str, tuple[str, str]] = SEX_MUNI,
) -> pl.DataFrame:
    """労働力状態コード（ソース）を持つ tidy を配布用10列へ写像する（年別マップ差し替えで共用）。

    男女コードは年で体系が違う（2015=4桁 SEX_MUNI／2020=1桁 SEX_MUNI_2020／2010=3桁 SEX_MUNI_2010）ため
    sex_map で差し替える。
    """
    return (
        df.filter(pl.col(lf_col).is_in(list(lf_map)))
        .filter(pl.col(sex_col).is_in(list(sex_map)))
        .filter(exclude_imputed_version_expr())
        .select(
            *area_passthrough_cols(),
            *code_name_cols(sex_col, sex_map, "sex"),
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


def clean_2020(tidy: pl.DataFrame) -> pl.DataFrame:
    """2020（0003450558・労働力状態×年齢×男女・全市区町村版）用。年齢総数(cat02='00')で絞り労働力状態marginalを復元。

    労働力状態=cat03（1桁）・男女=cat01（1桁 SEX_MUNI_2020）・tab=2020_01（人口）・area=level4/6。
    取得は filters cdCat02='00' で年齢総数に絞り込む（source_params 側）。
    """
    return _finalize(
        tidy.filter(pl.col("tab_code") == _TAB_POPULATION_2020).filter(pl.col("cat02_code") == "00"),
        lf_col="cat03_code",
        lf_map=_LF_2020,
        sex_col="cat01_code",
        sex_map=SEX_MUNI_2020,
    )


def clean_2010(tidy: pl.DataFrame) -> pl.DataFrame:
    """2010（0003052121・労働力状態×年齢×男女）用。年齢総数×DID全域で絞り労働力状態marginalを復元。

    労働力状態=cat02（3桁）・男女=cat04（3桁 SEX_MUNI_2010）・年齢=cat03（総数000）・DID=cat01（全域00710）・
    tab=320。取得は filters cdCat03='000'・cdCat01='00710' で絞る（source_params 側）。
    """
    return _finalize(
        tidy.filter(pl.col("tab_code") == _TAB_POPULATION_2010)
        .filter(pl.col("cat01_code") == _DID_WHOLE_2010)
        .filter(pl.col("cat03_code") == "000"),
        lf_col="cat02_code",
        lf_map=_LF_2010,
        sex_col="cat04_code",
        sex_map=SEX_MUNI_2010,
    )


# 労働力状態_2005（cat05）→ 同上。ただし 2005 は不詳の独立コードが無く総数(000)に内包される
# （2010/2015/2020 と違う）＝マクロ labor_force.py と同じく 999 を導出注入する（下記 clean_2005）。
# 就業者内訳(003-006 lv3)・再掲雇用者(007-011)・非労働力内訳(014/015/016 lv2)はマップ非収載＝除外。
_LF_2005 = {
    "000": "100",  # 総数（労働力状態「不詳」を含む）
    "001": "110",  # 労働力人口
    "002": "120",  # 就業者（労働力人口の再掲）
    "012": "130",  # 完全失業者（労働力人口の再掲）
    "013": "140",  # 非労働力人口
}


def clean_2005(tidy: pl.DataFrame) -> pl.DataFrame:
    """2005（0000033948・配偶関係×男女×年齢×労働力状態）用。配偶総数×年齢総数×全域で労働力状態marginalを復元。

    労働力状態=cat05（3桁）・男女=cat03（3桁 SEX_MUNI_2010）・配偶関係=cat02（総数000）・年齢=cat04（総数515）・
    DID=cat01（全域00700）。取得は filters cdCat02='000'・cdCat04='515'・cdCat01='00700' で絞る（source_params 側）。
    この表は単一表章項目で tab 絞り不要。**不詳(999)は独立コードが無く総数に内包されるため、マクロと同じく
    総数−労働力人口−非労働力人口で導出注入する**（2010/2015/2020 は独立コードを持つので注入しない点と対照）。
    旧市町村 level7 は持たず、2005 のグローバル既定 leaf {3} が当たらないため muni_levels={4,6} を明示上書きする。
    """
    fact = _finalize(
        tidy,
        lf_col="cat05_code",
        lf_map=_LF_2005,
        sex_col="cat03_code",
        sex_map=SEX_MUNI_2010,
    )
    return _inject_labor_unknown(fact)
