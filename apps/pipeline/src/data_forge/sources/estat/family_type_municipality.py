"""国勢調査 世帯の家族類型（16区分）別 一般世帯数・世帯人員 市区町村版（family_type のミクロ系列）のクレンジング。

各回の人口等基本集計（回次別）の市区町村「世帯の家族類型」表。
同じ table_name "family_type" に同居する全国／都道府県のみの
回次跨マクロ（単一 ID・1995-2020／family_type.py）と対をなし、市区町村まで下りる。
対象＝2005〜2020 の各回（★1995/2000 は市区町村版が旧分類しか無く新分類マクロと非互換ゆえ不採用＝下記）。

**帳票の事実は docs/sources/estat-census-catalog.md「家族類型」節が正典**
（ここには再掲しない＝ドリフト防止）＝年別の statsDataId・軸割当/コード体系・分類区分数の非対称・
DID 潰し・muni_levels 上書き。

Note（実装判断のみ）:
- **年別 cleaner**: 市区町村版は家族類型の**コード体系が年で違う**（マクロ 100〜290/999 ＝「16区分A_時系列」に対し、
  市区町村版は 2020=0/1/11…・2015=0000/0010…・2005/2010=0010/0020…）。各年マップでマクロコードへ写像して
  縫合する。マップは getStatsData の実コードで確定する（getMetaInfo と食い違う年がある＝age5year ミクロと同じ罠）。
- **1995/2000 不採用**: 両年の市区町村版は旧分類（A親族/B非親族/C単独）しか無く、新分類マクロと親族ツリー全体で
  非互換（県 rollup の Σ|diff|≒33万/年・写像不能）。occupation major10/12 と同じ分類改訂断層で union 不可。
  2005 は新分類遡及集計（0003032309）で diff=0 ゆえ採り、ミクロは 2005 始まりとする。
- **交差軸の周辺化**: 市区町村版は家族類型に別軸（世帯人員/住宅の所有 等）が交差する重い表なので、
  その軸を「総数」で絞り家族類型×area の周辺分布を復元する（households ミクロの絞り込みと同型）。
- **世帯人員の非対称同居**: tab に世帯数/世帯人員が並ぶ年（2005/2010）は両測度を採り、
  一般世帯数のみの年（2015/2020）は household_members を null 注入する（列は常に持つ＝マクロとスキーマ一致）。
- **家族類型不詳(999)**: 市区町村版が独立コードで直接持つ年（2015=0330・2020=cat02 "4"）はそのまま写像し、
  持たない年（2005/2010）は マクロと同じ **総数−親族のみ−非親族−単独** で導出注入する
  （family_type._inject_unknown を共用）。
- **全域/DID 潰し**（2015=00710）と **muni_levels 上書き**（2005 は令和型 level4/6
  ＝グローバル {3} が当たらない・households ミクロと同じ理由）は datasets 側で設定する。
- **合併畳込（aggregate_to_base）は共有インフラに委ね**、clean は全 area level を素直に出す。

出力スキーマ 9 列（family_type.py マクロと同一）。列は _finalize の select が正典。
grain＝area×family_type×year。
"""

import polars as pl

from data_forge.area.levels import is_current_expr
from data_forge.sources.estat.family_type import _FT_UNKNOWN, FAMILY_TYPE, _inject_unknown
from data_forge.sources.estat.transform import (
    area_passthrough_cols,
    int_value_expr,
    year_from_time_code_expr,
)

# --- 家族類型 入力コード → マクロ「16区分A_時系列」コード（family_type.FAMILY_TYPE の鍵）。--------------------
# ツリーは全年同一16区分で、コード体系だけが違う。（再掲）系（3世代/母子/父子 等）と lv4 詳細
# （夫の親/妻の親）はマップに含めず自動除外する。

# 2020（cat02・0/1/11…）。不詳=cat02 "4" を直接写像。
_FT_2020 = {
    "0": "100", "1": "110", "11": "120", "111": "130", "112": "140", "113": "150", "114": "160",
    "12": "170", "1201": "180", "1202": "190", "1203": "200", "1204": "210", "1205": "220",
    "1206": "230", "1207": "240", "1208": "250", "1209": "260", "1210": "270",
    "2": "280", "3": "290", "4": _FT_UNKNOWN[0],
}  # fmt: skip

# 2015（cat02・4桁 0000/0010…）。不詳=0330 を直接写像。0340（再掲3世代）は除外。
_FT_2015 = {
    "0000": "100", "0010": "110", "0020": "120", "0030": "130", "0040": "140", "0050": "150",
    "0060": "160", "0070": "170", "0080": "180", "0110": "190", "0140": "200", "0170": "210",
    "0200": "220", "0210": "230", "0220": "240", "0250": "250", "0280": "260", "0290": "270",
    "0300": "280", "0310": "290", "0330": _FT_UNKNOWN[0],
}  # fmt: skip

# 2005/2010（家族類型2010・0010/0020…）。不詳コード無し＝導出注入。lv4 詳細(2005)・再掲(0330…)は除外。
_FT_2010 = {
    "0010": "100", "0020": "110", "0030": "120", "0040": "130", "0050": "140", "0060": "150",
    "0070": "160", "0080": "170", "0090": "180", "0120": "190", "0150": "200", "0180": "210",
    "0210": "220", "0220": "230", "0230": "240", "0260": "250", "0290": "260", "0300": "270",
    "0310": "280", "0320": "290",
}  # fmt: skip

# ★1995/2000 は不採用: 市区町村版が旧分類（A親族/B非親族/C単独）しか無く、新分類マクロと親族ツリー全体で
#   非互換（写像不能＝occupation major10/12 と同じ分類改訂断層）。ミクロは 2005（新分類遡及集計）始まり。

# マクロ code → family_type_level（0003414255 cat01_level を実測。ツリー正典＝family_type.FAMILY_TYPE）。
# 100=総数(1) / 110・280・290・999=総数直下(2) / 120・170=核家族・核家族以外(3) / 残りの内訳(4)。
_MACRO_LEVEL = {"100": 1, "110": 2, "280": 2, "290": 2, _FT_UNKNOWN[0]: 2, "120": 3, "170": 3}
_MACRO_LEVEL |= {c: 4 for c in FAMILY_TYPE if c not in _MACRO_LEVEL and c != "100"}

# family_type_code → 名称（マクロ FAMILY_TYPE ＋ 不詳）。
_FT_NAME = {**FAMILY_TYPE, _FT_UNKNOWN[0]: _FT_UNKNOWN[1]}

_JOIN_KEYS = ["area_code", "time_code", "family_type_code"]


def _finalize(df: pl.DataFrame) -> pl.DataFrame:
    """family_type_code / households / household_members / time_code を持つ中間 DF を配布用9列へ写像する。

    area 3列（code/name/level）と time_code、households・household_members 列は入力に揃っている前提。
    """
    return (
        df.select(
            *area_passthrough_cols(),
            pl.col("family_type_code"),
            pl.col("family_type_code").replace_strict(_FT_NAME).alias("family_type"),
            pl.col("family_type_code").replace_strict(_MACRO_LEVEL).cast(pl.Int8).alias("family_type_level"),
            year_from_time_code_expr(),
            pl.col("households"),
            pl.col("household_members"),
        )
        .with_columns(is_current_expr())
        .sort("area_code", "family_type_code", "year")
    )


def _households_only(
    tidy: pl.DataFrame,
    *,
    ft_col: str,
    ft_map: dict[str, str],
    filters: list[tuple[str, str]] | None = None,
) -> pl.DataFrame:
    """一般世帯数のみ（世帯人員なし）の年を配布用9列へ写像する。household_members は null 注入。

    `filters` は周辺化/全域潰しの (列, コード) 群（例: 全域=cat01 "00710"・世帯人員総数=cat03 "0000"）。
    """
    df = tidy
    for col, code in filters or []:
        df = df.filter(pl.col(col) == code)
    df = df.filter(pl.col(f"{ft_col}_code").is_in(list(ft_map))).with_columns(
        pl.col(f"{ft_col}_code").replace_strict(ft_map).alias("family_type_code"),
        int_value_expr().alias("households"),
        pl.lit(None, dtype=pl.Int64).alias("household_members"),
    )
    return _finalize(df)


def _two_measures(
    tidy: pl.DataFrame,
    *,
    ft_col: str,
    ft_map: dict[str, str],
    measure_col: str,
    hh_code: str,
    mem_code: str,
    filters: list[tuple[str, str]] | None = None,
) -> pl.DataFrame:
    """世帯数・世帯人員の両測度を持つ年を配布用9列へ写像し、家族類型不詳(999)を導出注入する。

    測度は `measure_col`（tab）の `hh_code`＝世帯数 / `mem_code`＝世帯人員 で分かれる。
    `filters` は周辺化/全域潰しの (列, コード) 群。不詳コードを持たない年（2005/2010）専用。
    """
    df = tidy
    for col, code in filters or []:
        df = df.filter(pl.col(col) == code)
    df = df.filter(pl.col(f"{ft_col}_code").is_in(list(ft_map))).with_columns(
        pl.col(f"{ft_col}_code").replace_strict(ft_map).alias("family_type_code")
    )
    households = df.filter(pl.col(f"{measure_col}_code") == hh_code).with_columns(int_value_expr().alias("households"))
    members = df.filter(pl.col(f"{measure_col}_code") == mem_code).select(
        *_JOIN_KEYS, int_value_expr().alias("household_members")
    )
    fact = _finalize(households.join(members, on=_JOIN_KEYS, how="left"))
    return _inject_unknown(fact).sort("area_code", "family_type_code", "year")


def clean_2005(tidy: pl.DataFrame) -> pl.DataFrame:
    """2005（0003032309）用。家族類型=cat01（0010…・lv4詳細は無視）・測度=tab(6世帯数/7世帯人員)・交差軸なし。不詳は導出。"""
    return _two_measures(tidy, ft_col="cat01", ft_map=_FT_2010, measure_col="tab", hh_code="6", mem_code="7")


def clean_2010(tidy: pl.DataFrame) -> pl.DataFrame:
    """2010（0003038618）用。家族類型=cat01・測度=tab(6/7)・住居の所有=cat02(000総数で周辺化)。不詳は導出。"""
    return _two_measures(
        tidy,
        ft_col="cat01",
        ft_map=_FT_2010,
        measure_col="tab",
        hh_code="6",
        mem_code="7",
        filters=[("cat02_code", "000")],
    )


def clean_2015(tidy: pl.DataFrame) -> pl.DataFrame:
    """2015（0003148560）用。家族類型=cat02（4桁・不詳0330あり）・世帯数のみ(tab6)・全域=cat01(00710)・世帯人員=cat03(0000で周辺化)。"""
    return _households_only(
        tidy,
        ft_col="cat02",
        ft_map=_FT_2015,
        filters=[("cat01_code", "00710"), ("cat03_code", "0000")],
    )


def clean_2020(tidy: pl.DataFrame) -> pl.DataFrame:
    """2020（0003445080）用。家族類型=cat02（不詳"4"あり）・世帯人員の人数=cat01("0"総数で周辺化）・tab=一般世帯数のみ。"""
    return _households_only(tidy, ft_col="cat02", ft_map=_FT_2020, filters=[("cat01_code", "0")])
